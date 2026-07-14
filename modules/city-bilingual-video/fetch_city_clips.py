#!/usr/bin/env python3
"""Fetch or slice city clips for bilingual promo (hybrid asset mode)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from douyin_broll import assign_broll_by_keywords, assign_broll_to_shots, prepare_broll_pools  # noqa: E402
from lib import load_json, resolve_work_dir, save_json  # noqa: E402


def _slice_reference_clip(
    source_mp4: Path,
    output_mp4: Path,
    start_sec: float,
    duration_sec: float,
    width: int,
    height: int,
) -> None:
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1"
    )
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(start_sec),
            "-i",
            str(source_mp4),
            "-t",
            str(duration_sec),
            "-vf",
            vf,
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(output_mp4),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"slice failed: {output_mp4}")


def _placeholder_clip(output_mp4: Path, phase: str, width: int, height: int, duration_sec: float) -> None:
    colors = {
        "day": "0x87a8c8",
        "transition": "0xc88f5a",
        "night": "0x2a1a10",
    }
    color = colors.get(phase, "0x333333")
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s={width}x{height}:d={duration_sec}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(output_mp4),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _load_douyin_sources(config: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    if config.get("douyin_sources"):
        custom = work_dir / str(config["douyin_sources"])
        if custom.exists():
            return load_json(custom)
    template = ROOT / "douyin_sources.template.json"
    city_template = ROOT / f"douyin_sources.{config.get('city_name', '')}.json"
    if city_template.exists():
        return load_json(city_template)
    return load_json(template)


def _fetch_douyin_broll(
    config: dict[str, Any],
    work_dir: Path,
    shots: list[dict[str, Any]],
    width: int,
    height: int,
    force: bool = False,
) -> list[dict[str, Any]]:
    sources = _load_douyin_sources(config, work_dir)
    cut_mode = str(config.get("cut_mode", "reference_cuts"))
    if cut_mode == "narration_sync":
        print("Fetching landmark-matched B-roll (narration_sync)...")
        return assign_broll_by_keywords(shots, work_dir, sources, width, height, force=force)

    pools = prepare_broll_pools(sources, work_dir, force=force)
    if not pools:
        raise RuntimeError("No Douyin B-roll pools built")
    return assign_broll_to_shots(shots, pools, work_dir, width, height)


def fetch_city_clips(config: dict[str, Any], work_dir: Path, force: bool = False) -> list[dict[str, Any]]:
    shot_plan_path = work_dir / "shot_plan.json"
    if not shot_plan_path.exists():
        raise SystemExit(f"Missing shot plan: {shot_plan_path}")

    shot_plan = load_json(shot_plan_path)
    shots = shot_plan.get("shots", [])
    source_mp4 = work_dir / "reference" / "source.mp4"
    width = int(config.get("width", 1080))
    height = int(config.get("height", 1920))
    asset_mode = str(config.get("asset_mode", "hybrid"))

    if asset_mode in {"douyin_broll", "douyin_search", "hybrid"}:
        try:
            clips = _fetch_douyin_broll(config, work_dir, shots, width, height, force=force)
            if clips:
                return clips
        except Exception as exc:
            print(f"Douyin B-roll failed: {exc}")
            if asset_mode == "douyin_broll":
                raise

    clips: list[dict[str, Any]] = []
    for shot in shots:
        clip_path = work_dir / shot["clip"]
        duration = float(shot["duration_sec"])
        if asset_mode in {"hybrid", "reference_slice"} and source_mp4.exists():
            try:
                _slice_reference_clip(
                    source_mp4,
                    clip_path,
                    float(shot["reference_time"]),
                    duration,
                    width,
                    height,
                )
                source = "reference_slice"
            except Exception as exc:
                print(f"Slice failed {shot['id']}: {exc}; using placeholder")
                _placeholder_clip(clip_path, shot.get("phase", "day"), width, height, duration)
                source = "placeholder"
        else:
            _placeholder_clip(clip_path, shot.get("phase", "day"), width, height, duration)
            source = "placeholder"

        clips.append(
            {
                "id": shot["id"],
                "clip": shot["clip"],
                "is_image": False,
                "duration_sec": duration,
                "phase": shot.get("phase", "day"),
                "source": source,
                "douyin_keyword": shot.get("douyin_keyword", ""),
            }
        )

    return clips


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch/slice city clips.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)

    clips = fetch_city_clips(config, work_dir, force=args.force)
    save_json(work_dir / "clips_manifest.json", {"clips": clips, "count": len(clips)})
    print(f"Clips manifest: {work_dir / 'clips_manifest.json'} ({len(clips)} clips)")


if __name__ == "__main__":
    main()
