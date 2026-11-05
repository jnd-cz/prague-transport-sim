"""Who works where, what clashes, what waits: the work in flight from git, GitHub and the heavy-job queue (#280).

    python -I tools/board.py               # the board
    python -I tools/board.py --questions   # only what the open PRs ask the user
    python -I tools/board.py --json        # the same, as JSON (for a page or another agent)
    python -I tools/board.py --no-fetch    # without fetching origin first

A row is a branch with a worktree or an open PR. Flags:
  gone      its PR merged or closed: the worktree can go (after a look at its dirty files)
  missing   the worktree's folder is gone (git worktree prune)
  stale     nothing committed or edited for 24 h
  conflict  GitHub cannot merge the PR into main
  recheck   main changed the branch's own files (or the data under it) since it branched: its checks
            ran against other code
  rebuilds  it changes a build step of tools/rebuild.py, data/MANIFEST.json or the snapshot: one such
            branch rebuilds and publishes at a time, the one whose issue holds the `rebuild` label
  asks      its PR has questions for the user
  parked    its issue or PR is labelled `parked`: out of the clashes and the lane counts
  ready     its PR is ready and waits for the user's merge
Clashes are pairs of rows that change the same files, or that both rebuild data. Lanes are the issues'
`lane:*` labels, with a limit of sessions each (LIMITS), counted over the rows a session works on now. Ready to start: open issues of a lane with no
agent, not parked or waiting for the user, whose blockers (GitHub's blocked-by links) are all closed.
Changes nothing but the remote refs the fetch updates.
"""
import argparse
import ast
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)
import baseline_store  # noqa: E402  (the heavy-job queue: headless.py, rebuild.py, frametime.py)

STALE = 24 * 3600
# a rebuild besides the build tools: new data or a new snapshot. data/truth.json is not here: most of its
# edits need no rebuild, and two branches editing it clash as a shared file anyway.
DATA_INPUTS = ("data/MANIFEST.json", "snapshots/")
ASKS = re.compile(r"^(#+\s*|\*\*)(open questions|questions|for the user|to decide|the user decides)", re.I)
# sessions at once per lane (AGENTS.md, Lanes): the world lane's second writes tools without publishing
LIMITS = {"world": 2, "sim": 1, "assets": 1, "tooling": 1}
REBUILD = "rebuild"  # the label: the one issue whose branch may rebuild and publish data


def git(*a, cwd=ROOT, strip=True):
    r = subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True, encoding="utf-8")
    return (r.stdout.strip() if strip else r.stdout) if r.returncode == 0 else None


def gh(*a):
    try:
        r = subprocess.run(["gh", *a], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    except OSError:
        return None
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout else None


def labels(issue):
    return {lb["name"] for lb in (issue or {}).get("labels", [])}


def lane(issue):
    ls = sorted(n[5:] for n in labels(issue) if n.startswith("lane:"))
    return ls[0] if ls else None


def build_tools(tools=TOOLS):
    """tools/ files a rebuild runs: rebuild.py's steps and what they import from tools/, transitively.
    Read from rebuild.py, so a new step counts without a list here."""
    src = open(os.path.join(tools, "rebuild.py"), encoding="utf-8").read()
    todo = {"rebuild.py", *re.findall(r'"(\w+\.py)"', src)}
    seen = set()
    while todo:
        n = todo.pop()
        p = os.path.join(tools, n)
        if n in seen or not os.path.exists(p):
            continue
        seen.add(n)
        try:
            tree = ast.parse(open(p, encoding="utf-8").read(), p)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module] if isinstance(node, ast.ImportFrom) and node.module and not node.level else []
            todo.update(f"{m.split('.')[0]}.py" for m in names)
    return {f"tools/{n}" for n in seen if not n.startswith("test_")}


def rebuilds(files, tools):
    return sorted(f for f in files if f in tools or f.startswith(DATA_INPUTS))


def kind(f):
    """A file's part of the project, for the row's summary and the clash's weight."""
    if f.endswith(".md"):
        return "docs"
    if f.startswith("src/") or f == "index.html":
        return "game"
    if f.startswith(("tools/bench/", "tools/lint.js", "tools/traffic_lint.js", "tools/headless.py")):
        return "checks"
    if f.startswith("reports/review/"):
        return "review"
    if f.startswith(("data/", "snapshots/")):
        return "data"
    return "tools"


def questions(body, width=160):
    """The question sections of a PR description: [(heading, [first line of each item])], each item cut at
    width characters (None: whole, for the review directory, tools/review_sets.py)."""
    out, cur, level = [], None, 0
    for line in (body or "").splitlines():
        h = re.match(r"^(#+)\s", line)
        if cur is not None and h and len(h.group(1)) <= level:
            cur = None
        if ASKS.match(line.strip()):
            level = len(h.group(1)) if h else 9
            cur = []
            out.append((line.strip("#* ").strip(), cur))
            continue
        if cur is not None:
            m = re.match(r"^(?:[-*]|\d+\.)\s+(.*)", line)  # top-level items only: their sub-points stay out
            if m:
                cur.append(m.group(1).strip()[:width] if width else m.group(1).strip())
    return [(t, items) for t, items in out if items]


def branch_issue(branch):
    m = re.match(r"(\d+)-", branch or "")
    return int(m.group(1)) if m else None


def rebuild_label(branch=None):
    """(this branch's issue, whether it holds the rebuild label, the open issues holding it); holds is
    None when GitHub cannot be asked."""
    issue = branch_issue(branch or git("branch", "--show-current"))
    held = gh("issue", "list", "--state", "open", "--label", REBUILD, "--json", "number")
    if held is None:
        return issue, None, []
    holders = sorted(i["number"] for i in held)
    return issue, issue in holders, holders


def check_rebuild_label(what, warn_only=False, branch=None, out=None):
    """Refuse `what` (a data-publish) unless this branch's issue holds the rebuild label: one branch
    rebuilds and publishes at a time (#280). warn_only: say so and go on (a local rebuild)."""
    out = out or sys.stderr
    issue, holds, holders = rebuild_label(branch)
    if holds is None:
        print(f"note: GitHub not reachable: the `{REBUILD}` label was not checked", file=out)
        return
    if holds:
        return
    by = f"held by {', '.join(f'#{n}' for n in holders)}" if holders else "nobody holds it"
    msg = (f"{what}: this branch's issue ({f'#{issue}' if issue else 'none'}) does not hold the `{REBUILD}` label"
           f" ({by}). One branch rebuilds and publishes at a time (AGENTS.md, #280): take the label with"
           f" `gh issue edit N --add-label {REBUILD}` once nobody holds it.")
    if warn_only:
        print(f"note: {msg} A local rebuild is fine; publishing it needs the label.", file=out)
        return
    raise SystemExit(f"{msg} Or pass --without-rebuild-label with a --note saying why.")


def worktrees():
    out, cur = [], None
    for line in (git("worktree", "list", "--porcelain") or "").splitlines():
        k, _, v = line.partition(" ")
        if k == "worktree":
            cur = {"path": os.path.normpath(v), "branch": None, "head": None, "missing": False}
            out.append(cur)
        elif k == "HEAD" and cur:
            cur["head"] = v
        elif k == "branch" and cur:
            cur["branch"] = v.removeprefix("refs/heads/")
        elif k == "prunable" and cur:
            cur["missing"] = True
    for w in out:
        w["missing"] = w["missing"] or not os.path.isdir(w["path"])
    return out


def touched(path):
    """Newest edit in a worktree: its dirty files' times (what a session is doing before it commits)."""
    st = git("status", "--porcelain", cwd=path, strip=False)  # (a strip would cut the first line's " M")
    if st is None:
        return [], 0
    files = [ln[3:].strip().strip('"') for ln in st.splitlines() if ln]
    t = 0
    for f in files:
        try:
            t = max(t, os.path.getmtime(os.path.join(path, f.split(" -> ")[-1])))
        except OSError:
            pass
    return files, t


def fetch_github():
    with ThreadPoolExecutor(3) as ex:  # (each gh call takes seconds)
        return list(ex.map(lambda a: gh(*a), [
            ("pr", "list", "--state", "open", "--limit", "100", "--json",
             "number,title,headRefName,isDraft,mergeable,updatedAt,body,labels"),
            ("pr", "list", "--state", "all", "--limit", "300", "--json", "number,headRefName,state"),
            ("issue", "list", "--state", "open", "--limit", "400", "--json", "number,title,labels,blockedBy")]))


def rows(prs_open, prs_all, issues, now=None):
    now = now or time.time()
    main = "origin/main"
    tools = build_tools()
    by_issue = {i["number"]: i for i in issues or []}
    last_pr = {}
    for p in reversed(prs_all or []):  # newest first from gh: the reversed walk leaves the newest
        last_pr[p["headRefName"]] = p
    open_pr = {p["headRefName"]: p for p in prs_open or []}

    wts = worktrees()
    seen, out = set(), []
    for w in wts:
        out.append({"worktree": w["path"], "branch": w["branch"], "head": w["head"], "missing": w["missing"]})
        seen.add(w["branch"])
    for b in open_pr:
        if b not in seen:
            out.append({"worktree": None, "branch": b, "head": None, "missing": False})

    for r in out:
        b = r["branch"]
        ref = (b if git("rev-parse", "--verify", "--quiet", b) else f"origin/{b}") if b else r["head"]
        r["issue"] = branch_issue(b)
        iss = by_issue.get(r["issue"])
        r["issueTitle"] = iss["title"] if iss else None
        r["agents"] = sorted(n[6:] for n in labels(iss) if n.startswith("agent:"))
        r["lane"] = lane(iss)
        r["label"] = REBUILD in labels(iss)
        pr = open_pr.get(b) or last_pr.get(b)
        r["pr"] = pr and {"number": pr["number"], "state": pr.get("state", "OPEN"), "draft": pr.get("isDraft"),
                          "mergeable": pr.get("mergeable"), "title": pr.get("title"),
                          "updated": pr.get("updatedAt")}
        r["asks"] = questions(open_pr[b]["body"]) if b in open_pr else []
        base = git("merge-base", main, ref)
        files = (git("diff", "--name-only", f"{base}..{ref}") or "").split() if base else []
        main_files = set((git("diff", "--name-only", f"{base}..{main}") or "").split()) if base else set()
        lr = (git("rev-list", "--left-right", "--count", f"{main}...{ref}") or "0 0").split()
        r["behind"], r["ahead"] = int(lr[0]), int(lr[1])
        r["files"] = files
        r["rebuilds"] = rebuilds(files, tools)
        recheck = set(files) & main_files
        if "data/MANIFEST.json" in main_files and any(kind(f) in ("game", "checks") or f in tools for f in files):
            recheck.add("data/MANIFEST.json")  # main published new data under the branch's checks
        r["recheck"] = sorted(recheck)
        ct = int(git("log", "-1", "--format=%ct", ref) or 0)
        dirty, t = touched(r["worktree"]) if r["worktree"] and not r["missing"] else ([], 0)
        r["dirty"] = dirty
        r["touched"] = max(ct, t)
        r["main"] = bool(wts) and os.path.normcase(r["worktree"] or "") == os.path.normcase(wts[0]["path"])
        fl = []
        if r["missing"]:
            fl.append("missing")
        if r["pr"] and r["pr"]["state"] in ("MERGED", "CLOSED") and b not in open_pr:
            fl.append("gone")
        if now - r["touched"] > STALE and "gone" not in fl:
            fl.append("stale")
        if r["pr"] and r["pr"]["mergeable"] == "CONFLICTING":
            fl.append("conflict")
        if r["recheck"] and "gone" not in fl:
            fl.append("recheck")
        if r["rebuilds"] and "gone" not in fl:
            fl.append("rebuilds")
        if r["asks"]:
            fl.append("asks")
        if "parked" in labels(iss) or "parked" in labels(open_pr.get(b)):
            fl.append("parked")
        if b in open_pr and not open_pr[b].get("isDraft"):
            fl.append("ready")  # (waits for the user's merge: no session works on it)
        r["flags"] = fl
    return out


def live(r, now):
    """A row a session works on now: edited within STALE, not finished, parked or waiting for its merge."""
    return not {"gone", "missing", "stale", "parked", "ready"} & set(r["flags"]) and now - r["touched"] <= STALE


def clashes(rs):
    """Pairs of rows in flight changing the same files, and pairs that both rebuild data."""
    act = [r for r in rs if not {"gone", "missing", "parked"} & set(r["flags"]) and r["files"]]
    out = []
    for i, a in enumerate(act):
        for b in act[i + 1:]:
            shared = sorted(set(a["files"]) & set(b["files"]))
            hard = [f for f in shared if kind(f) != "docs"]
            if a["rebuilds"] and b["rebuilds"]:
                out.append({"kind": "data", "a": a, "b": b, "files": hard,
                            "why": "both rebuild data: one rebuilds and publishes, the other rebases on it"})
            elif hard:
                out.append({"kind": "code", "a": a, "b": b, "files": hard, "why": ""})
            elif shared:
                out.append({"kind": "docs", "a": a, "b": b, "files": shared, "why": ""})
    order = {"data": 0, "code": 1, "docs": 2}
    return sorted(out, key=lambda c: order[c["kind"]])


def lanes(rs, now):
    """{lane: live rows} and the lanes over their limit."""
    by = {}
    for r in rs:
        if r["lane"] and live(r, now):
            by.setdefault(r["lane"], []).append(r)
    over = {k: v for k, v in by.items() if len(v) > LIMITS.get(k, 1)}
    return by, over


def ready(issues, rs, per_lane=6):
    """{lane: [issues]} open, with no agent and not parked or waiting for the user, every blocker closed,
    and no branch of their own yet."""
    busy = {r["issue"] for r in rs if r["issue"]}
    out = {}
    for i in sorted(issues or [], key=lambda i: i["number"]):
        ls = labels(i)
        if not lane(i) or any(n.startswith("agent:") for n in ls) or {"parked", "needs-user"} & ls or i["number"] in busy:
            continue
        if any(b.get("state") != "CLOSED" for b in (i.get("blockedBy") or {}).get("nodes", [])):
            continue
        out.setdefault(lane(i), []).append(i)
    return {k: v[:per_lane] for k, v in out.items()}


def ago(t, now):
    if not t:
        return "-"
    s = now - t
    return f"{s / 60:.0f} min" if s < 3600 else f"{s / 3600:.0f} h" if s < 172800 else f"{s / 86400:.0f} d"


def name(r):
    return f"#{r['issue']}" if r["issue"] else (r["branch"] or f"@{(r['head'] or '')[:7]}")


def summary(files):
    c = {}
    for f in files:
        c[kind(f)] = c.get(kind(f), 0) + 1
    return " ".join(f"{k} {n}" for k, n in sorted(c.items(), key=lambda kv: -kv[1]))


def show(rs, issues, jobs, now):
    head = git("log", "-1", "--format=%h %s", "origin/main") or "?"
    print(f"origin/main {head[:90]}")
    print("Heavy jobs: " + ("; ".join(baseline_store.describe(j, now) for j in jobs) if jobs else "none"))
    holders = [i["number"] for i in issues or [] if REBUILD in labels(i)]
    print(f"Rebuild label: {', '.join(f'#{n}' for n in holders) if holders else 'nobody'}"
          + ("  (more than one: only one branch may publish)" if len(holders) > 1 else ""))
    print()
    print(f"{'':6} {'branch':28} {'PR':12} {'lane':8} {'agent':7} {'worktree':22} {'touched':>7} {'+/-main':>8}  files / flags")
    for r in sorted(rs, key=lambda r: ("gone" in r["flags"] or "missing" in r["flags"], -r["touched"])):
        pr = r["pr"]
        p = "-" if not pr else f"#{pr['number']} " + ("draft" if pr["draft"] and pr["state"] == "OPEN" else pr["state"].lower())
        wt = os.path.basename(r["worktree"]) + (" (MAIN)" if r["main"] else "") if r["worktree"] else "(remote only)"
        print(f"{name(r):6} {(r['branch'] or 'detached')[:28]:28} {p:12} {r['lane'] or '-':8} {','.join(r['agents']) or '-':7} "
              f"{wt[:22]:22} {ago(r['touched'], now):>7} {r['ahead']:>3}/{r['behind']:<4}  {summary(r['files'])}")
        extra = []
        if r["flags"]:
            extra.append(" ".join(r["flags"]) + (" (holds the label)" if r["label"] and "rebuilds" in r["flags"] else ""))
        if r["dirty"]:
            extra.append(f"{len(r['dirty'])} dirty ({', '.join(r['dirty'][:2])}{', …' if len(r['dirty']) > 2 else ''})")
        if r["recheck"] and "gone" not in r["flags"]:
            extra.append("main changed: " + ", ".join(os.path.basename(f) for f in r["recheck"][:4])
                         + (" …" if len(r["recheck"]) > 4 else ""))
        if extra:
            print(f"{'':6} └ " + "; ".join(extra))
    if any(r["main"] and r["branch"] not in (None, "main") for r in rs):
        b = next(r["branch"] for r in rs if r["main"])
        print(f"\nThe main checkout is on {b}: it should stay on main (AGENTS.md); a session works in its own worktree.")
    cl = clashes(rs)
    print("\nClashes" + ("" if cl else ": none"))
    for c in cl:
        f = ", ".join(c["files"][:5]) + (" …" if len(c["files"]) > 5 else "")
        print(f"  {c['kind']:5} {name(c['a'])} {c['a']['branch']} × {name(c['b'])} {c['b']['branch']}"
              + (f": {c['why']}" if c["why"] else "") + (f" [{f}]" if f else ""))
    by, over = lanes(rs, now)
    print("\nLanes (live rows / limit): " + ", ".join(f"{k} {len(by.get(k, []))}/{n}" for k, n in LIMITS.items()))
    for k, v in over.items():
        print(f"  over the limit: {k}: {', '.join(name(r) for r in v)}")
    rd = ready(issues, rs)
    print("\nReady to start (no agent, blockers closed)" + ("" if rd else ": none with a lane label"))
    for k in LIMITS:
        for i in rd.get(k, []):
            print(f"  {k:8} #{i['number']} {i['title'][:90]}")
    show_questions(rs)


def show_questions(rs):
    asks = [r for r in rs if r["asks"]]
    print("\nWaiting for the user" + ("" if asks else ": nothing in the open PRs"))
    for r in asks:
        print(f"  PR #{r['pr']['number']} ({name(r)}) {r['pr']['title'][:80]}")
        for title, items in r["asks"]:
            print(f"    {title}: {len(items)}")
            for it in items:
                print(f"      - {it}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--questions", action="store_true", help="only the open PRs' questions for the user")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-fetch", action="store_true")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    now = time.time()
    if not a.no_fetch:
        git("fetch", "--quiet", "origin")
    prs_open, prs_all, issues = fetch_github()
    if issues is None:
        print("note: GitHub not reachable: rows from git only", file=sys.stderr)
    rs = rows(prs_open, prs_all, issues, now)
    jobs = baseline_store.queue()
    if a.json:
        cl = [{**c, "a": c["a"]["branch"], "b": c["b"]["branch"]} for c in clashes(rs)]
        rd = {k: [i["number"] for i in v] for k, v in ready(issues, rs).items()}
        print(json.dumps({"rows": rs, "clashes": cl, "heavy": jobs, "ready": rd,
                          "rebuildLabel": [i["number"] for i in issues or [] if REBUILD in labels(i)]},
                         ensure_ascii=False, indent=1))
    elif a.questions:
        show_questions(rs)
    else:
        show(rs, issues, jobs, now)


if __name__ == "__main__":
    main()
