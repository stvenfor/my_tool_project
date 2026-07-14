#!/usr/bin/env python3
"""Generate cognitive video script.json from transcript or LLM."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import (  # noqa: E402
    extract_emphasis,
    infer_phase,
    load_json,
    resolve_work_dir,
    save_json,
    split_chinese_sentences,
    visual_keyword_for_phase,
)

LLM_SYSTEM_PROMPT = """你是抖音认知类短视频脚本策划。根据话题生成 script JSON。

结构要求：
- 痛点提问 → 反常识结论 → 2-4 个论证点 → 行动建议 → CTA
- 每段 narration 口语化、有冲击力，15-40字
- emphasis 从 narration 中提取 1-3 个关键词
- visual_keyword 描述 B-roll 画面（中文，4-8字）

严格输出 JSON，无 markdown。字段：
series, episode, title, hook, segments[], cta, tags[]

segments 每项：id, narration, emphasis[], visual_keyword, phase
phase 取值：pain | insight | contrast | action | cta
"""


def _call_openai_script(topic: str, config: dict[str, Any]) -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    user_prompt = (
        f"topic: {topic}\n"
        f"series: {config.get('series', '认知提升')}\n"
        f"episode: {config.get('episode', '01')}\n"
        f"title: {config.get('title', '')}\n"
        f"hook: {config.get('hook', '')}\n"
        f"tags: {', '.join(config.get('tags', []))}\n"
        "Output only valid JSON."
    )

    payload = {
        "model": os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        "messages": [
            {"role": "system", "content": LLM_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
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
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API error: {detail}") from exc

    content = body["choices"][0]["message"]["content"]
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _segments_from_whisper(transcript: dict[str, Any]) -> list[str]:
    whisper_segments = transcript.get("segments", [])
    if whisper_segments and isinstance(whisper_segments[0], dict):
        if "text" in whisper_segments[0]:
            return [str(s.get("text", "")).strip() for s in whisper_segments if s.get("text")]
    return []


def _default_segments(config: dict[str, Any]) -> list[dict[str, Any]]:
    hook = str(config.get("hook", "去换个活法吧！当局者困在围城，局外者活成神仙"))
    title = str(config.get("title", "中产退场 低欲生活才是赢家"))
    cta = str(config.get("cta", "建议收藏，换个活法"))
    return [
        {
            "id": "pain",
            "narration": "你还在存量博弈里当耗材、不敢停下来吗？",
            "emphasis": ["存量博弈", "耗材"],
            "visual_keyword": "都市白领 加班 地铁",
            "phase": "pain",
        },
        {
            "id": "reframe",
            "narration": f"{title}。当局者困在围城，局外者活成神仙。",
            "emphasis": ["低欲生活", "赢家"],
            "visual_keyword": "城市夜景 思考 独处",
            "phase": "insight",
        },
        {
            "id": "contrast",
            "narration": "你以为逃离城市就可以了，其实困住你的是欲望，不是坐标。",
            "emphasis": ["欲望", "坐标"],
            "visual_keyword": "对比 城市 小城 生活",
            "phase": "contrast",
        },
        {
            "id": "action",
            "narration": "人生选择：去换个活法吧，把竞争从面子转向日子。",
            "emphasis": ["人生选择", "换个活法"],
            "visual_keyword": "慢生活 自然 日常 小城",
            "phase": "action",
        },
        {
            "id": "insight_02",
            "narration": hook,
            "emphasis": extract_emphasis(hook),
            "visual_keyword": visual_keyword_for_phase("insight"),
            "phase": "insight",
        },
        {
            "id": "cta",
            "narration": cta,
            "emphasis": ["收藏"],
            "visual_keyword": visual_keyword_for_phase("cta"),
            "phase": "cta",
        },
    ]


def _build_segments_from_text(
    sentences: list[str],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    if not sentences:
        hook = str(config.get("hook", "去换个活法吧"))
        return [
            {
                "id": "pain",
                "narration": hook,
                "emphasis": extract_emphasis(hook),
                "visual_keyword": visual_keyword_for_phase("pain"),
                "phase": "pain",
            },
            {
                "id": "insight",
                "narration": str(config.get("title", "认知刷新")),
                "emphasis": extract_emphasis(str(config.get("title", ""))),
                "visual_keyword": visual_keyword_for_phase("insight"),
                "phase": "insight",
            },
            {
                "id": "action",
                "narration": "人生选择：去换个活法吧",
                "emphasis": ["人生选择", "换个活法"],
                "visual_keyword": visual_keyword_for_phase("action"),
                "phase": "action",
            },
            {
                "id": "cta",
                "narration": str(config.get("cta", "建议收藏")),
                "emphasis": ["收藏"],
                "visual_keyword": visual_keyword_for_phase("cta"),
                "phase": "cta",
            },
        ]

    segments: list[dict[str, Any]] = []
    total = len(sentences)
    for index, sentence in enumerate(sentences):
        sentence = sentence.strip()
        if not sentence:
            continue
        phase = infer_phase(sentence, index, total)
        seg_id = f"{phase}_{index + 1:02d}"
        segments.append(
            {
                "id": seg_id,
                "narration": sentence,
                "emphasis": extract_emphasis(sentence),
                "visual_keyword": visual_keyword_for_phase(phase),
                "phase": phase,
            }
        )
    return segments


def generate_script(config: dict[str, Any], work_dir: Path, use_llm: bool = False) -> dict[str, Any]:
    if use_llm:
        topic = str(config.get("title", config.get("topic_id", "认知话题")))
        script = _call_openai_script(topic, config)
    else:
        transcript_path = work_dir / "reference" / "transcript.json"
        transcript = load_json(transcript_path) if transcript_path.exists() else {}

        sentences = _segments_from_whisper(transcript)
        if not sentences:
            full_text = str(transcript.get("zh_full", "")).strip()
            if full_text:
                sentences = split_chinese_sentences(full_text)

        if not sentences:
            segments = _default_segments(config)
        else:
            segments = _build_segments_from_text(sentences, config)
            if len(segments) < 4:
                segments = _default_segments(config)
        script = {
            "series": config.get("series", transcript.get("series", "认知提升")),
            "episode": config.get("episode", transcript.get("episode", "01")),
            "title": config.get("title", transcript.get("title", "")),
            "hook": config.get("hook", transcript.get("hook_zh", "")),
            "segments": segments,
            "cta": config.get("cta", "建议收藏"),
            "tags": config.get("tags", []),
        }

    script_path = work_dir / "script.json"
    save_json(script_path, script)
    return script


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate cognitive video script.")
    parser.add_argument("--config", default="")
    parser.add_argument("--id", default="middle-class-exit")
    parser.add_argument("--llm", action="store_true", help="Use OpenAI to generate script")
    args = parser.parse_args()

    if args.config:
        config_path = Path(args.config).resolve()
        work_dir = resolve_work_dir(config_path)
        config = load_json(config_path)
    else:
        work_dir = ROOT / "work" / args.id
        config_path = work_dir / "config.json"
        if not config_path.exists():
            raise SystemExit(f"Missing config: {config_path}")
        config = load_json(config_path)

    use_llm = args.llm or bool(config.get("use_llm", False))
    script = generate_script(config, work_dir, use_llm=use_llm)
    print(f"Script saved: {work_dir / 'script.json'} ({len(script.get('segments', []))} segments)")


if __name__ == "__main__":
    main()
