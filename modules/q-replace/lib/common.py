from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or ROOT / "config.yaml"
    with cfg_path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def resolve_device(requested: str = "auto") -> str:
    import torch

    if requested == "cpu":
        return "cpu"
    if requested == "mps":
        return "mps" if torch.backends.mps.is_available() else "cpu"
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def probe_video(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    video_stream = next(s for s in data["streams"] if s["codec_type"] == "video")
    fps_parts = video_stream.get("r_frame_rate", "30/1").split("/")
    fps = float(fps_parts[0]) / float(fps_parts[1]) if len(fps_parts) == 2 else 30.0
    return {
        "path": str(path.resolve()),
        "duration": float(data["format"]["duration"]),
        "width": int(video_stream["width"]),
        "height": int(video_stream["height"]),
        "fps": round(fps, 3),
        "has_audio": any(s["codec_type"] == "audio" for s in data["streams"]),
    }


def detect_scene_times(path: Path, threshold: float) -> list[float]:
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
    duration = probe_duration(path)
    if times[-1] < duration - 0.05:
        times.append(round(duration, 3))
    return sorted(set(times))


def build_shots(times: list[float], min_duration: float) -> list[dict[str, float]]:
    shots: list[dict[str, float]] = []
    for index in range(len(times) - 1):
        start = times[index]
        end = times[index + 1]
        duration = end - start
        if duration < min_duration:
            continue
        shots.append({"shot_id": len(shots), "start": start, "end": end, "duration": duration})
    if not shots:
        shots.append({"shot_id": 0, "start": 0.0, "end": times[-1], "duration": times[-1]})
    return shots


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def frame_index_to_time(frame_idx: int, fps: float) -> float:
    return round(frame_idx / fps, 4)


def time_to_frame_index(time_sec: float, fps: float) -> int:
    return int(round(time_sec * fps))
