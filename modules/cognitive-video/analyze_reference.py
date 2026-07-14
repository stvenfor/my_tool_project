#!/usr/bin/env python3
"""Download and deconstruct a Douyin cognitive/explainer reference video."""

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
    audio_to_wav,
    download_reference_video,
    extract_audio_from_video,
    get_audio_duration,
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


def _transcribe_audio(audio_wav: Path, language: str = "zh") -> tuple[str, list[dict[str, Any]]]:
    try:
        import whisper
    except ImportError:
        print("whisper not installed; skipping transcription")
        return "", []

    model = whisper.load_model("base")
    result = model.transcribe(str(audio_wav), language=language, fp16=False)
    full_text = str(result.get("text", "")).strip()
    segments: list[dict[str, Any]] = []
    for seg in result.get("segments", []):
        segments.append(
            {
                "start_sec": round(float(seg.get("start", 0)), 3),
                "end_sec": round(float(seg.get("end", 0)), 3),
                "text": str(seg.get("text", "")).strip(),
            }
        )
    return full_text, segments


def _segments_from_text(text: str, duration_sec: float) -> list[dict[str, Any]]:
    chunks = [part.strip() for part in re.split(r"[。！？\n]+", text) if part.strip()]
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
                "text": chunk,
            }
        )
        cursor += seg_dur
    return segments


def _build_style_profile(video_meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "aspect": "9:16",
        "width": video_meta["width"],
        "height": video_meta["height"],
        "fps": video_meta["fps"],
        "grade": {
            "warmth": 0.35,
            "contrast": 1.05,
            "vignette": 0.25,
        },
        "subtitle": {
            "mode": "zh",
            "position": "bottom",
            "zh_size": 36,
            "margin_bottom": 200,
            "color_zh": "#ffffff",
            "shadow": "0 2px 12px rgba(0,0,0,0.55)",
        },
        "hook": {
            "duration_sec": 2.8,
            "font_size": 44,
            "color": "#fff8ec",
        },
        "series_badge": {
            "font_size": 22,
            "color": "#f0d8a8",
            "position": "top-left",
        },
        "emphasis": {
            "font_size": 52,
            "color": "#ffe8b0",
            "position": "center",
        },
        "transition": {
            "default": "crossfade",
            "crossfade_frames": 8,
        },
    }


def analyze_reference(
    url: str,
    work_dir: Path,
    caption: str = "",
    title: str = "",
    series: str = "认知提升",
    episode: str = "01",
    max_duration: float = 120.0,
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
        scene_threshold=0.22,
        min_duration=0.4,
        max_seg_duration=3.0,
    )
    cuts = cuts_payload.get("cuts", [])

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
            save_json(beats_path, {"bpm": 90, "beats": []})
    else:
        save_json(beats_path, {"bpm": 90, "beats": []})

    zh_text, whisper_segments = _transcribe_audio(audio_wav, "zh")
    if not whisper_segments and zh_text:
        whisper_segments = _segments_from_text(zh_text, duration_sec)

    hook_zh = caption or title or "去换个活法吧"
    transcript = {
        "hook_zh": hook_zh,
        "title": title,
        "series": series,
        "episode": episode,
        "zh_full": zh_text,
        "segments": whisper_segments,
    }
    save_json(ref_dir / "transcript.json", transcript)

    style_profile = _build_style_profile(video_meta)
    save_json(ref_dir / "style_profile.json", style_profile)

    cuts_out = {
        **cuts_payload,
        "cut_count": len(cuts),
    }
    save_json(ref_dir / "reference_cuts.json", cuts_out)

    manifest = {
        "source_url": url,
        "source_mp4": "reference/source.mp4",
        "source_audio": "reference/source.audio.m4a",
        "audio_wav": "reference/audio.wav",
        "bgm_wav": "reference/bgm.wav",
        "caption": hook_zh,
        "title": title,
        "series": series,
        "episode": episode,
        "duration_sec": duration_sec,
        "width": video_meta["width"],
        "height": video_meta["height"],
        "fps": video_meta["fps"],
        "cut_count": len(cuts),
        "audio_duration_sec": round(get_audio_duration(audio_wav), 3),
        "has_transcript": bool(zh_text),
    }
    save_json(ref_dir / "reference_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze Douyin cognitive reference video.")
    parser.add_argument("--url", required=True, help="Douyin share URL")
    parser.add_argument("--id", default="middle-class-exit", help="Topic id / work dir name")
    parser.add_argument("--caption", default="", help="Override hook/caption")
    parser.add_argument("--title", default="中产退场 低欲生活才是赢家", help="Video title")
    parser.add_argument("--series", default="认知提升")
    parser.add_argument("--episode", default="01")
    parser.add_argument("--work-dir", default="", help="Override output work dir")
    args = parser.parse_args()

    if args.work_dir:
        work_dir = Path(args.work_dir).resolve()
    else:
        work_dir = DEFAULT_OUTPUT_ROOT / slugify(args.id)

    work_dir.mkdir(parents=True, exist_ok=True)
    manifest = analyze_reference(
        args.url,
        work_dir,
        caption=args.caption,
        title=args.title,
        series=args.series,
        episode=args.episode,
    )
    print(f"Reference pack saved: {work_dir / 'reference'}")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
