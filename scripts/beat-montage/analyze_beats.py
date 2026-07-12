#!/usr/bin/env python3
"""Analyze audio beats and section boundaries for beat-sync montage."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import struct
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect beats and sections from an audio file.")
    parser.add_argument("audio", help="Path to mp3/wav audio")
    parser.add_argument(
        "--output",
        default=str(ROOT / "output" / "beats.json"),
        help="Output beats.json path",
    )
    parser.add_argument("--max-duration", type=float, default=45.0, help="Trim analysis to first N seconds")
    parser.add_argument("--default-bpm", type=float, default=128.0, help="Fallback BPM when detection fails")
    return parser.parse_args()


def _to_wav(audio_path: Path) -> Path:
    if audio_path.suffix.lower() == ".wav":
        return audio_path

    if shutil.which("afconvert"):
        tmp = Path(tempfile.mkstemp(suffix=".wav")[1])
        subprocess.run(
            [
                "afconvert",
                str(audio_path),
                str(tmp),
                "-d",
                "LEI16",
                "-f",
                "WAVE",
                "-c",
                "1",
                "-r",
                "22050",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return tmp

    raise RuntimeError("Cannot decode audio: install macOS afconvert or provide a WAV file.")


def _load_mono_wav(wav_path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(wav_path), "rb") as wf:
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        frame_count = wf.getnframes()
        raw = wf.readframes(frame_count)

    if sample_width != 2:
        raise ValueError("Expected 16-bit PCM WAV.")

    samples = np.array(struct.unpack(f"<{frame_count * channels}h", raw), dtype=np.float32)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    samples /= 32768.0
    return samples, sample_rate


def _detect_beats_librosa(samples: np.ndarray, sample_rate: int) -> tuple[list[float], float]:
    import librosa

    onset_env = librosa.onset.onset_strength(y=samples, sr=sample_rate)
    tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sample_rate)
    beat_times = librosa.frames_to_time(beat_frames, sr=sample_rate).tolist()
    bpm = float(tempo) if np.ndim(tempo) == 0 else float(tempo[0])
    return beat_times, bpm


def _detect_beats_kick(samples: np.ndarray, sample_rate: int, default_bpm: float) -> tuple[list[float], float]:
    """Kick-focused onset detection without librosa (works when librosa/_lzma unavailable)."""
    frame = max(1, int(sample_rate * 0.046))
    hop = max(1, frame // 2)
    if len(samples) < frame * 8:
        interval = 60.0 / default_bpm
        duration = len(samples) / sample_rate
        return [round(i * interval, 3) for i in range(int(duration / interval) + 1)], default_bpm

    short: list[float] = []
    long: list[float] = []
    long_frame = frame * 4
    for start in range(0, len(samples) - long_frame, hop):
        chunk_s = samples[start : start + frame]
        chunk_l = samples[start : start + long_frame]
        short.append(float(np.sqrt(np.mean(chunk_s * chunk_s))))
        long.append(float(np.sqrt(np.mean(chunk_l * chunk_l))))

    short_arr = np.array(short, dtype=np.float32)
    long_arr = np.array(long, dtype=np.float32)
    flux = np.maximum(short_arr - long_arr * 0.85, 0.0)
    if flux.max() <= 0:
        interval = 60.0 / default_bpm
        duration = len(samples) / sample_rate
        return [round(i * interval, 3) for i in range(int(duration / interval) + 1)], default_bpm

    flux = flux / flux.max()
    smooth = np.convolve(flux, np.ones(5) / 5.0, mode="same")
    interval = 60.0 / default_bpm
    min_gap = max(1, int(interval * sample_rate / hop * 0.55))

    peaks: list[int] = []
    threshold = float(np.percentile(smooth, 78))
    for idx in range(1, len(smooth) - 1):
        if smooth[idx] >= threshold and smooth[idx] >= smooth[idx - 1] and smooth[idx] > smooth[idx + 1]:
            if peaks and idx - peaks[-1] < min_gap:
                if smooth[idx] > smooth[peaks[-1]]:
                    peaks[-1] = idx
                continue
            peaks.append(idx)

    if len(peaks) < 4:
        duration = len(samples) / sample_rate
        return [round(i * interval, 3) for i in range(int(duration / interval) + 1)], default_bpm

    beat_times = [round((idx * hop) / sample_rate, 3) for idx in peaks]
    intervals = np.diff(beat_times)
    median_interval = float(np.median(intervals))
    bpm = 60.0 / median_interval if median_interval > 0 else default_bpm
    return beat_times, round(min(170.0, max(80.0, bpm)), 2)


def _detect_beats_energy(samples: np.ndarray, sample_rate: int, default_bpm: float) -> tuple[list[float], float]:
    frame = max(1, int(sample_rate * 0.04))
    hop = max(1, frame // 2)
    if len(samples) < frame * 4:
        duration = len(samples) / sample_rate
        beat_interval = 60.0 / default_bpm
        beats = [round(i * beat_interval, 3) for i in range(int(duration / beat_interval) + 1)]
        return beats, default_bpm

    energy = []
    for start in range(0, len(samples) - frame, hop):
        chunk = samples[start : start + frame]
        energy.append(float(np.sqrt(np.mean(chunk * chunk))))

    energy = np.array(energy, dtype=np.float32)
    if energy.max() <= 0:
        duration = len(samples) / sample_rate
        beat_interval = 60.0 / default_bpm
        beats = [round(i * beat_interval, 3) for i in range(int(duration / beat_interval) + 1)]
        return beats, default_bpm

    smooth = np.convolve(energy, np.ones(5) / 5.0, mode="same")
    threshold = float(np.percentile(smooth, 70))
    peaks: list[int] = []
    min_gap = max(1, int((60.0 / default_bpm) * sample_rate / hop * 0.45))
    for idx in range(1, len(smooth) - 1):
        if smooth[idx] >= threshold and smooth[idx] > smooth[idx - 1] and smooth[idx] >= smooth[idx + 1]:
            if peaks and idx - peaks[-1] < min_gap:
                if smooth[idx] > smooth[peaks[-1]]:
                    peaks[-1] = idx
                continue
            peaks.append(idx)

    beat_times = [round((idx * hop) / sample_rate, 3) for idx in peaks]
    if len(beat_times) < 4:
        duration = len(samples) / sample_rate
        beat_interval = 60.0 / default_bpm
        beat_times = [round(i * beat_interval, 3) for i in range(int(duration / beat_interval) + 1)]
        return beat_times, default_bpm

    intervals = np.diff(beat_times)
    median_interval = float(np.median(intervals))
    bpm = 60.0 / median_interval if median_interval > 0 else default_bpm
    return beat_times, round(bpm, 2)


def _trim_beats(beat_times: list[float], max_duration: float) -> list[float]:
    beats = [round(t, 3) for t in beat_times if t <= max_duration]
    if not beats or beats[0] != 0.0:
        beats = [0.0] + [b for b in beats if b > 0.0]
    return beats


def _build_sections(duration: float) -> list[dict[str, float | str]]:
    if duration <= 0:
        return []

    cold_end = min(duration * 0.2, 8.0)
    warm_end = min(duration * 0.45, cold_end + 10.0)
    hot_end = min(duration * 0.85, warm_end + 14.0)

    return [
        {"name": "cold", "start": 0.0, "end": round(cold_end, 3)},
        {"name": "warm", "start": round(cold_end, 3), "end": round(warm_end, 3)},
        {"name": "hot", "start": round(warm_end, 3), "end": round(hot_end, 3)},
        {"name": "outro", "start": round(hot_end, 3), "end": round(duration, 3)},
    ]


def _build_cut_beats(beats: list[float], bpm: float, duration: float, detector: str) -> list[float]:
    """Build a musical cut grid — action hits land on these, not micro-onsets."""
    if bpm > 170 or bpm < 80:
        bpm = 128.0
    interval = 60.0 / bpm
    grid = [round(index * interval, 3) for index in range(int(duration / interval) + 1)]
    grid = [beat for beat in grid if beat <= duration + 0.001]
    if not grid or grid[0] != 0.0:
        grid = [0.0] + [beat for beat in grid if beat > 0.0]

    if detector in {"librosa", "kick"} and len(beats) >= 8:
        merged: list[float] = [0.0]
        for beat in beats[1:]:
            if beat - merged[-1] >= interval * 0.72:
                merged.append(beat)
        if merged[-1] < duration - interval * 0.5:
            merged.append(round(duration, 3))
        return merged

    return grid


def analyze_audio(audio_path: Path, max_duration: float, default_bpm: float) -> dict:
    wav_path = _to_wav(audio_path)
    cleanup = wav_path != audio_path
    try:
        samples, sample_rate = _load_mono_wav(wav_path)
        max_samples = int(max_duration * sample_rate)
        samples = samples[:max_samples]
        duration = len(samples) / sample_rate

        try:
            beat_times, bpm = _detect_beats_librosa(samples, sample_rate)
            detector = "librosa"
        except Exception:
            beat_times, bpm = _detect_beats_kick(samples, sample_rate, default_bpm)
            detector = "kick"

        beats = _trim_beats(beat_times, duration)
        cut_beats = _build_cut_beats(beats, float(bpm), duration, detector)
        return {
            "audio": str(audio_path),
            "detector": detector,
            "bpm": round(float(bpm), 2),
            "duration": round(duration, 3),
            "sections": _build_sections(duration),
            "beats": beats,
            "cut_beats": cut_beats,
        }
    finally:
        if cleanup and wav_path.exists():
            wav_path.unlink(missing_ok=True)


def main() -> None:
    args = parse_args()
    audio_path = Path(args.audio).resolve()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = analyze_audio(audio_path, args.max_duration, args.default_bpm)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved beats: {output_path}")
    print(f"Detector={result['detector']} BPM={result['bpm']} beats={len(result['beats'])} cut_beats={len(result.get('cut_beats', []))}")


if __name__ == "__main__":
    main()
