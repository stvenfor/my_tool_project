#!/usr/bin/env python3
"""Publish queue for video-factory Douyin outputs."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from lib import DEFAULT_OUTPUT_ROOT, PROJECT_ROOT, load_json, save_json


def _manifest_path() -> Path:
    return DEFAULT_OUTPUT_ROOT / "publish-queue.json"


def _load_manifest() -> tuple[dict, Path]:
    path = _manifest_path()
    if not path.exists():
        manifest = {"items": [], "updated_at": ""}
        save_json(path, manifest)
        return manifest, path
    return load_json(path), path


def _scan_outputs() -> list[dict]:
    items = []
    if not DEFAULT_OUTPUT_ROOT.exists():
        return items
    for work_dir in sorted(DEFAULT_OUTPUT_ROOT.iterdir()):
        if not work_dir.is_dir() or work_dir.name == "assets":
            continue
        douyin_json = work_dir / "douyin-video.json"
        final_mp4 = work_dir / "output" / "final.mp4"
        if douyin_json.exists() and final_mp4.exists():
            meta = load_json(douyin_json)
            items.append(
                {
                    "id": work_dir.name,
                    "work_dir": str(work_dir.relative_to(PROJECT_ROOT)),
                    "douyin_config": str(douyin_json.relative_to(PROJECT_ROOT)),
                    "title": meta.get("title", ""),
                    "sent": False,
                }
            )
    return items


def _sync_manifest(manifest: dict) -> dict:
    scanned = _scan_outputs()
    existing = {item["id"]: item for item in manifest.get("items", [])}
    merged = []
    for item in scanned:
        prev = existing.get(item["id"], {})
        merged.append({**item, "sent": bool(prev.get("sent")), "sent_at": prev.get("sent_at", "")})
    manifest["items"] = merged
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Video-factory publish queue")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sync", action="store_true", help="Scan work dirs and refresh queue")
    group.add_argument("--next", action="store_true", help="Print next unsent item as JSON")
    group.add_argument("--mark-sent", metavar="ID", help="Mark item sent after publish")
    group.add_argument("--status", action="store_true", help="Print queue summary")
    args = parser.parse_args()

    manifest, path = _load_manifest()

    if args.sync:
        manifest = _sync_manifest(manifest)
        save_json(path, manifest)
        print(f"Queue synced: {len(manifest['items'])} items")
        return

    if args.status:
        pending = sum(1 for i in manifest.get("items", []) if not i.get("sent"))
        sent = sum(1 for i in manifest.get("items", []) if i.get("sent"))
        print(json.dumps({"pending": pending, "sent": sent, "total": len(manifest.get("items", []))}, ensure_ascii=False))
        return

    if args.next:
        item = next((i for i in manifest.get("items", []) if not i.get("sent")), None)
        print(json.dumps(item, ensure_ascii=False) if item else "null")
        return

    for item in manifest.get("items", []):
        if item["id"] == args.mark_sent:
            if not item.get("sent"):
                item["sent"] = True
                item["sent_at"] = datetime.now(timezone.utc).isoformat()
                manifest["updated_at"] = item["sent_at"]
                save_json(path, manifest)
            print(json.dumps(item, ensure_ascii=False))
            return
    raise SystemExit(f"Unknown item id: {args.mark_sent}")


if __name__ == "__main__":
    main()
