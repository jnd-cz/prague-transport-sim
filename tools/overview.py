# SPDX-License-Identifier: AGPL-3.0-or-later
"""The project's overview for the test site (#826): what waits for the user, the heavy queue with its expected times,
the agents' sessions and the board, as overview.json, which overview.html shows at phone width.

    python -I tools/overview.py --print          # the snapshot to stdout, nothing written or uploaded
    python -P -E tools/overview.py               # writes overview.json in the checkout, uploads it when it changed
    python -I tools/overview.py --install [MIN]  # a scheduled task: every MIN minutes (default 5), with pythonw
    python -I tools/overview.py --uninstall

The snapshot:
- the board: tools/board.py's rows, clashes, lanes, the `rebuild` label and the issues ready to start;
- sessions: every agent's session log changed in the last 48 h (LOGS), with its last activity and the folder it works
  in, mapped to its worktree, issue and PR. Only the `cwd` field is read from a log, from its end (the logs reach
  hundreds of MB); no message text, title or prompt;
- waiting for the user: the open PRs' questions, the issues labelled `needs-user`, the PRs ready for a merge window
  (the review sets with their unanswered counts the page reads live, as reviews.html does);
- the heavy queue: each job with its expected time and estimated start and finish (baseline_store.schedule), the
  machine's free memory and cores, and the jobs a watch ended in the last day.

The upload goes to the test target of deploy.local.json only (never a public one), over tools/deploy.py's FTPS
connection, when the snapshot changed or HEARTBEAT s after the last one (the page turns red after 15 min without
one). tools/deploy.py never deletes overview.json (KEPT). A failed login is not tried again for RETRY s: the host bans
repeated failed logins. Its own task, every 5 min (the user, 2026-11-23: "I would pick every 5 minutes"), not a step
of tools/autodeploy.py's: that one runs every 10 min and waits for a deploy or a data fetch. It never waits for the heavy queue (it is no heavy job). Log and state:
reports/overview.log, reports/overview-state.json, reports/overview-cache.json (git-ignored).
"""
import argparse
import datetime
import ftplib
import glob
import hashlib
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import baseline_store  # noqa: E402
import board  # noqa: E402
import sysinfo  # noqa: E402

OUT = os.path.join(ROOT, "overview.json")  # (git-ignored; tools/serve.py serves it for the page)
NAME = "overview.json"  # (on the host, beside overview.html)
LOG = os.path.join(ROOT, "reports", "overview.log")
STATE = os.path.join(ROOT, "reports", "overview-state.json")
CACHE = os.path.join(ROOT, "reports", "overview-cache.json")  # (board.rows' git answers by commit)
TASK = "tram-overview"
REPO = "jnd-cz/prague-transport-sim"
RECENT = 48 * 3600  # (sessions whose log changed within this)
ENDS = 24 * 3600  # (jobs a watch ended within this)
# (s: an unchanged snapshot goes up again after this, so the page's age says the PC is on: every second run of 5 min,
# also when the task fires a little early; the page stays under ~11 min old, red past 15)
HEARTBEAT = 540
RETRY = 3600  # (s after a failed login)
FETCH = 600  # (s between git fetches: the remote branches' diffs)
READY = 10  # (ready issues listed per lane)
# where each agent keeps its session logs, under the home folder; one JSON object a line, the folder it works in as
# "cwd" (Claude Code: on most entries; Codex: in the first line's and each turn's "payload")
LOGS = [("claude", (".claude", "projects", "*", "*.jsonl")),
        ("codex", (".codex", "sessions", "*", "*", "*", "*.jsonl"))]


def read_log(path, chunk=1 << 16, most=1 << 23):
    """(the last "cwd" a log names, top level or in "payload"; the number of the last PR of this repository its harness
    linked, a "pr-link" entry's prNumber), read from its end in growing chunks up to `most` bytes, the cwd else from
    its first line; None for what it does not name. Only those two fields are read: no text of a message, a title or
    a prompt. (A Claude Code session started in the main checkout logs that folder as its cwd while it works in an
    issue's worktree: its PR says which. The PR number read too on the user's word, 2026-11-23, PR #827: "yes".)"""
    cwd = pr = None

    def look(line):
        nonlocal cwd, pr
        if not (cwd is None and b'"cwd"' in line or pr is None and b'"pr-link"' in line):
            return
        try:
            d = json.loads(line)
        except ValueError:
            return
        if not isinstance(d, dict):
            return
        if cwd is None:
            c = d.get("cwd") if "cwd" in d else (d.get("payload") or {}).get("cwd") if isinstance(d.get("payload"), dict) else None
            cwd = c if isinstance(c, str) and c else None
        if pr is None and d.get("type") == "pr-link" and d.get("prRepository") == REPO and isinstance(d.get("prNumber"), int):
            pr = d["prNumber"]
    try:
        with open(path, "rb") as f:
            size = f.seek(0, 2)
            n = chunk
            while cwd is None or pr is None:
                f.seek(max(0, size - n))
                lines = f.read(min(n, size)).split(b"\n")
                if n < size:
                    lines = lines[1:]  # (cut at the chunk's start)
                for line in reversed(lines):
                    look(line)
                if n >= size or n >= most:
                    break
                n *= 4
            if cwd is None:
                f.seek(0)
                look(f.readline(most))
    except OSError:
        pass
    return cwd, pr


def logs(home=None, now=None, places=None):
    """[(agent, log path, its last change)] of the logs changed within RECENT."""
    home = home or os.path.expanduser("~")
    now = time.time() if now is None else now
    out = []
    for agent, parts in places or LOGS:
        for p in glob.glob(os.path.join(home, *parts)):
            try:
                t = os.path.getmtime(p)
            except OSError:
                continue
            if now - t <= RECENT:
                out.append((agent, p, t))
    return out


def norm(p):
    return os.path.normcase(os.path.normpath(p))


def place(cwd, rows, home, cache):
    """(the folder shown, the board row it works in or None) for a session's cwd; None when the folder is no checkout of
    this repository (another project's session stays out). A worktree of this repository maps to its row; another
    clone (Codex's own) to the row of the branch it has checked out."""
    if cwd in cache:
        return cache[cwd]
    c = norm(cwd)
    best = None
    for r in rows:
        w = r.get("worktree")
        if w and (c == norm(w) or c.startswith(norm(w) + os.sep)) and (not best or len(w) > len(best["worktree"])):
            best = r
    res = None
    if best:
        res = best
    elif os.path.isdir(cwd) and REPO in (board.git("remote", "get-url", "origin", cwd=cwd) or ""):
        b = board.git("branch", "--show-current", cwd=cwd)
        res = next((r for r in rows if b and r.get("branch") == b), None) or {"branch": b, "issue": board.branch_issue(b)}
    if res is None:
        cache[cwd] = None
        return None
    base = os.path.dirname(os.path.dirname(board.ROOT))  # (Claude/transport-game-826: no user name on the page)
    shown = os.path.relpath(cwd, base) if norm(cwd).startswith(norm(base) + os.sep) else os.path.basename(cwd)
    cache[cwd] = (shown.replace(os.sep, "/"), res)
    return cache[cwd]


def sessions(rows, home=None, now=None, places=None, prs=None):
    """The sessions of the last RECENT s, newest first. prs: every PR ({number, headRefName, state}), for a session
    whose PR has no row of its own (merged, its worktree gone)."""
    out, cache = [], {}
    by_pr = {r["pr"]["number"]: r for r in rows if r.get("pr")}
    heads = {p["number"]: p for p in prs or []}
    for agent, p, t in logs(home, now, places):
        cwd, n = read_log(p)
        hit = place(cwd, rows, home, cache) if cwd else None
        if not hit:
            continue
        shown, r = hit
        if n and n in by_pr:
            r = by_pr[n]
        elif n:
            h = heads.get(n) or {}
            r = {"branch": h.get("headRefName"), "issue": board.branch_issue(h.get("headRefName")),
                 "pr": {"number": n, "state": h.get("state"), "draft": None}}
        pr = r.get("pr")
        out.append({"agent": agent, "last": t, "folder": shown, "branch": r.get("branch"), "issue": r.get("issue"),
                    "issueTitle": r.get("issueTitle"), "main": bool(r.get("main")),
                    "pr": pr and {"number": pr["number"], "state": pr["state"], "draft": pr.get("draft")}})
    return sorted(out, key=lambda s: -s["last"])


def row_out(r):
    pr = r.get("pr")
    return {"name": board.name(r), "branch": r["branch"], "issue": r["issue"], "issueTitle": r.get("issueTitle"),
            "pr": pr and {k: pr.get(k) for k in ("number", "state", "draft", "title")}, "lane": r["lane"],
            "agents": r["agents"], "worktree": os.path.basename(r["worktree"]) if r["worktree"] else None,
            "main": r["main"], "touched": r["touched"], "ahead": r["ahead"], "behind": r["behind"],
            "files": board.summary(r["files"]), "flags": r["flags"], "dirty": len(r["dirty"]), "label": r["label"]}


def heavy(now, records=None, jobs=None, free=None):
    jobs = baseline_store.queue() if jobs is None else jobs
    free = sysinfo.available_gb() if free is None else free
    keep = ("what", "root", "pid", "state", "since", "t", "share", "gb", "warn", "kind", "expect", "expectFrom",
            "start", "finish", "late")
    out = []
    for j in baseline_store.schedule(jobs, now, records, free=free):
        j = {k: j.get(k) for k in keep}
        j["root"] = os.path.basename(os.path.normpath(j["root"] or ""))
        out.append(j)
    ends = [{"what": r.get("what"), "root": os.path.basename(os.path.normpath(r.get("root") or "")),
             "end": r.get("t", 0) + r.get("wall", 0), "wall": r.get("wall"), "ended": r.get("ended")}
            for r in baseline_store.recent_ends(now, ENDS, records)]
    return {"jobs": out, "freeGb": free, "cores": baseline_store.HeavyJob.CORES, "keepGb": baseline_store.HeavyJob.KEEP,
            "ended": ends}


def snapshot(now=None, github=None, home=None, places=None, records=None, jobs=None, free=None, cache=None):
    """The overview as a dict. github: (open PRs, all PRs, open issues) as board.fetch_github() gives them; cache:
    board.rows'."""
    now = time.time() if now is None else now
    prs_open, prs_all, issues = github if github is not None else board.fetch_github()
    rs = board.rows(prs_open, prs_all, issues, now, cache=cache)
    by, over = board.lanes(rs, now)
    rd = board.ready(issues, rs)
    head = (board.git("log", "-1", "--format=%H%x00%s%x00%ct", "origin/main") or "\0\0").split("\0")
    lab = board.labels
    return {
        "time": now, "repo": REPO, "github": issues is not None,
        "main": {"commit": head[0], "subject": head[1], "time": int(head[2] or 0)},
        "waiting": {
            "questions": [{"pr": r["pr"]["number"], "title": r["pr"]["title"], "issue": r["issue"],
                           "sections": [{"title": t, "items": items} for t, items in r["asks"]]} for r in rs if r["asks"]],
            "needsUser": [{"number": i["number"], "title": i["title"]} for i in issues or [] if "needs-user" in lab(i)],
            "readyPrs": [{"pr": r["pr"]["number"], "title": r["pr"]["title"], "issue": r["issue"]}
                         for r in rs if "ready" in r["flags"] and r["pr"]],
        },
        "heavy": heavy(now, records, jobs, free),
        "sessions": sessions(rs, home, now, places, prs_all),
        "board": {
            "rows": [row_out(r) for r in sorted(rs, key=lambda r: ("gone" in r["flags"] or "missing" in r["flags"], -r["touched"]))],
            "clashes": [{"kind": c["kind"], "a": board.name(c["a"]), "aBranch": c["a"]["branch"], "b": board.name(c["b"]),
                         "bBranch": c["b"]["branch"], "files": c["files"][:5], "more": max(0, len(c["files"]) - 5),
                         "why": c["why"]} for c in board.clashes(rs)],
            "lanes": [{"lane": k, "limit": n, "live": [board.name(r) for r in by.get(k, [])], "over": k in over,
                       "paused": board.PAUSED.get(k)} for k, n in board.LIMITS.items()],
            "rebuildLabel": [i["number"] for i in issues or [] if board.REBUILD in lab(i)],
            "ready": {k: {"count": len(v), "issues": [{"number": i["number"], "title": i["title"],
                                                        "milestone": (board.milestone(i).split() or ["-"])[0]}
                                                       for i in v[:READY]]} for k, v in rd.items()},
            "claimed": [i["number"] for i in board.claimed(issues, rs)],
        },
    }


def digest(snap):
    """The snapshot's hash without its time: an upload only when something else changed."""
    return hashlib.sha256(json.dumps({k: v for k, v in snap.items() if k != "time"}, sort_keys=True).encode()).hexdigest()


def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE + ".tmp", "w", encoding="utf-8", newline="\n") as f:
        json.dump(st, f, indent=1)
    os.replace(STATE + ".tmp", STATE)


def say(log, text):
    print(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {text}", file=log, flush=True)


def upload(data, key, st, now, log, connect=None, config=None):
    """data (bytes) up to the test target when its key (digest()) changed or HEARTBEAT s went by since the last upload;
    st updated. True when it went up."""
    if st.get("sent") == key and now - st.get("at", 0) < HEARTBEAT:
        return False
    if now - st.get("login_failed_at", 0) < RETRY:
        return False
    import deploy  # (brotli, from the user site packages: python -P -E; --print and the snapshot do without)
    with open(config or deploy.CONFIG, encoding="utf-8") as f:
        cfg = deploy.target(json.load(f), "test")
    if cfg.get("public"):
        raise SystemExit("the overview goes to the test site only: deploy.local.json's top level is a public target")
    try:
        ftp = (connect or deploy.connect)(cfg, deploy.password(cfg))
    except ftplib.error_perm as e:  # (530: the login refused)
        st["login_failed_at"] = now
        say(log, f"login refused ({e}); next try in {RETRY // 60} min")
        return False
    try:
        deploy.upload(ftp, NAME, data, set())
    finally:
        try:
            ftp.quit()
        except (ftplib.Error, OSError):
            pass
    st.pop("login_failed_at", None)
    st.update(sent=key, at=now)
    return True


def once(log, now=None, connect=None, config=None, **snap_args):
    """One run: the snapshot written to OUT and uploaded when it changed; the exit code."""
    now = time.time() if now is None else now
    st = load_state()
    if "github" not in snap_args and now - st.get("fetched", 0) >= FETCH:
        board.git("fetch", "--quiet", "origin")
        st["fetched"] = now
    try:
        with open(CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    snap = snapshot(now, cache=cache, **snap_args)
    with open(CACHE + ".tmp", "w", encoding="utf-8", newline="\n") as f:
        json.dump(cache, f)
    os.replace(CACHE + ".tmp", CACHE)
    data = json.dumps(snap, ensure_ascii=False, indent=0).encode()
    with open(OUT + ".tmp", "wb") as f:
        f.write(data)
    os.replace(OUT + ".tmp", OUT)
    code = 0
    try:
        upload(data, digest(snap), st, now, log, connect, config)
    except (ftplib.Error, OSError) as e:
        say(log, f"upload failed: {type(e).__name__}: {e}")
        code = 1
    save_state(st)
    return code


def install(minutes):
    exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    cmd = f'"{exe}" -P -E "{os.path.abspath(__file__)}"'
    subprocess.run(["schtasks", "/Create", "/F", "/TN", TASK, "/SC", "MINUTE", "/MO", str(minutes), "/TR", cmd],
                   check=True)
    print(f"{TASK}: every {minutes} min, log {LOG}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--print", action="store_true", help="the snapshot to stdout; nothing written or uploaded")
    ap.add_argument("--install", nargs="?", type=int, const=5, metavar="MIN",
                    help="register the scheduled task (every MIN minutes, default 5)")
    ap.add_argument("--uninstall", action="store_true", help="remove the scheduled task")
    a = ap.parse_args(argv)
    if a.install:
        return install(a.install)
    if a.uninstall:
        return subprocess.run(["schtasks", "/Delete", "/F", "/TN", TASK]).returncode
    if a.print:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(json.dumps(snapshot(), ensure_ascii=False, indent=1))
        return 0
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as log:
        try:
            return once(log)
        except Exception as e:  # (a scheduled run has nobody watching: the reason goes to the log)
            say(log, f"{type(e).__name__}: {e}")
            return 1


if __name__ == "__main__":
    sys.exit(main())
