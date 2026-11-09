# Rules for every agent and session (Claude, ChatGPT / Codex, others)

A Tatra T3 tram driving game in a 3D Prague built from real data. Plain ES modules + Three.js, no build
step; Python tools build the world from pinned source snapshots. Read before working:
[DEVELOPING.md](DEVELOPING.md) (build, deploy, dev tools), [DATA.md](DATA.md) (snapshots, data store),
[README.md](README.md) (the player's guide in Czech; [README.en.md](README.en.md) in English),
[ROADMAP.md](ROADMAP.md) (milestones), [docs/knowledge.md](docs/knowledge.md) (what we learned: data
quirks, conventions, why the main heuristics exist), [docs/architecture.md](docs/architecture.md) (the
target design) and [docs/decisions/](docs/decisions/).

## Starting a session (one issue per session)

1. **The main checkout stays on `main`** (`git pull` there); every session works in its issue's own
   worktree: `git worktree add ../<repo>-N -b N-short-name origin/main`, then in it
   `python -I tools/snapshot.py data-fetch` (from the machine cache in seconds; builds also need `fetch`
   for `raw/`). Removed when its PR merges, after a look at its untracked files.
2. `python --version` is 3.12 or newer (an older one first on PATH breaks `-P`).
3. `python -I tools/board.py`: who works where, the heavy-job queue, the holder of the `rebuild` label,
   clashes between branches, what is ready to start. A clash with files the issue will touch is settled
   before the work starts: wait for that branch, branch from it, or take another issue.
4. `gh issue view N --comments`. The issue says what is now, where, and when it is done; the known
   failures below are not yours.

In Claude Code, `/issue N` runs these steps and `/regress` the regression check before a PR
(`.claude/skills/`). `/housekeeping` is the weekly pass, also run every Monday at 06:30, and with
`checkpoint` the architecture review at a world checkpoint ([docs/housekeeping.md](docs/housekeeping.md));
both post on the pinned #291 and only propose.

## Work

- **Tasks live in GitHub issues** (`jnd-cz/prague-transport-sim`), grouped by milestone. Docs link to
  issues instead of listing tasks. New findings that are not fixed now become an issue.
- **Who works on what:** an issue in progress carries its agent's label (`agent:claude`, `agent:codex`),
  set when the work starts and removed when its PR merges; `tools/board.py` shows every branch with its
  agent, worktree, last edit and the files it shares with other branches.
- **Lanes** (the issues' `lane:*` labels; the board counts the live sessions of each against `LIMITS`):

  | lane | covers | sessions | checks (below) |
  |---|---|---|---|
  | `lane:world` | build tools, `data/`, `truth.json`, the ground and track drawing, review queues | 2: one holds the `rebuild` label, one writes tools and tests without publishing | static |
  | `lane:sim` | traffic, autopilot, tram physics, walkers' behaviour, the game's rules | 1 | seeded |
  | `lane:assets` | models, materials, frame time | 1 | drawing |
  | `lane:tooling` | checks, board, queue, deploy, CI, docs | 1 | its tests |

  The world comes first, one layer at a time with a checkpoint after each (ROADMAP.md). The simulation
  lane waits for checkpoint W2, apart from the PRs in flight on 2026-11-05 (the user, 2026-11-05: "pause
  simulation work after finishing the current PRs"); the board shows it paused (`tools/board.py` `PAUSED`, removed at
  that checkpoint).
- **One rebuild at a time:** only the branch whose issue holds the `rebuild` label rebuilds every line
  and publishes (`snapshot.py data-publish` refuses on another branch). It is taken with `gh issue edit N
  --add-label rebuild` while nobody holds it (the board shows the holder) and removed when that data's PR
  merges. Other branches change build tools, test them on a local rebuild and wait to publish.
- **Order:** GitHub's blocked-by links (an issue's "Blocked by") say what comes first; the board lists the
  issues ready to start. A step that reads another step's output waits for it: heights, stops and speeds
  read the track; the ground reads the track and its profile; structures and furniture stand on the ground.
- One branch per issue (`<number>-<short-name>`), PR into `main`, the PR says which checks were run and
  their numbers. Small doc or data-fact changes may go straight to `main`.
- PR description: `Closes #N.` (or `Part of #N.`, below), what changes and why, a check table (line × check, before → after),
  and for rebuilt data what changed per line. Merged as a squash, subject `<PR title> (#PR)` (the title
  ends with `(#issue)`), branch deleted.
- **`Closes #N` only when this PR meets every point of the issue's "Done when".** Anything still
  open (the user's answers in a review queue, an import of those answers, a rebuild, a data-publish,
  another line) makes it `Part of #N`; the PR and a comment on the issue list what remains. What remains
  that belongs to another issue moves there (a comment, a blocked-by link), so an open issue holds only
  its own open points. Only the PR that finishes it says `Closes #N`. A reviewer who finds an open point changes the keyword before the
  merge (#146 was nearly closed with six places still awaiting the user's answers).
- Review findings: a reviewer posts them as a PR comment ("To fix before merge", "Smaller"); the author
  answers point by point in a comment and pushes. A PR is marked ready and merged on the user's word only.
- **Merge windows:** the user merges ready PRs in batches. A session whose checks are done says so and
  waits; a draft idle for 48 h is closed or labelled `parked`, with a comment on what is left and what to
  redo. Questions for the user go under a "Questions for the user" heading in the PR (the board collects
  them: `board.py --questions`); an issue waiting for answers carries `needs-user`.
- Rebuilt data: `python -I tools/snapshot.py data-publish --note "…"` from the branch holding the
  `rebuild` label, commit
  `data/MANIFEST.json` on it, then merge. `main`'s manifest always names data that is in the store.
- New issues: what is now (with numbers), where in the code, what done means, which checks prove it.
  A fresh session should need nothing but the issue.
- **The player's guide comes in two languages:** a change to `README.md` (Czech, first) changes
  `README.en.md` too; both are Help in the game's menu (`src/help.js`). `tools/test_readme.py` checks their
  headings, not their sentences. Developer docs stay in English, in `DEVELOPING.md`.
- Where docs go: DATA.md is how snapshots and the store work and how to refresh sources, and
  `snapshots/README.md` lists the snapshots (a row with each new one); facts learned about data
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
- **Questions for the user go to a `?review` findings file** (`reports/review/`, DEVELOPING.md): the place,
  imagery links, a picture where it helps, answer choices. Offer only answers that an importer turns into
  evidence, and say on the card why another answer stays held (#162, #176). An answer is keyed by a
  stable identity (a decision ID, a place), never by a generated array index. The file names its `issue`
  and `line` (or `lines`): the review directory (`reviews.html`, #288) lists it under them. A set whose
  issue is closed while findings wait is out of date: delete its file (the user, 2026-11-05: "If the issue
  is closed and reviews are unasnwered then it's out of date and can be deleted"); the directory lists
  such sets apart.

## Unattended runs (overnight, Codex /goal, scheduled sessions)

- The task states what may be done without the user. Default when it does not: push the issue
  branch, open and update a draft PR, open issues for findings. Not without saying so: data-publish,
  marking a PR ready, merging, pushing to main, force-pushing, closing or editing other issues, a
  `Closes #N` for an issue with open points.
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
  Hand-made facts go to `data/truth.json`: facts from the user or a source, each citing where it came
  from; a new section names its reader in the file's `readers`, or that it is reference only (#224).
  Not check exemptions, agent audits or lists of generated array indexes: a rebuild renumbers
  them (#177's allowlist would have failed every line on the next rebuild). Key a fact by place, a
  stable source ID or a stop. What a check can decide from geometry stays a rule in the check, counted
  per class with its places, so `--compare` shows what a rebuild moved.
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
  (pyosmium, pyproj, shapely, numpy, Pillow, brotli). Write multi-line scripts to a file and run it: shell
  heredocs with quotes can break in the Windows shells.
- Tests: `python -I tools/test_all.py` runs every `tools/test_*.py` the way it must run (`-I` or `-P -E`
  from its imports; `--browser` adds the page tests, `-k name` picks some). A tool's test is
  `tools/test_<tool>.py`: a change to a tool runs it, a new tool gets one. CI
  (`.github/workflows/tests.yml`) runs the tests that need no `data/` or `raw/` and `ruff check tools` on
  every PR; a test that needs them skips without them, saying what to fetch.
- Checks from the command line: `python -P -E tools/headless.py --lines 17 --checks u3,redruns,traffic,lint
  --seeds 1-3` (headless Chromium, its own server; exit code 1 on a failed threshold, the thresholds being
  `judge` in that tool; `--jobs N` pages at once, by default as many as cores and free memory allow). Rebuilds: `python -P -E tools/rebuild.py 17`
  (`--parallel` for several lines).
- **Heavy jobs take turns:** `headless.py`, `rebuild.py` and `frametime.py` queue for the machine
  (`baseline_store.HeavyJob`, first come first served, #280), print whom they wait for, and size their
  pages and builds by the memory free when their turn comes (`tools/sysinfo.py`). Start one in the
  background and let it wait; `TRAM_HEAVY_NOWAIT=1` runs one beside the others (it slows both).
- **Which checks a change needs** (`/regress` picks them from the diff; a change of two kinds runs both):

  | change | runs | leaves out |
  |---|---|---|
  | docs, research, harness | nothing; the PR says so | all |
  | the review page, review cards | `tools/test_review.py` (phone and desktop sizes) | headless |
  | a build tool, its data rebuilt (world) | the tool's test; `--checks lint,surfaces,canted,crossing,spacing,heights` on the rebuilt lines; `tools/datadiff.py` or `tools/track_moves.py` per line; a smoke drive per line (`--checks u3 --seeds 1`: it reaches the last stop, not stuck) | redruns, traffic, seeds 2–5 |
  | drawn geometry in the game (surfaces, track beds, crossings, kerbs) | `lint,surfaces,crossing,canted`; every seedless move needs a reason | seeded checks |
  | drawing or load that keeps the world (models, materials, load cuts) | screenshots main vs branch, `tools/frametime.py`; for a load cut, the world after load compared with main's | seeded checks |
  | the simulation (`traffic.js`, `autopilot.js`, `tram.js`, `tr37.js`, `electric.js`, the game's rules) | `u3,redruns,traffic,lint` on all lines, seeds 1–5, `--compare`; the tram or the autopilot: also `stops`, `tools/test_traction.py`, `tools/test_electric.py`, `tools/test_drives.py` | the geometry checks |
  | track heights (`tools/line_heights.py`, the profile) | also `heights` | |
  | a world checkpoint (W1, W2 …, ROADMAP.md) | every check on every line once; its moves explained in its PR | |

  Seeded traffic checks on a world change measure traffic reshuffled by the new data (#156) and say
  little about the change, so they run at the checkpoints (the user, 2026-11-05: "build up the static
  world … without regression checks at every step where they don't make sense yet (like traffic behavior
  because of shifting terrain)").
- Tests that drive a page set a time limit for the whole test (`faulthandler.dump_traceback_later`, as
  `tools/test_review.py`): Playwright's `page.evaluate` has none, and a promise that never resolves
  hangs the run without output.
- Checks in a page: `tools/lint.js` on a page loaded with `?keepgeo` (`lint()`, `lint({ traffic: true })` averages
  seeds 22, 7, 1234), regressions through `headless.py --compare`; benches in `tools/bench/`
  (u3, redruns, walkers; `batch.html`). Run long browser jobs unawaited and poll (script calls time out
  at 45 s); a background window throttles frames, so no fps readings then.
- **Long jobs pin their checkout** (a rebuild, a fetch, a check run reads the files as they are): work on
  another issue meanwhile in its own worktree (`git worktree add ../<repo>-N -b N-name origin/main`, then
  `python -I tools/snapshot.py data-fetch`, from the machine cache in seconds), removed when done.
- Dev switches: `?line=N`, `?inspect`, `?review` (findings on the map, DEVELOPING.md), `?bot`, `?keepgeo`, `?nofine`, `?nospread`, `?notunnels`, `?boxpeople` (the box figures instead of the pedestrian models, #251), `?profile=<name>` (a trial height profile from `reports/review/profiles/`, to drive and compare, #358), `?seed=N&at=S` (the traffic check's run of seed N, replayed up to route s and handed over paused: a stuck scene as it was, #157).
- A regression check compares a run with main's stored baseline (`headless.py … --compare`, seeds 1-5 by
  default, the table goes into the PR). Seeded counts are judged by the branch's mean against the min-max
  of main's seeds: a change to the tram's timing reshuffles traffic like a new seed (#156), so moves inside
  the spread are listed as noise. Stuck, unfinished and penalty runs are listed per seed and need a reason,
  as does every move of the seedless checks (lint, surfaces) and every mean outside the spread. The table
  also lists places new and gone (#157). Main's baseline is measured at night by the deploy PC after a
  merge that changes the game, the checks, the data or `data/truth.json` (`tools/autodeploy.py`, 2 pages at
  once, not while a heavy job runs) and published to the data store; `--compare` takes the one of the branch's merge base. A PR does not
  refresh the baseline.
- **Which baseline each tier compares with** (#282): a checkpoint's run stores itself under its name
  (`--baseline --publish --checkpoint W1`: every check, seeds 1-5). Seedless checks (the world and drawn-geometry tiers)
  compare with main at the merge base: its baseline, else measured there once in a pinned worktree through the
  queue and kept on this machine by its key. Seeded checks (the simulation tier) compare with main's at the merge
  base when the night has measured it, else with the latest checkpoint; `--against W1` names one.

## Known failures (not caused by your change; remove a row when its issue closes)

| check | line | symptom | issue |
|---|---|---|---|
| page load | lines without them | console 404s for optional sidecars (`line9.dtm.json`, `.signals`) | (expected) |
| crossing | 17 | 1 unexplained pedestrian obstruction | #146 |
| crossing | 9 | 2 unexplained pedestrian obstructions: a surveyed sidewalk 0.40 m over the rails at s 3672 (since its survey, #125) | #146 |
| `tools/test_audio_pause.py` `test_shift_lifecycle` | 23 | the master gain is 0 after the shift starts (wants over 0.01) | #381 |
| `tools/test_headless_timeout.py` `test_stuck_and_scheduled_wait` | (its own page) | `KeyError: 'stuck'` in both modes | #381 |

## Code style

- Don't reformat code you are not changing (no formatter over whole files: #119's reflow buried its
  changes). Match the surrounding code: plain modules, short names in hot loops, comments that say why (the data
  quirk, the measured case), not what. Units are metres, seconds, m/s unless named otherwise.
- Docs say what is and what was measured, briefly: no disclaimers or hedges, no restating.
- No new dependencies or build steps without an issue that decides it. Tests and benches: Python +
  Playwright (headless Chromium); Node / Deno only once the simulation core is split out.
- Randomness must be reproducible: today the benches override `Math.random` with a seeded one; new
  simulation code takes its randomness from one place so a seeded RNG per run can replace it.
