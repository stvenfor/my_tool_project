from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from lib.common import save_json

ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT / "models"

POSE_CONNECTIONS = [
    (11, 12),
    (11, 13),
    (13, 15),
    (12, 14),
    (14, 16),
    (11, 23),
    (12, 24),
    (23, 24),
    (23, 25),
    (25, 27),
    (24, 26),
    (26, 28),
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 7),
    (0, 4),
    (4, 5),
    (5, 6),
    (6, 8),
    (9, 10),
]

MODEL_URLS = {
    "pose_landmarker_heavy.task": (
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/"
        "pose_landmarker_heavy.task"
    ),
    "face_landmarker.task": (
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/"
        "face_landmarker.task"
    ),
}


def ensure_model(name: str) -> Path:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    dest = MODELS_DIR / name
    if dest.exists():
        return dest
    url = MODEL_URLS[name]
    print(f"Downloading {name} ...")
    urllib.request.urlretrieve(url, dest)
    return dest


def _draw_openpose(canvas: np.ndarray, landmarks: list[dict[str, float]], visibility_threshold: float = 0.5) -> None:
    h, w = canvas.shape[:2]
    points: dict[int, tuple[int, int]] = {}
    for idx, lm in enumerate(landmarks):
        if lm.get("visibility", 1.0) < visibility_threshold:
            continue
        x = int(lm["x"] * w)
        y = int(lm["y"] * h)
        points[idx] = (x, y)
        cv2.circle(canvas, (x, y), 4, (255, 255, 255), -1)

    for a, b in POSE_CONNECTIONS:
        if a in points and b in points:
            cv2.line(canvas, points[a], points[b], (0, 255, 0), 3, cv2.LINE_AA)


def _head_pose_from_face(landmarks: list[dict[str, float]]) -> dict[str, float]:
    if len(landmarks) < 10:
        return {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}
    nose = landmarks[1]
    left_eye = landmarks[33] if len(landmarks) > 33 else landmarks[5]
    right_eye = landmarks[263] if len(landmarks) > 263 else landmarks[2]
    dx = right_eye["x"] - left_eye["x"]
    dy = right_eye["y"] - left_eye["y"]
    roll = float(np.degrees(np.arctan2(dy, dx)))
    yaw = float((nose["x"] - (left_eye["x"] + right_eye["x"]) / 2.0) * 120.0)
    pitch = float((nose["y"] - (left_eye["y"] + right_eye["y"]) / 2.0) * 120.0)
    return {"yaw": yaw, "pitch": pitch, "roll": roll}


def _expression_metrics(blendshapes: dict[str, float]) -> dict[str, float]:
    eye_keys = [
        "eyeBlinkLeft",
        "eyeBlinkRight",
        "eyeSquintLeft",
        "eyeSquintRight",
    ]
    mouth_keys = [
        "jawOpen",
        "mouthFunnel",
        "mouthPucker",
        "mouthSmileLeft",
        "mouthSmileRight",
        "mouthClose",
    ]
    eye_closure = max(blendshapes.get(k, 0.0) for k in eye_keys[:2])
    mouth_open = max(blendshapes.get(k, 0.0) for k in mouth_keys)
    return {
        "eye_closure": float(eye_closure),
        "mouth_open": float(mouth_open),
        "smile": float(
            (blendshapes.get("mouthSmileLeft", 0.0) + blendshapes.get("mouthSmileRight", 0.0)) / 2.0
        ),
    }


def run_motion_capture(
    probe_manifest: dict[str, Any],
    tracks_manifest: dict[str, Any],
    work_dir: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    pose_model = ensure_model(config["motion"]["pose_model"])
    face_model = ensure_model(config["motion"]["face_model"])

    base_options_pose = mp_python.BaseOptions(model_asset_path=str(pose_model))
    pose_options = vision.PoseLandmarkerOptions(
        base_options=base_options_pose,
        running_mode=vision.RunningMode.IMAGE,
        min_pose_detection_confidence=config["motion"]["min_detection_confidence"],
        min_pose_presence_confidence=config["motion"]["min_tracking_confidence"],
        min_tracking_confidence=config["motion"]["min_tracking_confidence"],
        output_segmentation_masks=False,
    )

    base_options_face = mp_python.BaseOptions(model_asset_path=str(face_model))
    face_options = vision.FaceLandmarkerOptions(
        base_options=base_options_face,
        running_mode=vision.RunningMode.IMAGE,
        min_face_detection_confidence=config["motion"]["min_detection_confidence"],
        min_face_presence_confidence=config["motion"]["min_tracking_confidence"],
        min_tracking_confidence=config["motion"]["min_tracking_confidence"],
        output_face_blendshapes=True,
    )

    analysis_dir = Path(probe_manifest["analysis_dir"])
    motion_dir = work_dir / "motion"
    openpose_dir = work_dir / "openpose"
    motion_dir.mkdir(parents=True, exist_ok=True)
    openpose_dir.mkdir(parents=True, exist_ok=True)

    motion_manifest: dict[str, Any] = {"frames": {}, "person_ids": tracks_manifest["person_ids"]}

    with vision.PoseLandmarker.create_from_options(pose_options) as pose_landmarker, vision.FaceLandmarker.create_from_options(
        face_options
    ) as face_landmarker:
        for frame_key, entries in tracks_manifest["tracks_by_frame"].items():
            frame_path = analysis_dir / f"frame_{frame_key}.jpg"
            image_bgr = cv2.imread(str(frame_path))
            if image_bgr is None:
                continue
            h, w = image_bgr.shape[:2]
            image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)

            frame_motion: dict[str, Any] = {}
            for entry in entries:
                person_id = entry["person_id"]
                x1, y1, x2, y2 = [int(v) for v in entry["bbox"]]
                crop = image_bgr[max(0, y1) : min(h, y2), max(0, x1) : min(w, x2)]
                if crop.size == 0:
                    continue
                ch, cw = crop.shape[:2]
                crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                crop_mp = mp.Image(image_format=mp.ImageFormat.SRGB, data=crop_rgb)

                pose_result = pose_landmarker.detect(crop_mp)
                pose_landmarks: list[dict[str, float]] = []
                if pose_result.pose_landmarks:
                    for lm in pose_result.pose_landmarks[0]:
                        pose_landmarks.append(
                            {
                                "x": float(lm.x),
                                "y": float(lm.y),
                                "z": float(lm.z),
                                "visibility": float(lm.visibility),
                            }
                        )

                face_result = face_landmarker.detect(crop_mp)
                face_landmarks: list[dict[str, float]] = []
                blendshapes: dict[str, float] = {}
                if face_result.face_landmarks:
                    for lm in face_result.face_landmarks[0]:
                        face_landmarks.append({"x": float(lm.x), "y": float(lm.y), "z": float(lm.z)})
                if face_result.face_blendshapes:
                    for bs in face_result.face_blendshapes[0]:
                        blendshapes[bs.category_name] = float(bs.score)

                openpose_h = max(256, int(round(512 * ch / max(cw, 1))))
                openpose_w = 512
                openpose = np.zeros((openpose_h, openpose_w, 3), dtype=np.uint8)
                _draw_openpose(openpose, pose_landmarks)
                openpose_path = openpose_dir / f"{frame_key}_{person_id}.png"
                cv2.imwrite(str(openpose_path), openpose)

                head_pose = _head_pose_from_face(face_landmarks)
                expression = _expression_metrics(blendshapes)

                person_motion = {
                    "person_id": person_id,
                    "bbox": entry["bbox"],
                    "pose_landmarks": pose_landmarks,
                    "face_landmarks": face_landmarks,
                    "blendshapes": blendshapes,
                    "head_pose": head_pose,
                    "expression": expression,
                    "openpose_path": str(openpose_path),
                }
                motion_path = motion_dir / f"{frame_key}_{person_id}.json"
                save_json(motion_path, person_motion)
                frame_motion[str(person_id)] = {
                    "motion_path": str(motion_path),
                    "openpose_path": str(openpose_path),
                    "expression": expression,
                    "head_pose": head_pose,
                }

            motion_manifest["frames"][frame_key] = frame_motion

    save_json(work_dir / "motion_manifest.json", motion_manifest)
    return motion_manifest
