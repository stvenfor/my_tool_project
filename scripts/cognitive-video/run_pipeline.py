#!/usr/bin/env python3
"""End-to-end cognitive video pipeline."""

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


def ensure_config(topic_id: str) -> Path:
    work_dir = DEFAULT_OUTPUT_ROOT / slugify(topic_id)
    work_dir.mkdir(parents=True, exist_ok=True)
    config_path = work_dir / "config.json"
    if not config_path.exists():
        shutil.copy2(ROOT / "config.template.json", config_path)
        config = load_json(config_path)
        config["topic_id"] = topic_id
        save_json(config_path, config)
    return config_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run cognitive video pipeline.")
    parser.add_argument("--config", default="")
    parser.add_argument("--id", default="middle-class-exit")
    parser.add_argument("--url", default="https://v.douyin.com/A3HUZVm7ZgM/")
    parser.add_argument("--skip-analyze", action="store_true")
    parser.add_argument("--use-whisper-align", action="store_true")
    parser.add_argument("--skip-script", action="store_true")
    parser.add_argument("--skip-voice", action="store_true")
    parser.add_argument("--skip-broll", action="store_true")
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--skip-export", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    config_path = Path(args.config).resolve() if args.config else ensure_config(args.id)
    config = load_json(config_path)
    work_dir = config_path.parent
    topic_id = str(config.get("topic_id", args.id))

    if not args.skip_analyze and not (work_dir / "reference" / "reference_manifest.json").exists():
        run(
            [
                sys.executable,
                str(ROOT / "analyze_reference.py"),
                "--url",
                str(config.get("reference_url", args.url)),
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
        save_json(config_path, config)

    if not args.skip_script:
        run([sys.executable, str(ROOT / "generate_script.py"), "--config", str(config_path)])

    if not args.skip_voice:
        run([sys.executable, str(ROOT / "synthesize_voice.py"), "--config", str(config_path)])

    if args.use_whisper_align and (work_dir / "reference" / "transcript.json").exists():
        run([sys.executable, str(ROOT / "align_whisper.py"), "--config", str(config_path)])

    if not args.skip_broll:
        run([sys.executable, str(ROOT / "fetch_broll.py"), "--config", str(config_path)])

    run([sys.executable, str(ROOT / "build_storyboard.py"), "--config", str(config_path)])

    storyboard_path = work_dir / "storyboard.json"
    output_path = (
        Path(args.output).resolve()
        if args.output
        else (work_dir / "output" / "final.mp4")
    )

    if not args.skip_render:
        remotion_dir = ROOT / "remotion"
        if not (remotion_dir / "node_modules").exists():
            run(["npm", "install"], cwd=remotion_dir)

        output_path.parent.mkdir(parents=True, exist_ok=True)
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

    if not args.skip_export:
        run([sys.executable, str(ROOT / "export_douyin.py"), "--config", str(config_path)])

    save_json(
        work_dir / "pipeline-result.json",
        {
            "config": str(config_path.relative_to(PROJECT_ROOT)),
            "storyboard": str(storyboard_path.relative_to(PROJECT_ROOT)),
            "output": str(output_path.relative_to(PROJECT_ROOT)) if not args.skip_render else "",
        },
    )
    print(f"Pipeline complete: {work_dir}")


if __name__ == "__main__":
    main()
