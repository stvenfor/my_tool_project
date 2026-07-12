#!/usr/bin/env python3
"""Generate placeholder clip images for demo/offline city-healing renders."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import build_scene_prompts, load_json, resolve_work_dir  # noqa: E402

CREAM_PALETTE = [
    "#f5e6d3",
    "#edd9c2",
    "#e8d0b5",
    "#f0dcc8",
    "#e5cdb0",
    "#f2e2cc",
    "#ebd6be",
    "#f7ebe0",
    "#e2c9a8",
    "#f4e4d4",
]


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


def render_placeholder(
    scene: dict,
    city_name: str,
    width: int,
    height: int,
    color: str,
) -> Image.Image:
    image = Image.new("RGB", (width, height), color)
    draw = ImageDraw.Draw(image)
    title_font = _load_font(64)
    body_font = _load_font(36)
    small_font = _load_font(28)

    draw.rectangle([(0, 0), (width, height)], fill=color)
    draw.rectangle([(48, 120), (width - 48, height - 120)], outline="#d4b896", width=3)

    title = f"{scene['id']} · {scene['zh_desc']}"
    draw.text((72, 180), title, fill="#6b5344", font=title_font)
    draw.text((72, 280), city_name, fill="#8b6f5c", font=body_font)

    wrapped = scene.get("prompt_en", "")[:180]
    y = 380
    for line in _wrap_text(wrapped, 22):
        draw.text((72, y), line, fill="#9a7d68", font=small_font)
        y += 42

    draw.text((72, height - 180), "cream film · healing city", fill="#b89578", font=small_font)
    return image


def _wrap_text(text: str, max_chars: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:6]


def image_to_mp4(image_path: Path, output_path: Path, duration_sec: float, fps: int = 30) -> bool:
    cmd = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_path),
        "-c:v",
        "libx264",
        "-t",
        str(duration_sec),
        "-pix_fmt",
        "yuv420p",
        "-vf",
        f"scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
        "-r",
        str(fps),
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate placeholder city-healing clips.")
    parser.add_argument("--config", required=True, help="Path to city.config.json")
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)
    clips_dir = work_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    width = int(config.get("width", 1080))
    height = int(config.get("height", 1920))
    city_name = str(config.get("city_name", "【目标城市】"))
    scenes = build_scene_prompts(config)

    manifest: list[dict] = []
    for index, scene in enumerate(scenes):
        color = CREAM_PALETTE[index % len(CREAM_PALETTE)]
        image_path = clips_dir / f"{scene['id']}.png"
        mp4_path = clips_dir / f"{scene['id']}.mp4"
        image = render_placeholder(scene, city_name, width, height, color)
        image.save(image_path)

        duration = float(scene.get("duration_sec", 6))
        if image_to_mp4(image_path, mp4_path, duration, fps=args.fps):
            clip_file = f"clips/{scene['id']}.mp4"
            is_image = False
        else:
            clip_file = f"clips/{scene['id']}.png"
            is_image = True
            print(f"ffmpeg unavailable, using still image for {scene['id']}")

        manifest.append(
            {
                "id": scene["id"],
                "clip": clip_file,
                "is_image": is_image,
                "duration_sec": duration,
                "zh_desc": scene["zh_desc"],
            }
        )

    save_path = work_dir / "clips_manifest.json"
    save_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Placeholder clips saved to {clips_dir}")
    print(f"Manifest: {save_path}")


if __name__ == "__main__":
    main()
