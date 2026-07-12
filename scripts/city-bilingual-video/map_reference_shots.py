#!/usr/bin/env python3
"""Map reference cut timeline to replacement clip manifest."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import fill_template, load_json, resolve_work_dir, save_json  # noqa: E402


def _build_keyword(shot: dict[str, Any], prompts: dict[str, Any], mapping: dict[str, str]) -> str:
    phase = shot.get("phase", "day")
    phase_cfg = prompts.get("phases", {}).get(phase, {})
    keywords = phase_cfg.get("keywords", [])
    if keywords:
        return fill_template(str(keywords[0]), mapping)
    return fill_template(str(prompts.get("phases", {}).get("day", {}).get("keywords", ["城市"])[0]), mapping)


def _build_prompt(shot: dict[str, Any], prompts: dict[str, Any], mapping: dict[str, str]) -> str:
    phase = shot.get("phase", "day")
    phase_cfg = prompts.get("phases", {}).get(phase, {})
    core = fill_template(str(phase_cfg.get("prompt_core", "")), mapping)
    suffix = fill_template(str(prompts.get("style_suffix", "")), mapping)
    return f"{core}, {suffix}".strip(", ")


def map_reference_shots(config: dict[str, Any], work_dir: Path) -> list[dict[str, Any]]:
    cuts_path = work_dir / "reference" / "reference_cuts.json"
    if not cuts_path.exists():
        raise SystemExit(f"Missing reference cuts: {cuts_path}")

    cuts_payload = load_json(cuts_path)
    shots = cuts_payload.get("shots") or cuts_payload.get("cuts", [])
    prompts = load_json(ROOT / "prompts" / "scene-prompts.template.json")
    mapping = {
        "city_name": str(config.get("city_name", "")),
        "ancient_name": str(config.get("ancient_name", "")),
        "landmark_day_1": str((config.get("landmarks_day") or [""])[0]),
        "landmark_day_2": str((config.get("landmarks_day") or ["", ""])[1] if len(config.get("landmarks_day", [])) > 1 else ""),
        "landmark_night_1": str((config.get("landmarks_night") or [""])[0]),
    }

    mapped: list[dict[str, Any]] = []
    for shot in shots:
        shot_id = shot.get("id") or f"S{len(mapped)+1:02d}"
        mapped.append(
            {
                "id": shot_id,
                "phase": shot.get("phase", "day"),
                "start_sec": float(shot.get("start_sec", shot.get("time", 0))),
                "duration_sec": float(shot.get("duration", shot.get("duration_sec", 2.0))),
                "reference_time": float(shot.get("time", shot.get("start_sec", 0))),
                "douyin_keyword": _build_keyword(shot, prompts, mapping),
                "ai_prompt": _build_prompt(shot, prompts, mapping),
                "clip": f"clips/{shot_id}.mp4",
                "source": "reference_slice",
            }
        )
    return mapped


def main() -> None:
    parser = argparse.ArgumentParser(description="Map reference shots to clip plan.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)

    mapped = map_reference_shots(config, work_dir)
    save_json(work_dir / "shot_plan.json", {"shots": mapped, "count": len(mapped)})
    print(f"Shot plan saved: {work_dir / 'shot_plan.json'} ({len(mapped)} shots)")


if __name__ == "__main__":
    main()
