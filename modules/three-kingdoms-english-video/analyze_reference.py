#!/usr/bin/env python3
"""Analyze Douyin reference for Three Kingdoms English episodes."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent
sys.path.insert(0, str(ROOT))

from lib import (  # noqa: E402
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

REFERENCE_ROOT = Path(__file__).resolve().parent / "work" / "reference"


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


def _try_whisper(audio_wav: Path) -> dict[str, Any]:
    try:
        import whisper
    except ImportError:
        return {"segments": [], "full_text": "", "language": ""}

    model = whisper.load_model("tiny")
    result = model.transcribe(str(audio_wav), verbose=False)
    segments = [
        {"start_sec": round(float(s["start"]), 3), "end_sec": round(float(s["end"]), 3), "text": s["text"].strip()}
        for s in result.get("segments", [])
    ]
    return {"segments": segments, "full_text": result.get("text", "").strip(), "language": result.get("language", "")}


def analyze_reference(url: str, work_dir: Path, caption: str = "", skip_whisper: bool = False) -> dict[str, Any]:
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
            shutil.copy2(sidecar, source_audio)
        else:
            extract_audio_from_video(source_mp4, source_audio)

    audio_to_wav(source_audio, audio_wav)
    audio_to_wav(source_audio, bgm_wav)

    video_meta = probe_video(source_mp4)
    duration_sec = float(video_meta["duration_sec"])

    extract_reference_cuts = _load_extract_reference_cuts()
    cuts_payload = extract_reference_cuts(
        source_mp4,
        max_duration=duration_sec,
        scene_threshold=0.22,
        min_duration=0.5,
        max_seg_duration=8.0,
    )

    whisper_data = {} if skip_whisper else _try_whisper(audio_wav)
    transcript = {
        "hook_zh": caption,
        "language": whisper_data.get("language", ""),
        "full_text": whisper_data.get("full_text", ""),
        "whisper_segments": whisper_data.get("segments", []),
        "annotated_segments": load_json(ROOT / "copy" / "subtitles.template.json").get("segments", []),
        "note": "annotated_segments 为手工校对英中台词；whisper_segments 为自动转写参考",
    }
    save_json(ref_dir / "transcript.json", transcript)

    style_profile = {
        "aspect": "16:9_source",
        "output_aspect": "9:16",
        "width": video_meta["width"],
        "height": video_meta["height"],
        "fps": video_meta["fps"],
        "visual": {
            "style": "3D Q版三国动画，皮克斯黏土质感，暖色调",
            "characters": ["曹操", "汉献帝", "董昭", "徐晃"],
            "embedded_text_in_frame": True,
        },
        "subtitle": {
            "mode": "zh_en",
            "position": "top",
            "zh_size": 28,
            "en_size": 22,
            "margin_top": 80,
            "color_zh": "#ffffff",
            "color_en": "#ffe066",
            "shadow": "0 2px 8px rgba(0,0,0,0.7)",
        },
        "hook": {"duration_sec": 3.0, "font_size": 42, "format": "【移驾许昌】", "color": "#fff8ec"},
        "transition": {"default": "crossfade", "crossfade_frames": 8},
        "bgm": {"type": "light_children_music", "volume_ratio_to_voice": 0.25},
    }
    save_json(ref_dir / "style_profile.json", style_profile)
    save_json(ref_dir / "reference_cuts.json", cuts_payload)

    manifest = {
        "source_url": url,
        "video_id": "7660741104572157203",
        "source_mp4": "reference/source.mp4",
        "caption": caption,
        "duration_sec": duration_sec,
        "width": video_meta["width"],
        "height": video_meta["height"],
        "fps": video_meta["fps"],
        "cut_count": len(cuts_payload.get("cuts", [])),
        "audio_duration_sec": round(get_audio_duration(audio_wav), 3),
    }
    save_json(ref_dir / "reference_manifest.json", manifest)

    ref_copy = ref_dir / "reference.mp4"
    if not ref_copy.exists():
        shutil.copy2(source_mp4, ref_copy)

    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze Douyin reference for Three Kingdoms English.")
    parser.add_argument("--url", default="https://v.douyin.com/AAXEY5R5UMo/")
    parser.add_argument("--episode", default="移驾许昌")
    parser.add_argument("--caption", default="儿童英语三国【移驾许昌】从此曹操霸业开始")
    parser.add_argument("--work-dir", default="")
    parser.add_argument("--skip-whisper", action="store_true")
    args = parser.parse_args()

    work_dir = Path(args.work_dir).resolve() if args.work_dir else REFERENCE_ROOT / slugify(args.episode)
    work_dir.mkdir(parents=True, exist_ok=True)
    manifest = analyze_reference(args.url, work_dir, caption=args.caption, skip_whisper=args.skip_whisper)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
