"""Behavior classification: turn track stats + geometry into the
sheet-style fields (leave?, intake method, hub role, stuck events,
cycle timing, shot spots, drive profile)."""
import numpy as np

from .report import AUTO_S

MATCH_S = 150.0
ENDGAME_S = 30.0
STATIONARY_MPS = 0.15
STUCK_S = 6.0
PICKUP_ZONES = ("depot", "station_w", "station_e")
HUBS = ("hub_west", "hub_east")
TOWERS = ("tower_s", "tower_n")


def classify_track(track: dict, stats: dict, fps: float) -> dict:
    """Add behavior features to a summarized track."""
    xy = np.array(track["xy"])
    t = np.array(track["t"])
    if len(xy) < 10:
        return {}
    dt = np.diff(t)
    dt[dt <= 0] = 1 / fps
    speed = np.linalg.norm(np.diff(xy, axis=0), axis=1) / dt
    k = min(5, len(speed))
    if k > 1:
        speed = np.convolve(speed, np.ones(k) / k, mode="same")

    f = {}
    # --- motion quality / drive profile
    acc = np.abs(np.diff(speed)) / dt[1:]
    f["accel95_mps2"] = float(np.percentile(acc, 95)) if len(acc) else 0.0
    if len(acc) > 2:
        jerk = np.abs(np.diff(acc)) / dt[2:]
        f["jerk95_mps3"] = float(np.percentile(jerk, 95))
    else:
        f["jerk95_mps3"] = 0.0
    f["cruise_speed_mps"] = float(np.percentile(speed, 90))

    # --- idle / stuck windows (disabled, pinned, dead motor)
    idle = speed < STATIONARY_MPS
    f["idle_time_s"] = float(idle.sum() / fps)
    f["idle_frac"] = round(f["idle_time_s"] /
                         max(stats["drive_time_s"], 1e-6), 3)
    stuck = _runs(idle, min_len=int(STUCK_S * fps))
    f["stuck_windows"] = [
        {"t0": round(float(t[s]), 1), "dur_s": round((e - s) / fps, 1),
         "pos": [round(float(v), 2) for v in xy[s + 1]]}
        for s, e in stuck]
    f["stuck_count"] = len(stuck)

    # --- leave? (auto: path reaches opponent-half-ish displacement)
    am = t < AUTO_S
    if am.sum() > 2:
        a = xy[am]
        f["auto_start"] = [round(float(v), 2) for v in a[0]]
        f["auto_end"] = [round(float(v), 2) for v in a[-1]]
        disp = np.linalg.norm(a[-1] - a[0])
        f["auto_leave"] = bool(disp > 3.0)
    else:
        f["auto_leave"] = None

    # --- path efficiency (displacement / distance), lower = wandering
    net = np.linalg.norm(xy[-1] - xy[0])
    f["path_efficiency"] = round(
        float(net / max(stats["path_length_m"], 1e-6)), 3)

    # --- intake preference: depot (ground piles) vs stations
    zv = stats.get("zone_visits", {})
    depot_v = zv.get("depot", 0)
    station_v = zv.get("station_w", 0) + zv.get("station_e", 0)
    if depot_v + station_v > 0:
        f["intake_pref"] = ("ground" if depot_v >= station_v
                            else "station")
        f["pickup_visits"] = depot_v + station_v
    else:
        f["intake_pref"] = None
        f["pickup_visits"] = 0

    # --- cycles: pickup-zone -> hub-zone round trips
    cyc, ctimes = _cycles(track, t, fps)
    f["cycles"] = cyc
    f["cycle_time_s"] = round(float(np.median(ctimes)), 1) \
        if ctimes else None

    # --- hub role heuristic
    zt = stats.get("zone_time_s", {})
    own_hub = _own_hub(track["alliance"])
    hub_t = zt.get(own_hub, 0.0)
    opp_hub = "hub_east" if own_hub == "hub_west" else "hub_west"
    opp_t = zt.get(opp_hub, 0.0)
    f["own_hub_time_s"] = round(hub_t, 1)
    f["opp_hub_time_s"] = round(opp_t, 1)
    if opp_t > hub_t and opp_t > 8:
        f["hub_role"] = "defender"
    elif cyc >= 2:
        f["hub_role"] = "scorer"
    elif hub_t > 10:
        f["hub_role"] = "cleanup"
    else:
        f["hub_role"] = "passing"

    # --- shot spots: positions adjacent to own hub (resting approach)
    hx, hz = _zone_center(own_hub)
    d_hub = np.linalg.norm(xy - [hx, hz], axis=1)
    near = (d_hub < 3.2) & (np.r_[True, speed] < 1.0)
    if near.sum() > 3:
        f["shot_spot_dist_m"] = round(float(np.median(d_hub[near])), 2)

    # --- tower behavior at phase boundaries
    tow = np.array([_in_tower(p) for p in xy])
    f["auto_at_tower"] = bool(tow[:int(AUTO_S * fps)].any()) \
        if len(tow) else False
    end_idx = t > (MATCH_S - ENDGAME_S)
    f["endgame_at_tower"] = bool(tow[end_idx].any()) if end_idx.any() \
        else bool(tow[int(0.7 * len(tow)):].any())
    f["endgame_tower_time_s"] = round(
        float((tow & end_idx).sum() / fps), 1) if end_idx.any() else 0.0
    if f["endgame_at_tower"]:
        idx = np.where(tow & end_idx)[0] if end_idx.any() \
            else np.where(tow)[0]
        if len(idx):
            f["climb_start_s"] = round(float(t[idx[0]]), 1)

    return f


def autobind(tracks: dict, summary: dict, event_detail: dict) -> dict:
    """Suggest track->team labels from official per-team results.

    Signals: auto tower yes/no, endgame tower level (None/no climb).
    Greedy assignment per alliance; returns {key: {"team", "conf",
    "why"}} for keys like 'red-track-m7'.
    """
    out = {}
    rows = (event_detail or {}).get("rows", {})
    for side in ("red", "blue"):
        roster = event_detail.get(side, []) if event_detail else []
        cands = {k: s for k, s in summary.items()
                 if s.get("alliance") == side}
        # score each (candidate, team) pair
        scored = []
        for tm in roster:
            auto_t = rows.get("Auto Tower", {}).get(
                f"{side}_by_team", {}).get(tm)
            endg = rows.get("Endgame Tower", {}).get(
                f"{side}_by_team", {}).get(tm)
            for key, st in cands.items():
                ft = st.get("features", {})
                score, why = 0.0, []
                if auto_t == "yes" and ft.get("auto_at_tower"):
                    score += 3; why.append("auto-climb")
                elif auto_t == "no" and ft.get("auto_at_tower"):
                    score -= 3; why.append("auto-climb-mismatch")
                if endg and endg != "None" and ft.get("endgame_at_tower"):
                    score += 4; why.append(f"endgame-{endg}")
                elif endg == "None" and ft.get("endgame_at_tower"):
                    score -= 4; why.append("endgame-mismatch")
                if score > 0:
                    scored.append((score, key, tm, why))
        # greedy assign best-first, each track & team once
        scored.sort(key=lambda x: -x[0])
        used_t, used_k = set(), set()
        for score, key, tm, why in scored:
            if tm in used_t or key in used_k:
                continue
            used_t.add(tm); used_k.add(key)
            out[key] = {"team": tm, "conf": min(score / 7.0, 1.0),
                        "why": why}
    return out


def _runs(mask, min_len):
    idx = np.where(mask)[0]
    if len(idx) == 0:
        return []
    splits = np.where(np.diff(idx) > 1)[0] + 1
    runs = []
    for grp in np.split(idx, splits):
        if len(grp) >= min_len:
            runs.append((grp[0], grp[-1]))
    return runs


def _cycles(track, t, fps):
    """Count pickup->hub trips; return (count, [duration_s])."""
    from .report import _zone_of
    zseq = [_zone_of(p[0], p[1]) for p in track["xy"]]
    count, times = 0, []
    pick_t = None
    for zn, tt in zip(zseq, t):
        if zn in PICKUP_ZONES and pick_t is None:
            pick_t = tt
        elif zn == _own_hub(track["alliance"]) and pick_t is not None:
            count += 1
            times.append(tt - pick_t)
            pick_t = None
    return count, times


def _own_hub(alliance):
    return "hub_west" if alliance == "blue" else "hub_east"


def _zone_center(name):
    from .calibrate import ZONES
    return ZONES[name]["center"]


def _in_tower(p):
    for n in TOWERS:
        c = _zone_center(n)
        if (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 <= 1.4 ** 2:
            return True
    return False
