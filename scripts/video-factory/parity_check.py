#!/usr/bin/env python3
"""QA parity check for video-factory outputs."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import get_audio_duration, load_json, load_project_config, probe_video, project_work_dir, save_json  # noqa: E402


def _subtitle_coverage(subtitles_path: Path, duration_sec: float) -> float:
    if not subtitles_path.exists():
        return 0.0
    subs = load_json(subtitles_path)
    covered = sum(float(s.get("duration_sec", 0)) for s in subs.get("segments", []))
    return round(covered / duration_sec, 3) if duration_sec > 0 else 0.0


def qa_check(work_dir: Path, reference_mp4: Path | None = None) -> dict:
    final_mp4 = work_dir / "output" / "final.mp4"
    if not final_mp4.exists():
        raise SystemExit(f"Missing output: {final_mp4}")

    meta = probe_video(final_mp4)
    config = load_project_config(work_dir) if (work_dir / "project.config.json").exists() else {}
    expected_w = int(config.get("width", 1080))
    expected_h = int(config.get("height", 1920))

    subtitles_path = work_dir / "subtitles.json"
    narration_wav = work_dir / "narration.wav"
    audio_duration = get_audio_duration(narration_wav) if narration_wav.exists() else 0.0
    coverage = _subtitle_coverage(subtitles_path, meta["duration_sec"])

    checks = {
        "has_output": final_mp4.exists(),
        "aspect_match": meta["width"] == expected_w and meta["height"] == expected_h,
        "duration_positive": meta["duration_sec"] > 5,
        "subtitle_coverage": coverage >= 0.5,
        "has_douyin_meta": (work_dir / "douyin-video.json").exists(),
    }

    if reference_mp4 and reference_mp4.exists():
        ref_meta = probe_video(reference_mp4)
        delta = abs(ref_meta["duration_sec"] - meta["duration_sec"])
        checks["duration_within_5pct"] = delta <= ref_meta["duration_sec"] * 0.05

    passed = all(v for k, v in checks.items() if k != "duration_within_5pct" or reference_mp4)
    return {
        "project": work_dir.name,
        "output": str(final_mp4),
        "meta": meta,
        "audio_duration_sec": round(audio_duration, 3),
        "subtitle_coverage": coverage,
        "checks": checks,
        "passed": passed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="QA check video-factory output.")
    parser.add_argument("--id", required=True)
    parser.add_argument("--reference", default="")
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()

    work_dir = project_work_dir(args.id)
    reference = Path(args.reference).resolve() if args.reference else None
    report = qa_check(work_dir, reference)
    if args.save:
        save_json(work_dir / "qa-report.json", report)
    print(f"QA {'PASSED' if report['passed'] else 'FAILED'}: {work_dir.name}")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
