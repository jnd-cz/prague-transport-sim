# Rules for every agent and session (Claude, ChatGPT / Codex, others)

A Tatra T3 tram driving game in a 3D Prague built from real data. Plain ES modules + Three.js, no build
step; Python tools build the world from pinned source snapshots. This file is the rules, kept short. How
things are done, and why a rule exists, is in the files it points to:

| file | holds |
|---|---|
| [ROADMAP.md](ROADMAP.md) | the order of work (the current order: #731) |
| [DEVELOPING.md](DEVELOPING.md) | build, checks, baselines, deploy, dev tools; *Working rules in detail* at its end |
| [DATA.md](DATA.md) | snapshots, the data store, refreshing sources |
| [docs/knowledge.md](docs/knowledge.md) | data quirks and why the heuristics exist: read the sections of what you touch |
| [docs/architecture.md](docs/architecture.md), [docs/decisions/](docs/decisions/) | the target design and the decisions taken |
| [README.md](README.md), [README.en.md](README.en.md) | the player's guide, Czech first |

## Start (one issue per session; `/issue N` does it in Claude Code)

1. **The main checkout stays on `main`.** `python --version` is 3.12 or newer.
2. `python -I tools/board.py`: who works where, the heavy-job queue, the holder of the `rebuild` label, clashes,
   the lanes. A clash with files the issue will touch is settled first: wait for that branch, branch from it, or
   take another issue.
3. `python -I tools/session.py start N` (`--agent codex`; `--fetch-raw` for a build): the issue's own worktree
   `../<repo>-N` on a branch `N-short-name` from `origin/main`, the repository's author email, the built data from
   the machine cache, the agent's label.
4. `gh issue view N --comments`: what is now, where, and when it is done. The known failures (below) are not yours.
5. When its PR merges: `python -I tools/session.py finish N` removes the worktree, the branch and the label. It
   lists changed and untracked files first and stops until they have been looked at.

## What to work on

- **The order:** ROADMAP.md. Until the city's tram world runs (#731): the small fixes, the city data model, one
  tram world built per tile, driving on the track graph, the simulation's core apart from drawing. Scenery (W4)
  and Backlog wait for it.
- **Tasks are GitHub issues** (`jnd-cz/prague-transport-sim`). A new one says what is now (with numbers), where
  in the code, what done means and which checks prove it: a fresh session should need nothing else.
- **Findings** that are not fixed now: on the path, or failing a check or a build, an issue; off the path, a
  comment on the lane's list (#732 world, #733 sim, #734 assets, #735 tooling), picked from at checkpoints.
- **Lanes** (the issues' `lane:*` labels; the board counts live sessions and shows a paused lane):

  | lane | covers | sessions | checks (below) |
  |---|---|---|---|
  | `lane:world` | build tools, `data/`, `truth.json`, the ground and track drawing, review queues | 2: one holds the `rebuild` label, one writes tools and tests without publishing | static |
  | `lane:sim` | traffic, autopilot, tram physics, walkers' behaviour, the game's rules | 1 | seeded |
  | `lane:assets` | models, materials, sound, the interface, frame time | 1 | drawing |
  | `lane:tooling` | checks, board, queue, deploy, CI, docs | 1 | its tests |

- **Order between issues:** GitHub's blocked-by links; the board lists what is ready. A step that reads another
  step's output waits for it: heights, stops and speeds read the track; the ground reads the track and its
  profile; structures and furniture stand on the ground.
- **Fix rules, not spots.** Measure an issue on every line, change the rule that produced it, measure again on
  all lines. A local special case is a fact in `data/truth.json`, not a coordinate in code.
- **Realism over convenience.** Keep the driver's real skills (contacts, coasting, signals). Facts from the user
  (a Prague tram expert) win over heuristics, and each cites where it was said: the quote, and the issue or PR
  comment or the session's date.
- **Calibrate a check before it holds or overrules data:** against an independent source, split by the cases it
  covers. A heuristic standing in for missing data logs what it decided (F8 overlay, `window.game`).

## Branch, PR, merge

- One branch per issue (`<number>-<short-name>`), a PR into `main`. Small doc or data-fact changes may go
  straight to `main`.
- **The PR's text:** `Closes #N.` or `Part of #N.`, what changes and why, a check table (line × check, before →
  after), and for rebuilt data what changed per line. The verdict, the table and any "Questions for the user"
  come first. Pictures go in from the branch by commit SHA (DEVELOPING.md, Pictures in a PR).
- **`Closes #N` only when the PR meets every point of the issue's "Done when".** Anything open (the user's
  answers, an import, a rebuild, a publish, another line) makes it `Part of #N`, and the PR and a comment on the
  issue list what remains. A reviewer who finds an open point changes the keyword before the merge.
- **Merge windows:** the user merges in batches. A PR is marked ready and merged on the user's word only, as a squash titled
  `<PR title> (#PR)` (the title ends with `(#issue)`), the branch deleted. A session whose checks are done says
  so and waits. A draft idle for 48 h is closed or labelled `parked`, saying what is left.
- **Review findings** go in a PR comment ("To fix before merge", "Smaller"); the author answers point by point
  and pushes.
- **Stacked work** branches from the branch it needs and opens its PR with `--base` on it; after the base
  merges, merge main in (no force-push) and rerun the checks.
- **Commits:** what changed and why, with numbers where something was measured.
- **A security hole is not written up in public** (the repository is public; the user, 2026-11-19: "fix and
  file privately"): fix it on a branch under a plain title, and put the details in a draft security advisory
  (`gh api repos/jnd-cz/prague-transport-sim/security-advisories`), not in an issue, a PR or a commit message.

## Questions for the user

- Their attention is the bottleneck: few questions, numbered, each with a recommendation. In a PR they go under
  a "Questions for the user" heading (`board.py --questions` collects them); an issue waiting for answers
  carries `needs-user`.
- **Many places of one kind go to a `?review` findings file** (`reports/review/`, DEVELOPING.md): the place,
  imagery links, a picture where it helps, answer choices. Offer only answers an importer turns into evidence.
  Key an answer by a stable identity (a decision ID, a place), never a generated index. The file names its
  `issue` and `line`. A set whose issue is closed is out of date and is deleted, unless a build reads it
  (`tools/review_sets.py` `READ_BY`).

## Data

- **Never edit generated data by hand** (`data/line*.json` and sidecars): change the tool and rebuild.
- **Hand-made facts go to `data/truth.json`:** from the user or a source, each citing where it came from, keyed
  by place, a stable source ID or a stop, in a section whose reader the file's `readers` names. Not check
  exemptions, audits or generated indexes (a rebuild renumbers them). A fact that overrides a source records
  what the source said (DATA.md, Facts over a source).
- **One rebuild at a time:** only the branch whose issue holds the `rebuild` label rebuilds every line and
  publishes (`python -I tools/snapshot.py data-publish --note "…"`, then commit `data/MANIFEST.json`, then
  merge). Take the label with `gh issue edit N --add-label rebuild` while nobody holds it; it goes when that
  PR merges. Other branches change tools, test them on a local rebuild and wait. `main`'s manifest always names
  data that is in the store; a publish is checked with `snapshot.py verify`.
- **Sources** come only from the pinned snapshot in `raw/` (`snapshot.py fetch`), OSM only from its local
  extract: the public Overpass API is not used. A new source file goes into a snapshot with its URL, licence
  and date, and into `tools/sources.py`. A provider that refuses scripted requests is waited out, never fooled.
- One coordinate conversion for every tool: `tools/geo.py`. Tools write files in `data/` and `raw/` whole
  (`tools/atomic.py`): with a machine cache they are hard links shared by every checkout.

## Running and checking

- **Python:** `python -I` for stdlib-only tools, `python -P -E` for those needing the user site packages
  (DEVELOPING.md lists them). Multi-line scripts go into a file, not a shell heredoc.
- **Ports:** dev server `python tools/serve.py 8742` (Claude; Codex 8743; `headless.py` 8745). Port 8740 may be
  another session's: never use or stop it. A tool or test that needs a page starts its own server on a free port.
- **Tests:** `python -I tools/test_all.py` (`--browser` adds the page tests, `-k name` picks some). A change to a
  tool runs `tools/test_<tool>.py`; a new tool gets one. A test that drives a page sets a time limit for the
  whole test. CI runs the tests that need no data and `ruff check tools`.
- **Heavy jobs take turns:** every job that keeps several cores or GBs busy for over a minute waits for the
  machine's other heavy jobs and holds its turn, so that it does not spoil another's measurement (the user,
  2026-11-12, #516). These take their turn themselves: `headless.py`, `rebuild.py`, `frametime.py`,
  `city_terrain.py`, `ground_mesh.py`; `build_line.py`, `dtm.py`, `line_heights.py`, `import_track_heights.py`,
  `street_profile.py` and `ground_partition.py` when run alone; `test_all.py` for the whole suite. Anything
  else runs through `python -I tools/heavy.py "what" -- CMD ...`. Start one in the background and let it wait;
  never start a second beside it. A timing runs alone (`frametime.py`, a bench, the whole test suite, plain
  `heavy.py`). Count runs and builds (`headless.py`, `rebuild.py`, `ground_mesh.py`, `city_terrain.py`,
  `heavy.py --shared GB,CORES` for pictures and the like) run beside each other while their memory and cores
  fit (the user, 2026-11-19, #728). A wait that ends with "does nothing" names a stuck job: look at that one.
- **A long job pins its checkout:** work on another issue meanwhile in its own worktree.
- **Which checks a change needs** (`/regress` picks them from the diff and has the commands; a change of two
  kinds runs both):

  | change | runs | leaves out |
  |---|---|---|
  | docs, research, harness | nothing; the PR says so | all |
  | the review page, review cards | `tools/test_review.py` (phone and desktop sizes) | headless |
  | a build tool, its data rebuilt (world) | the tool's test; `--checks lint,surfaces,canted,crossing,spacing,heights` on the rebuilt lines; `tools/datadiff.py` or `tools/track_moves.py` per line; a smoke drive per line (`--checks u3 --seeds 1`) | redruns, traffic, seeds 2–5 |
  | drawn geometry in the game (surfaces, track beds, crossings, kerbs) | `lint,surfaces,crossing,canted`; every seedless move needs a reason | seeded checks |
  | drawing or load that keeps the world (models, materials, load cuts) | screenshots main vs branch, `tools/frametime.py`; for a load cut, the world after load compared with main's | seeded checks |
  | the simulation (`traffic.js`, `autopilot.js`, `tram.js`, `tr37.js`, `electric.js`, the game's rules) | `u3,redruns,stops,traffic,lint` on all lines, seeds 1–5, `--compare` (`stops` rides on the `u3` drive); the tram or the autopilot: also `tools/test_traction.py`, `tools/test_electric.py`, `tools/test_drives.py` | the geometry checks |
  | track heights (`tools/line_heights.py`, the profile) | also `heights` | |
  | a world checkpoint (W1, W2 …, ROADMAP.md) | every check on every line once; its moves explained in its PR | |

- **Reading a compare** (DEVELOPING.md, Baselines): seeded counts are judged by the branch's mean against the
  min–max of main's seeds; moves inside it are noise. Every mean outside it, every stuck, unfinished or penalty
  run and every seedless move needs a reason tied to the change. Where main has no baseline at the merge base,
  `--compare` measures the runs there first and keeps them (the first compare on a base takes about twice as
  long). A note that seeded runs compare with a checkpoint means no move is read from them. A PR does not refresh
  the baseline: the deploy PC measures main's at night.
- A measurement worth repeating becomes a check (`tools/bench/`, a `headless.py --checks` entry), not a scratch
  script. Scratch output goes to `reports/` (ignored but for `reports/review/`) or outside the checkout.

## Unattended runs (overnight, Codex /goal, scheduled sessions)

- **Allowed without the user unless the task says otherwise:** push the issue's branch, open and update a draft
  PR, open issues or list comments for findings. **Not allowed:** data-publish, marking a PR ready, merging,
  pushing to main, force-pushing, closing or editing other issues, a `Closes #N` with open points.
- **The progress log is the draft PR,** opened after the first commit: its description holds the current state
  (questions for the user first, then the check table), with a dated comment per step. No log files in the repo.
- A defect outside the issue is fixed on the same branch only when the issue's checks cannot pass without it,
  in its own commits, and the PR says so.
- The run ends with the draft PR saying what is done, what was measured and what the user must decide.

## Known failures (not caused by your change; remove a row when its issue closes)

| check | line | symptom | issue |
|---|---|---|---|
| page load | lines without them | console 404s for optional sidecars (`line9.dtm.json`, `.signals`) | (expected) |

## Code and docs

- Don't reformat code you are not changing. Match the surrounding code: plain modules, short names in hot loops,
  comments that say why (the data quirk, the measured case). Units are metres, seconds, m/s unless named.
- A new source file in `src/` or `tools/` starts with `SPDX-License-Identifier: AGPL-3.0-or-later` in a comment.
- No new dependencies or build steps without an issue that decides it. Tests and benches: Python + Playwright;
  Node / Deno only once the simulation core is split out.
- Randomness is reproducible: simulation code takes it from one seeded place (`src/random.js`), never `Math.random`.
- Text from a package, a player's note or built data is written as text (`textContent`, or escaped), never put
  into `innerHTML` as it is.
- **Docs** say what is and what was measured, briefly: no hedges, no restating. One place per fact: point to a
  table in code instead of copying it. Facts learned about data and code go to `docs/knowledge.md`, decisions to
  `docs/decisions/`, snapshots to `snapshots/README.md`, how a rule came about to DEVELOPING.md.
- A change to `README.md` (Czech, first) changes `README.en.md` too; both are Help in the game's menu.
