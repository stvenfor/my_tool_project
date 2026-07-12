"""Shared helpers for city-healing-video pipeline."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "_city-healing" / "output"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text.strip())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or "demo-city"


def resolve_work_dir(config_path: Path) -> Path:
    return config_path.parent


def fill_template(text: str, mapping: dict[str, str]) -> str:
    result = text
    for key, value in mapping.items():
        result = result.replace(f"【{key}】", str(value))
        result = result.replace(f"{{{key}}}", str(value))
    return result


def build_prompt_mapping(config: dict[str, Any]) -> dict[str, str]:
    return {
        "city_name": str(config.get("city_name", "")),
        "district": str(config.get("district", "")),
        "local_shop_type": str(config.get("local_shop_type", "")),
        "local_breakfast": str(config.get("local_breakfast", "")),
        "craft_name": str(config.get("craft_name", "")),
        "dish_name": str(config.get("dish_name", "")),
        "landmark_name": str(config.get("landmark_name", "")),
        "industry_name": str(config.get("industry_name", "")),
        "industry_scene": str(config.get("industry_scene", "")),
    }


def build_narration_mapping(config: dict[str, Any]) -> dict[str, str]:
    mapping = build_prompt_mapping(config)
    mapping.update(
        {
            "目标城市": str(config.get("city_name", "")),
            "本地早餐": str(config.get("local_breakfast", "")),
            "非遗手艺": str(config.get("craft_name", "")),
            "小众地标": str(config.get("landmark_name", "")),
            "人口数据": str(config.get("population_wan", "")),
            "文旅数据": str(config.get("tourism_wan", "")),
            "特色产业": str(config.get("industry_name", "")),
        }
    )
    return mapping


def count_chinese_chars(text: str) -> int:
    compact = re.sub(r"\s+", "", text)
    return len(compact)


def is_chinese_narration(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return False
    chinese = len(re.findall(r"[\u4e00-\u9fff]", compact))
    return chinese / len(compact) >= 0.4


def default_chinese_voice(config: dict[str, Any]) -> str:
    return str(config.get("voice", "zh-CN-YunyangNeural"))


def default_chinese_rate(config: dict[str, Any]) -> str:
    return str(config.get("voice_rate", "-8%"))


def build_scene_prompts(config: dict[str, Any], prompts_path: Path | None = None) -> list[dict[str, Any]]:
    template_path = prompts_path or (ROOT / "prompts" / "scene-prompts.template.json")
    template = load_json(template_path)
    mapping = build_prompt_mapping(config)
    style_suffix = fill_template(template["style_suffix"], mapping)
    negative = template.get("negative_prompt", "")
    scenes: list[dict[str, Any]] = []
    for scene in template["scenes"]:
        core = fill_template(scene["prompt_core"], mapping)
        prompt_en = f"{core}, {scene['camera']}, {style_suffix}"
        scenes.append(
            {
                **scene,
                "prompt_en": prompt_en,
                "negative_prompt": negative,
            }
        )
    return scenes


def default_data_cards(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": "population",
            "label": "常住人口",
            "value": config.get("population_wan", 0),
            "unit": "万人",
            "appear_at_sec": 32,
            "duration_sec": 2.5,
        },
        {
            "id": "tourism",
            "label": "年度文旅",
            "value": config.get("tourism_wan", 0),
            "unit": "万人次",
            "appear_at_sec": 44,
            "duration_sec": 2.5,
        },
        {
            "id": "industry",
            "label": str(config.get("industry_name", "特色产业")),
            "value": config.get("industry_value", 0),
            "unit": str(config.get("industry_unit", "亿元")),
            "appear_at_sec": 50,
            "duration_sec": 2.5,
        },
    ]


def detect_torch_device() -> str:
    try:
        import torch

        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


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


def resolve_voice_reference(config: dict[str, Any], work_dir: Path) -> Path:
    rel = str(config.get("voice_reference_audio", "reference/voice_reference.wav"))
    return work_dir / rel


def resolve_prompt_text(config: dict[str, Any], work_dir: Path) -> str:
    if config.get("voice_reference_prompt_text"):
        return str(config["voice_reference_prompt_text"]).strip()

    meta_path = work_dir / "reference" / "voice_reference.json"
    if meta_path.exists():
        meta = load_json(meta_path)
        if meta.get("prompt_text"):
            return str(meta["prompt_text"]).strip()

    return "当亚马逊雨林的水位以肉眼可见的速度上涨时，那意味着洪泛森林即将来临。"
