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
# or try the automatic search (slower, ~30 min):
uv run frc-scout autocal <video.mp4> --out calibrations/<name>.json
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

## Official event data (recommended complement)

FIRST publishes full match score breakdowns at
`frc-events.firstinspires.org` — scrapable HTML, no API key:

```bash
uv run frc-scout event HOPPER --season 2026            # all 124 quals
uv run frc-scout event HOPPER --matches 10             # subset
# merge one match's official stats into a scouting run:
uv run frc-scout run <video> --calibration calibrations/x.json \
    --event HOPPER --match 1
```

Per match you get per-team auto-climb and endgame-tower results plus
alliance fuel counts per shift, fouls and final score — ground truth
that video inference can't match. `scouting.json` then contains both
the official `event` block and the video-derived track stats.

## Labeling tracks with team numbers

Bumper OCR doesn't work at broadcast resolution, so assign team
numbers manually — takes ~2 min per match:

```bash
uv run frc-scout label data/work/q1full2/out   # writes label.html
# open label.html in a browser: click a trajectory, pick its team
# from the roster, hit Export -> save as labels.json in the same dir
uv run frc-scout run <video> --calibration ... --labels labels.json
```

`--labels` renames tracks to real team numbers before archetypes and
strategy TOMLs are written, and merges fragments assigned to the same
team.

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
  are filtered by histogram matching against the calibration frame,
  but expect noise around segment boundaries.
- Team-number OCR on bumper plates is **not viable** at broadcast
  resolution — tesseract finds nothing. Instead the scorebug overlay
  is parsed for the 6 roster team numbers (`scorebug.py`), and
  `eventdata.py` pulls official per-match stats. Track→team-number
  assignment inside the video is still open; tracks are reported as
  `<alliance>-track-N` and merged when OCR does succeed.
- `mass`/`max_force` in emitted archetypes are heuristic estimates
  from observed speed/acceleration — treat as priors, not measurements.
- Auto-calibration (`autocal`) works but is slow (~5 min) and can land
  on degenerate quads; verify `calibrations/*.json` corners look right
  (field should fill most of the frame bottom). The click calibration
  remains the reliable path.
