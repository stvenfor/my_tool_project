"""Local dialogue voice helpers (copied — no cognitive-video import)."""

from __future__ import annotations

import asyncio
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

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


