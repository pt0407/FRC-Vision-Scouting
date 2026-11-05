"""Team-number OCR via tesseract on bumper crops.

FRC bumpers carry the team number on a light plate. We crop a window
around each detection (biased toward the robot's lower half where
bumpers sit), upscale, threshold, and vote across frames.
"""
import re
import subprocess

import cv2
import numpy as np

VALID_TEAMS = set(range(1, 10000))


def _ocr_digits(img_bgr) -> list[str]:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    _, bw = cv2.threshold(gray, 0, 255,
                          cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ok, png = cv2.imencode(".png", bw)
    if not ok:
        return []
    try:
        out = subprocess.run(
            ["tesseract", "stdin", "stdout", "--psm", "7", "-c",
             "tessedit_char_whitelist=0123456789"],
            input=png.tobytes(), capture_output=True, timeout=10)
        text = out.stdout.decode("utf-8", "replace").strip()
    except Exception:
        return []
    cands = []
    for m in re.findall(r"\d{3,5}", text):
        n = int(m)
        if n in VALID_TEAMS:
            cands.append(str(n))
    return cands


def read_team_number(frame_bgr, bbox, centroid):
    """Crop window around the blob's lower half (bumper plate) and OCR.
    Returns candidate digit strings."""
    x, y, w, h = bbox
    cx, _ = centroid
    cy0 = int(y + h * 0.55)
    x0 = max(0, int(cx - w * 0.9))
    ww = min(int(w * 1.8), frame_bgr.shape[1] - x0)
    hh = max(int(h * 0.8), 16)
    crop = frame_bgr[max(0, cy0 - hh // 2):cy0 + hh // 2, x0:x0 + ww]
    if not crop.size:
        return []
    return _ocr_digits(crop)
