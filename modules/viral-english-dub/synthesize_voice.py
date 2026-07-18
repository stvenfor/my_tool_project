#!/usr/bin/env python3
"""Cross-lingual voice clone per script segment (English with original accent)."""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from lib import (  # noqa: E402
    default_english_rate,
    default_english_voice,
    detect_torch_device,
    fit_audio_duration,
    fit_audio_for_slot,
    fit_audio_prefer_complete,
    get_audio_duration,
    load_json,
    resolve_work_dir,
    save_json,
    speaker_prompt_path,
    speaker_prompt_text_path,
)


async def _synthesize_edge_tts(text: str, voice: str, output_path: Path, rate: str) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(str(output_path))


class SoproVoiceCloner:
    """Reuse prepared speaker references for consistent cross-lingual cloning."""

    def __init__(self, tts: Any, config: dict[str, Any]) -> None:
        self.tts = tts
        self.config = config
        self._ref_cache: dict[str, Any] = {}

    def synthesize(self, text: str, prompt_wav: Path, output_path: Path) -> None:
        key = str(prompt_wav.resolve())
        if key not in self._ref_cache:
            ref_seconds = min(
                get_audio_duration(prompt_wav),
                float(self.config.get("sopro_ref_seconds_max", 12.0)),
            )
            ref_seconds = max(ref_seconds, float(self.config.get("sopro_ref_seconds_min", 0.8)))
            self._ref_cache[key] = self.tts.prepare_reference(
                ref_audio_path=str(prompt_wav),
                ref_seconds=ref_seconds,
            )

        wav = self.tts.synthesize(
            text,
            ref=self._ref_cache[key],
            style_strength=float(self.config.get("sopro_style_strength", 1.65)),
            temperature=float(self.config.get("sopro_temperature", 0.92)),
            top_p=float(self.config.get("sopro_top_p", 0.9)),
        )
        self.tts.save_wav(str(output_path), wav)


def _load_sopro(device: str) -> Any:
    from sopro import SoproTTS

    print(f"Loading Sopro model on {device}...")
    return SoproTTS.from_pretrained("samuel-vitorino/sopro", device=device)


def _synthesize_zipvoice(
    text: str,
    prompt_wav: Path,
    prompt_text: str,
    output_path: Path,
    config: dict[str, Any],
    work_dir: Path,
) -> None:
    from zipvoice_clone import prepare_short_prompt, synthesize_zipvoice  # noqa: E402

    short_prompt = work_dir / "reference" / f"prompt_short_{output_path.stem}.wav"
    prepare_short_prompt(prompt_wav, short_prompt, max_sec=3.0)
    synthesize_zipvoice(
        text=text,
        prompt_wav=short_prompt,
        prompt_text=prompt_text,
        output_wav=output_path,
        model_name=str(config.get("zipvoice_model", "zipvoice_distill")),
        num_steps=int(config.get("zipvoice_num_steps", 8)),
    )


def _resolve_speaker_prompt(work_dir: Path, speaker_id: str) -> tuple[Path, str]:
    prompt_wav = speaker_prompt_path(work_dir, speaker_id)
    prompt_text_path = speaker_prompt_text_path(work_dir, speaker_id)
    if not prompt_wav.exists():
        fallback = work_dir / "reference" / "vocals_24k.wav"
        if not fallback.exists():
            fallback = work_dir / "reference" / "audio_24k.wav"
        if fallback.exists():
            prompt_wav = fallback
        else:
            raise FileNotFoundError(f"Speaker prompt missing: {prompt_wav}")
    prompt_text = prompt_text_path.read_text(encoding="utf-8").strip() if prompt_text_path.exists() else ""
    if not prompt_text:
        prompt_text = "这是参考音频中的中文台词。"
    return prompt_wav, prompt_text


def _resolve_prompt_source_audio(work_dir: Path, config: dict[str, Any]) -> Path:
    """Prefer clean vocal stem so CosyVoice copies tone without BGM bleed."""
    for candidate in (
        work_dir / "reference" / "vocals_24k.wav",
        work_dir / "reference" / "vocals_stem.wav",
        work_dir / "reference" / "audio.wav",
    ):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No prompt source audio under {work_dir / 'reference'}")


def _build_context_prompt(
    work_dir: Path,
    segments: list[dict[str, Any]],
    index: int,
    config: dict[str, Any],
) -> tuple[Path, str] | None:
    """Widen short prompts so CosyVoice has enough speech to lock timbre + tone.

    CosyVoice warns when English is much shorter than prompt_text, so we only pad
    when the English line is long enough relative to the expanded Chinese.
    """
    min_sec = float(config.get("min_prompt_sec", 3.2))
    max_sec = float(config.get("max_prompt_sec", 8.0))
    if min_sec <= 0:
        return None

    seg = segments[index]
    start = float(seg["start_sec"])
    end = float(seg["end_sec"])
    if end - start >= min_sec * 0.92:
        return None

    left = index
    right = index
    texts = [str(seg.get("prompt_text") or seg.get("text_zh") or "").strip()]
    while (end - start) < min_sec and (left > 0 or right < len(segments) - 1):
        grew = False
        if left > 0:
            left -= 1
            neighbor = segments[left]
            start = float(neighbor["start_sec"])
            texts.insert(0, str(neighbor.get("prompt_text") or neighbor.get("text_zh") or "").strip())
            grew = True
        if (end - start) >= min_sec:
            break
        if right < len(segments) - 1:
            right += 1
            neighbor = segments[right]
            end = float(neighbor["end_sec"])
            texts.append(str(neighbor.get("prompt_text") or neighbor.get("text_zh") or "").strip())
            grew = True
        if not grew:
            break

    if end - start > max_sec:
        mid = (float(seg["start_sec"]) + float(seg["end_sec"])) / 2.0
        start = max(0.0, mid - max_sec / 2.0)
        end = start + max_sec

    prompt_text = "".join(t for t in texts if t)
    text_en = str(seg.get("en", "")).strip()
    # CosyVoice: synthesis text should not be << half of prompt text length.
    if prompt_text and len(text_en) < 0.45 * len(prompt_text):
        return None

    source = _resolve_prompt_source_audio(work_dir, config)
    out_dir = work_dir / "reference" / "prosody_prompts"
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_wav = out_dir / f"seg_{index:02d}.wav"
    from lib import extract_audio_segment  # noqa: E402

    extract_audio_segment(source, prompt_wav, start, end, sample_rate=24000)
    return prompt_wav, prompt_text


def _resolve_segment_prompt(
    work_dir: Path,
    seg: dict[str, Any],
    speaker_id: str,
    config: dict[str, Any],
    *,
    segments: list[dict[str, Any]] | None = None,
    index: int | None = None,
) -> tuple[Path, str]:
    use_inline = bool(config.get("use_inline_prompt", config.get("sopro_use_inline_prompt", True)))
    prompt_mode = str(config.get("segment_prompt_mode", "speaker")).strip().lower()
    if use_inline or prompt_mode == "inline":
        if segments is not None and index is not None and bool(config.get("expand_short_prompts", True)):
            expanded = _build_context_prompt(work_dir, segments, index, config)
            if expanded is not None:
                return expanded
        prompt_rel = str(seg.get("prompt_wav", "")).strip()
        if prompt_rel:
            prompt_wav = work_dir / prompt_rel
            if prompt_wav.exists():
                prompt_text = str(seg.get("prompt_text", seg.get("text_zh", ""))).strip()
                if prompt_text:
                    return prompt_wav, prompt_text

    prompt_wav, prompt_text = _resolve_speaker_prompt(work_dir, speaker_id)
    return prompt_wav, prompt_text


def _fit_segment_audio(
    input_wav: Path,
    output_wav: Path,
    target_sec: float,
    config: dict[str, Any],
) -> float:
    max_stretch = float(config.get("max_stretch_ratio", 1.22))
    fit_mode = str(config.get("audio_fit_mode", "prefer_complete")).strip().lower()
    # Max spoken wall-time when remapping video slowly (default ~1.35x Chinese slot).
    video_slow = float(config.get("video_min_playback_rate", 0.72))
    video_slow = max(0.55, min(1.0, video_slow))
    max_output_sec = target_sec / video_slow

    if fit_mode in {"prefer_complete", "complete", "natural"}:
        return fit_audio_prefer_complete(
            input_wav,
            output_wav,
            target_sec,
            max_stretch_ratio=max_stretch,
            max_output_sec=max_output_sec,
        )
    if fit_mode == "trim_pad":
        return fit_audio_duration(
            input_wav, output_wav, target_sec, max_stretch_ratio=max_stretch, exact=False
        )
    return fit_audio_for_slot(input_wav, output_wav, target_sec, max_stretch_ratio=max_stretch)


def _clone_segment(
    text: str,
    seg: dict[str, Any],
    speaker_id: str,
    output_path: Path,
    config: dict[str, Any],
    work_dir: Path,
    *,
    sopro_cloner: SoproVoiceCloner | None = None,
    segments: list[dict[str, Any]] | None = None,
    index: int | None = None,
) -> str:
    backend = str(config.get("voice_clone_backend", "cosyvoice")).strip().lower()
    prompt_wav, prompt_text = _resolve_segment_prompt(
        work_dir, seg, speaker_id, config, segments=segments, index=index
    )

    if backend == "cosyvoice":
        from cosyvoice_clone import synthesize_cosyvoice  # noqa: E402

        target_sec = float(seg.get("duration_sec", max(0.1, float(seg["end_sec"]) - float(seg["start_sec"]))))
        prompt_dur = get_audio_duration(prompt_wav) if prompt_wav.exists() else 0.0
        print(
            f"  clone backend=cosyvoice speaker={speaker_id} "
            f"prompt={prompt_wav.name} ({prompt_dur:.2f}s) text={prompt_text[:24]!r}"
        )
        synthesize_cosyvoice(
            text,
            prompt_wav,
            output_path,
            prompt_text_zh=prompt_text,
            target_sec=target_sec,
            config=config,
        )
        return "cosyvoice"

    if backend == "sopro":
        if sopro_cloner is None:
            device = detect_torch_device()
            sopro_cloner = SoproVoiceCloner(_load_sopro(device), config)
        print(f"  clone backend=sopro speaker={speaker_id} prompt={prompt_wav.name}")
        sopro_cloner.synthesize(text, prompt_wav, output_path)
        return "sopro"

    if backend == "zipvoice":
        print(f"  clone backend=zipvoice speaker={speaker_id} prompt={prompt_wav.name}")
        _synthesize_zipvoice(text, prompt_wav, prompt_text, output_path, config, work_dir)
        return "zipvoice"

    raise SystemExit(f"Unsupported voice_clone_backend: {backend}")


def synthesize_segments(config: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    script_path = work_dir / "script.json"
    if not script_path.exists():
        raise SystemExit(f"Missing script: {script_path}")

    script = load_json(script_path)
    segments = script.get("segments", [])
    if not segments:
        raise SystemExit("No script segments found")

    voice_mode = str(config.get("voice_mode", "cross_lingual_clone")).strip().lower()
    disallow_fallback = bool(config.get("disallow_tts_fallback", True))
    segments_dir = work_dir / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)

    manifest_segments: list[dict[str, Any]] = []
    backend_used = voice_mode
    sopro_cloner: SoproVoiceCloner | None = None
    backend = str(config.get("voice_clone_backend", "cosyvoice")).lower()
    if voice_mode == "cross_lingual_clone" and backend == "sopro":
        sopro_cloner = SoproVoiceCloner(_load_sopro(detect_torch_device()), config)

    for index, seg in enumerate(segments):
        text = str(seg.get("en", "")).strip()
        if not text or text.startswith("[EN]"):
            continue
        if voice_mode == "cross_lingual_clone" and re.search(r"[\u4e00-\u9fff]", text):
            raise SystemExit(
                f"Segment {index} English text still contains Chinese. "
                "Fix script.json or set OPENAI_API_KEY for translate."
            )
        speaker_id = str(seg.get("speaker_id", "spk0"))
        target_sec = float(seg.get("duration_sec", max(0.1, float(seg["end_sec"]) - float(seg["start_sec"]))))
        raw_wav = segments_dir / f"seg_{index:02d}_raw.wav"
        fitted_wav = segments_dir / f"seg_{index:02d}.wav"

        if voice_mode == "cross_lingual_clone":
            backend_used = _clone_segment(
                text,
                seg,
                speaker_id,
                raw_wav,
                config,
                work_dir,
                sopro_cloner=sopro_cloner,
                segments=segments,
                index=index,
            )
        elif voice_mode == "edge-tts":
            voice = default_english_voice(config)
            rate = default_english_rate(config)
            asyncio.run(_synthesize_edge_tts(text, voice, raw_wav, rate))
            backend_used = "edge-tts"
        else:
            raise SystemExit(f"Unsupported voice_mode: {voice_mode}")

        raw_sec = get_audio_duration(raw_wav)
        final_duration = _fit_segment_audio(raw_wav, fitted_wav, target_sec, config)
        manifest_segments.append(
            {
                "index": index,
                "wav": str(fitted_wav.relative_to(work_dir)),
                "raw_wav": str(raw_wav.relative_to(work_dir)),
                "speaker_id": speaker_id,
                "en": text,
                "target_sec": target_sec,
                "raw_sec": round(raw_sec, 3),
                "actual_sec": round(final_duration, 3),
                "start_sec": seg["start_sec"],
                "end_sec": seg["end_sec"],
            }
        )
        print(
            f"Segment {index:02d}: raw={raw_sec:.2f}s fitted={final_duration:.2f}s "
            f"target={target_sec:.2f}s"
        )

    payload = {
        "voice_mode": voice_mode,
        "backend_used": backend_used,
        "segments": manifest_segments,
    }
    save_json(segments_dir / "manifest.json", payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthesize cloned English segments.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)

    payload = synthesize_segments(config, work_dir)
    print(f"Segments synthesized: {len(payload['segments'])} via {payload['backend_used']}")


if __name__ == "__main__":
    main()
