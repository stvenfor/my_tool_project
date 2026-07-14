#!/usr/bin/env python3
"""Lightweight speaker diarization and per-speaker voice prompt extraction."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import (  # noqa: E402
    audio_to_wav,
    extract_audio_segment,
    load_json,
    resolve_work_dir,
    resolve_voice_reference_path,
    save_json,
    speaker_prompt_path,
    speaker_prompt_text_path,
)


def _assign_speakers(segments: list[dict[str, Any]], switch_threshold: float = 0.55) -> list[dict[str, Any]]:
    if not segments:
        return segments

    gaps = []
    for index in range(len(segments) - 1):
        gap = float(segments[index + 1]["start_sec"]) - float(segments[index]["end_sec"])
        gaps.append(gap)

    speaker_ids = ["spk0"]
    current = "spk0"
    for gap in gaps:
        if gap >= switch_threshold:
            current = "spk1" if current == "spk0" else "spk0"
        speaker_ids.append(current)

    enriched: list[dict[str, Any]] = []
    for seg, speaker_id in zip(segments, speaker_ids):
        enriched.append({**seg, "speaker_id": speaker_id})
    return enriched


def _apply_speaker_assignments(
    segments: list[dict[str, Any]],
    assignments: list[str] | dict[str, str],
) -> list[dict[str, Any]]:
    if not assignments:
        return segments

    enriched: list[dict[str, Any]] = []
    for index, seg in enumerate(segments):
        speaker_id = seg.get("speaker_id", "spk0")
        if isinstance(assignments, list) and index < len(assignments):
            speaker_id = str(assignments[index])
        elif isinstance(assignments, dict):
            speaker_id = str(assignments.get(str(index), assignments.get(index, speaker_id)))
        enriched.append({**seg, "speaker_id": speaker_id})
    return enriched


def _pick_prompt_segment(
    segments: list[dict[str, Any]],
    speaker_id: str,
    max_sec: float = 5.0,
) -> dict[str, Any] | None:
    candidates = [s for s in segments if s.get("speaker_id") == speaker_id]
    if not candidates:
        return None

    # Prefer a longer single line; if all are short, span consecutive lines by the same speaker.
    best = max(
        candidates,
        key=lambda s: min(float(s["end_sec"]) - float(s["start_sec"]), max_sec),
    )
    best_duration = float(best["end_sec"]) - float(best["start_sec"])
    if best_duration < 1.5 and len(candidates) > 1:
        ordered = sorted(candidates, key=lambda s: float(s["start_sec"]))
        start = float(ordered[0]["start_sec"])
        end = float(ordered[0]["end_sec"])
        texts = [str(ordered[0].get("text_zh", "")).strip()]
        for seg in ordered[1:]:
            gap = float(seg["start_sec"]) - end
            span = float(seg["end_sec"]) - start
            if gap > 1.2 or span >= max_sec:
                break
            end = float(seg["end_sec"])
            texts.append(str(seg.get("text_zh", "")).strip())
        if end - start > best_duration:
            best = {
                **ordered[0],
                "start_sec": round(start, 3),
                "end_sec": round(min(end, start + max_sec), 3),
                "text_zh": " ".join(t for t in texts if t),
            }

    duration = float(best["end_sec"]) - float(best["start_sec"])
    if duration > max_sec:
        best = {**best, "end_sec": round(float(best["start_sec"]) + max_sec, 3)}
    return best


def _extract_inline_segment_prompts(
    segments: list[dict[str, Any]],
    audio_wav: Path,
    work_dir: Path,
) -> list[dict[str, Any]]:
    prompts_dir = work_dir / "reference" / "segment_prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    enriched: list[dict[str, Any]] = []

    for index, seg in enumerate(segments):
        start = float(seg["start_sec"])
        end = float(seg["end_sec"])
        duration = max(0.15, end - start)
        prompt_wav = prompts_dir / f"seg_{index:02d}.wav"
        extract_audio_segment(audio_wav, prompt_wav, start, end, sample_rate=24000)
        prompt_text = str(seg.get("text_zh", "")).strip()
        enriched.append(
            {
                **seg,
                "prompt_wav": str(prompt_wav.relative_to(work_dir)),
                "prompt_text": prompt_text,
                "duration_sec": round(duration, 3),
            }
        )
    return enriched


def _extract_speaker_prompts(
    segments: list[dict[str, Any]],
    audio_wav: Path,
    work_dir: Path,
    *,
    max_sec: float = 5.0,
) -> dict[str, Any]:
    speaker_ids = sorted({str(s.get("speaker_id", "spk0")) for s in segments})
    speakers_meta: dict[str, Any] = {}
    for speaker_id in speaker_ids:
        prompt_seg = _pick_prompt_segment(segments, speaker_id, max_sec=max_sec)
        if not prompt_seg:
            continue
        prompt_wav = speaker_prompt_path(work_dir, speaker_id)
        extract_audio_segment(
            audio_wav,
            prompt_wav,
            float(prompt_seg["start_sec"]),
            float(prompt_seg["end_sec"]),
            sample_rate=24000,
        )
        prompt_text = str(prompt_seg.get("text_zh", "")).strip()
        speaker_prompt_text_path(work_dir, speaker_id).write_text(prompt_text + "\n", encoding="utf-8")
        speakers_meta[speaker_id] = {
            "prompt_wav": str(prompt_wav.relative_to(work_dir)),
            "prompt_text": prompt_text,
            "source_segment": {
                "start_sec": prompt_seg["start_sec"],
                "end_sec": prompt_seg["end_sec"],
            },
        }
    return speakers_meta


def _resolve_prompt_audio(work_dir: Path, config: dict[str, Any]) -> Path:
    if config.get("use_vocal_stem_for_prompts", True):
        vocals_stem = work_dir / "reference" / "vocals_stem.wav"
        if vocals_stem.exists():
            prompt_audio = work_dir / "reference" / "vocals_24k.wav"
            if not prompt_audio.exists() or prompt_audio.stat().st_mtime < vocals_stem.stat().st_mtime:
                audio_to_wav(vocals_stem, prompt_audio, sample_rate=24000)
            return prompt_audio

    target_audio = work_dir / "reference" / "audio.wav"
    if not target_audio.exists():
        raise SystemExit(f"Missing target audio wav: {target_audio}")

    prompt_audio_24k = work_dir / "reference" / "audio_24k.wav"
    audio_to_wav(target_audio, prompt_audio_24k, sample_rate=24000)
    return prompt_audio_24k


def diarize_speakers(config: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    transcript_path = work_dir / "reference" / "transcript.json"
    if not transcript_path.exists():
        raise SystemExit(f"Missing transcript: {transcript_path}")

    transcript = load_json(transcript_path)
    segments = transcript.get("segments", [])
    if not segments:
        raise SystemExit("No transcript segments to diarize")

    manual_assignments = config.get("speaker_assignments") or []
    if manual_assignments:
        segments = _apply_speaker_assignments(segments, manual_assignments)
    else:
        segments = _assign_speakers(segments, float(config.get("speaker_switch_gap_sec", 0.55)))

    prompt_mode = str(config.get("segment_prompt_mode", "speaker")).strip().lower()
    prompt_audio_24k = _resolve_prompt_audio(work_dir, config)

    voice_ref_path = resolve_voice_reference_path(config)
    if voice_ref_path and prompt_mode != "inline":
        voice_ref_dir = work_dir / "voice_reference"
        voice_ref_dir.mkdir(parents=True, exist_ok=True)
        voice_ref_wav = voice_ref_dir / "audio_24k.wav"
        if not voice_ref_wav.exists():
            ref_m4a = voice_ref_dir / "source.audio.m4a"
            from lib import extract_audio_from_video  # noqa: WPS433

            extract_audio_from_video(voice_ref_path, ref_m4a)
            audio_to_wav(ref_m4a, voice_ref_wav, sample_rate=24000)
        prompt_audio_24k = voice_ref_wav

    speakers_meta: dict[str, Any] = {}
    segments = _extract_inline_segment_prompts(segments, prompt_audio_24k, work_dir)
    if prompt_mode != "inline":
        max_sec = float(config.get("speaker_prompt_max_sec", 5.0))
        speakers_meta = _extract_speaker_prompts(segments, prompt_audio_24k, work_dir, max_sec=max_sec)

    transcript["segments"] = segments
    save_json(transcript_path, transcript)

    payload = {
        "segment_prompt_mode": prompt_mode,
        "segment_count": len(segments),
        "voice_reference": str(voice_ref_path) if voice_ref_path else "",
        "prompt_audio": str(prompt_audio_24k.relative_to(work_dir)),
        "speakers": speakers_meta,
    }
    save_json(work_dir / "reference" / "speakers.json", payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Diarize speakers and extract voice prompts.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)

    payload = diarize_speakers(config, work_dir)
    print(f"Prompt mode: {payload['segment_prompt_mode']}, segments: {payload['segment_count']}")
    if payload.get("speakers"):
        print(f"Speaker prompts: {', '.join(payload['speakers'].keys())}")


if __name__ == "__main__":
    main()
