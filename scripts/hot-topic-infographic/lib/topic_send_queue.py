#!/usr/bin/env python3
"""FIFO queue for category topic images; sent items never reappear."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from common import ROOT

MANIFEST = ROOT / "_hot-topic-infographic" / "category-topics" / "manifest.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--next", action="store_true")
    group.add_argument("--mark-sent", metavar="ID")
    group.add_argument("--status", action="store_true", help="Print queue totals grouped by label")
    parser.add_argument("--label", help="Limit lookup/marking to one label")
    args = parser.parse_args()
    if not MANIFEST.exists():
        raise SystemExit("Manifest missing; run infographic:topic-images first")
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    matches = [x for x in data["items"] if not args.label or x["label"] == args.label]
    if args.status:
        groups: dict[str, dict[str, int]] = {}
        for item in matches:
            row = groups.setdefault(item["label"], {"total": 0, "sent": 0, "pending": 0})
            row["total"] += 1
            key = "sent" if item.get("sent") else "pending"
            row[key] += 1
        result = {
            "total": len(matches),
            "sent": sum(bool(x.get("sent")) for x in matches),
            "pending": sum(not x.get("sent") for x in matches),
            "labels": groups,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.next:
        item = next((x for x in matches if not x.get("sent")), None)
        print(json.dumps(item, ensure_ascii=False) if item else "null")
        return
    found = [x for x in matches if x["id"] == args.mark_sent]
    if len(found) != 1:
        raise SystemExit(f"Expected exactly one matching label/id, found {len(found)}")
    item = found[0]
    if not item.get("sent"):
        now = datetime.now(timezone.utc).isoformat()
        item["sent"], item["sent_at"], data["updated_at"] = True, now, now
        MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(item, ensure_ascii=False))


if __name__ == "__main__":
    main()
