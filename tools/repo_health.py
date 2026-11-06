"""The repository's health, for the weekly housekeeping pass (#290, docs/housekeeping.md): sizes, work in
flight, review sets, leftovers, known failures, dated issues, CI. Read-only apart from --post.

    python -I tools/repo_health.py              # Markdown to stdout
    python -I tools/repo_health.py --json       # the numbers as JSON
    python -I tools/repo_health.py --post N     # adds the Markdown as a comment to issue N (the pinned
                                                # housekeeping issue), with the numbers in a hidden block

The change of each size since the last posted pass comes from that hidden block in the issue's newest
comment that has one (--since N reads it without posting).
"""
import argparse
import datetime
import glob
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import board  # noqa: E402  (gh, git, the rows of the work in flight)
import review_sets  # noqa: E402

MARK = "repo-health"  # the hidden block: <!-- repo-health {...} -->
IDLE = 48 * 3600  # s: a draft idle this long is closed or parked (AGENTS.md, Merge windows)
SOON = 7  # days: a dated issue is listed when its date comes within this
# "before 10 Nov 2026", "after 2026-11-18", "until 18 Nov 2026, 23:59": a date an issue waits for
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
# ("from" is left out: "built from 2026-10-30" names a source, not a date to wait for, #26)
DATED = re.compile(r"\b(before|after|until|by)\s+\**(?:(\d{4})-(\d{2})-(\d{2})|(\d{1,2})\.?\s+([A-Za-z]{3})[a-z]*\.?\s+(\d{4}))", re.I)


def lines_of(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def sizes(root=ROOT, top=8):
    """The largest game modules and tools, the docs, and how many tools and tests there are."""
    def biggest(pattern, n):
        files = [(os.path.relpath(p, root).replace(os.sep, "/"), lines_of(p)) for p in glob.glob(os.path.join(root, pattern))]
        return dict(sorted(files, key=lambda kv: -kv[1])[:n])
    tools = [os.path.basename(p) for p in glob.glob(os.path.join(root, "tools", "*.py"))]
    return {
        "src": biggest("src/*.js", top),
        "srcTotal": sum(lines_of(p) for p in glob.glob(os.path.join(root, "src", "*.js"))),
        "tools": biggest("tools/*.py", 6),
        "toolFiles": len([t for t in tools if not t.startswith("test_")]),
        "testFiles": len([t for t in tools if t.startswith("test_")]),
        "docs": {**biggest("*.md", 5), **biggest("docs/*.md", 5)},
    }


def due(text, today):
    """The dates an issue waits for (before / after / until …) that have come or come within SOON days."""
    out = []
    for m in DATED.finditer(text or ""):
        try:
            if m.group(2):
                d = datetime.date(int(m.group(2)), int(m.group(3)), int(m.group(4)))
            else:
                d = datetime.date(int(m.group(7)), MONTHS[m.group(6).lower()[:3]], int(m.group(5)))
        except (KeyError, ValueError):
            continue
        if (d - today).days <= SOON:
            out.append((m.group(1).lower(), d.isoformat()))
    return sorted(set(out), key=lambda x: x[1])


def known_failures(agents_md):
    """The issues named in AGENTS.md's known-failures table: [(row text, issue number)]."""
    rows, inside = [], False
    for line in agents_md.splitlines():
        if line.startswith("## Known failures"):
            inside = True
            continue
        if inside and line.startswith("## "):
            break
        if inside and line.startswith("|") and (m := re.search(r"#(\d+)\s*\|\s*$", line)):
            rows.append((line.split("|")[1].strip() + " / " + line.split("|")[2].strip(), int(m.group(1))))
    return rows


def deltas(now, before):
    """{name: change} for the sizes of now against the last pass's (only what changed)."""
    out = {}
    for group in ("src", "tools", "docs"):
        for k, v in (now.get(group) or {}).items():
            b = (before.get(group) or {}).get(k)
            if b is not None and b != v:
                out[k] = v - b
    for k in ("srcTotal", "toolFiles", "testFiles"):
        if k in before and before[k] != now.get(k):
            out[k] = now[k] - before[k]
    return out


def last_numbers(issue):
    """The hidden block of the issue's newest comment that has one, or {}."""
    comments = board.gh("issue", "view", str(issue), "--json", "comments") or {}
    for c in reversed(comments.get("comments", [])):
        if (m := re.search(r"<!-- " + MARK + r" (\{.*?\}) -->", c.get("body", ""), re.S)):
            try:
                return json.loads(m.group(1))
            except ValueError:
                pass
    return {}


def ci_times():
    runs = board.gh("run", "list", "--limit", "20", "--json", "startedAt,updatedAt,conclusion,event") or []
    secs = []
    for r in runs:
        try:
            a = datetime.datetime.fromisoformat(r["startedAt"].replace("Z", "+00:00"))
            b = datetime.datetime.fromisoformat(r["updatedAt"].replace("Z", "+00:00"))
            secs.append((b - a).total_seconds())
        except (KeyError, ValueError, AttributeError):
            pass
    fails = sum(1 for r in runs if r.get("conclusion") not in ("success", None, ""))
    secs.sort()
    return {"runs": len(secs), "median_s": round(secs[len(secs) // 2]) if secs else None, "max_s": round(max(secs)) if secs else None, "failed": fails}


def finished_on_remote(ls_remote, finished):
    """The branches `git ls-remote --heads` lists whose PR is finished. Asked of the remote: a tracking ref outlives its
    branch until a fetch prunes it (58 such were reported on 2026-11-06, with one branch really there, #346)."""
    heads = [w[len("refs/heads/"):] for w in (ls_remote or "").split() if w.startswith("refs/heads/")]
    return sorted(b for b in heads if b in finished)


def collect(root=ROOT, now=None):
    now = now or time.time()
    today = datetime.date.fromtimestamp(now)
    prs_open, prs_all, issues = board.fetch_github()
    rs = board.rows(prs_open, prs_all, issues, now)
    issues = issues or []
    by_n = {i["number"]: i for i in issues}
    labels = {i["number"]: board.labels(i) for i in issues}
    lanes = {}
    for i in issues:
        lanes[board.lane(i) or "none"] = lanes.get(board.lane(i) or "none", 0) + 1
    prs = []
    for p in prs_open or []:
        upd = datetime.datetime.fromisoformat(p["updatedAt"].replace("Z", "+00:00")).timestamp()
        prs.append({"pr": p["number"], "title": p["title"], "draft": p.get("isDraft"), "idle_h": round((now - upd) / 3600)})
    # half-done: open issues with a merged "Part of #N" PR
    merged = board.gh("pr", "list", "--state", "merged", "--limit", "200", "--json", "number,body,mergedAt") or []
    part_of = {}
    for p in merged:
        for n in re.findall(r"Part of #(\d+)", p.get("body") or ""):
            part_of.setdefault(int(n), []).append(p["number"])
    half = sorted(n for n in part_of if n in by_n)
    # review sets whose issue is closed (out of date if a finding still waits: reviews.html says which)
    sets = review_sets.sets(os.path.join(root, "reports", "review"))
    info = review_sets.issues({s["waitsFor"] for s in sets if s["waitsFor"]})
    closed_sets = [s["file"] for s in sets if (info.get(s["waitsFor"]) or {}).get("state") == "CLOSED"]
    # leftovers: worktrees of finished work, remote branches whose PR is merged or closed
    gone_wt = [os.path.basename(r["worktree"]) for r in rs if r["worktree"] and {"gone", "missing"} & set(r["flags"])]
    stale_wt = [os.path.basename(r["worktree"]) for r in rs if r["worktree"] and "stale" in r["flags"] and not {"gone", "missing"} & set(r["flags"])]
    finished = {p["headRefName"] for p in prs_all or [] if p.get("state") in ("MERGED", "CLOSED")} - {p["headRefName"] for p in prs_open or []}
    leftover_branches = finished_on_remote(board.git("ls-remote", "--heads", "origin", cwd=root), finished)
    with open(os.path.join(root, "AGENTS.md"), encoding="utf-8") as f:
        kf = known_failures(f.read())
    kf_closed = [(row, n) for row, n in kf if n not in by_n]
    dated = []
    for i in board.gh("issue", "list", "--state", "open", "--limit", "400", "--json", "number,title,body") or []:
        for kind, d in due(f"{i['title']}\n{i.get('body') or ''}", today):
            dated.append({"issue": i["number"], "title": i["title"], "when": f"{kind} {d}"})
    return {
        "date": today.isoformat(), "commit": board.git("rev-parse", "--short", "origin/main", cwd=root),
        "sizes": sizes(root),
        "work": {"prs": prs, "issues": len(issues), "lanes": lanes, "halfDone": half,
                 "parked": sum("parked" in labels[n] for n in labels), "needsUser": sum("needs-user" in labels[n] for n in labels),
                 "rebuildLabel": [n for n in labels if board.REBUILD in labels[n]]},
        "reviews": {"sets": len(sets), "findings": sum(s["findings"] for s in sets), "issueClosed": closed_sets},
        "leftovers": {"worktreesDone": gone_wt, "worktreesStale": stale_wt, "branches": leftover_branches},
        "knownFailuresClosed": kf_closed, "dated": dated, "ci": ci_times(),
    }


def markdown(h, before=None):
    d = deltas(h["sizes"], (before or {}).get("sizes") or {}) if before else {}
    ch = lambda k: f" ({d[k]:+d})" if k in d else ""  # noqa: E731
    s, w = h["sizes"], h["work"]
    out = [f"## Housekeeping {h['date']} (main {h['commit']})" + (f", against {before['date']}" if before else ""), ""]
    out += ["**Sizes** (lines): " + ", ".join(f"`{k}` {v}{ch(k)}" for k, v in s["src"].items()) + f"; src total {s['srcTotal']}{ch('srcTotal')}.",
            "Tools: " + ", ".join(f"`{k}` {v}{ch(k)}" for k, v in s["tools"].items())
            + f"; {s['toolFiles']} tools{ch('toolFiles')} and {s['testFiles']} tests{ch('testFiles')} in `tools/`.",
            "Docs: " + ", ".join(f"`{k}` {v}{ch(k)}" for k, v in s["docs"].items()) + ".", ""]
    idle = [p for p in w["prs"] if p["draft"] and p["idle_h"] * 3600 > IDLE]
    ready = [p for p in w["prs"] if not p["draft"]]
    out += [f"**Work:** {w['issues']} open issues (" + ", ".join(f"{k} {v}" for k, v in sorted(w["lanes"].items())) + f"); "
            f"{len(w['prs'])} open PRs, {len(ready)} ready, {len(idle)} drafts idle over 48 h; "
            f"{w['parked']} parked, {w['needsUser']} waiting for the user; rebuild label: "
            + (", ".join(f"#{n}" for n in w["rebuildLabel"]) or "nobody") + "."]
    for p in idle:
        out.append(f"- idle {p['idle_h']} h: #{p['pr']} {p['title']} (close or park)")
    for p in ready:
        out.append(f"- ready for the merge window: #{p['pr']} {p['title']}")
    if w["halfDone"]:
        out.append("- half-done (a merged \"Part of\" PR): " + ", ".join(f"#{n}" for n in w["halfDone"]) + " (does each still hold only its own points?)")
    if (n := w["lanes"].get("none")):
        out.append(f"- {n} issues without a lane")
    out += ["", f"**Review sets:** {h['reviews']['sets']} sets, {h['reviews']['findings']} findings (counts of answers: reviews.html)."]
    for f in h["reviews"]["issueClosed"]:
        out.append(f"- `{f}`: its issue is closed; out of date if a finding still waits (delete it)")
    lo = h["leftovers"]
    if lo["worktreesDone"] or lo["worktreesStale"] or lo["branches"]:
        out += ["", "**Leftovers:**"]
        out += [f"- worktree of finished work: `{x}`" for x in lo["worktreesDone"]]
        out += [f"- worktree idle over 24 h: `{x}`" for x in lo["worktreesStale"]]
        if lo["branches"]:
            out.append("- remote branches of merged or closed PRs: " + ", ".join(f"`{b}`" for b in lo["branches"]))
    if h["knownFailuresClosed"]:
        out += ["", "**Known failures whose issue is closed** (remove the row or find its new issue):"]
        out += [f"- {row} (#{n})" for row, n in h["knownFailuresClosed"]]
    if h["dated"]:
        out += ["", f"**Dated, due within {SOON} days or past:**"]
        out += [f"- #{x['issue']} {x['title']}: {x['when']}" for x in h["dated"]]
    c = h["ci"]
    out += ["", f"**CI:** last {c['runs']} runs, median {c['median_s']} s, longest {c['max_s']} s, {c['failed']} not successful."]
    out += ["", f"<!-- {MARK} {json.dumps({'date': h['date'], 'sizes': h['sizes']}, separators=(',', ':'))} -->"]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--post", type=int, help="add the pass as a comment to this issue")
    ap.add_argument("--since", type=int, help="compare with the last pass posted to this issue (implied by --post)")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    board.git("fetch", "--quiet", "origin")
    h = collect()
    if a.json:
        print(json.dumps(h, ensure_ascii=False, indent=1))
        return
    issue = a.post or a.since
    text = markdown(h, last_numbers(issue) if issue else None)
    if a.post:
        r = subprocess.run(["gh", "issue", "comment", str(a.post), "--body-file", "-"], input=text, text=True,
                           encoding="utf-8", capture_output=True, cwd=ROOT)
        print(r.stdout.strip() or r.stderr.strip())
        sys.exit(r.returncode)
    print(text)


if __name__ == "__main__":
    main()
