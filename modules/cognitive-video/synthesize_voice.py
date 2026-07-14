#!/usr/bin/env python3
"""Synthesize Chinese narration with natural pacing (no aggressive time-stretch)."""

from __future__ import annotations

import argparse
import asyncio
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import (  # noqa: E402
    default_chinese_pitch,
    default_chinese_rate,
    default_chinese_voice,
    default_chinese_volume,
    get_audio_duration,
    load_json,
    resolve_work_dir,
    save_json,
    segment_gap_for_phase,
    voice_rhythm_config,
)


def _prepare_narration_text(text: str) -> str:
    """Light spacing after punctuation — edge-tts SSML breaks are unreliable."""
    text = text.strip()
    text = re.sub(r"([。！？；])", r"\1 ", text)
    text = re.sub(r"([，、])", r"\1 ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _split_clauses(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？；])", text.strip())
    return [p.strip() for p in parts if p.strip()]


async def _synthesize_clause(
    text: str,
    voice: str,
    output_path: Path,
    rate: str,
    pitch: str,
    volume: str,
) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(
        _prepare_narration_text(text),
        voice,
        rate=rate,
        pitch=pitch,
        volume=volume,
    )
    await communicate.save(str(output_path))


def _split_phrases(text: str) -> list[str]:
    """Split into speakable phrases at sentence and comma boundaries."""
    phrases: list[str] = []
    for clause in _split_clauses(text):
        chunks = re.split(r"(?<=[，、])", clause)
        for chunk in chunks:
            chunk = chunk.strip()
            if chunk:
                phrases.append(chunk)
    return phrases if phrases else [text.strip()]


def _parse_rate_percent(rate: str) -> int:
    match = re.match(r"([+-]?\d+)%", rate.strip())
    return int(match.group(1)) if match else 0


def _parse_pitch_hz(pitch: str) -> int:
    match = re.match(r"([+-]?\d+)Hz", pitch.strip())
    return int(match.group(1)) if match else 0


def _format_rate(percent: int) -> str:
    return f"{percent:+d}%"


def _format_pitch(hz: int) -> str:
    return f"{hz:+d}Hz"


def _gap_after_phrase(phrase: str, rhythm: dict[str, Any]) -> float:
    if re.search(r"[。！？；!?]$", phrase):
        return float(rhythm.get("strong_clause_gap_ms", 320)) / 1000.0
    if re.search(r"[，、]$", phrase):
        return float(rhythm.get("comma_clause_gap_ms", 150)) / 1000.0
    return float(rhythm.get("clause_gap_ms", 220)) / 1000.0


def _prosody_for_phrase(
    phase: str,
    index: int,
    total: int,
    base_rate: str,
    base_pitch: str,
    rhythm: dict[str, Any],
) -> tuple[str, str]:
    """Alternate rate/pitch across phrases for stronger 抑扬顿挫."""
    rate_val = _parse_rate_percent(base_rate)
    pitch_val = _parse_pitch_hz(base_pitch)

    phase_delta = (rhythm.get("prosody_by_phase") or {}).get(phase, {})
    rate_val += int(phase_delta.get("rate_delta", 0))
    pitch_val += int(phase_delta.get("pitch_delta", 0))

    if index == 0:
        rate_val -= int(rhythm.get("opening_rate_drop_pct", 4))
    if index == total - 1 and total > 1:
        rate_val += int(rhythm.get("closing_rate_boost_pct", 4))

    if index % 2 == 1:
        pitch_val += int(rhythm.get("pitch_bounce_hz", 3))
        rate_val += int(rhythm.get("rate_bounce_pct", 2))
    elif index % 2 == 0 and index > 0:
        pitch_val -= int(rhythm.get("pitch_dip_hz", 1))

    rate_val = max(-50, min(80, rate_val))
    pitch_val = max(-20, min(20, pitch_val))
    return _format_rate(rate_val), _format_pitch(pitch_val)


async def _synthesize_segment(
    text: str,
    voice: str,
    output_wav: Path,
    rate: str,
    pitch: str,
    volume: str,
    rhythm: dict[str, Any],
    phase: str = "insight",
) -> None:
    phrases = _split_phrases(text)
    if len(phrases) <= 1:
        phrase_rate, phrase_pitch = _prosody_for_phrase(phase, 0, 1, rate, pitch, rhythm)
        with tempfile.TemporaryDirectory(prefix="cognitive-clause-") as tmp:
            raw = Path(tmp) / "single.mp3"
            await _synthesize_clause(text, voice, raw, phrase_rate, phrase_pitch, volume)
            _normalize_wav(raw, output_wav)
        return

    with tempfile.TemporaryDirectory(prefix="cognitive-clause-") as tmp:
        tmp_dir = Path(tmp)
        parts: list[Path] = []
        gaps: list[float] = []
        total = len(phrases)
        for index, phrase in enumerate(phrases):
            phrase_rate, phrase_pitch = _prosody_for_phrase(
                phase, index, total, rate, pitch, rhythm
            )
            raw = tmp_dir / f"phrase_{index:02d}.mp3"
            wav = tmp_dir / f"phrase_{index:02d}.wav"
            await _synthesize_clause(phrase, voice, raw, phrase_rate, phrase_pitch, volume)
            _normalize_wav(raw, wav)
            parts.append(wav)
            if index < total - 1:
                gaps.append(_gap_after_phrase(phrase, rhythm))
        _concat_wavs(parts, output_wav, gaps=gaps)


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
    if duration_sec <= 0:
        return
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


def _concat_wavs(parts: list[Path], output_wav: Path, gaps: list[float] | None = None) -> None:
    if not parts:
        raise RuntimeError("No narration segments to concat")
    gaps = gaps or []
    if len(parts) == 1 and not any(g > 0 for g in gaps):
        _normalize_wav(parts[0], output_wav)
        return

    list_file = output_wav.with_suffix(".txt")
    lines: list[str] = []
    for index, part in enumerate(parts):
        lines.append(f"file '{part.resolve()}'")
        if index < len(parts) - 1:
            gap_sec = gaps[index] if index < len(gaps) else 0.0
            if gap_sec > 0:
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


def _enhance_narration(
    input_wav: Path,
    output_wav: Path,
    volume: float,
    enhance: dict[str, Any],
) -> None:
    """Light polish: EQ warmth/presence + compression + limiter."""
    warmth = float(enhance.get("warmth_db", 1.2))
    presence = float(enhance.get("presence_db", 0.6))
    ratio = float(enhance.get("compressor_ratio", 2.2))
    af = (
        f"highpass=f=75,lowpass=f=11500,"
        f"equalizer=f=180:width_type=o:width=1.5:g={warmth:.1f},"
        f"equalizer=f=2800:width_type=o:width=1.2:g={presence:.1f},"
        f"acompressor=threshold=-19dB:ratio={ratio:.1f}:attack=10:release=90:makeup=1.8,"
        f"alimiter=limit=0.90,"
        f"volume={volume:.2f}"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_wav),
            "-af",
            af,
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


def synthesize_narration(config: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    script_path = work_dir / "script.json"
    if not script_path.exists():
        raise SystemExit(f"Missing script: {script_path}")

    script = load_json(script_path)
    segments = script.get("segments", [])
    if not segments:
        raise SystemExit("No script segments found")

    hook_duration = float(config.get("hook_duration_sec", 2.8))
    tail_padding = float(config.get("tail_padding_sec", 3.5))
    voice = default_chinese_voice(config)
    rate = default_chinese_rate(config)
    pitch = default_chinese_pitch(config)
    volume = default_chinese_volume(config)
    rhythm = voice_rhythm_config(config)
    enhance = config.get("voice_enhance") or {}
    narration_volume = float(config.get("narration_volume", 1.0))

    aligned_segments: list[dict[str, Any]] = []
    part_paths: list[Path] = []
    segment_gaps: list[float] = []

    with tempfile.TemporaryDirectory(prefix="cognitive-voice-") as tmp:
        tmp_dir = Path(tmp)
        cursor = hook_duration if hook_duration > 0 else 0.0

        for index, seg in enumerate(segments):
            text = str(seg.get("narration", "")).strip()
            if not text:
                continue
            phase = str(seg.get("phase", "insight"))
            part_wav = tmp_dir / f"seg_{index:02d}.wav"
            asyncio.run(
                _synthesize_segment(
                    text, voice, part_wav, rate, pitch, volume, rhythm, phase=phase
                )
            )
            duration = get_audio_duration(part_wav)
            aligned_segments.append(
                {
                    "start_sec": round(cursor, 3),
                    "duration_sec": round(duration, 3),
                    "zh": text,
                    "emphasis": seg.get("emphasis", []),
                    "visual_keyword": seg.get("visual_keyword", ""),
                    "phase": phase,
                    "id": seg.get("id", f"seg_{index + 1:02d}"),
                }
            )
            part_paths.append(part_wav)
            if index < len(segments) - 1:
                gap = segment_gap_for_phase(config, phase)
                segment_gaps.append(gap)
                cursor += duration + gap
            else:
                cursor += duration

        narration_body = tmp_dir / "narration_body.wav"
        _concat_wavs(part_paths, narration_body, gaps=segment_gaps)

        hook_pad = tmp_dir / "hook_pad.wav"
        if hook_duration > 0:
            _make_silence(hook_pad, hook_duration)
        tail_pad = tmp_dir / "tail_pad.wav"
        _make_silence(tail_pad, tail_padding)

        raw_concat = tmp_dir / "narration_concat.wav"
        concat_parts = ([hook_pad] if hook_duration > 0 else []) + [narration_body, tail_pad]
        _concat_wavs(concat_parts, raw_concat, gaps=[])

        final_duration = get_audio_duration(raw_concat)

        enhanced = tmp_dir / "narration_enhanced.wav"
        _enhance_narration(raw_concat, enhanced, narration_volume, enhance)

        narration_wav = work_dir / "narration.wav"
        subprocess.run(
            ["cp", str(enhanced), str(narration_wav)],
            check=True,
        )

        target_sec = round(final_duration, 3)
        subtitles = {
            "hook_zh": script.get("hook", ""),
            "hook_duration_sec": hook_duration,
            "duration_sec": target_sec,
            "tail_padding_sec": tail_padding,
            "segments": aligned_segments,
        }
        save_json(work_dir / "subtitles.json", subtitles)
        (work_dir / "narration.zh.txt").write_text(
            "\n".join(seg["zh"] for seg in aligned_segments) + "\n",
            encoding="utf-8",
        )

        return {
            "duration_sec": target_sec,
            "segments": len(aligned_segments),
            "voice": voice,
            "rate": rate,
            "pitch": pitch,
            "volume": volume,
            "rhythm": rhythm,
            "stretch_ratio": 1.0,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthesize Chinese narration.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)

    result = synthesize_narration(config, work_dir)
    config["duration_sec"] = result["duration_sec"]
    save_json(config_path, config)

    rhythm = result["rhythm"]
    print(
        f"Narration: {work_dir / 'narration.wav'} "
        f"({result['duration_sec']:.2f}s, {result['segments']} segments)"
    )
    print(
        f"Voice: {result['voice']}, rate: {result['rate']}, "
        f"pitch: {result['pitch']}, volume: {result['volume']}"
    )
    print(
        "Rhythm: "
        f"强停{rhythm.get('strong_clause_gap_ms', 320)}ms, "
        f"逗停{rhythm.get('comma_clause_gap_ms', 150)}ms, "
        f"段间{rhythm['segment_gap_by_phase']}"
    )
    print(f"Synced subtitles: {work_dir / 'subtitles.json'}")


if __name__ == "__main__":
    main()
