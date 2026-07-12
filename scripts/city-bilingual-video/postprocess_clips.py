#!/usr/bin/env python3
"""Normalize clip brightness/quality for consistent visual output."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import load_json, resolve_work_dir  # noqa: E402

# Single unified look — no per-phase brightness shifts.
UNIFIED_EQ = "eq=contrast=1.04:brightness=0.02:saturation=1.05:gamma=1.02"


def _normalize_clip(src: Path, dest: Path, width: int, height: int) -> None:
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width}:{height},"
        f"{UNIFIED_EQ},"
        f"unsharp=5:5:0.3:5:5:0.0,"
        f"fps=30,format=yuv420p"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-vf",
            vf,
            "-an",
            "-c:v",
            "libx264",
            "-crf",
            "17",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            str(dest),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize city clips for consistent quality.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)
    manifest_path = work_dir / "clips_manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"Missing clips manifest: {manifest_path}")

    manifest = load_json(manifest_path)
    clips = manifest.get("clips", [])
    width = int(config.get("width", 1080))
    height = int(config.get("height", 1920))

    for clip in clips:
        src = work_dir / clip["clip"]
        if not src.exists():
            print(f"Skip missing: {src}")
            continue
        tmp = src.with_suffix(".norm.mp4")
        _normalize_clip(src, tmp, width, height)
        tmp.replace(src)
        print(f"Normalized {clip['id']}")


if __name__ == "__main__":
    main()
