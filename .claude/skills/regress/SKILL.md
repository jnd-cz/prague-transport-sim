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
2. **Lines** (unless given: $ARGUMENTS):
   - `src/`, `index.html`, `tools/lint.js`, `tools/traffic_lint.js`, `tools/bench/`, `tools/autopilot.js`:
     all lines, 9,17,22,23,37 (they change every line's numbers).
   - rebuilt data: the lines whose files changed in the manifest (or in `data/` against it).
   - a build tool only, data not rebuilt yet: rebuild first (`python -P -E tools/rebuild.py <lines>
     --parallel`), then the changed lines.
   - docs or harness only: no run needed; say so.
3. **Run** (in the background; about 10 minutes for all lines with 4 pages at once):
   `python -P -E tools/headless.py --lines <lines> --checks u3,redruns,traffic,lint --seeds 1 --compare`
   Add the seeds the issue names (traffic varies by seed; a moved traffic count is worth a second seed).
4. **Read the result:**
   - A stale-baseline warning: main moved since its baseline. Say so, and read the differences as main's
     changes plus the branch's.
   - Known failures in AGENTS.md (line 9 u3 stuck at 14355, #80) are not regressions.
   - Every count that moved needs a reason tied to the change (e.g. "roads changed at the corridor
     edge"). A **worse** mark without one is a regression: report it, don't paper over it.
5. **For the PR:** the table from `reports/headless/compare.md`, the reasons, and for rebuilt data what
   changed per line. When the numbers moved for good reasons, and code and data are committed and
   published, rerun with `--baseline` instead of `--compare` and commit `reports/baseline/headless.json`
   on the branch, so main's baseline is current after the merge.
