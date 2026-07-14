#!/usr/bin/env python3
"""Extract scene cut timeline from reference montage video."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from slice_douyin_video import _build_segments, _detect_scene_times, _probe_duration

ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect reference video scene cuts.")
    parser.add_argument("reference", help="Reference mp4 path")
    parser.add_argument("--output", default="", help="reference_cuts.{stem}.json")
    parser.add_argument("--max-duration", type=float, default=45.0)
    parser.add_argument("--scene-threshold", type=float, default=0.32)
    parser.add_argument("--min-duration", type=float, default=0.3)
    parser.add_argument("--max-duration-seg", type=float, default=1.5)
    return parser.parse_args()


def extract_reference_cuts(
    reference: Path,
    max_duration: float,
    scene_threshold: float,
    min_duration: float,
    max_seg_duration: float,
) -> dict:
    scene_times = _detect_scene_times(reference, scene_threshold)
    segments = _build_segments(scene_times, min_duration, max_seg_duration)
    cuts: list[dict] = []
    cursor = 0.0

    for start, end in segments:
        if start >= max_duration - 0.01:
            break
        duration = min(end, max_duration) - start
        if duration < min_duration:
            continue
        cuts.append(
            {
                "time": round(start, 3),
                "duration": round(duration, 3),
                "end": round(min(end, max_duration), 3),
            }
        )
        cursor = end

    if not cuts or cuts[-1]["end"] < max_duration - 0.05:
        last_start = cuts[-1]["end"] if cuts else 0.0
        if max_duration - last_start >= min_duration:
            cuts.append(
                {
                    "time": round(last_start, 3),
                    "duration": round(max_duration - last_start, 3),
                    "end": round(max_duration, 3),
                }
            )

    return {
        "reference": str(reference.resolve()),
        "source_duration": round(min(_probe_duration(reference), max_duration), 3),
        "scene_points": len(scene_times),
        "cuts": cuts,
        "cut_count": len(cuts),
    }


def main() -> None:
    args = parse_args()
    reference = Path(args.reference).resolve()
    if not reference.exists():
        raise SystemExit(f"Reference not found: {reference}")

    result = extract_reference_cuts(
        reference,
        args.max_duration,
        args.scene_threshold,
        args.min_duration,
        args.max_duration_seg,
    )

    stem = reference.stem
    output = Path(args.output).resolve() if args.output else ROOT / "output" / f"reference_cuts.{stem}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved reference cuts ({result['cut_count']}): {output}")


if __name__ == "__main__":
    main()
