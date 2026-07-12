#!/usr/bin/env python3
"""Batch run video-factory pipeline for approved topics."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent
TOPICS_DIR = ROOT / "topics"


def _run_pipeline(project_id: str, skip_render: bool = False, force: bool = False) -> int:
    work_dir = PROJECT_ROOT / "_video-factory" / project_id
    final_mp4 = work_dir / "output" / "final.mp4"
    if final_mp4.exists() and not force:
        print(f"Skip {project_id}: output exists (use --force)")
        return 0

    cmd = [
        sys.executable,
        str(ROOT / "run_pipeline.py"),
        "--id",
        project_id,
        "--init",
    ]
    if skip_render:
        cmd.append("--skip-render")
    print("$", " ".join(cmd))
    return subprocess.run(cmd, cwd=PROJECT_ROOT).returncode


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch video-factory pipeline.")
    parser.add_argument("--id", default="", help="Single project id")
    parser.add_argument("--all", action="store_true", help="Run all approved topics")
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.id:
        raise SystemExit(_run_pipeline(args.id, skip_render=args.skip_render, force=args.force))

    if not args.all:
        raise SystemExit("Pass --id <project> or --all")

    approved_dir = TOPICS_DIR / "approved"
    if not approved_dir.exists():
        raise SystemExit(f"No approved topics: {approved_dir}")

    topic_files = sorted(approved_dir.glob("*.json"))
    if not topic_files:
        raise SystemExit("No approved topic configs found")

    failures = 0
    for topic_file in topic_files:
        project_id = topic_file.stem
        print(f"\n=== {project_id} ===")
        if _run_pipeline(project_id, skip_render=args.skip_render, force=args.force) != 0:
            failures += 1

    if failures:
        raise SystemExit(f"{failures} project(s) failed")
    print(f"Batch complete: {len(topic_files)} projects")


if __name__ == "__main__":
    main()
