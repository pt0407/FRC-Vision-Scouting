"""frc-scout CLI."""
import argparse
import sys
from pathlib import Path


def main():
    p = argparse.ArgumentParser(prog="frc-scout")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="scout a match video")
    r.add_argument("video", help="mp4 file or YouTube URL")
    r.add_argument("--work", default="data/work",
                   help="working dir for frames/output")
    r.add_argument("--calibration", required=True,
                   help="calibration JSON (see `calibrate`)")
    r.add_argument("--fps", type=float, default=10.0)
    r.add_argument("--no-ocr", action="store_true")
    r.add_argument("--max-seconds", type=float, default=None)
    r.add_argument("--event", default=None,
                   help="FIRST event key (e.g. HOPPER) to merge official "
                        "match data")
    r.add_argument("--match", type=int, default=None,
                   help="qualification match number")
    r.add_argument("--labels", default=None,
                   help="labels.json from `frc-scout label`")

    c = sub.add_parser("calibrate",
                       help="click 4 field corners on a frame")
    c.add_argument("video")
    c.add_argument("--out", default="calibrations/default.json")
    c.add_argument("--t", type=float, default=60.0,
                   help="seek seconds into video")

    f = sub.add_parser("feed",
                       help="copy scouted archetypes into frc-multi-sim")
    f.add_argument("--sim", default="../frc-sim-m0",
                   help="path to frc-multi-sim checkout")
    f.add_argument("--scouting", required=True,
                   help="scouting.json from a `run`")
    f.add_argument("--top", type=int, default=6,
                   help="keep top-N tracks by drive time")

    bt = sub.add_parser("batch",
                        help="scout every qual match in an event")
    bt.add_argument("event", help="event key, e.g. HOPPER")
    bt.add_argument("playlist", help="YouTube playlist URL of match VODs")
    bt.add_argument("--season", type=int, default=2026)
    bt.add_argument("--calibration", required=True)
    bt.add_argument("--limit", type=int, default=None,
                    help="max matches to process")
    bt.add_argument("--skip", type=int, default=0,
                    help="skip first N matches")
    bt.add_argument("--fps", type=float, default=6.0)
    bt.add_argument("--max-seconds", type=float, default=None)
    bt.add_argument("--aggregate-only", action="store_true",
                    help="skip video, just rebuild team profiles")
    bt.add_argument("--reclassify", action="store_true",
                    help="backfill behavior features into processed "
                         "matches, then exit")
    bt.add_argument("--keep-frames", action="store_true")
    bt.add_argument("--keep-video", action="store_true")

    ev = sub.add_parser("event",
                        help="scrape FIRST event match data")
    ev.add_argument("event", help="event key, e.g. HOPPER")
    ev.add_argument("--season", type=int, default=2026)
    ev.add_argument("--matches", type=int, default=None,
                    help="limit to first N quals (default: all)")
    ev.add_argument("--out", default=None)

    lb = sub.add_parser("label",
                        help="generate HTML track-labeling tool")
    lb.add_argument("out_dir", help="scouting output dir")

    ac = sub.add_parser("autocal",
                        help="auto-search field calibration")
    ac.add_argument("video")
    ac.add_argument("--out", required=True)
    ac.add_argument("--max-seconds", type=float, default=90.0)

    pl = sub.add_parser("playlist",
                        help="list videos in a YouTube playlist")
    pl.add_argument("url")

    rg = sub.add_parser("registry",
                        help="mechanism registry (CAD-tagged)")
    rg.add_argument("action", choices=["set", "list", "import"])
    rg.add_argument("value", nargs="?",
                    help="team number (set) or export JSON file (import)")
    rg.add_argument("--mech", action="append", default=[],
                    help="type:param=val,... (repeatable)")
    rg.add_argument("--cad-url", default=None)
    rg.add_argument("--robot-name", default=None)
    rg.add_argument("--notes", default=None)

    cd = sub.add_parser("cads",
                        help="generate CAD/mechanism review page for "
                             "an event")
    cd.add_argument("event", help="event key, e.g. HOPPER")
    cd.add_argument("--season", type=int, default=2026)

    sh = sub.add_parser("sheet",
                        help="export 5572-style per-team scouting CSV")
    sh.add_argument("event", help="event key, e.g. HOPPER")
    sh.add_argument("--season", type=int, default=2026)

    a = p.parse_args()
    work = Path(a.work) if hasattr(a, "work") else Path("data/work")

    if a.cmd == "run":
        from . import download, pipeline
        video = Path(a.video)
        if not video.exists():
            print(f"[scout] downloading {a.video}")
            video = download.download(a.video, work / "videos")
        event_detail = None
        event, match = a.event, a.match
        if (event is None or match is None) and not Path(a.video).exists():
            # parse "Qualification N - ... - <Division> Division" titles
            import re
            import subprocess
            title = subprocess.run(
                ["yt-dlp", "--print", "%(title)s", "--no-download",
                 a.video], capture_output=True, text=True).stdout.strip()
            m = re.search(r"Qualification\s+(\d+)", title, re.I)
            d = re.search(r"-\s*([A-Za-z]+)\s+Division", title)
            if m and d:
                match = match or int(m.group(1))
                event = event or d.group(1).upper()
                print(f"[scout] parsed title -> match {match}, "
                      f"event {event}")
        if event and match:
            from . import eventdata
            event_detail = eventdata.match_detail(2026, event, match)
        labels = None
        if a.labels:
            import json as _json
            labels = _json.loads(Path(a.labels).read_text()).get(
                "labels", {})
        pipeline.run(video, work, Path(a.calibration), fps=a.fps,
                     do_ocr=not a.no_ocr, max_seconds=a.max_seconds,
                     event_detail=event_detail, labels=labels)
    elif a.cmd == "calibrate":
        import cv2
        from . import calibrate
        video = Path(a.video)
        cap = cv2.VideoCapture(str(video))
        cap.set(cv2.CAP_PROP_POS_MSEC, a.t * 1000)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            sys.exit("could not read frame from video")
        quad = calibrate.auto_detect_quad(frame)
        if quad is None:
            print("auto-detection failed — opening click UI "
                  "(click BL, BR, TR, TL; ESC to quit)")
            try:
                calibrate.make_viewer(Path(a.out), video, work)
            except cv2.error as e:
                sys.exit(f"no display for click UI ({e}); edit the "
                         "calibration JSON manually with 4 field-corner "
                         "pixel coords (order: bottom-left, "
                         "bottom-right, top-right, top-left).")
            return
        calibrate.save_calibration(quad, Path(a.out),
                                   frame.shape[1], frame.shape[0])
        print("wrote", a.out, quad)
    elif a.cmd == "feed":
        import json
        import shutil
        scouting = json.loads(Path(a.scouting).read_text())
        # top-N per alliance (default 3 = a real match lineup)
        per_alliance = max(1, a.top // 2)
        teams = []
        for alliance in ("red", "blue"):
            group = [(k, v) for k, v in scouting["teams"].items()
                     if k.startswith(alliance + "-")]
            group.sort(key=lambda kv: -kv[1]["drive_time_s"])
            teams.extend(group[:per_alliance])
        dest = Path(a.sim) / "archetypes" / "scouted"
        dest.mkdir(parents=True, exist_ok=True)
        src_dir = Path(a.scouting).parent / "archetypes"
        picked = []
        for key, st in teams:
            src = src_dir / f"{key}.toml"
            if src.exists():
                shutil.copy(src, dest / src.name)
                picked.append(src.name)
        print(f"fed {len(picked)} archetypes -> {dest}")
        for p in picked:
            print(" ", p)
    elif a.cmd == "batch":
        import json as _json
        from . import batch, eventdata
        season, event = a.season, a.event
        work = Path("data/batch") / f"{season}_{event}"
        work.mkdir(parents=True, exist_ok=True)
        # ensure event-level scrape exists
        ev_json = work / f"{season}_{event}.json"
        if not ev_json.exists():
            data = eventdata.event_scouting(season, event)
            ev_json.write_text(_json.dumps(data))
        if a.reclassify:
            n = batch.reclassify_all(work)
            print(f"reclassified {n} matches")
            return
        if not a.aggregate_only:
            quals = _json.loads(ev_json.read_text())["quals"]
            for q in quals[a.skip:][:a.limit]:
                try:
                    out_dir, skipped = batch.run_match(
                        season, event, q["match"], a.playlist, work,
                        Path(a.calibration), fps=a.fps,
                        max_seconds=a.max_seconds,
                        keep_frames=a.keep_frames,
                        keep_video=a.keep_video)
                    print(f"match {q['match']}: "
                          f"{'skipped' if skipped else 'done'} -> {out_dir}")
                except Exception as e:
                    print(f"match {q['match']}: FAILED {e}")
        teams = batch.aggregate(work, season, event)
        print(f"aggregated {len(teams)} team profiles -> {work/'teams'}")
    elif a.cmd == "label":
        from . import labeltool
        labeltool.generate(Path(a.out_dir))
    elif a.cmd == "event":
        import json
        from . import eventdata
        out = Path(a.out) if a.out else \
            Path("data/event") / f"{a.season}_{a.event}.json"
        data = eventdata.event_scouting(a.season, a.event, a.matches)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, indent=2))
        print(f"wrote {out}: {len(data['quals'])} matches, "
              f"{len(data['teams'])} teams")
    elif a.cmd == "autocal":
        from . import autocal
        autocal.run(Path(a.video), work, Path(a.out),
                    max_seconds=a.max_seconds)
    elif a.cmd == "registry":
        import json as _json
        from . import registry
        reg_path = Path("data/registry/teams.json")
        if a.action == "set":
            e = registry.set_mechanisms(
                reg_path, a.value, a.mech,
                cad_url=a.cad_url, robot_name=a.robot_name,
                notes=a.notes)
            print(_json.dumps({a.value: e}, indent=2))
        elif a.action == "import":
            exported = _json.loads(Path(a.value).read_text())
            reg = registry.merge_export(reg_path, exported)
            print(f"merged {len(exported)} teams -> {reg_path}")
        else:
            print(_json.dumps(registry.load(reg_path), indent=2))
    elif a.cmd == "cads":
        import json as _json
        from . import cads, registry
        ev_json = Path("data/event") / f"{a.season}_{a.event}.json"
        if not ev_json.exists():
            ev_json = Path("data/batch") / \
                f"{a.season}_{a.event}" / ev_json.name
        teams = sorted(_json.loads(ev_json.read_text())["teams"],
                       key=int)
        out = cads.review_page(
            teams, a.event, Path("data/registry/review.html"),
            existing=registry.load(Path("data/registry/teams.json")))
        print(f"wrote {out} ({len(teams)} teams)")
    elif a.cmd == "sheet":
        from . import sheet
        batch_dir = Path("data/batch") / f"{a.season}_{a.event}"
        out = batch_dir / "sheet.csv"
        rows = sheet.build_sheet(batch_dir, out)
        print(f"wrote {out} ({len(rows)} teams)")
    elif a.cmd == "playlist":
        import subprocess
        subprocess.run(["yt-dlp", "--flat-playlist", "--print",
                        "%(id)s | %(title)s", a.url], check=True)


if __name__ == "__main__":
    sys.exit(main())
