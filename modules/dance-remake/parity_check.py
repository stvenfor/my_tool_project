#!/usr/bin/env python3
"""Parity check for dance remake vs reference."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def probe_video(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    fmt = data["format"]
    duration = float(fmt["duration"])
    fps_parts = video.get("r_frame_rate", "30/1").split("/")
    fps = float(fps_parts[0]) / float(fps_parts[1]) if len(fps_parts) == 2 else 30.0
    return {
        "path": str(path),
        "duration_sec": round(duration, 3),
        "width": int(video["width"]),
        "height": int(video["height"]),
        "fps": round(fps, 2),
        "codec": video.get("codec_name", ""),
    }


def ssim_at(ref: Path, replica: Path, timestamp: float) -> float | None:
    filt = (
        f"[0:v]trim=start={timestamp}:duration=0.08,setpts=PTS-STARTPTS[ref];"
        f"[1:v]trim=start={timestamp}:duration=0.08,setpts=PTS-STARTPTS[rep];"
        "[ref][rep]scale2ref=flags=bilinear[ref2][rep2];[ref2][rep2]ssim"
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


def load_beat_map(root: Path) -> dict:
    path = root / "modules/dance-remake/work/reference/beat_map.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def parity_check(reference: Path, replica: Path | None, beat_map: dict) -> dict:
    ref_meta = probe_video(reference)
    segments = beat_map.get("segments", [])

    report: dict = {
        "reference": str(reference),
        "replica": str(replica) if replica else None,
        "reference_meta": ref_meta,
        "segment_timing_reference": segments,
        "checks": {},
        "passed": False,
        "status": "pending_replica",
    }

    if replica is None or not replica.exists():
        report["checks"] = {
            "replica_exists": False,
            "reference_duration_ok": 9.5 <= ref_meta["duration_sec"] <= 10.5,
            "reference_aspect_ok": ref_meta["height"] > ref_meta["width"],
            "reference_fps_ok": abs(ref_meta["fps"] - 30) <= 2,
        }
        report["passed"] = all(report["checks"].values())
        report["message"] = "Reference baseline OK. Add output/final.mp4 and re-run for full parity."
        return report

    rep_meta = probe_video(replica)
    report["replica_meta"] = rep_meta
    report["status"] = "compared"

    duration_delta = abs(ref_meta["duration_sec"] - rep_meta["duration_sec"])
    aspect_match = (
        abs(rep_meta["width"] / rep_meta["height"] - ref_meta["width"] / ref_meta["height"]) < 0.02
    )

    sample_times = [0.5, 2.5, 4.5, 6.0, 8.0, 9.5]
    ssim_samples: dict[str, float] = {}
    for t in sample_times:
        if t < min(ref_meta["duration_sec"], rep_meta["duration_sec"]) - 0.2:
            score = ssim_at(reference, replica, t)
            if score is not None:
                ssim_samples[str(t)] = round(score, 4)

    ssim_avg = round(sum(ssim_samples.values()) / len(ssim_samples), 4) if ssim_samples else None

    report["duration_delta_sec"] = round(duration_delta, 3)
    report["ssim_samples"] = ssim_samples
    report["checks"] = {
        "replica_exists": True,
        "duration_within_200ms": duration_delta <= 0.2,
        "aspect_match": aspect_match,
        "fps_match": abs(rep_meta["fps"] - ref_meta["fps"]) <= 2,
        "ssim_avg_above_0.5": ssim_avg is not None and ssim_avg >= 0.5,
        "vertical_9_16": rep_meta["height"] > rep_meta["width"],
    }
    report["ssim_avg"] = ssim_avg
    report["passed"] = all(report["checks"].values())
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Dance remake parity check.")
    parser.add_argument("--reference", default="modules/dance-remake/work/reference/source.mp4")
    parser.add_argument("--replica", default="modules/dance-remake/work/output/final.mp4")
    parser.add_argument("--output", default="modules/dance-remake/work/output/parity_report.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    reference = (root / args.reference).resolve()
    replica = (root / args.replica).resolve()
    output = (root / args.output).resolve()

    if not reference.exists():
        raise SystemExit(f"Reference not found: {reference}")

    beat_map = load_beat_map(root)
    replica_path = replica if replica.exists() else None
    report = parity_check(reference, replica_path, beat_map)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nParity report: {output} (passed={report['passed']}, status={report['status']})")


if __name__ == "__main__":
    main()
