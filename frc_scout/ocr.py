"""Team-number OCR via tesseract on bumper crops.

FRC bumpers carry the team number on a light plate. We crop a window
around each detection (biased toward the robot's lower half where
bumpers sit), upscale, threshold, and vote across frames.
"""
import re
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np

VALID_TEAMS = set(range(1, 10000))


def _ocr_digits(img_bgr) -> list[str]:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    _, bw = cv2.threshold(gray, 0, 255,
                          cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        cv2.imwrite(f.name, bw)
        path = f.name
    try:
        out = subprocess.run(
            ["tesseract", path, "stdout", "--psm", "7", "-c",
             "tessedit_char_whitelist=0123456789"],
            capture_output=True, text=True, timeout=10)
        text = out.stdout.strip()
    except Exception:
        return []
    finally:
        Path(path).unlink(missing_ok=True)
    cands = []
    for m in re.findall(r"\d{3,5}", text):
        n = int(m)
        if n in VALID_TEAMS:
            cands.append(str(n))
    return cands


def read_team_number(frame_bgr, bbox, centroid):
    """Try several crop offsets around the blob; return digit strings."""
    x, y, w, h = bbox
    cx, cy = centroid
    crops = []
    # bumper plate is usually near the bottom of the robot blob
    for dy_frac in (0.55, 0.4, 0.7):
        cy0 = int(y + h * dy_frac)
        x0 = int(cx - w * 0.9)
        ww = int(w * 1.8)
        hh = max(int(h * 0.8), 16)
        x0 = max(0, x0)
        if x0 + ww > frame_bgr.shape[1]:
            ww = frame_bgr.shape[1] - x0
        crop = frame_bgr[max(0, cy0 - hh // 2):cy0 + hh // 2, x0:x0 + ww]
        if crop.size:
            crops.append(crop)
    votes = []
    for c in crops:
        votes.extend(_ocr_digits(c))
    return votes
