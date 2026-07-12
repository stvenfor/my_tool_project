#!/usr/bin/env python3
"""Align script segments to Whisper transcript timestamps."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import load_json, resolve_work_dir, save_json, split_chinese_sentences  # noqa: E402


def _normalize(text: str) -> str:
    return "".join(ch for ch in text if ch not in "，,。！？；!?; \n\t")


def _match_segment_to_whisper(
    narration: str,
    whisper_segments: list[dict[str, Any]],
    cursor_index: int,
) -> tuple[float, float, int]:
    target = _normalize(narration)
    if not target or not whisper_segments:
        return 0.0, 0.0, cursor_index

    best_score = 0.0
    best_start = float(whisper_segments[cursor_index].get("start_sec", 0))
    best_end = float(whisper_segments[cursor_index].get("end_sec", best_start + 2))
    best_index = cursor_index

    for index in range(cursor_index, min(cursor_index + 6, len(whisper_segments))):
        window = whisper_segments[index : index + 3]
        merged = _normalize("".join(str(s.get("text", "")) for s in window))
        if not merged:
            continue
        overlap = sum(1 for ch in target if ch in merged)
        score = overlap / max(len(target), 1)
        if score > best_score:
            best_score = score
            best_start = float(window[0].get("start_sec", 0))
            best_end = float(window[-1].get("end_sec", best_start + 2))
            best_index = index + len(window)

    if best_score < 0.2:
        seg = whisper_segments[min(cursor_index, len(whisper_segments) - 1)]
        start = float(seg.get("start_sec", 0))
        end = float(seg.get("end_sec", start + 2))
        return start, end, cursor_index + 1

    return best_start, best_end, best_index


def align_subtitles(work_dir: Path, hook_duration: float = 2.8) -> dict[str, Any]:
    script = load_json(work_dir / "script.json")
    transcript_path = work_dir / "reference" / "transcript.json"
    if not transcript_path.exists():
        raise SystemExit(f"Missing transcript for alignment: {transcript_path}")

    transcript = load_json(transcript_path)
    whisper_segments = transcript.get("segments", [])
    if not whisper_segments:
        raise SystemExit("No whisper segments found in transcript.json")

    aligned: list[dict[str, Any]] = []
    cursor = 0
    for seg in script.get("segments", []):
        narration = str(seg.get("narration", "")).strip()
        if not narration:
            continue
        start, end, cursor = _match_segment_to_whisper(narration, whisper_segments, cursor)
        duration = max(0.8, end - start)
        aligned.append(
            {
                "start_sec": round(max(hook_duration, start), 3),
                "duration_sec": round(duration, 3),
                "zh": narration,
                "emphasis": seg.get("emphasis", []),
                "visual_keyword": seg.get("visual_keyword", ""),
                "phase": seg.get("phase", "insight"),
                "id": seg.get("id", ""),
            }
        )

    manifest_path = work_dir / "reference" / "reference_manifest.json"
    duration_sec = float(load_json(manifest_path).get("duration_sec", 60)) if manifest_path.exists() else 60.0

    subtitles = {
        "hook_zh": script.get("hook", ""),
        "hook_duration_sec": hook_duration,
        "duration_sec": duration_sec,
        "segments": aligned,
        "alignment": "whisper",
    }
    save_json(work_dir / "subtitles.json", subtitles)
    return subtitles


def main() -> None:
    parser = argparse.ArgumentParser(description="Align subtitles with Whisper transcript.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--hook-duration", type=float, default=2.8)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    work_dir = resolve_work_dir(config_path)
    subtitles = align_subtitles(work_dir, hook_duration=args.hook_duration)
    print(f"Aligned subtitles: {work_dir / 'subtitles.json'} ({len(subtitles['segments'])} segments)")


if __name__ == "__main__":
    main()
