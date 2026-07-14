"""Shared helpers for city-bilingual-video pipeline."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent
DEFAULT_OUTPUT_ROOT = ROOT / "work" / "output"
DOUYIN_DOWNLOADER = PROJECT_ROOT / "modules" / "shared" / "douyin" / "download_douyin_ref.mjs"
SHARED_MEDIA_ROOT = PROJECT_ROOT / "modules" / "shared" / "media"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text.strip())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or "city"


def resolve_work_dir(config_path: Path) -> Path:
    return config_path.parent


def fill_template(text: str, mapping: dict[str, str]) -> str:
    result = text
    for key, value in mapping.items():
        result = result.replace(f"【{key}】", str(value))
        result = result.replace(f"{{{key}}}", str(value))
    return result


def build_config_mapping(config: dict[str, Any]) -> dict[str, str]:
    city = str(config.get("city_name", ""))
    ancient = str(config.get("ancient_name", city))
    day_landmarks = config.get("landmarks_day", [])
    night_landmarks = config.get("landmarks_night", [])
    return {
        "city_name": city,
        "ancient_name": ancient,
        "landmark_day_1": str(day_landmarks[0]) if day_landmarks else city,
        "landmark_day_2": str(day_landmarks[1]) if len(day_landmarks) > 1 else city,
        "landmark_day_3": str(day_landmarks[2]) if len(day_landmarks) > 2 else city,
        "landmark_night_1": str(night_landmarks[0]) if night_landmarks else ancient,
        "landmark_night_2": str(night_landmarks[1]) if len(night_landmarks) > 1 else ancient,
        "landmark_night_3": str(night_landmarks[2]) if len(night_landmarks) > 2 else ancient,
        "hook_zh": str(config.get("hook_zh", f"白天是{city}，晚上是{ancient}")),
    }


def get_audio_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffprobe failed")
    return float(result.stdout.strip())


def probe_video(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffprobe failed")
    payload = json.loads(result.stdout)
    stream = (payload.get("streams") or [{}])[0]
    fmt = payload.get("format") or {}
    fps_raw = str(stream.get("r_frame_rate", "30/1"))
    if "/" in fps_raw:
        num, den = fps_raw.split("/", 1)
        fps = float(num) / float(den or 1)
    else:
        fps = float(fps_raw)
    return {
        "width": int(stream.get("width", 1080)),
        "height": int(stream.get("height", 1920)),
        "fps": round(fps, 3),
        "duration_sec": round(float(fmt.get("duration", 0)), 3),
    }


def _atempo_chain(ratio: float) -> str:
    filters: list[str] = []
    remaining = ratio
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.6f}")
    return ",".join(filters)


def fit_audio_duration(
    input_wav: Path,
    output_wav: Path,
    target_sec: float,
    sample_rate: int = 44100,
) -> float:
    current = get_audio_duration(input_wav)
    if current <= 0:
        raise RuntimeError(f"Invalid audio duration: {input_wav}")
    ratio = current / target_sec
    filter_chain = _atempo_chain(ratio)
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_wav),
            "-af",
            filter_chain,
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            str(output_wav),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg atempo failed")
    return get_audio_duration(output_wav)


def run_cmd(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    print("$", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd or PROJECT_ROOT, capture_output=True, text=True)


def download_reference_video(url: str, output_mp4: Path) -> None:
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    if DOUYIN_DOWNLOADER.exists():
        result = run_cmd(
            ["node", str(DOUYIN_DOWNLOADER), "--url", url, "--output", str(output_mp4)],
            cwd=DOUYIN_DOWNLOADER.parent,
        )
        if result.returncode == 0 and output_mp4.exists() and output_mp4.stat().st_size > 10000:
            return
        print(result.stderr or result.stdout)

    raise SystemExit(
        f"Failed to download reference video. Place source manually at: {output_mp4}"
    )


def extract_audio_from_video(video_path: Path, output_audio: Path) -> None:
    output_audio.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-acodec",
            "aac",
            str(output_audio),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg audio extract failed")


def audio_to_wav(input_audio: Path, output_wav: Path, sample_rate: int = 44100) -> None:
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_audio),
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            str(output_wav),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg wav convert failed")


def default_english_voice(config: dict[str, Any]) -> str:
    return str(config.get("voice", "en-US-GuyNeural"))


def default_english_rate(config: dict[str, Any]) -> str:
    return str(config.get("voice_rate", "-5%"))


def infer_day_night_pivot(cuts: list[dict[str, Any]]) -> float:
    if not cuts:
        return 0.0
    total = sum(float(c.get("duration", 0)) for c in cuts)
    return round(total * 0.5, 3)


def assign_shot_phases(cuts: list[dict[str, Any]], pivot_sec: float) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    cursor = 0.0
    for index, cut in enumerate(cuts):
        start = float(cut.get("time", cursor))
        duration = float(cut.get("duration", 0))
        end = start + duration
        if end <= pivot_sec - 0.5:
            phase = "day"
        elif start >= pivot_sec + 0.5:
            phase = "night"
        else:
            phase = "transition"
        enriched.append(
            {
                **cut,
                "id": f"S{index + 1:02d}",
                "start_sec": round(start, 3),
                "end_sec": round(end, 3),
                "phase": phase,
            }
        )
        cursor = end
    return enriched
