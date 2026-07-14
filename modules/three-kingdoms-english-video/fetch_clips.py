#!/usr/bin/env python3
"""Slice reference video or import manual clips for Three Kingdoms episodes."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

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
    vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1"
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
    colors = {"hook": "0xc88f5a", "story": "0x8a6a4a", "closing": "0x4a3020"}
    color = colors.get(phase, "0x5a4030")
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


def _resolve_source_mp4(config: dict[str, Any], work_dir: Path) -> Path | None:
    candidates = [
        work_dir / "reference" / "source.mp4",
        ROOT.parent.parent / str(config.get("reference_work_dir", "")) / "reference" / "source.mp4",
        ROOT / "work" / "reference" / "yijia-xuchang" / "reference" / "source.mp4",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def fetch_clips(config: dict[str, Any], work_dir: Path, force: bool = False) -> list[dict[str, Any]]:
    shot_plan = load_json(work_dir / "shot_plan.json")
    shots = shot_plan.get("shots", [])
    source_mp4 = _resolve_source_mp4(config, work_dir)
    manual_dir = work_dir / "manual_clips"
    width = int(config.get("width", 1080))
    height = int(config.get("height", 1920))
    asset_mode = str(config.get("asset_mode", "reference_slice"))

    clips: list[dict[str, Any]] = []
    for shot in shots:
        clip_path = work_dir / shot["clip"]
        duration = float(shot["duration_sec"])
        source = "placeholder"

        manual_clip = manual_dir / f"{shot['id']}.mp4"
        use_manual = asset_mode in {"manual_clip", "manual_or_reference"} and manual_clip.exists()
        if use_manual and not force:
            clip_path.parent.mkdir(parents=True, exist_ok=True)
            if manual_clip.resolve() != clip_path.resolve():
                clip_path.write_bytes(manual_clip.read_bytes())
            source = "manual_clip"
        elif asset_mode in {"reference_slice", "hybrid", "manual_or_reference"} and source_mp4 and source_mp4.exists():
            try:
                _slice_reference_clip(
                    source_mp4,
                    clip_path,
                    float(shot.get("reference_time", 0)),
                    duration,
                    width,
                    height,
                )
                source = "reference_slice"
            except Exception as exc:
                print(f"Slice failed {shot['id']}: {exc}")
                _placeholder_clip(clip_path, shot.get("phase", "story"), width, height, duration)
                source = "placeholder"
        else:
            _placeholder_clip(clip_path, shot.get("phase", "story"), width, height, duration)

        clips.append(
            {
                "id": shot["id"],
                "clip": shot["clip"],
                "is_image": False,
                "duration_sec": duration,
                "phase": shot.get("phase", "story"),
                "source": source,
                "visual_keyword": shot.get("visual_keyword", ""),
                "reference_time": shot.get("reference_time", 0),
            }
        )

    return clips


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch/slice clips for Three Kingdoms video.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)

    clips = fetch_clips(config, work_dir, force=args.force)
    save_json(work_dir / "clips_manifest.json", {"clips": clips, "count": len(clips)})
    print(f"Clips manifest: {work_dir / 'clips_manifest.json'} ({len(clips)} clips)")


if __name__ == "__main__":
    main()
