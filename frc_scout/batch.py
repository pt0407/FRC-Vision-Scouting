"""Batch playlist scouting: every qual match -> per-team profiles.

Pipeline per match:
  1. yt-dlp flat-playlist -> {match_number: video_id} map (cached)
  2. download VOD (skip if present), extract metadata title
  3. pipeline.run(...) -> out/scouting.json per match
  4. aggregate: event stats (always) + video track stats + labels.json
     (when the user has labeled tracks) -> teams/<team>.json profile

Resumable: matches with an existing scouting.json are skipped.
"""
import json
import re
import subprocess
from pathlib import Path

import requests

from . import calibrate, classify, download, eventdata, pipeline


def reclassify_all(work: Path):
    """Backfill `features` + `suggested_labels` into existing
    scouting.json files (computed from paths/*.json, no re-tracking)."""
    done = 0
    for sj in sorted(work.glob("matches/*/out/scouting.json")):
        d = json.loads(sj.read_text())
        if "suggested_labels" in d:
            continue
        fps = d.get("fps", 6.0)
        tracks, summary = {}, {}
        for pf in (sj.parent / "paths").glob("*.json"):
            p = json.loads(pf.read_text())
            key = pf.stem
            st = d["teams"].get(key, {})
            tr = {"xy": [[s[1], s[2]] for s in p["samples"]],
                  "t": [s[0] for s in p["samples"]],
                  "alliance": p["alliance"], "team": p["team"]}
            ft = classify.classify_track(tr, st, fps)
            st["features"] = ft
            tracks[key] = tr
            summary[key] = st
        sug = classify.autobind(tracks, summary, d.get("event"))
        d["suggested_labels"] = sug
        if sug:
            (sj.parent / "labels_suggested.json").write_text(json.dumps(
                {"labels": {k: v["team"] for k, v in sug.items()},
                 "detail": sug}, indent=2))
        sj.write_text(json.dumps(d, indent=2))
        done += 1
    return done

UA = {"User-Agent": "Mozilla/5.0 (frc-scout)"}


def playlist_map(playlist_url: str, cache: Path) -> dict[int, str]:
    """YouTube playlist -> {match_number: video_id} for Qualification N."""
    if cache.exists():
        return {int(k): v for k, v in json.loads(cache.read_text()).items()}
    out = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--print",
         "%(id)s\t%(title)s", playlist_url],
        capture_output=True, text=True, check=True).stdout
    m = {}
    for line in out.splitlines():
        vid, _, title = line.partition("\t")
        mm = re.search(r"Qualification\s+(\d+)", title or "", re.I)
        if mm:
            m[int(mm.group(1))] = vid.strip()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(m, indent=1))
    return m


def video_url(vid: str) -> str:
    return f"https://www.youtube.com/watch?v={vid}"


def run_match(season, event, match, playlist_url, work, calib_path,
              fps=6.0, width=None, do_ocr=False, max_seconds=None,
              keep_frames=False, keep_video=False):
    """Scout one match end-to-end. Returns out dir.

    Deletes intermediate frames (~260MB/match) and the VOD (~55MB)
    after a successful run — everything needed downstream is in
    out/. Pass keep_frames/keep_video to retain them.
    """
    vmap = playlist_map(playlist_url, work / "playlist_map.json")
    vid = vmap.get(match)
    if not vid:
        raise RuntimeError(f"no playlist video for match {match}")
    url = video_url(vid)
    out_dir = work / "matches" / f"{match:03d}" / "out"
    if (out_dir / "scouting.json").exists():
        return out_dir, True
    video = download.download(url, work / "videos")
    detail = eventdata.match_detail(season, event, match)
    match_dir = work / "matches" / f"{match:03d}"
    pipeline.run(video, match_dir,
                 calib_path, fps=fps, do_ocr=do_ocr,
                 max_seconds=max_seconds, event_detail=detail)
    if not keep_frames:
        import shutil
        shutil.rmtree(match_dir / "frames", ignore_errors=True)
    if not keep_video:
        video.unlink(missing_ok=True)
    return out_dir, False


def aggregate(event_dir: Path, season, event):
    """Merge per-match scouting.json + event data + labels into
    teams/<team>.json profiles."""
    teams = {}
    # 1. official event stats per team
    try:
        ev = json.loads(
            (event_dir / f"{season}_{event}.json").read_text())
        for tm, t in ev["teams"].items():
            teams[tm] = {"team": tm, "event": t, "matches": {}}
    except FileNotFoundError:
        ev = None

    # 2. per-match video stats (track-level; team labels when present)
    for sj in sorted(event_dir.glob("matches/*/out/scouting.json")):
        m = int(sj.parent.parent.name)
        d = json.loads(sj.read_text())
        labels = {}
        lp = sj.parent / "labels.json"
        if lp.exists():
            labels = json.loads(lp.read_text()).get("labels", {})
        for key, st in d.get("teams", {}).items():
            team = labels.get(key) or (
                st["team"] if not st["team"].startswith("track")
                else None)
            if team is None:
                continue
            prof = teams.setdefault(team, {"team": team, "matches": {}})
            prof["matches"][str(m)] = {
                "alliance": st["alliance"],
                "avg_speed": st["avg_speed_mps"],
                "max_speed": st["max_speed_mps"],
                "drive_time": st["drive_time_s"],
                "path_m": st["path_length_m"],
                "zone_time": st["zone_time_s"],
                "zone_visits": st.get("zone_visits", {}),
                "auto_path_m": st["auto"]["path_length_m"],
                "features": st.get("features", {}),
            }

    # 3. roll up per team
    for tm, prof in teams.items():
        ms = prof.get("matches", {})
        if not ms:
            continue
        speeds = [v["avg_speed"] for v in ms.values()]
        prof["summary"] = {
            "matches_scouted": len(ms),
            "avg_speed_mean": round(sum(speeds) / len(speeds), 2),
            "max_speed_best": round(max(v["max_speed"] for v in ms.values()), 2),
            "drive_time_mean": round(
                sum(v["drive_time"] for v in ms.values()) / len(ms), 1),
        }
    out = event_dir / "teams"
    out.mkdir(parents=True, exist_ok=True)
    for tm, prof in teams.items():
        (out / f"{tm}.json").write_text(json.dumps(prof, indent=2))
    (event_dir / "teams_index.json").write_text(json.dumps(
        {tm: p.get("summary", {}) for tm, p in teams.items()}, indent=2))
    return teams
