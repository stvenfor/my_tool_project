#!/usr/bin/env python3
"""Align cloned segment audio to a retimed timeline (complete English + video remap)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import get_audio_duration, load_json, resolve_work_dir, save_json  # noqa: E402


def _make_silence(output_wav: Path, duration_sec: float, sample_rate: int = 44100) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r={sample_rate}:cl=mono",
            "-t",
            str(max(0.01, duration_sec)),
            str(output_wav),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _normalize_wav(input_wav: Path, output_wav: Path, sample_rate: int = 44100) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_wav),
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            str(output_wav),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _mix_timeline(
    segment_entries: list[dict[str, Any]],
    total_sec: float,
    output_wav: Path,
    sample_rate: int = 44100,
) -> None:
    """Place each segment at start_sec using ffmpeg adelay + amix."""
    if not segment_entries:
        _make_silence(output_wav, total_sec, sample_rate)
        return

    tmp_dir = output_wav.parent / "_align_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    inputs: list[str] = []
    filter_parts: list[str] = []

    for index, entry in enumerate(segment_entries):
        src = Path(entry["wav"])
        norm = tmp_dir / f"norm_{index:02d}.wav"
        _normalize_wav(src, norm, sample_rate)
        delay_ms = int(round(float(entry["start_sec"]) * 1000))
        inputs.extend(["-i", str(norm)])
        filter_parts.append(f"[{index}:a]adelay={delay_ms}|{delay_ms}[a{index}]")

    mix_inputs = "".join(f"[a{i}]" for i in range(len(segment_entries)))
    filter_parts.append(f"{mix_inputs}amix=inputs={len(segment_entries)}:normalize=0[out]")
    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex",
        filter_complex,
        "-map",
        "[out]",
        "-t",
        str(total_sec),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        str(output_wav),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg amix failed")


def _soften_narration(input_wav: Path, output_wav: Path, volume: float) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_wav),
            "-af",
            f"highpass=f=80,lowpass=f=12000,volume={volume:.2f},alimiter=limit=0.92",
            "-ac",
            "1",
            "-ar",
            "44100",
            str(output_wav),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _build_retimed_timeline(
    segments: list[dict[str, Any]],
    source_duration_sec: float,
    *,
    min_playback_rate: float = 0.72,
    max_playback_rate: float = 1.28,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float]:
    """
    Map source video ranges onto a wall-clock timeline where English can finish.

    Speech pieces: slow video when English is longer than Chinese mouthing window.
    Gaps: keep 1x.
    """
    min_rate = max(0.55, min(1.0, min_playback_rate))

    ordered = sorted(segments, key=lambda s: float(s["start_sec"]))
    video_pieces: list[dict[str, Any]] = []
    speech_placements: list[dict[str, Any]] = []
    wall = 0.0
    cursor_src = 0.0

    for item in ordered:
        src_start = float(item["start_sec"])
        src_end = float(item["end_sec"])
        src_dur = max(0.08, src_end - src_start)
        audio_dur = float(item.get("actual_sec") or get_audio_duration(Path(item["wav"])))
        audio_dur = max(0.08, audio_dur)

        gap = src_start - cursor_src
        if gap > 0.02:
            video_pieces.append(
                {
                    "kind": "gap",
                    "src_start_sec": round(cursor_src, 3),
                    "src_end_sec": round(src_start, 3),
                    "out_start_sec": round(wall, 3),
                    "out_duration_sec": round(gap, 3),
                    "playback_rate": 1.0,
                }
            )
            wall += gap

        max_out = src_dur / min_rate
        if audio_dur <= src_dur * 1.03:
            # Shorter or close: keep original mouth timing; audio sits at the start.
            out_dur = src_dur
            rate = 1.0
        else:
            out_dur = min(audio_dur, max_out)
            rate = max(min_rate, src_dur / out_dur)
            out_dur = src_dur / rate

        video_pieces.append(
            {
                "kind": "speech",
                "src_start_sec": round(src_start, 3),
                "src_end_sec": round(src_end, 3),
                "out_start_sec": round(wall, 3),
                "out_duration_sec": round(out_dur, 3),
                "playback_rate": round(rate, 4),
                "index": item.get("index"),
            }
        )
        speech_placements.append(
            {
                "wav": item["wav"],
                "start_sec": round(wall, 3),
                "duration_sec": round(min(audio_dur, out_dur), 3),
                "en": item.get("en", ""),
                "zh": item.get("zh", item.get("text_zh", "")),
                "speaker_id": item.get("speaker_id", "spk0"),
                "src_start_sec": round(src_start, 3),
                "src_end_sec": round(src_end, 3),
                "index": item.get("index"),
            }
        )
        wall += out_dur
        cursor_src = src_end

    if cursor_src < source_duration_sec - 0.02:
        trail = source_duration_sec - cursor_src
        video_pieces.append(
            {
                "kind": "gap",
                "src_start_sec": round(cursor_src, 3),
                "src_end_sec": round(source_duration_sec, 3),
                "out_start_sec": round(wall, 3),
                "out_duration_sec": round(trail, 3),
                "playback_rate": 1.0,
            }
        )
        wall += trail

    return video_pieces, speech_placements, wall


def align_audio(config: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    manifest_path = work_dir / "segments" / "manifest.json"
    script_path = work_dir / "script.json"
    if not manifest_path.exists():
        raise SystemExit(f"Missing segment manifest: {manifest_path}")
    if not script_path.exists():
        raise SystemExit(f"Missing script: {script_path}")

    manifest = load_json(manifest_path)
    script = load_json(script_path)
    source_duration = float(config.get("duration_sec", script.get("duration_sec", 0)))
    if source_duration <= 0:
        source_duration = float(script["segments"][-1]["end_sec"]) if script.get("segments") else 30.0

    script_by_index = {i: seg for i, seg in enumerate(script.get("segments", []))}
    min_rate = float(config.get("video_min_playback_rate", 0.72))
    max_rate = float(config.get("video_max_playback_rate", 1.28))

    aligned_segments: list[dict[str, Any]] = []
    for item in manifest.get("segments", []):
        idx = int(item.get("index", len(aligned_segments)))
        script_seg = script_by_index.get(idx, {})
        wav_rel = str(item["wav"])
        wav_path = work_dir / wav_rel
        if not wav_path.exists():
            raise SystemExit(f"Missing segment wav: {wav_path}")
        actual = float(item.get("actual_sec") or get_audio_duration(wav_path))
        aligned_segments.append(
            {
                "index": idx,
                "wav": str(wav_path),
                "start_sec": float(item.get("start_sec", script_seg.get("start_sec", 0))),
                "end_sec": float(item.get("end_sec", script_seg.get("end_sec", 0))),
                "actual_sec": actual,
                "en": item.get("en", script_seg.get("en", "")),
                "zh": script_seg.get("text_zh", script_seg.get("zh", "")),
                "speaker_id": item.get("speaker_id", script_seg.get("speaker_id", "spk0")),
            }
        )

    video_pieces, speech_placements, total_sec = _build_retimed_timeline(
        aligned_segments,
        source_duration,
        min_playback_rate=min_rate,
        max_playback_rate=max_rate,
    )

    mix_entries = [
        {"wav": p["wav"], "start_sec": p["start_sec"], "en": p.get("en", "")}
        for p in speech_placements
    ]
    raw_mix = work_dir / "narration_raw.wav"
    _mix_timeline(mix_entries, total_sec, raw_mix)

    narration_volume = float(config.get("narration_volume", 0.92))
    narration_wav = work_dir / "narration.wav"
    _soften_narration(raw_mix, narration_wav, narration_volume)

    subtitle_segments = [
        {
            "start_sec": round(float(p["start_sec"]), 3),
            "duration_sec": round(float(p["duration_sec"]), 3),
            "en": p.get("en", ""),
            "zh": p.get("zh", ""),
            "speaker_id": p.get("speaker_id", "spk0"),
        }
        for p in speech_placements
    ]
    subtitles = {
        "hook_en": config.get("hook_en", config.get("title", "Classic scene in English")),
        "hook_duration_sec": float(config.get("hook_duration_sec", 1.5)),
        "segments": subtitle_segments,
        "duration_sec": total_sec,
    }
    save_json(work_dir / "subtitles.json", subtitles)

    timeline = {
        "source_duration_sec": source_duration,
        "duration_sec": round(total_sec, 3),
        "video_pieces": video_pieces,
        "speech_placements": [
            {
                **{k: v for k, v in p.items() if k != "wav"},
                "wav": str(Path(p["wav"]).relative_to(work_dir)),
            }
            for p in speech_placements
        ],
    }
    save_json(work_dir / "timeline.json", timeline)

    payload = {
        "duration_sec": get_audio_duration(narration_wav),
        "source_duration_sec": source_duration,
        "segment_count": len(speech_placements),
        "narration": str(narration_wav.relative_to(work_dir)),
        "retimed": True,
    }
    save_json(work_dir / "alignment.json", payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Align cloned segments to timeline.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)

    payload = align_audio(config, work_dir)
    print(
        f"Narration aligned: {work_dir / 'narration.wav'} "
        f"({payload['duration_sec']:.2f}s, source {payload['source_duration_sec']:.2f}s)"
    )


if __name__ == "__main__":
    main()
