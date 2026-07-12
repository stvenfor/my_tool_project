#!/usr/bin/env python3
"""Merge reference scene cuts with music beats — beat priority."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent

MIN_DURATION = 0.3
MAX_DURATION = 1.5
REF_TOLERANCE = 0.15


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build cut_grid from cut_beats (beat priority).")
    parser.add_argument("--beats", required=True)
    parser.add_argument("--reference-cuts", required=True)
    parser.add_argument("--output", default="")
    return parser.parse_args()


def _nearest_beat(beats: list[float], time_value: float) -> tuple[float, float]:
    if not beats:
        return time_value, 0.0
    nearest = min(beats, key=lambda beat: abs(beat - time_value))
    return nearest, round(nearest - time_value, 3)


def merge_cut_grid(beats_data: dict, reference_data: dict) -> dict:
    cut_beats: list[float] = beats_data.get("cut_beats") or beats_data["beats"]
    audio_duration = float(beats_data["duration"])
    sections: list[dict] = beats_data.get("sections", [])
    ref_cuts: list[dict] = reference_data.get("cuts", [])

    slots: list[dict] = []
    ref_snaps: list[dict] = []

    for index, start_time in enumerate(cut_beats):
        if start_time >= audio_duration - 0.01:
            break
        next_time = cut_beats[index + 1] if index + 1 < len(cut_beats) else audio_duration
        duration = round(min(MAX_DURATION, max(MIN_DURATION, next_time - start_time)), 3)

        section_name = "outro"
        for section in sections:
            if section["start"] <= start_time < section["end"]:
                section_name = str(section["name"])
                break

        nearest_ref = None
        nearest_delta = None
        for ref_cut in ref_cuts:
            ref_time = float(ref_cut["time"])
            delta = abs(ref_time - start_time)
            if nearest_delta is None or delta < nearest_delta:
                nearest_delta = delta
                nearest_ref = ref_time

        beat_snap_ms = round((nearest_delta or 0.0) * 1000)
        ref_snaps.append(
            {
                "beat": round(start_time, 3),
                "referenceCut": nearest_ref,
                "deltaSec": round(nearest_delta or 0.0, 3),
                "beatSnapMs": beat_snap_ms,
            }
        )

        slots.append(
            {
                "index": index,
                "startTime": round(start_time, 3),
                "duration": duration,
                "endTime": round(min(start_time + duration, audio_duration), 3),
                "section": section_name,
                "referenceCut": nearest_ref,
                "beatSnapMs": beat_snap_ms,
            }
        )

    durations = [slot["duration"] for slot in slots]
    deltas = [snap["deltaSec"] for snap in ref_snaps if snap["referenceCut"] is not None]
    median_beat_interval = statistics.median(durations) if durations else 0.48

    return {
        "audio_duration": round(audio_duration, 3),
        "beat_count": len(slots),
        "reference_cut_count": len(ref_cuts),
        "median_beat_interval": round(median_beat_interval, 3),
        "median_ref_delta": round(statistics.median(deltas), 3) if deltas else 0.0,
        "max_ref_delta": round(max(deltas), 3) if deltas else 0.0,
        "slots": slots,
        "reference_alignment": ref_snaps,
    }


def main() -> None:
    args = parse_args()
    beats_path = Path(args.beats).resolve()
    ref_path = Path(args.reference_cuts).resolve()
    beats_data = json.loads(beats_path.read_text(encoding="utf-8"))
    reference_data = json.loads(ref_path.read_text(encoding="utf-8"))

    stem = beats_path.stem.replace("beats.", "", 1) if beats_path.stem.startswith("beats.") else beats_path.stem
    output = Path(args.output).resolve() if args.output else ROOT / "output" / f"cut_grid.{stem}.json"

    result = merge_cut_grid(beats_data, reference_data)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Saved cut_grid ({result['beat_count']} slots, median interval {result['median_beat_interval']}s, "
        f"ref delta median {result['median_ref_delta']}s): {output}"
    )


if __name__ == "__main__":
    main()
