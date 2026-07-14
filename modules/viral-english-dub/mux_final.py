#!/usr/bin/env python3
"""Mux English narration onto target video without re-encoding video stream."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import get_audio_duration, load_json, probe_video, resolve_work_dir  # noqa: E402


def mux_final_video(config: dict[str, Any], work_dir: Path, output_path: Path | None = None) -> Path:
    source_mp4 = work_dir / "reference" / "source.mp4"
    narration_wav = work_dir / "final_audio.wav"
    if not narration_wav.exists():
        narration_wav = work_dir / "narration.wav"
    if not source_mp4.exists():
        raise SystemExit(f"Missing target video: {source_mp4}")
    if not narration_wav.exists():
        raise SystemExit(f"Missing narration/final_audio: {narration_wav}")

    output = output_path or (work_dir / "final.mp4")
    video_meta = probe_video(source_mp4)
    target_duration = float(config.get("duration_sec", video_meta["duration_sec"]))
    narration_duration = get_audio_duration(narration_wav)

    filter_parts: list[str] = []
    if narration_duration + 0.05 < target_duration:
        pad = target_duration - narration_duration
        filter_parts.append(f"[1:a]apad=pad_dur={pad:.3f}[aout]")
        map_audio = "[aout]"
    else:
        map_audio = "1:a:0"

    cmd = ["ffmpeg", "-y", "-i", str(source_mp4), "-i", str(narration_wav)]
    if filter_parts:
        cmd.extend(["-filter_complex", ";".join(filter_parts)])
        cmd.extend(["-map", "0:v:0", "-map", map_audio])
    else:
        cmd.extend(["-map", "0:v:0", "-map", "1:a:0"])
    cmd.extend(
        [
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-t",
            str(target_duration),
            str(output),
        ]
    )
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg mux failed")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Mux cloned audio onto target video (video copy).")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)
    output_path = Path(args.output).resolve() if args.output else None

    output = mux_final_video(config, work_dir, output_path)
    print(f"Muxed video (video stream copied): {output}")


if __name__ == "__main__":
    main()
