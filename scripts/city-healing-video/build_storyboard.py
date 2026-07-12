#!/usr/bin/env python3
"""Build storyboard.json from config, clips, and narration."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import (  # noqa: E402
    build_scene_prompts,
    default_data_cards,
    load_json,
    resolve_work_dir,
    save_json,
)


def load_clips_manifest(work_dir: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    manifest_path = work_dir / "clips_manifest.json"
    if manifest_path.exists():
        payload = load_json(manifest_path)
        if isinstance(payload, dict) and "clips" in payload:
            return payload["clips"]
        if isinstance(payload, list):
            return payload

    scenes = build_scene_prompts(config)
    clips: list[dict[str, Any]] = []
    for scene in scenes:
        mp4 = work_dir / "clips" / f"{scene['id']}.mp4"
        png = work_dir / "clips" / f"{scene['id']}.png"
        if mp4.exists():
            clip = f"clips/{scene['id']}.mp4"
            is_image = False
        elif png.exists():
            clip = f"clips/{scene['id']}.png"
            is_image = True
        else:
            clip = f"clips/{scene['id']}.mp4"
            is_image = False
        clips.append(
            {
                "id": scene["id"],
                "clip": clip,
                "is_image": is_image,
                "duration_sec": scene.get("duration_sec", 6),
                "zh_desc": scene["zh_desc"],
            }
        )
    return clips


def main() -> None:
    parser = argparse.ArgumentParser(description="Build city-healing storyboard JSON.")
    parser.add_argument("--config", required=True, help="Path to city.config.json")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)
    work_dir.mkdir(parents=True, exist_ok=True)

    fps = int(config.get("fps", 30))
    duration_sec = float(config.get("duration_sec", 60))
    width = int(config.get("width", 1080))
    height = int(config.get("height", 1920))
    transition_frames = 12

    clips = load_clips_manifest(work_dir, config)
    scenes = build_scene_prompts(config)
    scene_map = {scene["id"]: scene for scene in scenes}

    shots: list[dict[str, Any]] = []
    cursor = 0.0
    for clip in clips:
        scene = scene_map.get(clip["id"], {})
        shot_duration = float(clip.get("duration_sec", scene.get("duration_sec", 6)))
        shots.append(
            {
                "id": clip["id"],
                "clip": clip["clip"],
                "is_image": bool(clip.get("is_image", False)),
                "start_sec": round(cursor, 3),
                "duration_sec": shot_duration,
                "transition_frames": transition_frames,
                "zh_desc": clip.get("zh_desc", scene.get("zh_desc", "")),
            }
        )
        cursor += shot_duration

    if cursor > duration_sec + 0.5:
        scale = duration_sec / cursor
        cursor = 0.0
        for shot in shots:
            shot["duration_sec"] = round(shot["duration_sec"] * scale, 3)
            shot["start_sec"] = round(cursor, 3)
            cursor += shot["duration_sec"]

    narration_rel = "narration.wav" if (work_dir / "narration.wav").exists() else ""
    bgm_rel = ""
    if (ROOT / "assets" / "ambient.mp3").exists():
        bgm_rel = "assets/ambient.mp3"

    storyboard = {
        "city_name": config.get("city_name", "【目标城市】"),
        "fps": fps,
        "width": width,
        "height": height,
        "duration_sec": duration_sec,
        "duration_in_frames": int(round(duration_sec * fps)),
        "transition_frames": transition_frames,
        "narration": narration_rel,
        "bgm": bgm_rel,
        "bgm_volume": float(config.get("bgm_volume", 0.12)),
        "shots": shots,
        "data_cards": default_data_cards(config),
        "closing_title": {
            "text": str(config.get("city_name", "【目标城市】")),
            "appear_at_sec": 54,
            "duration_sec": 6,
        },
    }

    output_path = work_dir / "storyboard.json"
    save_json(output_path, storyboard)
    print(f"Storyboard saved: {output_path}")
    print(f"Shots: {len(shots)}, total span ~{cursor:.1f}s")


if __name__ == "__main__":
    main()
