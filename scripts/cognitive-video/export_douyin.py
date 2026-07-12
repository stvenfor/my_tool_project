#!/usr/bin/env python3
"""Export douyin-video.json for cognitive video publish."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent
sys.path.insert(0, str(ROOT))

from lib import load_json, resolve_work_dir, save_json  # noqa: E402


def export_douyin(config: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    script = load_json(work_dir / "script.json") if (work_dir / "script.json").exists() else {}
    storyboard = load_json(work_dir / "storyboard.json") if (work_dir / "storyboard.json").exists() else {}

    title = str(script.get("title", config.get("title", "认知提升")))
    if len(title) > 30:
        title = title[:30]

    tags = script.get("tags", config.get("tags", []))[:5]
    hook = str(script.get("hook", config.get("hook", "")))
    cta = str(script.get("cta", config.get("cta", "建议收藏")))
    series = str(script.get("series", config.get("series", "认知提升")))
    episode = str(script.get("episode", config.get("episode", "01")))

    description = f"{hook} {cta} {series}{episode}"

    video_path = work_dir / "output" / "final.mp4"
    if not video_path.exists():
        video_path = work_dir / "final.mp4"

    rel_video = "output/final.mp4" if (work_dir / "output" / "final.mp4").exists() else "final.mp4"

    payload = {
        "videoPath": rel_video,
        "title": title,
        "description": description,
        "tags": tags,
    }
    save_json(work_dir / "douyin-video.json", payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Export douyin-video.json.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)

    payload = export_douyin(config, work_dir)
    print(f"Douyin config: {work_dir / 'douyin-video.json'}")
    print(f"Title: {payload['title']}")


if __name__ == "__main__":
    main()
