#!/usr/bin/env python3
"""Generate AI video clips via videoagent-video-studio proxy."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent
VIDEOAGENT_TOOL = Path.home() / ".agents" / "skills" / "videoagent-video-studio" / "tools" / "generate.js"

sys.path.insert(0, str(ROOT))

from lib import build_scene_prompts, load_json, resolve_work_dir, save_json  # noqa: E402


def download_video(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response:
        dest.write_bytes(response.read())


def generate_clip(
    prompt: str,
    duration: int,
    aspect_ratio: str,
    model: str,
) -> dict:
    if not VIDEOAGENT_TOOL.exists():
        raise FileNotFoundError(f"videoagent tool not found: {VIDEOAGENT_TOOL}")

    cmd = [
        "node",
        str(VIDEOAGENT_TOOL),
        "--mode",
        "text-to-video",
        "--prompt",
        prompt,
        "--duration",
        str(duration),
        "--aspect-ratio",
        aspect_ratio,
    ]
    if model:
        cmd.extend(["--model", model])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)

    payload = json.loads(result.stdout)
    if not payload.get("success"):
        raise RuntimeError(payload.get("error") or "video generation failed")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate city-healing AI clips.")
    parser.add_argument("--config", required=True, help="Path to city.config.json")
    parser.add_argument("--model", default="kling", help="videoagent model id")
    parser.add_argument("--aspect-ratio", default="9:16")
    parser.add_argument("--scene", default="", help="Generate only one scene id, e.g. S01")
    parser.add_argument("--placeholder-on-fail", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)
    clips_dir = work_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    scenes = build_scene_prompts(config)
    if args.scene:
        scenes = [scene for scene in scenes if scene["id"] == args.scene]
        if not scenes:
            raise SystemExit(f"Scene not found: {args.scene}")

    manifest: list[dict] = []
    failures: list[str] = []

    for scene in scenes:
        out_path = clips_dir / f"{scene['id']}.mp4"
        if out_path.exists() and out_path.stat().st_size > 0:
            print(f"Skip existing clip: {out_path}")
            manifest.append(
                {
                    "id": scene["id"],
                    "clip": f"clips/{scene['id']}.mp4",
                    "is_image": False,
                    "duration_sec": scene.get("duration_sec", 6),
                    "zh_desc": scene["zh_desc"],
                    "source": "cached",
                }
            )
            continue

        print(f"Generating {scene['id']} — {scene['zh_desc']}")
        try:
            payload = generate_clip(
                prompt=scene["prompt_en"],
                duration=int(scene.get("gen_duration_sec", 5)),
                aspect_ratio=args.aspect_ratio,
                model=args.model,
            )
            video_url = payload.get("videoUrl")
            if not video_url:
                raise RuntimeError("missing videoUrl in response")
            download_video(video_url, out_path)
            manifest.append(
                {
                    "id": scene["id"],
                    "clip": f"clips/{scene['id']}.mp4",
                    "is_image": False,
                    "duration_sec": scene.get("duration_sec", 6),
                    "zh_desc": scene["zh_desc"],
                    "source": "videoagent",
                    "video_url": video_url,
                }
            )
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{scene['id']}: {exc}")
            print(f"Failed {scene['id']}: {exc}", file=sys.stderr)

    if failures and args.placeholder_on_fail:
        print("Falling back to placeholder clips for failed scenes...")
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "generate_placeholder_clips.py"),
                "--config",
                str(config_path),
            ],
            check=False,
        )
        placeholder_manifest = load_json(work_dir / "clips_manifest.json")
        existing_ids = {item["id"] for item in manifest}
        for item in placeholder_manifest:
            if item["id"] not in existing_ids:
                manifest.append(item)
        failures = []

    manifest.sort(key=lambda item: item["id"])
    save_json(work_dir / "clips_manifest.json", {"clips": manifest, "failures": failures})

    if failures:
        raise SystemExit(f"Clip generation incomplete: {len(failures)} failures")

    print(f"Clips saved to {clips_dir}")


if __name__ == "__main__":
    main()
