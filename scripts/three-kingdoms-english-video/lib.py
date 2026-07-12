"""Shared helpers for three-kingdoms-english-video pipeline."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "_three-kingdoms-english" / "output"
REFERENCE_ROOT = PROJECT_ROOT / "_three-kingdoms-english" / "reference"
DOUYIN_DOWNLOADER = PROJECT_ROOT / "scripts" / "cffex-daily" / "douyin" / "download_douyin_ref.mjs"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text.strip())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or "episode"


def resolve_work_dir(config_path: Path) -> Path:
    return config_path.parent


def fill_template(text: str, mapping: dict[str, str]) -> str:
    result = text
    for key, value in mapping.items():
        result = result.replace(f"【{key}】", str(value))
        result = result.replace(f"{{{key}}}", str(value))
    return result


def build_config_mapping(config: dict[str, Any]) -> dict[str, str]:
    characters = config.get("characters", [])
    return {
        "episode_title": str(config.get("episode_title", "")),
        "episode_hook": str(config.get("episode_hook", "")),
        "series_title": str(config.get("series_title", "儿童英语三国")),
        "character_1": str(characters[0]) if characters else "曹操",
        "character_2": str(characters[1]) if len(characters) > 1 else "汉献帝",
        "character_3": str(characters[2]) if len(characters) > 2 else "董昭",
        "hook_zh": str(config.get("hook_zh", "")),
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
    raise SystemExit(f"Failed to download reference video. Place source manually at: {output_mp4}")


def extract_audio_from_video(video_path: Path, output_audio: Path) -> None:
    output_audio.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-acodec", "aac", str(output_audio)],
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
    return str(config.get("voice", "en-US-AnaNeural"))


def default_english_rate(config: dict[str, Any]) -> str:
    return str(config.get("voice_rate", "-10%"))


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


def assign_reference_times(shots: list[dict[str, Any]], source_duration: float) -> list[dict[str, Any]]:
    """Map narration shots to proportional positions in reference video."""
    total = sum(float(s.get("duration_sec", 0)) for s in shots) or 1.0
    cursor = 0.0
    for shot in shots:
        ratio_start = cursor / total
        shot["reference_time"] = round(ratio_start * source_duration, 3)
        cursor += float(shot.get("duration_sec", 0))
    return shots
