#!/usr/bin/env python3
"""Download royalty-free online clips and build clip_manifest.json."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLIPS_DIR = ROOT / "clips"
DEFAULT_SOURCES = ROOT / "online_sources.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch online stock clips into clips/ library.")
    parser.add_argument("--sources", default=str(DEFAULT_SOURCES), help="online_sources.json path")
    parser.add_argument("--manifest", default=str(ROOT / "clip_manifest.json"), help="Output manifest path")
    parser.add_argument("--force", action="store_true", help="Re-download even if file exists")
    return parser.parse_args()


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("curl"):
        subprocess.run(["curl", "-fsSL", "-o", str(dest), url], check=True)
        return

    with urllib.request.urlopen(url, timeout=120) as response, dest.open("wb") as handle:
        handle.write(response.read())


def _download_with_ytdlp(url: str, dest: Path) -> None:
    if not shutil.which("yt-dlp"):
        raise RuntimeError("yt-dlp not found; install with: brew install yt-dlp")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp.mp4")
    subprocess.run(
        [
            "yt-dlp",
            "-f",
            "best[ext=mp4]/best",
            "-o",
            str(tmp),
            url,
        ],
        check=True,
    )
    tmp.replace(dest)


def _normalize_to_vertical(src: Path, dest: Path) -> None:
    """Scale/crop to 1080x1920 for consistent montage rendering."""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-vf",
            "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            str(dest),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def fetch_clips(sources_path: Path, manifest_path: Path, force: bool) -> list[dict]:
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    manifest: list[dict] = []

    for entry in sources.get("clips", []):
        clip_id = entry["id"]
        clip_type = entry["type"]
        rel_path = f"{clip_type}/{clip_id}.mp4"
        dest = CLIPS_DIR / rel_path
        raw_dest = dest.with_suffix(".raw.mp4")

        if dest.exists() and not force:
            print(f"Skip existing: {dest.name}")
        else:
            url = entry["url"]
            print(f"Downloading {clip_id} ...")
            try:
                if "mixkit.co/videos/" in url or url.endswith(".mp4"):
                    _download(url, raw_dest)
                else:
                    _download_with_ytdlp(url, raw_dest)
            except Exception as exc:
                raise RuntimeError(f"Failed to download {clip_id} from {url}: {exc}") from exc

            _normalize_to_vertical(raw_dest, dest)
            raw_dest.unlink(missing_ok=True)
            print(f"Saved {dest}")

        duration = _probe_duration(dest)
        trim_in = float(entry.get("trim_in", 0.0))
        trim_in = min(trim_in, max(0.0, duration - 0.5))

        manifest.append(
            {
                "id": clip_id,
                "path": rel_path,
                "type": clip_type,
                "energy": entry.get("energy", 5),
                "tags": entry.get("tags", []),
                "trim_in": round(trim_in, 2),
                "duration_hint": entry.get("duration_hint", 1.5),
                "source_url": entry.get("url", ""),
                "source_duration": round(duration, 2),
            }
        )

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved manifest ({len(manifest)} clips): {manifest_path}")
    return manifest


def main() -> None:
    args = parse_args()
    manifest_path = Path(args.manifest).resolve()
    fetch_clips(Path(args.sources).resolve(), manifest_path, args.force)

    analyze_script = ROOT / "analyze_clip_actions.py"
    if analyze_script.exists():
        subprocess.run(
            [sys.executable, str(analyze_script), "--manifest", str(manifest_path)],
            check=True,
        )


if __name__ == "__main__":
    main()
