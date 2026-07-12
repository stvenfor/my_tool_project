#!/usr/bin/env python3
"""Fetch keyword-matched stock B-roll clips for cognitive video segments."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
STOCK_CACHE = ROOT / "stock_cache"
DEFAULT_SOURCES = ROOT / "broll_sources.json"
DEFAULT_STICKMAN = ROOT / "stickman_scenes.json"
sys.path.insert(0, str(ROOT))

from lib import load_json, probe_video, resolve_work_dir, save_json, philosophy_quote_for_segment  # noqa: E402

PHASE_COLORS = {
    "pain": "#2a2438",
    "insight": "#1e2a3a",
    "contrast": "#2d2a24",
    "action": "#1f3028",
    "cta": "#2a2820",
}


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ):
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _score_clip(entry: dict[str, Any], keyword: str, phase: str) -> int:
    score = 0
    if phase in entry.get("phases", []):
        score += 4
    for tag in entry.get("tags", []):
        if tag in keyword:
            score += 3
        if any(ch in keyword for ch in tag if len(tag) >= 2):
            score += 1
    return score


def _pick_stock_clip(
    catalog: list[dict[str, Any]],
    keyword: str,
    phase: str,
    used_ids: set[str],
) -> dict[str, Any]:
    ranked = sorted(
        catalog,
        key=lambda e: (_score_clip(e, keyword, phase), e["id"] not in used_ids),
        reverse=True,
    )
    for entry in ranked:
        if entry["id"] not in used_ids:
            return entry
    return ranked[0]


def _download_stock(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 10000:
        return
    if shutil.which("curl"):
        subprocess.run(["curl", "-fsSL", "-o", str(dest), url], check=True)
        return
    with urllib.request.urlopen(url, timeout=120) as response, dest.open("wb") as handle:
        handle.write(response.read())


def _trim_clip_to_duration(
    source_mp4: Path,
    output_mp4: Path,
    duration_sec: float,
    trim_in: float,
    width: int,
    height: int,
    fps: int,
) -> None:
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    meta = probe_video(source_mp4)
    source_dur = float(meta.get("duration_sec", duration_sec + trim_in + 1))
    max_take = max(1.5, min(duration_sec + 0.5, source_dur - trim_in - 0.2))
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"zoompan=z='min(zoom+0.0004,1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={int(max_take * fps)}:s={width}x{height}:fps={fps}"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(trim_in),
            "-i",
            str(source_mp4),
            "-t",
            str(max_take),
            "-vf",
            vf,
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(output_mp4),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    actual = probe_video(output_mp4)["duration_sec"]
    if actual + 0.15 < duration_sec:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(output_mp4),
                "-vf",
                f"tpad=stop_mode=clone:stop_duration={duration_sec - actual:.3f}",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(output_mp4),
            ],
            check=True,
            capture_output=True,
            text=True,
        )


def _slice_reference_clip(
    source_mp4: Path,
    start_sec: float,
    duration_sec: float,
    output_mp4: Path,
    width: int,
    height: int,
    fps: int = 30,
) -> None:
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(start_sec),
            "-i",
            str(source_mp4),
            "-t",
            str(duration_sec),
            "-vf",
            f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
            "-r",
            str(fps),
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(output_mp4),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _placeholder_clip(
    seg_id: str,
    keyword: str,
    phase: str,
    width: int,
    height: int,
    duration_sec: float,
    output_mp4: Path,
    fps: int,
) -> None:
    color = PHASE_COLORS.get(phase, "#1a1a22")
    image = Image.new("RGB", (width, height), color)
    draw = ImageDraw.Draw(image)
    title_font = _load_font(56)
    body_font = _load_font(36)
    draw.text((64, 160), seg_id, fill="#c8b8a0", font=title_font)
    draw.text((64, 280), keyword[:24], fill="#e8dcc8", font=body_font)
    image_path = output_mp4.with_suffix(".png")
    image.save(image_path, format="PNG")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-t",
            str(duration_sec),
            "-vf",
            f"scale={width}:{height}",
            "-r",
            str(fps),
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            str(output_mp4),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _score_stickman_scene(entry: dict[str, Any], keyword: str, phase: str) -> int:
    score = 0
    if phase in entry.get("phases", []):
        score += 4
    for tag in entry.get("tags", []):
        if tag in keyword:
            score += 3
    return score


def _pick_stickman_scene(
    catalog: list[dict[str, Any]],
    keyword: str,
    phase: str,
    used_ids: set[str],
) -> dict[str, Any]:
    ranked = sorted(
        catalog,
        key=lambda e: (_score_stickman_scene(e, keyword, phase), e["id"] not in used_ids),
        reverse=True,
    )
    for entry in ranked:
        if entry["id"] not in used_ids:
            return entry
    return ranked[0]


def fetch_stickman_scenes(config: dict[str, Any], work_dir: Path) -> list[dict[str, Any]]:
    subtitles_path = work_dir / "subtitles.json"
    if not subtitles_path.exists():
        raise SystemExit(f"Missing subtitles: {subtitles_path}")

    subtitles = load_json(subtitles_path)
    segments = subtitles.get("segments", [])
    if not segments:
        raise SystemExit("No subtitle segments for stickman mapping")

    scenes_path = Path(config.get("stickman_scenes", DEFAULT_STICKMAN)).resolve()
    scene_catalog = load_json(scenes_path) if scenes_path.exists() else {}
    catalog = scene_catalog.get("scenes", [])
    watermark = str(scene_catalog.get("watermark", ""))
    disclaimer = str(scene_catalog.get("disclaimer", "个人观点，无不良引导"))

    used_scene_ids: set[str] = set()
    clips: list[dict[str, Any]] = []

    for index, seg in enumerate(segments):
        seg_id = str(seg.get("id", f"seg_{index + 1:02d}"))
        duration = float(seg.get("duration_sec", 2.5))
        phase = str(seg.get("phase", "insight"))
        keyword = str(seg.get("visual_keyword", phase))
        entry = _pick_stickman_scene(catalog, keyword, phase, used_scene_ids)
        used_scene_ids.add(entry["id"])

        stickman_scene: dict[str, Any] = {
                    "pose": entry["pose"],
                    "prop": entry.get("prop", "none"),
                    "scene_title": keyword,
                    "headline": entry.get("headline", ""),
                    "extras": entry.get("extras", []),
                    "philosophy_quote": philosophy_quote_for_segment(seg, config),
                }
        if watermark:
            stickman_scene["watermark"] = watermark
        clips.append(
            {
                "id": seg_id,
                "clip": "",
                "is_image": False,
                "duration_sec": round(duration, 3),
                "phase": phase,
                "visual_keyword": keyword,
                "stock_id": entry["id"],
                "source": "stickman",
                "stickman_scene": stickman_scene,
            }
        )

    manifest = {
        "clips": clips,
        "asset_mode": "stickman",
        "stickman": {
            "disclaimer": disclaimer,
            "series_title": str(config.get("stickman_series_title", config.get("series", "认知提升"))),
        },
    }
    save_json(work_dir / "clips_manifest.json", manifest)
    return clips


def fetch_broll(config: dict[str, Any], work_dir: Path) -> list[dict[str, Any]]:
    asset_mode = str(config.get("asset_mode", "web"))
    if asset_mode == "stickman":
        return fetch_stickman_scenes(config, work_dir)

    subtitles_path = work_dir / "subtitles.json"
    if not subtitles_path.exists():
        raise SystemExit(f"Missing subtitles: {subtitles_path}")

    subtitles = load_json(subtitles_path)
    segments = subtitles.get("segments", [])
    if not segments:
        raise SystemExit("No subtitle segments for b-roll mapping")

    fps = int(config.get("fps", 30))
    width = int(config.get("width", 1920))
    height = int(config.get("height", 1080))
    asset_mode = str(config.get("asset_mode", "web"))

    sources_path = Path(config.get("broll_sources", DEFAULT_SOURCES)).resolve()
    catalog = load_json(sources_path).get("clips", []) if sources_path.exists() else []

    clips_dir = work_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    STOCK_CACHE.mkdir(parents=True, exist_ok=True)

    ref_mp4 = work_dir / "reference" / "source.mp4"
    cuts_path = work_dir / "reference" / "reference_cuts.json"
    cuts: list[dict[str, Any]] = []
    if cuts_path.exists():
        cuts = load_json(cuts_path).get("cuts", [])

    used_stock_ids: set[str] = set()
    clips: list[dict[str, Any]] = []

    for index, seg in enumerate(segments):
        seg_id = str(seg.get("id", f"seg_{index + 1:02d}"))
        duration = float(seg.get("duration_sec", 2.5))
        phase = str(seg.get("phase", "insight"))
        keyword = str(seg.get("visual_keyword", phase))
        clip_rel = f"clips/{seg_id}.mp4"
        clip_path = work_dir / clip_rel
        stock_id = ""
        source_kind = "placeholder"

        try:
            if asset_mode == "reference_slice" and ref_mp4.exists() and ref_mp4.stat().st_size > 10000 and cuts:
                cut = cuts[index % len(cuts)]
                start = float(cut.get("time", 0))
                cut_dur = float(cut.get("duration", duration))
                _slice_reference_clip(
                    ref_mp4,
                    start,
                    min(duration, cut_dur),
                    clip_path,
                    width,
                    height,
                    fps=fps,
                )
                source_kind = "reference_slice"
            elif asset_mode in {"web", "mixkit"} and catalog:
                entry = _pick_stock_clip(catalog, keyword, phase, used_stock_ids)
                stock_id = entry["id"]
                used_stock_ids.add(stock_id)
                cached = STOCK_CACHE / f"{stock_id}.mp4"
                _download_stock(entry["url"], cached)
                _trim_clip_to_duration(
                    cached,
                    clip_path,
                    duration,
                    float(entry.get("trim_in", 0.5)),
                    width,
                    height,
                    fps,
                )
                source_kind = "web_stock"
            else:
                raise RuntimeError(f"unsupported asset_mode: {asset_mode}")
        except Exception as exc:
            print(f"Warning: clip fallback for {seg_id}: {exc}")
            _placeholder_clip(seg_id, keyword, phase, width, height, duration, clip_path, fps)
            source_kind = "placeholder"

        clips.append(
            {
                "id": seg_id,
                "clip": clip_rel,
                "is_image": False,
                "duration_sec": round(duration, 3),
                "phase": phase,
                "visual_keyword": keyword,
                "stock_id": stock_id,
                "source": source_kind,
            }
        )

    manifest = {"clips": clips, "asset_mode": asset_mode}
    save_json(work_dir / "clips_manifest.json", manifest)
    return clips


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch B-roll clips for cognitive video.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)

    clips = fetch_broll(config, work_dir)
    stickman_count = sum(1 for c in clips if c.get("source") == "stickman")
    web_count = sum(1 for c in clips if c.get("source") == "web_stock")
    if stickman_count:
        print(f"Clips manifest: {work_dir / 'clips_manifest.json'} ({len(clips)} stickman scenes)")
    else:
        print(f"Clips manifest: {work_dir / 'clips_manifest.json'} ({len(clips)} clips, {web_count} stock)")
    for clip in clips:
        label = clip.get("stock_id", clip.get("source", "-"))
        print(f"  {clip['id']}: {label} ({clip.get('source')})")


if __name__ == "__main__":
    main()
