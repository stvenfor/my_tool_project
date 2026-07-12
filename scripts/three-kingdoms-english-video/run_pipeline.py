#!/usr/bin/env python3
"""End-to-end Three Kingdoms English video pipeline."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent

sys.path.insert(0, str(ROOT))

from lib import DEFAULT_OUTPUT_ROOT, load_json, save_json, slugify  # noqa: E402


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("$", " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd or PROJECT_ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def ensure_config(episode_id: str = "yijia-xuchang") -> Path:
    demo_dir = DEFAULT_OUTPUT_ROOT / slugify(episode_id)
    demo_dir.mkdir(parents=True, exist_ok=True)
    demo_config = demo_dir / "episode.config.json"
    if not demo_config.exists():
        shutil.copy2(ROOT / "config.template.json", demo_config)
    ref_src = PROJECT_ROOT / "_three-kingdoms-english/reference/yijia-xuchang/reference"
    ref_dst = demo_dir / "reference"
    ref_dst.mkdir(parents=True, exist_ok=True)
    for name in ["source.mp4", "source.audio.m4a", "audio.wav", "bgm.wav", "style_profile.json", "reference_cuts.json", "reference_manifest.json", "transcript.json"]:
        src = ref_src / name
        if src.exists() and not (ref_dst / name).exists():
            shutil.copy2(src, ref_dst / name)
    return demo_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Three Kingdoms English video pipeline.")
    parser.add_argument("--config", default="")
    parser.add_argument("--episode", default="yijia-xuchang")
    parser.add_argument("--skip-script", action="store_true")
    parser.add_argument("--skip-voice", action="store_true")
    parser.add_argument("--skip-clips", action="store_true")
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    config_path = Path(args.config).resolve() if args.config else ensure_config(args.episode)
    config = load_json(config_path)
    work_dir = config_path.parent

    if not args.skip_script:
        run([sys.executable, str(ROOT / "generate_script.py"), "--config", str(config_path)])

    if not args.skip_voice:
        run([sys.executable, str(ROOT / "synthesize_voice.py"), "--config", str(config_path)])

    if not args.skip_clips:
        run([sys.executable, str(ROOT / "map_narration_shots.py"), "--config", str(config_path)])
        run([sys.executable, str(ROOT / "fetch_clips.py"), "--config", str(config_path)])

    run([sys.executable, str(ROOT / "build_storyboard.py"), "--config", str(config_path)])

    storyboard_path = work_dir / "storyboard.json"
    output_path = Path(args.output).resolve() if args.output else (work_dir / "final.mp4")

    if not args.skip_render:
        remotion_dir = ROOT / "remotion"
        if not (remotion_dir / "node_modules").exists():
            run(["npm", "install"], cwd=remotion_dir)

        run(
            [
                "node",
                str(ROOT / "render.mjs"),
                "--storyboard",
                str(storyboard_path.relative_to(PROJECT_ROOT)),
                "--work-dir",
                str(work_dir.relative_to(PROJECT_ROOT)),
                "--output",
                str(output_path.relative_to(PROJECT_ROOT)),
            ]
        )

    douyin_cfg = config.get("douyin", {})
    save_json(
        work_dir / "douyin-video.json",
        {
            "title": douyin_cfg.get("title", config.get("hook_zh", "")),
            "description": douyin_cfg.get("description", ""),
            "tags": douyin_cfg.get("tags", []),
            "videoPath": str(output_path.name),
        },
    )

    save_json(
        work_dir / "pipeline-result.json",
        {
            "config": str(config_path.relative_to(PROJECT_ROOT)),
            "storyboard": str(storyboard_path.relative_to(PROJECT_ROOT)),
            "output": str(output_path.relative_to(PROJECT_ROOT)) if not args.skip_render else "",
            "douyin": str((work_dir / "douyin-video.json").relative_to(PROJECT_ROOT)),
        },
    )
    print(f"Pipeline complete: {work_dir}")


if __name__ == "__main__":
    main()
