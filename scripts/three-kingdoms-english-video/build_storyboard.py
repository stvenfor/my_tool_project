#!/usr/bin/env python3
"""Build Three Kingdoms English storyboard.json for Remotion."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import load_json, resolve_work_dir, save_json  # noqa: E402


def prepare_bgm(work_dir: Path, duration_sec: float) -> Path | None:
    candidates = [
        work_dir / "reference" / "bgm.wav",
        work_dir / "reference" / "audio.wav",
        ROOT.parent.parent / "_three-kingdoms-english/reference/yijia-xuchang/reference/bgm.wav",
    ]
    source = next((p for p in candidates if p.exists()), None)
    if source is None:
        return None

    output = work_dir / "bgm.wav"
    fade_out_start = max(0.0, duration_sec - 2.5)
    af = (
        "highpass=f=180,lowpass=f=5200,volume=0.22,"
        f"afade=t=in:st=0:d=2,afade=t=out:st={fade_out_start:.3f}:d=2.5"
    )
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(source), "-t", str(duration_sec), "-af", af, "-ac", "1", "-ar", "44100", str(output)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Three Kingdoms storyboard.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)

    fps = int(config.get("fps", 30))
    duration_sec = float(config.get("duration_sec", 141.767))
    width = int(config.get("width", 1080))
    height = int(config.get("height", 1920))

    clips = load_json(work_dir / "clips_manifest.json").get("clips", [])
    subtitles = load_json(work_dir / "subtitles.json")

    style_path = work_dir / "reference" / "style_profile.json"
    if not style_path.exists():
        alt = ROOT.parent.parent / "_three-kingdoms-english/reference/yijia-xuchang/reference/style_profile.json"
        style_path = alt if alt.exists() else style_path
    style_profile = load_json(style_path) if style_path.exists() else {}

    clip_by_id = {c["id"]: c for c in clips}
    shots: list[dict[str, Any]] = []
    shot_plan_path = work_dir / "shot_plan.json"
    if shot_plan_path.exists():
        for shot in load_json(shot_plan_path).get("shots", []):
            clip = clip_by_id.get(shot["id"], {})
            shots.append(
                {
                    "id": shot["id"],
                    "clip": clip.get("clip", shot.get("clip", "")),
                    "is_image": bool(clip.get("is_image", False)),
                    "start_sec": float(shot.get("start_sec", 0)),
                    "duration_sec": float(shot.get("duration_sec", 2.0)),
                    "phase": shot.get("phase", "story"),
                    "transition": "none",
                }
            )
        max_end = max((s["start_sec"] + s["duration_sec"]) for s in shots)
        duration_sec = max(duration_sec, max_end)
    else:
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
                    "phase": clip.get("phase", "story"),
                    "transition": "crossfade",
                }
            )
            cursor += duration

    bgm_rel = ""
    if config.get("use_reference_bgm", True):
        bgm = prepare_bgm(work_dir, duration_sec)
        if bgm:
            bgm_rel = bgm.name

    storyboard = {
        "style": "three_kingdoms_english",
        "series_title": config.get("series_title", "儿童英语三国"),
        "episode_title": config.get("episode_title", ""),
        "episode_hook": config.get("episode_hook", ""),
        "fps": fps,
        "width": width,
        "height": height,
        "duration_sec": duration_sec,
        "duration_in_frames": int(round(duration_sec * fps)),
        "transition_frames": int(config.get("transition_frames", 0)),
        "narration": "narration.wav" if (work_dir / "narration.wav").exists() else "",
        "narration_volume": float(config.get("narration_volume", 0.85)),
        "bgm": bgm_rel,
        "bgm_volume": float(config.get("bgm_volume", 0.25)),
        "hook": {
            "text_zh": subtitles.get("hook_zh", config.get("hook_zh", "")),
            "text_en": subtitles.get("hook_en", ""),
            "duration_sec": float(subtitles.get("hook_duration_sec", 3.0)),
        },
        "subtitles": subtitles.get("segments", []),
        "subtitle_style": style_profile.get("subtitle", {}),
        "shots": shots,
        "closing_title": {
            "text_zh": f"【{config.get('episode_title', '')}】{config.get('episode_hook', '')}",
            "text_en": config.get("episode_hook", ""),
            "appear_at_sec": max(0.0, duration_sec - 5.0),
            "duration_sec": 5.0,
        },
    }

    save_json(work_dir / "storyboard.json", storyboard)
    print(f"Storyboard saved: {work_dir / 'storyboard.json'} ({len(shots)} shots)")


if __name__ == "__main__":
    main()
