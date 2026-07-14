#!/usr/bin/env python3
"""Compose 9:16 infographic with per-topic dynamic layout."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import FONT_CANDIDATES, load_config, load_topic, load_topic_layout, sync_topic_to_output, topic_paths

DEFAULT_COLORS = {
    "bg": "#F5F0E8",
    "text": "#1A1A1A",
    "subtitle": "#DC2626",
    "muted": "#666666",
    "warning_bg": "#FEF3C7",
    "warning_border": "#F59E0B",
    "receipt_bg": "#FFFFFF",
}


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        if not Path(path).exists():
            continue
        try:
            return ImageFont.truetype(path, size=size, index=0)
        except OSError:
            continue
    return ImageFont.load_default()


def text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def color(key: str, cfg: dict | None = None) -> str:
    colors = (cfg or {}).get("colors", DEFAULT_COLORS)
    return colors.get(key, DEFAULT_COLORS.get(key, "#1A1A1A"))


def draw_text(draw, xy, text, font, fill, anchor="lt", max_width=None):
    if not text:
        return
    if max_width:
        lines, current = [], ""
        for ch in text:
            trial = current + ch
            w, _ = text_size(draw, trial, font)
            if w <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = ch
        if current:
            lines.append(current)
        x, y = xy
        lh = text_size(draw, "测", font)[1] + 4
        for line in lines:
            draw.text((x, y), line, font=font, fill=fill)
            y += lh
        return
    draw.text(xy, text, font=font, fill=fill, anchor=anchor)


def draw_right(draw, x_right, y, text, font, fill):
    w, _ = text_size(draw, text, font)
    draw.text((x_right - w, y), text, font=font, fill=fill)


def create_single_template(topic: dict, layout: dict) -> Image.Image:
    cw, ch = layout["canvas"]["width"], layout["canvas"]["height"]
    img = Image.new("RGB", (cw, ch), color("bg"))
    draw = ImageDraw.Draw(img)
    single = layout["single"]

    for i, card in enumerate(topic["cards"]):
        cl = single["cards"][i]
        box = cl["box"]
        x, y, w, h = box["x"], box["y"], box["w"], box["h"]
        accent = card["accent"]
        hh = cl.get("header_h", 48)
        draw.rounded_rectangle((x, y, x + w, y + h), radius=12, fill="#FFFFFF", outline="#D1D5DB", width=2)
        draw.rounded_rectangle((x, y, x + w, y + hh), radius=12, fill=accent)
        draw.rectangle((x, y + hh - 10, x + w, y + hh), fill=accent)
        iz = cl.get("illustration_zone")
        if iz:
            draw.rounded_rectangle(
                (iz["x"], iz["y"], iz["x"] + iz["w"], iz["y"] + iz["h"]),
                radius=8,
                fill="#F3F4F6",
                outline="#E5E7EB",
            )

    footer = single["footer"]
    for key in ("upgrades_box", "warning_box", "receipt_box"):
        b = footer[key]
        fill = color("warning_bg") if key == "warning_box" else "#FFFFFF"
        outline = color("warning_border") if key == "warning_box" else "#D1D5DB"
        draw.rounded_rectangle((b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]), radius=10, fill=fill, outline=outline, width=2)

    badge = single["header"].get("badge_box")
    if badge:
        draw.rounded_rectangle(
            (badge["x"], badge["y"], badge["x"] + badge["w"], badge["y"] + badge["h"]),
            radius=8,
            fill="#FFFFFF",
            outline="#D1D5DB",
            width=2,
        )
    return img


def create_carousel_template(topic: dict, layout: dict, slide_index: int) -> Image.Image:
    cw, ch = layout["canvas"]["width"], layout["canvas"]["height"]
    img = Image.new("RGB", (cw, ch), color("bg"))
    draw = ImageDraw.Draw(img)

    if slide_index == 0:
        cover = layout["carousel"]["cover"]
        badge = cover.get("badge_box")
        if badge:
            draw.rounded_rectangle(
                (badge["x"], badge["y"], badge["x"] + badge["w"], badge["y"] + badge["h"]),
                radius=10,
                fill="#FFFFFF",
                outline="#D1D5DB",
                width=2,
            )
        return img

    slide = layout["carousel"]["slides"][slide_index - 1]
    accent = slide.get("background_accent", topic["cards"][slide_index - 1]["accent"])
    draw.rectangle((0, 0, cw, 100), fill=accent)
    iz = slide["regions"].get("illustration_zone")
    if iz:
        draw.rounded_rectangle(
            (iz["x"], iz["y"], iz["x"] + iz["w"], iz["y"] + iz["h"]),
            radius=12,
            fill="#F3F4F6",
            outline="#E5E7EB",
        )
    draw.rectangle((0, ch - 80, cw, ch), fill="#F9FAFB")
    return img


def overlay_single(img: Image.Image, topic: dict, layout: dict) -> Image.Image:
    draw = ImageDraw.Draw(img)
    single = layout["single"]
    header = topic["header"]

    for key in ("title", "subtitle"):
        cfg = single["header"][key]
        fill = color(cfg.get("color", "text"))
        if cfg.get("color") == "subtitle":
            fill = color("subtitle")
        draw_text(
            draw,
            (cfg["x"], cfg["y"]),
            header[key],
            load_font(cfg["size"], bold=cfg.get("bold", False)),
            fill,
            anchor=cfg.get("anchor", "lt"),
        )

    for key in ("badge_top", "badge_bottom"):
        cfg = single["header"][key]
        fill = color("subtitle") if cfg.get("color") == "subtitle" else color("text")
        draw_text(draw, (cfg["x"], cfg["y"]), header[key], load_font(cfg["size"]), fill, anchor=cfg.get("anchor", "lt"))

    for i, card in enumerate(topic["cards"]):
        cl = single["cards"][i]
        white = "#FFFFFF"
        draw_text(draw, (cl["no"]["x"], cl["no"]["y"]), card["no"], load_font(cl["no"]["size"], True), white)
        draw_text(draw, (cl["name"]["x"], cl["name"]["y"]), card["name"], load_font(cl["name"]["size"], True), white)
        if cl["price"].get("anchor") == "rm":
            draw_right(draw, cl["price"]["x"], cl["price"]["y"], card["price"], load_font(cl["price"]["size"]), white)
        else:
            draw_text(draw, (cl["price"]["x"], cl["price"]["y"]), card["price"], load_font(cl["price"]["size"]), white)

        by = cl["bullets"]["y"]
        bf = load_font(cl["bullets"]["size"])
        for bullet in card["bullets"]:
            draw.text((cl["bullets"]["x"], by), f"• {bullet}", font=bf, fill=color("text"))
            by += cl["bullets"].get("line_height", 30)

        bubble = cl["bubble"]
        bx, by = bubble["x"], bubble["y"]
        bfont = load_font(bubble["size"])
        if bubble.get("bg"):
            tw, th = text_size(draw, card["bubble"], bfont)
            pad = 10
            draw.rounded_rectangle((bx - tw // 2 - pad, by - th // 2 - pad, bx + tw // 2 + pad, by + th // 2 + pad), radius=8, fill="#FFFFFF", outline="#D1D5DB")
        draw_text(draw, (bx, by), card["bubble"], bfont, color("text"), anchor=bubble.get("anchor", "lt"))

        ef = cl["effect"]
        draw.text((ef["x"], ef["y"]), f"效果：{card['effect']}", font=load_font(ef["size"], True), fill=color("text"))

    footer = single["footer"]
    ft = footer["upgrades_title"]
    draw.text((ft["x"], ft["y"]), "隐藏升级包", font=load_font(ft["size"], True), fill=color("text"))
    uy = footer["upgrades_items"]["y"]
    for item in topic["footer"]["upgrades"]:
        draw.text((footer["upgrades_items"]["x"], uy), f"☐ {item}", font=load_font(footer["upgrades_items"]["size"]), fill=color("text"))
        uy += footer["upgrades_items"].get("line_height", 34)

    warn = footer["warning_text"]
    draw_text(draw, (warn["x"], warn["y"]), topic["footer"]["warning"], load_font(warn["size"]), color("text"), anchor=warn.get("anchor", "lt"), max_width=warn.get("max_width"))

    rt = footer["receipt_title"]
    draw.text((rt["x"], rt["y"]), "账单明细", font=load_font(rt["size"], True), fill=color("text"))
    ry = footer["receipt_lines"]["y"]
    lf = load_font(footer["receipt_lines"]["size"])
    rb = footer["receipt_box"]
    for line in topic["footer"]["receipt"]["lines"]:
        draw.text((footer["receipt_lines"]["x"], ry), line["label"], font=lf, fill=color("text"))
        draw_right(draw, rb["x"] + rb["w"] - 16, ry, line["amount"], lf, color("text"))
        ry += footer["receipt_lines"].get("line_height", 28)

    receipt = topic["footer"]["receipt"]
    draw.text((footer["receipt_total"]["x"], footer["receipt_total"]["y"]), f"合计  {receipt['total']}", font=load_font(footer["receipt_total"]["size"], True), fill=color("text"))
    draw.text((footer["receipt_balance"]["x"], footer["receipt_balance"]["y"]), f"余额  {receipt['balance']}", font=load_font(footer["receipt_balance"]["size"]), fill=color("subtitle"))
    note = footer["receipt_note"]
    draw_text(draw, (note["x"], note["y"]), receipt["note"], load_font(note["size"], True), color("subtitle"), anchor=note.get("anchor", "lt"))

    tag = single["tagline"]
    draw_text(draw, (tag["x"], tag["y"]), topic["footer"]["tagline"], load_font(tag["size"], True), color("text"), anchor=tag.get("anchor", "lt"))
    return img


def overlay_carousel_slide(img: Image.Image, topic: dict, layout: dict, slide_index: int) -> Image.Image:
    draw = ImageDraw.Draw(img)
    carousel = layout["carousel"]

    if slide_index == 0:
        cover = carousel["cover"]
        header = topic["header"]
        for key, src in (("title", header["title"]), ("subtitle", header["subtitle"])):
            cfg = cover[key]
            fill = color("subtitle") if cfg.get("color") == "subtitle" else color("text")
            draw_text(draw, (cfg["x"], cfg["y"]), src, load_font(cfg["size"], cfg.get("bold", False)), fill, anchor=cfg.get("anchor", "lt"))
        for key, src in (("badge_top", header["badge_top"]), ("badge_bottom", header["badge_bottom"])):
            cfg = cover[key]
            fill = color("subtitle") if cfg.get("color") == "subtitle" else color("text")
            draw_text(draw, (cfg["x"], cfg["y"]), src, load_font(cfg["size"]), fill, anchor=cfg.get("anchor", "lt"))
        teaser = cover.get("teaser", {})
        teaser_text = teaser.get("text", f"合计 {topic['footer']['receipt']['total']}")
        draw_text(draw, (teaser["x"], teaser["y"]), teaser_text, load_font(teaser.get("size", 32), True), color("subtitle"), anchor=teaser.get("anchor", "lt"))
        draw_text(draw, (540, 1400), topic["footer"]["tagline"], load_font(20), color("text"), anchor="mm")
        return img

    slide = carousel["slides"][slide_index - 1]
    card = topic["cards"][slide_index - 1]
    regions = slide["regions"]
    white = "#FFFFFF"

    draw_text(draw, (regions["no"]["x"], regions["no"]["y"]), card["no"], load_font(regions["no"]["size"], True), white)
    draw_text(draw, (regions["name"]["x"], regions["name"]["y"]), card["name"], load_font(regions["name"]["size"], True), white)

    price_cfg = regions.get("price", {})
    if price_cfg:
        draw_right(draw, price_cfg["x"], price_cfg["y"], card["price"], load_font(price_cfg["size"]), white)

    by = regions["bullets"]["y"]
    bf = load_font(regions["bullets"]["size"])
    for bullet in card["bullets"]:
        draw.text((regions["bullets"]["x"], by), f"• {bullet}", font=bf, fill=color("text"))
        by += regions["bullets"].get("line_height", 36)

    bubble = regions["bubble"]
    bfont = load_font(bubble["size"])
    bx, by = bubble["x"], bubble["y"]
    if bubble.get("bg"):
        tw, th = text_size(draw, card["bubble"], bfont)
        pad = 12
        draw.rounded_rectangle((bx - tw // 2 - pad, by - th // 2 - pad, bx + tw // 2 + pad, by + th // 2 + pad), radius=10, fill="#FFFFFF", outline="#D1D5DB")
    draw_text(draw, (bx, by), card["bubble"], bfont, color("text"), anchor=bubble.get("anchor", "lt"))

    ef = regions["effect"]
    draw.text((ef["x"], ef["y"]), f"效果：{card['effect']}", font=load_font(ef["size"], True), fill=color("text"))
    return img


def load_base(path: Path, layout: dict) -> Image.Image | None:
    if not path.exists():
        return None
    img = Image.open(path).convert("RGB")
    cw, ch = layout["canvas"]["width"], layout["canvas"]["height"]
    if img.size != (cw, ch):
        img = img.resize((cw, ch), Image.Resampling.LANCZOS)
    return img


def compose_single(topic_id: str, template_only: bool = False) -> Path:
    sync_topic_to_output(topic_id)
    topic = load_topic(topic_id)
    layout = load_topic_layout(topic_id)
    paths = topic_paths(topic_id)
    paths["output_dir"].mkdir(parents=True, exist_ok=True)
    (paths["output_dir"] / "output").mkdir(parents=True, exist_ok=True)

    img = load_base(paths["base_png"], layout)
    if img is None or template_only:
        img = create_single_template(topic, layout)
    img = overlay_single(img, topic, layout)
    img.save(paths["final_png"], format="PNG", optimize=True)
    print(f"Saved single: {paths['final_png']}")
    return paths["final_png"]


def compose_carousel(topic_id: str, template_only: bool = False) -> list[Path]:
    sync_topic_to_output(topic_id)
    topic = load_topic(topic_id)
    layout = load_topic_layout(topic_id)
    paths = topic_paths(topic_id)
    paths["carousel_dir"].mkdir(parents=True, exist_ok=True)
    paths["carousel_base_dir"].mkdir(parents=True, exist_ok=True)

    names = ["00-cover.png", "01.png", "02.png", "03.png", "04.png"]
    outputs = []
    for idx, name in enumerate(names):
        base_path = paths["carousel_base_dir"] / f"base-{idx:02d}.png"
        img = load_base(base_path, layout)
        if img is None or template_only:
            img = create_carousel_template(topic, layout, idx)
        img = overlay_carousel_slide(img, topic, layout, idx)
        out = paths["carousel_dir"] / name
        img.save(out, format="PNG", optimize=True)
        outputs.append(out)
        print(f"Saved carousel: {out}")
    return outputs


def compose(topic_id: str, mode: str = "both", template_only: bool = False) -> dict:
    results: dict = {}
    if mode in ("single", "both"):
        results["single"] = compose_single(topic_id, template_only=template_only)
    if mode in ("carousel", "both"):
        results["carousel"] = compose_carousel(topic_id, template_only=template_only)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Compose 9:16 infographic")
    parser.add_argument("--id", required=True)
    parser.add_argument("--mode", choices=["single", "carousel", "both"], default="both")
    parser.add_argument("--template-only", action="store_true")
    args = parser.parse_args()
    compose(args.id, mode=args.mode, template_only=args.template_only)


if __name__ == "__main__":
    main()
