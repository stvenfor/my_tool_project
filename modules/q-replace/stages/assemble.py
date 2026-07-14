from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import cv2

from lib.common import save_json


def _prepare_sequential_frames(
    composite_dir: Path,
    frames_dir: Path,
    output_frame_count: int,
    seq_dir: Path,
) -> int:
    seq_dir.mkdir(parents=True, exist_ok=True)
    for old in seq_dir.glob("*.png"):
        old.unlink()

    written = 0
    for index in range(1, output_frame_count + 1):
        name = f"{index:06d}"
        composite_path = composite_dir / f"{name}.png"
        if composite_path.exists():
            dest = seq_dir / f"{name}.png"
            dest.write_bytes(composite_path.read_bytes())
            written += 1
            continue

        orig_jpg = frames_dir / f"orig_{name}.jpg"
        if not orig_jpg.exists():
            continue
        image = cv2.imread(str(orig_jpg))
        if image is None:
            continue
        cv2.imwrite(str(seq_dir / f"{name}.png"), image)
        written += 1
    return written


def _encode_from_frames(
    composite_dir: Path,
    output_path: Path,
    fps: float,
    crf: int,
    audio_source: Path | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pattern = str(composite_dir / "%06d.png")
    if not list(composite_dir.glob("*.png")):
        raise RuntimeError(f"No composite frames found in {composite_dir}")

    video_only = output_path.with_suffix(".video-only.mp4")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            pattern,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            str(crf),
            str(video_only),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if audio_source and audio_source.exists():
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video_only),
                "-i",
                str(audio_source),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0?",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-shortest",
                str(output_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        video_only.unlink(missing_ok=True)
    else:
        video_only.rename(output_path)


def run_assemble(
    probe_manifest: dict[str, Any],
    composite_manifest: dict[str, Any],
    work_dir: Path,
    video_path: Path,
    config: dict[str, Any],
    preview_only: bool = False,
) -> dict[str, Any]:
    composite_dir = Path(composite_manifest["composite_dir"])
    output_fps = float(probe_manifest["output_fps"])
    crf = int(config["output"]["crf"])
    preview_duration = float(config["output"]["preview_duration"])

    final_path = work_dir / "final.mp4"
    preview_path = work_dir / "preview_3s.mp4"

    if preview_only:
        preview_dir = work_dir / "preview_frames"
        preview_dir.mkdir(parents=True, exist_ok=True)
        max_frames = int(preview_duration * output_fps)
        frames = sorted(composite_dir.glob("*.png"))
        if not frames:
            raise RuntimeError("No frames available for preview")
        start = max(0, len(frames) // 2 - max_frames // 2)
        selected = frames[start : start + max_frames]
        for idx, src in enumerate(selected, start=1):
            dest = preview_dir / f"{idx:06d}.png"
            dest.write_bytes(src.read_bytes())
        _encode_from_frames(preview_dir, preview_path, output_fps, crf, video_path)
        manifest = {"preview_path": str(preview_path), "preview_frames": len(selected)}
    else:
        seq_dir = work_dir / "encode_frames"
        frames_dir = Path(probe_manifest["frames_dir"])
        output_count = int(probe_manifest["output_frame_count"])
        prepared = _prepare_sequential_frames(composite_dir, frames_dir, output_count, seq_dir)
        if prepared < 1:
            raise RuntimeError("No frames prepared for final encode")
        _encode_from_frames(seq_dir, final_path, output_fps, crf, video_path)
        manifest = {"final_path": str(final_path), "encoded_frames": prepared}

        # Also build preview from middle segment if enough frames exist.
        frames = sorted(composite_dir.glob("*.png"))
        if frames:
            preview_dir = work_dir / "preview_frames"
            preview_dir.mkdir(parents=True, exist_ok=True)
            max_frames = int(preview_duration * output_fps)
            start = max(0, len(frames) // 2 - max_frames // 2)
            selected = frames[start : start + max_frames]
            for idx, src in enumerate(selected, start=1):
                dest = preview_dir / f"{idx:06d}.png"
                dest.write_bytes(src.read_bytes())
            _encode_from_frames(preview_dir, preview_path, output_fps, crf, video_path)
            manifest["preview_path"] = str(preview_path)

    save_json(work_dir / "assemble_manifest.json", manifest)
    return manifest
