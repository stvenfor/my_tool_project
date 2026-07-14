#!/usr/bin/env python3
"""Analyze local or Douyin reference clip: audio, Whisper zh transcript, metadata."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import (  # noqa: E402
    audio_to_wav,
    copy_local_video,
    download_reference_video,
    extract_audio_from_video,
    load_json,
    probe_video,
    resolve_work_dir,
    resolve_target_video_path,
    save_json,
)


def _transcribe_audio(
    audio_wav: Path,
    language: str = "zh",
    model_name: str = "base",
) -> tuple[str, str, list[dict[str, Any]]]:
    try:
        import whisper
    except ImportError as exc:
        raise SystemExit("whisper not installed. Run: npm run viral-dub:setup") from exc

    model = whisper.load_model(model_name)
    kwargs: dict[str, Any] = {"fp16": False}
    if language and language != "auto":
        kwargs["language"] = language
    result = model.transcribe(str(audio_wav), **kwargs)
    detected = str(result.get("language", language or "auto"))
    full_text = str(result.get("text", "")).strip()
    segments: list[dict[str, Any]] = []
    for seg in result.get("segments", []):
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        segments.append(
            {
                "start_sec": round(float(seg.get("start", 0)), 3),
                "end_sec": round(float(seg.get("end", 0)), 3),
                "text_zh": text,
            }
        )
    return full_text, detected, segments


def _merge_short_segments(
    segments: list[dict[str, Any]],
    min_duration: float = 1.5,
    max_gap: float = 0.6,
) -> list[dict[str, Any]]:
    if not segments or min_duration <= 0:
        return segments

    merged: list[dict[str, Any]] = []
    bucket = dict(segments[0])
    bucket_text = [str(bucket.get("text_zh", "")).strip()]

    for seg in segments[1:]:
        gap = float(seg["start_sec"]) - float(bucket["end_sec"])
        duration = float(bucket["end_sec"]) - float(bucket["start_sec"])
        if duration < min_duration or gap <= max_gap:
            bucket["end_sec"] = seg["end_sec"]
            text = str(seg.get("text_zh", "")).strip()
            if text:
                bucket_text.append(text)
            continue
        bucket["text_zh"] = " ".join(part for part in bucket_text if part)
        merged.append(bucket)
        bucket = dict(seg)
        bucket_text = [str(bucket.get("text_zh", "")).strip()]

    bucket["text_zh"] = " ".join(part for part in bucket_text if part)
    merged.append(bucket)
    return merged


def analyze_reference(
    config: dict[str, Any],
    work_dir: Path,
    *,
    input_path: Path | None = None,
    url: str = "",
) -> dict[str, Any]:
    ref_dir = work_dir / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)
    source_mp4 = ref_dir / "source.mp4"

    target_path = resolve_target_video_path(config, input_path=input_path, url=url)
    if target_path is not None:
        copy_local_video(target_path, source_mp4)
    elif url:
        download_reference_video(url, source_mp4)
    elif source_mp4.exists():
        pass
    else:
        raise SystemExit(
            "No target video. Provide --input, --url, target_input, or reference_input in config."
        )

    video_meta = probe_video(source_mp4)
    audio_m4a = ref_dir / "source.audio.m4a"
    extract_audio_from_video(source_mp4, audio_m4a)
    audio_wav = ref_dir / "audio.wav"
    audio_to_wav(audio_m4a, audio_wav, sample_rate=16000)

    whisper_model = str(config.get("whisper_model", "base"))
    whisper_language = str(config.get("whisper_language", "auto"))
    full_text, detected_lang, segments = _transcribe_audio(audio_wav, whisper_language, whisper_model)
    min_seg = float(config.get("merge_min_segment_sec", 1.5))
    segments = _merge_short_segments(segments, min_duration=min_seg)

    if not segments and full_text:
        duration = video_meta["duration_sec"]
        segments = [
            {
                "start_sec": 0.0,
                "end_sec": round(duration, 3),
                "text_zh": full_text,
            }
        ]

    transcript = {
        "language": detected_lang,
        "whisper_language_setting": whisper_language,
        "full_text": full_text,
        "segments": segments,
        "duration_sec": video_meta["duration_sec"],
    }
    save_json(ref_dir / "transcript.json", transcript)

    manifest = {
        "source": str(source_mp4.relative_to(work_dir)),
        "duration_sec": video_meta["duration_sec"],
        "width": video_meta["width"],
        "height": video_meta["height"],
        "fps": video_meta["fps"],
        "segment_count": len(segments),
    }
    save_json(ref_dir / "reference_manifest.json", manifest)

    config["duration_sec"] = video_meta["duration_sec"]
    config["width"] = video_meta["width"]
    config["height"] = video_meta["height"]
    config["fps"] = video_meta["fps"]
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze viral clip reference.")
    parser.add_argument("--config", default="")
    parser.add_argument("--work-dir", default="")
    parser.add_argument("--input", default="", help="Local mp4 path")
    parser.add_argument("--url", default="", help="Douyin URL")
    parser.add_argument("--id", default="", help="Clip id for work dir")
    args = parser.parse_args()

    if args.config:
        config_path = Path(args.config).resolve()
        config = load_json(config_path)
        work_dir = resolve_work_dir(config_path)
    else:
        from lib import DEFAULT_OUTPUT_ROOT, ensure_config

        clip_id = args.id or "demo-clip"
        work_dir = (Path(args.work_dir).resolve() if args.work_dir else DEFAULT_OUTPUT_ROOT / clip_id)
        work_dir.mkdir(parents=True, exist_ok=True)
        config_path = ensure_config(work_dir, clip_id)
        config = load_json(config_path)

    input_path = Path(args.input).expanduser() if args.input else None
    manifest = analyze_reference(config, work_dir, input_path=input_path, url=args.url)
    save_json(work_dir / "config.json", config)

    print(f"Reference analyzed: {work_dir / 'reference' / 'source.mp4'}")
    print(f"Duration: {manifest['duration_sec']}s, segments: {manifest['segment_count']}")


if __name__ == "__main__":
    main()
