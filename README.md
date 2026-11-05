# FRC-Vision-Scouting

Video-based scouting for FIRST Robotics Competition: watch match VODs,
track every robot on the field, and emit per-team scouting reports,
strategy profiles, and robot archetypes that feed directly into
[`pt0407/frc-multi-sim`](https://github.com/pt0407/frc-multi-sim)
(`--archetype` TOML files).

Fully local and lightweight: yt-dlp + ffmpeg + OpenCV + numpy +
tesseract. No cloud APIs, no torch, no training required.

## Pipeline

```
YouTube VOD ──yt-dlp──▶ mp4 ──ffmpeg──▶ frames @10fps
                                        │
              field calibration JSON ───┤  (pixel→field homography)
                                        ▼
              HSV alliance segmentation (red/blue bumpers)
                                        ▼
              multi-object tracker (pixel space)
                                        ▼
              homography → field coords (m) → zone occupancy,
              speed/accel stats, auto-vs-teleop split
                                        ▼
              tesseract OCR on bumper crops → team numbers
                                        ▼
out/scouting.json  out/paths/*.json  out/archetypes/*.toml  out/strategies/*.toml
```

## Setup

```bash
uv sync
# one-time per broadcast angle: calibrate field corners
uv run frc-scout calibrate <video.mp4> --out calibrations/<name>.json --t 60
```

The calibrate tool opens the frame; click the four field corners in
order **bottom-left, bottom-right, top-right, top-left**. FIRST
championship broadcasts reuse the same main camera across a division,
so one calibration covers a whole playlist.

## Scout a match

```bash
uv run frc-scout run "https://www.youtube.com/watch?v=..." \
    --calibration calibrations/champs_hopper.json
# or a local file:
uv run frc-scout run data/q1.mp4 --calibration calibrations/x.json \
    --fps 10 --max-seconds 150
```

## Feed frc-multi-sim

Archetypes land in `out/archetypes/<alliance>-<team>.toml` in exactly
the format `frc-multi-sim`'s `--archetype` flag consumes:

```bash
cd ../frc-sim-m0
cargo run --release --bin server -- \
    --archetype ../frc-scout/out/archetypes/red-254.toml ...
```

`out/strategies/<team>.toml` carries scouting stats (zone times, speed,
auto behavior) for future strategy-agent conditioning.

## Status / known limitations

- v1: single fixed camera assumption; hard cuts to close-ups/replays
  will produce garbage tracks during those segments (tracks are
  filtered by motion, but expect noise).
- Team-number OCR is best-effort; tracks that never OCR a confident
  number are reported as `track-N` and listed under
  `unidentified_tracks` in `scouting.json`.
- `mass`/`max_force` in emitted archetypes are heuristic estimates
  from observed speed/acceleration — treat as priors, not measurements.
- Auto-calibration (`auto_detect_quad`) is a fallback; the click
  calibration is the reliable path.
