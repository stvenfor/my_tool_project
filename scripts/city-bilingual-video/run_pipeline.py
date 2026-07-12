#!/usr/bin/env python3
"""End-to-end city-bilingual video pipeline."""

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


def ensure_demo_config(city: str = "西安") -> Path:
    demo_dir = DEFAULT_OUTPUT_ROOT / slugify(city)
    demo_dir.mkdir(parents=True, exist_ok=True)
    demo_config = demo_dir / "city.config.json"
    if not demo_config.exists():
        shutil.copy2(ROOT / "config.template.json", demo_config)
    return demo_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Run city-bilingual video pipeline.")
    parser.add_argument("--config", default="")
    parser.add_argument("--url", default="https://v.douyin.com/iJCRT9D993w/")
    parser.add_argument("--city", default="西安")
    parser.add_argument("--skip-analyze", action="store_true")
    parser.add_argument("--skip-script", action="store_true")
    parser.add_argument("--skip-assets", action="store_true")
    parser.add_argument("--skip-voice", action="store_true")
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    config_path = Path(args.config).resolve() if args.config else ensure_demo_config(args.city)
    config = load_json(config_path)
    work_dir = config_path.parent

    if not args.skip_analyze and not (work_dir / "reference" / "reference_manifest.json").exists():
        run(
            [
                sys.executable,
                str(ROOT / "analyze_reference.py"),
                "--url",
                str(config.get("reference_url", args.url)),
                "--city",
                str(config.get("city_name", args.city)),
                "--caption",
                str(config.get("hook_zh", "")),
                "--work-dir",
                str(work_dir),
            ]
        )
        manifest = load_json(work_dir / "reference" / "reference_manifest.json")
        config["duration_sec"] = manifest.get("duration_sec", config.get("duration_sec", 51.233))
        save_json(config_path, config)

    if not args.skip_script:
        run([sys.executable, str(ROOT / "generate_script.py"), "--config", str(config_path)])

    if not args.skip_voice:
        run([sys.executable, str(ROOT / "synthesize_voice.py"), "--config", str(config_path)])

    if not args.skip_assets:
        cut_mode = str(config.get("cut_mode", "reference_cuts"))
        if cut_mode == "narration_sync":
            run([sys.executable, str(ROOT / "map_narration_shots.py"), "--config", str(config_path)])
        else:
            run([sys.executable, str(ROOT / "map_reference_shots.py"), "--config", str(config_path)])
        run([sys.executable, str(ROOT / "fetch_city_clips.py"), "--config", str(config_path)])
        run([sys.executable, str(ROOT / "postprocess_clips.py"), "--config", str(config_path)])

    elif not args.skip_voice:
        cut_mode = str(config.get("cut_mode", "reference_cuts"))
        if cut_mode == "narration_sync":
            run([sys.executable, str(ROOT / "map_narration_shots.py"), "--config", str(config_path)])

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
