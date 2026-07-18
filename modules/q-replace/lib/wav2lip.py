from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np


def mouth_sync_score(expression: dict[str, float], audio_energy: float) -> float:
    mouth = expression.get("mouth_open", 0.0)
    return abs(mouth - audio_energy)


def apply_blendshape_mouth(image_bgr: np.ndarray, expression: dict[str, float], audio_energy: float = 0.0) -> np.ndarray:
    """Fallback mouth animation driven by blendshape + audio energy."""
    out = image_bgr.copy()
    h, w = out.shape[:2]
    face_h = int(h * 0.38)
    face_w = int(w * 0.5)
    x0 = (w - face_w) // 2
    y0 = int(h * 0.12)
    roi = out[y0 : y0 + face_h, x0 : x0 + face_w]
    if roi.size == 0:
        return out

    eye_close = expression.get("eye_closure", 0.0)
    if eye_close > 0.35:
        eye_y = int(face_h * 0.25)
        eye_h = max(2, int(face_h * 0.18 * eye_close))
        roi[eye_y : eye_y + eye_h, :] = (roi[eye_y : eye_y + eye_h, :] * (1.0 - eye_close * 0.5)).astype(np.uint8)

    mouth_open = max(expression.get("mouth_open", 0.0), audio_energy * 0.8)
    if mouth_open > 0.15:
        mouth_y = int(face_h * 0.62)
        mouth_h = max(2, int(face_h * 0.1 * mouth_open))
        mouth_w = int(face_w * 0.32)
        mx = (face_w - mouth_w) // 2
        overlay = roi.copy()
        cv2.ellipse(
            overlay,
            (mx + mouth_w // 2, mouth_y),
            (max(2, mouth_w // 2), mouth_h),
            0,
            0,
            360,
            (45, 35, 30),
            -1,
            cv2.LINE_AA,
        )
        alpha = min(0.55, mouth_open)
        roi[:] = cv2.addWeighted(overlay, alpha, roi, 1.0 - alpha, 0)

    out[y0 : y0 + face_h, x0 : x0 + face_w] = roi
    return out


def _wav2lip_repo() -> Path:
    return Path.home() / "Wav2Lip"


def _wav2lip_available() -> Path | None:
    checkpoint = _wav2lip_repo() / "checkpoints" / "wav2lip_gan.pth"
    if checkpoint.exists() and checkpoint.stat().st_size > 1_000_000:
        return checkpoint
    return None


def _wav2lip_python(repo: Path) -> str:
    """Prefer the dedicated Wav2Lip venv over the system interpreter."""
    venv_python = repo / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable or "python3"


def apply_wav2lip_if_available(
    face_bgr: np.ndarray,
    audio_path: Path,
    start_time: float,
    duration: float,
    work_dir: Path,
) -> np.ndarray | None:
    checkpoint = _wav2lip_available()
    if checkpoint is None or not audio_path.exists():
        return None

    wav2lip_repo = _wav2lip_repo()
    inference = wav2lip_repo / "inference.py"
    if not inference.exists():
        return None

    clip_dir = work_dir / "wav2lip_clips"
    clip_dir.mkdir(parents=True, exist_ok=True)
    face_path = clip_dir / "face.png"
    cv2.imwrite(str(face_path), face_bgr)

    out_path = clip_dir / f"out_{start_time:.3f}.mp4"
    cmd = [
        _wav2lip_python(wav2lip_repo),
        str(inference),
        "--checkpoint_path",
        str(checkpoint),
        "--face",
        str(face_path),
        "--audio",
        str(audio_path),
        "--outfile",
        str(out_path),
        "--fps",
        "25",
    ]
    try:
        subprocess.run(cmd, check=True, cwd=str(wav2lip_repo), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cap = cv2.VideoCapture(str(out_path))
        ok, frame = cap.read()
        cap.release()
        if ok:
            return frame
    except Exception:
        return None
    return None
