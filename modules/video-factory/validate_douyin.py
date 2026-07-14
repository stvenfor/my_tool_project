#!/usr/bin/env python3
"""Validate douyin-video.json without launching a browser."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import load_json, project_work_dir  # noqa: E402


def validate(work_dir: Path) -> dict:
    douyin_path = work_dir / "douyin-video.json"
    if not douyin_path.exists():
        raise SystemExit(f"Missing {douyin_path}")

    meta = load_json(douyin_path)
    required = ["videoPath", "title", "description", "tags"]
    missing = [k for k in required if not meta.get(k)]
    video = work_dir / str(meta["videoPath"])
    checks = {
        "has_required_fields": not missing,
        "video_exists": video.exists(),
        "title_length_ok": 0 < len(str(meta.get("title", ""))) <= 30,
        "tags_count_ok": 1 <= len(meta.get("tags", [])) <= 5,
    }
    passed = all(checks.values())
    return {"path": str(douyin_path), "checks": checks, "passed": passed, "missing": missing}


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate douyin-video.json")
    parser.add_argument("--id", required=True)
    args = parser.parse_args()
    report = validate(project_work_dir(args.id))
    print(f"Validate {'PASSED' if report['passed'] else 'FAILED'}: {args.id}")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
