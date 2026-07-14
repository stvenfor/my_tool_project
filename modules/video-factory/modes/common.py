"""Shared pipeline helpers for video-factory modes."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from lib import COGNITIVE_ROOT, PROJECT_ROOT, load_json, run, save_json  # noqa: E402


def render_storyboard(work_dir: Path, output_path: Path) -> None:
    remotion_dir = COGNITIVE_ROOT / "remotion"
    if not (remotion_dir / "node_modules").exists():
        run(["npm", "install"], cwd=remotion_dir)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "node",
            str(COGNITIVE_ROOT / "render.mjs"),
            "--storyboard",
            str((work_dir / "storyboard.json").relative_to(PROJECT_ROOT)),
            "--work-dir",
            str(work_dir.relative_to(PROJECT_ROOT)),
            "--output",
            str(output_path.relative_to(PROJECT_ROOT)),
        ]
    )


def export_douyin(config: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    script = load_json(work_dir / "script.json") if (work_dir / "script.json").exists() else {}
    title = str(script.get("title", config.get("title", "口播视频")))
    if len(title) > 30:
        title = title[:30]
    tags = list(script.get("tags", config.get("tags", [])))[:5]
    hook = str(script.get("hook", config.get("hook", "")))
    cta = str(script.get("cta", config.get("cta", "建议收藏")))
    series = str(script.get("series", config.get("series", "")))
    episode = str(script.get("episode", config.get("episode", "01")))
    description = f"{hook} {cta} {series}{episode}".strip()
    rel_video = "output/final.mp4" if (work_dir / "output" / "final.mp4").exists() else "final.mp4"
    payload = {
        "videoPath": rel_video,
        "title": title,
        "description": description,
        "tags": tags,
    }
    save_json(work_dir / "douyin-video.json", payload)
    return payload


def run_cognitive_script(config_path: Path, use_llm: bool = False) -> None:
    cmd = [sys.executable, str(COGNITIVE_ROOT / "generate_script.py"), "--config", str(config_path)]
    if use_llm:
        cmd.append("--llm")
    run(cmd)
