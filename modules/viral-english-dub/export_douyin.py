#!/usr/bin/env python3
"""Export douyin-video.json for viral english dub publish."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import load_json, resolve_work_dir, save_json  # noqa: E402


def export_douyin(config: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    script = load_json(work_dir / "script.json") if (work_dir / "script.json").exists() else {}

    title = str(script.get("title", config.get("title", "Classic scene in English")))
    if len(title) > 30:
        title = title[:30]

    tags = config.get("tags", ["English", "dub", "viral"])[:5]
    description = str(config.get("description", config.get("hook_en", title)))

    rel_video = "final.mp4" if (work_dir / "final.mp4").exists() else "output/final.mp4"
    if not (work_dir / rel_video).exists() and (work_dir / "output" / "final.mp4").exists():
        rel_video = "output/final.mp4"

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
