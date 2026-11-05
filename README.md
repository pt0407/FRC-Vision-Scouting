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

## Batch playlist scouting

Process every qual match in an event playlist and aggregate
per-team season profiles:

```bash
uv run frc-scout batch HOPPER \
    "https://www.youtube.com/playlist?list=PLZT9pIgNOV6a8Ygkf-b-B50eHs0C-0BK7" \
    --calibration calibrations/champs_hopper.json
# resume later — matches with existing scouting.json are skipped:
uv run frc-scout batch HOPPER <playlist> --calibration ... --skip 5
# rebuild profiles from already-processed matches only:
uv run frc-scout batch HOPPER <playlist> --calibration ... --aggregate-only
```

Per match: `data/batch/<season>_<event>/matches/NNN/out/` (same
outputs as `run`), plus `data/batch/<season>_<event>/teams/<team>.json`
with official event stats + any labeled video track stats rolled up.
Playlist→match mapping is cached in `playlist_map.json`.

Caveats: each division's broadcast may use a different camera angle —
one calibration JSON per division/broadcast. ~55 MB per VOD; at
`--fps 6` a match takes a few minutes locally.

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

## Mechanism registry (CAD-tagged)

Video can't see mechanisms at broadcast resolution — so tag them
yourself from team CADs/reveals, and the sim gets real `[[mech]]`
geometry:

```bash
# review page: one card per team with CAD/reveal search links,
# mechanism checkboxes, notes. Open, tag, Export JSON:
uv run frc-scout cads HOPPER           # -> data/registry/review.html

# or tag directly:
uv run frc-scout registry set 8749 \
    --mech "turret_shooter:mount=corner" \
    --mech "climb_arm:level=2" \
    --cad-url "https://cad.onshape.com/..." \
    --notes "corner turret, ground intake"

# merge the exported JSON from the review page:
uv run frc-scout registry import mechanisms_export.json
uv run frc-scout registry list
```

Registry lives in `data/registry/teams.json`. Mech types:
`ground_intake`, `climb_arm`, `climb_elevator`, `turret_shooter`
(sim geometry presets -> `[[mech]]` TOML in archetypes) plus tag-only
types `station_intake`, `hopper`, `feeder`, `die_rotor`,
`inline_shooter`, `over_bumper_intake`, `defense`.

Once a labeled run hits a registry team, the emitted archetype TOML
carries real mechanism joints matching frc-multi-sim's `[[mech]]`
schema — not just a rigid box.
