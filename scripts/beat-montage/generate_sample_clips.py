#!/usr/bin/env python3
"""Generate placeholder clip assets for the beat-montage pipeline."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
CLIPS_DIR = ROOT / "clips"
MANIFEST_PATH = ROOT / "clip_manifest.json"

SAMPLES = [
    {
        "id": "comedy_bean_01",
        "file": "comedy/bean_01.png",
        "type": "comedy",
        "energy": 2,
        "tags": ["憨豆", "喜剧", "冷场"],
        "label": "COMEDY\n憨豆冷场",
        "color": "#2d4a3e",
    },
    {
        "id": "slow_build_01",
        "file": "slow_build/charge_01.png",
        "type": "slow_build",
        "energy": 3,
        "tags": ["蓄力", "慢镜"],
        "label": "SLOW BUILD\n蓄力前摇",
        "color": "#3d2d4a",
    },
    {
        "id": "action_punch_01",
        "file": "action_punch/punch_01.png",
        "type": "action_punch",
        "energy": 8,
        "tags": ["拳脚", "打击"],
        "label": "PUNCH\n拳脚重击",
        "color": "#4a2d2d",
    },
    {
        "id": "action_gun_01",
        "file": "action_gun/gun_01.png",
        "type": "action_gun",
        "energy": 9,
        "tags": ["射击", "枪战"],
        "label": "GUN\n射击卡点",
        "color": "#2d3a4a",
    },
    {
        "id": "hero_shot_01",
        "file": "hero_shot/hero_01.png",
        "type": "hero_shot",
        "energy": 5,
        "tags": ["定格", "结尾"],
        "label": "HERO\n英雄定格",
        "color": "#4a4a2d",
    },
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial.ttf",
    ):
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_placeholder(sample: dict, width: int = 1080, height: int = 1920) -> None:
    image = Image.new("RGB", (width, height), sample["color"])
    draw = ImageDraw.Draw(image)
    font = _load_font(72)
    small = _load_font(42)

    draw.rectangle((60, 60, width - 60, height - 60), outline="#ffffff", width=4)
    draw.text((120, 180), sample["type"].upper(), fill="#f5d67b", font=small)
    draw.multiline_text((120, 320), sample["label"], fill="#ffffff", font=font, spacing=18)
    draw.text((120, height - 220), f"energy={sample['energy']}", fill="#9fd3ff", font=small)

    target = CLIPS_DIR / sample["file"]
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, format="PNG")
    print(f"Wrote {target}")


def build_manifest(samples: list[dict]) -> list[dict]:
    manifest = []
    for sample in samples:
        manifest.append(
            {
                "id": sample["id"],
                "path": sample["file"],
                "type": sample["type"],
                "energy": sample["energy"],
                "tags": sample["tags"],
                "trim_in": 0.0,
                "duration_hint": 1.5,
            }
        )
    return manifest


def main() -> None:
    for sample in SAMPLES:
        render_placeholder(sample)

    manifest = build_manifest(SAMPLES)
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
