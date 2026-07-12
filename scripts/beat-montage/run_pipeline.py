#!/usr/bin/env python3
"""Run the beat-montage pipeline: analyze -> map -> render."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Beat montage end-to-end pipeline.")
    parser.add_argument("--audio", required=True, help="BGM audio path")
    parser.add_argument("--max-duration", type=float, default=45.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--finalize", action="store_true", help="Write montage.json and render final output")
    return parser.parse_args()


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("$", " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd or PROJECT_ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> None:
    args = parse_args()
    audio_path = Path(args.audio).resolve()
    if not audio_path.exists():
        raise SystemExit(f"Audio not found: {audio_path}")

    output_dir = ROOT / "output"
    beats_dir = output_dir
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    render_output_dir = PROJECT_ROOT / config.get("output_dir", "_beat-montage/output")
    output_dir.mkdir(parents=True, exist_ok=True)
    render_output_dir.mkdir(parents=True, exist_ok=True)

    beats_path = beats_dir / "beats.json"
    run(
        [
            sys.executable,
            str(ROOT / "analyze_beats.py"),
            str(audio_path),
            "--output",
            str(beats_path),
            "--max-duration",
            str(args.max_duration),
        ]
    )

    montage_name = "montage.json" if args.finalize else "montage.draft.json"
    montage_path = output_dir / montage_name
    map_cmd = [
        sys.executable,
        str(ROOT / "map_clips.py"),
        "--beats",
        str(beats_path),
        "--audio",
        f"bgm/{audio_path.name}",
        "--output",
        str(montage_path),
        "--seed",
        str(args.seed),
    ]
    if args.finalize:
        map_cmd.append("--finalize")
    run(map_cmd)

    if args.skip_render:
        print(f"Pipeline done (render skipped): {montage_path}")
        return

    output_mp4 = render_output_dir / ("hongri-montage.mp4" if args.finalize else "hongri-montage-preview.mp4")
    run(
        [
            "node",
            str(ROOT / "render.mjs"),
            "--montage",
            str(montage_path),
            "--output",
            str(output_mp4),
        ]
    )

    douyin_config = {
        "videoPath": str(output_mp4.relative_to(PROJECT_ROOT)),
        "title": config["douyin"]["title"],
        "description": config["douyin"]["description"],
        "tags": config["douyin"]["tags"],
    }
    douyin_path = render_output_dir / "douyin-video.json"
    douyin_path.write_text(json.dumps(douyin_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved douyin config: {douyin_path}")


if __name__ == "__main__":
    main()
