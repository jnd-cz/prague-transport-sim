---
name: regress
description: Regression check of the current branch against main's stored baseline - pick the lines and checks from what the branch changed, run tools/headless.py --compare, and write the check table for the PR. Use when the user says /regress, "run the checks", "regression check" or before opening a PR in this repo.
argument-hint: "[lines, e.g. 9,23] (default: chosen from the diff)"
---

# Regression check

Compares this branch with main's baseline instead of rerunning the published data. Which one, by what
each run has (`tools/headless.py`, #282, #709): main's at the merge base (published at night, or this machine's own);
else the run is measured at the merge base once, in a pinned worktree in the heavy-job queue, and kept on
this machine for the next branch on that base (seedless: a few minutes a line; seeded: as long as the branch's own
run). `--against W1` names a checkpoint instead.

1. **What changed and what it runs:** `python -I tools/tiers.py` reads the branch's files against origin/main
   (uncommitted ones too) and prints each kind of change, the files that make it so, and the commands, the
   lines from the manifest (a world change: the lines whose files the manifest changed; none rebuilt yet: all,
   rebuilt first). The table is in it, once (#727). A file in no row is listed: choose its row by hand. Lines
   given ($ARGUMENTS) replace the lines it chose.
2. **Why each row runs what it does:** the simulation's seeded checks (`stops` rides on the `u3` drive, #708); a
   world change runs no traffic or redruns, which measure traffic reshuffled by the new data (#156), and its smoke
   drive only has to reach the last stop unstuck (its counts are not compared).
3. **Run** in the background. Heavy jobs take turns (AGENTS.md): the run waits its turn and says whom it
   waits for, so start it and let it wait rather than starting a second one beside it. Every check on
   every line takes 27 minutes with 4 pages at once (#205), the geometry checks a few minutes a line.
   `python -P -E tools/headless.py --lines <lines> --checks <the tier's checks> --compare`
   Seeded counts are judged against main's spread over
   its seeds (#156); fewer seeds (`--seeds 1-2`) still compare against the full spread, only less surely.
4. **Read the result:**
   - A stale-baseline warning: main moved since its baseline. Say so, and read the differences as main's
     changes plus the branch's.
   - A note that seeded runs compare with a checkpoint, "not with main" (measuring at the merge base was left out
     or gave nothing): read no move from them; run it again so that it measures there, and say so in the PR.
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
