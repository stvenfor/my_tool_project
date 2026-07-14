#!/usr/bin/env python3
"""Download Douyin reference video and extract a clean voice sample."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent
DOUYIN_DOWNLOADER = PROJECT_ROOT / "scripts" / "cffex-daily" / "douyin" / "download-for-montage.mjs"
DOUYIN_NETWORK_DOWNLOADER = DOUYIN_DOWNLOADER.parent / "download_douyin_ref.mjs"

sys.path.insert(0, str(ROOT))

from lib import load_json, resolve_work_dir, save_json  # noqa: E402


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    print("$", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd or PROJECT_ROOT, capture_output=True, text=True)


def download_reference_video(url: str, output_mp4: Path) -> None:
    output_mp4.parent.mkdir(parents=True, exist_ok=True)

    if DOUYIN_NETWORK_DOWNLOADER.exists():
        result = _run(
            ["node", str(DOUYIN_NETWORK_DOWNLOADER), "--url", url, "--output", str(output_mp4)],
            cwd=DOUYIN_DOWNLOADER.parent,
        )
        if result.returncode == 0 and output_mp4.exists() and output_mp4.stat().st_size > 10000:
            return
        print(result.stderr or result.stdout, file=sys.stderr)

    if DOUYIN_DOWNLOADER.exists():
        result = _run(
            ["node", str(DOUYIN_DOWNLOADER), "--url", url, "--output", str(output_mp4)]
        )
        if result.returncode == 0 and output_mp4.exists() and output_mp4.stat().st_size > 10000:
            return
        print(result.stderr or result.stdout, file=sys.stderr)

    if shutil.which("yt-dlp"):
        for browser in ("chrome", "safari", "edge"):
            result = _run(
                [
                    "yt-dlp",
                    "--cookies-from-browser",
                    browser,
                    "-f",
                    "best[ext=mp4]/best",
                    "-o",
                    str(output_mp4),
                    url,
                ]
            )
            if result.returncode == 0 and output_mp4.exists() and output_mp4.stat().st_size > 10000:
                return
            print(result.stderr or result.stdout, file=sys.stderr)

    raise SystemExit(
        "Failed to download reference video. "
        "Try `node modules/shared/douyin/auth.mjs` for Douyin login, "
        "or `fetch_voice_reference.py --ref-audio <wav>` / `--ref-video <mp4>`."
    )


def extract_audio(input_video: Path, output_wav: Path, sample_rate: int = 16000) -> None:
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    audio_sidecar = input_video.with_suffix(".audio.m4a")
    input_path = audio_sidecar if audio_sidecar.exists() else input_video
    result = _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-af",
            "highpass=f=120,lowpass=f=7000,loudnorm=I=-18:TP=-2:LRA=8",
            str(output_wav),
        ]
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr)


def _load_mono_audio(path: Path) -> tuple[np.ndarray, int]:
    try:
        import soundfile as sf

        audio, sample_rate = sf.read(str(path), dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        return audio.astype(np.float32), int(sample_rate)
    except Exception:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-i",
                str(path),
                "-f",
                "f32le",
                "-acodec",
                "pcm_f32le",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-",
            ],
            capture_output=True,
        )
        if proc.returncode != 0:
            raise SystemExit(proc.stderr.decode())
        audio = np.frombuffer(proc.stdout, dtype=np.float32)
        return audio, 16000


def _frame_rms(audio: np.ndarray, sample_rate: int, frame_ms: int = 30) -> np.ndarray:
    frame_len = max(1, int(sample_rate * frame_ms / 1000))
    pad = (-len(audio)) % frame_len
    if pad:
        audio = np.pad(audio, (0, pad))
    frames = audio.reshape(-1, frame_len)
    return np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)


def select_voice_segment(
    audio: np.ndarray,
    sample_rate: int,
    min_sec: float = 8.0,
    max_sec: float = 12.0,
) -> tuple[int, int]:
    rms = _frame_rms(audio, sample_rate)
    frame_sec = 0.03
    threshold = max(float(np.percentile(rms, 60)), float(np.mean(rms) * 1.1))

    voiced = rms >= threshold
    min_frames = int(math.ceil(min_sec / frame_sec))
    max_frames = int(math.floor(max_sec / frame_sec))

    best_start = 0
    best_score = -1.0
    best_len = min_frames

    for start in range(0, max(1, len(voiced) - min_frames)):
        if not voiced[start]:
            continue
        length = 0
        while start + length < len(voiced) and voiced[start + length] and length < max_frames:
            length += 1
        if length < min_frames:
            continue
        window = rms[start : start + length]
        score = float(np.mean(window))
        if score > best_score:
            best_score = score
            best_start = start
            best_len = length

    if best_score < 0:
        total_frames = min(len(rms), max_frames)
        if total_frames < min_frames:
            total_frames = min(len(rms), min_frames)
        best_start = max(0, len(rms) // 4)
        best_len = total_frames

    start_sample = int(best_start * frame_sec * sample_rate)
    end_sample = int((best_start + best_len) * frame_sec * sample_rate)
    end_sample = min(end_sample, len(audio))
    if end_sample - start_sample < int(min_sec * sample_rate * 0.8):
        end_sample = min(len(audio), start_sample + int(max_sec * sample_rate))
    return start_sample, end_sample


def save_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    import soundfile as sf

    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), audio, sample_rate, subtype="PCM_16")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and extract Douyin voice reference.")
    parser.add_argument("--config", required=True, help="Path to city.config.json")
    parser.add_argument("--ref-audio", default="", help="Manual reference WAV path")
    parser.add_argument("--ref-video", default="", help="Manual reference MP4 path")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)
    ref_dir = work_dir / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)

    ref_audio_rel = str(config.get("voice_reference_audio", "reference/voice_reference.wav"))
    ref_audio_path = work_dir / ref_audio_rel
    meta_path = ref_dir / "voice_reference.json"

    if args.ref_audio:
        manual = Path(args.ref_audio).resolve()
        if not manual.exists():
            raise SystemExit(f"Manual reference audio not found: {manual}")
        ref_audio_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(manual, ref_audio_path)
        save_json(
            meta_path,
            {
                "source_url": "manual",
                "manual_path": str(manual),
                "voice_reference_audio": ref_audio_rel,
                "duration_sec": round(len(_load_mono_audio(ref_audio_path)[0]) / 16000, 3),
            },
        )
        print(f"Manual voice reference saved: {ref_audio_path}")
        return

    if args.ref_video:
        manual_video = Path(args.ref_video).resolve()
        if not manual_video.exists():
            raise SystemExit(f"Manual reference video not found: {manual_video}")
        source_mp4 = ref_dir / "source.mp4"
        shutil.copy2(manual_video, source_mp4)
        raw_wav = ref_dir / "reference_raw.wav"
        extract_audio(source_mp4, raw_wav)
        audio, sample_rate = _load_mono_audio(raw_wav)
        start, end = select_voice_segment(audio, sample_rate)
        save_wav(ref_audio_path, audio[start:end], sample_rate)
        save_json(
            meta_path,
            {
                "source_url": "manual_video",
                "manual_path": str(manual_video),
                "voice_reference_audio": ref_audio_rel,
                "duration_sec": round((end - start) / sample_rate, 3),
            },
        )
        print(f"Voice reference from manual video: {ref_audio_path}")
        return

    if ref_audio_path.exists() and not args.force:
        print(f"Voice reference exists, skip download: {ref_audio_path}")
        return

    url = str(config.get("voice_reference_url", "")).strip()
    if not url:
        raise SystemExit("voice_reference_url missing in config")

    source_mp4 = ref_dir / "source.mp4"
    raw_wav = ref_dir / "reference_raw.wav"

    download_reference_video(url, source_mp4)
    extract_audio(source_mp4, raw_wav)

    audio, sample_rate = _load_mono_audio(raw_wav)
    start, end = select_voice_segment(audio, sample_rate)
    segment = audio[start:end]

    save_wav(ref_audio_path, segment, sample_rate)

    duration_sec = round((end - start) / sample_rate, 3)
    save_json(
        meta_path,
        {
            "source_url": url,
            "source_mp4": str(source_mp4.relative_to(work_dir)),
            "reference_raw": str(raw_wav.relative_to(work_dir)),
            "voice_reference_audio": ref_audio_rel,
            "start_sec": round(start / sample_rate, 3),
            "end_sec": round(end / sample_rate, 3),
            "duration_sec": duration_sec,
            "sample_rate": sample_rate,
        },
    )

    print(f"Voice reference saved: {ref_audio_path} ({duration_sec}s)")


if __name__ == "__main__":
    main()
