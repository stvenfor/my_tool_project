#!/usr/bin/env python3
"""Build and render EP01 cat-drama storyboard video with Remotion."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent
COGNITIVE_ROOT = PROJECT_ROOT / "modules" / "cognitive-video"

sys.path.insert(0, str(ROOT))

from ambient_bgm import prepare_ambient_bgm  # noqa: E402
from lib import load_json, save_json  # noqa: E402

WORK_DIR = ROOT / "work" / "EP01"
STORYBOARD_SRC = COGNITIVE_ROOT / "assets" / "storyboard"
CLIPS = [
    ("S01", "EP01_S01_全景_饭桌_v1.png", "setup"),
    ("S02", "EP01_S02_大橘_中景_委屈_v1.png", "daju"),
    ("S03", "EP01_S03_阿狸_特写_冷笑_v1.png", "alili"),
    ("S04", "EP01_S04_小白_中景_拱火_v1.png", "xiaobai"),
    ("S05", "EP01_S05_阿狸_特写_连珠炮_v1.png", "alili"),
    ("S06", "EP01_S06_大橘_中景_崩溃_v1.png", "daju"),
    ("S07", "EP01_S07_大橘_全景_躺倒_v1.png", "daju"),
    ("S08", "EP01_S08_阿狸_特写_收尾_v1.png", "alili"),
]


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("$", " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd or PROJECT_ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def upscale_clips() -> None:
    clips_dir = WORK_DIR / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image
    except ImportError as exc:
        raise SystemExit("Pillow required: pip install pillow") from exc

    for shot_id, src_name, _phase in CLIPS:
        src = STORYBOARD_SRC / src_name
        if not src.exists():
            raise SystemExit(f"Missing storyboard image: {src}")
        dest = clips_dir / f"{shot_id}.png"
        img = Image.open(src).convert("RGB")
        upscaled = img.resize((1080, 1920), Image.Resampling.LANCZOS)
        upscaled.save(dest, optimize=True)
        print(f"Upscaled {src_name} -> {dest.name} ({upscaled.size[0]}x{upscaled.size[1]})")


def ensure_config() -> Path:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    config_path = WORK_DIR / "config.json"
    defaults = {
        "topic_id": "cat-drama-ep01",
        "title": "饭桌修罗场",
        "series": "猫家日常",
        "episode": "01",
        "hook": "",
        "cta": "关注看下一集",
        "tags": ["搞笑", "猫咪", "家庭日常"],
        "duration_sec": 0,
        "fps": 30,
        "width": 1080,
        "height": 1920,
        "hook_duration_sec": 0,
        "narration_gap_sec": 0.18,
        "dialogue_gap_sec": 0.22,
        "tail_padding_sec": 2.0,
        "narration_volume": 0.92,
        "transition_frames": 8,
        "use_ambient_bgm": True,
        "ambient_bgm_volume": 0.08,
        "asset_mode": "image",
        "character_voices": {
            "alili": {
                "voice": "zh-CN-YunjianNeural",
                "rate": "+4%",
                "pitch": "-6Hz",
                "volume": "+2%",
            },
            "daju": {
                "voice": "zh-CN-YunxiaNeural",
                "rate": "+14%",
                "pitch": "+10Hz",
                "volume": "+4%",
            },
            "xiaobai": {
                "voice": "zh-CN-XiaoyiNeural",
                "rate": "+6%",
                "pitch": "+4Hz",
                "volume": "+2%",
            },
            "setup": {"silence_sec": 1.8},
        },
    }
    if config_path.exists():
        config = load_json(config_path)
        config.update({k: v for k, v in defaults.items() if k not in config})
        config["character_voices"] = defaults["character_voices"]
        config["dialogue_gap_sec"] = defaults["dialogue_gap_sec"]
    else:
        config = defaults
    save_json(config_path, config)
    return config_path


DIALOGUE_SEGMENTS = [
    {
        "id": "S01",
        "character": "",
        "character_key": "setup",
        "dialogue": "",
        "visual_keyword": "全景饭桌",
        "phase": "setup",
    },
    {
        "id": "S02",
        "character": "大橘",
        "character_key": "daju",
        "dialogue": "我就多睡了一觉，至于吗？",
        "visual_keyword": "大橘委屈",
        "phase": "daju",
    },
    {
        "id": "S03",
        "character": "阿狸",
        "character_key": "alili",
        "dialogue": "你那叫多睡？那是冬眠。",
        "visual_keyword": "阿狸冷笑",
        "phase": "alili",
    },
    {
        "id": "S04",
        "character": "小白",
        "character_key": "xiaobai",
        "dialogue": "别吵，让我再看看。",
        "visual_keyword": "小白拱火",
        "phase": "xiaobai",
    },
    {
        "id": "S05",
        "character": "阿狸",
        "character_key": "alili",
        "dialogue": "你除了吃还会什么？房贷车贷育儿班，你交过几笔？",
        "visual_keyword": "阿狸连珠炮",
        "phase": "alili",
    },
    {
        "id": "S06",
        "character": "大橘",
        "character_key": "daju",
        "dialogue": "你……你怎么全说了……",
        "visual_keyword": "大橘崩溃",
        "phase": "daju",
    },
    {
        "id": "S07",
        "character": "大橘",
        "character_key": "daju",
        "dialogue": "我不活了……",
        "visual_keyword": "大橘躺倒",
        "phase": "daju",
    },
    {
        "id": "S08",
        "character": "阿狸",
        "character_key": "alili",
        "dialogue": "哭完记得把碗洗了。",
        "visual_keyword": "阿狸收尾",
        "phase": "alili",
    },
]


def ensure_script() -> None:
    save_json(
        WORK_DIR / "script.json",
        {
            "series": "猫家日常",
            "episode": "01",
            "title": "饭桌修罗场",
            "hook": "",
            "mode": "dialogue",
            "segments": DIALOGUE_SEGMENTS,
            "cta": "关注看下一集",
            "tags": ["搞笑", "猫咪", "家庭日常"],
        },
    )


def build_clips_manifest(subtitles: dict) -> None:
    segments = subtitles.get("segments", [])
    if len(segments) != len(CLIPS):
        raise SystemExit(f"Expected {len(CLIPS)} segments, got {len(segments)}")

    clips = []
    for (shot_id, _src_name, phase), seg in zip(CLIPS, segments, strict=True):
        clips.append(
            {
                "id": shot_id,
                "clip": f"clips/{shot_id}.png",
                "is_image": True,
                "start_sec": float(seg["start_sec"]),
                "duration_sec": float(seg["duration_sec"]) + 0.12,
                "phase": phase,
            }
        )

    save_json(WORK_DIR / "clips_manifest.json", {"clips": clips})


def build_storyboard(config: dict, subtitles: dict) -> None:
    script = load_json(WORK_DIR / "script.json")
    clips_manifest = load_json(WORK_DIR / "clips_manifest.json")
    fps = int(config.get("fps", 30))
    width = int(config.get("width", 1080))
    height = int(config.get("height", 1920))
    segments = subtitles.get("segments", [])
    tail_padding = float(subtitles.get("tail_padding_sec", config.get("tail_padding_sec", 2.0)))
    duration_sec = float(subtitles.get("duration_sec", 30))

    shots = []
    for clip in clips_manifest.get("clips", []):
        duration = float(clip.get("duration_sec", 2.0))
        shots.append(
            {
                "id": clip["id"],
                "clip": clip.get("clip", ""),
                "is_image": True,
                "start_sec": round(float(clip.get("start_sec", 0.0)), 3),
                "duration_sec": duration,
                "phase": clip.get("phase", "setup"),
                "transition": "crossfade",
            }
        )

    narration_end = max((s["start_sec"] + s["duration_sec"] for s in shots), default=0.0)
    if narration_end + tail_padding > duration_sec:
        duration_sec = round(narration_end + tail_padding, 3)

    bgm_rel = ""
    if config.get("use_ambient_bgm", True):
        ambient = prepare_ambient_bgm(WORK_DIR, duration_sec)
        if ambient:
            bgm_rel = ambient.name

    emphasis_items = []

    storyboard = {
        "style": "cat_drama",
        "visual_style": "cinematic",
        "series": script.get("series", "猫家日常"),
        "episode": script.get("episode", "01"),
        "title": script.get("title", "饭桌修罗场"),
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
        "hook": {"text_zh": "", "duration_sec": 0.0},
        "series_badge": {
            "series": script.get("series", "猫家日常"),
            "episode": script.get("episode", "01"),
            "duration_sec": 2.5,
        },
        "subtitles": segments,
        "subtitle_style": {
            "zh_size": 38,
            "margin_bottom": 180,
            "color_zh": "#fff8ec",
        },
        "emphasis": [],
        "emphasis_style": {
            "font_size": 54,
            "color": "#ffd98a",
        },
        "grade": {"warmth": 0.45},
        "shots": shots,
        "closing_title": {
            "text_zh": script.get("cta", "关注看下一集"),
            "appear_at_sec": max(0.0, duration_sec - 2.5),
            "duration_sec": 2.5,
        },
        "tags": script.get("tags", []),
    }
    save_json(WORK_DIR / "storyboard.json", storyboard)
    config["duration_sec"] = duration_sec
    save_json(WORK_DIR / "config.json", config)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and render EP01 cat drama video.")
    parser.add_argument("--skip-voice", action="store_true")
    parser.add_argument("--skip-render", action="store_true")
    args = parser.parse_args()

    ensure_config()
    ensure_script()
    upscale_clips()
    config_path = WORK_DIR / "config.json"

    if not args.skip_voice or not (WORK_DIR / "narration.wav").exists():
        run([sys.executable, str(ROOT / "synthesize_dialogue.py"), "--config", str(config_path)])

    subtitles = load_json(WORK_DIR / "subtitles.json")
    config = load_json(config_path)
    build_clips_manifest(subtitles)
    build_storyboard(config, subtitles)

    output_path = WORK_DIR / "output" / "final.mp4"
    if args.skip_render:
        print(f"Storyboard ready: {WORK_DIR / 'storyboard.json'}")
        return

    remotion_dir = COGNITIVE_ROOT / "remotion"
    if not (remotion_dir / "node_modules").exists():
        run(["npm", "install"], cwd=remotion_dir)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "node",
            str(COGNITIVE_ROOT / "render.mjs"),
            "--storyboard",
            str((WORK_DIR / "storyboard.json").relative_to(PROJECT_ROOT)),
            "--work-dir",
            str(WORK_DIR.relative_to(PROJECT_ROOT)),
            "--output",
            str(output_path.relative_to(PROJECT_ROOT)),
        ]
    )

    save_json(
        WORK_DIR / "pipeline-result.json",
        {
            "storyboard": str((WORK_DIR / "storyboard.json").relative_to(PROJECT_ROOT)),
            "output": str(output_path.relative_to(PROJECT_ROOT)),
        },
    )
    print(f"Done: {output_path}")


if __name__ == "__main__":
    main()
