#!/usr/bin/env python3
"""Read unsent category previews and mark successfully sent images."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from common import CATEGORY_PREVIEW_ROOT


def load_manifest() -> tuple[dict, object]:
    path = CATEGORY_PREVIEW_ROOT / "manifest.json"
    if not path.exists():
        raise SystemExit("Manifest not found; run infographic:category-previews first")
    return json.loads(path.read_text(encoding="utf-8")), path


def main() -> None:
    parser = argparse.ArgumentParser(description="Category preview send queue")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--next", action="store_true", help="Print the next unsent item as JSON")
    group.add_argument("--mark-sent", metavar="ID", help="Mark an item sent after publishing succeeds")
    args = parser.parse_args()
    manifest, path = load_manifest()

    if args.next:
        item = next((item for item in manifest["items"] if not item.get("sent")), None)
        print(json.dumps(item, ensure_ascii=False) if item else "null")
        return

    for item in manifest["items"]:
        if item["id"] == args.mark_sent:
            if not item.get("sent"):
                item["sent"] = True
                item["sent_at"] = datetime.now(timezone.utc).isoformat()
                manifest["updated_at"] = item["sent_at"]
                path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(item, ensure_ascii=False))
            return
    raise SystemExit(f"Unknown item id: {args.mark_sent}")


if __name__ == "__main__":
    main()
