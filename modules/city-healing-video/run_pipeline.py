#!/usr/bin/env python3
"""End-to-end city-healing video pipeline."""

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


def ensure_demo_config() -> Path:
    demo_dir = DEFAULT_OUTPUT_ROOT / "demo-city"
    demo_dir.mkdir(parents=True, exist_ok=True)
    demo_config = demo_dir / "city.config.json"
    if not demo_config.exists():
        shutil.copy2(ROOT / "config.template.json", demo_config)
    return demo_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Run city-healing video pipeline.")
    parser.add_argument("--config", default="", help="Path to city.config.json")
    parser.add_argument("--use-ai-clips", action="store_true", help="Use videoagent instead of placeholders")
    parser.add_argument("--skip-clips", action="store_true")
    parser.add_argument("--skip-voice", action="store_true")
    parser.add_argument("--skip-voice-ref", action="store_true")
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--output", default="", help="Output mp4 path")
    args = parser.parse_args()

    if args.config:
        config_path = Path(args.config).resolve()
        if not config_path.exists():
            raise SystemExit(f"Config not found: {config_path}")
    else:
        config_path = ensure_demo_config()

    config = load_json(config_path)
    work_dir = config_path.parent
    work_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_clips:
        if args.use_ai_clips:
            run(
                [
                    sys.executable,
                    str(ROOT / "generate_clips.py"),
                    "--config",
                    str(config_path),
                    "--placeholder-on-fail",
                ]
            )
        else:
            run(
                [
                    sys.executable,
                    str(ROOT / "generate_placeholder_clips.py"),
                    "--config",
                    str(config_path),
                ]
            )

    if not args.skip_voice:
        if config.get("voice_mode") == "clone" and not args.skip_voice_ref:
            run(
                [
                    sys.executable,
                    str(ROOT / "fetch_voice_reference.py"),
                    "--config",
                    str(config_path),
                ]
            )
        run([sys.executable, str(ROOT / "synthesize_voice.py"), "--config", str(config_path)])

    run([sys.executable, str(ROOT / "build_storyboard.py"), "--config", str(config_path)])

    storyboard_path = work_dir / "storyboard.json"
    storyboard = load_json(storyboard_path)

    slug = slugify(str(config.get("city_name", "demo-city")))
    output_path = (
        Path(args.output).resolve()
        if args.output
        else (work_dir / "final.mp4")
    )

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

    save_json(
        work_dir / "pipeline-result.json",
        {
            "config": str(config_path.relative_to(PROJECT_ROOT)),
            "storyboard": str(storyboard_path.relative_to(PROJECT_ROOT)),
            "output": str(output_path.relative_to(PROJECT_ROOT)) if not args.skip_render else "",
            "city_name": storyboard.get("city_name"),
        },
    )

    print(f"Pipeline complete: {work_dir}")


if __name__ == "__main__":
    main()
