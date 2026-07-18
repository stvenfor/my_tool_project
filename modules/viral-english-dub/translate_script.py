#!/usr/bin/env python3
"""Faithful zh→en translation for transcript segments."""

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

from lib import load_json, resolve_work_dir, save_json  # noqa: E402

LLM_SYSTEM = """You translate Chinese dialogue from viral video clips into English.

Rules:
- Faithful to original meaning; do NOT rewrite as narration or commentary.
- Preserve emotion, rhetorical questions, and character tone.
- Keep English concise so it fits similar speaking duration (prefer short clauses).
- Keep proper names consistent (pinyin for Chinese names, e.g. Xiao Er, Yang Guo).
- When accent_preserve is true, use slightly non-native but natural English (Chinese-accent friendly), not broadcast American English.
- Output JSON only: {"segments":[{"en":"..."}]}
"""


def _fallback_translate(text_zh: str) -> str:
    """Offline fallback — translate known phrases, including merged lines."""
    phrase_map = {
        "已经找到为我捐陷四只的人了": "They found someone to donate all four limbs for me.",
        "我已经找到为我捐献四肢的人了": "They found someone to donate all four limbs for me.",
        "我终于可以自由了": "I can finally be free.",
        "恭喜你啊": "Congratulations.",
        "马上就要手术了": "The surgery is about to begin.",
        "马上就要守树了": "The surgery is about to begin.",
        "到底是谁啊": "Who is it?",
        "别说了主人": "Stop talking, master.",
        "手术快开始了": "The surgery is starting soon.",
        "守树快开始了": "The surgery is starting soon.",
        "臭狗": "You stupid dog,",
        "你居然为了我": "you actually did this for me.",
        "你怎么能这么傻": "How can you be so foolish?",
        "我下楼扔垃圾去了": "I went downstairs to take out the trash.",
        "好的": "Okay.",
        "回来": "Come back.",
        "咋的了": "What's wrong?",
        "走吧": "Let's go.",
        "那我走了": "Then I'm leaving.",
        "咋的了，买啥你说呀": "What's wrong? Tell me what you want to buy.",
        "咋的了要买啥你说呀": "What's wrong? Tell me what you want to buy.",
        "回来回来": "Come back, come back!",
        "不是让你在这等着吗，你遛狗呢": "I told you to wait here. Why are you walking the dog?",
        "你看地上有什么": "Look what's on the ground.",
        "什么也没有啊": "There's nothing there.",
    }
    cleaned = text_zh.strip()
    if cleaned in phrase_map:
        return phrase_map[cleaned]
    if not re.search(r"[\u4e00-\u9fff]", cleaned):
        return cleaned

    parts = re.split(r"\s+", cleaned)
    translated: list[str] = []
    for part in parts:
        if part in phrase_map:
            translated.append(phrase_map[part])
        elif not re.search(r"[\u4e00-\u9fff]", part):
            translated.append(part)
    if translated:
        return " ".join(translated)
    return cleaned


def _call_openai_translate(segments: list[dict[str, Any]], accent_preserve: bool) -> list[str]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    lines = []
    for index, seg in enumerate(segments):
        lines.append(
            {
                "index": index,
                "speaker_id": seg.get("speaker_id", "spk0"),
                "text_zh": seg.get("text_zh", ""),
                "start_sec": seg.get("start_sec"),
                "end_sec": seg.get("end_sec"),
            }
        )

    user_prompt = json.dumps(
        {
            "accent_preserve": accent_preserve,
            "segments": lines,
        },
        ensure_ascii=False,
    )

    payload = {
        "model": os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        "messages": [
            {"role": "system", "content": LLM_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
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
    parsed = json.loads(text)
    translated = parsed.get("segments", parsed.get("items", []))
    if isinstance(translated, list) and translated and isinstance(translated[0], dict):
        return [str(item.get("en", "")).strip() for item in translated]
    if isinstance(translated, list):
        return [str(item).strip() for item in translated]
    raise RuntimeError("Unexpected LLM translation format")


def translate_script(config: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    transcript_path = work_dir / "reference" / "transcript.json"
    if not transcript_path.exists():
        raise SystemExit(f"Missing transcript: {transcript_path}")

    transcript = load_json(transcript_path)
    segments = transcript.get("segments", [])
    if not segments:
        raise SystemExit("No segments in transcript")

    script_path = work_dir / "script.json"
    if script_path.exists() and config.get("skip_translate_if_script_exists"):
        return load_json(script_path)

    existing_script = load_json(script_path) if script_path.exists() else {}
    existing_segs = existing_script.get("segments", [])

    # Prefer enriched segments (speaker/prompt) from prior diarize if present.
    if existing_segs and len(existing_segs) == len(segments):
        source_segments = existing_segs
    else:
        source_segments = segments

    accent_preserve = bool(config.get("accent_preserve", True))
    use_llm = bool(config.get("use_llm_translate", True))
    english_lines: list[str] = []

    if use_llm and os.environ.get("OPENAI_API_KEY"):
        try:
            english_lines = _call_openai_translate(source_segments, accent_preserve)
            print(f"LLM translated {len(english_lines)} segments.")
        except Exception as exc:
            print(f"LLM translate failed ({exc}); using fallback.")
            english_lines = []

    if len(english_lines) != len(source_segments):
        # Prefer previously accepted English over unusable Chinese placeholders.
        preserved = [
            str(seg.get("en", "")).strip()
            for seg in source_segments
            if str(seg.get("en", "")).strip() and not re.search(r"[\u4e00-\u9fff]", str(seg.get("en", "")))
        ]
        if len(preserved) == len(source_segments):
            print("Keeping existing English lines after LLM failure.")
            english_lines = preserved
        else:
            english_lines = [_fallback_translate(str(seg.get("text_zh", ""))) for seg in source_segments]

    script_segments: list[dict[str, Any]] = []
    for seg, en in zip(source_segments, english_lines):
        start = float(seg["start_sec"])
        end = float(seg["end_sec"])
        prompt_text = str(seg.get("prompt_text") or seg.get("text_zh", "")).strip()
        script_segments.append(
            {
                "start_sec": round(start, 3),
                "end_sec": round(end, 3),
                "duration_sec": round(max(0.1, end - start), 3),
                "text_zh": str(seg.get("text_zh", "")).strip(),
                "en": en.strip(),
                "speaker_id": str(seg.get("speaker_id", "spk0")),
                "prompt_wav": seg.get("prompt_wav", ""),
                "prompt_text": prompt_text,
            }
        )

    payload = {
        "clip_id": config.get("clip_id", work_dir.name),
        "title": config.get("title", "Classic scene in English"),
        "accent_preserve": accent_preserve,
        "segments": script_segments,
        "duration_sec": float(config.get("duration_sec", script_segments[-1]["end_sec"] if script_segments else 0)),
    }
    save_json(script_path, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Translate transcript segments to English.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)

    payload = translate_script(config, work_dir)
    print(f"Script saved: {work_dir / 'script.json'} ({len(payload['segments'])} segments)")


if __name__ == "__main__":
    main()
