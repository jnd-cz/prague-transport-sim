# Rules for every agent and session (Claude, ChatGPT / Codex, others)

A Tatra T3 tram driving game in a 3D Prague built from real data. Plain ES modules + Three.js, no build
step; Python tools build the world from pinned source snapshots. Read before working:
[README.md](README.md) (run, build, play), [DATA.md](DATA.md) (snapshots, data store),
[ROADMAP.md](ROADMAP.md) (milestones), [docs/knowledge.md](docs/knowledge.md) (what we learned: data
quirks, conventions, why the main heuristics exist), [docs/architecture.md](docs/architecture.md) (the
target design) and [docs/decisions/](docs/decisions/).

## Starting a session (one issue per session)

1. `git checkout main && git pull`, then `python -I tools/snapshot.py status`; if `data/` differs from
   the manifest, `python -I tools/snapshot.py data-fetch` (builds also need `fetch` for `raw/`).
2. `python --version` is 3.12 or newer (an older one first on PATH breaks `-P`).
3. `gh issue view N --comments`; branch `N-short-name` from `main`.
4. The issue says what is now, where, and when it is done; the known failures below are not yours.

## Work

- **Tasks live in GitHub issues** (`jnd-cz/prague-transport-sim`), grouped by milestone. Docs link to
  issues instead of listing tasks. New findings that are not fixed now become an issue.
- One branch per issue (`<number>-<short-name>`), PR into `main`, the PR says which checks were run and
  their numbers. Small doc or data-fact changes may go straight to `main`.
- PR description: `Closes #N.`, what changes and why, a check table (line × check, before → after),
  and for rebuilt data what changed per line. Merged as a squash, subject `<PR title> (#PR)` (the title
  ends with `(#issue)`), branch deleted.
- Rebuilt data: `python -I tools/snapshot.py data-publish --note "…"` from the branch, commit
  `data/MANIFEST.json` on it, then merge. `main`'s manifest always names data that is in the store.
- New issues: what is now (with numbers), where in the code, what done means, which checks prove it.
  A fresh session should need nothing but the issue.
- Commits: what changed and why, with numbers where something was measured. Author email in this repo:
  `2506000+jnd-cz@users.noreply.github.com` (`git config user.email …` per clone).
- **Fix rules, not spots.** Measure an issue on every line (lints, benches, `data/truth.json`), change
  the rule that produced it, measure again on all lines. A local special case needs a fact in
  `data/truth.json`, not a coordinate in code.
- **Realism over convenience.** Keep the driver's real skills (contacts, coasting, signals) instead of
  automating them. Facts from the user (a Prague tram expert) win over heuristics.
- Heuristics standing in for missing data log what they decided (debug overlay F8, `window.game`) so they
  can be reviewed.

## Data

- **Never edit generated data by hand** (`data/line*.json` and sidecars): change the tool and rebuild.
  Hand-made facts go to `data/truth.json`.
- Sources come only from the pinned snapshot in `raw/` (`python -I tools/snapshot.py fetch`); OSM only
  from its local extract (`raw/osm/praha.osm.pbf`). **The public Overpass API is not used.**
- One coordinate conversion for every tool: `tools/geo.py`.
- Tools write files in `data/` and `raw/` whole (`tools/atomic.py`), never in place: with a machine cache
  (`TRAMDATA_CACHE`, DATA.md) they are protected hard links shared by every checkout.
- New source files go into a snapshot (`tools/snapshot.py publish`), with source URL, licence and date.

## Running and checking

- Dev server: `python tools/serve.py 8742` (no-cache headers; `POST /report/<name>.json` saves to
  `reports/`). One port per agent on a computer: Claude 8742, Codex 8743, `headless.py` 8745 (its
  default; a second run at once takes `--port 876x`). Port 8740 may belong to another session: never
  use or stop it.
- Python: `python -I` for stdlib-only tools; `python -P -E` for tools needing the user site packages
  (pyosmium, pyproj, shapely, numpy, Pillow). Write multi-line scripts to a file and run it: shell
  heredocs with quotes can break in the Windows shells.
- Checks from the command line: `python -P -E tools/headless.py --lines 17 --checks u3,redruns,traffic,lint
  --seeds 1-3` (headless Chromium, its own server; exit code 1 on a failed threshold; `--jobs N` pages at
  once, by default as many as cores and free memory allow). Rebuilds: `python -P -E tools/rebuild.py 17`
  (`--parallel` for several lines). Keep memory in check: long jobs size themselves by free memory
  (`tools/sysinfo.py`); don't start a second heavy job while one runs.
- Checks in a page: `tools/lint.js` on a page loaded with `?keepgeo` (`lint()`, `lint({ traffic: true })` averages
  seeds 22, 7, 1234), `python tools/lint_report.py` against `reports/baseline/lineN.json` (an in-page
  baseline of 2026-10-23, before #7 and #84, not maintained: regressions use `headless.py --compare`); benches in `tools/bench/`
  (u3, redruns, walkers; `batch.html`). Run long browser jobs unawaited and poll (script calls time out
  at 45 s); a background window throttles frames, so no fps readings then.
- Dev switches: `?line=N`, `?inspect`, `?bot`, `?keepgeo`, `?nofine`, `?nospread`, `?notunnels`.
- A regression check compares a run with main's stored baseline (`headless.py … --compare`, the table
  goes into the PR); a count that moves needs a reason in the PR. When a PR moves the numbers, rerun with
  `--baseline` once its code and data are committed and published, and commit
  `reports/baseline/headless.json` with it.

## Known failures (not caused by your change; remove a row when its issue closes)

| check | line | symptom | issue |
|---|---|---|---|
| u3 | 9 | "stuck at 14355" (the 9 → 10 layover counts as a deadlock), every seed | #80 |
| redruns | 17 | seed 1: "1 ahead red runs" (an AI tram at the s 10826 signal brakes too gently on warn) | #92 |
| page load | lines without them | console 404s for optional sidecars (`line9.dtm.json`, `.signals`, `.dtmpoints`) | (expected) |

## Code style

- Match the surrounding code: plain modules, short names in hot loops, comments that say why (the data
  quirk, the measured case), not what. Units are metres, seconds, m/s unless named otherwise.
- No new dependencies or build steps without an issue that decides it. Tests and benches: Python +
  Playwright (headless Chromium); Node / Deno only once the simulation core is split out.
- Randomness must be reproducible: today the benches override `Math.random` with a seeded one; new
  simulation code takes its randomness from one place so a seeded RNG per run can replace it.
