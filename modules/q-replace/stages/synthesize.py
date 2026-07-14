from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from lib.common import load_json, resolve_device, save_json
from lib.pose_warp import apply_head_pose_tilt, pose_affine_warp_character, pose_delta_warp_image
from lib.wav2lip import apply_blendshape_mouth, apply_wav2lip_if_available, mouth_sync_score
from stages.audio import extract_audio


def _expression_prompt(expression: dict[str, float]) -> str:
    parts = []
    if expression.get("eye_closure", 0.0) > 0.45:
        parts.append("eyes closed")
    else:
        parts.append("eyes open")
    mouth = expression.get("mouth_open", 0.0)
    if mouth > 0.45:
        parts.append("mouth open talking")
    elif expression.get("smile", 0.0) > 0.35:
        parts.append("smiling")
    else:
        parts.append("neutral mouth")
    return ", ".join(parts)


def _bbox_size(bbox: list[float]) -> tuple[int, int]:
    x1, y1, x2, y2 = [int(v) for v in bbox]
    return max(64, x2 - x1), max(64, y2 - y1)


def _load_pose_landmarks(motion_info: dict[str, Any]) -> list[dict[str, float]]:
    motion_path = motion_info.get("motion_path")
    if not motion_path:
        return []
    motion = load_json(Path(motion_path))
    return motion.get("pose_landmarks", [])


def _apply_expression(
    image: np.ndarray,
    expression: dict[str, float],
    head_pose: dict[str, float],
    audio_energy: float,
    config: dict[str, Any],
    *,
    skip_wav2lip: bool,
    audio_path: Path | None,
    frame_idx: int,
    analysis_fps: float,
    work_dir: Path,
) -> np.ndarray:
    out = apply_head_pose_tilt(image, head_pose)
    if config["synthesis"].get("wav2lip_enabled", False) and not skip_wav2lip:
        if mouth_sync_score(expression, audio_energy) > float(config["synthesis"].get("wav2lip_threshold", 0.35)):
            wav2lip_out = apply_wav2lip_if_available(
                out,
                audio_path or work_dir / "audio.wav",
                frame_idx / analysis_fps,
                1.0 / analysis_fps,
                work_dir,
            )
            if wav2lip_out is not None:
                return cv2.resize(wav2lip_out, (out.shape[1], out.shape[0]))
    return apply_blendshape_mouth(out, expression, audio_energy)


def _generate_pose_keyframe(
    character_bgr: np.ndarray,
    openpose_bgr: np.ndarray,
    expression: dict[str, float],
    bbox: list[float],
    config: dict[str, Any],
    device: str,
) -> np.ndarray | None:
    try:
        from lib.diffusion import generate_pose_character_frame

        identity_cfg = config["identity"]
        w, h = _bbox_size(bbox)
        max_side = 512
        scale = min(1.0, max_side / max(w, h))
        w = max(256, int((w * scale) // 8) * 8)
        h = max(256, int((h * scale) // 8) * 8)
        prompt = f"{identity_cfg['prompt']}, same character as reference, {_expression_prompt(expression)}"
        generated = generate_pose_character_frame(
            character_bgr,
            openpose_bgr,
            prompt,
            identity_cfg["negative_prompt"],
            config,
            device,
            seed=int(identity_cfg["seed"]),
            width=max(512, w),
            height=max(512, h),
        )
        tw, th = _bbox_size(bbox)
        return cv2.resize(generated, (tw, th), interpolation=cv2.INTER_LANCZOS4)
    except Exception as exc:
        print(f"Pose keyframe generation failed: {exc}")
        return None


def _pose_driven_frame(
    base_image: np.ndarray,
    ref_pose: list[dict[str, float]],
    cur_pose: list[dict[str, float]],
    bbox: list[float],
) -> np.ndarray:
    if ref_pose and cur_pose:
        return pose_delta_warp_image(base_image, ref_pose, cur_pose, bbox)
    return base_image


def _fallback_pose_warp(
    character_bgra: np.ndarray,
    target_bbox: list[float],
    pose_landmarks: list[dict[str, float]],
) -> np.ndarray:
    if pose_landmarks:
        return pose_affine_warp_character(character_bgra, pose_landmarks, target_bbox)
    tw, th = _bbox_size(target_bbox)
    return cv2.resize(character_bgra, (tw, th), interpolation=cv2.INTER_LANCZOS4)


def _get_audio_energy(audio_path: Path | None, frame_idx: int, analysis_fps: float) -> float:
    if audio_path is None or not audio_path.exists():
        return 0.0
    try:
        import wave

        with wave.open(str(audio_path), "rb") as wf:
            rate = wf.getframerate()
            t = frame_idx / analysis_fps
            start = int(t * rate)
            end = int((t + 1.0 / analysis_fps) * rate)
            frames = wf.readframes(end - start)
            if not frames:
                return 0.0
            data = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
            if data.size == 0:
                return 0.0
            rms = float(np.sqrt(np.mean(data * data)) / 32768.0)
            return min(1.0, rms * 4.0)
    except Exception:
        return 0.0


def run_synthesis(
    probe_manifest: dict[str, Any],
    tracks_manifest: dict[str, Any],
    motion_manifest: dict[str, Any],
    identity_manifest: dict[str, Any],
    work_dir: Path,
    config: dict[str, Any],
    use_diffusion: bool = True,
    frame_limit: int | None = None,
    video_path: Path | None = None,
    skip_wav2lip: bool = False,
    keyframe_interval: int | None = None,
) -> dict[str, Any]:
    analysis_dir = Path(probe_manifest["analysis_dir"])
    synth_dir = work_dir / "synth_frames"
    synth_dir.mkdir(parents=True, exist_ok=True)

    device = resolve_device(config.get("device", "auto"))
    keyframe_interval = keyframe_interval or int(config["synthesis"]["keyframe_interval"])
    analysis_fps = float(probe_manifest["analysis_fps"])

    character_bgr: np.ndarray | None = None
    if identity_manifest.get("character_ref"):
        character_bgr = cv2.imread(identity_manifest["character_ref"], cv2.IMREAD_UNCHANGED)
    if character_bgr is None:
        first_person = next(iter(identity_manifest.get("persons", {}).values()), None)
        if first_person:
            character_bgr = cv2.imread(first_person["identity_path"], cv2.IMREAD_UNCHANGED)

    audio_path: Path | None = None
    if config["synthesis"].get("wav2lip_enabled", False) and not skip_wav2lip and video_path:
        audio_path = extract_audio(video_path, work_dir)

    valid_person_ids = set(tracks_manifest.get("valid_person_ids", []))
    if not valid_person_ids:
        min_frames = int(config.get("synthesis", {}).get("min_track_frames", 5))
        valid_person_ids = {
            s["person_id"] for s in tracks_manifest.get("person_stats", []) if s.get("frames", 0) >= min_frames
        }
    if not valid_person_ids:
        valid_person_ids = set(tracks_manifest["person_ids"])

    frame_keys = sorted(tracks_manifest["tracks_by_frame"].keys())
    if frame_limit is not None:
        frame_keys = frame_keys[:frame_limit]

    shot_starts = {int(s["analysis_start_frame"]) for s in probe_manifest.get("shots", [])}

    keyframe_image: dict[int, np.ndarray] = {}
    keyframe_pose: dict[int, list[dict[str, float]]] = {}

    existing_manifest_path = work_dir / "synth_manifest.json"
    existing_frames: dict[str, Any] = {}
    if existing_manifest_path.exists():
        existing_manifest = load_json(existing_manifest_path)
        existing_frames = existing_manifest.get("frames", {})
        for frame_key in sorted(existing_frames.keys(), key=int):
            for person_id_str, info in existing_frames[frame_key].items():
                if not info.get("is_keyframe"):
                    continue
                img = cv2.imread(info["path"])
                if img is None:
                    continue
                person_id = int(person_id_str)
                keyframe_image[person_id] = img
                motion_info = motion_manifest["frames"].get(frame_key, {}).get(person_id_str, {})
                keyframe_pose[person_id] = _load_pose_landmarks(motion_info)

    synth_manifest: dict[str, Any] = {"frames": dict(existing_frames), "device": device, "mode": "pose_delta"}

    for idx, frame_key in enumerate(frame_keys):
        frame_path = analysis_dir / f"frame_{frame_key}.jpg"
        if not frame_path.exists():
            continue

        frame_idx = int(frame_key)
        audio_energy = _get_audio_energy(audio_path, frame_idx, analysis_fps)
        frame_entries = tracks_manifest["tracks_by_frame"].get(frame_key, [])
        frame_out: dict[str, Any] = {}

        for entry in frame_entries:
            person_id = int(entry["person_id"])
            if person_id not in valid_person_ids or character_bgr is None:
                continue

            out_path = synth_dir / f"{frame_key}_{person_id}.png"
            cached = existing_frames.get(frame_key, {}).get(str(person_id))
            if out_path.exists() and cached:
                frame_out[str(person_id)] = cached
                continue

            motion_info = motion_manifest["frames"].get(frame_key, {}).get(str(person_id), {})
            expression = motion_info.get("expression", {})
            head_pose = motion_info.get("head_pose", {})
            cur_pose = _load_pose_landmarks(motion_info)
            openpose_path = motion_info.get("openpose_path")
            openpose = cv2.imread(openpose_path) if openpose_path else None

            is_shot_start = frame_idx in shot_starts
            is_keyframe = is_shot_start or idx % keyframe_interval == 0
            generated: np.ndarray | None = None
            used_diffusion = False
            used_pose_delta = False

            if is_keyframe and use_diffusion and openpose is not None:
                generated = _generate_pose_keyframe(
                    character_bgr,
                    openpose,
                    expression,
                    entry["bbox"],
                    config,
                    device,
                )
                used_diffusion = generated is not None

            if generated is None and person_id in keyframe_image and keyframe_pose.get(person_id):
                generated = _pose_driven_frame(
                    keyframe_image[person_id],
                    keyframe_pose[person_id],
                    cur_pose,
                    entry["bbox"],
                )
                used_pose_delta = True

            if generated is None:
                generated = _fallback_pose_warp(character_bgr, entry["bbox"], cur_pose)

            generated = _apply_expression(
                generated,
                expression,
                head_pose,
                audio_energy,
                config,
                skip_wav2lip=skip_wav2lip,
                audio_path=audio_path,
                frame_idx=frame_idx,
                analysis_fps=analysis_fps,
                work_dir=work_dir,
            )

            if used_diffusion or is_keyframe or person_id not in keyframe_image:
                keyframe_image[person_id] = generated.copy()
                keyframe_pose[person_id] = cur_pose

            out_path = synth_dir / f"{frame_key}_{person_id}.png"
            cv2.imwrite(str(out_path), generated)
            frame_out[str(person_id)] = {
                "path": str(out_path),
                "is_keyframe": is_keyframe,
                "used_diffusion": used_diffusion,
                "used_pose_delta": used_pose_delta,
            }

        synth_manifest["frames"][frame_key] = frame_out

    save_json(work_dir / "synth_manifest.json", synth_manifest)
    return synth_manifest
