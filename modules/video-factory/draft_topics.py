#!/usr/bin/env python3
"""Generate draft topic JSON files for video-factory."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from lib import TOPICS_DIR, save_json, slugify

DRAFT_SEEDS = [
    {
        "id": "worker-salary-silence",
        "mode": "narration",
        "series": "打工逆袭",
        "title": "工资沉默的代价",
        "hook": "为什么你越努力，越不敢谈钱？",
        "tags": ["职场", "打工人", "人间清醒"],
        "visual_strategy": "stickman",
        "skip_analyze": True,
    },
    {
        "id": "workplace-taboo-narration",
        "mode": "narration",
        "series": "认知提升",
        "title": "职场三大禁忌",
        "hook": "聪明人从不在办公室说这三句话",
        "tags": ["职场", "处世智慧", "人性洞察"],
        "visual_strategy": "stickman",
        "skip_analyze": True,
    },
    {
        "id": "ai-poverty-narration",
        "mode": "narration",
        "series": "认知提升",
        "title": "AI时代的新贫困",
        "hook": "不会用AI的人，正在被悄悄甩开",
        "tags": ["AI", "自我成长", "认知提升"],
        "visual_strategy": "stickman",
        "skip_analyze": True,
    },
    {
        "id": "agent-productivity-narration",
        "mode": "narration",
        "series": "认知提升",
        "title": "Agent才是生产力",
        "hook": "你还在手动干活，别人已经让Agent跑起来了",
        "tags": ["AI", "效率", "职场"],
        "visual_strategy": "stickman",
        "skip_analyze": True,
    },
    {
        "id": "middle-class-burnout",
        "mode": "narration",
        "series": "认知提升",
        "title": "中产倦怠症",
        "hook": "收入涨了，快乐却没了，怎么回事？",
        "tags": ["自我成长", "人间清醒", "低欲生活"],
        "visual_strategy": "stickman",
        "skip_analyze": True,
    },
    {
        "id": "workplace-ep01",
        "mode": "dialogue",
        "series": "打工逆袭",
        "episode": "01",
        "title": "背锅三年，一朝翻盘",
        "hook": "",
        "cta": "下一集：离职还是升职？",
        "tags": ["职场", "逆袭", "打工人", "爽剧"],
        "visual_strategy": "manual_image",
        "voice_strategy": "edge_tts_multi",
        "script_source": "modules/video-factory/work/workplace-drama/EP01/script.json",
        "skip_analyze": True,
    },
    {
        "id": "talking-head-demo",
        "mode": "talking_head",
        "series": "认知提升",
        "title": "每天3分钟人间清醒",
        "hook": "今天聊一个很多人不愿意承认的真相",
        "tags": ["自我成长", "口播", "认知提升"],
        "visual_strategy": "talking_head",
        "voice_strategy": "edge_tts",
        "skip_analyze": True,
        "presenter_image": "modules/video-factory/assets/presenter/default.png",
    },
]


def create_draft(seed: dict) -> Path:
    draft_dir = TOPICS_DIR / "draft"
    draft_dir.mkdir(parents=True, exist_ok=True)
    topic_id = slugify(str(seed["id"]))
    payload = {
        **seed,
        "id": topic_id,
        "status": "draft",
        "episode": seed.get("episode", "01"),
        "cta": seed.get("cta", "建议收藏，持续更新"),
        "reference_url": seed.get("reference_url", ""),
        "use_llm": seed.get("use_llm", True),
        "meta": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": "video-factory:draft",
        },
    }
    path = draft_dir / f"{topic_id}.json"
    save_json(path, payload)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate draft topics.")
    parser.add_argument("--count", type=int, default=0, help="Limit number of seeds")
    parser.add_argument("--all", action="store_true", help="Write all built-in seeds")
    args = parser.parse_args()

    seeds = DRAFT_SEEDS
    if args.count > 0:
        seeds = seeds[: args.count]
    if not args.all and args.count == 0:
        seeds = seeds[:5]

    created = []
    for seed in seeds:
        path = create_draft(seed)
        created.append(str(path))
    print(json.dumps({"created": created, "count": len(created)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
