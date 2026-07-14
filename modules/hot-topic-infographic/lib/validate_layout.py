#!/usr/bin/env python3
"""Validate per-topic layout JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_topic_layout, topic_paths

CANVAS_W = 1080
CANVAS_H = 1920
MIN_FONT = 14


def rect_from_box(box: dict) -> tuple[int, int, int, int]:
    x, y, w, h = box["x"], box["y"], box["w"], box["h"]
    return x, y, x + w, y + h


def overlaps(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def in_canvas(box: dict) -> bool:
    x, y, w, h = box["x"], box["y"], box["w"], box["h"]
    return x >= 0 and y >= 0 and x + w <= CANVAS_W and y + h <= CANVAS_H


def validate_layout(data: dict) -> list[str]:
    errors: list[str] = []

    canvas = data.get("canvas", {})
    if canvas.get("width") != CANVAS_W or canvas.get("height") != CANVAS_H:
        errors.append(f"canvas must be {CANVAS_W}x{CANVAS_H}")

    single = data.get("single", {})
    cards = single.get("cards", [])
    if len(cards) != 4:
        errors.append("single.cards must have 4 items")

    card_boxes: list[tuple[int, int, int, int]] = []
    for i, card in enumerate(cards):
        box = card.get("box")
        if not box:
            errors.append(f"single.cards[{i}] missing box")
            continue
        if not in_canvas(box):
            errors.append(f"single.cards[{i}] box out of canvas")
        card_boxes.append(rect_from_box(box))
        for key in ("bullets", "bubble", "effect"):
            region = card.get(key, {})
            if region.get("size", MIN_FONT) < MIN_FONT:
                errors.append(f"single.cards[{i}].{key} font size < {MIN_FONT}")

    for i in range(len(card_boxes)):
        for j in range(i + 1, len(card_boxes)):
            if overlaps(card_boxes[i], card_boxes[j]):
                errors.append(f"single.cards[{i}] overlaps cards[{j}]")

    carousel = data.get("carousel", {})
    if "cover" not in carousel:
        errors.append("carousel.cover missing")
    slides = carousel.get("slides", [])
    if len(slides) != 4:
        errors.append("carousel.slides must have 4 items")

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate layout JSON")
    parser.add_argument("--id", help="Topic id")
    parser.add_argument("--file", help="Layout file path")
    args = parser.parse_args()

    if args.file:
        path = Path(args.file)
        data = json.loads(path.read_text(encoding="utf-8"))
    elif args.id:
        data = load_topic_layout(args.id)
        path = topic_paths(args.id)["layout_json"]
    else:
        parser.error("Provide --id or --file")

    errors = validate_layout(data)
    if errors:
        print(f"INVALID: {path}")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    print(f"OK: {path}")


if __name__ == "__main__":
    main()
