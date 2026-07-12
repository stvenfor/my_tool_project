#!/usr/bin/env python3
"""Generate one deterministic preview image per unique category label."""

from __future__ import annotations

import argparse
import hashlib
import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from common import CATEGORY_PREVIEW_ROOT, FONT_CANDIDATES, ROOT, load_categories

WIDTH, HEIGHT = 1080, 1920
PALETTES = [
    ("#F6F0E4", "#171717", "#B73A2E", "#F0D8B6"),
    ("#EEF4F1", "#17211D", "#286A57", "#D0E5DC"),
    ("#F4F0F8", "#211A29", "#74539A", "#DDD0EB"),
    ("#F7F1E7", "#1E1B18", "#C16B2F", "#E9D2B6"),
    ("#EDF2F8", "#17202B", "#346A9A", "#CDDDEB"),
]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = list(FONT_CANDIDATES)
    if bold:
        candidates = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
        ] + candidates
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size, index=0)
    return ImageFont.load_default()


def wrapped(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, *, width: int, size: int, fill: str, spacing: int = 14) -> None:
    lines = textwrap.wrap(value, width=width, break_long_words=True, break_on_hyphens=False)
    draw.multiline_text(xy, "\n".join(lines), font=font(size), fill=fill, spacing=spacing)


def render_category(slug: str, cfg: dict, out_path: Path) -> None:
    label = cfg["label"]
    seed = int(hashlib.sha256(slug.encode()).hexdigest()[:8], 16)
    bg, ink, accent, soft = PALETTES[seed % len(PALETTES)]
    variant = seed % 3
    image = Image.new("RGB", (WIDTH, HEIGHT), bg)
    draw = ImageDraw.Draw(image)
    margin = 42
    draw.rounded_rectangle((18, 18, WIDTH - 18, HEIGHT - 18), 30, outline=ink, width=4)

    draw.text((margin, 68), f"{label}避坑四件套", font=font(76, True), fill=ink)
    wrapped(draw, (margin, 170), cfg.get("tone", "生活观察、轻松避坑"), width=28, size=31, fill=accent)
    draw.rounded_rectangle((842, 52, 1028, 218), 20, outline=ink, width=3, fill=soft)
    draw.text((935, 90), "今日", anchor="mm", font=font(28, True), fill=ink)
    draw.text((935, 152), "少踩坑", anchor="mm", font=font(34, True), fill=accent)

    angles = list(cfg.get("angles", []))[:4]
    while len(angles) < 4:
        angles.append(f"{label}日常{len(angles) + 1}")
    card_hints = []
    for topic in cfg.get("pilot_topics", []):
        card_hints.extend(topic.get("card_hints", []))

    if variant == 0:
        boxes = [(42, 282, 520, 716), (560, 282, 1038, 716), (42, 748, 520, 1182), (560, 748, 1038, 1182)]
    elif variant == 1:
        boxes = [(42, 282, 1038, 492), (42, 520, 1038, 730), (42, 758, 1038, 968), (42, 996, 1038, 1206)]
    else:
        boxes = [(42, 282, 650, 686), (680, 282, 1038, 686), (42, 718, 400, 1122), (430, 718, 1038, 1122)]

    for i, (box, angle) in enumerate(zip(boxes, angles), 1):
        x1, y1, x2, y2 = box
        draw.rounded_rectangle(box, 22, fill="#FFFCF6", outline=ink, width=3)
        draw.rounded_rectangle((x1 + 18, y1 + 18, x1 + 102, y1 + 90), 14, fill=ink)
        draw.text((x1 + 60, y1 + 54), f"{i:02d}", anchor="mm", font=font(34, True), fill="#FFFFFF")
        draw.text((x1 + 122, y1 + 29), angle, font=font(38 if x2 - x1 > 500 else 31, True), fill=ink)
        hint = card_hints[i - 1] if i - 1 < len(card_hints) else angle
        bullets = [f"别被「{hint}」带节奏", "先看成本，再做决定", "给自己留一条退路"]
        if y2 - y1 < 300:
            bullets = bullets[:2]
        line_y = y1 + 122
        for bullet in bullets:
            draw.ellipse((x1 + 28, line_y + 9, x1 + 40, line_y + 21), fill=accent)
            wrapped(draw, (x1 + 54, line_y), bullet, width=18 if x2 - x1 < 500 else 28, size=25, fill=ink, spacing=8)
            line_y += 58
        # Abstract editorial illustration; omit it on narrow cards to preserve copy space.
        if x2 - x1 >= 430:
            radius = 50 if y2 - y1 < 300 else 66
            cx, cy = x2 - radius - 46, y2 - radius - 46
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=soft, outline=ink, width=3)
            draw.arc((cx - radius // 2, cy - 4, cx + radius // 2, cy + radius // 2), 195, 345, fill=ink, width=4)
            draw.ellipse((cx - radius // 2, cy - 22, cx - radius // 3, cy - 10), fill=ink)
            draw.ellipse((cx + radius // 3, cy - 22, cx + radius // 2, cy - 10), fill=ink)
        draw.text((x1 + 28, y2 - 54), f"效果：看懂套路，少交学费", font=font(23, True), fill=accent)

    footer_top = 1260
    draw.rounded_rectangle((42, footer_top, 1038, 1650), 24, fill=soft, outline=ink, width=3)
    draw.text((76, footer_top + 42), "温馨提示", font=font(44, True), fill=ink)
    wrapped(draw, (76, footer_top + 112), f"{cfg.get('framing', '避坑清单')}不是标准答案。先识别边界，再决定要不要入场。", width=25, size=31, fill=ink, spacing=18)
    draw.line((76, footer_top + 265, 1000, footer_top + 265), fill=ink, width=2)
    draw.text((76, footer_top + 292), "本期标签", font=font(28, True), fill=accent)
    tags = "  ".join(f"#{value}" for value in angles[:4])
    wrapped(draw, (250, footer_top + 292), tags, width=34, size=26, fill=ink)
    draw.text((WIDTH // 2, 1775), f"认真生活，也要记得保护自己。", anchor="mm", font=font(39, True), fill=ink)
    draw.text((WIDTH // 2, 1835), f"CATEGORY · {slug}", anchor="mm", font=font(22), fill=accent)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, quality=95)


def generate(force: bool = False) -> Path:
    categories = load_categories()
    CATEGORY_PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = CATEGORY_PREVIEW_ROOT / "manifest.json"
    previous = {}
    if manifest_path.exists():
        previous = {item["id"]: item for item in json.loads(manifest_path.read_text(encoding="utf-8")).get("items", [])}

    seen_labels: set[str] = set()
    items = []
    for slug, cfg in categories.items():
        label = cfg.get("label", slug)
        if label in seen_labels:
            continue
        seen_labels.add(label)
        storage_key = cfg.get("storage_key", slug)
        out_path = CATEGORY_PREVIEW_ROOT / storage_key / "preview.png"
        if force or not out_path.exists():
            render_category(slug, cfg, out_path)
        old = previous.get(slug, {})
        items.append({
            "id": slug,
            "label": label,
            "storage_key": storage_key,
            "image": str(out_path.relative_to(ROOT)),
            "sent": bool(old.get("sent", False)),
            "sent_at": old.get("sent_at"),
        })

    manifest = {"version": 1, "updated_at": datetime.now(timezone.utc).isoformat(), "items": items}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {len(items)} unique-label previews")
    print(manifest_path)
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    generate(force=args.force)


if __name__ == "__main__":
    main()
