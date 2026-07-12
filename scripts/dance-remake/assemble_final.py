#!/usr/bin/env python3
"""Assemble dance remake final: mux BGM + light beauty grade via ffmpeg."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def assemble(
    video: Path,
    audio: Path,
    output: Path,
    *,
    width: int = 720,
    height: int = 1280,
    fps: float = 30.0,
    crf: int = 20,
) -> Path:
    duration = min(probe_duration(video), probe_duration(audio))
    output.parent.mkdir(parents=True, exist_ok=True)

    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        "eq=brightness=0.03:saturation=1.05:gamma=1.02,"
        "unsharp=5:5:0.4:5:5:0.0,"
        f"fps={fps}"
    )

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video),
            "-i",
            str(audio),
            "-t",
            f"{duration:.3f}",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            "44100",
            "-ac",
            "1",
            "-b:a",
            "128k",
            "-shortest",
            str(output),
        ],
        check=True,
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Assemble dance remake final with BGM.")
    parser.add_argument("--video", default="_dance-remake/manual/takes/ai_take_01.mp4")
    parser.add_argument("--audio", default="_dance-remake/reference/audio.wav")
    parser.add_argument("--output", default="_dance-remake/output/final.mp4")
    parser.add_argument("--width", type=int, default=720)
    parser.add_argument("--height", type=int, default=1280)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    video = (root / args.video).resolve()
    audio = (root / args.audio).resolve()
    output = (root / args.output).resolve()

    if not video.exists():
        raise SystemExit(f"Video not found: {video}")
    if not audio.exists():
        raise SystemExit(f"Audio not found: {audio}")

    out = assemble(video, audio, output, width=args.width, height=args.height)
    print(f"Assembled: {out}")


if __name__ == "__main__":
    main()
