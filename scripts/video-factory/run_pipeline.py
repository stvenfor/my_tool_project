#!/usr/bin/env python3
"""End-to-end video-factory pipeline orchestrator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from init_project import init_from_topic  # noqa: E402
from lib import load_project_config, project_work_dir, save_json, write_project_config  # noqa: E402
from modes.dialogue import run_dialogue_pipeline  # noqa: E402
from modes.narration import run_narration_pipeline  # noqa: E402
from modes.talking_head import run_talking_head_pipeline  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run video-factory pipeline.")
    parser.add_argument("--id", default="", help="Project id")
    parser.add_argument("--config", default="", help="Path to project.config.json")
    parser.add_argument("--init", action="store_true", help="Init project from approved topic first")
    parser.add_argument("--skip-analyze", action="store_true")
    parser.add_argument("--skip-script", action="store_true")
    parser.add_argument("--skip-voice", action="store_true")
    parser.add_argument("--skip-broll", action="store_true")
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--skip-export", action="store_true")
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    if args.init and args.id:
        init_from_topic(args.id)

    if args.config:
        config_path = Path(args.config).resolve()
        work_dir = config_path.parent
        config = load_project_config(work_dir)
    elif args.id:
        work_dir = project_work_dir(args.id)
        if not (work_dir / "project.config.json").exists() and not (work_dir / "config.json").exists():
            init_from_topic(args.id)
        config = load_project_config(work_dir)
        config_path = work_dir / "project.config.json"
    else:
        raise SystemExit("Pass --id <project> or --config <path>")

    mode = str(config.get("mode", "narration"))
    output_path = Path(args.output).resolve() if args.output else None
    script_source = None
    topic = work_dir / "topic.json"
    if topic.exists():
        from lib import load_json

        topic_data = load_json(topic)
        if topic_data.get("script_source"):
            script_source = Path(str(topic_data["script_source"]))
            if not script_source.is_absolute():
                script_source = ROOT.parent.parent / script_source

    common = {
        "skip_render": args.skip_render,
        "skip_export": args.skip_export,
        "output_path": output_path,
    }

    if mode == "dialogue":
        result = run_dialogue_pipeline(
            config,
            work_dir,
            skip_voice=args.skip_voice,
            skip_render=args.skip_render,
            skip_export=args.skip_export,
            script_source=script_source,
            output_path=output_path,
        )
    elif mode == "talking_head":
        result = run_talking_head_pipeline(
            config,
            work_dir,
            skip_script=args.skip_script,
            skip_voice=args.skip_voice,
            skip_render=args.skip_render,
            skip_export=args.skip_export,
            use_llm=args.llm,
            output_path=output_path,
        )
    else:
        result = run_narration_pipeline(
            config,
            work_dir,
            skip_analyze=args.skip_analyze or bool(config.get("skip_analyze")),
            skip_script=args.skip_script,
            skip_voice=args.skip_voice,
            skip_broll=args.skip_broll,
            skip_render=args.skip_render,
            skip_export=args.skip_export,
            use_llm=args.llm,
            output_path=output_path,
        )

    write_project_config(work_dir, config)
    save_json(work_dir / "pipeline-result.json", result)
    print(f"Pipeline complete [{mode}]: {work_dir}")


if __name__ == "__main__":
    main()
