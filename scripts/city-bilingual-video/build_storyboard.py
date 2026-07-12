#!/usr/bin/env python3
"""Build bilingual storyboard.json."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import load_json, resolve_work_dir, save_json  # noqa: E402


def prepare_ambient_bgm(work_dir: Path, duration_sec: float, output_name: str = "ambient_bgm.wav") -> Path | None:
    """Create low-volume ambient bed from reference audio with vocal attenuation."""
    import subprocess

    candidates = [
        work_dir / "reference" / "audio.wav",
        work_dir / "reference" / "bgm.wav",
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


def load_clips_manifest(work_dir: Path) -> list[dict[str, Any]]:
    manifest_path = work_dir / "clips_manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"Missing clips manifest: {manifest_path}")
    payload = load_json(manifest_path)
    return payload.get("clips", payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build bilingual storyboard.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)

    fps = int(config.get("fps", 30))
    duration_sec = float(config.get("duration_sec", 51.233))
    width = int(config.get("width", 1080))
    height = int(config.get("height", 1920))

    clips = load_clips_manifest(work_dir)
    subtitles_path = work_dir / "subtitles.json"
    subtitles = load_json(subtitles_path) if subtitles_path.exists() else {"segments": [], "hook_zh": ""}

    style_profile_path = work_dir / "reference" / "style_profile.json"
    style_profile = load_json(style_profile_path) if style_profile_path.exists() else {}

    manifest_path = work_dir / "reference" / "reference_manifest.json"
    manifest = load_json(manifest_path) if manifest_path.exists() else {}

    shots: list[dict[str, Any]] = []
    cursor = 0.0
    for clip in clips:
        duration = float(clip.get("duration_sec", 2.0))
        shots.append(
            {
                "id": clip["id"],
                "clip": clip["clip"],
                "is_image": bool(clip.get("is_image", False)),
                "start_sec": round(cursor, 3),
                "duration_sec": duration,
                "phase": clip.get("phase", "day"),
                "transition": "crossfade",
            }
        )
        cursor += duration

    if cursor > 0 and abs(cursor - duration_sec) > 0.2:
        scale = duration_sec / cursor
        cursor = 0.0
        for shot in shots:
            shot["duration_sec"] = round(shot["duration_sec"] * scale, 3)
            shot["start_sec"] = round(cursor, 3)
            cursor += shot["duration_sec"]

    bgm_rel = ""
    if config.get("use_ambient_bgm", True):
        ambient = prepare_ambient_bgm(work_dir, duration_sec)
        if ambient:
            bgm_rel = ambient.name
            print(f"Ambient BGM: {ambient}")
    elif config.get("use_reference_bgm", False):
        ref_bgm = work_dir / "reference" / "bgm.wav"
        if ref_bgm.exists():
            shutil.copy2(ref_bgm, work_dir / "bgm.wav")
            bgm_rel = "bgm.wav"

    transition_frames = int(config.get("transition_frames", 0))

    pivot_sec = float(
        manifest.get("day_night_pivot_sec")
        or style_profile.get("grade", {}).get("pivot_sec", duration_sec * 0.5)
    )

    storyboard = {
        "style": "bilingual_travel",
        "city_name": config.get("city_name", ""),
        "ancient_name": config.get("ancient_name", ""),
        "fps": fps,
        "width": width,
        "height": height,
        "duration_sec": duration_sec,
        "duration_in_frames": int(round(duration_sec * fps)),
        "transition_frames": transition_frames,
        "narration": "narration.wav" if (work_dir / "narration.wav").exists() else "",
        "narration_volume": float(config.get("narration_volume", 0.55)),
        "bgm": bgm_rel,
        "bgm_volume": float(config.get("ambient_bgm_volume", config.get("bgm_volume", 0.08))),
        "hook": {
            "text_zh": subtitles.get("hook_zh", config.get("hook_zh", "")),
            "duration_sec": float(subtitles.get("hook_duration_sec", 2.5)),
        },
        "subtitles": subtitles.get("segments", []),
        "subtitle_style": style_profile.get("subtitle", {}),
        "grade": style_profile.get("grade", {"day_warmth": 0.15, "night_warmth": 0.55, "pivot_sec": pivot_sec}),
        "shots": shots,
        "closing_title": {
            "text_zh": config.get("hook_zh", ""),
            "text_en": f"Day is {config.get('city_name', '')}. Night is {config.get('ancient_name', '')}.",
            "appear_at_sec": max(0.0, duration_sec - 4.0),
            "duration_sec": 4.0,
        },
    }

    output_path = work_dir / "storyboard.json"
    save_json(output_path, storyboard)
    print(f"Storyboard saved: {output_path}")
    print(f"Shots: {len(shots)}, span ~{cursor:.1f}s")


if __name__ == "__main__":
    main()
