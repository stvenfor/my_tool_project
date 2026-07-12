#!/usr/bin/env python3
"""Parity check between reference and replica videos."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent
sys.path.insert(0, str(ROOT))

from lib import get_audio_duration, load_json, probe_video, save_json  # noqa: E402


def _ssim_sample(ref: Path, replica: Path, timestamp: float) -> float | None:
    filt = (
        f"[0:v]trim=start={timestamp}:duration=0.1,setpts=PTS-STARTPTS[ref];"
        f"[1:v]trim=start={timestamp}:duration=0.1,setpts=PTS-STARTPTS[rep];"
        "[ref][rep]scale2ref[ref2][rep2];[ref2][rep2]ssim"
    )
    result = subprocess.run(
        ["ffmpeg", "-i", str(ref), "-i", str(replica), "-lavfi", filt, "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    for line in (result.stderr or "").splitlines():
        if "All:" in line:
            try:
                return float(line.split("All:")[1].strip().split()[0])
            except (IndexError, ValueError):
                pass
    return None


def parity_check(reference_mp4: Path, replica_mp4: Path, subtitles_path: Path | None = None) -> dict:
    ref_meta = probe_video(reference_mp4)
    rep_meta = probe_video(replica_mp4)
    duration_delta = abs(ref_meta["duration_sec"] - rep_meta["duration_sec"])

    sample_times = [3.0, 30.0, 60.0, 90.0, 120.0]
    ssim_scores = {}
    for t in sample_times:
        if t < min(ref_meta["duration_sec"], rep_meta["duration_sec"]) - 1:
            score = _ssim_sample(reference_mp4, replica_mp4, t)
            if score is not None:
                ssim_scores[str(t)] = round(score, 4)

    word_count = 0
    if subtitles_path and subtitles_path.exists():
        subs = load_json(subtitles_path)
        word_count = sum(len(str(s.get("en", "")).split()) for s in subs.get("segments", []))

    checks = {
        "duration_within_5pct": duration_delta <= ref_meta["duration_sec"] * 0.05,
        "aspect_match": rep_meta["width"] == 1080 and rep_meta["height"] == 1920,
        "ssim_avg": round(sum(ssim_scores.values()) / len(ssim_scores), 4) if ssim_scores else None,
        "english_word_count": word_count,
    }
    passed = checks["duration_within_5pct"] and checks["aspect_match"]

    return {
        "reference": str(reference_mp4),
        "replica": str(replica_mp4),
        "reference_meta": ref_meta,
        "replica_meta": rep_meta,
        "duration_delta_sec": round(duration_delta, 3),
        "ssim_samples": ssim_scores,
        "checks": checks,
        "passed": passed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Parity check reference vs replica.")
    parser.add_argument("--reference", required=True)
    parser.add_argument("--replica", required=True)
    parser.add_argument("--subtitles", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    ref = Path(args.reference).resolve()
    rep = Path(args.replica).resolve()
    subs = Path(args.subtitles).resolve() if args.subtitles else None
    report = parity_check(ref, rep, subs)

    out = Path(args.output).resolve() if args.output else rep.parent / "parity_report.json"
    save_json(out, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Parity report: {out} (passed={report['passed']})")


if __name__ == "__main__":
    main()
