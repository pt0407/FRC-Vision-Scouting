"""FIRST event data scraping (frc-events.firstinspires.org).

Server-rendered HTML — no API key needed. Provides per-match,
per-team scouting data: auto climb, endgame tower level, alliance
fuel counts per shift, fouls, final score. Far more reliable than
video inference; the video pipeline adds paths/speeds on top.
"""
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://frc-events.firstinspires.org"
UA = {"User-Agent": "Mozilla/5.0 (frc-scout)"}


def _get(path: str) -> BeautifulSoup:
    r = requests.get(BASE + path, headers=UA, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def list_quals(season: int, event: str) -> list[dict]:
    """All qualification matches for an event (e.g. 2026, 'HOPPER')."""
    soup = _get(f"/{season}/{event}/qualifications")
    out = []
    for tr in soup.select("table tr"):
        tds = tr.find_all("td")
        if len(tds) < 9:
            continue
        txt = [td.get_text(" ", strip=True) for td in tds]
        # Qualification N | time | R1 R2 R3 | B1 B2 B3 | red blue
        m = re.match(r"Qualification\s+(\d+)", txt[0])
        if not m:
            continue
        red = [txt[2], txt[3], txt[4]]
        blue = [txt[5], txt[6], txt[7]]
        scores = txt[8:10]
        out.append({
            "match": int(m.group(1)),
            "time": txt[1],
            "red": red, "blue": blue,
            "red_score": scores[0] if scores else None,
            "blue_score": scores[1] if len(scores) > 1 else None,
        })
    return out


def _score_table(soup) -> dict:
    """Parse the 'Match Score Item' table into structured rows."""
    table = None
    for t in soup.find_all("table"):
        if t.find("th", string=re.compile("Match Score Item")):
            table = t
            break
    if table is None:
        return {}
    rows = {}
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) < 3:
            continue
        label = cells[0].get_text(" ", strip=True)
        blue = cells[1]
        red = cells[2]

        def cell_text(td):
            return td.get_text(" ", strip=True)

        def team_cells(td):
            # per-team cells carry title="Team N <what>" tooltips
            res = []
            for d in td.find_all("div"):
                title = d.get("title", "")
                m = re.match(r"Team (\d+)", title)
                if m:
                    html = str(d)
                    res.append({
                        "team": m.group(1),
                        "value": ("yes" if "fa-check" in html
                                  else "no" if "fa-times" in html
                                  else d.get_text(" ", strip=True)),
                        "title": title})
            return res

        rows[label] = {
            "blue": cell_text(blue), "red": cell_text(red),
            "blue_teams": team_cells(blue),
            "red_teams": team_cells(red),
        }
    return rows


def match_detail(season: int, event: str, match: int,
                 delay: float = 0.3) -> dict:
    """Full score breakdown for one qualification match."""
    soup = _get(f"/{season}/{event}/qualifications/{match}")
    rows = _score_table(soup)
    teams_row = rows.get("Teams", {})

    # Teams row: plain number divs, no tooltips — re-parse directly
    teams = {}
    for tr in soup.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) >= 3 and cells[0].get_text(strip=True) == "Teams":
            for side, td in (("blue", cells[1]), ("red", cells[2])):
                # leaf cells only: col-sm-4 divs holding a bare number
                teams[side] = [d.get_text(strip=True)
                               for d in td.select("div.col-sm-4")
                               if d.get_text(strip=True).isdigit()]
            break
    detail = {
        "match": match,
        "red": teams.get("red", []), "blue": teams.get("blue", []),
        "rows": {},
    }
    # per-team climb/endgame + alliance aggregates
    for label, row in rows.items():
        if label == "Teams":
            continue
        entry = {"blue": row["blue"], "red": row["red"]}
        bt = {c["team"]: c["value"] for c in row.get("blue_teams", [])}
        rt = {c["team"]: c["value"] for c in row.get("red_teams", [])}
        if bt or rt:
            entry["blue_by_team"] = bt
            entry["red_by_team"] = rt
        detail["rows"][label] = entry
    time.sleep(delay)
    return detail


def event_scouting(season: int, event: str,
                   max_matches: int | None = None) -> dict:
    """Aggregate per-team stats across all quals of an event."""
    quals = list_quals(season, event)
    if max_matches:
        quals = quals[:max_matches]
    teams = {}
    for q in quals:
        d = match_detail(season, event, q["match"])
        for side in ("red", "blue"):
            for tm in d[side]:
                t = teams.setdefault(tm, {
                    "team": tm, "matches": 0, "auto_climb": 0,
                    "endgame": {}, "alliances": set(),
                })
                t["matches"] += 1
                t["alliances"].add(side)
                rows = d["rows"]
                ac = rows.get("Auto Tower", {}).get(
                    f"{side}_by_team", {}).get(tm)
                if ac == "yes":
                    t["auto_climb"] += 1
                eg = rows.get("Endgame Tower", {}).get(
                    f"{side}_by_team", {}).get(tm)
                if eg:
                    t["endgame"][eg] = t["endgame"].get(eg, 0) + 1
    for t in teams.values():
        t["alliances"] = sorted(t["alliances"])
    return {"season": season, "event": event, "quals": quals,
            "teams": teams}
