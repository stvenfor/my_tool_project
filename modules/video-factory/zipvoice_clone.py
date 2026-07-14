#!/usr/bin/env python3
"""ZipVoice Chinese zero-shot voice cloning wrapper."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ZIPVOICE_ROOT = ROOT / "vendor" / "ZipVoice"


def ensure_zipvoice_repo() -> Path:
    if not (ZIPVOICE_ROOT / "zipvoice" / "bin" / "infer_zipvoice.py").exists():
        raise SystemExit(
            "ZipVoice repo missing. Run: npm run city:setup-zipvoice"
        )
    return ZIPVOICE_ROOT


def prepare_short_prompt(ref_audio: Path, output_path: Path, max_sec: float = 3.0) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(ref_audio),
            "-t",
            str(max_sec),
            "-ac",
            "1",
            "-ar",
            "24000",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg prompt trim failed")


def synthesize_zipvoice(
    text: str,
    prompt_wav: Path,
    prompt_text: str,
    output_wav: Path,
    model_name: str = "zipvoice_distill",
    num_steps: int = 8,
) -> None:
    repo = ensure_zipvoice_repo()
    prompt_wav = prompt_wav.resolve()
    output_wav = output_wav.resolve()
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    env["PYTHONPATH"] = str(repo) + os.pathsep + env.get("PYTHONPATH", "")

    cmd = [
        sys.executable,
        "-m",
        "zipvoice.bin.infer_zipvoice",
        "--model-name",
        model_name,
        "--prompt-wav",
        str(prompt_wav),
        "--prompt-text",
        prompt_text,
        "--text",
        text,
        "--res-wav-path",
        str(output_wav),
        "--num-step",
        str(num_steps),
    ]
    print("$", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(repo), env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "zipvoice infer failed").strip())
    if not output_wav.exists():
        raise RuntimeError(f"ZipVoice output missing: {output_wav}")
