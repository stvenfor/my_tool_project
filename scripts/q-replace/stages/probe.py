from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from lib.common import (
    build_shots,
    detect_scene_times,
    probe_video,
    save_json,
    time_to_frame_index,
)


def run_probe_and_extract(
    video_path: Path,
    work_dir: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    meta = probe_video(video_path)
    scene_threshold = config["video"]["scene_threshold"]
    min_shot = config["video"]["min_shot_duration"]
    analysis_fps = config["video"]["analysis_fps"]
    output_fps = config["video"]["output_fps"]

    scene_times = detect_scene_times(video_path, scene_threshold)
    shots = build_shots(scene_times, min_shot)

    frames_dir = work_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    # Full-rate original frames for compositing background.
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"fps={output_fps}",
            "-q:v",
            "2",
            str(frames_dir / "orig_%06d.jpg"),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Downsampled analysis frames.
    analysis_dir = work_dir / "frames" / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"fps={analysis_fps}",
            "-q:v",
            "2",
            str(analysis_dir / "frame_%06d.jpg"),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    analysis_count = len(list(analysis_dir.glob("frame_*.jpg")))
    output_count = len(list(frames_dir.glob("orig_*.jpg")))

    manifest = {
        "video": meta,
        "scene_times": scene_times,
        "shots": shots,
        "analysis_fps": analysis_fps,
        "output_fps": output_fps,
        "analysis_frame_count": analysis_count,
        "output_frame_count": output_count,
        "analysis_to_output_scale": output_fps / analysis_fps,
        "frames_dir": str(frames_dir),
        "analysis_dir": str(analysis_dir),
    }

    for shot in shots:
        shot["analysis_start_frame"] = time_to_frame_index(shot["start"], analysis_fps) + 1
        shot["analysis_end_frame"] = time_to_frame_index(shot["end"], analysis_fps)
        shot["output_start_frame"] = time_to_frame_index(shot["start"], output_fps) + 1
        shot["output_end_frame"] = time_to_frame_index(shot["end"], output_fps)

    save_json(work_dir / "probe.json", manifest)
    return manifest
