#!/usr/bin/env python3
"""Build storyboard.json for ViralDubVideo (full reference clip + bilingual subs)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import load_json, resolve_work_dir, save_json  # noqa: E402


def prepare_ambient_bgm(work_dir: Path, duration_sec: float, output_name: str = "ambient_bgm.wav") -> Path | None:
    candidates = [
        work_dir / "reference" / "audio.wav",
        work_dir / "reference" / "source.audio.m4a",
    ]
    source = next((p for p in candidates if p.exists()), None)
    if source is None:
        return None

    output = work_dir / output_name
    fade_out_start = max(0.0, duration_sec - 2.5)
    af = (
        "pan=stereo|c0=0.5*c0+-0.5*c1|c1=0.5*c1+-0.5*c0,"
        "highpass=f=180,lowpass=f=5200,volume=0.18,"
        f"afade=t=in:st=0:d=2,afade=t=out:st={fade_out_start:.3f}:d=2.5"
    )
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-t",
            str(duration_sec),
            "-af",
            af,
            "-ac",
            "1",
            "-ar",
            "44100",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not output.exists():
        print(result.stderr or result.stdout)
        return None
    return output


def build_storyboard(config: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    manifest_path = work_dir / "reference" / "reference_manifest.json"
    manifest = load_json(manifest_path) if manifest_path.exists() else {}

    fps = int(config.get("fps", manifest.get("fps", 30)))
    width = int(config.get("width", manifest.get("width", 1080)))
    height = int(config.get("height", manifest.get("height", 1920)))

    timeline_path = work_dir / "timeline.json"
    timeline = load_json(timeline_path) if timeline_path.exists() else {}
    subtitles_path = work_dir / "subtitles.json"
    subtitles = load_json(subtitles_path) if subtitles_path.exists() else {"segments": []}

    duration_sec = float(
        timeline.get("duration_sec")
        or subtitles.get("duration_sec")
        or config.get("duration_sec")
        or manifest.get("duration_sec")
        or 30
    )
    video_pieces = timeline.get("video_pieces") or []

    source_rel = "reference/source.mp4"
    if not (work_dir / source_rel).exists():
        raise SystemExit(f"Missing reference video: {work_dir / source_rel}")

    bgm_rel = ""
    if (work_dir / "final_audio.wav").exists():
        narration_rel = "final_audio.wav"
        bgm_rel = ""
    else:
        narration_rel = "narration.wav" if (work_dir / "narration.wav").exists() else ""
        if config.get("keep_bgm", True) and (work_dir / "reference" / "bgm_stem.wav").exists():
            bgm_rel = "reference/bgm_stem.wav"
        elif config.get("use_ambient_bgm", False):
            ambient = prepare_ambient_bgm(work_dir, duration_sec)
            if ambient:
                bgm_rel = ambient.name

    margin_bottom = int(config.get("subtitle_margin_bottom", int(height * 0.20) if height < width else 160))
    subtitle_position = str(config.get("subtitle_position", "bottom")).strip().lower()

    storyboard = {
        "style": "viral_english_dub",
        "clip_id": config.get("clip_id", work_dir.name),
        "title": config.get("title", "Classic scene in English"),
        "fps": fps,
        "width": width,
        "height": height,
        "duration_sec": duration_sec,
        "duration_in_frames": int(round(duration_sec * fps)),
        "source_video": source_rel,
        "video_pieces": video_pieces,
        "narration": narration_rel,
        "narration_volume": float(config.get("narration_volume", 1.0)),
        "bgm": bgm_rel,
        "bgm_volume": float(config.get("bgm_volume", 0.72)),
        "show_hook_title": bool(config.get("show_hook_title", False)),
        "show_subtitles": bool(config.get("show_subtitles", True)),
        "hide_original_subtitles": bool(config.get("hide_original_subtitles", True)),
        "subtitle_mask": config.get(
            "subtitle_mask",
            {"top_pct": 0.0, "bottom_pct": 0.0, "color": "#000000"},
        ),
        "hook": {
            "text_en": subtitles.get("hook_en", config.get("hook_en", config.get("title", ""))),
            "duration_sec": float(subtitles.get("hook_duration_sec", config.get("hook_duration_sec", 1.5))),
        },
        "subtitles": subtitles.get("segments", []),
        "subtitle_style": {
            "en_size": 26 if height < width else 28,
            "zh_size": 20 if height < width else 22,
            "margin_bottom": margin_bottom,
            "position": subtitle_position if subtitle_position in {"bottom", "center"} else "bottom",
            "color_en": "#ffffff",
            "color_zh": "#f0d8a8",
            "shadow": "0 2px 12px rgba(0,0,0,0.75)",
        },
    }

    output_path = work_dir / "storyboard.json"
    save_json(output_path, storyboard)
    return storyboard


def main() -> None:
    parser = argparse.ArgumentParser(description="Build viral dub storyboard.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)

    storyboard = build_storyboard(config, work_dir)
    print(f"Storyboard saved: {work_dir / 'storyboard.json'}")
    print(f"Duration: {storyboard['duration_sec']}s, subtitles: {len(storyboard['subtitles'])}")


if __name__ == "__main__":
    main()
