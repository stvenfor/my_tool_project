#!/usr/bin/env python3
"""Synthesize narration with edge-tts or zero-shot voice cloning."""

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

import os  # noqa: E402

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from lib import (  # noqa: E402
    build_narration_mapping,
    count_chinese_chars,
    default_chinese_rate,
    default_chinese_voice,
    detect_torch_device,
    fill_template,
    fit_audio_duration,
    is_chinese_narration,
    load_json,
    resolve_prompt_text,
    resolve_voice_reference,
    resolve_work_dir,
)
from zipvoice_clone import prepare_short_prompt, synthesize_zipvoice  # noqa: E402


async def _synthesize_edge_tts(
    text: str,
    voice: str,
    output_path: Path,
    rate: str = "+0%",
) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(str(output_path))


def _synthesize_sopro(text: str, ref_audio: Path, output_path: Path, device: str) -> None:
    from sopro import SoproTTS

    tts = SoproTTS.from_pretrained("samuel-vitorino/sopro", device=device)
    wav = tts.synthesize(text, ref_audio_path=str(ref_audio))
    tts.save_wav(str(output_path), wav)


def _synthesize_zipvoice(
    text: str,
    ref_audio: Path,
    prompt_text: str,
    output_path: Path,
    config: dict[str, Any],
    work_dir: Path,
) -> None:
    prompt_wav = work_dir / "reference" / "prompt_short.wav"
    prepare_short_prompt(ref_audio, prompt_wav, max_sec=3.0)
    synthesize_zipvoice(
        text=text,
        prompt_wav=prompt_wav,
        prompt_text=prompt_text,
        output_wav=output_path,
        model_name=str(config.get("zipvoice_model", "zipvoice_distill")),
        num_steps=int(config.get("zipvoice_num_steps", 8)),
    )


def _synthesize_clone(
    text: str,
    ref_audio: Path,
    output_path: Path,
    backend: str,
    config: dict[str, Any],
    work_dir: Path,
) -> None:
    if backend == "zipvoice":
        prompt_text = resolve_prompt_text(config, work_dir)
        print(f"Voice clone backend=zipvoice, prompt_text={prompt_text[:40]}...")
        _synthesize_zipvoice(text, ref_audio, prompt_text, output_path, config, work_dir)
        return

    if backend == "sopro":
        device = detect_torch_device()
        print(f"Voice clone backend=sopro, device={device}")
        _synthesize_sopro(text, ref_audio, output_path, device)
        return

    raise SystemExit(f"Unsupported voice_clone_backend: {backend}")


def _silent_placeholder(output_path: Path, duration: float) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=mono",
        "-t",
        str(duration),
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(result.stderr)


def _resolve_voice_mode(config: dict[str, Any], narration: str) -> str:
    voice_mode = str(config.get("voice_mode", "edge-tts")).strip().lower()
    backend = str(config.get("voice_clone_backend", "zipvoice")).strip().lower()

    if voice_mode in {"chinese", "zh", "edge-tts"}:
        return "chinese"
    if voice_mode == "clone":
        if is_chinese_narration(narration) and backend == "zipvoice":
            return "clone"
        if is_chinese_narration(narration):
            print("Chinese narration with non-zipvoice backend; using edge-tts fallback.")
            return "chinese"
        return "clone"
    return voice_mode


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthesize city-healing narration.")
    parser.add_argument("--config", required=True, help="Path to city.config.json")
    parser.add_argument("--max-chars", type=int, default=180)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)
    work_dir.mkdir(parents=True, exist_ok=True)

    template_path = ROOT / "copy" / "narration.template.txt"
    template = template_path.read_text(encoding="utf-8").strip()
    mapping = build_narration_mapping(config)
    narration = fill_template(template, mapping)

    char_count = count_chinese_chars(narration)
    if char_count > args.max_chars:
        raise SystemExit(f"Narration too long: {char_count} chars (max {args.max_chars})")

    narration_txt = work_dir / "narration.txt"
    narration_txt.write_text(narration + "\n", encoding="utf-8")

    voice_mode = _resolve_voice_mode(config, narration)
    narration_wav = work_dir / "narration.wav"
    target_sec = float(config.get("duration_sec", 60))

    with tempfile.TemporaryDirectory(prefix="city-voice-") as tmp_dir:
        raw_wav = Path(tmp_dir) / "narration_raw.wav"

        if voice_mode == "clone":
            ref_audio = resolve_voice_reference(config, work_dir)
            if not ref_audio.exists():
                raise SystemExit(
                    f"Voice reference not found: {ref_audio}. "
                    "Run fetch_voice_reference.py first or set --ref-audio."
                )
            backend = str(config.get("voice_clone_backend", "zipvoice"))
            try:
                _synthesize_clone(narration, ref_audio, raw_wav, backend, config, work_dir)
            except Exception as exc:
                if is_chinese_narration(narration):
                    print(f"Clone failed ({exc}); falling back to edge-tts Chinese voice.")
                    voice = default_chinese_voice(config)
                    rate = default_chinese_rate(config)
                    asyncio.run(_synthesize_edge_tts(narration, voice, raw_wav, rate=rate))
                else:
                    raise
        else:
            voice = default_chinese_voice(config)
            rate = default_chinese_rate(config)
            try:
                asyncio.run(_synthesize_edge_tts(narration, voice, raw_wav, rate=rate))
            except ImportError:
                print("edge-tts not installed, generating silent placeholder audio via ffmpeg")
                _silent_placeholder(raw_wav, target_sec)

        final_duration = fit_audio_duration(raw_wav, narration_wav, target_sec)
        print(f"Narration fitted to {final_duration:.2f}s (target {target_sec}s)")

    print(f"Narration text ({char_count} chars): {narration_txt}")
    print(f"Narration audio: {narration_wav} (mode={voice_mode})")


if __name__ == "__main__":
    main()
