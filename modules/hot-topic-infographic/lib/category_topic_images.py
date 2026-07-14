#!/usr/bin/env python3
"""Generate one image for every topic id grouped under every category label."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from common import FONT_CANDIDATES, ROOT, load_categories

OUT_ROOT = ROOT / "_hot-topic-infographic" / "category-topics"
WIDTH, HEIGHT = 1080, 1920
PALETTES = [
    ("#F6F0E5", "#20201F", "#B94336", "#E8CFC1"),
    ("#EEF3EE", "#20322C", "#477565", "#C9DDD3"),
    ("#F2EFF6", "#272231", "#725E91", "#D8D0E5"),
    ("#F7F2E8", "#28231E", "#C17435", "#EBD5B7"),
    ("#EDF3F7", "#1E2B34", "#3C718E", "#CADDE7"),
]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (["/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Medium.ttc"] if bold else []) + FONT_CANDIDATES
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size, index=0)
    return ImageFont.load_default()


def stable_topics(slug: str, cfg: dict) -> list[dict]:
    """Return explicit pilot ids plus enough deterministic angle ids for min_topics."""
    minimum = int(cfg.get("min_topics", 1))
    topics = [dict(item) for item in cfg.get("pilot_topics", [])]
    used_angles = {item.get("angle") for item in topics}
    for index, angle in enumerate(cfg.get("angles", []), 1):
        if len(topics) >= minimum:
            break
        if angle in used_angles:
            continue
        topics.append({
            "id": f"{slug}-{index:02d}-2026",
            "angle": angle,
            "keywords": [cfg.get("label", slug), angle],
            "card_hints": [],
        })
        used_angles.add(angle)
    return topics


def card_titles(topic: dict, cfg: dict) -> list[str]:
    hints = [str(x) for x in topic.get("card_hints", []) if str(x).strip()]
    angle = topic.get("angle", "日常关系")
    fallbacks = [f"{angle}信号", f"{angle}误区", f"{angle}边界", f"{angle}退路"]
    return (hints + fallbacks)[:4]


def render(slug: str, cfg: dict, topic: dict, out: Path) -> None:
    identity = f"{slug}:{topic['id']}"
    seed = int(hashlib.sha256(identity.encode()).hexdigest()[:8], 16)
    bg, ink, accent, soft = PALETTES[seed % len(PALETTES)]
    variant = seed % 3
    label, angle = cfg.get("label", slug), topic.get("angle", "话题")
    cards = card_titles(topic, cfg)
    image = Image.new("RGB", (WIDTH, HEIGHT), bg)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((18, 18, WIDTH - 18, HEIGHT - 18), 30, outline=ink, width=4)
    draw.text((52, 66), f"{label} · {angle}", font=font(68, True), fill=ink)
    draw.text((54, 158), cfg.get("framing", "关系与话题避坑清单"), font=font(30), fill=accent)
    draw.rounded_rectangle((824, 54, 1025, 205), 20, fill=soft, outline=ink, width=3)
    draw.text((925, 94), "看清", anchor="mm", font=font(28, True), fill=ink)
    draw.text((925, 153), "少内耗", anchor="mm", font=font(35, True), fill=accent)

    if variant == 0:
        boxes = [(42, 276, 520, 730), (560, 276, 1038, 730), (42, 760, 520, 1214), (560, 760, 1038, 1214)]
    elif variant == 1:
        boxes = [(42, 276, 1038, 498), (42, 526, 1038, 748), (42, 776, 1038, 998), (42, 1026, 1038, 1248)]
    else:
        boxes = [(42, 276, 650, 708), (680, 276, 1038, 708), (42, 738, 400, 1170), (430, 738, 1038, 1170)]

    for idx, (box, title) in enumerate(zip(boxes, cards), 1):
        x1, y1, x2, y2 = box
        draw.rounded_rectangle(box, 22, fill="#FFFCF7", outline=ink, width=3)
        draw.rounded_rectangle((x1 + 18, y1 + 18, x1 + 105, y1 + 92), 14, fill=ink)
        draw.text((x1 + 61, y1 + 55), f"{idx:02d}", anchor="mm", font=font(34, True), fill="#FFFFFF")
        title_size = 37 if x2 - x1 >= 450 else 29
        draw.text((x1 + 126, y1 + 31), title, font=font(title_size, True), fill=ink)
        bullets = ["先辨认信号，别急着回应", "看清成本，再做决定", "守住边界，给自己退路"]
        if y2 - y1 < 300:
            bullets = bullets[:2]
        y = y1 + 128
        for bullet in bullets:
            draw.ellipse((x1 + 30, y + 11, x1 + 42, y + 23), fill=accent)
            draw.text((x1 + 58, y), bullet, font=font(25), fill=ink)
            y += 62
        if x2 - x1 >= 440 and y2 - y1 >= 350:
            cx, cy, r = x2 - 102, y2 - 122, 58
            draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill=soft, outline=ink, width=3)
            draw.ellipse((cx-27, cy-18, cx-15, cy-6), fill=ink)
            draw.ellipse((cx+15, cy-18, cx+27, cy-6), fill=ink)
            draw.arc((cx-30, cy-2, cx+30, cy+37), 195, 345, fill=ink, width=4)
        draw.text((x1 + 28, y2 - 52), "结论：共鸣可以，内耗不必", font=font(22, True), fill=accent)

    footer_y = 1300
    draw.rounded_rectangle((42, footer_y, 1038, 1655), 24, fill=soft, outline=ink, width=3)
    draw.text((78, footer_y + 45), "写给正在经历的你", font=font(43, True), fill=ink)
    message = "不是教你做人，是帮你看清自己。\n扎心但真实，共鸣但不尖锐。"
    draw.multiline_text((78, footer_y + 120), message, font=font(34), fill=ink, spacing=24)
    keywords = "  ".join(f"#{x}" for x in topic.get("keywords", [])[:4])
    draw.line((78, footer_y + 270, 1000, footer_y + 270), fill=ink, width=2)
    draw.text((78, footer_y + 293), keywords or f"#{label}  #{angle}", font=font(26), fill=accent)
    draw.text((WIDTH // 2, 1770), "看清关系，也照顾好自己。", anchor="mm", font=font(39, True), fill=ink)
    draw.text((WIDTH // 2, 1835), topic["id"], anchor="mm", font=font(21), fill=accent)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)


def generate(force: bool = False) -> Path:
    categories = load_categories()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT_ROOT / "manifest.json"
    old_items = {}
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        old_items = {(x["label"], x["id"]): x for x in old.get("items", [])}
    items, generated, skipped = [], 0, 0
    for slug, cfg in categories.items():
        label = cfg.get("label", slug)
        storage_key = cfg.get("storage_key", slug)
        for topic in stable_topics(slug, cfg):
            topic_id = topic["id"]
            path = OUT_ROOT / storage_key / topic_id / "final.png"
            if force or not path.exists():
                render(slug, cfg, topic, path)
                generated += 1
            else:
                skipped += 1
            old = old_items.get((label, topic_id), {})
            stat = path.stat()
            items.append({
                "label": label,
                "category": slug,
                "id": topic_id,
                "angle": topic.get("angle"),
                "storage_key": storage_key,
                "image": str(path.relative_to(ROOT)),
                "generator": "category_topic_images.py",
                "generated_at": old.get("generated_at") or datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "bytes": stat.st_size,
                "sent": bool(old.get("sent", False)),
                "sent_at": old.get("sent_at"),
            })
    manifest = {"version": 1, "updated_at": datetime.now(timezone.utc).isoformat(), "items": items}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_gallery(items)
    print(f"generated={generated} skipped_existing={skipped} total={len(items)}")
    print(manifest_path)
    return manifest_path


def write_gallery(items: list[dict]) -> Path:
    """Create a zero-dependency browser gallery next to the manifest."""
    cards = []
    for item in items:
        src = Path(item["image"]).relative_to("_hot-topic-infographic/category-topics")
        cards.append(
            '<article class="card">'
            f'<a href="{html.escape(str(src))}"><img loading="lazy" src="{html.escape(str(src))}" alt="{html.escape(item["label"] + " " + item["angle"])}"></a>'
            f'<h2>{html.escape(item["label"])} · {html.escape(item["angle"] or "")}</h2>'
            f'<code>{html.escape(item["id"])}</code>'
            f'<p class="status">{("已发送" if item["sent"] else "待发送")}</p>'
            '</article>'
        )
    page = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>话题图片总览</title><style>
body{margin:0;background:#f3efe7;color:#28231e;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}
header{padding:32px 4vw 12px}h1{margin:0 0 8px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:24px;padding:24px 4vw 64px}
.card{background:#fffaf2;border:1px solid #d9d0c3;border-radius:18px;padding:12px;box-shadow:0 8px 30px #4b3d2d12}.card img{display:block;width:100%;aspect-ratio:9/16;object-fit:cover;border-radius:12px}.card h2{font-size:18px;margin:12px 0 5px}.card code{font-size:12px;overflow-wrap:anywhere}.status{color:#a45b38;font-weight:700;margin:8px 0 2px}
</style></head><body><header><h1>话题图片总览</h1><p>按 categories.json 的 label / id 生成；点击图片查看原图。</p></header><main class="grid">""" + "".join(cards) + "</main></body></html>"
    path = OUT_ROOT / "index.html"
    path.write_text(page, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Regenerate images; preserve sent state")
    args = parser.parse_args()
    generate(force=args.force)


if __name__ == "__main__":
    main()
