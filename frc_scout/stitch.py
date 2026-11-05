"""Tracklet stitching: link fragmented detections of the same robot.

The per-frame tracker drops robots during occlusion/clustering
changes, producing many short fragments. We greedily link fragments
of the same alliance when the end of one is near the start of the
next in space and time.
"""
import numpy as np

MAX_GAP_S = 4.0        # max time gap between fragments
MAX_DIST_M = 2.5       # max jump between fragment end and next start


def stitch(tracks_field: dict) -> dict:
    """tracks_field: {tid: {t, xy, alliance, ...}} -> merged dict."""
    # candidate fragments: enough samples to be meaningful
    frags = {tid: tk for tid, tk in tracks_field.items()
             if len(tk["t"]) >= 5}
    # sort each alliance's fragments by start time
    by_alliance = {}
    for tid, tk in frags.items():
        by_alliance.setdefault(tk.get("alliance") or "?", []).append(tid)

    parent = {tid: tid for tid in frags}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    for tids in by_alliance.values():
        tids.sort(key=lambda tid: frags[tid]["t"][0])
        # link each fragment to the best predecessor
        for i, tid in enumerate(tids):
            a = frags[tid]
            a_start = np.array(a["xy"][0])
            a_t0 = a["t"][0]
            best, bd = None, MAX_DIST_M
            for pj in tids[:i]:
                b = frags[pj]
                # only consider fragments that could precede (end < start)
                if b["t"][-1] > a_t0 + 0.5:
                    continue
                gap = a_t0 - b["t"][-1]
                if gap > MAX_GAP_S:
                    continue
                d = np.linalg.norm(np.array(b["xy"][-1]) - a_start)
                # allow bigger jumps for longer gaps
                if d < bd + 0.5 * gap and d < MAX_DIST_M + gap:
                    bd, best = d, pj
            if best is not None:
                union(tid, best)

    groups = {}
    for tid in frags:
        groups.setdefault(find(tid), []).append(tid)

    merged = {}
    for root, tids in groups.items():
        # order fragments by time, concatenate samples (dedupe overlap)
        tids.sort(key=lambda tid: frags[tid]["t"][0])
        t_all, xy_all = [], []
        alliance = frags[tids[0]].get("alliance")
        team_votes = {}
        team = None
        px_path = 0.0
        px_steps = []
        sizes = []
        for tid in tids:
            tk = frags[tid]
            for tt, xx in zip(tk["t"], tk["xy"]):
                if not t_all or tt > t_all[-1]:
                    t_all.append(tt)
                    xy_all.append(xx)
            for k, v in (tk.get("team_votes") or {}).items():
                team_votes[k] = team_votes.get(k, 0) + v
            if tk.get("team") and team is None:
                team = tk["team"]
            px_path += tk.get("px_path", 0.0)
            if tk.get("_px_step"):
                px_steps.append(tk["_px_step"])
            if tk.get("_size_m"):
                sizes.append(tk["_size_m"])
        if len(t_all) < 10:
            continue
        merged[f"m{root}"] = {
            "t": t_all, "xy": xy_all, "alliance": alliance,
            "team": team, "team_votes": team_votes,
            "hits": len(t_all), "px_path": px_path,
            "fragments": len(tids),
            "_size_m": float(np.median(sizes)) if sizes else None,
            "_px_step": max(px_steps) if px_steps else 0.0,
        }
    return merged
