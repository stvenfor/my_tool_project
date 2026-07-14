#!/usr/bin/env python3
"""Build whisper-aligned bilingual subtitles for yijia-xuchang reference."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent.parent

# 12 narrative beats merged from whisper + scene timing (移驾许昌 full episode)
SEGMENTS = [
    {
        "start_sec": 12.64,
        "end_sec": 24.16,
        "en": "Your majesty, I have a report. Yang Feng and Han Xian helped protect you. But now they are rude and bossy. Please punish them.",
        "zh": "陛下，臣有本奏。杨奉、韩暹曾护驾有功，如今却跋扈无礼，请陛下严惩。",
        "visual_keyword": "杨奉 韩暹 汉献帝 3D Q版三国",
        "phase": "story",
    },
    {
        "start_sec": 24.16,
        "end_sec": 36.56,
        "en": "Yang Feng, you're lying! You too. Stay or leave — the choice is yours. Yang Feng, you'll pay for this!",
        "zh": "杨奉，你撒谎！你也是。去或留，你自己选。杨奉，你会付出代价！",
        "visual_keyword": "杨奉 对峙 3D Q版",
        "phase": "story",
    },
    {
        "start_sec": 44.32,
        "end_sec": 53.36,
        "en": "Send for Xu Huang. Yes, general! Which group of generals does Xu Huang belong to?",
        "zh": "传徐晃来。遵命，将军！徐晃属于哪一类将军？",
        "visual_keyword": "徐晃 曹操 3D Q版三国",
        "phase": "story",
    },
    {
        "start_sec": 54.08,
        "end_sec": 61.92,
        "en": "A, the five tiger generals. B, the five elite generals. C, the five dragon generals.",
        "zh": "A，五虎上将。B，五子良将。C，五龙上将。",
        "visual_keyword": "选择题 五子良将 3D Q版",
        "phase": "story",
    },
    {
        "start_sec": 63.12,
        "end_sec": 69.36,
        "en": "Xu Huang, Yang Feng can't protect you. Join me and you'll be safe.",
        "zh": "徐晃，杨奉保护不了你。跟我，你就安全。",
        "visual_keyword": "曹操 徐晃 招降 3D Q版",
        "phase": "story",
    },
    {
        "start_sec": 74.4,
        "end_sec": 79.44,
        "en": "I will serve you. Great! From now on, we fight together.",
        "zh": "愿效忠将军。好！从今以后，我们一起战斗。",
        "visual_keyword": "徐晃 归顺 3D Q版",
        "phase": "story",
    },
    {
        "start_sec": 83.52,
        "end_sec": 90.08,
        "en": "Luoyang is very old and broken now, and we don't have enough food. Could we move somewhere else?",
        "zh": "洛阳如今残破不堪，粮食也不够。能迁到别处吗？",
        "visual_keyword": "洛阳废墟 缺粮 3D Q版",
        "phase": "story",
    },
    {
        "start_sec": 90.56,
        "end_sec": 95.6,
        "en": "Xuchang has plenty of food and is your base. This is a great plan.",
        "zh": "许昌粮足，又是将军根基。这是好主意。",
        "visual_keyword": "许昌 粮仓 地图 3D Q版",
        "phase": "story",
    },
    {
        "start_sec": 99.52,
        "end_sec": 105.28,
        "en": "Your majesty, we have no food here. Please move to Xuchang.",
        "zh": "陛下，此处无粮，请移驾许昌。",
        "visual_keyword": "移驾许昌 汉献帝 3D Q版",
        "phase": "story",
    },
    {
        "start_sec": 105.92,
        "end_sec": 116.08,
        "en": "I will follow your plan, General Cao. Then let's set off today.",
        "zh": "朕听从曹将军之计。那今日便出发吧。",
        "visual_keyword": "皇家车队 出发 3D Q版",
        "phase": "story",
    },
    {
        "start_sec": 125.52,
        "end_sec": 133.84,
        "en": "I'm making Xu Huang our top general. Great decision, your majesty.",
        "zh": "朕封徐晃为大将。陛下英明。",
        "visual_keyword": "拜将 徐晃 3D Q版",
        "phase": "story",
    },
    {
        "start_sec": 133.84,
        "end_sec": 141.767,
        "en": "Instead of complaining, take a brave new step. Cao Cao's power grew from here.",
        "zh": "别抱怨，勇敢迈出新一步。曹操霸业，从此开始。",
        "visual_keyword": "曹操 霸业 许昌 3D Q版",
        "phase": "closing",
    },
]

HOOK = {
    "zh": "儿童英语三国【移驾许昌】",
    "en": "Three Kingdoms English: Move to Xuchang",
    "duration_sec": 3.36,
    "visual_keyword": "三国 Q版 标题卡 移驾许昌 3D动画",
    "phase": "hook",
}


def build_subtitles(duration_sec: float = 141.767) -> dict:
    segments = []
    for seg in SEGMENTS:
        start = float(seg["start_sec"])
        end = float(seg["end_sec"])
        segments.append(
            {
                "start_sec": round(start, 3),
                "duration_sec": round(end - start, 3),
                "en": seg["en"],
                "zh": seg["zh"],
                "visual_keyword": seg["visual_keyword"],
                "phase": seg["phase"],
            }
        )
    return {
        "hook_zh": HOOK["zh"],
        "hook_en": HOOK["en"],
        "hook_duration_sec": HOOK["duration_sec"],
        "hook_visual_keyword": HOOK["visual_keyword"],
        "hook_phase": HOOK["phase"],
        "segments": segments,
        "duration_sec": duration_sec,
        "source": "whisper_aligned_v2",
    }


def main() -> None:
    out_dir = PROJECT / "modules/three-kingdoms-english-video/work/output/yijia-xuchang"
    template_path = ROOT / "copy" / "subtitles.template.json"
    subtitles = build_subtitles()

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "subtitles.json").write_text(json.dumps(subtitles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    template = {
        "hook": {
            "zh": HOOK["zh"],
            "en": HOOK["en"],
            "duration_sec": HOOK["duration_sec"],
            "visual_keyword": HOOK["visual_keyword"],
            "phase": HOOK["phase"],
        },
        "segments": [
            {
                "start_sec": s["start_sec"],
                "duration_sec": s["duration_sec"],
                "en": s["en"],
                "zh": s["zh"],
                "visual_keyword": s["visual_keyword"],
                "phase": s["phase"],
            }
            for s in subtitles["segments"]
        ],
    }
    template_path.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    parity_md = PROJECT / "modules/three-kingdoms-english-video/work/reference/yijia-xuchang/parity_report.md"
    lines = [
        "# 《移驾许昌》拉片报告 (Step1 定稿)\n",
        f"日期：2026-07-12\n",
        "## 台词切点表（Whisper 对齐）\n",
        "| # | start | end | EN | ZH |",
        "|---|-------|-----|----|----|",
        f"| hook | 0 | {HOOK['duration_sec']} | {HOOK['en']} | {HOOK['zh']} |",
    ]
    for i, s in enumerate(subtitles["segments"], 1):
        end = s["start_sec"] + s["duration_sec"]
        lines.append(f"| {i} | {s['start_sec']} | {end:.2f} | {s['en'][:50]}... | {s['zh'][:20]}... |")
    parity_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote {out_dir / 'subtitles.json'} ({len(subtitles['segments'])} segments)")
    print(f"Updated {template_path}")


if __name__ == "__main__":
    main()
