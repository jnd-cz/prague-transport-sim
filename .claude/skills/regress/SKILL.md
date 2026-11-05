---
name: regress
description: Regression check of the current branch against main's stored baseline - pick the lines and checks from what the branch changed, run tools/headless.py --compare, and write the check table for the PR. Use when the user says /regress, "run the checks", "regression check" or before opening a PR in this repo.
argument-hint: "[lines, e.g. 9,23] (default: chosen from the diff)"
---

# Regression check

Compares this branch with main's baseline (`reports/baseline/headless.json`, issue #89) instead of
rerunning the published data.

1. **What changed:** `git diff --name-only origin/main...HEAD` plus uncommitted changes, and
   `git diff origin/main -- data/MANIFEST.json` if data was rebuilt.
2. **The tier** (AGENTS.md, "Which checks a change needs"; a change of two kinds runs both), and the
   lines (unless given: $ARGUMENTS):
   - **the simulation** (`src/traffic.js`, `src/autopilot.js`, `src/tram.js`, `src/tr37.js`, the game's rules
     in `src/game.js`, `tools/traffic_lint.js`, `tools/bench/`, `tools/autopilot.js`): all lines,
     9,17,22,23,37, `--checks u3,redruns,traffic,lint`, seeds 1-5.
   - **a build tool with rebuilt data** (world): the lines whose files changed in the manifest (or in
     `data/` against it); a build tool whose data is not rebuilt yet is rebuilt first
     (`python -P -E tools/rebuild.py <lines> --parallel`). `--checks lint,surfaces,canted,crossing,spacing,heights`,
     then a smoke drive per line, `--checks u3 --seeds 1` (it reaches the last stop and is not stuck;
     its counts are not compared), and `tools/datadiff.py` / `tools/track_moves.py` per line. No traffic
     or redruns: they measure traffic reshuffled by the new data (#156).
   - **drawn geometry in the game** (surfaces, track beds, crossings, kerbs: `src/terrain.js`, `src/world.js`,
     `src/heights.js` …): all lines, `--checks lint,surfaces,crossing,canted`.
   - **drawing or load that keeps the world** (models, materials, load cuts): no headless run; screenshots
     main vs branch, `tools/frametime.py`, and for a load cut the world after load compared with main's.
   - the review page (`src/review.js`, `src/trackHeightProfile.js`) only: `python -P -E tools/test_review.py`
     instead of the headless checks.
   - docs or harness only: no run needed; say so.
3. **Run** in the background. Heavy jobs take turns (AGENTS.md): the run waits its turn and says whom it
   waits for, so start it and let it wait rather than starting a second one beside it. Every check on
   every line takes 27 minutes with 4 pages at once (#205), the geometry checks a few minutes a line.
   `python -P -E tools/headless.py --lines <lines> --checks <the tier's checks> --compare`
   (`--port 0` when another headless run uses 8745). Seeded counts are judged against main's spread over
   its seeds (#156); fewer seeds (`--seeds 1-2`) still compare against the full spread, only less surely.
4. **Read the result:**
   - A stale-baseline warning: main moved since its baseline. Say so, and read the differences as main's
     changes plus the branch's.
   - Known failures in AGENTS.md (its table) are not regressions.
   - The table lists, per line and check: counts whose mean left main's seed spread (**worse** /
     better), counts that moved inside it (noise: no reason needed), and per-seed hard failures
     (stuck, unfinished, penalties). Seedless checks (lint, surfaces) list every move.
   - Every mean outside the spread, every per-seed failure and every seedless move needs a reason tied to
     the change (e.g. "roads changed at the corridor edge"). A **worse** mark without one is a regression:
     report it, don't paper over it.
5. **For the PR:** the table from `reports/headless/compare.md` (counts and places), the reasons, and for
   rebuilt data what changed per line. The baseline is not refreshed in the PR: the deploy PC measures
   main's after the merge, at night, and publishes it (#157). A stuck run is opened with
   `?line=N&seed=S&at=<its s>` (the traffic check's run, handed over paused).
