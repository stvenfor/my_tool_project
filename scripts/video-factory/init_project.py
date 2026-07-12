#!/usr/bin/env python3
"""Initialize a video-factory project from a topic definition."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from lib import (
    DEFAULT_OUTPUT_ROOT,
    PROJECT_ROOT,
    apply_character_assets,
    apply_series_assets,
    copy_if_missing,
    load_json,
    project_work_dir,
    save_json,
    slugify,
    topic_path,
    write_project_config,
)
from modes.narration import migrate_from_cognitive


def init_from_topic(topic_id: str, status: str = "approved", force: bool = False) -> Path:
    topic_file = topic_path(topic_id, status)
    if not topic_file.exists():
        alt = topic_path(topic_id, "draft")
        if alt.exists():
            topic_file = alt
        else:
            raise SystemExit(f"Topic not found: {topic_id}")

    topic = load_json(topic_file)
    project_id = str(topic.get("id", topic_id))
    work_dir = project_work_dir(project_id)
    work_dir.mkdir(parents=True, exist_ok=True)

    if force and work_dir.exists():
        for child in work_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    config = apply_character_assets(apply_series_assets(dict(topic)))
    config["project_id"] = project_id
    config.setdefault("mode", "narration")
    config.setdefault("visual_strategy", "stickman")
    config.setdefault("voice_strategy", "edge_tts")
    config.setdefault("width", 1080)
    config.setdefault("height", 1920)
    config.setdefault("fps", 30)
    write_project_config(work_dir, config)

    script_source = topic.get("script_source")
    if script_source:
        src = Path(str(script_source))
        if not src.is_absolute():
            src = PROJECT_ROOT / src
        if src.exists():
            shutil.copy2(src, work_dir / "script.json")

    migrate_key = topic.get("migrate_from_cognitive", project_id)
    if topic.get("migrate_from_cognitive") is not False:
        migrate_from_cognitive(str(migrate_key), work_dir)

    presenter = topic.get("presenter_image")
    if presenter:
        src = Path(str(presenter))
        if not src.is_absolute():
            src = PROJECT_ROOT / src
        if src.exists():
            dest = work_dir / "presenter.png"
            copy_if_missing(src, dest)
            config["presenter_image"] = str(dest.relative_to(work_dir))

    save_json(work_dir / "topic.json", topic)
    print(f"Initialized: {work_dir}")
    return work_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Init video-factory project.")
    parser.add_argument("--id", required=True, help="Topic / project id")
    parser.add_argument("--status", default="approved", choices=["draft", "approved"])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    init_from_topic(args.id, status=args.status, force=args.force)


if __name__ == "__main__":
    main()
