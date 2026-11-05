"""Sheet-style export: per-team CSV matching the 5572 scouting format.

Columns blend official event stats (scoring, climb) with video-derived
behavior features (speed, intake pref, hub role, stuck events) once
tracks are labeled.
"""
import csv
import json
from collections import Counter
from pathlib import Path

COLS = [
    "team", "matches", "avg_points", "avg_auto_fuel", "avg_teleop_fuel",
    "auto_climb_pct", "endgame_mode", "driving_0_5", "defence_0_5",
    "intake_method", "hub_bot_type", "leave_pct", "tipped",
    "stuck_per_match", "cycle_time_s", "cruise_speed_mps",
    "path_efficiency", "matches_scouted",
]


def build_sheet(batch_dir: Path, out_csv: Path):
    """batch_dir = data/batch/<season>_<event>. Aggregates
    teams/*.json + per-match features into a CSV row per team."""
    rows = []
    tdir = batch_dir / "teams"
    for f in sorted(tdir.glob("*.json"), key=lambda p: int(p.stem)):
        prof = json.loads(f.read_text())
        ev = prof.get("event") or {}
        ms = prof.get("matches") or {}
        r = {"team": prof["team"], "matches": ev.get("matches", 0),
             "auto_climb_pct": round(
                 ev.get("auto_climb", 0) / max(ev.get("matches", 1), 1)
                 * 100),
             "endgame_mode": (Counter(ev.get("endgame", {}))
                              .most_common(1)[0][0]
                              if ev.get("endgame") else ""),
             "matches_scouted": len(ms)}
        # video aggregates across scouted matches
        if ms:
            feats = [m.get("features", {}) for m in ms.values()]
            cruise = [f.get("cruise_speed_mps", 0) for f in feats]
            stucks = [f.get("stuck_count", 0) for f in feats]
            leaves = [f.get("auto_leave") for f in feats]
            leaves = [v for v in leaves if v is not None]
            effs = [f.get("path_efficiency", 0) for f in feats]
            cts = [f["cycle_time_s"] for f in feats
                   if f.get("cycle_time_s")]
            intake = Counter(f.get("intake_pref") for f in feats
                             if f.get("intake_pref"))
            roles = Counter(f.get("hub_role") for f in feats
                            if f.get("hub_role"))
            r.update({
                "driving_0_5": round(min(max(cruise) / 4.5, 1.0) * 5, 1)
                if cruise else "",
                "cruise_speed_mps": round(max(cruise), 2)
                if cruise else "",
                "stuck_per_match": round(sum(stucks) / len(stucks), 1),
                "tipped": "maybe" if sum(stucks) > 2 else "no",
                "leave_pct": round(100 * sum(leaves) / len(leaves))
                if leaves else "",
                "intake_method": intake.most_common(1)[0][0]
                if intake else "",
                "hub_bot_type": roles.most_common(1)[0][0]
                if roles else "",
                "cycle_time_s": round(sum(cts) / len(cts), 1)
                if cts else "",
                "path_efficiency": round(sum(effs) / len(effs), 2)
                if effs else "",
            })
        else:
            r.update({"driving_0_5": "", "cruise_speed_mps": "",
                      "stuck_per_match": "", "tipped": "",
                      "leave_pct": "", "intake_method": "",
                      "hub_bot_type": "", "cycle_time_s": "",
                      "path_efficiency": ""})
        # event-level averages (alliance stats; per-team where known)
        r.setdefault("avg_points", "")
        r.setdefault("avg_auto_fuel", "")
        r.setdefault("avg_teleop_fuel", "")
        r.setdefault("defence_0_5", "")
        rows.append(r)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    return rows
