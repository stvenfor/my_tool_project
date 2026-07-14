#!/usr/bin/env python3
"""Mix BGM stem + English narration; denoise dub track, smooth sidechained BGM."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import get_audio_duration, load_json, resolve_work_dir, save_json  # noqa: E402


def _run_ffmpeg(cmd: list[str], err_label: str) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or err_label).strip() or err_label)


def _denoise_narration(input_wav: Path, output_wav: Path, *, strength: str = "strong") -> None:
    """Remove clone hiss/artifacts; gate pauses so noise does not linger between lines."""
    strength = strength.strip().lower()
    if strength in {"off", "none", "0"}:
        af = "highpass=f=80,lowpass=f=12000,volume=0.95,alimiter=limit=0.92"
    elif strength in {"light", "mild"}:
        af = (
            "highpass=f=90,"
            "afftdn=nr=12:nf=-28:tn=1,"
            "lowpass=f=11000,"
            "agate=threshold=0.015:ratio=3:attack=8:release=180:range=0.08,"
            "acompressor=threshold=-18dB:ratio=2.2:attack=8:release=120:makeup=2,"
            "alimiter=limit=0.90"
        )
    else:
        # strong (default): FFT denoise + NLM + pause gate + gentle polish
        af = (
            "highpass=f=100,"
            "afftdn=nr=18:nf=-25:tn=1,"
            "anlmdn=s=0.0008:p=0.002:r=0.01:m=15,"
            "equalizer=f=6500:width_type=h:width=2500:g=-3,"
            "lowpass=f=10500,"
            "agate=threshold=0.012:ratio=4:attack=5:release=160:range=0.05,"
            "acompressor=threshold=-20dB:ratio=2.5:attack=6:release=140:makeup=3,"
            "loudnorm=I=-16:TP=-1.5:LRA=11,"
            "alimiter=limit=0.89"
        )
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_wav),
            "-af",
            af,
            "-ac",
            "2",
            "-ar",
            "44100",
            str(output_wav),
        ],
        "ffmpeg denoise failed",
    )


def _prepare_smooth_bgm(
    bgm_wav: Path,
    output_wav: Path,
    duration_sec: float,
    *,
    bgm_vol: float,
) -> None:
    """Stretch/pad BGM gently, clean bleed, fade edges for a continuous bed."""
    bgm_dur = get_audio_duration(bgm_wav)
    fade_out_start = max(0.0, duration_sec - 1.4)
    cleanup = (
        "highpass=f=60,lowpass=f=9000,"
        "equalizer=f=300:width_type=o:width=1.4:g=-2,"
        "equalizer=f=2200:width_type=o:width=1.2:g=-2,"
        "afftdn=nr=8:nf=-35:tn=1,"
        "acompressor=threshold=-22dB:ratio=1.8:attack=20:release=220:makeup=1,"
        f"volume={bgm_vol:.3f},"
        f"afade=t=in:st=0:d=0.35,afade=t=out:st={fade_out_start:.3f}:d=1.4"
    )

    if abs(bgm_dur - duration_sec) <= 0.08:
        af = f"{cleanup},apad=pad_dur=0.5"
        _run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(bgm_wav),
                "-af",
                af,
                "-t",
                f"{duration_sec:.3f}",
                "-ac",
                "2",
                "-ar",
                "44100",
                str(output_wav),
            ],
            "ffmpeg bgm prepare failed",
        )
        return

    # Prefer mild atempo (≤±12%); beyond that, pad/loop with short crossfade.
    tempo = bgm_dur / max(0.05, duration_sec)
    if 0.88 <= tempo <= 1.12:
        af = f"atempo={max(0.5, min(2.0, tempo)):.6f},{cleanup},apad=pad_dur=0.5"
        _run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(bgm_wav),
                "-af",
                af,
                "-t",
                f"{duration_sec:.3f}",
                "-ac",
                "2",
                "-ar",
                "44100",
                str(output_wav),
            ],
            "ffmpeg bgm retime failed",
        )
        return

    # Loop + acrossfade for large extensions (smoother than extreme atempo).
    loops = max(2, int(duration_sec / max(0.5, bgm_dur)) + 2)
    inputs: list[str] = []
    for _ in range(loops):
        inputs.extend(["-i", str(bgm_wav)])
    filter_parts: list[str] = []
    current = "[0:a]"
    for i in range(1, loops):
        out = f"[c{i}]"
        # acrossfade needs two labeled inputs
        left = current if i == 1 else f"[c{i-1}]"
        filter_parts.append(f"{left}[{i}:a]acrossfade=d=0.45:c1=tri:c2=tri{out}")
        current = out
    filter_parts.append(
        f"{current}atrim=0:{duration_sec:.3f},asetpts=PTS-STARTPTS,{cleanup}[out]"
    )
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            *inputs,
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[out]",
            "-t",
            f"{duration_sec:.3f}",
            "-ac",
            "2",
            "-ar",
            "44100",
            str(output_wav),
        ],
        "ffmpeg bgm loop-crossfade failed",
    )


def mix_final_audio(config: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    narration_wav = work_dir / "narration.wav"
    bgm_wav = work_dir / "reference" / "bgm_stem.wav"
    if not narration_wav.exists():
        raise SystemExit(f"Missing narration: {narration_wav}")
    if not bgm_wav.exists():
        raise SystemExit(f"Missing BGM stem. Run separate_bgm.py first: {bgm_wav}")

    timeline_path = work_dir / "timeline.json"
    if timeline_path.exists():
        duration_sec = float(load_json(timeline_path).get("duration_sec", 0)) or get_audio_duration(
            narration_wav
        )
    else:
        duration_sec = float(config.get("duration_sec", get_audio_duration(bgm_wav)))
    duration_sec = max(duration_sec, get_audio_duration(narration_wav))

    bgm_vol = float(config.get("bgm_volume", 0.48))
    narration_vol = float(config.get("narration_volume", 1.0))
    denoise_strength = str(config.get("denoise_strength", "strong"))
    duck = bool(config.get("bgm_sidechain_duck", True))
    duck_threshold = float(config.get("bgm_duck_threshold_db", -28))
    duck_ratio = float(config.get("bgm_duck_ratio", 4.5))

    denoised = work_dir / "narration_clean.wav"
    _denoise_narration(narration_wav, denoised, strength=denoise_strength)

    smooth_bgm = work_dir / "reference" / "bgm_smooth.wav"
    _prepare_smooth_bgm(bgm_wav, smooth_bgm, duration_sec, bgm_vol=bgm_vol)

    final_audio = work_dir / "final_audio.wav"
    pad = max(0.0, duration_sec - get_audio_duration(denoised))

    if duck:
        # asplit: sidechaincompress consumes one copy; amix needs another.
        filter_complex = (
            f"[1:a]volume={narration_vol:.3f},apad=pad_dur={pad:.3f},asplit=2[vox][vox_sc];"
            f"[0:a][vox_sc]sidechaincompress="
            f"threshold={duck_threshold}dB:ratio={duck_ratio}:attack=12:release=280:"
            f"makeup=1:knee=6:detection=rms:mix=0.85[bgm_ducked];"
            f"[bgm_ducked][vox]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
            f"alimiter=limit=0.93[out]"
        )
    else:
        filter_complex = (
            f"[0:a]apad=pad_dur={pad:.3f}[bgm];"
            f"[1:a]volume={narration_vol:.3f}[vox];"
            f"[bgm][vox]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,"
            f"alimiter=limit=0.93[out]"
        )

    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(smooth_bgm),
            "-i",
            str(denoised),
            "-filter_complex",
            filter_complex,
            "-map",
            "[out]",
            "-t",
            str(duration_sec),
            "-ac",
            "2",
            "-ar",
            "44100",
            str(final_audio),
        ],
        "ffmpeg mix failed",
    )

    payload = {
        "final_audio": str(final_audio.relative_to(work_dir)),
        "duration_sec": get_audio_duration(final_audio),
        "bgm_volume": bgm_vol,
        "narration_volume": narration_vol,
        "denoise_strength": denoise_strength,
        "bgm_sidechain_duck": duck,
    }
    save_json(work_dir / "audio_mix.json", payload)
    print(f"Final audio mix: {final_audio} ({payload['duration_sec']:.2f}s)")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Mix BGM stem with denoised narration.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)
    mix_final_audio(config, work_dir)


if __name__ == "__main__":
    main()
