#!/usr/bin/env python3
"""Shared LLM topic generation helpers."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import date
from typing import Any

from common import SCHEMA_PATH

BASE_SYSTEM_PROMPT = """你是中文社媒讽刺信息图文案策划。根据热点关键词，生成「四件套」讽刺图文 topic JSON。

要求：
- 讽刺自嘲、有讨论性，不人身攻击、不造谣
- 四格必须是同一主题下的4个消费/认知陷阱或关系雷区，有递进
- 严格 JSON，无 markdown
- 字段约束：header.title≤18字，subtitle≤24字，每条bullet≤14字，bubble≤16字，effect≤14字
- cards 固定4项，hooks 固定4项，footer.upgrades 固定4项，receipt.lines 4-6行
- accent 色：#2563EB #16A34A #EA580C #64748B #DC2626 可按主题微调
- scene_prompt 用英文描述漫画场景，不含可读文字
- copy.douyin_tags 3-5个，copy.xiaohongshu_tags 3-8个
- meta 必须包含 category、angle、framing 字段
"""


def extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def build_category_system_prompt(category_slug: str, category_cfg: dict) -> str:
    label = category_cfg.get("label", category_slug)
    tone = category_cfg.get("tone", "讽刺自嘲")
    framing = category_cfg.get("framing", "四件套清单")
    return (
        f"{BASE_SYSTEM_PROMPT}\n"
        f"目标人群：{label}\n"
        f"语气风格：{tone}\n"
        f"内容框架：{framing}\n"
        f"meta.category 固定为 \"{category_slug}\"\n"
    )


def call_openai_topic(
    *,
    topic_id: str,
    theme: str,
    keywords: list[str],
    system_prompt: str | None = None,
    extra_context: str = "",
    category_slug: str | None = None,
    angle: str | None = None,
    framing: str | None = None,
    card_hints: list[str] | None = None,
) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    schema_hint = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""
    kw_str = ", ".join(keywords)
    hints_block = ""
    if card_hints:
        hints_block = "四格方向提示：" + " / ".join(card_hints) + "\n"

    user_prompt = (
        f"topic id: {topic_id}\n"
        f"theme: {theme}\n"
        f"keywords: {kw_str}\n"
        f"status: draft\n"
        f"created_at: {date.today().isoformat()}\n"
    )
    if category_slug:
        user_prompt += f"meta.category: {category_slug}\n"
    if angle:
        user_prompt += f"meta.angle: {angle}\n"
    if framing:
        user_prompt += f"meta.framing: {framing}\n"
    if hints_block:
        user_prompt += f"\n{hints_block}"
    if extra_context:
        user_prompt += f"\n{extra_context}\n"
    user_prompt += (
        f"\nJSON Schema reference:\n{schema_hint[:4000]}\n\n"
        "Output only valid JSON object."
    )

    payload = {
        "model": os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        "messages": [
            {"role": "system", "content": system_prompt or BASE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.8,
        "response_format": {"type": "json_object"},
    }

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    content = result["choices"][0]["message"]["content"]
    data = extract_json(content)
    return normalize_topic(
        data,
        topic_id=topic_id,
        theme=theme,
        keywords=keywords,
        category_slug=category_slug,
        angle=angle,
        framing=framing,
    )


def normalize_topic(
    data: dict,
    *,
    topic_id: str,
    theme: str,
    keywords: list[str],
    category_slug: str | None = None,
    angle: str | None = None,
    framing: str | None = None,
) -> dict:
    data["id"] = topic_id
    data.setdefault("status", "draft")
    data.setdefault("meta", {})
    data["meta"].setdefault("theme", theme)
    data["meta"].setdefault("hot_keywords", keywords)
    data["meta"].setdefault("tone", "satire")
    data["meta"].setdefault("created_at", date.today().isoformat())
    if category_slug:
        data["meta"]["category"] = category_slug
    if angle:
        data["meta"]["angle"] = angle
    if framing:
        data["meta"]["framing"] = framing
    return data


def fallback_draft(
    *,
    topic_id: str,
    theme: str,
    keywords: list[str],
    category_slug: str | None = None,
    angle: str | None = None,
    framing: str | None = None,
    card_hints: list[str] | None = None,
) -> dict:
    label = keywords[0] if keywords else theme
    hints = card_hints or []
    accents = ["#2563EB", "#16A34A", "#EA580C", "#64748B"]

    cards = []
    for i in range(4):
        name = hints[i] if i < len(hints) else f"陷阱{i + 1}"
        kw = keywords[i] if i < len(keywords) else name
        cards.append(
            {
                "no": f"{i + 1:02d}",
                "name": name[:12],
                "price": "代价高",
                "accent": accents[i],
                "bullets": [
                    f"{kw}很常见",
                    "以为能掌控",
                    "其实更焦虑",
                ],
                "scene_prompt": "person looking stressed in everyday life scene",
                "bubble": "又踩坑了",
                "effect": "越挣扎越内耗",
            }
        )

    return {
        "id": topic_id,
        "status": "draft",
        "meta": {
            "theme": theme,
            "hot_keywords": keywords,
            "tone": "satire",
            "created_at": date.today().isoformat(),
            **({"category": category_slug} if category_slug else {}),
            **({"angle": angle} if angle else {}),
            **({"framing": framing} if framing else {}),
        },
        "header": {
            "title": f"{theme}四件套"[:18],
            "subtitle": f"踩中一条，{label}更难受"[:24],
            "badge_top": "越干越亏",
            "badge_bottom": "余额不足",
        },
        "cards": cards,
        "footer": {
            "upgrades": ["情绪保险", "付费社群", "大师课程", "自救指南"],
            "warning": "本清单不保证解决问题，只保证引发共鸣。请理性看待。",
            "receipt": {
                "lines": [
                    {"label": cards[0]["name"], "amount": "内耗+1"},
                    {"label": cards[1]["name"], "amount": "内耗+2"},
                    {"label": cards[2]["name"], "amount": "内耗+3"},
                    {"label": cards[3]["name"], "amount": "内耗+4"},
                ],
                "total": "精神破产",
                "balance": "-∞",
                "note": "已透支",
            },
            "tagline": "认真生活，别踩这些坑。",
        },
        "hooks": [
            "你中了几个？",
            "哪个最扎心？",
            "你会劝朋友避坑吗？",
            "如果只能改一个？",
        ],
        "copy": {
            "douyin_tags": [theme[:8], label[:6], "避坑", "共鸣"],
            "xiaohongshu_tags": [theme[:8], "避坑", "日常", "共鸣", "讨论"],
        },
    }


def generate_topic_data(
    *,
    topic_id: str,
    theme: str,
    keywords: list[str],
    use_llm: bool = True,
    system_prompt: str | None = None,
    extra_context: str = "",
    category_slug: str | None = None,
    angle: str | None = None,
    framing: str | None = None,
    card_hints: list[str] | None = None,
) -> tuple[dict, str]:
    """Return (topic_data, source) where source is 'llm' or 'fallback'."""
    fallback_kwargs: dict[str, Any] = {
        "topic_id": topic_id,
        "theme": theme,
        "keywords": keywords,
        "category_slug": category_slug,
        "angle": angle,
        "framing": framing,
        "card_hints": card_hints,
    }
    llm_kwargs = {
        **fallback_kwargs,
        "system_prompt": system_prompt,
        "extra_context": extra_context,
    }

    if use_llm and os.environ.get("OPENAI_API_KEY"):
        try:
            return call_openai_topic(**llm_kwargs), "llm"
        except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, json.JSONDecodeError) as exc:
            print(f"LLM failed ({exc}), using fallback template")
            return fallback_draft(**fallback_kwargs), "fallback"

    print("Using fallback template (no OPENAI_API_KEY or --no-llm)")
    return fallback_draft(**fallback_kwargs), "fallback"
