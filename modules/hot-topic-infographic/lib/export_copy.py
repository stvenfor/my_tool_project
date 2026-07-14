#!/usr/bin/env python3
"""Export Douyin / Xiaohongshu copy from topic JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import SCRIPT_DIR, ROOT, load_topic, sync_topic_to_output, topic_paths


def card_one_liner(card: dict) -> str:
    return f"- {card['name']} {card['price']} — {card['effect']}"


def build_douyin_description(topic: dict) -> str:
    theme = topic["meta"].get("theme", topic["id"])
    total = topic["footer"]["receipt"]["total"]
    names = " + ".join(c["name"] for c in topic["cards"])
    hook = topic["hooks"][0] if topic.get("hooks") else "你中了几个？"
    return (
        f"2026 版{theme}：{names}。\n\n"
        f"账单合计 {total}，{topic['footer']['receipt']['note']}。\n\n"
        f"{hook}"
    )


def build_xiaohongshu_title(topic: dict) -> str:
    theme = topic["meta"].get("theme", topic["id"])
    return f"2026 {theme}：{topic['header']['title']}"


def build_xiaohongshu_body(topic: dict, carousel: bool = False) -> str:
    lines = [topic["header"]["subtitle"], ""]
    if carousel:
        lines.extend(["本篇为 9:16 轮播组图（封面+四格），建议按顺序滑动阅读。", ""])
    lines.append("四件套账单：")
    for card in topic["cards"]:
        lines.append(card_one_liner(card))
    receipt = topic["footer"]["receipt"]
    lines.extend(
        [
            "",
            f"合计 {receipt['total']}，余额 {receipt['balance']}，{receipt['note']}。",
            "",
            topic["footer"]["tagline"],
            "",
            "---",
            "",
            "来聊聊：",
        ]
    )
    for i, hook in enumerate(topic.get("hooks", []), 1):
        lines.append(f"{i}. {hook}")
    return "\n".join(lines)


def carousel_image_paths(paths: dict) -> list[str]:
    carousel_dir = paths["carousel_dir"]
    names = ["00-cover.png", "01.png", "02.png", "03.png", "04.png"]
    return [str((carousel_dir / n).resolve()) for n in names]


def export_copy(topic_id: str, mode: str = "both") -> dict[str, Path]:
    sync_topic_to_output(topic_id)
    topic = load_topic(topic_id)
    paths = topic_paths(topic_id)
    paths["copy_dir"].mkdir(parents=True, exist_ok=True)

    douyin_desc = build_douyin_description(topic)
    carousel_paths = carousel_image_paths(paths)
    has_carousel = all(Path(p).exists() for p in carousel_paths)

    if mode == "carousel" and has_carousel:
        image_paths = carousel_paths
    elif mode == "single" and paths["final_png"].exists():
        image_paths = [str(paths["final_png"].resolve())]
    elif has_carousel:
        image_paths = carousel_paths
    elif paths["final_png"].exists():
        image_paths = [str(paths["final_png"].resolve())]
    else:
        image_paths = carousel_paths

    douyin_json = {
        "imagePaths": image_paths,
        "description": douyin_desc,
        "tags": topic["copy"]["douyin_tags"][:5],
    }
    douyin_path = paths["copy_dir"] / "douyin.json"
    douyin_path.write_text(json.dumps(douyin_json, ensure_ascii=False, indent=2), encoding="utf-8")

    xhs_title = build_xiaohongshu_title(topic)
    xhs_body = build_xiaohongshu_body(topic, carousel=has_carousel)
    xhs_tags = " ".join(f"#{t}" for t in topic["copy"]["xiaohongshu_tags"])
    xhs_md = (
        f"# 小红书图文文案\n\n"
        f"## 标题\n\n{xhs_title}\n\n"
        f"## 正文\n\n{xhs_body}\n\n"
        f"## 标签\n\n{xhs_tags}\n\n"
        f"## 附件说明\n\n"
        f"- 单张长图：`output/final.png`（9:16）\n"
        f"- 轮播组图：`output/carousel/00-cover.png` ~ `04.png`\n"
    )
    xhs_path = paths["copy_dir"] / "xiaohongshu.md"
    xhs_path.write_text(xhs_md, encoding="utf-8")

    douyin_md = (
        f"# 抖音图文文案\n\n"
        f"## 描述\n\n{douyin_desc}\n\n"
        f"## 图片\n\n"
        + "\n".join(f"- `{p}`" for p in image_paths)
        + "\n\n## 话题\n\n"
        + "\n".join(f"- {t}" for t in topic["copy"]["douyin_tags"])
        + "\n"
    )
    (paths["copy_dir"] / "douyin.md").write_text(douyin_md, encoding="utf-8")

    print(f"Saved: {douyin_path}")
    print(f"Saved: {xhs_path}")
    return {"douyin": douyin_path, "xiaohongshu": xhs_path}


def export_all(mode: str = "both") -> None:
    approved_dir = (SCRIPT_DIR / "topics" / "approved")
    for path in sorted(approved_dir.glob("*.json")):
        export_copy(path.stem, mode=mode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export platform copy")
    parser.add_argument("--id", help="Topic id")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--mode", choices=["single", "carousel", "both"], default="both")
    args = parser.parse_args()

    if args.all:
        export_all(mode=args.mode)
    elif args.id:
        export_copy(args.id, mode=args.mode)
    else:
        parser.error("Provide --id or --all")


if __name__ == "__main__":
    main()
