"""Ambient BGM preparation (local copy — no cross-module import)."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

AMBIENT_BGM_URL = "https://assets.mixkit.co/music/preview/mixkit-serene-view-443.mp3"


def _synthesize_ambient_bgm(output: Path, duration_sec: float) -> Path | None:
    """Generate a subtle ambient bed when no downloadable stock track is available."""
    fade_out_start = max(0.0, duration_sec - 2.5)
    af = (
        "amix=inputs=3:duration=first:dropout_transition=0,volume=0.08,"
        "highpass=f=140,lowpass=f=3600,"
        f"afade=t=in:st=0:d=2,afade=t=out:st={fade_out_start:.3f}:d=2.5"
    )
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=196:duration={duration_sec}:sample_rate=44100",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=294:duration={duration_sec}:sample_rate=44100",
            "-f",
            "lavfi",
            "-i",
            f"anoisesrc=d={duration_sec}:c=pink:a=0.012:sample_rate=44100",
            "-filter_complex",
            af,
            "-ac",
            "1",
            "-ar",
            "44100",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not output.exists():
        print(result.stderr or result.stdout)
        return None
    return output


def prepare_ambient_bgm(work_dir: Path, duration_sec: float, output_name: str = "ambient_bgm.wav") -> Path | None:
    candidates = [
        work_dir / "reference" / "audio.wav",
        work_dir / "reference" / "bgm.wav",
        work_dir / "reference" / "source.audio.m4a",
    ]
    source = next((p for p in candidates if p.exists()), None)

    output = work_dir / output_name
    fade_out_start = max(0.0, duration_sec - 2.5)

    if source is None:
        stock_bgm = ROOT / "stock_cache" / "ambient_bgm.mp3"
        stock_bgm.parent.mkdir(parents=True, exist_ok=True)
        if not stock_bgm.exists():
            subprocess.run(
                ["curl", "-fsSL", "-o", str(stock_bgm), AMBIENT_BGM_URL],
                check=False,
            )
        if not stock_bgm.exists():
            print("Stock BGM unavailable, synthesizing ambient bed")
            return _synthesize_ambient_bgm(output, duration_sec)
        source = stock_bgm

    af = (
        "pan=stereo|c0=0.5*c0+-0.5*c1|c1=0.5*c1+-0.5*c0,"
        "highpass=f=180,lowpass=f=5200,volume=0.14,"
        f"afade=t=in:st=0:d=2,afade=t=out:st={fade_out_start:.3f}:d=2.5"
    )
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-t",
            str(duration_sec),
            "-af",
            af,
            "-ac",
            "1",
            "-ar",
            "44100",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not output.exists():
        print(result.stderr or result.stdout)
        return None
    return output


def _build_emphasis_timeline(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    emphasis_items: list[dict[str, Any]] = []
    for seg in segments:
        start = float(seg.get("start_sec", 0))
        duration = float(seg.get("duration_sec", 2))
        words = seg.get("emphasis", [])
        if not words:
            continue
        slot = duration / len(words)
        for index, word in enumerate(words):
            emphasis_items.append(
                {
                    "text": word,
                    "start_sec": round(start + index * slot, 3),
                    "duration_sec": round(min(slot * 1.2, duration - index * slot), 3),
                    "phase": seg.get("phase", "insight"),
                }
            )
    return emphasis_items


def main() -> None:
    parser = argparse.ArgumentParser(description="Build cognitive storyboard.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)

    script = load_json(work_dir / "script.json") if (work_dir / "script.json").exists() else {}
    subtitles_path = work_dir / "subtitles.json"
    subtitles = load_json(subtitles_path) if subtitles_path.exists() else {}
    clips_manifest = load_json(work_dir / "clips_manifest.json") if (work_dir / "clips_manifest.json").exists() else {}
    style_profile = (
        load_json(work_dir / "reference" / "style_profile.json")
        if (work_dir / "reference" / "style_profile.json").exists()
        else {}
    )

    fps = int(config.get("fps", 30))
    width = int(config.get("width", 1920))
    height = int(config.get("height", 1080))
    is_landscape = width > height
    duration_sec = float(subtitles.get("duration_sec") or config.get("duration_sec") or 60)

    clips = clips_manifest.get("clips", [])
    segments = subtitles.get("segments", [])
    asset_mode = str(config.get("asset_mode", "web"))
    visual_style = "stickman" if asset_mode == "stickman" else "cinematic"

    shots: list[dict[str, Any]] = []
    cursor = 0.0
    for clip in clips:
        duration = float(clip.get("duration_sec", 2.0))
        shot: dict[str, Any] = {
            "id": clip["id"],
            "clip": clip.get("clip", ""),
            "is_image": bool(clip.get("is_image", False)),
            "start_sec": round(cursor, 3),
            "duration_sec": duration,
            "phase": clip.get("phase", "insight"),
            "transition": "crossfade",
        }
        if clip.get("stickman_scene"):
            shot["stickman_scene"] = clip["stickman_scene"]
        shots.append(shot)
        cursor += duration

    tail_padding = float(subtitles.get("tail_padding_sec", config.get("tail_padding_sec", 2.0)))
    if shots and tail_padding > 0:
        shots[-1]["duration_sec"] = round(float(shots[-1]["duration_sec"]) + tail_padding, 3)

    narration_end = max((s["start_sec"] + s["duration_sec"] for s in shots), default=0.0)
    content_end = max(
        (float(s.get("start_sec", 0)) + float(s.get("duration_sec", 0)) for s in segments),
        default=0.0,
    )
    duration_sec = float(subtitles.get("duration_sec") or config.get("duration_sec") or 60)
    if narration_end > duration_sec - 0.05:
        duration_sec = round(narration_end, 3)

    bgm_rel = ""
    if config.get("use_ambient_bgm", True):
        ambient = prepare_ambient_bgm(work_dir, duration_sec)
        if ambient:
            bgm_rel = ambient.name

    emphasis_timeline = _build_emphasis_timeline(segments)

    storyboard = {
        "style": "cognitive_explainer",
        "visual_style": visual_style,
        "stickman": clips_manifest.get("stickman", {}) if visual_style == "stickman" else {},
        "series": script.get("series", config.get("series", "认知提升")),
        "episode": script.get("episode", config.get("episode", "01")),
        "title": script.get("title", config.get("title", "")),
        "fps": fps,
        "width": width,
        "height": height,
        "duration_sec": duration_sec,
        "duration_in_frames": int(round(duration_sec * fps)),
        "transition_frames": int(config.get("transition_frames", 8)),
        "narration": "narration.wav" if (work_dir / "narration.wav").exists() else "",
        "narration_volume": float(config.get("narration_volume", 0.92)),
        "bgm": bgm_rel,
        "bgm_volume": float(config.get("ambient_bgm_volume", config.get("bgm_volume", 0.1))),
        "hook": {
            "text_zh": subtitles.get("hook_zh", script.get("hook", "")),
            "duration_sec": float(subtitles.get("hook_duration_sec", config.get("hook_duration_sec", 2.8))),
        },
        "series_badge": {
            "series": script.get("series", config.get("series", "认知提升")),
            "episode": script.get("episode", config.get("episode", "01")),
            "duration_sec": float(subtitles.get("hook_duration_sec", 2.8)) + 1.5,
        },
        "subtitles": segments,
        "subtitle_style": (
            {
                "mode": "stickman_bar",
                "zh_size": 28 if is_landscape else 34,
                "margin_bottom": 64 if is_landscape else 72,
                "color_zh": "#111111",
            }
            if visual_style == "stickman"
            else style_profile.get("subtitle", {})
        ),
        "emphasis": emphasis_timeline,
        "emphasis_style": style_profile.get("emphasis", {}),
        "grade": style_profile.get("grade", {"warmth": 0.35}),
        "shots": shots,
        "closing_title": {
            "text_zh": script.get("cta", config.get("cta", "建议收藏")),
            "appear_at_sec": round(content_end, 3),
            "duration_sec": tail_padding,
        },
        "tags": script.get("tags", config.get("tags", [])),
    }

    output_path = work_dir / "storyboard.json"
    save_json(output_path, storyboard)
    config["duration_sec"] = duration_sec
    save_json(config_path, config)
    print(f"Storyboard saved: {output_path}")
    print(f"Shots: {len(shots)}, emphasis: {len(emphasis_timeline)}, duration: {duration_sec:.1f}s")


if __name__ == "__main__":
    main()

