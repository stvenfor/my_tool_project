#!/usr/bin/env python3
"""Assemble 10x CET vocab: 30 days × (80 words + 40 phrases) → by-day/*.md + index."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "by-day"
INDEX = ROOT / "daily-vocab-30day.md"


def trim80(words):
    seen = set()
    out = []
    for w in words:
        key = w[0].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(w)
        if len(out) == 80:
            break
    if len(out) < 80:
        raise ValueError(f"only {len(out)} unique words")
    return out


def trim40(phrases):
    seen = set()
    out = []
    for p in phrases:
        key = p[0].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
        if len(out) == 40:
            break
    if len(out) < 40:
        raise ValueError(f"only {len(out)} unique phrases")
    return out


def render_day(d: dict) -> str:
    n = d["n"]
    lines = [
        f"# Day {n} — {d['title']}",
        "",
        f"本日 **80 词 + 40 短语**（四六级）。跟读音标 → 英译中 → 中译英。",
        "",
        "## 词根词缀",
        "",
        "| 成分 | 含义 | 例词 |",
        "|------|------|------|",
    ]
    for root, meaning, examples in d["roots"]:
        lines.append(f"| **{root}** | {meaning} | {examples} |")
    lines += [
        "",
        "## 单词（80）",
        "",
        "| # | 单词 | 音标 | 词性/中文 | 词源提示 | 学完 |",
        "|---|------|------|-----------|----------|------|",
    ]
    for i, (word, ipa, gloss, tip) in enumerate(d["words"], 1):
        ipa = ipa if ipa.startswith("/") else f"/{ipa.strip('/')}/"
        lines.append(f"| {i} | **{word}** | {ipa} | {gloss} | {tip} | [ ] |")
    lines += [
        "",
        "## 短语（40）",
        "",
        "| # | 短语 | 音标 | 中文 | 例句 | 学完 |",
        "|---|------|------|------|------|------|",
    ]
    for i, (phrase, ipa, gloss, ex) in enumerate(d["phrases"], 1):
        ipa = ipa if ipa.startswith("/") else f"/{ipa.strip('/')}/"
        lines.append(f"| {i} | {phrase} | {ipa} | {gloss} | {ex} | [ ] |")
    lines.append("")
    return "\n".join(lines)


def load_partial():
    """Load whatever complete-enough days exist from prior scripts."""
    days = {}

    from _gen_vocab_days_1_10 import (
        day1_words,
        day1_phrases,
        day2_words,
        day2_phrases,
        day3_words,
        day3_phrases,
    )

    days[1] = {
        "n": 1,
        "title": "认知与学习 | cogn / sci / prehend / ceiv",
        "roots": [
            ("cogn", "知道、认识", "recognize, cognitive, cognition"),
            ("sci", "知道", "science, conscious, conscience"),
            ("prehend", "抓住", "comprehend, apprehend, comprehensive"),
            ("ceiv / cept", "取", "perceive, receive, concept"),
        ],
        "words": trim80(day1_words()),
        "phrases": trim40(day1_phrases()),
    }
    days[2] = {
        "n": 2,
        "title": "论证与观点 | dict / claim / spect",
        "roots": [
            ("dict / dic", "说、宣称", "predict, contradict, dictate"),
            ("claim", "声称", "proclaim, exclaim, reclaim"),
            ("spect / spec", "看", "perspective, speculate, inspect"),
            ("contra- / pre-", "相反 / 预先", "contradict, predict"),
        ],
        "words": trim80(day2_words()),
        "phrases": trim40(day2_phrases()),
    }
    days[3] = {
        "n": 3,
        "title": "因果与逻辑 | sequ / tribut / duc",
        "roots": [
            ("sequ / secut", "跟随", "sequence, subsequent, consecutive"),
            ("tribut", "给予", "attribute, contribute, distribute"),
            ("duc / duct", "引导", "induce, deduce, conduct"),
            ("caus / effect", "因果", "cause, causal, effect"),
        ],
        "words": trim80(day3_words()),
        "phrases": trim40(day3_phrases()),
    }
    return days


ROOTS_DEFAULT = [
    ("re-", "再、回", "retain, revise, reinforce"),
    ("in- / im-", "否定或进入", "inevitable, influence"),
    ("con- / com-", "共同", "contribute, compose"),
    ("-ion / -tion", "名词：行为/状态", "recognition, inflation"),
]


def parse_bank_file(path: Path) -> dict:
    """Format:
    #TITLE title text
    #ROOT root|meaning|examples
    #WORD word|ipa|gloss|tip
    #PHRASE phrase|ipa|gloss|example
    """
    title = path.stem
    roots = []
    words = []
    phrases = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("#TITLE "):
            title = line[7:].strip()
        elif line.startswith("#ROOT "):
            a, b, c = line[6:].split("|", 2)
            roots.append((a.strip(), b.strip(), c.strip()))
        elif line.startswith("#WORD "):
            a, b, c, d = line[6:].split("|", 3)
            words.append((a.strip(), b.strip(), c.strip(), d.strip()))
        elif line.startswith("#PHRASE "):
            a, b, c, d = line[8:].split("|", 3)
            phrases.append((a.strip(), b.strip(), c.strip(), d.strip()))
    if not roots:
        roots = ROOTS_DEFAULT
    return {
        "title": title,
        "roots": roots,
        "words": trim80(words),
        "phrases": trim40(phrases),
    }


def main():
    OUT_DIR.mkdir(exist_ok=True)
    days = load_partial()

    bank = ROOT / "bank"
    bank.mkdir(exist_ok=True)
    for p in sorted(bank.glob("day*.txt")):
        m = re.match(r"day(\d+)\.txt", p.name)
        if not m:
            continue
        n = int(m.group(1))
        data = parse_bank_file(p)
        days[n] = {"n": n, **data}

    # Try load more from build scripts if bank missing
    missing = [i for i in range(1, 31) if i not in days]
    if missing:
        print("Missing days (need bank/dayNN.txt):", missing)

    for n in sorted(days):
        d = days[n]
        assert len(d["words"]) == 80, n
        assert len(d["phrases"]) == 40, n
        path = OUT_DIR / f"day-{n:02d}.md"
        path.write_text(render_day(d), encoding="utf-8")
        print("wrote", path.name)

    # Index
    lines = [
        "# 30 天四六级词汇（10× 扩容版）",
        "",
        "每天 **80 个单词（含音标）+ 40 个短语（含音标）+ 词根词缀**。",
        "",
        "**学法（约 90–120 min）**",
        "1. 音标跟读 → 英译中 → 中译英",
        "2. 词根串记同族词",
        "3. 短语整句跟读；睡前复习昨天 20 词",
        "",
        "分日文件在 [`by-day/`](by-day/)；下表可跳转。",
        "",
        "| Day | 主题 | 文件 |",
        "|-----|------|------|",
    ]
    for n in range(1, 31):
        if n not in days:
            lines.append(f"| {n} | （待补） | — |")
            continue
        title = days[n]["title"].replace("|", "/")
        lines.append(f"| {n} | {title} | [day-{n:02d}.md](by-day/day-{n:02d}.md) |")
    lines += [
        "",
        "## 进度建议",
        "",
        "- Day 7 / 14 / 21 / 28 / 30：以复习薄弱项为主（文件仍是完整 80+40，可当自测卷）",
        "- 每日不必一次学完 80 词：可拆成早 40 + 晚 40",
        "",
    ]
    INDEX.write_text("\n".join(lines), encoding="utf-8")
    print("index →", INDEX)
    print(f"done: {len(days)}/30 days")


if __name__ == "__main__":
    main()
