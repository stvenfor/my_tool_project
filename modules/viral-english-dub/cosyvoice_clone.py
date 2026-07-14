#!/usr/bin/env python3
"""CosyVoice cross-lingual / zero-shot dubbing with prosody from reference audio."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
COSYVOICE_ROOT = ROOT / "vendor" / "CosyVoice"
DEFAULT_MODEL_DIR = ROOT / "pretrained_models" / "CosyVoice2-0.5B"

_COSYVOICE_INSTANCE: Any | None = None


def ensure_cosyvoice_repo() -> Path:
    return ensure_cosyvoice_repo_paths()


def ensure_cosyvoice_repo_paths() -> Path:
    if not (COSYVOICE_ROOT / "cosyvoice" / "cli" / "cosyvoice.py").exists():
        raise SystemExit(
            "CosyVoice repo missing. Run: npm run viral-dub:setup-cosyvoice"
        )
    matcha_root = COSYVOICE_ROOT / "third_party" / "Matcha-TTS"
    if not (matcha_root / "matcha").exists():
        raise SystemExit(
            "Matcha-TTS missing. Run: npm run viral-dub:setup-cosyvoice"
        )
    for path in (str(matcha_root), str(COSYVOICE_ROOT)):
        if path not in sys.path:
            sys.path.insert(0, path)
    return COSYVOICE_ROOT


def resolve_model_dir(config: dict[str, Any] | None = None) -> Path:
    config = config or {}
    raw = str(config.get("cosyvoice_model_dir", "")).strip()
    if raw:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = (ROOT / path).resolve()
        if path.exists():
            return path
    if DEFAULT_MODEL_DIR.exists() and (DEFAULT_MODEL_DIR / "cosyvoice2.yaml").exists():
        return DEFAULT_MODEL_DIR
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    from huggingface_hub import snapshot_download

    model_name = str(config.get("cosyvoice_model", "FunAudioLLM/CosyVoice2-0.5B"))
    return Path(snapshot_download(model_name, local_dir=str(DEFAULT_MODEL_DIR)))


def load_cosyvoice(config: dict[str, Any] | None = None) -> Any:
    global _COSYVOICE_INSTANCE
    if _COSYVOICE_INSTANCE is not None:
        return _COSYVOICE_INSTANCE

    ensure_cosyvoice_repo_paths()
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    from cosyvoice.cli.cosyvoice import AutoModel

    model_dir = resolve_model_dir(config)
    print(f"Loading CosyVoice model from {model_dir}...")
    _COSYVOICE_INSTANCE = AutoModel(model_dir=str(model_dir))
    return _COSYVOICE_INSTANCE


def _wav_duration(path: Path) -> float:
    import soundfile as sf

    info = sf.info(str(path))
    return float(info.duration)


def _save_first_chunk(cosyvoice: Any, outputs: Any, output_wav: Path) -> None:
    import torchaudio

    output_wav.parent.mkdir(parents=True, exist_ok=True)
    for chunk in outputs:
        torchaudio.save(str(output_wav), chunk["tts_speech"], cosyvoice.sample_rate)
        return
    raise RuntimeError("CosyVoice produced no audio output")


def _run_inference(
    cosyvoice: Any,
    *,
    text_en: str,
    prompt_wav: Path,
    prompt_text_zh: str,
    mode: str,
    speed: float,
    output_wav: Path,
) -> None:
    if mode == "cross_lingual":
        tts_text = text_en.strip()
        if not tts_text.startswith("<|"):
            tts_text = f"<|en|>{tts_text}"
        outputs = cosyvoice.inference_cross_lingual(
            tts_text,
            str(prompt_wav),
            stream=False,
            speed=speed,
            text_frontend=False,
        )
        _save_first_chunk(cosyvoice, outputs, output_wav)
        return

    outputs = cosyvoice.inference_zero_shot(
        text_en.strip(),
        prompt_text_zh.strip(),
        str(prompt_wav),
        stream=False,
        speed=speed,
        text_frontend=False,
    )
    _save_first_chunk(cosyvoice, outputs, output_wav)


def synthesize_cosyvoice(
    text_en: str,
    prompt_wav: Path,
    output_wav: Path,
    *,
    prompt_text_zh: str = "",
    target_sec: float | None = None,
    config: dict[str, Any] | None = None,
) -> None:
    """Synthesize English speech while preserving reference prosody/tone."""
    cosyvoice = load_cosyvoice(config)
    config = config or {}
    mode = str(config.get("cosyvoice_mode", "zero_shot")).strip().lower()
    prompt_wav = prompt_wav.resolve()
    output_wav = output_wav.resolve()

    if mode != "cross_lingual" and not prompt_text_zh.strip():
        raise RuntimeError("CosyVoice zero_shot requires prompt_text_zh (original Chinese line).")

    _run_inference(
        cosyvoice,
        text_en=text_en,
        prompt_wav=prompt_wav,
        prompt_text_zh=prompt_text_zh,
        mode=mode,
        speed=1.0,
        output_wav=output_wav,
    )

    if not target_sec or target_sec <= 0.05:
        return

    actual = _wav_duration(output_wav)
    if actual <= 0.05:
        return

    ratio = actual / target_sec
    # CosyVoice speed>1 shortens; speed<1 lengthens.
    # Keep retune gentle so tone/prosody survive; video remapping absorbs the rest.
    if 0.88 <= ratio <= 1.12:
        return

    speed = max(0.85, min(1.35, ratio))
    print(f"    cosyvoice retune speed={speed:.2f} (raw={actual:.2f}s target={target_sec:.2f}s)")
    _run_inference(
        cosyvoice,
        text_en=text_en,
        prompt_wav=prompt_wav,
        prompt_text_zh=prompt_text_zh,
        mode=mode,
        speed=speed,
        output_wav=output_wav,
    )
