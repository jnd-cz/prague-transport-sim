---
name: housekeeping
description: The repository's housekeeping review - the weekly pass (work in flight, leftovers, sizes, posted on the pinned issue #291) or, with "checkpoint", the architecture review at a world checkpoint. Use when the user says /housekeeping, "weekly pass", "housekeeping", "repository review" or "architecture review", and for the Monday 06:30 scheduled run.
argument-hint: "[weekly|checkpoint] (default: weekly)"
---

# Housekeeping: $ARGUMENTS

`docs/housekeeping.md` holds the checklists; read it first. Both reviews only report and propose: change
nothing in the repository, its branches, issues or PRs, except posting the comments below.

1. **Setup:** in the main checkout, `git pull --ff-only` on `main` (leave it as it is and say so if it is
   on another branch or has changes). No heavy job is needed.
2. **Measure:** `python -I tools/board.py` and `python -I tools/repo_health.py --since 291` (the change
   since the last pass comes from #291's newest report).
3. **Weekly** (the default): go through the weekly checklist in `docs/housekeeping.md` with the report and
   the board, and write the proposals: numbered, one line each, an action with its target ("delete the
   remote branches of 38 merged PRs", "close draft #N, idle 60 h, or park it with what is left"). Skip
   what needs no action.
   **Checkpoint:** go through the architecture checklist as well, with the measurements that support each
   proposal (sizes, how many branches touched a file since the last checkpoint, the clashes).
4. **Post:** `python -I tools/repo_health.py --post 291`, then one comment on #291 with the proposals,
   headed "Proposed actions (answer by number)". On a scheduled run, that is all: nobody is there to ask.
5. **Say** in a few lines what the report found and where it was posted.
