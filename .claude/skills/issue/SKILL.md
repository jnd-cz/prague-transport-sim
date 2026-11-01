---
name: issue
description: Start work on a GitHub issue of this repo the same way every session - check the setup, read the issue, create its branch and state the plan with its checks. Use when the user says /issue N, "work on #N", "start issue N" or "pick up #N".
argument-hint: <issue number>
---

# Start issue #$ARGUMENTS

AGENTS.md holds the rules (start-of-session checklist, conventions, known failures). This skill runs
them in order; read AGENTS.md first if it is not in context yet.

1. **Setup**, in one go, reporting only what is wrong:
   - `git status --short` must be clean; if not, stop and ask what to do with the changes.
   - `git checkout main && git pull --ff-only`
   - `python --version` must be 3.12 or newer (otherwise say so and stop: `-P` and the build tools need it).
   - `python -I tools/snapshot.py status`; if `data/` differs from the manifest, run
     `python -I tools/snapshot.py data-fetch`. If the issue needs a rebuild and `raw/` differs, also
     `python -I tools/snapshot.py fetch` (about 2.5 GB the first time; run it in the background).
2. **The issue:** `gh issue view $ARGUMENTS --comments`. Note its Now / Where / Done when / Checks (the
   issue template). If it lacks one of them, work it out from the code and say what you assumed.
   Check the linked issues and the known failures table in AGENTS.md, so you know which failures are
   not yours. Check who else works nearby: `gh issue list --label agent:codex` and the open PRs
   (`gh pr list`; `gh pr diff N --name-only` for the files they touch). Say if one overlaps.
   Long jobs running in this checkout pin it: then work in a worktree (AGENTS.md).
3. **Branch:** `git checkout -b $ARGUMENTS-<two or three words from the title, kebab-case>`; set
   `git config user.email "2506000+jnd-cz@users.noreply.github.com"` if it is not set in this clone.
   Label the issue: `gh issue edit $ARGUMENTS --add-label agent:claude`.
4. **Plan:** say in a few lines what you will change (files, the rule, not a spot fix), and which checks
   prove it: the issue's Checks, plus `/regress` before the PR. If the issue changes built data, the plan
   ends with rebuild, `/regress`, `data-publish` and the manifest commit on the branch (AGENTS.md).

Then start the work. Ask the user only for decisions the issue leaves open, not about the setup.
