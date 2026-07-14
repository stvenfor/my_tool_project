"""Dialogue (剧情对白) mode — multi-character voice + image clips."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from lib import CAT_DRAMA_ROOT, load_json, run, save_json, write_project_config  # noqa: E402
from modes.common import export_douyin, render_storyboard  # noqa: E402

from modes.ambient_bgm import prepare_ambient_bgm  # noqa: E402


def _ensure_placeholder_clips(work_dir: Path, segments: list[dict[str, Any]]) -> None:
    clips_dir = work_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        Image = None  # type: ignore

    for seg in segments:
        shot_id = str(seg.get("id", ""))
        if not shot_id:
            continue
        dest = clips_dir / f"{shot_id}.png"
        if dest.exists():
            continue
        keyword = str(seg.get("visual_keyword", shot_id))
        character = str(seg.get("character", ""))
        if Image is None:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=#1a1a2e:s=1080x1920:d=1",
                    "-frames:v", "1", str(dest),
                ],
                check=True,
                capture_output=True,
            )
            continue
        img = Image.new("RGB", (1080, 1920), color=(26, 26, 46))
        draw = ImageDraw.Draw(img)
        title = f"{shot_id} {character}".strip()
        draw.text((60, 800), title, fill=(255, 248, 236))
        draw.text((60, 900), keyword[:40], fill=(200, 200, 220))
        img.save(dest, optimize=True)


def build_clips_manifest(subtitles: dict[str, Any], script: dict[str, Any]) -> dict[str, Any]:
    segments = subtitles.get("segments", [])
    script_segs = script.get("segments", [])
    clips = []
    for seg, script_seg in zip(segments, script_segs, strict=False):
        shot_id = str(script_seg.get("id", seg.get("id", "")))
        clips.append(
            {
                "id": shot_id,
                "clip": f"clips/{shot_id}.png",
                "is_image": True,
                "start_sec": float(seg["start_sec"]),
                "duration_sec": float(seg["duration_sec"]) + 0.12,
                "phase": seg.get("phase", script_seg.get("character_key", "setup")),
            }
        )
    manifest = {"clips": clips}
    return manifest


def build_dialogue_storyboard(config: dict[str, Any], work_dir: Path) -> None:
    script = load_json(work_dir / "script.json")
    subtitles = load_json(work_dir / "subtitles.json")
    clips_manifest = build_clips_manifest(subtitles, script)
    save_json(work_dir / "clips_manifest.json", clips_manifest)

    fps = int(config.get("fps", 30))
    width = int(config.get("width", 1080))
    height = int(config.get("height", 1920))
    segments = subtitles.get("segments", [])
    tail_padding = float(subtitles.get("tail_padding_sec", config.get("tail_padding_sec", 2.0)))
    duration_sec = float(subtitles.get("duration_sec", 30))

    shots = []
    for clip in clips_manifest.get("clips", []):
        shots.append(
            {
                "id": clip["id"],
                "clip": clip.get("clip", ""),
                "is_image": True,
                "start_sec": round(float(clip.get("start_sec", 0.0)), 3),
                "duration_sec": float(clip.get("duration_sec", 2.0)),
                "phase": clip.get("phase", "setup"),
                "transition": "crossfade",
            }
        )

    narration_end = max((s["start_sec"] + s["duration_sec"] for s in shots), default=0.0)
    if narration_end + tail_padding > duration_sec:
        duration_sec = round(narration_end + tail_padding, 3)

    bgm_rel = ""
    if config.get("use_ambient_bgm", True):
        ambient = prepare_ambient_bgm(work_dir, duration_sec)
        if ambient:
            bgm_rel = ambient.name

    storyboard = {
        "style": "cat_drama",
        "visual_style": "cinematic",
        "series": script.get("series", config.get("series", "")),
        "episode": script.get("episode", config.get("episode", "01")),
        "title": script.get("title", config.get("title", "")),
        "fps": fps,
        "width": width,
        "height": height,
        "duration_sec": duration_sec,
        "duration_in_frames": int(round(duration_sec * fps)),
        "transition_frames": int(config.get("transition_frames", 8)),
        "narration": "narration.wav",
        "narration_volume": float(config.get("narration_volume", 0.92)),
        "bgm": bgm_rel,
        "bgm_volume": float(config.get("ambient_bgm_volume", 0.08)),
        "hook": {"text_zh": script.get("hook", ""), "duration_sec": 0.0},
        "series_badge": {
            "series": script.get("series", config.get("series", "")),
            "episode": script.get("episode", config.get("episode", "01")),
            "duration_sec": 2.5,
        },
        "subtitles": segments,
        "subtitle_style": {
            "zh_size": 38,
            "margin_bottom": 180,
            "color_zh": "#fff8ec",
        },
        "emphasis": [],
        "emphasis_style": {"font_size": 54, "color": "#ffd98a"},
        "grade": {"warmth": 0.45},
        "shots": shots,
        "closing_title": {
            "text_zh": script.get("cta", config.get("cta", "关注看下一集")),
            "appear_at_sec": max(0.0, duration_sec - 2.5),
            "duration_sec": 2.5,
        },
        "tags": script.get("tags", config.get("tags", [])),
    }
    save_json(work_dir / "storyboard.json", storyboard)
    config["duration_sec"] = duration_sec
    write_project_config(work_dir, config)


def export_jimeng_prompts(work_dir: Path) -> Path:
    script = load_json(work_dir / "script.json")
    lines = ["# 即梦分镜 Prompt", ""]
    for seg in script.get("segments", []):
        shot_id = seg.get("id", "")
        keyword = seg.get("visual_keyword", "")
        prompt = ""
        for p in script.get("storyboard_prompts", []):
            if p.get("id") == shot_id:
                prompt = p.get("prompt", "")
                break
        if not prompt:
            prompt = f"写实插画/3D卡通，{keyword}，竖屏9:16，电影感构图"
        lines.append(f"## {shot_id}")
        lines.append(prompt)
        lines.append("")
    out = work_dir / "jimeng-prompts.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def run_dialogue_pipeline(
    config: dict[str, Any],
    work_dir: Path,
    *,
    skip_voice: bool = False,
    skip_render: bool = False,
    skip_export: bool = False,
    script_source: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    config_path = write_project_config(work_dir, config)
    work_dir.mkdir(parents=True, exist_ok=True)

    if script_source and script_source.exists():
        script = load_json(script_source)
        if script.get("character_voices"):
            config["character_voices"] = script["character_voices"]
            write_project_config(work_dir, config)
        save_json(work_dir / "script.json", script)

    script_path = work_dir / "script.json"
    if not script_path.exists():
        raise SystemExit(f"Missing script.json in {work_dir}")

    script = load_json(script_path)
    _ensure_placeholder_clips(work_dir, script.get("segments", []))
    export_jimeng_prompts(work_dir)

    if not skip_voice or not (work_dir / "narration.wav").exists():
        run([sys.executable, str(CAT_DRAMA_ROOT / "synthesize_dialogue.py"), "--config", str(work_dir / "config.json")])

    build_dialogue_storyboard(config, work_dir)

    final_output = output_path or (work_dir / "output" / "final.mp4")
    if not skip_render:
        render_storyboard(work_dir, final_output)

    if not skip_export:
        export_douyin(config, work_dir)

    result = {
        "mode": "dialogue",
        "config": str(config_path.relative_to(work_dir.parent.parent)),
        "storyboard": str((work_dir / "storyboard.json").relative_to(work_dir.parent.parent)),
        "output": str(final_output.relative_to(work_dir.parent.parent)) if not skip_render else "",
    }
    save_json(work_dir / "pipeline-result.json", result)
    return result
