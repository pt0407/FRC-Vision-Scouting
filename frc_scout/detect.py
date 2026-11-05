"""Robot detection: alliance-color segmentation + blob filtering.

FRC bumpers are saturated red or blue. We threshold in HSV, clean up
with morphology, and keep compact blobs inside the field polygon.
"""
import cv2
import numpy as np

# HSV ranges tuned for broadcast footage (OpenCV hue 0-179).
RED_RANGES = [((0, 90, 70), (12, 255, 255)),
              ((168, 90, 70), (179, 255, 255))]
BLUE_RANGE = ((95, 55, 55), (135, 255, 255))
YELLOW_RANGE = ((18, 90, 120), (38, 255, 255))  # fuel balls


def _mask(hsv, ranges):
    out = None
    for lo, hi in ranges:
        m = cv2.inRange(hsv, np.array(lo), np.array(hi))
        out = m if out is None else cv2.bitwise_or(out, m)
    return out


def alliance_masks(img_bgr):
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    hsv = cv2.medianBlur(hsv, 3)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    red = cv2.morphologyEx(_mask(hsv, RED_RANGES), cv2.MORPH_OPEN, k)
    blue = cv2.morphologyEx(_mask(hsv, [BLUE_RANGE]), cv2.MORPH_OPEN, k)
    return red, blue, hsv


def blobs_from_mask(mask, min_area=120, max_area=20000):
    n, _, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if min_area <= a <= max_area and 0.2 < w / max(h, 1) < 5.0:
            out.append({"bbox": (int(x), int(y), int(w), int(h)),
                        "area": int(a), "centroid": tuple(map(float, cents[i]))})
    return out


def cluster_blobs(blobs, merge_dist=50.0):
    """Merge blobs whose centroids are close — one robot often yields
    several bumper/chassis fragments. Returns merged pseudo-blobs."""
    blobs = sorted(blobs, key=lambda b: -b["area"])
    used = [False] * len(blobs)
    out = []
    for i, b in enumerate(blobs):
        if used[i]:
            continue
        group = [b]
        used[i] = True
        cx, cy = b["centroid"]
        for j in range(i + 1, len(blobs)):
            if used[j]:
                continue
            dx = blobs[j]["centroid"][0] - cx
            dy = blobs[j]["centroid"][1] - cy
            if dx * dx + dy * dy < merge_dist * merge_dist:
                group.append(blobs[j])
                used[j] = True
        if len(group) == 1:
            out.append(b)
            continue
        # weighted centroid + union bbox
        tot = sum(g["area"] for g in group)
        mx = sum(g["centroid"][0] * g["area"] for g in group) / tot
        my = sum(g["centroid"][1] * g["area"] for g in group) / tot
        x0 = min(g["bbox"][0] for g in group)
        y0 = min(g["bbox"][1] for g in group)
        x1 = max(g["bbox"][0] + g["bbox"][2] for g in group)
        y1 = max(g["bbox"][1] + g["bbox"][3] for g in group)
        out.append({"bbox": (x0, y0, x1 - x0, y1 - y0),
                    "area": int(tot), "centroid": (mx, my)})
    return out


def inside_poly(points, poly):
    return [p for p in points if cv2.pointPolygonTest(poly, p, False) >= 0]
