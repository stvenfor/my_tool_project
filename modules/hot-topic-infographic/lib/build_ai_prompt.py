#!/usr/bin/env python3
"""Build GPT-Image2 base prompts from topic + per-topic layout."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import SCRIPT_DIR, load_topic, load_topic_layout, topic_paths

PROMPT_SINGLE = (SCRIPT_DIR / "templates" / "prompt-base.txt").read_text(encoding="utf-8")
PROMPT_CAROUSEL = (SCRIPT_DIR / "templates" / "prompt-carousel.txt").read_text(encoding="utf-8")


def format_zones(layout: dict) -> str:
    lines = ["Header blank zone at top"]
    for i, card in enumerate(layout["single"]["cards"], 1):
        iz = card.get("illustration_zone", {})
        lines.append(f"Card {i:02d} illustration zone at x={iz.get('x')}, y={iz.get('y')}, w={iz.get('w')}, h={iz.get('h')}")
    lines.append("Footer three-column blank zone")
    return "\n".join(lines)


def build_single_prompt(topic: dict, layout: dict) -> str:
    cards = topic["cards"]
    return PROMPT_SINGLE.format(
        theme=topic["meta"].get("theme", topic["id"]),
        style_variant=layout.get("style_variant", "custom"),
        layout_zones=format_zones(layout),
        accent_1=cards[0]["accent"],
        accent_2=cards[1]["accent"],
        accent_3=cards[2]["accent"],
        accent_4=cards[3]["accent"],
        scene_1=cards[0]["scene_prompt"],
        scene_2=cards[1]["scene_prompt"],
        scene_3=cards[2]["scene_prompt"],
        scene_4=cards[3]["scene_prompt"],
    )


def build_carousel_prompt(topic: dict, layout: dict, slide_index: int) -> str:
    if slide_index == 0:
        desc = (
            "Cover slide: large blank title area center, blank subtitle below, "
            "small badge area top-right, blank teaser area lower center for bill total."
        )
    else:
        card = topic["cards"][slide_index - 1]
        slide = layout["carousel"]["slides"][slide_index - 1]
        iz = slide["regions"].get("illustration_zone", {})
        desc = (
            f"Full slide for item {card['no']}, accent color {card['accent']} header bar, "
            f"illustration: {card['scene_prompt']}, "
            f"illustration zone x={iz.get('x')} y={iz.get('y')} w={iz.get('w')} h={iz.get('h')}, "
            "blank areas for bullets and speech bubble."
        )
    return PROMPT_CAROUSEL.format(slide_description=desc)


def build_prompt(topic: dict, layout: dict | None = None, mode: str = "single", slide_index: int = 0) -> str:
    if layout is None:
        from generate_layout import build_fallback_layout

        layout = build_fallback_layout(topic)
    if mode == "carousel":
        return build_carousel_prompt(topic, layout, slide_index)
    return build_single_prompt(topic, layout)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build AI base image prompt")
    parser.add_argument("--id", required=True)
    parser.add_argument("--mode", choices=["single", "carousel"], default="single")
    parser.add_argument("--slide", type=int, default=0, help="Carousel slide index 0-4")
    parser.add_argument("--out", help="Write prompt to file")
    args = parser.parse_args()

    topic = load_topic(args.id)
    try:
        layout = load_topic_layout(args.id)
    except FileNotFoundError:
        from generate_layout import build_fallback_layout

        layout = build_fallback_layout(topic)

    prompt = build_prompt(topic, layout, mode=args.mode, slide_index=args.slide)

    if args.out:
        out = Path(args.out)
    else:
        paths = topic_paths(args.id)
        if args.mode == "carousel":
            out = paths["carousel_base_dir"] / f"prompt-{args.slide:02d}.txt"
        else:
            out = paths["output_dir"] / "prompt.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(prompt, encoding="utf-8")
    print(f"Saved prompt: {out}")
    print("\n--- PROMPT ---\n")
    print(prompt)


if __name__ == "__main__":
    main()
