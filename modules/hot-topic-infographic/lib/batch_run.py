#!/usr/bin/env python3
"""Batch run 9:16 infographic pipeline for approved topics."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import SCRIPT_DIR, ROOT, topic_paths
from compose import compose
from export_copy import export_copy
from generate_base import generate_base
from generate_layout import generate_layout


def run_one(
    topic_id: str,
    force: bool = False,
    skip_base: bool = False,
    skip_layout: bool = False,
    template_only: bool = False,
    mode: str = "both",
) -> None:
    print(f"\n=== Processing {topic_id} ===")
    paths = topic_paths(topic_id)

    if not skip_layout and (not paths["layout_json"].exists() or force):
        generate_layout(topic_id)

    if not skip_base:
        try:
            generate_base(topic_id, mode=mode, force=force)
        except SystemExit as exc:
            print(f"Base skipped, using template: {exc}")

    compose(topic_id, mode=mode, template_only=template_only or not paths["base_png"].exists())
    export_copy(topic_id, mode=mode)


def run_batch(
    force: bool = False,
    skip_base: bool = False,
    skip_layout: bool = False,
    template_only: bool = False,
    mode: str = "both",
) -> None:
    approved = (SCRIPT_DIR / "topics" / "approved")
    for path in sorted(approved.glob("*.json")):
        topic_id = path.stem
        final = topic_paths(topic_id)["final_png"]
        carousel = topic_paths(topic_id)["carousel_dir"] / "00-cover.png"
        done = final.exists() and (mode != "both" or carousel.exists())
        if done and not force:
            print(f"Skip {topic_id}: output exists (use --force)")
            continue
        run_one(
            topic_id,
            force=force,
            skip_base=skip_base,
            skip_layout=skip_layout,
            template_only=template_only,
            mode=mode,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch 9:16 infographic pipeline")
    parser.add_argument("--one", action="store_true")
    parser.add_argument("--id", help="Topic id")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-base", action="store_true")
    parser.add_argument("--skip-layout", action="store_true")
    parser.add_argument("--skip-carousel", action="store_true", help="Only single mode")
    parser.add_argument("--carousel-only", action="store_true", help="Only carousel mode")
    parser.add_argument("--template-only", action="store_true")
    args = parser.parse_args()

    if args.carousel_only:
        mode = "carousel"
    elif args.skip_carousel:
        mode = "single"
    else:
        mode = "both"

    if args.one:
        if not args.id:
            parser.error("--one requires --id")
        run_one(
            args.id,
            force=args.force,
            skip_base=args.skip_base,
            skip_layout=args.skip_layout,
            template_only=args.template_only,
            mode=mode,
        )
    else:
        run_batch(
            force=args.force,
            skip_base=args.skip_base,
            skip_layout=args.skip_layout,
            template_only=args.template_only,
            mode=mode,
        )


if __name__ == "__main__":
    main()
