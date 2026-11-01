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

In Claude Code, `/issue N` runs these steps and `/regress` the regression check before a PR
(`.claude/skills/`).

## Work

- **Tasks live in GitHub issues** (`jnd-cz/prague-transport-sim`), grouped by milestone. Docs link to
  issues instead of listing tasks. New findings that are not fixed now become an issue.
- **Who works on what:** an issue in progress carries its agent's label (`agent:claude`, `agent:codex`),
  set when the work starts and removed when its PR merges; `gh issue list --label agent:codex` shows the
  other agent's work, its branch and draft PR the rest. Before starting, check the open PRs for files
  the issue will touch too (`gh pr list`, `gh pr diff N --name-only`).
- One branch per issue (`<number>-<short-name>`), PR into `main`, the PR says which checks were run and
  their numbers. Small doc or data-fact changes may go straight to `main`.
- PR description: `Closes #N.`, what changes and why, a check table (line × check, before → after),
  and for rebuilt data what changed per line. Merged as a squash, subject `<PR title> (#PR)` (the title
  ends with `(#issue)`), branch deleted.
- An issue done in parts (time-bound, waiting on data): each PR says `Part of #N`, and only the PR
  that finishes it says `Closes #N`.
- Rebuilt data: `python -I tools/snapshot.py data-publish --note "…"` from the branch, commit
  `data/MANIFEST.json` on it, then merge. `main`'s manifest always names data that is in the store.
- New issues: what is now (with numbers), where in the code, what done means, which checks prove it.
  A fresh session should need nothing but the issue.
- Where docs go: DATA.md is snapshots, the store and how to refresh sources; facts learned about data
  and code go to `docs/knowledge.md`, decisions to `docs/decisions/`. One place per fact: point to a
  table in code instead of copying it.
- Commits: what changed and why, with numbers where something was measured. Author email in this repo:
  `2506000+jnd-cz@users.noreply.github.com` (`git config user.email …` per clone).
- **Fix rules, not spots.** Measure an issue on every line (lints, benches, `data/truth.json`), change
  the rule that produced it, measure again on all lines. A local special case needs a fact in
  `data/truth.json`, not a coordinate in code.
- **Realism over convenience.** Keep the driver's real skills (contacts, coasting, signals) instead of
  automating them. Facts from the user (a Prague tram expert) win over heuristics. A user fact cites
  where it was said (the quote, and the issue or PR comment or the session date), in `data/truth.json`
  and in the PR.
- **Calibrate a check before it holds or overrules data:** measure it against an independent source where
  one exists (DI heights, survey points), split by the cases it covers. The #119 survey check held 4.6 km
  of line 17's open track: calibrated on street track only.
- Heuristics standing in for missing data log what they decided (debug overlay F8, `window.game`) so they
  can be reviewed.

## Unattended runs (overnight, Codex /goal, scheduled sessions)

- The task states what may be done without the user. Default when it does not: push the issue
  branch, open and update a draft PR, open issues for findings. Not without saying so: data-publish,
  marking a PR ready, merging, pushing to main, force-pushing, closing or editing other issues.
- The progress log is the draft PR, opened after the first commit: its description holds the current
  state (open questions for the user first, then the check table), with a dated comment per step.
  No log files in the repo; scratch output goes to `reports/` (ignored) or outside the checkout.
- A defect outside the issue becomes an issue (or a "Findings" section in the PR when issues are not
  allowed). It is fixed on the same branch only when the issue's checks cannot pass without it, in
  its own commits, and the PR says so.
- A measurement worth repeating becomes a check (`tools/bench/`, a `headless.py --checks` entry), not a
  scratch script the next session rewrites.
- Investigation scripts are not committed unless they run like the other tools: their own server on
  a free port (as `headless.py`), no fixed agent port, a usage line at the top.
- The run ends with the draft PR saying what is done, what was measured and what the user must
  decide; it does not mark it ready.

## Data

- **Never edit generated data by hand** (`data/line*.json` and sidecars): change the tool and rebuild.
  Hand-made facts go to `data/truth.json`.
- A provider that refuses scripted requests is waited out or read from a saved copy; requests are never
  disguised as a browser's (DATA.md, ZPS downloads).
- Sources come only from the pinned snapshot in `raw/` (`python -I tools/snapshot.py fetch`); OSM only
  from its local extract (`raw/osm/praha.osm.pbf`). **The public Overpass API is not used.**
- One coordinate conversion for every tool: `tools/geo.py`.
- Tools write files in `data/` and `raw/` whole (`tools/atomic.py`), never in place: with a machine cache
  (`TRAMDATA_CACHE`, DATA.md) they are protected hard links shared by every checkout.
- New source files go into a snapshot (`tools/snapshot.py publish`), with source URL, licence and date,
  and into `tools/sources.py` (its layer's fallback order, date, credits); built files carry their
  `provenance` from it.
- A publish is checked with `python -I tools/snapshot.py verify` (only the new files are fetched back),
  not by a full `fetch` into a fresh checkout.

## Running and checking

- Dev server: `python tools/serve.py 8742` (no-cache headers; `POST /report/<name>.json` saves to
  `reports/`). One port per agent on a computer: Claude 8742, Codex 8743, `headless.py` 8745 (its
  default; a second run at once takes `--port 876x`). Port 8740 may belong to another session: never
  use or stop it. A tool or test that needs a page starts its own server on a free port; the
  per-agent ports are for interactive dev servers.
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
- **Long jobs pin their checkout** (a rebuild, a fetch, a check run reads the files as they are): work on
  another issue meanwhile in its own worktree (`git worktree add ../<repo>-N -b N-name origin/main`, then
  `python -I tools/snapshot.py data-fetch`, from the machine cache in seconds), removed when done.
- Dev switches: `?line=N`, `?inspect`, `?review` (findings on the map, README), `?bot`, `?keepgeo`, `?nofine`, `?nospread`, `?notunnels`.
- A regression check compares a run with main's stored baseline (`headless.py … --compare`, the table
  goes into the PR); a count that moves needs a reason in the PR. When a PR moves the numbers, rerun with
  `--baseline` once its code and data are committed and published, and commit
  `reports/baseline/headless.json` with it.

## Known failures (not caused by your change; remove a row when its issue closes)

| check | line | symptom | issue |
|---|---|---|---|
| page load | lines without them | console 404s for optional sidecars (`line9.dtm.json`, `.signals`, `.dtmpoints`) | (expected) |
| traffic seed 3 | 22 | did not finish (stop 24, 7200 s): a jam | #154 |

## Code style

- Don't reformat code you are not changing (no formatter over whole files: #119's reflow buried its
  changes). Match the surrounding code: plain modules, short names in hot loops, comments that say why (the data
  quirk, the measured case), not what. Units are metres, seconds, m/s unless named otherwise.
- Docs say what is and what was measured, briefly: no disclaimers or hedges, no restating.
- No new dependencies or build steps without an issue that decides it. Tests and benches: Python +
  Playwright (headless Chromium); Node / Deno only once the simulation core is split out.
- Randomness must be reproducible: today the benches override `Math.random` with a seeded one; new
  simulation code takes its randomness from one place so a seeded RNG per run can replace it.
