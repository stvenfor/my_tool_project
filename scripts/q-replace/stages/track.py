from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from lib.common import save_json


def _bbox_mask(shape: tuple[int, int], bbox: list[float], feather: int) -> np.ndarray:
    h, w = shape
    mask = np.zeros((h, w), dtype=np.float32)
    x1, y1, x2, y2 = [int(v) for v in bbox]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    mask[y1:y2, x1:x2] = 1.0
    if feather > 0:
        k = feather * 2 + 1
        mask = cv2.GaussianBlur(mask, (k, k), 0)
    return np.clip(mask, 0.0, 1.0)


def _try_rembg_mask(image_bgr: np.ndarray) -> np.ndarray | None:
    try:
        from rembg import remove
        from PIL import Image

        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        out = remove(pil)
        alpha = np.array(out.split()[-1], dtype=np.float32) / 255.0
        return alpha
    except Exception:
        return None


def _group_frames_by_shot(frame_paths: list[Path], shots: list[dict[str, Any]]) -> list[tuple[int, list[Path]]]:
    if not shots:
        return [(0, frame_paths)]

    groups: list[tuple[int, list[Path]]] = []
    for shot in shots:
        shot_id = int(shot["shot_id"])
        start = int(shot["analysis_start_frame"])
        end = int(shot["analysis_end_frame"])
        group = [p for p in frame_paths if start <= int(p.stem.split("_")[-1]) <= end]
        if group:
            groups.append((shot_id, group))
    return groups or [(0, frame_paths)]


def _iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class HogTracker:
    """Fallback person tracker when ultralytics/torch is unavailable."""

    def __init__(self) -> None:
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        self.next_id = 1
        self.tracks: dict[int, list[float]] = {}

    def reset(self, id_offset: int) -> None:
        self.next_id = id_offset + 1
        self.tracks = {}


def _hog_detect(image: np.ndarray, tracker: HogTracker, conf: float) -> list[tuple[int, list[float], float]]:
    rects, weights = tracker.hog.detectMultiScale(image, winStride=(8, 8), padding=(8, 8), scale=1.05)
    detections: list[tuple[list[float], float]] = []
    for (x, y, w, h), weight in zip(rects, weights, strict=True):
        score = float(weight)
        if score < conf:
            continue
        detections.append(([float(x), float(y), float(x + w), float(y + h)], score))

    assigned: dict[int, tuple[list[float], float]] = {}
    used_tracks: set[int] = set()
    for bbox, score in sorted(detections, key=lambda item: item[1], reverse=True):
        best_id = None
        best_iou = 0.0
        for track_id, prev_bbox in tracker.tracks.items():
            if track_id in used_tracks:
                continue
            overlap = _iou(bbox, prev_bbox)
            if overlap > best_iou:
                best_iou = overlap
                best_id = track_id
        if best_id is not None and best_iou >= 0.25:
            track_id = best_id
        else:
            track_id = tracker.next_id
            tracker.next_id += 1
        used_tracks.add(track_id)
        assigned[track_id] = (bbox, score)

    tracker.tracks = {tid: bbox for tid, (bbox, _) in assigned.items()}
    return [(tid, bbox, score) for tid, (bbox, score) in assigned.items()]


def _process_frame(
    image: np.ndarray,
    frame_key: str,
    detections: list[tuple[int, list[float], float]],
    masks_root: Path,
    feather: int,
    person_stats: dict[int, dict[str, Any]],
    shot_id: int,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for person_id, bbox_list, score in detections:
        x1, y1, x2, y2 = [int(v) for v in bbox_list]
        crop = image[max(0, y1) : min(image.shape[0], y2), max(0, x1) : min(image.shape[1], x2)]
        mask = _try_rembg_mask(crop) if crop.size else None
        if mask is None:
            mask_crop = _bbox_mask(image.shape[:2], bbox_list, feather)
        else:
            mask_full = np.zeros(image.shape[:2], dtype=np.float32)
            mask_full[max(0, y1) : min(image.shape[0], y2), max(0, x1) : min(image.shape[1], x2)] = mask
            k = feather * 2 + 1
            mask_crop = cv2.GaussianBlur(mask_full, (k, k), 0)

        mask_path = masks_root / f"{frame_key}_{person_id}.png"
        cv2.imwrite(str(mask_path), (np.clip(mask_crop, 0, 1) * 255).astype(np.uint8))

        entry = {
            "person_id": person_id,
            "shot_id": shot_id,
            "bbox": bbox_list,
            "confidence": float(score),
            "mask_path": str(mask_path),
        }
        entries.append(entry)

        stats = person_stats.setdefault(
            person_id,
            {
                "person_id": person_id,
                "shot_id": shot_id,
                "frames": 0,
                "avg_conf": 0.0,
                "best_frame": frame_key,
                "best_conf": 0.0,
            },
        )
        stats["frames"] += 1
        stats["avg_conf"] += float(score)
        if float(score) > stats["best_conf"]:
            stats["best_conf"] = float(score)
            stats["best_frame"] = frame_key
    return entries


def _run_yolo_tracking(
    frame_groups: list[tuple[int, list[Path]]],
    model_name: str,
    conf: float,
    config: dict[str, Any],
    masks_root: Path,
    feather: int,
) -> tuple[dict[str, list[dict[str, Any]]], dict[int, dict[str, Any]], list[dict[str, Any]]]:
    from ultralytics import YOLO

    tracks_by_frame: dict[str, list[dict[str, Any]]] = {}
    person_stats: dict[int, dict[str, Any]] = {}
    quality_flags: list[dict[str, Any]] = []

    for shot_id, group in frame_groups:
        model = YOLO(model_name)
        id_offset = shot_id * 100

        for frame_path in group:
            frame_idx = int(frame_path.stem.split("_")[-1])
            image = cv2.imread(str(frame_path))
            if image is None:
                continue

            results = model.track(
                image,
                persist=True,
                classes=[0],
                conf=conf,
                iou=config["tracking"]["iou"],
                tracker="botsort.yaml",
                verbose=False,
            )

            frame_key = f"{frame_idx:06d}"
            entries: list[dict[str, Any]] = []
            if results and results[0].boxes is not None and results[0].boxes.id is not None:
                boxes = results[0].boxes.xyxy.cpu().numpy()
                ids = results[0].boxes.id.cpu().numpy().astype(int)
                confs = results[0].boxes.conf.cpu().numpy()
                detections = [(id_offset + int(local_id), bbox.tolist(), float(score)) for local_id, bbox, score in zip(ids, boxes, confs, strict=True)]
                entries = _process_frame(image, frame_key, detections, masks_root, feather, person_stats, shot_id)

            tracks_by_frame[frame_key] = entries
            if len(entries) > 4:
                quality_flags.append({"frame": frame_key, "issue": "too_many_people", "count": len(entries)})

    return tracks_by_frame, person_stats, quality_flags


def _run_hog_tracking(
    frame_groups: list[tuple[int, list[Path]]],
    conf: float,
    masks_root: Path,
    feather: int,
) -> tuple[dict[str, list[dict[str, Any]]], dict[int, dict[str, Any]], list[dict[str, Any]]]:
    tracks_by_frame: dict[str, list[dict[str, Any]]] = {}
    person_stats: dict[int, dict[str, Any]] = {}
    quality_flags: list[dict[str, Any]] = []
    tracker = HogTracker()

    for shot_id, group in frame_groups:
        id_offset = shot_id * 100
        tracker.reset(id_offset)

        for frame_path in group:
            frame_idx = int(frame_path.stem.split("_")[-1])
            image = cv2.imread(str(frame_path))
            if image is None:
                continue

            frame_key = f"{frame_idx:06d}"
            detections = _hog_detect(image, tracker, conf)
            entries = _process_frame(image, frame_key, detections, masks_root, feather, person_stats, shot_id)
            tracks_by_frame[frame_key] = entries
            if len(entries) > 4:
                quality_flags.append({"frame": frame_key, "issue": "too_many_people", "count": len(entries)})

    return tracks_by_frame, person_stats, quality_flags


def _filter_tracks(
    tracks_by_frame: dict[str, list[dict[str, Any]]],
    person_stats: dict[int, dict[str, Any]],
    config: dict[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], set[int]]:
    min_frames = int(config.get("synthesis", {}).get("min_track_frames", 5))
    max_per_frame = int(config.get("synthesis", {}).get("max_persons_per_frame", 4))

    valid_ids = {pid for pid, stats in person_stats.items() if stats["frames"] >= min_frames}
    filtered: dict[str, list[dict[str, Any]]] = {}

    for frame_key, entries in tracks_by_frame.items():
        kept = [e for e in entries if e["person_id"] in valid_ids]
        kept.sort(key=lambda e: e["confidence"], reverse=True)
        filtered[frame_key] = kept[:max_per_frame]

    return filtered, valid_ids


def run_tracking(
    probe_manifest: dict[str, Any],
    work_dir: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    analysis_dir = Path(probe_manifest["analysis_dir"])
    analysis_fps = float(probe_manifest["analysis_fps"])
    model_name = config["tracking"]["model"]
    conf = config["tracking"]["conf"]
    feather = config["tracking"]["mask_feather"]

    masks_root = work_dir / "masks"
    masks_root.mkdir(parents=True, exist_ok=True)

    frame_paths = sorted(analysis_dir.glob("frame_*.jpg"))
    frame_groups = _group_frames_by_shot(frame_paths, probe_manifest.get("shots", []))

    backend = "yolo"
    try:
        tracks_by_frame, person_stats, quality_flags = _run_yolo_tracking(
            frame_groups, model_name, conf, config, masks_root, feather
        )
    except Exception as exc:
        print(f"YOLO tracking unavailable ({exc}), falling back to OpenCV HOG.")
        backend = "hog"
        tracks_by_frame, person_stats, quality_flags = _run_hog_tracking(
            frame_groups, conf, masks_root, feather
        )

    for stats in person_stats.values():
        stats["avg_conf"] = round(stats["avg_conf"] / max(stats["frames"], 1), 4)

    tracks_by_frame, valid_person_ids = _filter_tracks(tracks_by_frame, person_stats, config)

    manifest = {
        "tracks_by_frame": tracks_by_frame,
        "person_ids": sorted(person_stats.keys()),
        "valid_person_ids": sorted(valid_person_ids),
        "person_stats": [person_stats[pid] for pid in sorted(person_stats.keys())],
        "frame_count": len(frame_paths),
        "quality_flags": quality_flags,
        "analysis_fps": analysis_fps,
        "backend": backend,
    }
    save_json(work_dir / "tracks.json", manifest)
    return manifest
