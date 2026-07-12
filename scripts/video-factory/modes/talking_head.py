"""Talking-head (出镜口播) mode — narration + presenter clip."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from lib import COGNITIVE_ROOT, PROJECT_ROOT, get_audio_duration, load_json, run, save_json, write_project_config  # noqa: E402
from modes.common import export_douyin, render_storyboard, run_cognitive_script  # noqa: E402

Q_REPLACE_ROOT = Path(__file__).resolve().parent.parent.parent / "q-replace"
DEFAULT_PRESENTER = Path(__file__).resolve().parent.parent / "assets" / "presenter" / "default.png"


def _ken_burns_video(image_path: Path, audio_path: Path, output_mp4: Path, duration_sec: float) -> None:
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "zoompan=z='min(zoom+0.0004,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={int(duration_sec * 30)}:s=1080x1920:fps=30"
    )
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(image_path),
            "-i", str(audio_path),
            "-vf", vf,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            "-t", str(duration_sec),
            str(output_mp4),
        ],
        check=True,
        capture_output=True,
    )


def _try_wav2lip(image_path: Path, audio_path: Path, work_dir: Path, duration_sec: float) -> Path | None:
    try:
        import cv2
        sys.path.insert(0, str(Q_REPLACE_ROOT / "lib"))
        from wav2lip import apply_wav2lip_if_available  # type: ignore

        frame = cv2.imread(str(image_path))
        if frame is None:
            return None
        result = apply_wav2lip_if_available(frame, audio_path, 0.0, duration_sec, work_dir / "talking_head")
        if result is None:
            return None
        out_mp4 = work_dir / "talking_head" / "wav2lip_clips" / "out_0.000.mp4"
        if out_mp4.exists():
            dest = work_dir / "clips" / "presenter.mp4"
            dest.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["cp", str(out_mp4), str(dest)], check=True)
            return dest
    except Exception as exc:
        print(f"Wav2Lip unavailable, using ken-burns fallback: {exc}")
    return None


def build_talking_head_storyboard(config: dict[str, Any], work_dir: Path, presenter_clip: str) -> None:
    subtitles = load_json(work_dir / "subtitles.json")
    script = load_json(work_dir / "script.json") if (work_dir / "script.json").exists() else {}
    fps = int(config.get("fps", 30))
    width = int(config.get("width", 1080))
    height = int(config.get("height", 1920))
    duration_sec = float(subtitles.get("duration_sec", config.get("duration_sec", 60)))
    segments = subtitles.get("segments", [])

    storyboard = {
        "style": "talking_head",
        "visual_style": "cinematic",
        "series": script.get("series", config.get("series", "")),
        "episode": script.get("episode", config.get("episode", "01")),
        "title": script.get("title", config.get("title", "")),
        "fps": fps,
        "width": width,
        "height": height,
        "duration_sec": duration_sec,
        "duration_in_frames": int(round(duration_sec * fps)),
        "transition_frames": 0,
        "narration": "narration.wav",
        "narration_volume": float(config.get("narration_volume", 0.94)),
        "bgm": "",
        "bgm_volume": float(config.get("ambient_bgm_volume", 0.08)),
        "hook": {
            "text_zh": script.get("hook", config.get("hook", "")),
            "duration_sec": float(config.get("hook_duration_sec", 2.5)),
        },
        "series_badge": {
            "series": script.get("series", config.get("series", "")),
            "episode": script.get("episode", config.get("episode", "01")),
            "duration_sec": 2.5,
        },
        "subtitles": segments,
        "subtitle_style": {
            "zh_size": 36,
            "margin_bottom": 120,
            "color_zh": "#ffffff",
        },
        "emphasis": [],
        "emphasis_style": {"font_size": 48, "color": "#ffd98a"},
        "grade": {"warmth": 0.3},
        "shots": [
            {
                "id": "presenter",
                "clip": presenter_clip,
                "is_image": presenter_clip.endswith(".png"),
                "start_sec": 0.0,
                "duration_sec": duration_sec,
                "phase": "presenter",
                "transition": "none",
            }
        ],
        "closing_title": {
            "text_zh": script.get("cta", config.get("cta", "关注不迷路")),
            "appear_at_sec": max(0.0, duration_sec - 2.5),
            "duration_sec": 2.5,
        },
        "tags": script.get("tags", config.get("tags", [])),
    }
    save_json(work_dir / "storyboard.json", storyboard)


def run_talking_head_pipeline(
    config: dict[str, Any],
    work_dir: Path,
    *,
    skip_script: bool = False,
    skip_voice: bool = False,
    skip_render: bool = False,
    skip_export: bool = False,
    use_llm: bool = False,
    output_path: Path | None = None,
) -> dict[str, Any]:
    config_path = write_project_config(work_dir, config)
    work_dir.mkdir(parents=True, exist_ok=True)
    clips_dir = work_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    presenter_src = Path(str(config.get("presenter_image", DEFAULT_PRESENTER)))
    if not presenter_src.is_absolute():
        candidate = PROJECT_ROOT / presenter_src
        presenter_src = candidate if candidate.exists() else (Path(__file__).resolve().parent.parent / presenter_src)
    if not presenter_src.exists():
        raise SystemExit(f"Missing presenter image: {presenter_src}")

    if not skip_script:
        run_cognitive_script(work_dir / "config.json", use_llm=use_llm or bool(config.get("use_llm")))

    if not skip_voice:
        run([sys.executable, str(COGNITIVE_ROOT / "synthesize_voice.py"), "--config", str(work_dir / "config.json")])

    narration_wav = work_dir / "narration.wav"
    if not narration_wav.exists():
        raise SystemExit("narration.wav missing after voice synthesis")

    duration_sec = get_audio_duration(narration_wav)
    presenter_mp4 = clips_dir / "presenter.mp4"
    wav2lip_out = _try_wav2lip(presenter_src, narration_wav, work_dir, duration_sec)
    if wav2lip_out and wav2lip_out.exists():
        presenter_clip = "clips/presenter.mp4"
    else:
        _ken_burns_video(presenter_src, narration_wav, presenter_mp4, duration_sec)
        presenter_clip = "clips/presenter.mp4"

    build_talking_head_storyboard(config, work_dir, presenter_clip)

    final_output = output_path or (work_dir / "output" / "final.mp4")
    if not skip_render:
        render_storyboard(work_dir, final_output)

    if not skip_export:
        export_douyin(config, work_dir)

    result = {
        "mode": "talking_head",
        "config": str(config_path.relative_to(work_dir.parent.parent)),
        "storyboard": str((work_dir / "storyboard.json").relative_to(work_dir.parent.parent)),
        "output": str(final_output.relative_to(work_dir.parent.parent)) if not skip_render else "",
    }
    save_json(work_dir / "pipeline-result.json", result)
    return result
