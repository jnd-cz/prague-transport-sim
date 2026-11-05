# Housekeeping

Two reviews keep the repository manageable as it grows (#290; the user, 2026-11-05: "where and when to
put architecture analysis … so that the projects stay manageable as it grows"). Both only report and
propose. A change goes through an issue and the user's word, like any other.

| review | when | what it looks at | where its result goes |
|---|---|---|---|
| **Weekly pass** | Mondays 06:30 (scheduled task on the PC), or `/housekeeping` | the work in flight, leftovers, sizes and their change | a comment on the pinned [#291](https://github.com/jnd-cz/prague-transport-sim/issues/291): the report, then the proposed actions, numbered |
| **Architecture review** | at each world checkpoint (W1, W2 …, ROADMAP.md) and before a new milestone starts; `/housekeeping checkpoint` | structure, hotspots, refactor targets | a decision record in `docs/decisions/` per structural change decided, an issue per refactor (lane, blocked-by), linked on #291 and the checkpoint's PR |

A checkpoint is where structural changes are cheapest: no rebuild is in flight, and the next layer's work
starts from the new baseline anyway.

## The weekly pass

1. `python -I tools/board.py` and `python -I tools/repo_health.py --since 291`. The report lists:
   - the sizes and their change since the last pass;
   - the work in flight: PRs, issues per lane, half-done issues, parked, waiting for the user;
   - review sets whose issue is closed;
   - leftover worktrees and branches;
   - known failures whose issue is closed;
   - dated issues;
   - CI times.
2. Turn what it shows into proposals, one line each, which someone can act on:
   - a draft idle over 48 h: close it, or label it `parked` with what is left (AGENTS.md, Merge windows);
   - ready PRs: the list for the merge window;
   - a half-done issue: does it still hold only its own points? Split or close it;
   - issues without a lane; a lane over its session limit (the board);
   - a review set whose issue is closed while findings wait: delete it (`reviews.html` has the counts; AGENTS.md);
   - a worktree of finished work, a remote branch of a merged or closed PR: delete it, after a look at its
     untracked files (they go to `worktree-leftovers/` beside the checkouts);
   - a known-failure row whose issue is closed: remove it, or name its new issue;
   - a dated issue whose day has come: who takes it;
   - a file that grew over 15 % in a week, or passed 2000 lines: noted for the next architecture review;
   - CI's median over 2 minutes, or runs that failed.
3. Post: `python -I tools/repo_health.py --post 291`, then one comment with the proposals, numbered, so
   the user answers by number. The pass changes nothing itself.

## The architecture review

At a checkpoint, from `repo_health.py`'s numbers and the code:

- **Hotspots:**
  - the largest modules;
  - the files most branches touched since the last checkpoint
    (`git log --since=<last checkpoint> --name-only --format= | sort | uniq -c | sort -rn | head`);
  - the clashes the board reported.

  Is a split due, and does an issue already plan it? The simulation core's split is M5's (#226, #227, #228).
- **Structure:** does each folder hold one kind of thing (`src/`, `tools/`, `tools/bench/`, `reports/`,
  `docs/`)? Look for files that belong together but sit apart, and for a file doing two jobs. `tools/` is flat
  by design, since every documented command names `tools/x.py`: group it in an index rather than by moving
  files.
- **One rule, one place:** a rule implemented twice drifts. Two cases: the track profile and cant in the
  page and in a build tool (#276), and a finding's identity in JavaScript and Python.
- **Data flow:** a tool that reads another's output without `tools/rebuild.py` knowing the order, or a
  sidecar no build step writes.
- **Dead code:** unused exports, and tools that no doc, test or other tool runs.
- **Docs:** are they true now? `docs/knowledge.md`'s growth (one fact, one place), decisions the code has
  left, and `docs/architecture.md` against the code.
- **Checks:** the time per check tier, a check that never fails or always fails, and a known failure older
  than a checkpoint.

The result is proposals, as in the weekly pass, with the measurements that support them. What the user
accepts becomes issues and decision records.
