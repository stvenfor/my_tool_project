#!/usr/bin/env python3
"""Slice local Douyin/montage videos into clip library segments at scene boundaries."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLIPS_DIR = ROOT / "clips"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Slice local Douyin videos into beat-montage clips.")
    parser.add_argument("videos", nargs="+", help="Local mp4 paths")
    parser.add_argument("--manifest", default=str(ROOT / "clip_manifest.json"))
    parser.add_argument("--scene-threshold", type=float, default=0.32)
    parser.add_argument("--min-duration", type=float, default=0.35)
    parser.add_argument("--max-duration", type=float, default=4.5)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def _detect_scene_times(path: Path, threshold: float) -> list[float]:
    cmd = [
        "ffmpeg",
        "-i",
        str(path),
        "-filter:v",
        f"select='gt(scene,{threshold})',showinfo",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    times = [0.0]
    for line in proc.stderr.splitlines():
        match = re.search(r"pts_time:([0-9.]+)", line)
        if match:
            times.append(round(float(match.group(1)), 3))
    duration = _probe_duration(path)
    if times[-1] < duration - 0.05:
        times.append(round(duration, 3))
    return sorted(set(times))


def _build_segments(times: list[float], min_duration: float, max_duration: float) -> list[tuple[float, float]]:
    segments: list[tuple[float, float]] = []
    start = times[0]
    for point in times[1:]:
        duration = point - start
        if duration < min_duration:
            continue
        if duration > max_duration:
            cursor = start
            while point - cursor > max_duration:
                segments.append((cursor, cursor + max_duration))
                cursor += max_duration
            if point - cursor >= min_duration:
                segments.append((cursor, point))
        else:
            segments.append((start, point))
        start = point
    return segments


def _normalize_segment(src: Path, dest: Path, start: float, duration: float) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(src),
            "-t",
            f"{duration:.3f}",
            "-vf",
            "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "22",
            str(dest),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _guess_type(index: int, duration: float, source_name: str) -> tuple[str, int, list[str]]:
    if duration >= 2.0:
        return "slow_build", 4, ["蓄力", "慢镜", source_name]
    if index % 5 == 0:
        return "comedy", 3, ["喜剧", "调剂", source_name]
    if index % 3 == 0:
        return "action_gun", 9, ["射击", "枪战", source_name]
    if index % 2 == 0:
        return "action_punch", 8, ["拳脚", "打击", source_name]
    return "hero_shot", 5, ["定格", "结尾", source_name]


def slice_videos(
    video_paths: list[Path],
    manifest_path: Path,
    scene_threshold: float,
    min_duration: float,
    max_duration: float,
    force: bool,
) -> list[dict]:
    manifest: list[dict] = []
    clip_index = 0

    for video_path in video_paths:
        if not video_path.exists():
            raise FileNotFoundError(video_path)

        source_name = video_path.stem[:16]
        scene_times = _detect_scene_times(video_path, scene_threshold)
        segments = _build_segments(scene_times, min_duration, max_duration)
        print(f"{video_path.name}: {len(segments)} segments from {len(scene_times)} scene points")

        for seg_start, seg_end in segments:
            duration = round(seg_end - seg_start, 3)
            clip_type, energy, tags = _guess_type(clip_index, duration, source_name)
            clip_id = f"dy_{source_name}_{clip_index:03d}"
            rel_path = f"{clip_type}/{clip_id}.mp4"
            dest = CLIPS_DIR / rel_path

            if dest.exists() and not force:
                print(f"Skip existing: {dest.name}")
            else:
                print(f"Extract {clip_id}: {seg_start:.2f}-{seg_end:.2f}s")
                _normalize_segment(video_path, dest, seg_start, duration)

            manifest.append(
                {
                    "id": clip_id,
                    "path": rel_path,
                    "type": clip_type,
                    "energy": energy,
                    "tags": tags,
                    "trim_in": 0.0,
                    "duration_hint": min(2.0, max(0.5, duration)),
                    "source_video": str(video_path),
                    "source_range": [seg_start, seg_end],
                }
            )
            clip_index += 1

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved manifest ({len(manifest)} clips): {manifest_path}")
    return manifest


def main() -> None:
    args = parse_args()
    slice_videos(
        [Path(item).resolve() for item in args.videos],
        Path(args.manifest).resolve(),
        args.scene_threshold,
        args.min_duration,
        args.max_duration,
        args.force,
    )


if __name__ == "__main__":
    main()
