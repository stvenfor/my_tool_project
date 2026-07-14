#!/usr/bin/env python3
"""Map synced subtitle segments to landmark-matched shot plan."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import load_json, resolve_work_dir, save_json  # noqa: E402


def _shot_duration(
    index: int,
    segments: list[dict[str, Any]],
    start_sec: float,
    total_sec: float,
) -> float:
    if index < len(segments) - 1:
        return float(segments[index + 1]["start_sec"]) - start_sec
    return max(0.8, total_sec - start_sec)


def map_narration_shots(config: dict[str, Any], work_dir: Path) -> list[dict[str, Any]]:
    subtitles_path = work_dir / "subtitles.json"
    if not subtitles_path.exists():
        raise SystemExit(f"Missing subtitles: {subtitles_path}")

    subtitles = load_json(subtitles_path)
    segments = subtitles.get("segments", [])
    if not segments:
        raise SystemExit("No subtitle segments found")

    total_sec = float(subtitles.get("duration_sec", config.get("duration_sec", 51.233)))
    hook_duration = float(subtitles.get("hook_duration_sec", config.get("hook_duration_sec", 2.5)))
    hook_keyword = str(
        subtitles.get("hook_visual_keyword")
        or config.get("hook_visual_keyword")
        or f"{config.get('city_name', '')} 城市 航拍"
    ).strip()
    hook_landmark = str(subtitles.get("hook_landmark") or config.get("city_name", "")).strip()

    shots: list[dict[str, Any]] = []
    hook_start = 0.0
    hook_end = float(segments[0]["start_sec"]) if segments else hook_duration
    shots.append(
        {
            "id": "S00",
            "phase": str(subtitles.get("hook_phase", "day")),
            "start_sec": hook_start,
            "duration_sec": round(hook_end - hook_start, 3),
            "douyin_keyword": hook_keyword,
            "visual_keyword": hook_keyword,
            "landmark": hook_landmark,
            "zh": subtitles.get("hook_zh", ""),
            "segment_index": -1,
            "clip": "clips/S00.mp4",
            "source": "narration_sync",
        }
    )

    for index, seg in enumerate(segments):
        start_sec = float(seg["start_sec"])
        duration_sec = round(_shot_duration(index, segments, start_sec, total_sec), 3)
        keyword = str(seg.get("visual_keyword") or seg.get("douyin_keyword") or "").strip()
        if not keyword:
            phase = seg.get("phase", "day")
            keyword = f"{config.get('city_name', '')} {phase}"

        shots.append(
            {
                "id": f"S{index + 1:02d}",
                "phase": seg.get("phase", "day"),
                "start_sec": round(start_sec, 3),
                "duration_sec": duration_sec,
                "douyin_keyword": keyword,
                "visual_keyword": keyword,
                "landmark": seg.get("landmark", ""),
                "zh": seg.get("zh", ""),
                "en": seg.get("en", ""),
                "segment_index": index,
                "clip": f"clips/S{index + 1:02d}.mp4",
                "source": "narration_sync",
            }
        )

    return shots


def main() -> None:
    parser = argparse.ArgumentParser(description="Map narration segments to landmark shots.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)

    mapped = map_narration_shots(config, work_dir)
    save_json(work_dir / "shot_plan.json", {"shots": mapped, "count": len(mapped), "mode": "narration_sync"})
    print(f"Narration shot plan: {work_dir / 'shot_plan.json'} ({len(mapped)} shots)")
    for shot in mapped:
        print(f"  {shot['id']} {shot['duration_sec']:5.2f}s  [{shot.get('landmark', '')}] {shot.get('zh', '')}")


if __name__ == "__main__":
    main()
