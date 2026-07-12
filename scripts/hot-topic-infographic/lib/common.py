#!/usr/bin/env python3
"""Shared helpers for hot-topic infographic pipeline."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = SCRIPT_DIR / "config.json"
CATEGORIES_PATH = SCRIPT_DIR / "config" / "categories.json"
CATEGORY_PREVIEW_ROOT = ROOT / "_hot-topic-infographic" / "category-previews"
SCHEMA_PATH = SCRIPT_DIR / "schema" / "topic.schema.json"
LAYOUT_SCHEMA_PATH = SCRIPT_DIR / "schema" / "layout.schema.json"
LAYOUT_PATH = SCRIPT_DIR / "templates" / "layout.json"  # legacy fallback reference only

FONT_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def load_categories() -> dict:
    if CATEGORIES_PATH.exists():
        return json.loads(CATEGORIES_PATH.read_text(encoding="utf-8"))
    return {}


def topic_paths(topic_id: str) -> dict[str, Path]:
    cfg = load_config()
    out_root = ROOT / cfg.get("output_root", "_hot-topic-infographic") / topic_id
    upload_subdir = cfg.get("upload_images_subdir", "upload-images")
    carousel_dir = out_root / "output" / "carousel"
    carousel_base_dir = out_root / "carousel"
    return {
        "output_dir": out_root,
        "topic_json": out_root / "topic.json",
        "layout_json": out_root / "layout.json",
        "base_png": out_root / "base.png",
        "final_png": out_root / "output" / "final.png",
        "carousel_dir": carousel_dir,
        "carousel_base_dir": carousel_base_dir,
        "copy_dir": out_root / "copy",
        "upload_images_dir": out_root / upload_subdir,
        "draft_json": SCRIPT_DIR / "topics" / "draft" / f"{topic_id}.json",
        "approved_json": SCRIPT_DIR / "topics" / "approved" / f"{topic_id}.json",
    }


def ensure_topic_dirs(topic_id: str) -> dict[str, Path]:
    paths = topic_paths(topic_id)
    paths["upload_images_dir"].mkdir(parents=True, exist_ok=True)
    return paths


def find_topic_json(topic_id: str) -> Path:
    paths = topic_paths(topic_id)
    for candidate in (paths["approved_json"], paths["draft_json"], paths["topic_json"]):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Topic JSON not found for id={topic_id}")


def load_topic(topic_id: str) -> dict:
    return json.loads(find_topic_json(topic_id).read_text(encoding="utf-8"))


def sync_topic_to_output(topic_id: str) -> Path:
    src = find_topic_json(topic_id)
    dst = topic_paths(topic_id)["topic_json"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return dst


def load_topic_layout(topic_id: str) -> dict:
    path = topic_paths(topic_id)["layout_json"]
    if not path.exists():
        raise FileNotFoundError(f"Layout not found: {path}. Run generate_layout.py first.")
    return json.loads(path.read_text(encoding="utf-8"))


def load_layout() -> dict:
    """Legacy global layout — prefer load_topic_layout."""
    if LAYOUT_PATH.exists():
        return json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
    cfg = load_config()
    return {
        "canvas": {"width": cfg.get("canvas_width", 1080), "height": cfg.get("canvas_height", 1920)},
        "colors": {
            "bg": "#F5F0E8",
            "text": "#1A1A1A",
            "subtitle": "#DC2626",
            "warning_bg": "#FEF3C7",
            "warning_border": "#F59E0B",
            "receipt_bg": "#FFFFFF",
        },
    }
