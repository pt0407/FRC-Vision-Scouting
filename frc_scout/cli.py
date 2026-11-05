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

    ac = sub.add_parser("autocal",
                        help="auto-search field calibration")
    ac.add_argument("video")
    ac.add_argument("--out", required=True)
    ac.add_argument("--max-seconds", type=float, default=90.0)

    pl = sub.add_parser("playlist",
                        help="list videos in a YouTube playlist")
    pl.add_argument("url")

    a = p.parse_args()
    work = Path(a.work) if hasattr(a, "work") else Path("data/work")

    if a.cmd == "run":
        from . import download, pipeline
        video = Path(a.video)
        if not video.exists():
            print(f"[scout] downloading {a.video}")
            video = download.download(a.video, work / "videos")
        pipeline.run(video, work, Path(a.calibration), fps=a.fps,
                     do_ocr=not a.no_ocr, max_seconds=a.max_seconds)
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
        teams = sorted(scouting["teams"].items(),
                       key=lambda kv: -kv[1]["drive_time_s"])[:a.top]
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
    elif a.cmd == "autocal":
        from . import autocal
        autocal.run(Path(a.video), work, Path(a.out),
                    max_seconds=a.max_seconds)
    elif a.cmd == "playlist":
        import subprocess
        subprocess.run(["yt-dlp", "--flat-playlist", "--print",
                        "%(id)s | %(title)s", a.url], check=True)


if __name__ == "__main__":
    sys.exit(main())
