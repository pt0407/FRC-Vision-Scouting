"""Frame extraction + scene-cut splitting."""
import subprocess
from pathlib import Path

import cv2
import numpy as np


def extract_frames(video: Path, out_dir: Path, fps: float = 10.0,
                   width: int = 1280, max_seconds: float | None = None):
    """Decode video to JPEG frames at `fps`. Returns list of paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "f%06d.jpg")
    vf = f"fps={fps},scale={width}:-2"
    cmd = ["ffmpeg", "-v", "error", "-i", str(video)]
    if max_seconds:
        cmd += ["-t", str(max_seconds)]
    cmd += ["-vf", vf, "-q:v", "3", pattern]
    subprocess.run(cmd, check=True)
    return sorted(out_dir.glob("f*.jpg"))


def frame_times(n_frames: int, fps: float):
    return [i / fps for i in range(n_frames)]


def scene_cuts(frame_paths: list[Path], thresh: float = 0.35,
               sample_every: int = 5):
    """Return list of (start_idx, end_idx) segments split on hard cuts."""
    prev = None
    cuts = [0]
    for i in range(0, len(frame_paths), sample_every):
        img = cv2.imread(str(frame_paths[i]), cv2.IMREAD_GRAYSCALE)
        img = cv2.resize(img, (160, 90))
        if prev is not None:
            diff = np.mean(np.abs(img.astype(float) - prev.astype(float))) / 255.0
            # mean-abs diff is small even on cuts; use histogram instead
            h1 = cv2.calcHist([img], [0], None, [32], [0, 256])
            # cheap alternative: normalized correlation on downsampled
            # pixel diff catches fades poorly but cuts well enough when
            # combined with a higher threshold
            if diff > 0.18:
                cuts.append(i)
        prev = img
    cuts.append(len(frame_paths))
    return [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1)
            if cuts[i + 1] - cuts[i] > 30]
