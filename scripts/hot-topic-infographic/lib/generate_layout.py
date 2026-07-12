#!/usr/bin/env python3
"""Generate per-topic 9:16 layout JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LAYOUT_SCHEMA_PATH, load_topic, sync_topic_to_output, topic_paths
from validate_layout import validate_layout

VARIANTS = ["grid_2x2_compact", "vertical_stack", "staggered_cards"]

SYSTEM_PROMPT = """你是信息图排版工程师。根据 topic JSON 生成 9:16 (1080x1920) 的 layout JSON。
输出严格 JSON，包含 canvas, style_variant, single, carousel。
single 含 header(title/subtitle/badge_top/badge_bottom 坐标), cards[4](box/header_h/bullets/bubble/effect/illustration_zone), footer(upgrades_box/warning_box/receipt_box), tagline。
carousel 含 cover(title/subtitle/badge/teaser) 和 slides[4](card_index, background_accent, regions)。
所有 box 不得越界、卡片 box 不得重叠。字号>=14。"""


def pick_variant(topic_id: str) -> str:
    digest = hashlib.md5(topic_id.encode()).hexdigest()
    return VARIANTS[int(digest, 16) % len(VARIANTS)]


def text_region(x: int, y: int, size: int = 18, anchor: str = "lt", **extra) -> dict:
    return {"x": x, "y": y, "size": size, "anchor": anchor, **extra}


def build_grid_2x2(topic: dict) -> dict:
    cards_layout = []
    positions = [(32, 220, 500, 380), (548, 220, 500, 380), (32, 620, 500, 380), (548, 620, 500, 380)]
    for i, (x, y, w, h) in enumerate(positions):
        cards_layout.append(
            {
                "box": {"x": x, "y": y, "w": w, "h": h},
                "header_h": 48,
                "no": text_region(x + 16, y + 14, 20),
                "name": text_region(x + 56, y + 12, 22, bold=True),
                "price": text_region(x + w - 16, y + 12, 18, anchor="rm"),
                "bullets": text_region(x + 16, y + 60, 17, line_height=30),
                "bubble": text_region(x + w // 2, y + h - 100, 17, anchor="mm", bg=True),
                "effect": text_region(x + 16, y + h - 36, 17, bold=True),
                "illustration_zone": {"x": x + 16, "y": y + 150, "w": w - 32, "h": h - 210},
            }
        )
    return {
        "header": {
            "title": text_region(540, 72, 44, anchor="mm", bold=True),
            "subtitle": text_region(540, 120, 22, anchor="mm", color="subtitle"),
            "badge_box": {"x": 860, "y": 40, "w": 180, "h": 90},
            "badge_top": text_region(950, 68, 18, anchor="mm"),
            "badge_bottom": text_region(950, 98, 16, anchor="mm", color="subtitle"),
        },
        "cards": cards_layout,
        "footer": {
            "upgrades_box": {"x": 32, "y": 1020, "w": 320, "h": 260},
            "upgrades_title": text_region(52, 1048, 20, bold=True),
            "upgrades_items": text_region(52, 1088, 17, line_height=34),
            "warning_box": {"x": 368, "y": 1020, "w": 344, "h": 260},
            "warning_text": text_region(540, 1150, 18, anchor="mm", max_width=300),
            "receipt_box": {"x": 728, "y": 1020, "w": 320, "h": 260},
            "receipt_title": text_region(752, 1048, 18, bold=True),
            "receipt_lines": text_region(752, 1088, 16, line_height=28),
            "receipt_total": text_region(752, 1200, 17, bold=True),
            "receipt_balance": text_region(752, 1228, 17, color="subtitle"),
            "receipt_note": text_region(888, 1260, 18, anchor="mm", color="subtitle", bold=True),
        },
        "tagline": text_region(540, 1320, 20, anchor="mm", bold=True),
    }


def build_vertical_stack(topic: dict) -> dict:
    cards_layout = []
    y_start = 200
    card_h = 280
    gap = 16
    for i in range(4):
        y = y_start + i * (card_h + gap)
        cards_layout.append(
            {
                "box": {"x": 40, "y": y, "w": 1000, "h": card_h},
                "header_h": 44,
                "no": text_region(56, y + 12, 20),
                "name": text_region(100, y + 10, 22, bold=True),
                "price": text_region(1024, y + 10, 18, anchor="rm"),
                "bullets": text_region(56, y + 52, 17, line_height=28),
                "bubble": text_region(820, y + card_h - 70, 16, anchor="mm", bg=True),
                "effect": text_region(56, y + card_h - 32, 17, bold=True),
                "illustration_zone": {"x": 680, "y": y + 50, "w": 340, "h": card_h - 90},
            }
        )
    footer_y = y_start + 4 * (card_h + gap) + 20
    return {
        "header": {
            "title": text_region(540, 64, 42, anchor="mm", bold=True),
            "subtitle": text_region(540, 108, 20, anchor="mm", color="subtitle"),
            "badge_box": {"x": 860, "y": 36, "w": 180, "h": 86},
            "badge_top": text_region(950, 62, 17, anchor="mm"),
            "badge_bottom": text_region(950, 90, 15, anchor="mm", color="subtitle"),
        },
        "cards": cards_layout,
        "footer": {
            "upgrades_box": {"x": 40, "y": footer_y, "w": 300, "h": 240},
            "upgrades_title": text_region(60, footer_y + 24, 19, bold=True),
            "upgrades_items": text_region(60, footer_y + 60, 16, line_height=32),
            "warning_box": {"x": 360, "y": footer_y, "w": 360, "h": 240},
            "warning_text": text_region(540, footer_y + 120, 17, anchor="mm", max_width=320),
            "receipt_box": {"x": 740, "y": footer_y, "w": 300, "h": 240},
            "receipt_title": text_region(760, footer_y + 24, 17, bold=True),
            "receipt_lines": text_region(760, footer_y + 60, 15, line_height=26),
            "receipt_total": text_region(760, footer_y + 170, 16, bold=True),
            "receipt_balance": text_region(760, footer_y + 196, 16, color="subtitle"),
            "receipt_note": text_region(890, footer_y + 220, 17, anchor="mm", color="subtitle", bold=True),
        },
        "tagline": text_region(540, footer_y + 260, 19, anchor="mm", bold=True),
    }


def build_staggered(topic: dict) -> dict:
    cards_layout = []
    specs = [
        (40, 200, 480, 300),
        (560, 200, 480, 300),
        (80, 520, 480, 300),
        (600, 520, 480, 300),
    ]
    for i, (x, y, w, h) in enumerate(specs):
        cards_layout.append(
            {
                "box": {"x": x, "y": y, "w": w, "h": h},
                "header_h": 46,
                "no": text_region(x + 14, y + 12, 20),
                "name": text_region(x + 52, y + 10, 21, bold=True),
                "price": text_region(x + w - 14, y + 10, 17, anchor="rm"),
                "bullets": text_region(x + 14, y + 56, 16, line_height=28),
                "bubble": text_region(x + w // 2, y + h - 90, 16, anchor="mm", bg=True),
                "effect": text_region(x + 14, y + h - 30, 16, bold=True),
                "illustration_zone": {"x": x + 14, "y": y + 140, "w": w - 28, "h": h - 200},
            }
        )
    return {
        "header": {
            "title": text_region(540, 70, 43, anchor="mm", bold=True),
            "subtitle": text_region(540, 118, 21, anchor="mm", color="subtitle"),
            "badge_box": {"x": 850, "y": 38, "w": 190, "h": 88},
            "badge_top": text_region(945, 64, 17, anchor="mm"),
            "badge_bottom": text_region(945, 92, 15, anchor="mm", color="subtitle"),
        },
        "cards": cards_layout,
        "footer": {
            "upgrades_box": {"x": 40, "y": 860, "w": 310, "h": 250},
            "upgrades_title": text_region(60, 888, 19, bold=True),
            "upgrades_items": text_region(60, 924, 16, line_height=32),
            "warning_box": {"x": 370, "y": 860, "w": 340, "h": 250},
            "warning_text": text_region(540, 985, 17, anchor="mm", max_width=300),
            "receipt_box": {"x": 730, "y": 860, "w": 310, "h": 250},
            "receipt_title": text_region(750, 888, 17, bold=True),
            "receipt_lines": text_region(750, 924, 15, line_height=26),
            "receipt_total": text_region(750, 1030, 16, bold=True),
            "receipt_balance": text_region(750, 1056, 16, color="subtitle"),
            "receipt_note": text_region(885, 1084, 17, anchor="mm", color="subtitle", bold=True),
        },
        "tagline": text_region(540, 1140, 19, anchor="mm", bold=True),
    }


BUILDERS = {
    "grid_2x2_compact": build_grid_2x2,
    "vertical_stack": build_vertical_stack,
    "staggered_cards": build_staggered,
}


def build_carousel(topic: dict) -> dict:
    slides = []
    for i, card in enumerate(topic["cards"]):
        slides.append(
            {
                "card_index": i,
                "background_accent": card["accent"],
                "regions": {
                    "no": text_region(80, 120, 28),
                    "name": text_region(140, 110, 36, bold=True),
                    "price": text_region(1000, 110, 28, anchor="rm"),
                    "bullets": text_region(80, 200, 24, line_height=42),
                    "bubble": text_region(540, 920, 22, anchor="mm", bg=True),
                    "effect": text_region(80, 1680, 22, bold=True),
                    "illustration_zone": {"x": 80, "y": 380, "w": 920, "h": 500},
                },
            }
        )
    total = topic["footer"]["receipt"]["total"]
    return {
        "cover": {
            "title": text_region(540, 280, 52, anchor="mm", bold=True),
            "subtitle": text_region(540, 360, 26, anchor="mm", color="subtitle"),
            "badge_box": {"x": 820, "y": 80, "w": 220, "h": 100},
            "badge_top": text_region(930, 115, 20, anchor="mm"),
            "badge_bottom": text_region(930, 148, 18, anchor="mm", color="subtitle"),
            "teaser": text_region(540, 1200, 32, anchor="mm", bold=True, text=f"合计 {total}"),
        },
        "slides": slides,
    }


def build_fallback_layout(topic: dict, variant: str | None = None) -> dict:
    topic_id = topic["id"]
    variant = variant or pick_variant(topic_id)
    builder = BUILDERS.get(variant, build_grid_2x2)
    single = builder(topic)
    return {
        "canvas": {"width": 1080, "height": 1920},
        "style_variant": variant,
        "single": single,
        "carousel": build_carousel(topic),
    }


def call_openai_layout(topic: dict) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    schema_hint = ""
    if LAYOUT_SCHEMA_PATH.exists():
        schema_hint = LAYOUT_SCHEMA_PATH.read_text(encoding="utf-8")[:3000]

    payload = {
        "model": os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"topic:\n{json.dumps(topic, ensure_ascii=False)}\n\nschema:\n{schema_hint}\n\nOutput JSON only.",
            },
        ],
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    content = result["choices"][0]["message"]["content"]
    if content.strip().startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content.strip())
        content = re.sub(r"\s*```$", "", content)
    return json.loads(content)


def generate_layout(topic_id: str, variant: str | None = None, use_llm: bool = False) -> Path:
    sync_topic_to_output(topic_id)
    topic = load_topic(topic_id)
    paths = topic_paths(topic_id)
    paths["output_dir"].mkdir(parents=True, exist_ok=True)

    try:
        if use_llm and os.environ.get("OPENAI_API_KEY"):
            layout = call_openai_layout(topic)
        else:
            layout = build_fallback_layout(topic, variant)
    except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"LLM layout failed ({exc}), using fallback")
        layout = build_fallback_layout(topic, variant)

    errors = validate_layout(layout)
    if errors:
        print("Layout validation issues, rebuilding fallback:")
        for err in errors:
            print(f"  - {err}")
        layout = build_fallback_layout(topic, variant or pick_variant(topic_id))
        errors = validate_layout(layout)
        if errors:
            raise SystemExit(f"Layout still invalid: {errors}")

    out = paths["layout_json"]
    out.write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved layout ({layout['style_variant']}): {out}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate per-topic 9:16 layout")
    parser.add_argument("--id", required=True)
    parser.add_argument("--variant", choices=VARIANTS)
    parser.add_argument("--llm", action="store_true", help="Use OpenAI for layout")
    args = parser.parse_args()
    generate_layout(args.id, variant=args.variant, use_llm=args.llm)


if __name__ == "__main__":
    main()
