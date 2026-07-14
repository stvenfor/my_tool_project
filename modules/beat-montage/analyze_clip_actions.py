#!/usr/bin/env python3
"""Detect action impact points in video clips via frame motion analysis."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect action peaks in video clips.")
    parser.add_argument("video", nargs="?", help="Single video path")
    parser.add_argument("--manifest", default="", help="Update clip_manifest.json in place")
    parser.add_argument("--fps", type=float, default=12.0, help="Analysis sample rate")
    parser.add_argument("--width", type=int, default=180, help="Downscale width for analysis")
    parser.add_argument("--min-gap", type=float, default=0.28, help="Minimum seconds between peaks")
    parser.add_argument("--top-k", type=int, default=24, help="Max peaks per clip")
    return parser.parse_args()


def _probe_size(video_path: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    parts = [part for part in result.stdout.strip().split(",") if part]
    width, height = parts[0], parts[1]
    return int(width), int(height)


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def _read_gray_frames(video_path: Path, fps: float, width: int) -> tuple[np.ndarray, float]:
    _, src_height = _probe_size(video_path)
    height = max(1, int(src_height * width / max(_probe_size(video_path)[0], 1)))

    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(video_path),
        "-vf",
        f"fps={fps},scale={width}:{height}",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=True)
    frame_bytes = width * height
    if frame_bytes <= 0 or len(proc.stdout) < frame_bytes:
        return np.zeros((0, height, width), dtype=np.uint8), fps

    frame_count = len(proc.stdout) // frame_bytes
    frames = np.frombuffer(proc.stdout[: frame_count * frame_bytes], dtype=np.uint8)
    frames = frames.reshape(frame_count, height, width)
    return frames, fps


def detect_action_peaks(
    video_path: Path,
    fps: float = 12.0,
    width: int = 180,
    min_gap: float = 0.28,
    top_k: int = 24,
) -> list[dict]:
    frames, sample_fps = _read_gray_frames(video_path, fps, width)
    if len(frames) < 3:
        return [{"time": 0.0, "strength": 0.5}]

    diffs = np.abs(frames[1:].astype(np.float32) - frames[:-1].astype(np.float32))
    motion = diffs.mean(axis=(1, 2))
    if motion.max() <= 0:
        return [{"time": 0.0, "strength": 0.5}]

    motion = motion / motion.max()
    smooth = np.convolve(motion, np.ones(3) / 3.0, mode="same")
    threshold = float(np.percentile(smooth, 72))

    candidates: list[dict] = []
    for index in range(1, len(smooth) - 1):
        if smooth[index] >= threshold and smooth[index] >= smooth[index - 1] and smooth[index] > smooth[index + 1]:
            candidates.append(
                {
                    "time": round((index + 1) / sample_fps, 3),
                    "strength": round(float(smooth[index]), 4),
                }
            )

    if not candidates:
        peak_index = int(np.argmax(smooth))
        return [{"time": round((peak_index + 1) / sample_fps, 3), "strength": round(float(smooth[peak_index]), 4)}]

    candidates.sort(key=lambda item: item["strength"], reverse=True)
    selected: list[dict] = []
    for candidate in candidates:
        if any(abs(candidate["time"] - item["time"]) < min_gap for item in selected):
            continue
        selected.append(candidate)
        if len(selected) >= top_k:
            break

    selected.sort(key=lambda item: item["time"])
    return selected


def _infer_energy(peaks: list[dict]) -> int:
    if not peaks:
        return 5
    strength = max(item["strength"] for item in peaks)
    return int(min(10, max(1, round(strength * 10))))


def analyze_manifest(manifest_path: Path, fps: float, width: int, min_gap: float, top_k: int) -> list[dict]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    updated: list[dict] = []

    for entry in manifest:
        clip_path = ROOT / "clips" / entry["path"]
        if not clip_path.exists():
            print(f"Skip missing clip: {clip_path}")
            updated.append(entry)
            continue

        peaks = detect_action_peaks(clip_path, fps=fps, width=width, min_gap=min_gap, top_k=top_k)
        entry = {
            **entry,
            "action_peaks": peaks,
            "energy": entry.get("energy") or _infer_energy(peaks),
            "trim_in": entry.get("trim_in", peaks[0]["time"] if peaks else 0.0),
            "source_duration": round(_probe_duration(clip_path), 2),
        }
        updated.append(entry)
        print(f"{entry['id']}: {len(peaks)} action peaks, top={peaks[0]['time']:.2f}s")

    manifest_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return updated


def main() -> None:
    args = parse_args()
    if args.manifest:
        analyze_manifest(Path(args.manifest).resolve(), args.fps, args.width, args.min_gap, args.top_k)
        return

    if not args.video:
        raise SystemExit("Provide a video path or --manifest")

    peaks = detect_action_peaks(
        Path(args.video).resolve(),
        fps=args.fps,
        width=args.width,
        min_gap=args.min_gap,
        top_k=args.top_k,
    )
    print(json.dumps(peaks, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
