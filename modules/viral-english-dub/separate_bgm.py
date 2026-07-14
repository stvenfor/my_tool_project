#!/usr/bin/env python3
"""Separate vocals from BGM/ambient using demucs (fallback: ffmpeg attenuation)."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import audio_to_wav, get_audio_duration, load_json, resolve_work_dir, save_json  # noqa: E402


def _ffmpeg_vocal_attenuate(input_wav: Path, output_bgm: Path, duration_sec: float) -> None:
    """Fallback: suppress mid-range vocal band, keep ambience (mono-safe)."""
    fade_out = max(0.0, duration_sec - 2.0)
    af = (
        "highpass=f=120,lowpass=f=7800,"
        "equalizer=f=280:width_type=o:width=1.5:g=-8,"
        "equalizer=f=900:width_type=o:width=1.2:g=-6,"
        "equalizer=f=2500:width_type=o:width=1.0:g=-4,"
        f"afade=t=in:st=0:d=0.5,afade=t=out:st={fade_out:.3f}:d=2"
    )
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_wav),
            "-t",
            str(duration_sec),
            "-af",
            af,
            "-ac",
            "2",
            "-ar",
            "44100",
            str(output_bgm),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg bgm fallback failed")


def _separate_with_demucs(input_wav: Path, work_dir: Path) -> Path:
    stems_dir = work_dir / "reference" / "stems"
    if stems_dir.exists():
        shutil.rmtree(stems_dir)
    stems_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "demucs",
        "--two-stems",
        "vocals",
        "-n",
        "htdemucs",
        "--out",
        str(stems_dir),
        str(input_wav),
    ]
    print("$", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "demucs failed").strip())

    stem_candidates = list(stems_dir.rglob("no_vocals.wav"))
    if not stem_candidates:
        stem_candidates = list(stems_dir.rglob("*.wav"))
        stem_candidates = [p for p in stem_candidates if "vocals" not in p.name.lower()]
    if not stem_candidates:
        raise RuntimeError(f"demucs output not found under {stems_dir}")
    return stem_candidates[0]


def separate_bgm(config: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    audio_wav = work_dir / "reference" / "audio.wav"
    if not audio_wav.exists():
        raise SystemExit(f"Missing source audio: {audio_wav}")

    duration_sec = float(config.get("duration_sec", get_audio_duration(audio_wav)))
    bgm_out = work_dir / "reference" / "bgm_stem.wav"
    vocals_out = work_dir / "reference" / "vocals_stem.wav"
    method = "demucs"

    try:
        demucs_input = work_dir / "reference" / "audio_stereo.wav"
        audio_to_wav(audio_wav, demucs_input, sample_rate=44100)
        no_vocals = _separate_with_demucs(demucs_input, work_dir)
        shutil.copy2(no_vocals, bgm_out)

        vocal_candidates = list((work_dir / "reference" / "stems").rglob("vocals.wav"))
        if vocal_candidates:
            shutil.copy2(vocal_candidates[0], vocals_out)
    except Exception as exc:
        print(f"demucs unavailable ({exc}); using ffmpeg vocal attenuation fallback.")
        method = "ffmpeg_fallback"
        _ffmpeg_vocal_attenuate(audio_wav, bgm_out, duration_sec)

    payload = {
        "method": method,
        "bgm_stem": str(bgm_out.relative_to(work_dir)),
        "duration_sec": get_audio_duration(bgm_out),
    }
    save_json(work_dir / "reference" / "bgm_separation.json", payload)
    print(f"BGM stem: {bgm_out} ({payload['duration_sec']:.2f}s, method={method})")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Separate BGM from vocals.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)
    separate_bgm(config, work_dir)


if __name__ == "__main__":
    main()
