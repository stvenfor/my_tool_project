#!/usr/bin/env python3
"""Play reference BGM and print shoot cues in sync (macOS afplay)."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    beat_map_path = root / "_dance-remake/reference/beat_map.json"
    audio_path = root / "_dance-remake/reference/audio.wav"

    if not beat_map_path.exists():
        print("Run: npm run dance-remake:beats", file=sys.stderr)
        raise SystemExit(1)
    if not audio_path.exists():
        print(f"Missing audio: {audio_path}", file=sys.stderr)
        raise SystemExit(1)

    beat_map = json.loads(beat_map_path.read_text(encoding="utf-8"))
    cues = beat_map.get("shoot_cues", [])
    segments = beat_map.get("segments", [])

    print("=== Dance Remake Shoot Cues ===")
    print(f"BPM: {beat_map.get('bpm_estimate')}  Duration: {beat_map.get('duration_sec')}s")
    print("Segments:")
    for seg in segments:
        print(f"  {seg['id']} {seg['start']}-{seg['end']}s: {seg['action']}")
    print("\nStarting playback in 2s...\n")

    time.sleep(2)
    start = time.monotonic()

    def play_audio() -> None:
        subprocess.run(["afplay", str(audio_path)], check=False)

    audio_thread = threading.Thread(target=play_audio, daemon=True)
    audio_thread.start()

    fired: set[float] = set()
    duration = float(beat_map.get("duration_sec", 10)) + 0.5

    while time.monotonic() - start < duration:
        elapsed = time.monotonic() - start
        for cue in cues:
            t = float(cue["time_sec"])
            if t not in fired and elapsed >= t:
                fired.add(t)
                seg = next((s for s in segments if s["start"] <= t < s["end"]), None)
                seg_id = seg["id"] if seg else "?"
                print(f"[{elapsed:5.2f}s] >>> {seg_id}: {cue['cue']}")
        time.sleep(0.05)

    audio_thread.join(timeout=1)
    print("\nDone.")


if __name__ == "__main__":
    main()
