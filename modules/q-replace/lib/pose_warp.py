from __future__ import annotations

import cv2
import numpy as np

# MediaPipe pose indices used for piecewise warp
_WARP_INDICES = [0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]
_LEFT_SHOULDER = 11
_RIGHT_SHOULDER = 12
_LEFT_HIP = 23
_RIGHT_HIP = 24


def _landmark_xy(
    landmarks: list[dict[str, float]],
    index: int,
    width: int,
    height: int,
    *,
    min_visibility: float = 0.3,
) -> np.ndarray | None:
    if index >= len(landmarks):
        return None
    lm = landmarks[index]
    if lm.get("visibility", 1.0) < min_visibility:
        return None
    return np.array([lm["x"] * width, lm["y"] * height], dtype=np.float32)


def _collect_warp_points(
    landmarks: list[dict[str, float]],
    width: int,
    height: int,
) -> tuple[np.ndarray, list[int]]:
    points: list[np.ndarray] = []
    indices: list[int] = []
    for idx in _WARP_INDICES:
        pt = _landmark_xy(landmarks, idx, width, height)
        if pt is not None:
            points.append(pt)
            indices.append(idx)
    if len(points) < 3:
        return np.empty((0, 2), dtype=np.float32), []
    return np.asarray(points, dtype=np.float32), indices


def _clamp_point(x: float, y: float, w: int, h: int) -> tuple[float, float]:
    return (
        float(np.clip(x, 0.0, max(0.0, w - 1))),
        float(np.clip(y, 0.0, max(0.0, h - 1))),
    )


def _apply_piecewise_affine(
    image: np.ndarray,
    src_pts: np.ndarray,
    dst_pts: np.ndarray,
    out_size: tuple[int, int],
) -> np.ndarray:
    """Warp image with Delaunay triangles from src_pts to dst_pts."""
    w, h = out_size
    if src_pts.shape[0] < 3 or dst_pts.shape[0] < 3:
        return cv2.resize(image, (w, h), interpolation=cv2.INTER_LANCZOS4)

    try:
        corners = np.float32([[0, 0], [w - 1, 0], [0, h - 1], [w - 1, h - 1]])
        src = np.vstack([src_pts, corners])
        dst = np.vstack([dst_pts, corners])

        rect = (0, 0, w, h)
        subdiv = cv2.Subdiv2D(rect)
        for x, y in dst:
            cx, cy = _clamp_point(float(x), float(y), w, h)
            subdiv.insert((cx, cy))

        triangles: list[tuple[int, int, int]] = []
        for t in subdiv.getTriangleList():
            pts = [(t[0], t[1]), (t[2], t[3]), (t[4], t[5])]
            idxs: list[int] = []
            for px, py in pts:
                dists = np.sum((dst - np.float32([px, py])) ** 2, axis=1)
                idx = int(np.argmin(dists))
                if dists[idx] > 9.0:
                    break
                idxs.append(idx)
            else:
                if len(idxs) == 3 and len(set(idxs)) == 3:
                    tri = tuple(sorted(idxs))
                    if tri not in triangles:
                        triangles.append(tri)

        if not triangles:
            return cv2.resize(image, (w, h), interpolation=cv2.INTER_LANCZOS4)

        if image.ndim == 3 and image.shape[2] == 4:
            warped = np.zeros((h, w, 4), dtype=image.dtype)
        else:
            warped = np.zeros((h, w, image.shape[2]), dtype=image.dtype)

        ih, iw = image.shape[:2]
        if (iw, ih) != (w, h):
            image = cv2.resize(image, (w, h), interpolation=cv2.INTER_LANCZOS4)

        for i, j, k in triangles:
            src_tri = np.float32([src[i], src[j], src[k]])
            dst_tri = np.float32([dst[i], dst[j], dst[k]])
            matrix = cv2.getAffineTransform(src_tri, dst_tri)

            x, y, bw, bh = cv2.boundingRect(dst_tri)
            x2, y2 = x + bw, y + bh
            x, y = max(0, x), max(0, y)
            x2, y2 = min(w, x2), min(h, y2)
            bw, bh = x2 - x, y2 - y
            if bw <= 0 or bh <= 0:
                continue

            warped_tri = cv2.warpAffine(
                image,
                matrix,
                (w, h),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_REFLECT_101,
            )

            mask = np.zeros((bh, bw), dtype=np.float32)
            local_tri = dst_tri.copy()
            local_tri[:, 0] -= x
            local_tri[:, 1] -= y
            cv2.fillConvexPoly(mask, local_tri.astype(np.int32), 1.0, lineType=cv2.LINE_AA)

            patch = warped_tri[y:y2, x:x2]
            m = mask[..., None]
            warped[y:y2, x:x2] = (
                patch.astype(np.float32) * m + warped[y:y2, x:x2].astype(np.float32) * (1.0 - m)
            ).astype(image.dtype)

        return warped
    except cv2.error:
        return cv2.resize(image, (w, h), interpolation=cv2.INTER_LANCZOS4)


def pose_affine_warp_character(
    character_bgra: np.ndarray,
    pose_landmarks: list[dict[str, float]],
    bbox: list[float],
) -> np.ndarray:
    """Affine warp character toward detected torso pose (fallback without diffusion)."""
    x1, y1, x2, y2 = [int(v) for v in bbox]
    tw = max(1, x2 - x1)
    th = max(1, y2 - y1)

    ch, cw = character_bgra.shape[:2]
    src_pts = np.float32(
        [
            [cw * 0.35, ch * 0.28],
            [cw * 0.65, ch * 0.28],
            [cw * 0.5, ch * 0.72],
        ]
    )

    if len(pose_landmarks) < 25:
        return cv2.resize(character_bgra, (tw, th), interpolation=cv2.INTER_LANCZOS4)

    ls = _landmark_xy(pose_landmarks, _LEFT_SHOULDER, tw, th)
    rs = _landmark_xy(pose_landmarks, _RIGHT_SHOULDER, tw, th)
    lh = _landmark_xy(pose_landmarks, _LEFT_HIP, tw, th)
    rh = _landmark_xy(pose_landmarks, _RIGHT_HIP, tw, th)
    if ls is None or rs is None or lh is None or rh is None:
        return cv2.resize(character_bgra, (tw, th), interpolation=cv2.INTER_LANCZOS4)

    hip = (lh + rh) / 2.0
    dst_pts = np.float32([ls, rs, hip])

    matrix = cv2.getAffineTransform(src_pts, dst_pts)
    if character_bgra.ndim == 3 and character_bgra.shape[2] == 4:
        return cv2.warpAffine(
            character_bgra,
            matrix,
            (tw, th),
            flags=cv2.INTER_LANCZOS4,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0, 0),
        )
    return cv2.warpAffine(character_bgra, matrix, (tw, th), flags=cv2.INTER_LANCZOS4, borderValue=(0, 0, 0, 0))


def pose_delta_warp_image(
    image: np.ndarray,
    ref_pose: list[dict[str, float]],
    cur_pose: list[dict[str, float]],
    bbox: list[float],
) -> np.ndarray:
    """Warp a rendered character from ref_pose toward cur_pose using skeleton deltas."""
    x1, y1, x2, y2 = [int(v) for v in bbox]
    tw = max(1, x2 - x1)
    th = max(1, y2 - y1)

    if (tw, th) != (image.shape[1], image.shape[0]):
        image = cv2.resize(image, (tw, th), interpolation=cv2.INTER_LANCZOS4)

    ref_pts, ref_idx = _collect_warp_points(ref_pose, tw, th)
    cur_pts, cur_idx = _collect_warp_points(cur_pose, tw, th)
    if ref_pts.shape[0] < 3 or cur_pts.shape[0] < 3:
        return image

    common = sorted(set(ref_idx) & set(cur_idx), key=_WARP_INDICES.index)
    if len(common) < 3:
        return image

    ref_map = {idx: pt for idx, pt in zip(ref_idx, ref_pts, strict=True)}
    cur_map = {idx: pt for idx, pt in zip(cur_idx, cur_pts, strict=True)}
    src = np.float32([ref_map[i] for i in common])
    dst = np.float32([cur_map[i] for i in common])
    return _apply_piecewise_affine(image, src, dst, (tw, th))


def apply_head_pose_tilt(
    image_bgr: np.ndarray,
    head_pose: dict[str, float],
) -> np.ndarray:
    """Light head tilt from face yaw/pitch/roll."""
    yaw = float(head_pose.get("yaw", 0.0))
    pitch = float(head_pose.get("pitch", 0.0))
    roll = float(head_pose.get("roll", 0.0))
    if max(abs(yaw), abs(pitch), abs(roll)) < 2.0:
        return image_bgr

    h, w = image_bgr.shape[:2]
    cx, cy = w * 0.5, h * 0.32
    matrix = cv2.getRotationMatrix2D((cx, cy), roll + yaw * 0.25, 1.0)
    matrix[1, 2] += pitch * 0.15
    return cv2.warpAffine(
        image_bgr,
        matrix,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101,
    )
