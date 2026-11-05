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


def inside_poly(points, poly):
    return [p for p in points if cv2.pointPolygonTest(poly, p, False) >= 0]
