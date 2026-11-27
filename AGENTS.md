# Rules for every agent and session (Claude, ChatGPT / Codex, others)

A Tatra T3 tram driving game in a 3D Prague built from real data. Plain ES modules + Three.js, no build
step; Python tools build the world from pinned source snapshots. This file is the rules, kept short. How
things are done, and why a rule exists, is in the files it points to:

| file | holds |
|---|---|
| [ROADMAP.md](ROADMAP.md) | the order of work (the current order: #731) |
| [DEVELOPING.md](DEVELOPING.md) | build, checks, baselines, heavy jobs, deploy, dev tools; *Working rules in detail* at its end |
| [DATA.md](DATA.md) | snapshots, the data store, refreshing sources |
| [docs/knowledge.md](docs/knowledge.md) | data quirks and why the heuristics exist: its index, then the sections of what you touch |
| [docs/architecture.md](docs/architecture.md), [docs/decisions/](docs/decisions/) | the target design and the decisions taken |
| [README.md](README.md), [README.en.md](README.en.md) | the player's guide, Czech first |

## Start (one issue per session; `/issue N` does it in Claude Code)

1. **The main checkout stays on `main`.** `python --version` is 3.12 or newer.
2. `python -I tools/board.py`: who works where, the heavy-job queue, the `rebuild` label, clashes, the lanes. A
   clash with files the issue will touch is settled first: wait for that branch, branch from it, or take another.
3. `python -I tools/session.py start N` (`--agent codex`; `--fetch-raw` for a build): the issue's worktree and branch.
4. `gh issue view N --comments`: what is now, where, and when it is done. The known failures (below) are not yours.
5. On the user's word to merge: `python -I tools/session.py merge N` (it lists the worktree's files first).

## What to work on

- **The order:** ROADMAP.md. Until the city's tram world runs (#731): the fused ground stable on its places (#757),
  the small fixes, the city data model, one tram world per tile, driving on the track graph, the simulation's core
  apart from drawing. Scenery (W4) and Backlog wait for it.
- **Tasks are GitHub issues** (`jnd-cz/prague-transport-sim`). A new one says what is now (with numbers), where
  in the code, what done means and which checks prove it: a fresh session should need nothing else.
- **Findings** not fixed now go on the lane's list as one line (#732 world, #733 sim, #734 assets, #735 tooling).
  One gets an issue of its own only when the roadmap's next step needs it or a check or build fails on it, and
  only after `gh issue list --search "…"` finds none. The user's reports from one place or batch share one issue.
- **Lanes** (the issues' `lane:*` labels; the board counts live sessions):

  | lane | covers | sessions | checks |
  |---|---|---|---|
  | `lane:world` | build tools, `data/`, `truth.json`, the ground and track drawing, review queues | 2: one holds the `rebuild` label, one writes tools and tests without publishing | static |
  | `lane:sim` | traffic, autopilot, tram physics, walkers' behaviour, the game's rules | 1 | seeded |
  | `lane:assets` | models, materials, sound, the interface, frame time | 1 | drawing |
  | `lane:tooling` | checks, board, queue, deploy, CI, docs | 1 | its tests |

- **Order between issues:** GitHub's blocked-by links. A step that reads another step's output waits for it.
- **Fix rules, not spots.** Measure on every line, change the rule that produced it, measure again on all lines. A
  local special case is a fact in `data/truth.json`, not a coordinate in code.
- **Realism over convenience.** Keep the driver's real skills (contacts, coasting, signals). Facts from the
  maintainer (a Prague tram expert) win over heuristics, and each cites where it was said: "(maintainer, #N)", the
  date only when there is no issue or PR. Docs don't quote chat; a short quote only where the words are the evidence.
- **Calibrate a check before it holds or overrules data,** against an independent source, split by its cases. A
  heuristic standing in for missing data logs what it decided (F8 overlay, `window.game`).

## Branch, PR, merge

- One branch per issue (`<number>-<short-name>`), a PR into `main`. Small doc or data-fact changes may go to `main`.
- **The PR's text** starts with the verdict, the check table (line × check, before → after) and any "Questions
  for the user"; for rebuilt data, what changed per line. Pictures by commit SHA (DEVELOPING.md). `Closes #N` only
  when every point of the issue's "Done when" is met; anything open makes it `Part of #N`, and the PR and a comment
  on the issue list what remains. A ground rule's PR closes its issue once its places hold; the rebuild is the
  batch's (#757). CI holds the title and the keyword (`tools/pr_text.py`).
- **Merges** are the user's, in batches, on their word only: `session.py merge N` (squash, the branch and worktree
  removed). A session whose checks are done says so and waits. A draft idle for 48 h is closed or `parked`.
- **Review findings** go in a PR comment; the author answers point by point. **Stacked work** opens its PR with
  `--base` on the branch it needs, and merges main in after the base merges (no force-push).
- **Commits** say what changed and why, with numbers where something was measured.
- **A security hole is not written up in public** (maintainer, 2026-11-19): fix it under a
  plain title; the details go in a draft security advisory, not an issue, a PR or a commit message.

## Questions for the user

- Their attention is the bottleneck: few questions, numbered, each with a recommendation, under "Questions for the
  user" in a PR (`board.py --questions`); an issue waiting for answers carries `needs-user`.
- Many places of one kind go to a `?review` findings file (`reports/review/`, DEVELOPING.md), keyed by a stable
  identity, never a generated index, offering only answers an importer turns into evidence; the file names its
  `issue` and `line`. A set whose issue is closed is deleted unless a build reads it (`tools/review_sets.py` `READ_BY`).

## Data

- **Never edit generated data by hand** (`data/line*.json` and sidecars): change the tool and rebuild.
- **Hand-made facts go to `data/truth.json`,** each citing where it came from, keyed by place, a stable source ID or
  a stop, in a section whose reader `readers` names; a fact over a source records what the source said (DATA.md).
  Not check exemptions, audits or generated indexes.
- **One rebuild at a time:** only the branch whose issue holds the `rebuild` label rebuilds every line and
  publishes (`snapshot.py data-publish`, then commit `data/MANIFEST.json`). Others test on a local rebuild and
  wait. `main`'s manifest always names data that is in the store (`snapshot.py verify`).
- **Ground changes are proven on places, rebuilt in batches** (#757): a ground rule's PR carries the tool, its
  test and the numbers of the locality set and its rules' places (`tiers.py` names them, #865); `--all --rings` and every
  line's rebuild are the batch's, by the holder of `rebuild`.
- **Sources** come only from the pinned snapshot in `raw/` (`snapshot.py fetch`), OSM only from its local extract,
  never the public Overpass API. A new source goes into a snapshot with its URL, licence and date, and into
  `tools/sources.py`. A provider that refuses scripted requests is waited out, never fooled.
- One coordinate conversion: `tools/geo.py`. Tools write files in `data/` and `raw/` whole (`tools/atomic.py`).

## Running and checking

- **Python:** `python -I` for stdlib-only tools, `python -P -E` for those needing the user site packages
  (DEVELOPING.md lists them). Multi-line scripts go into a file, not a shell heredoc.
- **Ports:** dev server `python tools/serve.py 8742` (Claude; Codex 8743); never use or stop 8740. A tool or test
  that needs a page starts its own server on a free port.
- **Tests:** `python -I tools/test_all.py` (`--browser` adds the page tests, `-k name` picks some). A changed tool
  runs its `tools/test_<tool>.py`; a new tool gets one; a test that drives a page has a time limit.
- **Which checks a change needs:** `python -I tools/tiers.py` picks them from the diff (the table is in it); a
  change of two kinds runs both; `/regress` runs them. A world checkpoint (W1, W2 …) runs every check on every line.
- **Heavy jobs take turns** (#516; DEVELOPING.md, Heavy jobs, lists the tools that take
  theirs): anything else heavy runs through `python -I tools/heavy.py "what" -- CMD ...`. Start one in the
  background and let it wait; never run one around the queue. **A batch is queued at its start, its shared steps
  (counts, builds: `--shared GB,CORES`) apart from its alone ones (timings)**, so that they run beside other jobs
  (maintainer, 2026-11-24; DEVELOPING.md, Heavy jobs). **Never start a job detached** (`Start-Process`,
  `start`, `nohup … &`): it ends as orphaned (#815). End a background command with something
  after its last program (`; echo "exit $?"`), so that a stop reaches it.
- **The heaviest work runs at night** (23:00 to 07:00) or on the user's word (maintainer, 2026-11-21; from 23:00 since 2026-11-23): a rebuild of
  every line, a seeded compare of every line, a checkpoint's run. By day: the place loop, tests, one-line runs. The
  queue holds it to that (#851): by day a job expected over 30 min, or of unknown time (`--expect` states it), waits
  for 23:00 and holds no one up; the user's word runs it by day (`heavy.py --day`, `TRAM_HEAVY_DAY=1`) or starts
  the night early for every held job (`heavy.py --night`). Jobs of 10 min or less go first.
- **A long job pins its checkout:** work on another issue meanwhile in its own worktree.
- **Reading a compare** (DEVELOPING.md, Baselines): every mean outside main's seed spread, every stuck, unfinished
  or penalty run and every seedless move needs a reason tied to the change.
- A measurement worth repeating becomes a check (`tools/bench/`, a `headless.py --checks` entry). Scratch output
  goes to `reports/` or outside the checkout.

## Unattended runs (overnight, Codex /goal, scheduled sessions)

- **Allowed without the user unless the task says otherwise:** push the issue's branch, open and update a draft
  PR, open issues or list comments for findings. **Not allowed:** data-publish, marking a PR ready, merging,
  pushing to main, force-pushing, closing or editing other issues, a `Closes #N` with open points.
- **The progress log is the draft PR:** its description holds the current state (questions first, then the check
  table), with a dated comment per step; no log files in the repo. A defect outside the issue is fixed on the same
  branch only when the issue's checks cannot pass without it, in its own commits. The run ends with the draft PR
  saying what is done, what was measured and what the user must decide.

## Known failures (not caused by your change; remove a row when its issue closes)

| check | line | symptom | issue |
|---|---|---|---|
| stops, load10 | 9 seed 2; 17 `load10` seed 5 | one brake-to-drive change with nothing in front, 1.7 m before the stop point (Klamovka s 6087; Strossmayerovo náměstí s 16329) | #756 |
| page load | lines without them | console 404s for optional sidecars (`line9.dtm.json`, `.signals`) | (expected) |

## Code and docs

- Don't reformat code you are not changing. Match the surrounding code: plain modules, short names in hot loops,
  comments that say why. Units are metres, seconds, m/s unless named. A new file in `src/` or `tools/` starts
  with `SPDX-License-Identifier: AGPL-3.0-or-later` (`tools/test_pr_text.py`).
- No new dependencies or build steps without an issue that decides it; tests and benches are Python + Playwright
  (Node / Deno once the simulation core is split out). Randomness in the simulation comes from
  `src/random.js`, never `Math.random`. Text from a package, a player's note or built data is written as text,
  never into `innerHTML` as it is.
- **Docs** say what is and what was measured, briefly, one place per fact (point to a table in code, don't copy it):
  facts about data and code in
  `docs/knowledge.md`, decisions in `docs/decisions/`, how a rule came about in DEVELOPING.md. A change to
  `README.md` (Czech, first) changes `README.en.md` too.
