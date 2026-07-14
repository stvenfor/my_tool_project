#!/usr/bin/env python3
"""End-to-end viral english dub pipeline."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent

sys.path.insert(0, str(ROOT))

from lib import DEFAULT_OUTPUT_ROOT, ensure_config, load_json, save_json, slugify  # noqa: E402


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("$", " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd or PROJECT_ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run viral english dub pipeline.")
    parser.add_argument("--config", default="")
    parser.add_argument("--id", default="demo-clip")
    parser.add_argument("--input", default="", help="Target mp4 path (alias of --target-input)")
    parser.add_argument("--target-input", default="", help="Target mp4 to dub")
    parser.add_argument("--voice-ref-input", default="", help="Optional voice reference mp4 (read-only)")
    parser.add_argument("--url", default="", help="Douyin URL")
    parser.add_argument("--skip-analyze", action="store_true")
    parser.add_argument("--skip-diarize", action="store_true")
    parser.add_argument("--skip-translate", action="store_true")
    parser.add_argument("--skip-voice", action="store_true")
    parser.add_argument("--skip-align", action="store_true")
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    if args.config:
        config_path = Path(args.config).resolve()
        work_dir = config_path.parent
    else:
        clip_id = slugify(args.id)
        work_dir = DEFAULT_OUTPUT_ROOT / clip_id
        work_dir.mkdir(parents=True, exist_ok=True)
        config_path = ensure_config(work_dir, clip_id)
        if args.input or args.target_input:
            config = load_json(config_path)
            target = args.target_input or args.input
            config["target_input"] = str(Path(target).expanduser())
            if args.voice_ref_input:
                config["voice_reference_input"] = str(Path(args.voice_ref_input).expanduser())
            save_json(config_path, config)

    config = load_json(config_path)
    target_arg = args.target_input or args.input

    if not args.skip_analyze and not (work_dir / "reference" / "transcript.json").exists():
        analyze_cmd = [sys.executable, str(ROOT / "analyze_reference.py"), "--config", str(config_path)]
        if target_arg:
            analyze_cmd.extend(["--input", target_arg])
        if args.url:
            analyze_cmd.extend(["--url", args.url])
        run(analyze_cmd)
        config = load_json(config_path)

    if config.get("keep_bgm", True) and config.get("use_vocal_stem_for_prompts", True):
        bgm_meta_path = work_dir / "reference" / "bgm_separation.json"
        if not bgm_meta_path.exists():
            run([sys.executable, str(ROOT / "separate_bgm.py"), "--config", str(config_path)])

    if not args.skip_diarize:
        run([sys.executable, str(ROOT / "diarize_speakers.py"), "--config", str(config_path)])

    if not args.skip_translate:
        run([sys.executable, str(ROOT / "translate_script.py"), "--config", str(config_path)])

    if not args.skip_voice:
        run([sys.executable, str(ROOT / "synthesize_voice.py"), "--config", str(config_path)])

    if not args.skip_align:
        run([sys.executable, str(ROOT / "align_audio.py"), "--config", str(config_path)])

    if config.get("keep_bgm", True):
        run([sys.executable, str(ROOT / "separate_bgm.py"), "--config", str(config_path)])
        run([sys.executable, str(ROOT / "mix_audio.py"), "--config", str(config_path)])

    run([sys.executable, str(ROOT / "build_storyboard.py"), "--config", str(config_path)])

    storyboard_path = work_dir / "storyboard.json"
    output_path = Path(args.output).resolve() if args.output else (work_dir / "final.mp4")

    if not args.skip_render:
        if config.get("show_subtitles", True):
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
        elif config.get("video_passthrough", False):
            run([sys.executable, str(ROOT / "mux_final.py"), "--config", str(config_path)])
        else:
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

    run([sys.executable, str(ROOT / "export_douyin.py"), "--config", str(config_path)])

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
