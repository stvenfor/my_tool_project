#!/usr/bin/env python3
"""Download diverse web clips (Mixkit + optional Douyin URLs) for beat-sync montage."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent
DEFAULT_SOURCES = ROOT / "web_clips_sources.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch diverse web clips into clip library.")
    parser.add_argument("--sources", default=str(DEFAULT_SOURCES))
    parser.add_argument("--manifest", default=str(ROOT / "clip_manifest.json"))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--try-douyin", action="store_true", help="Also try downloading douyin_urls")
    return parser.parse_args()


def _run(cmd: list[str]) -> None:
    print("$", " ".join(cmd))
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def _try_douyin(urls: list[str], cookies: str, force: bool) -> None:
    if not urls:
        return
    dest_dir = ROOT / "clips" / "_downloads"
    dest_dir.mkdir(parents=True, exist_ok=True)
    for index, url in enumerate(urls):
        output = dest_dir / f"douyin_{index:02d}.mp4"
        if output.exists() and not force:
            continue
        cmd = ["yt-dlp", "-f", "best[ext=mp4]/best", "-o", str(output), url]
        if cookies:
            cmd[1:1] = ["--cookies-from-browser", cookies]
        print(f"Trying Douyin: {url}")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"Douyin skip (need login cookies): {url}", file=sys.stderr)


def main() -> None:
    args = parse_args()
    sources_path = Path(args.sources).resolve()
    sources = json.loads(sources_path.read_text(encoding="utf-8"))

    if args.try_douyin:
        _try_douyin(sources.get("douyin_urls", []), sources.get("cookies_from_browser", "chrome"), args.force)

    _run(
        [
            sys.executable,
            str(ROOT / "fetch_online_clips.py"),
            "--sources",
            str(sources_path),
            "--manifest",
            str(Path(args.manifest).resolve()),
            *(["--force"] if args.force else []),
        ]
    )


if __name__ == "__main__":
    main()
