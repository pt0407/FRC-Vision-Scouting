"""Automatic field calibration via homography search.

Idea: the correct pixel->field homography maps detected robot blobs
inside the field rectangle AND gives physically plausible speeds
(FRC robots move ~0.3-7 m/s). Wrong quads either throw blobs outside
the field or produce absurd velocities. We precompute alliance-blob
detections once, then optimize the 4 corner positions against that
objective — no tracking needed inside the loop, so it's fast.
"""
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import differential_evolution

from . import calibrate, detect

FIELD_W = calibrate.FIELD_HALF_X * 2   # 16.541 m
FIELD_H = calibrate.FIELD_HALF_Z * 2   #  8.069 m


def precompute_detections(frame_paths: list[Path], step: int = 5):
    """Per sampled frame: (t_idx, [(x, y, alliance), ...]) in pixels."""
    frames = []
    for i in range(0, len(frame_paths), step):
        img = cv2.imread(str(frame_paths[i]))
        if img is None:
            continue
        red, blue, _ = detect.alliance_masks(img)
        dets = []
        for alliance, mask in (("r", red), ("b", blue)):
            for b in detect.blobs_from_mask(mask, min_area=80,
                                             max_area=15000):
                dets.append((b["centroid"][0], b["centroid"][1],
                             alliance))
        if dets:
            frames.append(dets)
    return frames


def _score(params, frames, fh, fw):
    corners = params.reshape(4, 2)
    # corners order: BL, BR, TR, TL (pixel) -> field rect
    dst = np.array([[-calibrate.FIELD_HALF_X, -calibrate.FIELD_HALF_Z],
                    [ calibrate.FIELD_HALF_X, -calibrate.FIELD_HALF_Z],
                    [ calibrate.FIELD_HALF_X,  calibrate.FIELD_HALF_Z],
                    [-calibrate.FIELD_HALF_X,  calibrate.FIELD_HALF_Z]],
                   dtype=np.float32)
    try:
        H = cv2.getPerspectiveTransform(
            corners.astype(np.float32), dst)
    except cv2.error:
        return -1e9
    Hinv = np.linalg.inv(H)

    total_in = 0
    total = 0
    good_speeds = 0
    matched = 0
    prev = None
    dt = 0.5  # seconds between sampled frames (step=5 @10fps)
    for dets in frames:
        pts = np.array([[d[0], d[1], 1.0] for d in dets],
                       dtype=np.float32)
        f = (H @ pts.T).T
        f = f[:, :2] / np.maximum(f[:, 2:3], 1e-6)
        inside = (np.abs(f[:, 0]) <= calibrate.FIELD_HALF_X + 0.5) & \
                 (np.abs(f[:, 1]) <= calibrate.FIELD_HALF_Z + 0.5)
        total_in += inside.sum()
        total += len(dets)
        # greedy nearest-neighbour matching across frames for speed
        if prev is not None:
            pf, pa = prev
            for i, d in enumerate(dets):
                if not inside[i]:
                    continue
                best, bd = None, 1e9
                for j, q in enumerate(pf):
                    if pa[j] != d[2]:
                        continue
                    dd = (f[i, 0] - q[0]) ** 2 + (f[i, 1] - q[1]) ** 2
                    if dd < bd:
                        bd, best = dd, j
                if best is not None and bd < 4.0:   # <2 m jump
                    sp = np.sqrt(bd) / dt
                    matched += 1
                    if 0.2 <= sp <= 8.0:
                        good_speeds += 1
        prev = (f, [d[2] for d in dets])

    if total == 0 or matched < 10:
        return -1e9
    inside_frac = total_in / total
    speed_frac = good_speeds / matched
    # reward quads that keep most blobs in-field with sane speeds
    return inside_frac * 2.0 + speed_frac - 0.5 * abs(inside_frac - 0.8)


def search(frame_paths: list[Path], maxiter: int = 60,
           seed: int = 1) -> tuple[np.ndarray, float]:
    frames = precompute_detections(frame_paths)
    if len(frames) < 5:
        raise RuntimeError("too few detections to auto-calibrate")
    h, w = cv2.imread(str(frame_paths[0])).shape[:2]

    # bounds: plausible field quads in the lower 4/5 of frame
    bounds = [(0.0, w * 0.55),      # BL x
              (h * 0.55, h),        # BL y
              (w * 0.45, w),        # BR x
              (h * 0.55, h),        # BR y
              (w * 0.45, w),        # TR x
              (h * 0.15, h * 0.75), # TR y
              (0.0, w * 0.55),      # TL x
              (h * 0.15, h * 0.75)] # TL y

    def obj(p):
        return -_score(p, frames, h, w)

    res = differential_evolution(
        obj, bounds, maxiter=maxiter, popsize=12, seed=seed,
        tol=1e-4, polish=True, workers=1)
    return res.x.reshape(4, 2), -res.fun


def run(video: Path, work: Path, calib_out: Path,
        max_seconds: float | None = None):
    from . import frames as frames_mod
    fdir = work / "frames_autocal"
    paths = frames_mod.extract_frames(video, fdir, fps=10.0,
                                      max_seconds=max_seconds or 90.0)
    corners, score = search(paths)
    first = cv2.imread(str(paths[len(paths) // 2]))
    calibrate.save_calibration(corners.tolist(), calib_out,
                               first.shape[1], first.shape[0])
    print(f"[autocal] score={score:.3f} corners={corners.tolist()}")
    print(f"[autocal] wrote {calib_out}")
    return score
