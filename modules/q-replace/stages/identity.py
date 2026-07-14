from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from lib.common import resolve_device, save_json


def _score_reference_frame(
    image_bgr: np.ndarray,
    bbox: list[float],
    motion: dict[str, Any] | None,
    confidence: float,
) -> float:
    h, w = image_bgr.shape[:2]
    x1, y1, x2, y2 = bbox
    area = max(0.0, (x2 - x1) * (y2 - y1)) / float(w * h)
    area_score = min(area * 4.0, 1.0)

    face_score = 0.0
    pose_score = 0.0
    frontal_score = 0.0
    if motion:
        face_count = len(motion.get("face_landmarks", []))
        pose_count = len(motion.get("pose_landmarks", []))
        face_score = min(face_count / 100.0, 1.0)
        pose_score = min(pose_count / 20.0, 1.0)
        yaw = abs(motion.get("head_pose", {}).get("yaw", 90.0))
        frontal_score = max(0.0, 1.0 - yaw / 45.0)

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    x1i, y1i, x2i, y2i = [int(v) for v in bbox]
    crop = gray[max(0, y1i) : min(h, y2i), max(0, x1i) : min(w, x2i)]
    sharpness = float(cv2.Laplacian(crop, cv2.CV_64F).var()) if crop.size else 0.0
    sharp_score = min(sharpness / 250.0, 1.0)

    return float(0.25 * area_score + 0.2 * face_score + 0.2 * pose_score + 0.15 * frontal_score + 0.1 * sharp_score + 0.1 * confidence)


def _load_motion(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _stylize_fallback(crop_bgr: np.ndarray) -> np.ndarray:
    h, w = crop_bgr.shape[:2]
    scale = 0.45
    small = cv2.resize(crop_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    chibi = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
    chibi = cv2.bilateralFilter(chibi, 9, 80, 80)
    return chibi


def _generate_with_diffusers(
    crop_bgr: np.ndarray,
    config: dict[str, Any],
    device: str,
) -> np.ndarray:
    from lib.diffusion import generate_img2img_controlnet

    identity_cfg = config["identity"]
    openpose = np.zeros((512, 512, 3), dtype=np.uint8)
    return generate_img2img_controlnet(
        crop_bgr,
        openpose,
        identity_cfg["prompt"],
        identity_cfg["negative_prompt"],
        config,
        device,
        strength=float(identity_cfg["strength"]),
        num_inference_steps=int(identity_cfg["num_inference_steps"]),
        guidance_scale=float(identity_cfg["guidance_scale"]),
        controlnet_conditioning_scale=0.4,
        seed=int(identity_cfg["seed"]),
    )


def run_identity_generation(
    probe_manifest: dict[str, Any],
    tracks_manifest: dict[str, Any],
    motion_manifest: dict[str, Any],
    work_dir: Path,
    config: dict[str, Any],
    use_diffusion: bool = True,
    character_ref: Path | None = None,
) -> dict[str, Any]:
    analysis_dir = Path(probe_manifest["analysis_dir"])
    identities_dir = work_dir / "identities"
    references_dir = work_dir / "references"
    identities_dir.mkdir(parents=True, exist_ok=True)
    references_dir.mkdir(parents=True, exist_ok=True)

    device = resolve_device(config.get("device", "auto"))
    valid_person_ids = set(tracks_manifest.get("valid_person_ids", []))
    if not valid_person_ids:
        min_frames = int(config.get("synthesis", {}).get("min_track_frames", 5))
        valid_person_ids = {
            s["person_id"] for s in tracks_manifest.get("person_stats", []) if s.get("frames", 0) >= min_frames
        }
    if not valid_person_ids:
        valid_person_ids = set(tracks_manifest["person_ids"])
    identity_manifest: dict[str, Any] = {
        "persons": {},
        "device": device,
        "valid_person_ids": sorted(valid_person_ids),
    }

    shared_character_path: Path | None = None
    if character_ref is not None:
        from lib.character import prepare_character_asset

        shared_character_path = work_dir / "character_ref.png"
        prepare_character_asset(character_ref, shared_character_path)
        identity_manifest["character_ref"] = str(shared_character_path.resolve())
        print(f"Using fixed character: {character_ref}")

        for person_id in valid_person_ids:
            identity_path = identities_dir / f"person_{person_id}.png"
            if not identity_path.exists():
                identity_path.write_bytes(shared_character_path.read_bytes())
            identity_manifest["persons"][str(person_id)] = {
                "person_id": person_id,
                "identity_path": str(identity_path),
                "uses_fixed_character": True,
                "generated_with_diffusion": False,
            }
        save_json(work_dir / "identity_manifest.json", identity_manifest)
        return identity_manifest

    for person_id in valid_person_ids:
        best_score = -1.0
        best_frame = None
        best_entry = None
        best_motion = None

        for frame_key, entries in tracks_manifest["tracks_by_frame"].items():
            for entry in entries:
                if entry["person_id"] != person_id:
                    continue
                motion_info = motion_manifest["frames"].get(frame_key, {}).get(str(person_id))
                motion = _load_motion(Path(motion_info["motion_path"])) if motion_info else None
                frame_path = analysis_dir / f"frame_{frame_key}.jpg"
                image = cv2.imread(str(frame_path))
                if image is None:
                    continue
                score = _score_reference_frame(image, entry["bbox"], motion, entry["confidence"])
                if score > best_score:
                    best_score = score
                    best_frame = frame_key
                    best_entry = entry
                    best_motion = motion

        if best_entry is None or best_frame is None:
            continue

        frame_path = analysis_dir / f"frame_{best_frame}.jpg"
        image = cv2.imread(str(frame_path))
        x1, y1, x2, y2 = [int(v) for v in best_entry["bbox"]]
        h, w = image.shape[:2]
        crop = image[max(0, y1) : min(h, y2), max(0, x1) : min(w, x2)]
        ref_path = references_dir / f"person_{person_id}_ref.jpg"
        cv2.imwrite(str(ref_path), crop)

        identity_path = identities_dir / f"person_{person_id}.png"
        generated = False
        if use_diffusion:
            try:
                out_bgr = _generate_with_diffusers(crop, config, device)
                cv2.imwrite(str(identity_path), out_bgr)
                generated = True
            except Exception as exc:
                print(f"Diffusion identity generation failed for person {person_id}: {exc}")

        if not generated:
            out_bgr = _stylize_fallback(crop)
            cv2.imwrite(str(identity_path), out_bgr)

        identity_manifest["persons"][str(person_id)] = {
            "person_id": person_id,
            "reference_frame": best_frame,
            "reference_score": round(best_score, 4),
            "reference_path": str(ref_path),
            "identity_path": str(identity_path),
            "generated_with_diffusion": generated,
            "uses_fixed_character": False,
            "expression_baseline": best_motion.get("expression", {}) if best_motion else {},
        }

    save_json(work_dir / "identity_manifest.json", identity_manifest)
    return identity_manifest
