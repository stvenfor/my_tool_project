#!/usr/bin/env python3
"""Batch run cognitive video pipeline for approved topics."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent
TOPICS_DIR = ROOT / "topics"
sys.path.insert(0, str(ROOT))
from lib import DEFAULT_OUTPUT_ROOT  # noqa: E402


def _run_pipeline(config_path: Path, skip_render: bool = False) -> int:
    cmd = [
        sys.executable,
        str(ROOT / "run_pipeline.py"),
        "--config",
        str(config_path),
    ]
    if skip_render:
        cmd.append("--skip-render")
    print("$", " ".join(cmd))
    return subprocess.run(cmd, cwd=PROJECT_ROOT).returncode


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch cognitive video pipeline.")
    parser.add_argument("--id", default="", help="Single topic id")
    parser.add_argument("--all", action="store_true", help="Run all approved topics")
    parser.add_argument("--skip-render", action="store_true")
    args = parser.parse_args()

    if args.id:
        config_path = DEFAULT_OUTPUT_ROOT / args.id / "config.json"
        if not config_path.exists():
            raise SystemExit(f"Missing config: {config_path}")
        raise SystemExit(_run_pipeline(config_path, skip_render=args.skip_render))

    if not args.all:
        raise SystemExit("Pass --id <topic> or --all")

    approved_dir = TOPICS_DIR / "approved"
    if not approved_dir.exists():
        raise SystemExit(f"No approved topics: {approved_dir}")

    configs = sorted(approved_dir.glob("*/config.json"))
    if not configs:
        raise SystemExit("No approved topic configs found")

    failures = 0
    for config_path in configs:
        print(f"\n=== {config_path.parent.name} ===")
        if _run_pipeline(config_path, skip_render=args.skip_render) != 0:
            failures += 1

    if failures:
        raise SystemExit(f"{failures} topic(s) failed")
    print(f"Batch complete: {len(configs)} topics")


if __name__ == "__main__":
    main()
