"""Multi-object tracking for robot blobs.

Greedy nearest-neighbour tracker with constant-velocity prediction.
Tracks live in pixel space; positions are mapped to field coords by
the caller. Each track carries an alliance label (red/blue) fixed at
creation.
"""
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Track:
    tid: int
    alliance: str            # "red" | "blue"
    pos: np.ndarray          # pixel xy (filtered)
    vel: np.ndarray
    bbox: tuple
    area: float
    hits: int = 1
    missed: int = 0
    team: str | None = None
    team_votes: dict = field(default_factory=dict)
    history: list = field(default_factory=list)  # (t, x, y) pixel

    @property
    def confirmed(self):
        return self.hits >= 5


class Tracker:
    MAX_DIST_PX = 110.0      # gating distance per frame @10fps
    MAX_MISSED = 12

    def __init__(self):
        self.tracks: dict[int, Track] = {}
        self._next = 0

    def update(self, detections: dict[str, list], t: float,
               field_poly=None):
        """detections: {"red": [blob,...], "blue": [...]}
        Returns list of Track for this frame."""
        # gather all detections with alliance
        dets = []
        for alliance, blobs in detections.items():
            for b in blobs:
                cx, cy = b["centroid"]
                if field_poly is not None:
                    import cv2
                    if cv2.pointPolygonTest(field_poly, (cx, cy), False) < 0:
                        continue
                dets.append((alliance, b))

        # predict
        for tr in self.tracks.values():
            tr.pos = tr.pos + tr.vel
            tr.missed += 1

        # greedy assignment by distance
        pairs = []
        for di, (_, b) in enumerate(dets):
            c = np.array(b["centroid"], dtype=float)
            for tid, tr in self.tracks.items():
                if tr.alliance != _:
                    continue
                d = np.linalg.norm(c - tr.pos)
                if d < self.MAX_DIST_PX:
                    pairs.append((d, di, tid))
        pairs.sort()
        used_d, used_t = set(), set()
        assign = {}
        for d, di, tid in pairs:
            if di in used_d or tid in used_t:
                continue
            used_d.add(di); used_t.add(tid)
            assign[di] = tid

        for di, (_, b) in enumerate(dets):
            c = np.array(b["centroid"], dtype=float)
            if di in assign:
                tr = self.tracks[assign[di]]
                new_vel = c - tr.pos
                tr.vel = 0.6 * tr.vel + 0.4 * new_vel
                tr.pos = c
                tr.bbox = b["bbox"]; tr.area = b["area"]
                tr.hits += 1; tr.missed = 0
            else:
                tr = Track(tid=self._next, alliance=_, pos=c.copy(),
                           vel=np.zeros(2), bbox=b["bbox"],
                           area=b["area"])
                tr.history.append((t, c[0], c[1]))
                self.tracks[self._next] = tr
                self._next += 1
                used_t.add(tr.tid)

        # age out lost tracks
        dead = [tid for tid, tr in self.tracks.items()
                if tr.missed > self.MAX_MISSED]
        for tid in dead:
            del self.tracks[tid]
        return [tr for tr in self.tracks.values() if tr.missed == 0]

    def finish(self):
        return list(self.tracks.values())
