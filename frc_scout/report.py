"""Turn raw tracks into scouting stats, archetypes and strategies."""
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from .calibrate import ZONES

# FRC 2026 REBUILT rules-of-thumb
AUTO_S = 20.0          # autonomous period (game manual)
MATCH_S = 150.0
MAX_FOOTPRINT_M = 3.05  # ~120 in size limit


def _zone_of(x, z):
    for name, zn in ZONES.items():
        if (x - zn["center"][0]) ** 2 + (z - zn["center"][1]) ** 2 \
                <= zn["radius"] ** 2:
            return name
    return None


def build_tracks(traj_px, H_px_to_field, fps):
    """traj_px: {tid: [(t, px, py), ...]} -> per-track field-coord series.

    H_px_to_field is the homography mapping pixel coords to field
    metres (x, z)."""
    tracks = {}
    for tid, pts in traj_px.items():
        if len(pts) < 10:
            continue
        arr = np.array([[p[1], p[2]] for p in pts], dtype=np.float32)
        ones = np.ones((len(arr), 1), dtype=np.float32)
        homo = np.hstack([arr, ones])
        field = (H_px_to_field @ homo.T).T
        field = field[:, :2] / field[:, 2:3]
        tracks[tid] = {
            "t": [p[0] for p in pts],
            "xy": field.tolist(),          # (x, z) metres
            "alliance": None, "team": None,
            "bbox_area": [], "hits": len(pts),
        }
    return tracks


def summarize(track, fps):
    xy = np.array(track["xy"])
    t = np.array(track["t"])
    dt = np.diff(t)
    dt[dt <= 0] = 1 / fps
    dist = np.linalg.norm(np.diff(xy, axis=0), axis=1)
    speed = dist / dt
    # smooth speed lightly
    k = min(5, len(speed))
    if k > 1:
        speed = np.convolve(speed, np.ones(k) / k, mode="same")
    stats = {
        "path_length_m": float(dist.sum()),
        "avg_speed_mps": float(np.mean(speed)),
        "max_speed_mps": float(np.percentile(speed, 95)),
        "drive_time_s": float(t[-1] - t[0]),
        "samples": len(t),
    }
    # zone occupancy + visit counts (entries into each zone)
    occ = defaultdict(float)
    visits = defaultdict(int)
    prev_zone = None
    for p in xy:
        zn = _zone_of(p[0], p[1])
        if zn:
            occ[zn] += 1 / fps
            if zn != prev_zone:
                visits[zn] += 1
        prev_zone = zn
    stats["zone_time_s"] = {k: round(v, 1) for k, v in occ.items()}
    stats["zone_visits"] = dict(visits)
    # auto vs teleop
    auto_mask = t < AUTO_S
    stats["auto"] = {
        "path_length_m": float(
            np.linalg.norm(np.diff(xy[auto_mask], axis=0), axis=1).sum())
        if auto_mask.sum() > 2 else 0.0,
        "zone_time_s": {},
    }
    if auto_mask.sum() > 2:
        az = defaultdict(float)
        for p in xy[auto_mask]:
            zn = _zone_of(p[0], p[1])
            if zn:
                az[zn] += 1 / fps
        stats["auto"]["zone_time_s"] = {k: round(v, 1) for k, v in az.items()}
    return stats, xy, speed


def estimate_archetype(track, stats, speed, team):
    """Rough physical estimates from observed motion.

    Footprint from the track's pixel bbox is not stored here; caller
    passes median apparent size in metres via stats['_size_m'].
    """
    size = stats.get("_size_m", 0.8)
    half = [round(min(max(size * 0.55, 0.30), MAX_FOOTPRINT_M / 2), 3)] * 2
    # mass: FRC robots cluster 45-75 kg; scale mildly with speed class
    mass = 55.0 + 10.0 * min(stats["max_speed_mps"] / 5.0, 1.0)
    # force: estimate from 95th-pct accel * assumed mass, clamped to sane
    # drivetrain outputs (typical FRC ~800-3000 N)
    accel = stats.get("_accel95", 2.0)
    force = float(np.clip(accel * mass, 600.0, 3200.0))
    return {
        "name": f"team-{team}" if team else "unknown",
        "mass": round(mass, 1),
        "half_extents": [half[0], round(size * 0.35, 3), half[0]],
        "max_force": round(force, 0),
        "drivetrain": "swerve",
    }


def archetype_toml(a: dict) -> str:
    return (
        f'name = "{a["name"]}"\n'
        f'mass = {a["mass"]}\n'
        f'half_extents = [{a["half_extents"][0]}, {a["half_extents"][1]}, '
        f'{a["half_extents"][2]}]\n'
        f'max_force = {a["max_force"]}\n'
        f'drivetrain = "{a["drivetrain"]}"\n'
        f'\n[sensors]\npreset = "competition"\n'
    )


def strategy_toml(team, stats, alliance):
    zt = stats["zone_time_s"]
    return (
        f'team = "{team}"\nalliance = "{alliance}"\n'
        f'avg_speed_mps = {stats["avg_speed_mps"]:.2f}\n'
        f'max_speed_mps = {stats["max_speed_mps"]:.2f}\n'
        f'path_length_m = {stats["path_length_m"]:.1f}\n'
        f'zone_time_s = {zt}\n'
        f'zone_visits = {stats.get("zone_visits", {})}\n'
        f'[auto]\npath_length_m = {stats["auto"]["path_length_m"]:.1f}\n'
        f'zone_time_s = {stats["auto"]["zone_time_s"]}\n'
    )
