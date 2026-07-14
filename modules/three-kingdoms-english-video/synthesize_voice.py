#!/usr/bin/env python3
"""Synthesize English narration per subtitle segment for A/V sync."""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import (  # noqa: E402
    default_english_rate,
    default_english_voice,
    fit_audio_duration,
    get_audio_duration,
    load_json,
    resolve_work_dir,
    save_json,
)


async def _synthesize_edge_tts(text: str, voice: str, output_path: Path, rate: str) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(str(output_path))


def _normalize_wav(input_wav: Path, output_wav: Path, sample_rate: int = 44100) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_wav),
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            str(output_wav),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _make_silence(output_wav: Path, duration_sec: float, sample_rate: int = 44100) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r={sample_rate}:cl=mono",
            "-t",
            str(duration_sec),
            str(output_wav),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _concat_wavs(parts: list[Path], output_wav: Path, gap_sec: float = 0.0) -> None:
    if not parts:
        raise RuntimeError("No narration segments to concat")
    if len(parts) == 1:
        _normalize_wav(parts[0], output_wav)
        return

    list_file = output_wav.with_suffix(".txt")
    lines: list[str] = []
    for index, part in enumerate(parts):
        lines.append(f"file '{part.resolve()}'")
        if index < len(parts) - 1 and gap_sec > 0:
            gap = part.with_name(f"gap_{index}.wav")
            _make_silence(gap, gap_sec)
            lines.append(f"file '{gap.resolve()}'")
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-ac",
            "1",
            "-ar",
            "44100",
            "-c:a",
            "pcm_s16le",
            str(output_wav),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _soften_narration(input_wav: Path, output_wav: Path, volume: float) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_wav),
            "-af",
            f"highpass=f=90,lowpass=f=9000,volume={volume:.2f},dynaudnorm=f=75:g=7",
            "-ac",
            "1",
            "-ar",
            "44100",
            str(output_wav),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _scale_segments(
    segments: list[dict[str, Any]],
    hook_duration: float,
    gap_sec: float,
    ratio: float,
    target_sec: float,
) -> list[dict[str, Any]]:
    scaled: list[dict[str, Any]] = []
    cursor = hook_duration * ratio
    scaled_gap = gap_sec * ratio

    for index, seg in enumerate(segments):
        duration = round(float(seg["duration_sec"]) * ratio, 3)
        start = round(cursor, 3)
        scaled.append(
            {
                "start_sec": start,
                "duration_sec": duration,
                "en": seg["en"],
                "zh": seg.get("zh", ""),
                "visual_keyword": seg.get("visual_keyword", ""),
                "landmark": seg.get("landmark", ""),
                "phase": seg.get("phase", "day"),
            }
        )
        cursor += duration
        if index < len(segments) - 1:
            cursor += scaled_gap

    if scaled:
        last = scaled[-1]
        end = last["start_sec"] + last["duration_sec"]
        if end > target_sec:
            last["duration_sec"] = round(max(0.8, target_sec - last["start_sec"]), 3)
        if last["start_sec"] >= target_sec:
            last["start_sec"] = round(max(hook_duration * ratio, target_sec - last["duration_sec"]), 3)

    return scaled


def synthesize_fixed_timing_narration(config: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    """Place TTS at subtitle start_sec; pad silence to preserve reference timing."""
    subtitles_path = work_dir / "subtitles.json"
    subtitles = load_json(subtitles_path)
    segments = subtitles.get("segments", [])
    target_sec = float(config.get("duration_sec", subtitles.get("duration_sec", 141.767)))
    hook_duration = float(subtitles.get("hook_duration_sec", 3.36))
    voice = default_english_voice(config)
    rate = default_english_rate(config)
    narration_volume = float(config.get("narration_post_volume", 0.85))

    with tempfile.TemporaryDirectory(prefix="tk-english-voice-") as tmp:
        tmp_dir = Path(tmp)
        timeline = tmp_dir / "timeline.wav"
        _make_silence(timeline, target_sec)

        for index, seg in enumerate(segments):
            text = str(seg.get("en", "")).strip()
            if not text:
                continue
            start_sec = float(seg.get("start_sec", 0))
            window_sec = float(seg.get("duration_sec", 3.0))
            raw_part = tmp_dir / f"seg_{index:02d}.raw.wav"
            part_wav = tmp_dir / f"seg_{index:02d}.wav"
            asyncio.run(_synthesize_edge_tts(text, voice, raw_part, rate))
            _normalize_wav(raw_part, part_wav)
            tts_dur = get_audio_duration(part_wav)
            if tts_dur > window_sec and window_sec > 0.3:
                fitted = tmp_dir / f"seg_{index:02d}.fit.wav"
                fit_audio_duration(part_wav, fitted, window_sec * 0.95)
                part_wav.write_bytes(fitted.read_bytes())
                tts_dur = get_audio_duration(part_wav)

            padded = tmp_dir / f"seg_{index:02d}.pad.wav"
            _make_silence(padded, max(0.01, window_sec - min(tts_dur, window_sec)))
            seg_track = tmp_dir / f"seg_{index:02d}.track.wav"
            if tts_dur >= window_sec * 0.99:
                seg_track.write_bytes(part_wav.read_bytes())
            else:
                _concat_wavs([part_wav, padded], seg_track, gap_sec=0.0)

            mixed = tmp_dir / f"mix_{index:02d}.wav"
            delay_ms = max(0, int(start_sec * 1000))
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(timeline),
                    "-i",
                    str(seg_track),
                    "-filter_complex",
                    f"[1:a]adelay={delay_ms}|{delay_ms}[d];[0:a][d]amix=inputs=2:duration=first:dropout_transition=0",
                    "-ac",
                    "1",
                    "-ar",
                    "44100",
                    str(mixed),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            timeline = mixed

        softened = tmp_dir / "narration_soft.wav"
        _soften_narration(timeline, softened, narration_volume)
        narration_wav = work_dir / "narration.wav"
        _normalize_wav(softened, narration_wav)

        subtitles["duration_sec"] = target_sec
        save_json(subtitles_path, subtitles)
        (work_dir / "narration.en.txt").write_text(
            "\n".join(str(s.get("en", "")) for s in segments if s.get("en")) + "\n",
            encoding="utf-8",
        )
        return {
            "duration_sec": get_audio_duration(narration_wav),
            "segments": len(segments),
            "voice": voice,
            "rate": rate,
            "stretch_ratio": 1.0,
            "mode": "fixed_timing",
        }


def synthesize_aligned_narration(config: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    if str(config.get("narration_timing", "")) == "fixed":
        return synthesize_fixed_timing_narration(config, work_dir)
    subtitles_path = work_dir / "subtitles.json"
    if not subtitles_path.exists():
        raise SystemExit(f"Missing subtitles: {subtitles_path}")

    subtitles = load_json(subtitles_path)
    segments = subtitles.get("segments", [])
    if not segments:
        raise SystemExit("No subtitle segments found")

    hook_duration = float(subtitles.get("hook_duration_sec", config.get("hook_duration_sec", 2.5)))
    target_sec = float(config.get("duration_sec", 51.233))
    voice = default_english_voice(config)
    rate = default_english_rate(config)
    gap_sec = float(config.get("narration_gap_sec", 0.18))
    narration_volume = float(config.get("narration_post_volume", 0.72))

    aligned_segments: list[dict[str, Any]] = []
    part_paths: list[Path] = []

    with tempfile.TemporaryDirectory(prefix="city-bilingual-voice-") as tmp:
        tmp_dir = Path(tmp)
        cursor = hook_duration

        for index, seg in enumerate(segments):
            text = str(seg.get("en", "")).strip()
            if not text:
                continue
            part_wav = tmp_dir / f"seg_{index:02d}.wav"
            raw_part = tmp_dir / f"seg_{index:02d}.raw.wav"
            asyncio.run(_synthesize_edge_tts(text, voice, raw_part, rate))
            _normalize_wav(raw_part, part_wav)
            duration = get_audio_duration(part_wav)
            aligned_segments.append(
                {
                    "start_sec": round(cursor, 3),
                    "duration_sec": round(duration, 3),
                    "en": text,
                    "zh": seg.get("zh", ""),
                    "visual_keyword": seg.get("visual_keyword", ""),
                    "landmark": seg.get("landmark", ""),
                    "phase": seg.get("phase", "day"),
                }
            )
            part_paths.append(part_wav)
            cursor += duration + gap_sec

        narration_body = tmp_dir / "narration_body.wav"
        _concat_wavs(part_paths, narration_body, gap_sec=gap_sec)

        hook_pad = tmp_dir / "hook_pad.wav"
        _make_silence(hook_pad, hook_duration)
        raw_concat = tmp_dir / "narration_concat.wav"
        _concat_wavs([hook_pad, narration_body], raw_concat, gap_sec=0.0)
        raw_duration = get_audio_duration(raw_concat)

        softened = tmp_dir / "narration_soft.wav"
        _soften_narration(raw_concat, softened, narration_volume)

        narration_wav = work_dir / "narration.wav"
        final_duration = fit_audio_duration(softened, narration_wav, target_sec)

        ratio = final_duration / raw_duration if raw_duration > 0 else 1.0
        synced_segments = _scale_segments(
            aligned_segments,
            hook_duration=hook_duration,
            gap_sec=gap_sec,
            ratio=ratio,
            target_sec=target_sec,
        )

        subtitles["segments"] = synced_segments
        subtitles["duration_sec"] = target_sec
        save_json(subtitles_path, subtitles)

        narration_lines = [seg["en"] for seg in synced_segments]
        (work_dir / "narration.en.txt").write_text("\n".join(narration_lines) + "\n", encoding="utf-8")

        return {
            "duration_sec": final_duration,
            "segments": len(synced_segments),
            "voice": voice,
            "rate": rate,
            "stretch_ratio": round(ratio, 4),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthesize aligned English narration.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)

    result = synthesize_aligned_narration(config, work_dir)
    print(
        f"Narration: {work_dir / 'narration.wav'} "
        f"({result['duration_sec']:.2f}s, {result['segments']} synced segments)"
    )
    print(f"Voice: {result['voice']}, rate: {result['rate']}, stretch: {result['stretch_ratio']}")
    print(f"Synced subtitles: {work_dir / 'subtitles.json'}")


if __name__ == "__main__":
    main()
