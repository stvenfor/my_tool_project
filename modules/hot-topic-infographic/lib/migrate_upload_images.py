#!/usr/bin/env python3
"""Migrate Codex-generated images into per-topic upload-images working directories."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ensure_topic_dirs, load_categories, topic_paths

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def collect_topic_ids_from_categories() -> list[str]:
    categories = load_categories()
    ids: list[str] = []
    seen: set[str] = set()
    for cfg in categories.values():
        for seed in cfg.get("pilot_topics", []):
            topic_id = seed.get("id")
            if topic_id and topic_id not in seen:
                seen.add(topic_id)
                ids.append(topic_id)
    return ids


def list_image_files(source_dir: Path) -> list[Path]:
    if not source_dir.is_dir():
        raise SystemExit(f"Source directory not found: {source_dir}")
    files = [
        p
        for p in sorted(source_dir.iterdir())
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES and not p.name.startswith(".")
    ]
    return files


def write_manifest(upload_dir: Path, *, topic_id: str, source: str, files: list[str], mode: str) -> Path:
    manifest_path = upload_dir / "manifest.json"
    existing: dict = {}
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))

    manifest = {
        "topic_id": topic_id,
        "source": source,
        "migrated_at": date.today().isoformat(),
        "mode": mode,
        "files": files,
    }
    if existing.get("history"):
        manifest["history"] = existing["history"] + [
            {
                "source": existing.get("source"),
                "migrated_at": existing.get("migrated_at"),
                "mode": existing.get("mode"),
                "file_count": len(existing.get("files", [])),
            }
        ]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def migrate_images(
    topic_id: str,
    source_dir: Path,
    *,
    move: bool = False,
    force: bool = False,
) -> list[str]:
    paths = ensure_topic_dirs(topic_id)
    upload_dir = paths["upload_images_dir"]
    images = list_image_files(source_dir)
    if not images:
        raise SystemExit(f"No image files found in: {source_dir}")

    copied: list[str] = []
    for src in images:
        dst = upload_dir / src.name
        if dst.exists() and not force:
            print(f"Skip existing: {dst.name}")
            copied.append(dst.name)
            continue
        if move:
            shutil.move(str(src), str(dst))
        else:
            shutil.copy2(src, dst)
        copied.append(dst.name)
        print(f"{'Moved' if move else 'Copied'}: {src.name} -> {dst}")

    write_manifest(
        upload_dir,
        topic_id=topic_id,
        source=str(source_dir.resolve()),
        files=sorted(set(copied)),
        mode="move" if move else "copy",
    )
    return copied


def init_from_categories() -> list[str]:
    topic_ids = collect_topic_ids_from_categories()
    for topic_id in topic_ids:
        ensure_topic_dirs(topic_id)
        print(f"Ensured upload-images: {topic_paths(topic_id)['upload_images_dir']}")
    return topic_ids


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Codex images to topic upload-images dirs")
    parser.add_argument("--id", help="Topic id slug")
    parser.add_argument("--source", help="Codex generated_images directory")
    parser.add_argument("--init-from-categories", action="store_true", help="Create upload-images for all category topic ids")
    parser.add_argument("--move", action="store_true", help="Move files instead of copy")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()

    if args.init_from_categories:
        ids = init_from_categories()
        print(f"\nInitialized {len(ids)} topic upload-images directories")
        if not args.id and not args.source:
            return

    if args.id and args.source:
        files = migrate_images(args.id, Path(args.source), move=args.move, force=args.force)
        print(f"\nDone: {len(files)} files in {topic_paths(args.id)['upload_images_dir']}")
        return

    if not args.init_from_categories:
        parser.error("Provide --id and --source, or --init-from-categories")


if __name__ == "__main__":
    main()
