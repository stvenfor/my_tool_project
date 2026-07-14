#!/usr/bin/env python3
"""Search, download, and slice Douyin B-roll for city bilingual videos."""

from __future__ import annotations

import hashlib
import importlib.util
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent
DOUYIN_DOWNLOADER = PROJECT_ROOT / "modules" / "shared" / "douyin" / "download_douyin_ref.mjs"
DOUYIN_URL_RE = re.compile(
    r"https?://v\.douyin\.com/[A-Za-z0-9_\-]+/?|https?://www\.douyin\.com/video/\d+"
)


def _load_slice_module():
    beat_root = PROJECT_ROOT / "modules" / "shared" / "media"
    sys.path.insert(0, str(beat_root))
    module_path = beat_root / "slice_douyin_video.py"
    spec = importlib.util.spec_from_file_location("slice_douyin_video", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _search_douyin_urls(keyword: str, max_results: int = 4) -> list[str]:
    query = f"site:v.douyin.com {keyword}"
    urls: list[str] = []
    for base in ("https://html.duckduckgo.com/html/?", "https://www.bing.com/search?"):
        try:
            req = urllib.request.Request(
                base + urllib.parse.urlencode({"q": query}),
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            )
            html = urllib.request.urlopen(req, timeout=12).read().decode("utf-8", errors="ignore")
            for match in DOUYIN_URL_RE.finditer(html):
                link = match.group(0).rstrip("/")
                if "/music/" in link:
                    continue
                if link not in urls:
                    urls.append(link)
                if len(urls) >= max_results:
                    return urls
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"Search failed ({keyword}): {exc}")
        time.sleep(0.6)
    return urls


def _download_playwright(url: str, output: Path) -> bool:
    if not DOUYIN_DOWNLOADER.exists():
        return False
    result = subprocess.run(
        ["node", str(DOUYIN_DOWNLOADER), "--url", url, "--output", str(output)],
        cwd=DOUYIN_DOWNLOADER.parent,
    )
    return result.returncode == 0 and output.exists() and output.stat().st_size > 10000


def _download_ytdlp(url: str, output: Path, browser: str = "chrome") -> bool:
    cmd = [
        "yt-dlp",
        "--cookies-from-browser",
        browser,
        "-f",
        "best[ext=mp4]/best",
        "-o",
        str(output),
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0 and output.exists() and output.stat().st_size > 10000


def download_url(url: str, output: Path, browser: str = "chrome") -> bool:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.stat().st_size > 10000:
        return True
    print(f"Downloading B-roll: {url}")
    if _download_playwright(url, output):
        return True
    return _download_ytdlp(url, output, browser)


def discover_phase_urls(sources: dict[str, Any], phase: str) -> list[str]:
    urls: list[str] = []
    seeds = sources.get("seed_urls", {}).get(phase, [])
    for url in seeds:
        if url not in urls:
            urls.append(url)

    for keyword in sources.get("search_keywords", {}).get(phase, []):
        for link in _search_douyin_urls(keyword, max_results=3):
            if link not in urls:
                urls.append(link)
        if len(urls) >= 6:
            break
    return urls


def download_phase_pool(
    sources: dict[str, Any],
    work_dir: Path,
    phase: str,
    force: bool = False,
) -> list[Path]:
    urls = discover_phase_urls(sources, phase)
    browser = sources.get("cookies_from_browser", "chrome")
    delay = float(sources.get("download_delay_sec", 2.5))
    dest_dir = work_dir / "broll" / "downloads" / phase
    dest_dir.mkdir(parents=True, exist_ok=True)

    downloaded: list[Path] = []
    for index, url in enumerate(urls):
        output = dest_dir / f"{phase}_{index:02d}.mp4"
        if not force and output.exists() and output.stat().st_size > 10000:
            downloaded.append(output)
            continue
        if download_url(url, output, browser):
            digest = hashlib.md5(output.read_bytes()[:300000]).hexdigest()
            if any(hashlib.md5(p.read_bytes()[:300000]).hexdigest() == digest for p in downloaded):
                print(f"Skip duplicate download: {output.name}")
                output.unlink(missing_ok=True)
            else:
                downloaded.append(output)
        if index < len(urls) - 1:
            time.sleep(delay)

    min_required = int(sources.get("min_videos_per_phase", 1))
    if len(downloaded) < min_required:
        print(f"Warning: phase={phase} only got {len(downloaded)} videos (want {min_required})")
    return downloaded


def build_segment_pool(
    video_paths: list[Path],
    pool_dir: Path,
    phase: str,
    scene_threshold: float = 0.28,
    min_duration: float = 0.35,
    max_duration: float = 3.0,
) -> list[dict[str, Any]]:
    slice_mod = _load_slice_module()
    pool_dir.mkdir(parents=True, exist_ok=True)
    segments: list[dict[str, Any]] = []

    for video_path in video_paths:
        if not video_path.exists():
            continue
        scene_times = slice_mod._detect_scene_times(video_path, scene_threshold)
        ranges = slice_mod._build_segments(scene_times, min_duration, max_duration)
        for seg_index, (start, end) in enumerate(ranges):
            duration = round(end - start, 3)
            clip_id = f"{phase}_{video_path.stem}_{seg_index:03d}"
            dest = pool_dir / f"{clip_id}.mp4"
            if not dest.exists():
                slice_mod._normalize_segment(video_path, dest, start, duration)
            segments.append(
                {
                    "id": clip_id,
                    "phase": phase,
                    "path": dest,
                    "duration_sec": duration,
                    "source_video": str(video_path),
                    "source_range": [start, end],
                }
            )
    return segments


def _fit_segment_to_duration(
    src: Path,
    dest: Path,
    target_duration: float,
    width: int,
    height: int,
) -> None:
    slice_mod = _load_slice_module()
    src_duration = slice_mod._probe_duration(src)
    if src_duration <= target_duration + 0.05:
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={width}:{height},setsar=1,"
            f"eq=contrast=1.06:brightness=0.02:saturation=1.05,"
            f"fps=30,format=yuv420p"
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(src),
                "-vf",
                vf,
                "-t",
                str(target_duration),
                "-an",
                "-c:v",
                "libx264",
                "-crf",
                "17",
                "-preset",
                "medium",
                "-pix_fmt",
                "yuv420p",
                str(dest),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return

    start = max(0.0, (src_duration - target_duration) / 2)
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width}:{height},setsar=1,"
        f"eq=contrast=1.06:brightness=0.02:saturation=1.05,"
        f"fps=30,format=yuv420p"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(src),
            "-t",
            f"{target_duration:.3f}",
            "-vf",
            vf,
            "-an",
            "-c:v",
            "libx264",
            "-crf",
            "17",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            str(dest),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _keyword_slug(keyword: str) -> str:
    digest = hashlib.md5(keyword.encode("utf-8")).hexdigest()[:10]
    safe = re.sub(r"[^\w\u4e00-\u9fff]+", "_", keyword.strip())[:24]
    return f"{safe}_{digest}"


def discover_keyword_urls(keyword: str, sources: dict[str, Any], phase: str = "day") -> list[str]:
    urls: list[str] = []
    landmark_urls = sources.get("landmark_urls", {})
    for landmark, links in landmark_urls.items():
        if landmark and landmark in keyword:
            for link in links:
                if link not in urls:
                    urls.append(link)

    for link in _search_douyin_urls(keyword, max_results=4):
        if link not in urls:
            urls.append(link)

    for link in discover_phase_urls(sources, phase):
        if link not in urls:
            urls.append(link)
        if len(urls) >= 8:
            break
    return urls


def _is_valid_video(path: Path, min_bytes: int = 100_000) -> bool:
    if not path.exists() or path.stat().st_size < min_bytes:
        return False
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    try:
        return float(result.stdout.strip()) > 0.3
    except ValueError:
        return False


def download_keyword_video(
    keyword: str,
    work_dir: Path,
    sources: dict[str, Any],
    phase: str = "day",
    force: bool = False,
) -> Path | None:
    slug = _keyword_slug(keyword)
    dest_dir = work_dir / "broll" / "keywords"
    dest_dir.mkdir(parents=True, exist_ok=True)
    output = dest_dir / f"{slug}.mp4"
    if not force and _is_valid_video(output):
        return output

    browser = sources.get("cookies_from_browser", "chrome")
    delay = float(sources.get("download_delay_sec", 2.5))
    urls = discover_keyword_urls(keyword, sources, phase)
    for index, url in enumerate(urls):
        tmp = dest_dir / f"{slug}_{index:02d}.mp4"
        if download_url(url, tmp, browser) and _is_valid_video(tmp):
            output.unlink(missing_ok=True)
            tmp.replace(output)
            print(f"Keyword B-roll [{keyword}]: {output.name}")
            return output
        tmp.unlink(missing_ok=True)
        if index < len(urls) - 1:
            time.sleep(delay)
    return output if _is_valid_video(output) else None


def _best_segment_for_shot(
    video_path: Path,
    shot_id: str,
    phase: str,
    work_dir: Path,
) -> Path:
    if not _is_valid_video(video_path):
        raise RuntimeError(f"Invalid keyword video: {video_path}")
    try:
        pool_dir = work_dir / "broll" / "pool" / "keyword" / shot_id
        segments = build_segment_pool([video_path], pool_dir, phase)
        if segments:
            return max(segments, key=lambda item: float(item["duration_sec"]))["path"]
    except Exception as exc:
        print(f"Scene split fallback for {shot_id}: {exc}")
    return video_path


def assign_broll_by_keywords(
    shots: list[dict[str, Any]],
    work_dir: Path,
    sources: dict[str, Any],
    width: int,
    height: int,
    force: bool = False,
) -> list[dict[str, Any]]:
    keyword_cache: dict[str, Path] = {}
    phase_pools: dict[str, list[dict[str, Any]]] | None = None
    phase_cursors: dict[str, int] = {}
    clips: list[dict[str, Any]] = []

    def _phase_pools() -> dict[str, list[dict[str, Any]]]:
        nonlocal phase_pools, phase_cursors
        if phase_pools is None:
            phase_pools = prepare_broll_pools(sources, work_dir, force=force)
            phase_cursors = {phase: 0 for phase in phase_pools}
        return phase_pools

    for shot in shots:
        keyword = str(shot.get("douyin_keyword") or shot.get("visual_keyword") or "").strip()
        phase = str(shot.get("phase", "day"))
        clip_path = work_dir / shot["clip"]
        clip_path.parent.mkdir(parents=True, exist_ok=True)

        source_video = ""
        segment_path: Path | None = None

        if keyword:
            if keyword not in keyword_cache or force:
                cached = download_keyword_video(keyword, work_dir, sources, phase=phase, force=force)
                if cached:
                    keyword_cache[keyword] = cached
            cached_video = keyword_cache.get(keyword)
            if cached_video:
                segment_path = _best_segment_for_shot(cached_video, shot["id"], phase, work_dir)
                source_video = str(cached_video)

        if segment_path is None:
            pools = _phase_pools()
            pool = pools.get(phase) or pools.get("day") or next(iter(pools.values()), [])
            if pool:
                cursor = phase_cursors.get(phase, 0)
                entry = pool[cursor % len(pool)]
                segment_path = entry["path"]
                source_video = entry.get("source_video", "")
                phase_cursors[phase] = cursor + 1

        if segment_path is None:
            raise RuntimeError(f"No B-roll for shot {shot['id']} keyword={keyword}")

        _fit_segment_to_duration(
            segment_path,
            clip_path,
            float(shot["duration_sec"]),
            width,
            height,
        )

        clips.append(
            {
                "id": shot["id"],
                "clip": shot["clip"],
                "is_image": False,
                "duration_sec": float(shot["duration_sec"]),
                "phase": phase,
                "source": "douyin_keyword" if keyword in keyword_cache else "douyin_broll",
                "douyin_keyword": keyword,
                "landmark": shot.get("landmark", ""),
                "zh": shot.get("zh", ""),
                "segment_index": shot.get("segment_index"),
                "broll_source_video": source_video,
            }
        )
        print(f"  {shot['id']} <- [{shot.get('landmark', keyword)}] {keyword}")
    return clips


def assign_broll_to_shots(
    shots: list[dict[str, Any]],
    pools: dict[str, list[dict[str, Any]]],
    work_dir: Path,
    width: int,
    height: int,
) -> list[dict[str, Any]]:
    cursors = {phase: 0 for phase in pools}
    clips: list[dict[str, Any]] = []

    for shot in shots:
        phase = shot.get("phase", "day")
        pool = pools.get(phase) or pools.get("day") or next(iter(pools.values()), [])
        if not pool:
            raise RuntimeError(f"No B-roll pool for phase={phase}")

        cursor = cursors.get(phase, 0)
        segment = pool[cursor % len(pool)]
        cursors[phase] = cursor + 1

        clip_path = work_dir / shot["clip"]
        clip_path.parent.mkdir(parents=True, exist_ok=True)
        _fit_segment_to_duration(
            segment["path"],
            clip_path,
            float(shot["duration_sec"]),
            width,
            height,
        )

        clips.append(
            {
                "id": shot["id"],
                "clip": shot["clip"],
                "is_image": False,
                "duration_sec": float(shot["duration_sec"]),
                "phase": phase,
                "source": "douyin_broll",
                "douyin_keyword": shot.get("douyin_keyword", ""),
                "broll_segment": segment["id"],
                "broll_source_video": segment.get("source_video", ""),
            }
        )
    return clips


def prepare_broll_pools(sources: dict[str, Any], work_dir: Path, force: bool = False) -> dict[str, list[dict[str, Any]]]:
    pools: dict[str, list[dict[str, Any]]] = {}
    for phase in ("day", "transition", "night"):
        videos = download_phase_pool(sources, work_dir, phase, force=force)
        if not videos:
            continue
        pool_dir = work_dir / "broll" / "pool" / phase
        segments = build_segment_pool(videos, pool_dir, phase)
        if segments:
            pools[phase] = segments
            print(f"B-roll pool {phase}: {len(segments)} segments from {len(videos)} videos")
    return pools
