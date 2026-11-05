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

from . import calibrate, download, eventdata, pipeline

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
              fps=6.0, width=None, do_ocr=False, max_seconds=None):
    """Scout one match end-to-end. Returns out dir."""
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
    pipeline.run(video, work / "matches" / f"{match:03d}",
                 calib_path, fps=fps, do_ocr=do_ocr,
                 max_seconds=max_seconds, event_detail=detail)
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
