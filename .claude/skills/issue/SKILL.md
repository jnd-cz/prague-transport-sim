---
name: issue
description: Start work on a GitHub issue of this repo the same way every session - check the setup, read the issue, look at the board for clashes, create its worktree and branch and state the plan with its checks. Use when the user says /issue N, "work on #N", "start issue N" or "pick up #N".
argument-hint: <issue number>
---

# Start issue #$ARGUMENTS

AGENTS.md holds the rules (start-of-session checklist, lanes, conventions, known failures). This skill
runs them in order; read AGENTS.md first if it is not in context yet.

1. **Setup**, in one go, reporting only what is wrong:
   - In the main checkout: `git pull --ff-only` on `main`. If the main checkout is on another branch or
     has changes, leave it as it is (another session may work there) and say so.
   - `python --version` must be 3.12 or newer (otherwise say so and stop: `-P` and the build tools need it).
2. **The board:** `python -I tools/board.py`. Note the heavy-job queue, the holder of the `rebuild` label,
   the lanes over their limit and every branch that touches the files this issue will touch. A clash is
   settled before the work starts: wait for that branch, branch from it, or tell the user and suggest
   another issue. The issue's lane (`lane:*` label) must have room and not be paused (the
   board's `PAUSED`, AGENTS.md Lanes) unless the user says otherwise.
3. **The issue:** `gh issue view $ARGUMENTS --comments`. Note its Now / Where / Done when / Checks. If it
   lacks one of them, work it out from the code and say what you assumed. Check its blocked-by links
   (an open blocker means it is not ready: say so) and the known failures table in AGENTS.md, so you
   know which failures are not yours.
4. **Worktree and branch:** `python -I tools/session.py start $ARGUMENTS` (`--name two-or-three-words` when the
   name it takes from the title says little; `--fetch-raw` if the issue needs a rebuild). It makes
   `../<repo>-$ARGUMENTS` on its branch from `origin/main`, sets the author email, fetches the built data from the
   machine cache and labels the issue `agent:claude`. Give the issue its lane label if it has none.
5. **Plan:** say in a few lines what you will change (files, the rule, not a spot fix), and which checks
   prove it: the issue's Checks and the tier of the change (`python -I tools/tiers.py`),
   with `/regress` before the PR. If the issue changes built data, the plan ends with rebuild, the checks,
   `data-publish` and the manifest commit on the branch, which needs the `rebuild` label: take it if
   nobody holds it, or say whom it waits for.

Then start the work. Ask the user only for decisions the issue leaves open, not about the setup.

On the user's word to merge: `python -I tools/session.py merge $ARGUMENTS` (it lists the worktree's changed and
untracked files first and stops until they have been looked at, then merges the PR as `<PR title> (#PR)` and removes
the worktree, the branch and the label; `finish $ARGUMENTS` for a PR merged another way).
