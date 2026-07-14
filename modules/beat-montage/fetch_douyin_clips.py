#!/usr/bin/env python3
"""Build clip library from Douyin videos: download -> beat-slice -> manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent
DEFAULT_SOURCES = ROOT / "douyin_sources.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch/slice Douyin clips by beat windows.")
    parser.add_argument("--sources", default=str(DEFAULT_SOURCES))
    parser.add_argument("--from-discovery", default="", help="discovered_urls.{stem}.json")
    parser.add_argument("--cut-grid", default="", help="cut_grid.{stem}.json for beat slicing")
    parser.add_argument("--manifest", default=str(ROOT / "clip_manifest.json"))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--download-delay", type=float, default=3.0)
    parser.add_argument("--min-downloads", type=int, default=8)
    parser.add_argument("--playwright-first", action="store_true", default=True)
    return parser.parse_args()


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    print("$", " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd or PROJECT_ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def _resolve_local(path_str: str) -> Path:
    path = Path(path_str)
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return path


def _is_video_share_url(url: str) -> bool:
    if "/music/" in url:
        return False
    try:
        request = urllib.request.Request(
            url,
            method="GET",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            final_url = response.geturl()
        if "/music/" in final_url:
            return False
        return "/video/" in final_url or "v.douyin.com" in url
    except Exception as exc:
        print(f"URL validate skip ({url}): {exc}", file=sys.stderr)
        return "v.douyin.com" in url and "/music/" not in url


def _download_playwright(url: str, output: Path) -> bool:
    pw_script = PROJECT_ROOT / "scripts" / "cffex-daily" / "douyin" / "download-for-montage.mjs"
    if not pw_script.exists():
        return False
    result = subprocess.run(
        ["node", str(pw_script), "--url", url, "--output", str(output)],
        cwd=str(pw_script.parent),
    )
    return result.returncode == 0 and output.exists() and output.stat().st_size > 10000


def _download_ytdlp(url: str, output: Path, cookies_from_browser: str) -> bool:
    cmd = ["yt-dlp", "-f", "best[ext=mp4]/best", "-o", str(output), url]
    if cookies_from_browser:
        cmd[1:1] = ["--cookies-from-browser", cookies_from_browser]
    result = subprocess.run(cmd)
    return result.returncode == 0 and output.exists() and output.stat().st_size > 10000


def _download_one(
    url: str,
    output: Path,
    cookies_from_browser: str,
    force: bool,
    playwright_first: bool,
) -> bool:
    if output.exists() and not force:
        return True

    print(f"Downloading Douyin URL: {url}")
    for attempt in range(2):
        ok = False
        if playwright_first:
            ok = _download_playwright(url, output)
            if not ok:
                ok = _download_ytdlp(url, output, cookies_from_browser)
        else:
            ok = _download_ytdlp(url, output, cookies_from_browser)
            if not ok:
                ok = _download_playwright(url, output)
        if ok:
            return True
        if attempt == 0:
            print(f"Retry download: {url}", file=sys.stderr)
            time.sleep(2.0)

    print(f"Warning: failed to download {url}", file=sys.stderr)
    return False


def _download_urls(
    urls: list[str],
    cookies_from_browser: str,
    dest_dir: Path,
    force: bool,
    download_delay: float,
    playwright_first: bool,
    min_downloads: int,
) -> list[Path]:
    downloaded: list[Path] = []
    dest_dir.mkdir(parents=True, exist_ok=True)

    filtered = list(dict.fromkeys(url for url in urls if _is_video_share_url(url)))
    skipped = len(urls) - len(filtered)
    if skipped:
        print(f"Filtered {skipped} duplicate/non-video URLs")

    min_required = min(min_downloads, max(2, len(filtered)))
    if len(filtered) < min_downloads:
        print(
            f"Warning: only {len(filtered)} unique video URLs (want {min_downloads}). "
            f"Proceeding with min_required={min_required}.",
            file=sys.stderr,
        )

    for index, url in enumerate(filtered):
        output = dest_dir / f"douyin_url_{index:02d}.mp4"
        if _download_one(url, output, cookies_from_browser, force, playwright_first):
            if output.exists():
                downloaded.append(output)
        if index < len(filtered) - 1:
            time.sleep(download_delay)

    unique_paths: list[Path] = []
    seen_hashes: set[str] = set()
    for path in downloaded:
        digest = hashlib.md5(path.read_bytes()[:500000]).hexdigest()
        if digest in seen_hashes:
            print(f"Skip duplicate content: {path.name}")
            continue
        seen_hashes.add(digest)
        unique_paths.append(path)

    if len(unique_paths) < min_required:
        raise SystemExit(
            f"Only {len(unique_paths)} unique videos downloaded (need {min_required}). "
            "Add more video share URLs to douyin_sources.json."
        )

    return unique_paths


def main() -> None:
    args = parse_args()
    sources_path = Path(args.sources).resolve()
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    manifest_path = Path(args.manifest).resolve()

    urls: list[str] = list(sources.get("urls", []))
    if args.from_discovery:
        discovery_path = Path(args.from_discovery).resolve()
        if not discovery_path.exists():
            raise SystemExit(f"Discovery file not found: {discovery_path}")
        discovery = json.loads(discovery_path.read_text(encoding="utf-8"))
        urls = discovery.get("urls", urls)

    cookies = sources.get("cookies_from_browser") or "chrome"
    local_paths = [_resolve_local(item) for item in sources.get("local_videos", [])]
    for path in local_paths:
        if not path.exists():
            raise SystemExit(f"Local Douyin video not found: {path}")

    url_paths = _download_urls(
        urls,
        cookies,
        ROOT / "clips" / "_downloads",
        args.force,
        args.download_delay,
        args.playwright_first,
        args.min_downloads,
    )

    video_paths = local_paths + url_paths

    cut_grid_path = Path(args.cut_grid).resolve() if args.cut_grid else None
    if not cut_grid_path or not cut_grid_path.exists():
        raise SystemExit("--cut-grid is required for beat-based slicing")

    slice_cmd = [
        sys.executable,
        str(ROOT / "slice_by_beats.py"),
        *[str(path) for path in video_paths],
        "--cut-grid",
        str(cut_grid_path),
        "--manifest",
        str(manifest_path),
    ]
    if args.force:
        slice_cmd.append("--force")
    _run(slice_cmd)


if __name__ == "__main__":
    main()
