#!/usr/bin/env python3
"""Extract BGM beats and action segment map from reference dance video."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import wave
import array
from pathlib import Path


def probe_duration(video: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def extract_audio(video: Path, wav_path: Path) -> None:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "44100",
            "-ac",
            "1",
            str(wav_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def analyze_beats(wav_path: Path) -> dict:
    with wave.open(str(wav_path)) as w:
        sr = w.getframerate()
        data = array.array("h", w.readframes(w.getnframes()))

    duration = len(data) / sr
    window = int(sr * 0.05)
    hop = int(sr * 0.025)

    energies: list[float] = []
    times: list[float] = []
    for i in range(0, len(data) - window, hop):
        chunk = data[i : i + window]
        rms = math.sqrt(sum(x * x for x in chunk) / len(chunk))
        energies.append(rms)
        times.append(i / sr)

    sorted_e = sorted(energies)
    threshold = sorted_e[int(len(sorted_e) * 0.72)]

    onsets: list[float] = []
    min_gap = 0.12
    last = -999.0
    for t, e in zip(times, energies):
        if e > threshold and (t - last) >= min_gap:
            onsets.append(round(t, 3))
            last = t

    intervals = [onsets[i + 1] - onsets[i] for i in range(len(onsets) - 1) if 0.2 < onsets[i + 1] - onsets[i] < 0.8]
    bpm = round(60 / sorted(intervals)[len(intervals) // 2]) if intervals else 120

    def score_bpm(candidate: int) -> float:
        period = 60.0 / candidate
        errors = [min((o % period) / period, 1 - (o % period) / period) for o in onsets]
        return sum(errors) / len(errors) if errors else 999.0

    best_bpm = bpm
    best_score = score_bpm(bpm)
    for candidate in range(max(80, bpm - 20), min(160, bpm + 21)):
        s = score_bpm(candidate)
        if s < best_score:
            best_score = s
            best_bpm = candidate

    beat_period = 60.0 / best_bpm
    beats: list[float] = []
    t = onsets[0] if onsets else 0.0
    while t < duration:
        beats.append(round(t, 3))
        t += beat_period

    segments = [
        {"id": "A", "label": "开场", "start": 0.0, "end": 1.5, "action": "正面站立，双手放胯/大腿，轻微摆胯"},
        {"id": "B", "label": "抬手", "start": 1.5, "end": 3.5, "action": "双臂抬至肩高，配合胯部左右摆"},
        {"id": "C", "label": "热舞", "start": 3.5, "end": 5.5, "action": "动作幅度加大，头发甩动"},
        {"id": "D", "label": "转身", "start": 5.5, "end": 7.0, "action": "背对镜头旋转/展示背影"},
        {"id": "E", "label": "回正", "start": 7.0, "end": 9.0, "action": "侧/front 交替，继续跟拍节奏"},
        {"id": "F", "label": "定帧", "start": 9.0, "end": 10.033, "action": "回眸 + 食指触唇收尾"},
    ]

    def nearest_beat(sec: float) -> float:
        return min(beats, key=lambda b: abs(b - sec)) if beats else sec

    segment_beats = {seg["id"]: [b for b in beats if seg["start"] <= b < seg["end"]] for seg in segments}

    return {
        "duration_sec": round(duration, 3),
        "sample_rate": sr,
        "bpm_estimate": best_bpm,
        "beat_period_sec": round(beat_period, 4),
        "onsets_sec": onsets,
        "beats_sec": beats,
        "segments": segments,
        "segment_beats": segment_beats,
        "segment_boundary_beats": {
            seg["id"]: {"start_beat": nearest_beat(seg["start"]), "end_beat": nearest_beat(seg["end"])}
            for seg in segments
        },
        "shoot_cues": [
            {"time_sec": 0.0, "cue": "音乐起，正面站拱门框中心，手放胯"},
            {"time_sec": 1.5, "cue": "双臂开始上抬"},
            {"time_sec": 3.5, "cue": "加大摆胯和甩发幅度"},
            {"time_sec": 5.5, "cue": "转身背对镜头"},
            {"time_sec": 7.0, "cue": "转回正面/侧面继续"},
            {"time_sec": 9.0, "cue": "回眸，食指触唇定帧"},
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract beat map from dance reference video.")
    parser.add_argument("--video", default="_dance-remake/reference/source.mp4")
    parser.add_argument("--output", default="_dance-remake/reference/beat_map.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    video = (root / args.video).resolve()
    output = (root / args.output).resolve()
    wav = output.parent / "audio.wav"

    if not video.exists():
        raise SystemExit(f"Video not found: {video}")

    extract_audio(video, wav)
    beat_data = analyze_beats(wav)
    beat_data["source"] = str(video.relative_to(root)) if video.is_relative_to(root) else str(video)

    output.write_text(json.dumps(beat_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {output} (BPM={beat_data['bpm_estimate']}, duration={beat_data['duration_sec']}s)")


if __name__ == "__main__":
    main()
