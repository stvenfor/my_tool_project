#!/usr/bin/env python3
"""Approve a draft topic by moving to approved/ and setting status."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import SCRIPT_DIR
from validate import validate_topic


def approve(topic_id: str) -> Path:
    draft = SCRIPT_DIR / "topics" / "draft" / f"{topic_id}.json"
    approved = SCRIPT_DIR / "topics" / "approved" / f"{topic_id}.json"
    if not draft.exists():
        raise SystemExit(f"Draft not found: {draft}")

    data = json.loads(draft.read_text(encoding="utf-8"))
    data["status"] = "approved"
    errors = validate_topic(data)
    if errors:
        print("Cannot approve, validation failed:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)

    approved.parent.mkdir(parents=True, exist_ok=True)
    approved.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    draft.unlink()
    print(f"Approved: {approved}")
    return approved


def main() -> None:
    parser = argparse.ArgumentParser(description="Approve draft topic")
    parser.add_argument("--id", required=True)
    args = parser.parse_args()
    approve(args.id)


if __name__ == "__main__":
    main()
