#!/usr/bin/env python3
"""Approve a draft topic by moving it to topics/approved/."""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone

from lib import TOPICS_DIR, load_json, save_json, slugify


def approve(topic_id: str) -> None:
    topic_id = slugify(topic_id)
    draft_path = TOPICS_DIR / "draft" / f"{topic_id}.json"
    if not draft_path.exists():
        raise SystemExit(f"Draft not found: {draft_path}")

    topic = load_json(draft_path)
    topic["status"] = "approved"
    topic.setdefault("meta", {})
    topic["meta"]["approved_at"] = datetime.now(timezone.utc).isoformat()

    approved_dir = TOPICS_DIR / "approved"
    approved_dir.mkdir(parents=True, exist_ok=True)
    approved_path = approved_dir / f"{topic_id}.json"
    save_json(approved_path, topic)
    draft_path.unlink()
    print(f"Approved: {approved_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Approve draft topic.")
    parser.add_argument("--id", required=True)
    args = parser.parse_args()
    approve(args.id)


if __name__ == "__main__":
    main()
