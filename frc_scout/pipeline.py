"""End-to-end scouting pipeline."""
import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

from . import calibrate, detect, frames as frames_mod, ocr, registry, report, track


def run(video: Path, work: Path, calib_path: Path, fps: float = 10.0,
        do_ocr: bool = True, verbose: bool = True,
        max_seconds: float | None = None,
        event_detail: dict | None = None,
        labels: dict | None = None):
    out = work / "out"
    (out / "paths").mkdir(parents=True, exist_ok=True)
    (out / "archetypes").mkdir(parents=True, exist_ok=True)
    (out / "strategies").mkdir(parents=True, exist_ok=True)
    reg = registry.load(Path("data/registry/teams.json"))

    # 1. frames
    fdir = work / "frames"
    frame_paths = frames_mod.extract_frames(video, fdir, fps=fps,
                                            max_seconds=max_seconds)
    times = frames_mod.frame_times(len(frame_paths), fps)
    if verbose:
        print(f"[scout] {len(frame_paths)} frames @ {fps}fps")

    # 2. calibration
    calib = calibrate.load_calibration(calib_path)
    H = calibrate.homography_from_corners(calib["field_corners_px"])
    ref_idx = len(frame_paths) // 2
    cam_mask = frames_mod.main_camera_mask(frame_paths, ref_idx)
    # keep contiguous main-camera runs longer than 3 s
    runs, start = [], None
    for i, ok in enumerate(cam_mask):
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            if i - start > 30:
                runs.append((start, i))
            start = None
    if start is not None and len(cam_mask) - start > 30:
        runs.append((start, len(cam_mask)))
    keep = np.zeros(len(frame_paths), dtype=bool)
    for a, b in runs:
        keep[a:b] = True
    if verbose:
        print(f"[scout] main-camera frames: {int(keep.sum())}/"
              f"{len(frame_paths)} in {len(runs)} segment(s)")
    frame_paths = [p for p, k in zip(frame_paths, keep) if k]
    times = [t for t, k in zip(times, keep) if k]
    if not frame_paths:
        raise RuntimeError("no main-camera frames found")
    ref_idx = min(ref_idx, len(frame_paths) - 1)
    first = cv2.imread(str(frame_paths[len(frame_paths) // 2]))
    # field -> pixel quad for containment tests
    field_poly = np.float32(cv2.perspectiveTransform(
        calibrate.FIELD_CORNERS_M.reshape(-1, 1, 2), np.linalg.inv(H)
    ).reshape(-1, 2))

    # 3. detect + track
    tracker = track.Tracker()
    clock_samples = []
    traj = defaultdict(list)          # tid -> [(t, px, py)]
    alliances = {}                    # tid -> alliance (first seen)
    sizes = defaultdict(list)         # tid -> apparent size m^2 proxy
    team_votes = defaultdict(lambda: defaultdict(int))

    for i, fp in enumerate(frame_paths):
        img = cv2.imread(str(fp))
        if img is None:
            continue
        red, blue, _ = detect.alliance_masks(img)
        rb = detect.cluster_blobs(
            [b for b in detect.blobs_from_mask(red)
             if cv2.pointPolygonTest(field_poly,
                                     b["centroid"], False) >= 0])
        bb = detect.cluster_blobs(
            [b for b in detect.blobs_from_mask(blue)
             if cv2.pointPolygonTest(field_poly,
                                     b["centroid"], False) >= 0])
        active = tracker.update({"red": rb, "blue": bb}, times[i],
                                field_poly=field_poly)
        by_tid = {}
        # map blob -> track: re-derive via nearest active track
        for tr in active:
            by_tid[tr.tid] = tr
            traj[tr.tid].append((times[i], float(tr.pos[0]),
                                 float(tr.pos[1])))
            alliances[tr.tid] = tr.alliance
            # apparent size: bbox diagonal in field metres
            x, y, w, h = tr.bbox
            cx, cy = tr.pos
            corners = np.float32([[x, y], [x + w, y + h]]).reshape(-1, 1, 2)
            fc = cv2.perspectiveTransform(corners, H).reshape(-1, 2)
            d = float(np.linalg.norm(fc[1] - fc[0]))
            sizes[tr.tid].append(min(d, 3.0))
        # OCR on confirmed, moving tracks — throttled: every 2 s of
        # video, at most 8 tracks per round, stop once team is known
        if do_ocr and i % 20 == 0:
            candidates = [tr for tr in active
                          if tr.confirmed and tr.team is None]
            candidates.sort(key=lambda tr: -tr.hits)
            for tr in candidates[:8]:
                dets = rb if tr.alliance == "red" else bb
                best = min(dets, key=lambda b: np.linalg.norm(
                    np.array(b["centroid"]) - tr.pos), default=None)
                if best is None:
                    continue
                for v in ocr.read_team_number(img, best["bbox"],
                                              best["centroid"]):
                    team_votes[tr.tid][v] += 1
                    if sum(team_votes[tr.tid].values()) >= 3:
                        tr.team = max(team_votes[tr.tid].items(),
                                      key=lambda kv: kv[1])[0]
                        break
        # scorebug clock sample every ~5 s of video
        if i % 50 == 0:
            try:
                from . import scorebug
                sb = scorebug.parse_scorebug(img)
                if sb and sb.get("clock"):
                    clock_samples.append([round(times[i], 1), sb["clock"]])
            except Exception:
                pass
        if verbose and i % 100 == 0:
            print(f"  frame {i}/{len(frame_paths)} tracks={len(active)}")

    # 4. trajectories -> field coords + stats
    all_tracks = tracker.finish()
    # include dead tracks' trajectories (traj already recorded)
    tracks_field = report.build_tracks(traj, H, fps)
    for tid, tr in ((t.tid, t) for t in all_tracks):
        if tid in tracks_field:
            tracks_field[tid]["alliance"] = tr.alliance
            tracks_field[tid]["team"] = tr.team
            tracks_field[tid]["team_votes"] = dict(team_votes.get(tid, {}))
    # dead tracks keep their alliance label via first-seen map
    for tid, tk in tracks_field.items():
        if tk["alliance"] is None:
            tk["alliance"] = alliances.get(tid)
            tk["team"] = None
            tk["team_votes"] = dict(team_votes.get(tid, {}))

    # pixel path lengths + apparent sizes per fragment
    for tid, tk in tracks_field.items():
        pts = traj[tid]
        steps = [np.hypot(pts[i+1][1]-pts[i][1], pts[i+1][2]-pts[i][2])
                 for i in range(len(pts)-1)]
        tk["px_path"] = float(sum(steps))
        tk["_px_step"] = float(np.median(steps)) if steps else 0.0
        sz = sizes.get(tid, [])
        tk["_size_m"] = float(np.median(sz)) if sz else None

    # stitch fragments into robot-length trajectories
    from . import stitch
    work_tracks = stitch.stitch(tracks_field)
    if verbose:
        print(f"[scout] stitched {len(tracks_field)} fragments -> "
              f"{len(work_tracks)} trajectories")

    summary = {}
    winners = {}
    for tid, tk in work_tracks.items():
        if tk["hits"] < 30 or tk["px_path"] < 150.0 \
                or tk.get("_px_step", 0) < 2.0:
            continue
        st, xy, speed = report.summarize(tk, fps)
        st["_size_m"] = tk.get("_size_m") or 0.8
        dt = np.diff(tk["t"]); dt[dt <= 0] = 1 / fps
        acc = np.abs(np.diff(speed)) / dt[1:] if len(speed) > 2 else [0]
        st["_accel95"] = float(np.percentile(acc, 95)) if len(acc) else 2.0
        votes = tk.get("team_votes", {})
        team = (tk["team"]
                or (max(votes.items(), key=lambda kv: kv[1])[0]
                    if votes else None)
                or f"track-{tid}")
        if labels:
            real = labels.get(f"{tk['alliance']}-{team}")
            if real:
                team = real
        key = f"{tk['alliance']}-{team}"
        st["team"] = team
        st["alliance"] = tk["alliance"]
        st["track_id"] = tid
        st["team_votes"] = tk.get("team_votes", {})
        st["px_path"] = tk["px_path"]
        # merge fragments that resolved to the same team: keep the
        # longest-lived fragment's stats
        prev = summary.get(key)
        frags = (prev or {}).get("fragments", 0) + 1
        st["fragments"] = frags
        if prev is None or st["drive_time_s"] > prev["drive_time_s"]:
            summary[key] = st
            winners[key] = (tid, tk, st, speed, team)
        else:
            prev["fragments"] = frags

    # write outputs for winning fragments
    for key, (tid, tk, st, speed, team) in winners.items():
        (out / "paths" / f"{key}.json").write_text(json.dumps({
            "team": team, "alliance": tk["alliance"],
            "samples": [[round(t, 2), round(x, 2), round(z, 2)]
                        for t, (x, z) in zip(tk["t"], tk["xy"])]}))
        arch = report.estimate_archetype(tk, st, speed, team)
        toml_text = report.archetype_toml(arch)
        if team and reg:
            tags = registry.mech_tags(team, reg)
            if tags:
                toml_text += f"\n# mechanisms: {', '.join(tags)}\n"
                toml_text += registry.mech_toml_blocks(team, reg)
        (out / "archetypes" / f"{key}.toml").write_text(toml_text)
        (out / "strategies" / f"{key}.toml").write_text(
            report.strategy_toml(team, st, tk["alliance"]))

    scouting = {
        "video": str(video), "fps": fps,
        "teams": summary,
        "unidentified_tracks": [
            {"tid": tid, "alliance": work_tracks[tid]["alliance"],
             "hits": work_tracks[tid]["hits"],
             "px_path": round(work_tracks[tid]["px_path"], 1),
             "votes": work_tracks[tid].get("team_votes", {})}
            for tid in work_tracks
            if work_tracks[tid]["hits"] >= 30
            and work_tracks[tid].get("px_path", 0) >= 150.0
            and work_tracks[tid]["team"] is None
        ],
    }
    if event_detail:
        scouting["event"] = event_detail
    scouting["clock_samples"] = clock_samples
    (out / "scouting.json").write_text(json.dumps(scouting, indent=2))
    if verbose:
        print(f"[scout] {len(summary)} robot-tracks -> {out}")
    return scouting
