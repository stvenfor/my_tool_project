from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from lib.common import save_json, time_to_frame_index


def _load_mask(mask_path: Path, shape: tuple[int, int]) -> np.ndarray:
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return np.zeros(shape, dtype=np.float32)
    if mask.shape[:2] != shape:
        mask = cv2.resize(mask, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)
    return mask.astype(np.float32) / 255.0


def _match_color(source: np.ndarray, target: np.ndarray, mask: np.ndarray) -> np.ndarray:
    if mask.sum() < 1.0:
        return source
    mask_u8 = (np.clip(mask, 0, 1) * 255).astype(np.uint8)
    src_mean = np.array([cv2.mean(source[:, :, c], mask=mask_u8)[0] for c in range(3)])
    tgt_mean = np.array([cv2.mean(target[:, :, c], mask=mask_u8)[0] for c in range(3)])
    delta = tgt_mean - src_mean
    adjusted = source.astype(np.float32)
    for c in range(3):
        adjusted[:, :, c] += delta[c]
    return np.clip(adjusted, 0, 255).astype(np.uint8)


def run_composite(
    probe_manifest: dict[str, Any],
    tracks_manifest: dict[str, Any],
    synth_manifest: dict[str, Any],
    work_dir: Path,
    config: dict[str, Any],
    frame_limit: int | None = None,
) -> dict[str, Any]:
    frames_dir = Path(probe_manifest["frames_dir"])
    composite_dir = work_dir / "composite_frames"
    composite_dir.mkdir(parents=True, exist_ok=True)

    analysis_fps = probe_manifest["analysis_fps"]
    output_fps = probe_manifest["output_fps"]
    feather = int(config["composite"]["alpha_feather"])
    color_match = bool(config["composite"]["color_match"])

    frame_keys = sorted(synth_manifest["frames"].keys())
    if frame_limit is not None:
        frame_keys = frame_keys[:frame_limit]

    mapping: dict[str, str] = {}

    for frame_key in frame_keys:
        analysis_index = int(frame_key)
        output_index = time_to_frame_index((analysis_index - 1) / analysis_fps, output_fps) + 1
        orig_path = frames_dir / f"orig_{output_index:06d}.jpg"
        if not orig_path.exists():
            orig_path = frames_dir / f"orig_{analysis_index:06d}.jpg"
        base = cv2.imread(str(orig_path))
        if base is None:
            continue

        h, w = base.shape[:2]
        entries = tracks_manifest["tracks_by_frame"].get(frame_key, [])
        entries_sorted = sorted(entries, key=lambda e: e["bbox"][2] * e["bbox"][3])

        composite = base.copy()
        for entry in entries_sorted:
            person_id = str(entry["person_id"])
            synth_info = synth_manifest["frames"].get(frame_key, {}).get(person_id)
            if not synth_info:
                continue
            layer = cv2.imread(synth_info["path"], cv2.IMREAD_UNCHANGED)
            if layer is None:
                continue

            x1, y1, x2, y2 = [int(v) for v in entry["bbox"]]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            target_w = max(1, x2 - x1)
            target_h = max(1, y2 - y1)

            layer_alpha: np.ndarray | None = None
            if layer.ndim == 3 and layer.shape[2] == 4:
                layer_alpha = cv2.resize(layer[:, :, 3], (target_w, target_h), interpolation=cv2.INTER_LINEAR).astype(
                    np.float32
                ) / 255.0
                layer = cv2.resize(layer[:, :, :3], (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)
            else:
                layer = cv2.resize(layer, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)

            mask = _load_mask(Path(entry["mask_path"]), (h, w))
            crop_mask = mask[y1:y2, x1:x2]
            if layer_alpha is not None:
                crop_mask = np.clip(crop_mask * layer_alpha, 0.0, 1.0)
            if feather > 0:
                k = feather * 2 + 1
                crop_mask = cv2.GaussianBlur(crop_mask, (k, k), 0)

            if color_match:
                target_crop = composite[y1:y2, x1:x2]
                layer = _match_color(layer, target_crop, crop_mask)

            alpha = crop_mask[..., None]
            target_region = composite[y1:y2, x1:x2].astype(np.float32)
            layer_f = layer.astype(np.float32)
            blended = layer_f * alpha + target_region * (1.0 - alpha)
            composite[y1:y2, x1:x2] = blended.astype(np.uint8)

        out_name = f"{output_index:06d}.png"
        out_path = composite_dir / out_name
        if out_path.exists():
            mapping[frame_key] = str(out_path)
            continue
        cv2.imwrite(str(out_path), composite)
        mapping[frame_key] = str(out_path)

    manifest = {
        "composite_dir": str(composite_dir),
        "frame_mapping": mapping,
        "frame_count": len(mapping),
    }
    save_json(work_dir / "composite_manifest.json", manifest)
    return manifest
