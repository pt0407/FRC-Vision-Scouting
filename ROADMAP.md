# FRC-Vision-Scouting — Roadmap & Feature Plan

Vision: watch real match VODs, extract everything a top scouting
spreadsheet collects by hand, and feed it straight into
[`frc-multi-sim`](https://github.com/pt0407/frc-multi-sim) so you can
practice against robots that drive like the real ones.

Local-only, lightweight: yt-dlp + ffmpeg + OpenCV + numpy +
tesseract. No cloud APIs, no torch.

## Status legend

- ✅ shipped
- ⚠️ feasible with current signals (tracking/zones/event data)
- 🔴 needs a hard improvement (better tracking, trained detector, or
  new signal)
- 🚫 needs external/pit data or isn't possible from broadcast video

## Phase 0 — foundation (done)

Pipeline: VOD → frames@6–10fps → main-camera filter → HSV alliance
segmentation → blob tracker → tracklet stitching → field homography
→ stats + zones + events → scouting.json / paths / archetypes /
strategies. Calibration (manual + auto), scorebug clock/roster
parsing, FIRST event-data scraping, track-labeling HTML, mechanism
registry, batch playlist scouting, behavior classifier, sheet CSV
export.

## Phase 1 — identity (the biggest unlock)

Tracks are anonymous; every downstream feature needs team binding.

| # | Feature | Status |
|---|---------|--------|
| 1 | Auto track→team via official per-team climb results vs track tower presence | ✅ (weak signal, ~2 bindings/match) |
| 2 | Start-zone binding: roster start slots vs `auto_start` positions | ⚠️ needs start-position source |
| 3 | Re-ID across cuts via trajectory continuity + color signature | ⚠️ |
| 4 | Bumper-number reads via multi-frame super-resolution | 🔴 |
| 5 | Team logo/bumper-patch detection | 🔴 |
| 6 | Persistent team identity across matches (no re-labeling) | 🔴 |
| 7 | Confidence on every binding + one-click confirm in label.html | ⚠️ |
| 8 | "Pick the 6 real robots" quick UI | ✅-ish (label.html) |

## Phase 2 — motion & driver quality

| # | Feature | Status |
|---|---------|--------|
| 9 | Velocity vectors, accel/decel profiles, jerk stats | ✅ (accel95, jerk95) |
| 10 | Cruise vs burst speed, time-to-speed | ✅/⚠️ |
| 11 | Turning-radius + heading/velocity mismatch (swerve vs tank feel) | ⚠️ |
| 12 | Idle/stuck/dead windows with positions (tipped? blocked?) | ✅ |
| 13 | Path efficiency per phase | ✅ |

## Phase 3 — game behavior

| # | Feature | Status |
|---|---------|--------|
| 14 | Intake preference (ground piles vs stations) | ✅ |
| 15 | Cycle detection: pickup→hub round trips + cycle time | ✅ |
| 16 | Hub role: scorer / cleanup / passer / defender | ✅ (heuristic) |
| 17 | Shot-spot distance + release-position heatmap | ✅-ish (dist) / ⚠️ |
| 18 | Shooting-on-the-move vs set-and-shoot | ⚠️ |
| 19 | Pass events / fuel handoffs | 🔴 (ball too small) |
| 20 | Shot counting + per-robot fuel attribution | 🔴 |
| 21 | Climb attempts, duration, face, timing | ⚠️ (presence now) |
| 22 | Auto routine classification (which of N known autos) | ⚠️ |
| 23 | Trench/bump traversal counts | ⚠️ (needs zones) |
| 24 | Leave? / midline crossing in auto | ✅ |

## Phase 4 — interaction & defense

| # | Feature | Status |
|---|---------|--------|
| 25 | Robot-robot proximity/contact events | ⚠️ |
| 26 | Pin detection: sustained close proximity | ⚠️ |
| 27 | Pairwise interaction matrix (who blocks whom) | ⚠️ |
| 28 | Defense effectiveness: opponent cycle time when escorted | 🔴 |
| 29 | Push events: displacement while adjacent | 🔴 |
| 30 | Near-miss frequency / avoidance skill | 🔴 |
| 31 | Alliance spacing & traffic conflicts | ⚠️ |

## Phase 5 — mechanisms (registry-driven)

| # | Feature | Status |
|---|---------|--------|
| 32 | Mechanism registry (human-tagged from CADs) → `[[mech]]` TOML | ✅ |
| 33 | CAD review page per event | ✅ |
| 34 | Intake type inference from pickup pose | 🔴 |
| 35 | Turret vs fixed shooter via aim-vs-heading | 🔴 |
| 36 | Shooter range estimate from shot distance distribution | ⚠️ |
| 37 | Hopper capacity from dump duration | 🔴 |

## Phase 6 — season aggregation & reporting

| # | Feature | Status |
|---|---------|--------|
| 38 | Per-team profiles: event stats + labeled video stats | ✅ |
| 39 | 5572-sheet-style CSV export | ✅ |
| 40 | Speed class / consistency / improvement trends | ⚠️ |
| 41 | OPR / DPR / CCWM from event data | ⚠️ |
| 42 | Pick-list ordering + complement scores | ⚠️ |
| 43 | Counter-scouting: how to defend each team | ⚠️ |
| 44 | Match-up prediction from profiles | 🔴 |
| 45 | Natural-language scouting summary | ⚠️ |
| 46 | Heatmaps per team (label page or PNG) | ⚠️ |
| 47 | Auto-cut highlight clips per team | ⚠️ |
| 48 | Side-by-side team comparison page | ⚠️ |
| 49 | Pre-match "what to expect" card | ⚠️ |
| 50 | Pit-scout merge (paper form → registry) | ✅-ish |

## Phase 7 — sim integration

| # | Feature | Status |
|---|---------|--------|
| 51 | `feed`: archetypes + `[[mech]]` into frc-multi-sim | ✅ |
| 52 | Replay scouted trajectories as scripted agents | ⚠️ (paths exist) |
| 53 | Strategy agents conditioned on tendencies | ⚠️ |
| 54 | Drive-profile fitting (accel limits, force) | ✅ (heuristic) |
| 55 | What-if: swap mechanism, re-sim match | ⚠️ |
| 56 | Sim-vs-real path divergence metric | 🔴 |
| 57 | Practice-partner: sim plays like a specific team | 🔴 |

## Phase 8 — pipeline robustness

| # | Feature | Status |
|---|---------|--------|
| 58 | Track counts to ~6 robots/match (from ~30-46 now) | 🔴 active |
| 59 | Auto-recalibration per camera cut / zoom | 🔴 |
| 60 | Occlusion masks for field elements (hubs block robots) | ⚠️ |
| 61 | Fuel-ball tracking | 🔴 |
| 62 | Replay/closeup exclusion improvements | ⚠️ |
| 63 | Per-point confidence (blur, occlusion) | ⚠️ |
| 64 | Phase boundaries from scorebug clock | ✅ |
| 65 | Video-quality score per match | ⚠️ |

## Working principles

- **Official data for *what*, video for *how*.** FIRST's match tables
  are ground truth for scoring/climbs; video answers "how did they
  move" that no score table can.
- **Human-in-the-loop beats bad automation.** 2 minutes of labeling
  per match (track→team, mechanism tags) beats a wrong guess baked
  into every downstream stat.
- **Stay lightweight.** If a feature needs a trained model, gate it
  behind an optional dependency; the default path stays OpenCV +
  numpy.
