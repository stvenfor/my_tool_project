#!/usr/bin/env python3
"""Download and deconstruct a Douyin reference video for bilingual city promos."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent
sys.path.insert(0, str(ROOT))

from lib import (  # noqa: E402
    DEFAULT_OUTPUT_ROOT,
    assign_shot_phases,
    audio_to_wav,
    download_reference_video,
    extract_audio_from_video,
    get_audio_duration,
    infer_day_night_pivot,
    load_json,
    probe_video,
    run_cmd,
    save_json,
    slugify,
)


def _load_extract_reference_cuts():
    beat_root = PROJECT_ROOT / "modules" / "shared" / "media"
    sys.path.insert(0, str(beat_root))
    module_path = beat_root / "extract_reference_cuts.py"
    spec = importlib.util.spec_from_file_location("extract_reference_cuts", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.extract_reference_cuts


def _probe_frame_brightness(video_path: Path, timestamp: float) -> float:
    result = subprocess.run(
        [
            "ffmpeg",
            "-ss",
            str(timestamp),
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        return 0.5
    data = result.stdout
    return sum(data) / (255 * len(data))


def _detect_day_night_pivot(video_path: Path, duration_sec: float, cuts: list[dict[str, Any]]) -> float:
    if not cuts:
        return duration_sec * 0.5
    sample_times = [float(c["time"]) for c in cuts]
    brightness = [_probe_frame_brightness(video_path, max(0.1, t)) for t in sample_times]
    if len(brightness) < 3:
        return infer_day_night_pivot(cuts)
    diffs = [brightness[i + 1] - brightness[i] for i in range(len(brightness) - 1)]
    if not diffs:
        return infer_day_night_pivot(cuts)
    pivot_index = min(range(len(diffs)), key=lambda i: diffs[i])
    return float(cuts[min(pivot_index + 1, len(cuts) - 1)]["time"])


def _transcribe_audio(audio_wav: Path, language: str) -> str:
    try:
        import whisper
    except ImportError:
        print("whisper not installed; skipping transcription")
        return ""

    model = whisper.load_model("base")
    result = model.transcribe(str(audio_wav), language=language, fp16=False)
    return str(result.get("text", "")).strip()


def _segments_from_text(text: str, duration_sec: float) -> list[dict[str, Any]]:
    chunks = [part.strip() for part in re.split(r"[.!?。！？\n]+", text) if part.strip()]
    if not chunks:
        return []
    seg_dur = duration_sec / len(chunks)
    segments: list[dict[str, Any]] = []
    cursor = 0.0
    for chunk in chunks:
        segments.append(
            {
                "start_sec": round(cursor, 3),
                "end_sec": round(cursor + seg_dur, 3),
                "en": chunk if re.search(r"[A-Za-z]", chunk) else "",
                "zh": chunk if re.search(r"[\u4e00-\u9fff]", chunk) else "",
            }
        )
        cursor += seg_dur
    return segments


def _build_style_profile(video_meta: dict[str, Any], pivot_sec: float) -> dict[str, Any]:
    return {
        "aspect": "9:16",
        "width": video_meta["width"],
        "height": video_meta["height"],
        "fps": video_meta["fps"],
        "grade": {
            "day_warmth": 0.15,
            "night_warmth": 0.55,
            "pivot_sec": pivot_sec,
        },
        "subtitle": {
            "mode": "zh_en",
            "position": "bottom",
            "zh_size": 34,
            "en_size": 22,
            "margin_bottom": 180,
            "color_zh": "#ffffff",
            "color_en": "#f0d8a8",
            "shadow": "0 2px 12px rgba(0,0,0,0.55)",
        },
        "hook": {
            "duration_sec": 2.5,
            "font_size": 46,
            "color": "#fff8ec",
        },
        "transition": {
            "default": "crossfade",
            "flash_on_beat": False,
            "crossfade_frames": 10,
        },
    }


def analyze_reference(
    url: str,
    work_dir: Path,
    caption: str = "",
    max_duration: float = 90.0,
) -> dict[str, Any]:
    ref_dir = work_dir / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)

    source_mp4 = ref_dir / "source.mp4"
    source_audio = ref_dir / "source.audio.m4a"
    audio_wav = ref_dir / "audio.wav"
    bgm_wav = ref_dir / "bgm.wav"

    if not source_mp4.exists() or source_mp4.stat().st_size < 10000:
        download_reference_video(url, source_mp4)

    if not source_audio.exists():
        sidecar = source_mp4.with_suffix(".audio.m4a")
        if sidecar.exists():
            source_audio.write_bytes(sidecar.read_bytes())
        else:
            extract_audio_from_video(source_mp4, source_audio)

    audio_to_wav(source_audio, audio_wav)
    audio_to_wav(source_audio, bgm_wav)

    video_meta = probe_video(source_mp4)
    duration_sec = min(float(video_meta["duration_sec"]), max_duration)

    extract_reference_cuts = _load_extract_reference_cuts()
    cuts_payload = extract_reference_cuts(
        source_mp4,
        max_duration=duration_sec,
        scene_threshold=0.28,
        min_duration=0.35,
        max_seg_duration=2.5,
    )
    cuts = cuts_payload.get("cuts", [])
    pivot_sec = _detect_day_night_pivot(source_mp4, duration_sec, cuts)
    shots = assign_shot_phases(cuts, pivot_sec)

    beats_path = ref_dir / "beats.json"
    analyze_beats = PROJECT_ROOT / "scripts" / "beat-montage" / "analyze_beats.py"
    if analyze_beats.exists():
        result = run_cmd(
            [
                sys.executable,
                str(analyze_beats),
                str(bgm_wav),
                "--output",
                str(beats_path),
                "--max-duration",
                str(duration_sec),
            ]
        )
        if result.returncode != 0:
            print(result.stderr or result.stdout)
            beats = {"bpm": 90, "beats": []}
            save_json(beats_path, beats)
    else:
        beats = {"bpm": 90, "beats": []}
        save_json(beats_path, beats)

    en_text = _transcribe_audio(audio_wav, "en")
    zh_text = _transcribe_audio(audio_wav, "zh")
    hook_zh = caption or "白天是西安，晚上是长安"
    segments = _segments_from_text(en_text or zh_text, duration_sec)

    transcript = {
        "hook_zh": hook_zh,
        "en_full": en_text,
        "zh_full": zh_text,
        "segments": segments,
    }
    save_json(ref_dir / "transcript.json", transcript)

    style_profile = _build_style_profile(video_meta, pivot_sec)
    save_json(ref_dir / "style_profile.json", style_profile)

    cuts_out = {
        **cuts_payload,
        "shots": shots,
        "day_night_pivot_sec": pivot_sec,
    }
    save_json(ref_dir / "reference_cuts.json", cuts_out)

    manifest = {
        "source_url": url,
        "source_mp4": "reference/source.mp4",
        "source_audio": "reference/source.audio.m4a",
        "audio_wav": "reference/audio.wav",
        "bgm_wav": "reference/bgm.wav",
        "caption": hook_zh,
        "duration_sec": duration_sec,
        "width": video_meta["width"],
        "height": video_meta["height"],
        "fps": video_meta["fps"],
        "has_english_vo": bool(en_text),
        "has_chinese_subtitle": True,
        "day_night_pivot_sec": pivot_sec,
        "cut_count": len(shots),
        "audio_duration_sec": round(get_audio_duration(audio_wav), 3),
    }
    save_json(ref_dir / "reference_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze Douyin reference for bilingual city video.")
    parser.add_argument("--url", required=True, help="Douyin share URL")
    parser.add_argument("--city", default="西安", help="City name for output folder")
    parser.add_argument("--caption", default="", help="Override caption/hook")
    parser.add_argument("--work-dir", default="", help="Override output work dir")
    args = parser.parse_args()

    if args.work_dir:
        work_dir = Path(args.work_dir).resolve()
    else:
        work_dir = DEFAULT_OUTPUT_ROOT / slugify(args.city)

    work_dir.mkdir(parents=True, exist_ok=True)
    manifest = analyze_reference(args.url, work_dir, caption=args.caption)
    print(f"Reference pack saved: {work_dir / 'reference'}")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
