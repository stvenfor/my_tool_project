#!/usr/bin/env python3
"""Map synced subtitle segments to shot plan with reference time alignment."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import assign_reference_times, load_json, probe_video, resolve_work_dir, save_json  # noqa: E402


def _shot_duration(index: int, segments: list[dict[str, Any]], start_sec: float, total_sec: float) -> float:
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

    total_sec = float(subtitles.get("duration_sec", config.get("duration_sec", 141.767)))
    hook_duration = float(subtitles.get("hook_duration_sec", config.get("hook_duration_sec", 3.0)))
    hook_keyword = str(subtitles.get("hook_visual_keyword") or f"三国 Q版 {config.get('episode_title', '')}").strip()

    shots: list[dict[str, Any]] = []
    hook_start = 0.0
    first_seg_start = float(segments[0]["start_sec"]) if segments else hook_duration
    hook_end = first_seg_start
    shots.append(
        {
            "id": "S00",
            "phase": str(subtitles.get("hook_phase", "hook")),
            "start_sec": hook_start,
            "duration_sec": round(hook_end - hook_start, 3),
            "reference_time": 0.0,
            "visual_keyword": hook_keyword,
            "zh": subtitles.get("hook_zh", ""),
            "en": subtitles.get("hook_en", ""),
            "segment_index": -1,
            "clip": "clips/S00.mp4",
            "source": "narration_sync",
        }
    )

    for index, seg in enumerate(segments):
        start_sec = float(seg["start_sec"])
        if config.get("narration_timing") == "fixed" and "duration_sec" in seg:
            duration_sec = round(float(seg["duration_sec"]), 3)
        else:
            duration_sec = round(_shot_duration(index, segments, start_sec, total_sec), 3)
        keyword = str(seg.get("visual_keyword") or "").strip() or f"三国 3D Q版 {config.get('episode_title', '')}"

        shots.append(
            {
                "id": f"S{index + 1:02d}",
                "phase": seg.get("phase", "story"),
                "start_sec": round(start_sec, 3),
                "duration_sec": duration_sec,
                "reference_time": round(start_sec, 3),
                "visual_keyword": keyword,
                "zh": seg.get("zh", ""),
                "en": seg.get("en", ""),
                "segment_index": index,
                "clip": f"clips/S{index + 1:02d}.mp4",
                "source": "narration_sync",
            }
        )

    source_mp4 = work_dir / "reference" / "source.mp4"
    if not source_mp4.exists():
        ref_dir = Path(config.get("reference_work_dir", ""))
        if ref_dir.is_absolute() or str(ref_dir).startswith("_"):
            alt = ROOT.parent.parent / ref_dir / "reference" / "source.mp4"
        else:
            alt = work_dir / ref_dir / "reference" / "source.mp4"
        if alt.exists():
            source_mp4 = alt

    source_duration = float(config.get("duration_sec", 141.767))
    if source_mp4.exists():
        source_duration = probe_video(source_mp4)["duration_sec"]

    time_mode = str(config.get("reference_time_mode", "segment_start"))
    if time_mode == "segment_start":
        for shot in shots:
            if shot.get("segment_index", -1) >= 0:
                shot["reference_time"] = float(shot["start_sec"])
            else:
                shot["reference_time"] = 0.0
        return shots

    return assign_reference_times(shots, source_duration)


def main() -> None:
    parser = argparse.ArgumentParser(description="Map narration segments to shots.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)

    mapped = map_narration_shots(config, work_dir)
    save_json(work_dir / "shot_plan.json", {"shots": mapped, "count": len(mapped), "mode": "narration_sync"})
    print(f"Shot plan: {work_dir / 'shot_plan.json'} ({len(mapped)} shots)")


if __name__ == "__main__":
    main()
