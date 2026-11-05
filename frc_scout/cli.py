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
        from . import calibrate
        video = Path(a.video)
        cap = __import__("cv2").VideoCapture(str(video))
        cap.set(__import__("cv2").CAP_PROP_POS_MSEC, a.t * 1000)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            sys.exit("could not read frame from video")
        quad = calibrate.auto_detect_quad(frame)
        if quad is None:
            print("auto-detection failed. Either install opencv-python "
                  "and re-run for the click UI, or edit the calibration "
                  "JSON manually with 4 field-corner pixel coords "
                  "(order: bottom-left, bottom-right, top-right, "
                  "top-left).")
            sys.exit(1)
        calibrate.save_calibration(quad, Path(a.out),
                                   frame.shape[1], frame.shape[0])
        print("wrote", a.out, quad)
    elif a.cmd == "playlist":
        import subprocess
        subprocess.run(["yt-dlp", "--flat-playlist", "--print",
                        "%(id)s | %(title)s", a.url], check=True)


if __name__ == "__main__":
    sys.exit(main())
