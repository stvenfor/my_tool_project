"""Shared helpers for video-factory orchestration."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "_video-factory"
TOPICS_DIR = ROOT / "topics"
ASSETS_DIR = DEFAULT_OUTPUT_ROOT / "assets"
COGNITIVE_ROOT = PROJECT_ROOT / "scripts" / "cognitive-video"
CAT_DRAMA_ROOT = PROJECT_ROOT / "scripts" / "cat-drama-video"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text.strip())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or "project"


def resolve_work_dir(config_path: Path) -> Path:
    return config_path.parent


def project_work_dir(project_id: str) -> Path:
    return DEFAULT_OUTPUT_ROOT / slugify(project_id)


def topic_path(topic_id: str, status: str = "approved") -> Path:
    return TOPICS_DIR / status / f"{slugify(topic_id)}.json"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("$", " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd or PROJECT_ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


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
    data = json.loads(result.stdout)
    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}
    fps_raw = str(stream.get("r_frame_rate", "30/1"))
    if "/" in fps_raw:
        num, den = fps_raw.split("/", 1)
        fps = float(num) / float(den or 1)
    else:
        fps = float(fps_raw)
    return {
        "width": int(stream.get("width", 0)),
        "height": int(stream.get("height", 0)),
        "duration_sec": float(fmt.get("duration", 0)),
        "fps": fps,
    }


def sync_cognitive_config(project_config: dict[str, Any]) -> dict[str, Any]:
    """Map project.config fields to cognitive config.json shape."""
    cognitive = dict(project_config)
    cognitive["topic_id"] = project_config.get("project_id", project_config.get("topic_id", ""))
    visual = str(project_config.get("visual_strategy", project_config.get("asset_mode", "stickman")))
    asset_map = {
        "stickman": "stickman",
        "web": "web",
        "manual_clip": "reference_slice",
        "manual_image": "image",
        "reference_slice": "reference_slice",
        "placeholder": "placeholder",
        "talking_head": "reference_slice",
    }
    cognitive["asset_mode"] = asset_map.get(visual, visual)
    return cognitive


def write_project_config(work_dir: Path, config: dict[str, Any]) -> Path:
    project_path = work_dir / "project.config.json"
    save_json(project_path, config)
    save_json(work_dir / "config.json", sync_cognitive_config(config))
    return project_path


def load_project_config(work_dir: Path) -> dict[str, Any]:
    path = work_dir / "project.config.json"
    if path.exists():
        return load_json(path)
    legacy = work_dir / "config.json"
    if legacy.exists():
        return load_json(legacy)
    raise SystemExit(f"Missing project config in {work_dir}")


def apply_series_assets(config: dict[str, Any]) -> dict[str, Any]:
    series = str(config.get("series", "")).strip()
    if not series:
        return config
    series_slug = slugify(series)
    series_path = ASSETS_DIR / "series" / f"{series_slug}.json"
    if series_path.exists():
        pack = load_json(series_path)
        for key, value in pack.items():
            if key not in config or config[key] in ("", None, [], {}):
                config[key] = value
    return config


def apply_character_assets(config: dict[str, Any]) -> dict[str, Any]:
    voices = dict(config.get("character_voices") or {})
    chars_dir = ASSETS_DIR / "characters"
    if not chars_dir.exists():
        config["character_voices"] = voices
        return config
    for char_file in sorted(chars_dir.glob("*.json")):
        char = load_json(char_file)
        key = str(char.get("key", char_file.stem))
        if key not in voices:
            voices[key] = char.get("voice_profile", {})
    config["character_voices"] = voices
    return config


def copy_if_missing(src: Path, dest: Path) -> None:
    if src.exists() and not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
