from __future__ import annotations

import subprocess
from pathlib import Path


def extract_audio(video_path: Path, work_dir: Path) -> Path | None:
    audio_path = work_dir / "audio.wav"
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not audio_path.exists():
        return None
    return audio_path
