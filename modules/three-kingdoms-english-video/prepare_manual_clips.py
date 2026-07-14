#!/usr/bin/env python3
"""Prepare manual_clips by slicing reference video at subtitle-aligned times."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import load_json, resolve_work_dir  # noqa: E402
from fetch_clips import _resolve_source_mp4, _slice_reference_clip  # noqa: E402
from map_narration_shots import map_narration_shots  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Slice reference into manual_clips/ for each shot.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)
    source_mp4 = _resolve_source_mp4(config, work_dir)
    if not source_mp4:
        raise SystemExit("Reference source.mp4 not found")

    subtitles_path = work_dir / "subtitles.json"
    if not subtitles_path.exists():
        raise SystemExit(f"Run build_subtitles_from_reference.py first: {subtitles_path}")

    shots = map_narration_shots(config, work_dir)
    manual_dir = work_dir / "manual_clips"
    manual_dir.mkdir(parents=True, exist_ok=True)
    width = int(config.get("width", 1080))
    height = int(config.get("height", 1920))

    for shot in shots:
        out = manual_dir / f"{shot['id']}.mp4"
        if out.exists() and not args.force:
            print(f"Skip existing {out.name}")
            continue
        ref_time = float(shot.get("reference_time", shot.get("start_sec", 0)))
        duration = float(shot["duration_sec"])
        _slice_reference_clip(source_mp4, out, ref_time, duration, width, height)
        print(f"Prepared {out.name} @ {ref_time:.2f}s ({duration:.2f}s)")

    print(f"Manual clips ready: {manual_dir} ({len(shots)} shots)")


if __name__ == "__main__":
    main()
