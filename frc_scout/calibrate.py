"""Field calibration: pixel <-> field metre homography.

A calibration JSON maps the four field corners (in pixels, order:
BL, BR, TR, TL of the field rectangle seen by the camera) to field
coordinates (+/-half_x, +/-half_z).

Auto mode tries to find the field quad via Canny + Hough line
intersection; manual mode takes 4 clicked points recorded by
`frc-scout calibrate`.
"""
import json
from pathlib import Path

import cv2
import numpy as np

# REBUILT 2026 field, metres. Matches frc-sim-m0 fields/rebuilt.toml.
FIELD_HALF_X = 8.2705
FIELD_HALF_Z = 4.0345

FIELD_CORNERS_M = np.float32([
    [-FIELD_HALF_X, -FIELD_HALF_Z],  # BL
    [ FIELD_HALF_X, -FIELD_HALF_Z],  # BR
    [ FIELD_HALF_X,  FIELD_HALF_Z],  # TR
    [-FIELD_HALF_X,  FIELD_HALF_Z],  # TL
])

# Key zones used by event detection / scouting, field coords (x, z).
ZONES = {
    "hub_west":  {"center": [-6.8, 0.0],  "radius": 1.4},
    "hub_east":  {"center": [ 6.8, 0.0],  "radius": 1.4},
    "tower_s":   {"center": [ 0.0, -3.2], "radius": 1.1},
    "tower_n":   {"center": [ 0.0,  3.2], "radius": 1.1},
    "depot":     {"center": [ 0.0,  0.0], "radius": 2.6},
    "station_w": {"center": [-8.0, 0.0],  "radius": 1.0},
    "station_e": {"center": [ 8.0, 0.0],  "radius": 1.0},
}


def load_calibration(path: Path) -> dict:
    return json.loads(path.read_text())


def save_calibration(corners_px: list, path: Path, w: int, h: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "frame_w": w, "frame_h": h,
        "field_corners_px": corners_px,
        "field_half_extents_m": [FIELD_HALF_X, FIELD_HALF_Z],
    }, indent=2))


def homography_from_corners(corners_px) -> np.ndarray:
    src = np.array(corners_px, dtype=np.float32)
    return cv2.getPerspectiveTransform(src, FIELD_CORNERS_M)


def auto_detect_quad(img_bgr) -> list | None:
    """Find the field rectangle via dominant long lines (Hough).

    Returns 4 pixel corners [BL,BR,TR,TL] or None.
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 40, 120)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 360, threshold=120,
                            minLineLength=img_bgr.shape[1] // 5,
                            maxLineGap=15)
    if lines is None:
        return None
    lines = np.asarray(lines).reshape(-1, 4)
    segs = lines
    # keep near-horizontal / near-vertical segments
    def angle(l):
        dx, dy = l[2] - l[0], l[3] - l[1]
        return np.degrees(np.arctan2(abs(dy), abs(dx)))
    h_lines = [l for l in segs if angle(l) < 12]
    v_lines = [l for l in segs if angle(l) > 78]

    def extremal(lines, idx, fn, reverse=False):
        best, val = None, None
        for l in lines:
            c = fn(l)
            if val is None or (c < val) == reverse:
                val, best = c, l
        return best

    # For each side we want the outermost line; approximate quad by
    # intersecting the 4 boundary lines.
    # top/bottom = horizontal lines with extreme mean-y; left/right =
    # vertical lines with extreme mean-x.
    def my(l): return (l[1] + l[3]) / 2
    def mx(l): return (l[0] + l[2]) / 2
    cands = {}
    if h_lines:
        cands["top"] = min(h_lines, key=my)
        cands["bot"] = max(h_lines, key=my)
    if v_lines:
        cands["left"] = min(v_lines, key=mx)
        cands["right"] = max(v_lines, key=mx)
    if len(cands) < 4:
        return None

    def inter(l1, l2):
        x1, y1, x2, y2 = l1
        x3, y3, x4, y4 = l2
        d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(d) < 1e-6:
            return None
        px = ((x1 * y2 - y1 * x2) * (x3 - x4) -
              (x1 - x2) * (x3 * y4 - y3 * x4)) / d
        py = ((x1 * y2 - y1 * x2) * (y3 - y4) -
              (y1 - y2) * (x3 * y4 - y3 * x4)) / d
        return [float(px), float(py)]

    tl = inter(cands["top"], cands["left"])
    tr = inter(cands["top"], cands["right"])
    br = inter(cands["bot"], cands["right"])
    bl = inter(cands["bot"], cands["left"])
    pts = [p for p in (bl, br, tr, tl) if p]
    if len(pts) != 4:
        return None
    # sanity: quad should cover a large fraction of the frame
    area = abs(cv2.contourArea(np.float32(pts)))
    if area < 0.15 * img_bgr.shape[0] * img_bgr.shape[1]:
        return None
    return pts


def make_viewer(calib_path: Path, out_video: Path, work_dir: Path):
    """Extract a frame + let the user click 4 field corners.

    Writes calibrations/<name>.json. Requires opencv highgui (use
    opencv-python, not headless, for this subcommand).
    """
    cap = cv2.VideoCapture(str(out_video))
    cap.set(cv2.CAP_PROP_POS_MSEC, 60_000)
    ok, frame = cap.read()
    if not ok:
        cap.set(cv2.CAP_PROP_POS_MSEC, 5_000)
        ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError("could not read frame")
    h, w = frame.shape[:2]
    pts = []

    def on_click(ev, x, y, flags, param):
        if ev == cv2.EVENT_LBUTTONDOWN and len(pts) < 4:
            pts.append([float(x), float(y)])
            cv2.circle(disp, (x, y), 6, (0, 255, 0), -1)
            cv2.imshow("calibrate", disp)

    disp = frame.copy()
    hint = auto_detect_quad(frame)
    if hint:
        cv2.polylines(disp, [np.int32(hint)], True, (0, 255, 255), 2)
    cv2.namedWindow("calibrate")
    cv2.setMouseCallback("calibrate", on_click)
    print("Click field corners in order: bottom-left, bottom-right, "
          "top-right, top-left. Close window when done.")
    while True:
        cv2.imshow("calibrate", disp)
        if cv2.waitKey(30) & 0xFF == 27 or len(pts) == 4:
            break
    cv2.destroyAllWindows()
    if len(pts) != 4:
        raise RuntimeError("need exactly 4 corner clicks")
    save_calibration(pts, calib_path, w, h)
    print("wrote", calib_path)
