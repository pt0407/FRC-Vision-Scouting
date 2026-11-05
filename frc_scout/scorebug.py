"""Scorebug parsing: extract the 6 team numbers + match clock from
the FIRST broadcast overlay at the top of the frame.

Layout (2026 FIRST Championship broadcast): a band near the top shows
[red alliance: 3 team numbers + score] ... [blue alliance: 3 team
numbers + score] plus the match clock. We OCR the band with tesseract
TSV, cluster digit-words into left/right groups, and classify each
group's alliance by the hue of the pixels behind the numbers.
"""
import subprocess

import cv2
import numpy as np


def _ocr_tsv(img_bgr):
    ok, png = cv2.imencode(".png", img_bgr)
    if not ok:
        return []
    out = subprocess.run(
        ["tesseract", "stdin", "stdout", "--psm", "11", "tsv"],
        input=png.tobytes(), capture_output=True, timeout=30)
    words = []
    for ln in out.stdout.decode("utf-8", "replace").splitlines()[1:]:
        p = ln.split("\t")
        if len(p) < 12 or not p[11].strip():
            continue
        txt = p[11].strip()
        if txt and any(c.isdigit() for c in txt):
            words.append({
                "text": txt,
                "x": int(p[6]), "y": int(p[7]),
                "w": int(p[8]), "h": int(p[9]),
                "conf": float(p[10] or 0),
            })
    # scale back if we upscaled
    return words


def _digits_only(word):
    return "".join(c for c in word if c.isdigit())


def _alliance_of(img_bgr, word):
    """Sample hue in a box around the word; red-ish vs blue-ish."""
    h, w = img_bgr.shape[:2]
    x0 = max(0, word["x"] - 10)
    y0 = max(0, word["y"] - 10)
    x1 = min(w, word["x"] + word["w"] + 10)
    y1 = min(h, word["y"] + word["h"] + 10)
    patch = img_bgr[y0:y1, x0:x1]
    if patch.size == 0:
        return None
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    m = (sat > 80) & (val > 60)
    if m.sum() < 20:
        return None
    hue = hsv[:, :, 0][m].mean()
    if hue < 15 or hue > 165:
        return "red"
    if 85 < hue < 140:
        return "blue"
    return None


def parse_scorebug(img_bgr):
    """Return {"red": [team,...], "blue": [team,...], "clock": str|None,
    "raw": [...]} or None."""
    h, w = img_bgr.shape[:2]
    # scorebug band: top ~4%-15% of frame
    band = img_bgr[int(h * 0.03):int(h * 0.16), :]
    scale = 3
    big = cv2.resize(band, None, fx=scale, fy=scale,
                     interpolation=cv2.INTER_CUBIC)
    words = _ocr_tsv(big)
    for wd in words:
        wd["x"] //= scale; wd["y"] //= scale
        wd["w"] //= scale; wd["h"] //= scale
        wd["y"] += int(h * 0.03)

    # team numbers: 3-5 digit words in the main scorebug row
    nums = []
    for wd in words:
        d = _digits_only(wd["text"])
        if 3 <= len(d) <= 5 and wd["conf"] > 30:
            nums.append((wd, d))
    if len(nums) < 6:
        return None

    # cluster by x into two alliance groups (left half / right half)
    nums.sort(key=lambda nd: nd[0]["x"])
    mid = w / 2
    left = [nd for nd in nums if nd[0]["x"] < mid * 1.2]
    right = [nd for nd in nums if nd[0]["x"] >= mid * 0.8]
    # fallback: split sorted-by-x into two halves
    if not left or not right:
        half = len(nums) // 2
        left, right = nums[:half + 1], nums[half + 1:]

    def pick3(group):
        # prefer words closest to the modal y (the team-number row)
        ys = [nd[0]["y"] for nd in group]
        ymode = max(set(ys), key=ys.count)
        row = [nd for nd in group if abs(nd[0]["y"] - ymode) < 25]
        row.sort(key=lambda nd: nd[0]["x"])
        return [nd[1] for nd in row[:3]]

    red_teams, blue_teams = pick3(left), pick3(right)

    # clock: look for m:ss pattern in words
    clock = None
    for wd in words:
        if ":" in wd["text"]:
            clock = wd["text"]

    # alliance color by hue behind first team number of each group
    def color_of(group_nums):
        for nd in group_nums:
            wd = nd[0]
            c = _alliance_of(img_bgr, wd)
            if c:
                return c
        return None

    # map groups to alliances by sampled color; default left=red
    lc, rc = color_of(left), color_of(right)
    if lc == "blue" and rc != "blue":
        blue_teams, red_teams = red_teams, blue_teams
    elif lc is None and rc == "red":
        blue_teams, red_teams = red_teams, blue_teams

    return {"red": red_teams, "blue": blue_teams,
            "clock": clock,
            "groups": {"left": [n[1] for n in left],
                       "right": [n[1] for n in right]}}
