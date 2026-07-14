"""Narration (口播解说) mode — delegates to cognitive-video."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

from lib import COGNITIVE_ROOT, load_json, run, save_json, write_project_config  # noqa: E402
from modes.common import export_douyin, render_storyboard, run_cognitive_script  # noqa: E402


def run_narration_pipeline(
    config: dict[str, Any],
    work_dir: Path,
    *,
    skip_analyze: bool = False,
    skip_script: bool = False,
    skip_voice: bool = False,
    skip_broll: bool = False,
    skip_render: bool = False,
    skip_export: bool = False,
    use_llm: bool = False,
    output_path: Path | None = None,
) -> dict[str, Any]:
    config_path = write_project_config(work_dir, config)
    topic_id = str(config.get("project_id", config.get("topic_id", "")))

    if not skip_analyze and not (work_dir / "reference" / "reference_manifest.json").exists():
        run(
            [
                sys.executable,
                str(COGNITIVE_ROOT / "analyze_reference.py"),
                "--url",
                str(config.get("reference_url", "")),
                "--id",
                topic_id,
                "--caption",
                str(config.get("hook", "")),
                "--title",
                str(config.get("title", "")),
                "--series",
                str(config.get("series", "认知提升")),
                "--episode",
                str(config.get("episode", "01")),
                "--work-dir",
                str(work_dir),
            ]
        )
        manifest = load_json(work_dir / "reference" / "reference_manifest.json")
        config["duration_sec"] = manifest.get("duration_sec", config.get("duration_sec", 60))
        write_project_config(work_dir, config)

    if not skip_script:
        run_cognitive_script(work_dir / "config.json", use_llm=use_llm or bool(config.get("use_llm")))

    voice_strategy = str(config.get("voice_strategy", "edge_tts"))
    if not skip_voice:
        if voice_strategy == "clone":
            run([sys.executable, str(Path(__file__).resolve().parent.parent / "voice_clone.py"), "--config", str(config_path)])
        else:
            run([sys.executable, str(COGNITIVE_ROOT / "synthesize_voice.py"), "--config", str(work_dir / "config.json")])

    if not skip_broll:
        run([sys.executable, str(COGNITIVE_ROOT / "fetch_broll.py"), "--config", str(work_dir / "config.json")])

    run([sys.executable, str(COGNITIVE_ROOT / "build_storyboard.py"), "--config", str(work_dir / "config.json")])

    final_output = output_path or (work_dir / "output" / "final.mp4")
    if not skip_render:
        render_storyboard(work_dir, final_output)

    if not skip_export:
        export_douyin(config, work_dir)

    result = {
        "mode": "narration",
        "config": str(config_path.relative_to(work_dir.parent.parent)),
        "storyboard": str((work_dir / "storyboard.json").relative_to(work_dir.parent.parent)),
        "output": str(final_output.relative_to(work_dir.parent.parent)) if not skip_render else "",
    }
    save_json(work_dir / "pipeline-result.json", result)
    return result


def migrate_from_cognitive(project_id: str, work_dir: Path) -> bool:
    """Copy existing cognitive-video output into video-factory work dir."""
    # work_dir = modules/video-factory/work/<id> → sibling cognitive work
    src = work_dir.parent.parent.parent / "cognitive-video" / "work" / project_id
    if not src.exists():
        return False
    for name in ("config.json", "script.json", "subtitles.json", "storyboard.json", "narration.wav",
                 "narration.zh.txt", "clips_manifest.json", "douyin-video.json", "pipeline-result.json",
                 "ambient_bgm.wav", "project.config.json"):
        copy_if = src / name
        if copy_if.exists():
            shutil.copy2(copy_if, work_dir / name)
    for sub in ("clips", "reference", "output", "manual_clips"):
        sub_src = src / sub
        if sub_src.exists():
            dest = work_dir / sub
            if not dest.exists():
                shutil.copytree(sub_src, dest)
    if (work_dir / "config.json").exists() and not (work_dir / "project.config.json").exists():
        cfg = load_json(work_dir / "config.json")
        cfg["project_id"] = project_id
        cfg["mode"] = "narration"
        cfg["visual_strategy"] = cfg.get("asset_mode", "stickman")
        cfg["voice_strategy"] = "edge_tts"
        write_project_config(work_dir, cfg)
    return True
