#!/usr/bin/env python3
"""Generate English narration and bilingual subtitles for Three Kingdoms episodes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import build_config_mapping, fill_template, load_json, resolve_work_dir, save_json  # noqa: E402


def build_subtitles(config: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    template_path = ROOT / "copy" / "subtitles.template.json"
    template = load_json(template_path)
    mapping = build_config_mapping(config)

    hook = template.get("hook", {})
    hook_zh = fill_template(str(hook.get("zh", mapping["hook_zh"])), mapping)
    hook_en = fill_template(str(hook.get("en", "")), mapping)

    segments: list[dict[str, Any]] = []
    for seg in template.get("segments", []):
        segments.append(
            {
                "start_sec": float(seg["start_sec"]),
                "duration_sec": float(seg["duration_sec"]),
                "en": fill_template(str(seg.get("en", "")), mapping),
                "zh": fill_template(str(seg.get("zh", "")), mapping),
                "visual_keyword": fill_template(str(seg.get("visual_keyword", "")), mapping),
                "phase": seg.get("phase", "story"),
            }
        )

    ref_transcript = work_dir / "reference" / "transcript.json"
    if ref_transcript.exists() and config.get("narration_mode") == "transcript_clone":
        ref = load_json(ref_transcript)
        if ref.get("segments"):
            segments = ref["segments"]

    duration_sec = float(
        config.get("duration_sec", segments[-1]["start_sec"] + segments[-1]["duration_sec"] if segments else 141.767)
    )
    return {
        "hook_zh": hook_zh,
        "hook_en": hook_en,
        "hook_duration_sec": float(hook.get("duration_sec", 3.0)),
        "hook_visual_keyword": fill_template(str(hook.get("visual_keyword", "")), mapping),
        "hook_phase": hook.get("phase", "hook"),
        "segments": segments,
        "duration_sec": duration_sec,
    }


def build_narration_text(config: dict[str, Any]) -> str:
    template_path = ROOT / "copy" / "narration.en.template.txt"
    template = template_path.read_text(encoding="utf-8").strip()
    mapping = build_config_mapping(config)
    return fill_template(template, mapping)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Three Kingdoms English script assets.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)
    work_dir.mkdir(parents=True, exist_ok=True)

    narration = build_narration_text(config)
    subtitles = build_subtitles(config, work_dir)

    (work_dir / "narration.en.txt").write_text(narration + "\n", encoding="utf-8")
    save_json(work_dir / "subtitles.json", subtitles)

    print(f"Narration: {work_dir / 'narration.en.txt'}")
    print(f"Subtitles: {work_dir / 'subtitles.json'} ({len(subtitles['segments'])} segments)")


if __name__ == "__main__":
    main()
