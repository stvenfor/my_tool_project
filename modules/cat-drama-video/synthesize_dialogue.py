#!/usr/bin/env python3
"""Synthesize multi-character dialogue (no narrator) for cat-drama episodes."""

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

from lib import get_audio_duration, load_json, resolve_work_dir, save_json  # noqa: E402
from voice_helpers import (  # noqa: E402
    _concat_wavs,
    _enhance_narration,
    _make_silence,
    _synthesize_segment,
)

DEFAULT_CHARACTER_VOICES: dict[str, dict[str, str | float]] = {
    "alili": {
        "voice": "zh-CN-YunjianNeural",
        "rate": "+4%",
        "pitch": "-6Hz",
        "volume": "+2%",
    },
    "daju": {
        "voice": "zh-CN-YunxiaNeural",
        "rate": "+14%",
        "pitch": "+10Hz",
        "volume": "+4%",
    },
    "xiaobai": {
        "voice": "zh-CN-XiaoyiNeural",
        "rate": "+6%",
        "pitch": "+4Hz",
        "volume": "+2%",
    },
    "setup": {"silence_sec": 1.8},
}


def _voice_for_segment(config: dict[str, Any], seg: dict[str, Any]) -> dict[str, str]:
    voices = {**DEFAULT_CHARACTER_VOICES, **(config.get("character_voices") or {})}
    key = str(seg.get("character_key") or seg.get("phase") or "alili")
    profile = voices.get(key, voices.get("alili", {}))
    if key == "setup":
        return {"kind": "silence", "silence_sec": float(profile.get("silence_sec", 1.8))}
    return {
        "kind": "speech",
        "voice": str(profile.get("voice", "zh-CN-YunjianNeural")),
        "rate": str(profile.get("rate", "+0%")),
        "pitch": str(profile.get("pitch", "+0Hz")),
        "volume": str(profile.get("volume", "+0%")),
    }


def synthesize_dialogue(config: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    script_path = work_dir / "script.json"
    if not script_path.exists():
        raise SystemExit(f"Missing script: {script_path}")

    script = load_json(script_path)
    segments = script.get("segments", [])
    if not segments:
        raise SystemExit("No dialogue segments found")

    tail_padding = float(config.get("tail_padding_sec", 2.0))
    enhance = config.get("voice_enhance") or {}
    narration_volume = float(config.get("narration_volume", 0.92))
    rhythm = config.get("voice_rhythm") or {}
    gap_sec = float(config.get("dialogue_gap_sec", config.get("narration_gap_sec", 0.22)))

    aligned_segments: list[dict[str, Any]] = []
    part_paths: list[Path] = []
    segment_gaps: list[float] = []

    with tempfile.TemporaryDirectory(prefix="cat-dialogue-") as tmp:
        tmp_dir = Path(tmp)
        cursor = 0.0

        for index, seg in enumerate(segments):
            profile = _voice_for_segment(config, seg)
            part_wav = tmp_dir / f"seg_{index:02d}.wav"
            character = str(seg.get("character", "")).strip()
            dialogue = str(seg.get("dialogue") or seg.get("narration", "")).strip()
            phase = str(seg.get("phase", seg.get("character_key", "insight")))

            if profile["kind"] == "silence":
                silence_sec = float(profile["silence_sec"])
                _make_silence(part_wav, silence_sec)
                duration = silence_sec
                subtitle_zh = ""
            else:
                if not dialogue:
                    raise SystemExit(f"Segment {seg.get('id', index)} missing dialogue")
                asyncio.run(
                    _synthesize_segment(
                        dialogue,
                        profile["voice"],
                        part_wav,
                        profile["rate"],
                        profile["pitch"],
                        profile["volume"],
                        rhythm,
                        phase=phase,
                    )
                )
                duration = get_audio_duration(part_wav)
                subtitle_zh = dialogue

            aligned_segments.append(
                {
                    "start_sec": round(cursor, 3),
                    "duration_sec": round(duration, 3),
                    "zh": subtitle_zh,
                    "speaker": character,
                    "character_key": seg.get("character_key", phase),
                    "emphasis": [],
                    "visual_keyword": seg.get("visual_keyword", ""),
                    "phase": phase,
                    "id": seg.get("id", f"seg_{index + 1:02d}"),
                }
            )
            part_paths.append(part_wav)
            if index < len(segments) - 1:
                segment_gaps.append(gap_sec)
                cursor += duration + gap_sec
            else:
                cursor += duration

        body = tmp_dir / "dialogue_body.wav"
        _concat_wavs(part_paths, body, gaps=segment_gaps)

        tail_pad = tmp_dir / "tail_pad.wav"
        _make_silence(tail_pad, tail_padding)
        raw_concat = tmp_dir / "dialogue_concat.wav"
        _concat_wavs([body, tail_pad], raw_concat, gaps=[])

        final_duration = get_audio_duration(raw_concat)
        enhanced = tmp_dir / "dialogue_enhanced.wav"
        _enhance_narration(raw_concat, enhanced, narration_volume, enhance)

        narration_wav = work_dir / "narration.wav"
        subprocess.run(["cp", str(enhanced), str(narration_wav)], check=True)

        subtitles = {
            "hook_zh": "",
            "hook_duration_sec": 0.0,
            "duration_sec": round(final_duration, 3),
            "tail_padding_sec": tail_padding,
            "segments": aligned_segments,
            "mode": "dialogue",
        }
        save_json(work_dir / "subtitles.json", subtitles)
        (work_dir / "narration.zh.txt").write_text(
            "\n".join(
                f"{seg.get('speaker', '')}：{seg['zh']}" if seg.get("speaker") and seg.get("zh") else ""
                for seg in aligned_segments
                if seg.get("zh")
            )
            + "\n",
            encoding="utf-8",
        )

        return {
            "duration_sec": round(final_duration, 3),
            "segments": len(aligned_segments),
            "mode": "dialogue",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthesize cat-drama character dialogue.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)

    result = synthesize_dialogue(config, work_dir)
    config["duration_sec"] = result["duration_sec"]
    save_json(config_path, config)

    print(
        f"Dialogue audio: {work_dir / 'narration.wav'} "
        f"({result['duration_sec']}s, {result['segments']} lines, mode={result['mode']})"
    )


if __name__ == "__main__":
    main()
