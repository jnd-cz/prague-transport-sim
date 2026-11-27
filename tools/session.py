# SPDX-License-Identifier: AGPL-3.0-or-later
"""An issue's session, started and finished the same way every time (#727; AGENTS.md, Start):

    python -I tools/session.py start N [--name short-name] [--agent claude|codex] [--fetch-raw]
    python -I tools/session.py merge N [--discard]      # on the maintainer's word only (AGENTS.md, Merge windows)
    python -I tools/session.py finish N [--discard]

start: the issue's worktree beside the main checkout (../<repo>-N) on a new branch N-<short-name> from origin/main
(the name from the issue's title unless given), the repository's author email in it, the built data from the machine
cache (and raw/ with --fetch-raw, for a build), the issue labelled agent:<agent>. It refuses where the branch or the
folder exists. Then it says what to read next.

merge: the issue's open PR marked ready and squash-merged as `<PR title> (#PR)`, then the session finished and the
remote branch deleted. It refuses, with nothing changed, while another PR stands on the branch, the PR is not
mergeable, a check of its has not passed, or the worktree holds changed or untracked files (listed; --discard after
you have looked).

finish (for a PR merged another way): once the branch's PR is merged, the worktree, the local branch and the agent's label go. It refuses while
the PR is not merged, and while the worktree holds changed or untracked files: it lists them, and --discard removes
the worktree with them after you have looked.
"""
import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMAIL = "2506000+jnd-cz@users.noreply.github.com"
SMALL = {"a", "an", "the", "of", "to", "in", "on", "at", "by", "for", "from", "with", "and", "or", "its", "is", "as", "not", "no"}


def run(*cmd, cwd=ROOT, check=True):
    """(stdout, return code) of a command; a failure of a checked one ends the tool with its message."""
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode:
        raise SystemExit(f"session: {' '.join(cmd[:4])} failed: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip(), r.returncode


def slug(title, words=3):
    """A branch's short name from an issue's title: its first few words that say something, in kebab-case."""
    said = lambda text: [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in SMALL]  # noqa: E731
    ws = said(re.split(r"[:(]", title, maxsplit=1)[0])
    if len(ws) < 2:  # (a one-word area before the colon, "Checks: ...": the words after it too)
        ws = said(title)
    return "-".join(ws[:words]) or "work"


def folder(n, root=ROOT):
    return os.path.join(os.path.dirname(root), f"{os.path.basename(root)}-{n}")


def branch_of(n, run=run):
    """The local branch of issue n (N-...), or None."""
    out, _ = run("git", "branch", "--list", f"{n}-*", "--format=%(refname:short)")
    names = [b for b in out.splitlines() if b.strip()]
    return names[0] if names else None


def start(n, name=None, agent="claude", raw=False, run=run, out=print):
    issue = json.loads(run("gh", "issue", "view", str(n), "--json", "title,state,labels")[0])
    if issue["state"] != "OPEN":
        raise SystemExit(f"session: issue #{n} is {issue['state'].lower()}")
    branch, wt = f"{n}-{name or slug(issue['title'])}", folder(n)
    if os.path.exists(wt):
        raise SystemExit(f"session: {wt} exists (a session of #{n} may be at work: python -I tools/board.py)")
    if have := branch_of(n, run):
        raise SystemExit(f"session: the branch {have} exists: finish it, or work in a worktree of it")
    run("git", "fetch", "-q", "origin", "main")
    run("git", "worktree", "add", "-q", wt, "-b", branch, "origin/main")
    run("git", "config", "user.email", EMAIL, cwd=wt)
    run(sys.executable, "-I", "tools/snapshot.py", "data-fetch", cwd=wt)
    if raw:
        run(sys.executable, "-I", "tools/snapshot.py", "fetch", cwd=wt)
    run("gh", "issue", "edit", str(n), "--add-label", f"agent:{agent}")
    lanes = [x["name"] for x in issue["labels"] if x["name"].startswith("lane:")]
    out(f"#{n} {issue['title']}\n  worktree {wt}\n  branch   {branch} ({', '.join(lanes) or 'no lane label'})\n"
        f"  next: python -I tools/board.py (clashes, the queue, the lane's room), gh issue view {n} --comments")
    return wt, branch


def prs_of(n, branch, run=run):
    """The pull requests of issue n's branch: by its name, or, with the local branch gone (the merge deleted it: #748
    and #749 left their sessions so), those whose branch is N-..."""
    if branch:
        return json.loads(run("gh", "pr", "list", "--head", branch, "--state", "all", "--json", "number,state")[0] or "[]")
    every = json.loads(run("gh", "pr", "list", "--state", "all", "--limit", "200", "--json", "number,state,headRefName")[0] or "[]")
    return [p for p in every if (p.get("headRefName") or "").startswith(f"{n}-")]


def finish(n, discard=False, run=run, out=print):
    wt, branch = folder(n), branch_of(n, run)
    prs = prs_of(n, branch, run)
    if not any(p["state"] == "MERGED" for p in prs) or any(p["state"] == "OPEN" for p in prs):
        raise SystemExit(f"session: {branch or f'#{n} (no local branch)'} has no merged PR or an open one "
                         f"({prs or 'none'}): nothing is removed")
    gone = []
    if os.path.isdir(wt):
        dirty, _ = run("git", "status", "--short", cwd=wt)
        if dirty and not discard:
            raise SystemExit(f"session: {wt} holds changed or untracked files; look at them, then --discard:\n{dirty}")
        run("git", "worktree", "remove", "--force", wt)
        gone.append(wt)
    if branch:
        run("git", "branch", "-D", branch)
        gone.append(branch)
    issue = json.loads(run("gh", "issue", "view", str(n), "--json", "labels")[0])
    for lab in [x["name"] for x in issue["labels"] if x["name"].startswith("agent:")]:
        run("gh", "issue", "edit", str(n), "--remove-label", lab)
    out(f"#{n}: {' and '.join(gone) + ' removed' if gone else 'its worktree and branch were gone already'}, the agent's label taken off")


PASSED = {"SUCCESS", "SKIPPED", "NEUTRAL"}


def merge(n, discard=False, run=run, out=print):
    """The issue's open PR squash-merged as `<PR title> (#PR)` and the session finished. Everything is checked before
    anything changes: one open PR of the branch, none standing on it, mergeable, its checks passed, the worktree's
    changed and untracked files looked at. gh's own --delete-branch is not used: it removes the worktree with its
    untracked files at once (#751 and #752, gh 2.103.3)."""
    wt, branch = folder(n), branch_of(n, run)
    if not branch:
        raise SystemExit(f"session: no local branch of #{n}")
    prs = json.loads(run("gh", "pr", "list", "--head", branch, "--state", "open", "--json",
                         "number,title,isDraft,mergeable,statusCheckRollup")[0] or "[]")
    if len(prs) != 1:
        raise SystemExit(f"session: {branch} has {len(prs)} open PRs, not one: nothing is merged")
    pr = prs[0]
    stacked = json.loads(run("gh", "pr", "list", "--base", branch, "--state", "open", "--json", "number")[0] or "[]")
    if stacked:
        raise SystemExit(f"session: {', '.join('#' + str(p['number']) for p in stacked)} stand on {branch}: move them to main "
                         f"first (gh pr edit N --base main); a PR whose base branch is deleted is closed for good (#745)")
    if pr.get("mergeable") != "MERGEABLE":
        raise SystemExit(f"session: PR #{pr['number']} is {str(pr.get('mergeable')).lower()}: merge main into {branch} first")
    waiting = [c.get("name") or c.get("context") or "?" for c in pr.get("statusCheckRollup") or []
               if (c.get("conclusion") or c.get("state")) not in PASSED]
    if waiting:
        raise SystemExit(f"session: PR #{pr['number']}'s checks have not passed: {', '.join(waiting)}")
    if os.path.isdir(wt):
        dirty, _ = run("git", "status", "--short", cwd=wt)
        if dirty and not discard:
            raise SystemExit(f"session: {wt} holds changed or untracked files; look at them, then --discard:\n{dirty}")
    if pr.get("isDraft"):
        run("gh", "pr", "ready", str(pr["number"]))
    run("gh", "pr", "merge", str(pr["number"]), "--squash", "--subject", f"{pr['title']} (#{pr['number']})")
    out(f"PR #{pr['number']} merged as \"{pr['title']} (#{pr['number']})\"")
    finish(n, discard=True, run=run, out=out)  # (its files were looked at above)
    run("git", "push", "-q", "origin", "--delete", branch, check=False)  # (gone already where GitHub deletes merged branches)
    run("git", "pull", "-q", "--ff-only", check=False)  # (the main checkout, where it is on main and clean)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("issue", type=int)
    s.add_argument("--name", help="the branch's short name (default: from the issue's title)")
    s.add_argument("--agent", default="claude", choices=("claude", "codex"))
    s.add_argument("--fetch-raw", action="store_true", help="also raw/ (snapshot.py fetch), for a build")
    f = sub.add_parser("finish")
    f.add_argument("issue", type=int)
    f.add_argument("--discard", action="store_true", help="remove the worktree with its changed and untracked files")
    m = sub.add_parser("merge")
    m.add_argument("issue", type=int)
    m.add_argument("--discard", action="store_true", help="merge and remove the worktree with its changed and untracked files")
    a = ap.parse_args(argv)
    if a.cmd == "start":
        start(a.issue, a.name, a.agent, a.fetch_raw)
    elif a.cmd == "merge":
        merge(a.issue, a.discard)
    else:
        finish(a.issue, a.discard)
    return 0


if __name__ == "__main__":
    # (an issue's title in Czech: a cp1252 console stopped start 697 at its last line, "Rašínovo", the work done)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
