from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def _remove_white_background(bgr: np.ndarray, threshold: int = 245) -> np.ndarray:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    mask = (gray < threshold).astype(np.uint8) * 255
    mask = cv2.GaussianBlur(mask, (5, 5), 0)
    bgra = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA)
    bgra[:, :, 3] = mask
    return bgra


def load_character_rgba(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise FileNotFoundError(f"Character image not found: {path}")

    if image.ndim == 3 and image.shape[2] == 4:
        return image

    bgr = image[:, :, :3] if image.ndim == 3 else image
    try:
        from rembg import remove
        from PIL import Image

        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        out = remove(Image.fromarray(rgb))
        rgba = np.array(out.convert("RGBA"))
        return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA)
    except Exception:
        return _remove_white_background(bgr)


def prepare_character_asset(source: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    rgba = load_character_rgba(source)
    cv2.imwrite(str(dest), rgba)
    return dest
