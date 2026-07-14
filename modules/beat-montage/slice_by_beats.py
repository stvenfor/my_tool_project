#!/usr/bin/env python3
"""Pre-slice downloaded Douyin videos by beat-interval windows; keep top-1 peak per video."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from analyze_clip_actions import _infer_energy, detect_action_peaks
from slice_douyin_video import _normalize_segment, _probe_duration

ROOT = Path(__file__).resolve().parent
CLIPS_DIR = ROOT / "clips"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Slice source videos by beat windows.")
    parser.add_argument("videos", nargs="+", help="Downloaded mp4 paths")
    parser.add_argument("--cut-grid", required=True)
    parser.add_argument("--manifest", default=str(ROOT / "clip_manifest.json"))
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def _load_cut_grid(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _guess_type_from_strength(strength: float, duration: float) -> tuple[str, int, list[str]]:
    if strength >= 0.75:
        return "action_punch", 9, ["拳脚", "打击"]
    if strength >= 0.6:
        return "action_gun", 8, ["射击", "枪战"]
    if duration >= 1.2:
        return "slow_build", 4, ["蓄力", "慢镜"]
    if strength <= 0.4:
        return "comedy", 3, ["喜剧", "调剂"]
    return "hero_shot", 5, ["定格", "结尾"]


def _extract_temp_segment(src: Path, start: float, duration: float, dest: Path) -> None:
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


def _best_window(
    video_path: Path,
    beat_interval: float,
    window_duration: float,
) -> dict | None:
    source_duration = _probe_duration(video_path)
    if source_duration < window_duration:
        window_duration = max(0.3, source_duration)

    step = max(0.25, beat_interval * 0.5)
    candidates: list[dict] = []
    cursor = 0.0
    temp_dir = ROOT / "output" / "_beat_windows"
    temp_dir.mkdir(parents=True, exist_ok=True)

    while cursor + window_duration <= source_duration + 0.01:
        window_duration_actual = min(window_duration, source_duration - cursor)
        if window_duration_actual < 0.3:
            break

        temp_path = temp_dir / f"{video_path.stem}_{int(cursor * 1000)}.mp4"
        try:
            _extract_temp_segment(video_path, cursor, window_duration_actual, temp_path)
            peaks = detect_action_peaks(temp_path, fps=10.0, width=160, min_gap=0.2, top_k=6)
        except subprocess.CalledProcessError:
            cursor += step
            continue
        finally:
            if temp_path.exists():
                temp_path.unlink()

        if not peaks:
            cursor += step
            continue

        best_peak = max(peaks, key=lambda item: float(item["strength"]))
        candidates.append(
            {
                "window_start": round(cursor, 3),
                "window_duration": round(window_duration_actual, 3),
                "peak_time": float(best_peak["time"]),
                "peak_strength": float(best_peak["strength"]),
                "peaks": peaks,
            }
        )
        cursor += step

    if not candidates:
        return None

    return max(candidates, key=lambda item: item["peak_strength"])


def slice_videos_by_beats(
    video_paths: list[Path],
    cut_grid: dict,
    manifest_path: Path,
    force: bool,
) -> list[dict]:
    beat_interval = float(cut_grid.get("median_beat_interval", 0.48))
    default_window = min(1.5, max(0.3, beat_interval * 2))
    manifest: list[dict] = []

    for video_path in video_paths:
        if not video_path.exists():
            raise FileNotFoundError(video_path)

        source_name = video_path.stem[:20]
        best = _best_window(video_path, beat_interval, default_window)
        if best is None:
            print(f"Skip (no action window): {video_path.name}")
            continue

        seg_start = best["window_start"]
        seg_duration = best["window_duration"]
        peak_time = best["peak_time"]
        peak_strength = best["peak_strength"]

        clip_type, energy, tags = _guess_type_from_strength(peak_strength, seg_duration)
        tags = [*tags, source_name]
        clip_id = f"beat_{source_name}"
        rel_path = f"{clip_type}/{clip_id}.mp4"
        dest = CLIPS_DIR / rel_path

        if dest.exists() and not force:
            print(f"Skip existing: {dest.name}")
        else:
            print(f"Extract {clip_id}: {seg_start:.2f}s +{seg_duration:.2f}s peak@{peak_time:.2f}s")
            _normalize_segment(video_path, dest, seg_start, seg_duration)

        peaks = detect_action_peaks(dest, fps=12.0, width=180, min_gap=0.2, top_k=8)
        manifest.append(
            {
                "id": clip_id,
                "path": rel_path,
                "type": clip_type,
                "energy": energy or _infer_energy(peaks),
                "tags": tags,
                "trim_in": 0.0,
                "duration_hint": round(seg_duration, 3),
                "source_video": str(video_path.resolve()),
                "source_range": [seg_start, round(seg_start + seg_duration, 3)],
                "beat_window": {
                    "interval": beat_interval,
                    "peak_global": round(seg_start + peak_time, 3),
                },
                "action_peaks": peaks,
                "source_duration": round(seg_duration, 2),
            }
        )

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved manifest ({len(manifest)} beat-sliced clips): {manifest_path}")
    return manifest


def main() -> None:
    args = parse_args()
    cut_grid = _load_cut_grid(Path(args.cut_grid).resolve())
    slice_videos_by_beats(
        [Path(item).resolve() for item in args.videos],
        cut_grid,
        Path(args.manifest).resolve(),
        args.force,
    )


if __name__ == "__main__":
    main()
