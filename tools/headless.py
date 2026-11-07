"""Headless checks from the command line (issue #2): the in-page benches and lints in headless Chromium.

    python -P -E tools/headless.py --lines 17,23 --checks u3,redruns --seeds 1-3
    python -P -E tools/headless.py --lines 23 --checks traffic --seeds 22,7,1234
    python -P -E tools/headless.py --lines 17 --checks lint            # static lints (no seed)
    python -P -E tools/headless.py --lines 9,17,22,23,37 --checks u3,lint --jobs 4   # 4 pages at once
    python -P -E tools/headless.py --lines 9,17,22,23,37 --checks canted             # rail/bed visibility
    python -P -E tools/headless.py --lines 9,17,22,23,37 --checks crossing           # pedestrian surfaces over rails
    python -P -E tools/headless.py --lines 17 --checks heights   # top of rail against the staged heights, junctions (#197)

Each run gets a fresh page (`/?line=N&keepgeo`), waits for the loading screen to finish, imports the
check and awaits it, exactly like tools/bench/batch.html. Results: one JSON per run in reports/headless/
and a table; the exit code is 1 when a run fails its thresholds (HARD below: u3 no red entries,
collisions, stuck tram or signal penalty; redruns no red runs; traffic must finish; lint has no
thresholds, `--compare` shows its moves).

Needs Playwright (`python -m pip install --user playwright`, `python -m playwright install chromium`).
Starts its own tools/serve.py on --port (0 picks a free port) and verifies its launch identity before
any job; an occupied port fails. --url explicitly uses an existing server. WebGL runs on
SwiftShader (software): slower than a desktop browser, the same results (the checks step the
simulation themselves). --batch N (default 6) runs up to N checks of one line one after another in one
loaded page, starting a new shift for each: the load (~60 s) once per batch instead of once per run, the
counts the same as in fresh pages (#205: all 21 of line 17's runs, run by run). --jobs N runs N pages
at once, each in a worker process with its own browser (default: half the cores, at most 4, and what free
memory holds at ~4 GB a page: line 17 measured 4.1 GB): every run is seeded, so the counts are the same as
one after another.

Baseline (#89): `--baseline` stores each run's key counts in reports/baseline/headless.json (this machine's,
ignored by git; --publish puts them in the data store), with what they were measured on (the git trees of the game, the in-page checks, the data manifest and
data/truth.json: MEASURED; the data files must match the manifest and those paths be committed). `--compare`
prints baseline -> now per run as a table for the PR (reports/headless/compare.md) and warns when the
baseline was not measured on the code, data and facts of main (the merge base). Main's baseline is
measured at night (tools/autodeploy.py), not by PRs:

    python -P -E tools/headless.py --lines 9,17,22,23,37 --checks u3,redruns,traffic,lint,surfaces --compare

What --compare reads (#282): --against NAME that checkpoint's run. Otherwise, per run, main's baseline of the merge
base, committed or published; where there is none, a seeded run takes the latest world checkpoint's, and a seedless
run is measured on demand at the merge base in a pinned worktree (--no-measure-base leaves it out) and kept on this
machine by its key for the next branch on the same base. A checkpoint is stored by
`--baseline --publish --checkpoint W1`; a name other than W<n> is a test's: stored under that name only, since a
partial run under the key would stop the nightly measurement of main.

The full run (all lines, all checks, seeds 1-5) takes ~27 min at 4 pages (2026-11-04, #205; ~2 h before).

Seed spread (#156): a change to the tram's timing reshuffles traffic like a new seed (#151 moved walkerHit
+54 % on one seed and -33 % on another). So --baseline and --compare run seeds 1-5 by default, and a
count is judged by the branch's mean over its seeds against the min-max of main's stored seeds; inside
it, the move is listed as noise. Problems that must stay at zero (stuck, collisions, red entries,
signal penalties, a traffic run that does not finish) are compared per seed as before.
"""
import argparse
import json
import multiprocessing
import os
import queue
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ProcessPoolExecutor

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves it out)
from sysinfo import workers  # noqa: E402
import baseline_store  # noqa: E402
from baseline_store import MEASURED, HeavyJob  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

# the page-side call per check; `seed` is substituted (static lints take none)
CALLS = {
    "u3": "const { run } = await import('/tools/bench/u3.js'); return await run(SEED);",
    "redruns": "const { run } = await import('/tools/bench/redruns.js'); return await run(SEED);",
    # u3 and redruns drive the same trip with the same seed: one drive, both watchers (#205), reported as both
    "drive": "const { run } = await import('/tools/bench/u3.js'); const { redrunsWatch } = await import('/tools/bench/redruns.js');"
             "const r = await run(SEED, { also: [redrunsWatch] }); const red = r.also[0]; delete r.also; return { u3: r, redruns: red };",
    "stops": "const { run } = await import('/tools/bench/stops.js'); return await run(SEED);",
    "autumn": "const { run } = await import('/tools/bench/stops.js'); return await run(SEED, { weather: 'leaves', full: true });",
    "traffic": "const { trafficRun } = await import('/tools/traffic_lint.js'); return await trafficRun({ seed: SEED });",
    "lint": "document.getElementById('btnStart').click(); await new Promise((r) => setTimeout(r, 2000));"
            "const { lint } = await import('/tools/lint.js'); return await lint({ save: false });",
    "canted": "document.getElementById('btnStart').click(); await new Promise((r) => setTimeout(r, 2000));"
              "const { cantedRailVisibility } = await import('/tools/lint.js'); "
              "return { checks: { cantedRailVisibility: cantedRailVisibility(window.game, window.world) } };",
    "crossing": "document.getElementById('btnStart').click(); await new Promise((r) => setTimeout(r, 2000));"
                "const { run } = await import('/tools/bench/crossingSlab.js'); return run();",
    "surfaces": "document.getElementById('btnStart').click(); await new Promise((r) => setTimeout(r, 2000));"
                "const { run } = await import('/tools/bench/surfaces.js'); return await run();",
    "spacing": "document.getElementById('btnStart').click(); await new Promise((r) => setTimeout(r, 2000));"
               "const { run } = await import('/tools/bench/spacing.js'); return run();",
    "heights": "document.getElementById('btnStart').click(); await new Promise((r) => setTimeout(r, 2000));"
               "const { run } = await import('/tools/bench/heights.js'); return run();",
}
SEEDLESS = {"lint", "surfaces", "canted", "crossing", "spacing", "heights"}


def judge(check, r):
    """(ok, one-line summary): the checks' thresholds are here; tools/bench/batch.html shows them in a page."""
    if "error" in r:
        return False, r["error"][:300]
    bad = []
    if check == "u3":
        if (r.get("carsIntoJunctions") or {}).get("red"):
            bad.append(f"{r['carsIntoJunctions']['red']} red entries")
        if r.get("hits"):
            bad.append(f"{r['hits']} collisions at {', '.join(str(round(c['s'])) for c in r.get('collisions') or [])}")
        if r.get("stuck") is not None:
            bad.append(f"stuck at {round(r['stuck'])}")
        if r.get("signalPenalty"):
            bad.append(f"signal penalty {r['signalPenalty']}")
        more = f"yielded {r.get('yielded')}, cut-ins {r.get('closeCuts')}, junctions {r.get('carsIntoJunctions')}"
    elif check == "redruns":
        if r.get("stuck") is not None:
            bad.append(f"stuck at {round(r['stuck'])}")
        if r.get("redRuns"):
            bad.append(f"{r['redRuns']} oncoming red runs ({r.get('avoidable')} avoidable)")
        if r.get("aheadRedRuns"):
            bad.append(f"{r['aheadRedRuns']} ahead red runs")
        if r.get("ourSignalPenalty"):
            bad.append(f"our signal penalty {r['ourSignalPenalty']}")
        more = f"warn passes {r.get('warnPasses')}, holds {r.get('holds')}"
    elif check in ("stops", "autumn"):
        # (#351: once braking for a stop the autopilot does not go back to the drive pedal, unless what is in
        # front of it changed; the user, 2026-11-06: "without any jums to jízda unless you're following tram in front of you")
        if r.get("stuck") is not None:
            bad.append(f"stuck at {round(r['stuck'])}")
        if r.get("flipsFree"):
            bad.append(f"{r['flipsFree']} brake-to-drive flips with nothing in front")
        if r.get("over"):
            bad.append(f"{r['over']} stops overrun by more than 3 m")
        if r.get("short"):
            bad.append(f"{r['short']} stops more than 3 m short")
        if r.get("hits"):
            bad.append(f"{r['hits']} collisions")
        if r.get("signalPenalty"):
            bad.append(f"signal penalty {r['signalPenalty']}")
        more = (f"{r.get('stops')} stops, flips short/ahead/signal/car/contact {r.get('flipsShort')}/{r.get('flipsAhead')}/{r.get('flipsSignal')}/{r.get('flipsCar')}/{r.get('flipsContact')}, pulses {r.get('pulses')}, "
                f"shoes at speed {r.get('shoesAtSpeed')}, decel {r.get('maxDecel')}, jerk {r.get('maxJerk')}, err p90 {r.get('errP90')} max {r.get('errMax')}, comfort {r.get('comfort')}, pedal/km {r.get('pedalChangesPerKm')}, "
                f"late {r.get('late')}, dev mean {r.get('devMean')} s, over 3 min {r.get('lateStops')}, presses {r.get('presses')} ({r.get('pressesRolling')} rolling), brakes {r.get('brakeApplies')}"
                + (f", slip {r.get('slipSecs')} s, slide {r.get('slideSecs')} s, emergencies {r.get('emergencies')}" if check == "autumn" else ""))
    elif check == "canted":
        c = (r.get("checks") or {}).get("cantedRailVisibility", {})
        if c.get("count"):
            bad.append(f"{c['count']} curves with bed above a rail")
        if c.get("unmeasuredCurves"):
            bad.append(f"{c['unmeasuredCurves']} curves missing a rail-side sample")
        if c.get("missingBed"):
            bad.append(f"{c['missingBed']} rail samples without their own bed")
        more = f"curves {c.get('curves')}, samples {c.get('of')}, missing samples {c.get('missing')}"
    elif check == "crossing":
        c = (r.get("checks") or {}).get("crossingSlab", {})
        if not c.get("of"):
            bad.append("no rail samples")
        if c.get("count"):
            bad.append(f"{c['count']} unexplained pedestrian obstructions")
        more = f"raw sections {c.get('rawCount')}, samples {c.get('of')}, missing samples {c.get('missing')}"
    elif check == "spacing":
        c = (r.get("checks") or {}).get("spacing", {})
        for sec in c.get("sections") or []:
            if sec.get("outside"):
                bad.append(f"{sec['name']}: {sec['outside']} sections outside {sec['expect']}")
            if sec.get("expect") and sec.get("kinks"):
                bad.append(f"{sec['name']}: {sec['kinks']} kinks")
        more = "; ".join(f"{s['name']} {s['min']}-{s['max']} m ({s['alongside']}/{s['sections']})"
                         for s in c.get("sections") or []) or "no pilot section on this line"
    elif check == "heights":
        c = (r.get("checks") or {}).get("heights", {})
        for k in ("path", "pathBack"):
            if (c.get(k) or {}).get("p90") is not None and c[k]["p90"] > 0.10:
                bad.append(f"{k} p90 {c[k]['p90']} m from the staged heights")
        if c.get("apartCount"):
            bad.append(f"{c['apartCount']} junctions with two heights")
        # (a line without them is not a full build: #237 published five so, this check passing)
        if not c.get("assembled"):
            bad.append("no assembled heights on this line")
        more = (f"path {c.get('path')}, pathBack {c.get('pathBack')}, junctions {c.get('junctions')}"
                if c.get("assembled") else "")
    elif check == "traffic":
        st = r.get("stats") or {}
        if not st.get("finished"):
            bad.append(f"did not finish (stop {st.get('nextStop')}, {st.get('simSeconds')} s): a jam")
        more = ", ".join(f"{k} {v.get('count') if isinstance(v, dict) else v}" for k, v in (r.get("checks") or {}).items())
    else:  # lint
        more = ", ".join(f"{k} {v.get('count')}" for k, v in (r.get("checks") or {}).items()
                         if isinstance(v, dict) and "count" in v)
    return not bad, ("; ".join(bad) or "clean") + " · " + more


BASELINE = os.path.join(ROOT, "reports", "baseline", "headless.json")
PLACES = os.path.join(ROOT, "reports", "baseline", "headless-places.json")  # where each counted problem was (#157)


def load_places():
    return json.load(open(PLACES, encoding="utf-8")) if os.path.exists(PLACES) else {}
# counts that are problems when they rise (the rest are context: yields, junction phases, holds)
BAD = {"u3": {"stuck", "hits", "red", "signalPenalty"},
       "stops": {"stuck", "flipsFree", "short", "over", "late", "lateStops"},
       "autumn": {"stuck", "hits", "signalPenalty", "flipsFree", "short", "over", "late", "lateStops", "slideSecs", "emergencies"},
       "redruns": {"stuck", "redRuns", "aheadRedRuns", "ourSignalPenalty"}}
# per seed: problems that must not appear on any seed (the rest are judged against the seed spread)
HARD = {"u3": {"stuck", "hits", "red", "signalPenalty"},
        "stops": {"stuck", "flipsFree"},
        "autumn": {"stuck", "hits", "signalPenalty"},
        "redruns": {"stuck", "redRuns", "aheadRedRuns", "ourSignalPenalty"},
        "traffic": {"finished"}}
SPREAD_SEEDS = "1-5"


def counts(check, r):
    """The key numbers of one run (what the baseline keeps)."""
    if "error" in r:
        return {"error": 1}
    if check == "u3":
        j = r.get("carsIntoJunctions") or {}
        return {"stuck": None if r.get("stuck") is None else round(r["stuck"]), "hits": r.get("hits") or 0,
                "red": j.get("red", 0), "signalPenalty": r.get("signalPenalty") or 0, "yielded": r.get("yielded"),
                "closeCuts": r.get("closeCuts"), "green": j.get("green"), "amber": j.get("amber")}
    if check == "redruns":
        return {k: r.get(k) for k in ("stuck", "redRuns", "avoidable", "aheadRedRuns", "ourSignalPenalty", "warnPasses", "holds")}
    if check in ("stops", "autumn"):
        keep = ("hits", "signalPenalty", "slipSecs", "slideSecs", "sandSecs", "emergencies") if check == "autumn" else ()
        return {k: r.get(k) for k in keep + ("stuck", "flipsFree", "flipsShort", "flipsAhead", "flipsSignal", "flipsCar", "flipsContact", "restarts", "pulses", "shoesAtSpeed", "short", "over", "maxDecel", "maxJerk", "errP90", "comfort", "late", "devMean", "lateStops", "presses", "pressesPerKm", "pressesPerStop", "pressesRolling", "brakeApplies", "coastStretches", "coastM", "driveM", "brakeM", "pedalChangesPerKm")}
    out = {k: v.get("count") if isinstance(v, dict) else v for k, v in (r.get("checks") or {}).items()
           if not isinstance(v, dict) or "count" in v}
    if check == "traffic":
        out["finished"] = int(bool((r.get("stats") or {}).get("finished")))
        out["cyclesBroken"] = (r.get("stats") or {}).get("cyclesBroken", 0)  # (#154: a car on the track left a deadlock)
    return out


def places(check, r):
    """Where each counted problem was, as [x, y, s] per count (x, y null for the benches, which give the route
    position only): the baseline keeps them so --compare lists places new and gone (#157)."""
    if "error" in r:
        return {}
    if check == "u3":
        return {k: [[None, None, round(i["s"])] for i in r.get(src) or [] if i.get("s") is not None]
                for k, src in (("hits", "collisions"), ("closeCuts", "cuts"))}
    if check == "redruns":
        return {k: [[None, None, round(i["s"])] for i in r.get(src) or [] if isinstance(i, dict) and i.get("s") is not None]
                for k, src in (("redRuns", "red"), ("aheadRedRuns", "aheadRed"))}
    return {k: v["at"] for k, v in (r.get("checks") or {}).items() if isinstance(v, dict) and "at" in v}


NEAR = 15  # m: a place counts as the same within this (route metres when there is no x, y)


def near(a, b):
    if a[0] is not None and b[0] is not None:
        return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 <= NEAR * NEAR
    return a[2] is not None and b[2] is not None and abs(a[2] - b[2]) <= NEAR


def place_rows(stored_places, found, limit=6):
    """Markdown rows: per line, check and count, the places new on the branch (none of main's stored
    runs of any seed had one within NEAR) and the places gone (main had them, no branch run has),
    most repeated first: 'x,y (s S) ×runs'."""
    groups = {}
    for (line, check, seed), p in found.items():
        groups.setdefault((line, check), []).append(p)
    rows = []
    for (line, check), runs in sorted(groups.items(), key=lambda kv: (int(kv[0][0]), kv[0][1])):
        prefix = f"line{line}-{check}" + ("" if check in SEEDLESS else "-seed")
        stored = [v for k, v in stored_places.items() if (k == prefix if check in SEEDLESS else k.startswith(prefix))]
        if not stored:
            continue
        for k in sorted({k for p in runs for k in p} & {k for p in stored for k in p}):
            mine = [p.get(k, []) for p in runs]
            main = [p.get(k, []) for p in stored]

            def lonely(lists, others):
                out = []  # [place, how many runs]
                flat = [q for o in others for q in o]
                for lst in lists:
                    for q in lst:
                        if any(near(q, o) for o in flat):
                            continue
                        hit = next((x for x in out if near(x[0], q)), None)
                        if hit:
                            hit[1] += 1
                        else:
                            out.append([q, 1])
                return sorted(out, key=lambda x: -x[1])

            def fmt_places(ps):
                # (a place in one run only is mostly the seed's reshuffle, as the counts' noise: counted, not
                # listed; seedless checks list every place)
                many = ps if check in SEEDLESS else [x for x in ps if x[1] > 1]
                parts = [((f"{q[0]},{q[1]}" if q[0] is not None else "") + (f" (s {q[2]})" if q[2] is not None else "")
                          + (f" ×{n}" if n > 1 else "")).strip() for q, n in many[:limit]]
                if len(many) > limit:
                    parts.append(f"+{len(many) - limit}")
                if len(ps) > len(many):
                    parts.append(f"{len(ps) - len(many)} once")
                return f"{len(ps)}: " + "; ".join(parts) if parts else "0"
            new, gone = lonely(mine, main), lonely(main, mine)
            if new or gone:
                rows.append(f"| {line} | {check} | {k} | {fmt_places(new)} | {fmt_places(gone)} |")
    return rows


git, trees = baseline_store.git, baseline_store.trees


def data_matches(lines):
    """Whether data/ holds the manifest's files for these lines (a hand-copied file would mix builds)."""
    import hashlib
    man = json.load(open(os.path.join(ROOT, "data", "MANIFEST.json"), encoding="utf-8"))["files"]
    bad = []
    for name, f in man.items():
        if not any(name.startswith(f"line{ln}.") for ln in lines):
            continue
        p = os.path.join(ROOT, "data", name)
        h = hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.exists(p) else None
        if h != f["sha256"]:
            bad.append(name)
    return bad


def key_of(line, check, seed):
    return f"line{line}-{check}" + ("" if check in SEEDLESS else f"-seed{seed}")


def problem(check, k):
    """A count that is a problem when it rises (lint and traffic counts are; u3's yields are context)."""
    return check in ("lint", "traffic", "surfaces") or k in BAD.get(check, ()) or k == "error"


def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def fmt(v):
    return f"{v:.0f}" if abs(v) >= 10 else f"{v:.2g}"


def spread_cell(k, before, after, check):
    """'k mean [min-max] → mean [min-max]' and its mark; None when the branch's mean stays inside main's
    spread (noise). before/after: the values of one count over the stored and the run seeds."""
    b, a = [v for v in before if num(v)], [v for v in after if num(v)]
    if not b or not a:
        return None
    bm, am = sum(b) / len(b), sum(a) / len(a)
    lo, hi = min(b), max(b)
    if lo <= am <= hi:
        return None
    rng = lambda v: "" if min(v) == max(v) else f" [{fmt(min(v))}–{fmt(max(v))}]"
    mark = (" **worse**" if am > hi else " better") if problem(check, k) else ""
    return f"{k} {fmt(bm)}{rng(b)} → {fmt(am)}{rng(a)}{mark}"


def jammed(c):
    """A run that did not get through (stuck, unfinished, an error): its counts measure the jam, not the
    traffic (line 17 traffic seed 4 in #151's check: walkerHit 133 against 11-39 on the other seeds);
    it is reported per seed and left out of the spread."""
    return bool(c.get("error")) or c.get("stuck") is not None or c.get("finished") == 0


def compare_rows(base, results):
    """Markdown rows per line and check: counts whose mean left main's seed spread (marked when a problem
    rose or fell), the counts that moved inside it, and per-seed changes of the hard problems."""
    groups = {}
    for (line, check, seed), c in results.items():
        groups.setdefault((line, check), {})[seed] = c
    rows = []
    for (line, check), runs in sorted(groups.items(), key=lambda kv: (int(kv[0][0]), kv[0][1])):
        if check in SEEDLESS:
            b = (base.get(key_of(line, check, 0)) or {}).get("counts")
            if b is None:
                rows.append(f"| {line} | {check} | | no baseline | | |")
                continue
            c = runs[0]
            moved = [f"{k} {b.get(k)} → {c.get(k)}" + (" **worse**" if num(c.get(k)) and c[k] > (b.get(k) or 0) else "")
                     for k in sorted(set(b) | set(c)) if b.get(k) != c.get(k)]
            rows.append(f"| {line} | {check} | | {'; '.join(moved) or 'same'} | | |")
            continue
        prefix = f"line{line}-{check}-seed"
        stored = {int(k[len(prefix):]): v["counts"] for k, v in base.items() if k.startswith(prefix)}
        if not stored:
            rows.append(f"| {line} | {check} | {','.join(map(str, sorted(runs)))} | no baseline | | |")
            continue
        hard, out, inside = [], [], []
        for seed in sorted(runs):
            b, c = stored.get(seed), runs[seed]
            if b is None:
                hard.append(f"seed {seed}: no baseline")
                continue
            for k in sorted(HARD.get(check, set()) | {"error"}):
                bv, cv = b.get(k), c.get(k)
                if bv == cv:
                    continue
                if k == "finished":
                    worse = not cv
                elif k == "stuck":  # (a position: newly stuck is worse, stuck elsewhere is context)
                    worse = bv is None
                else:
                    worse = num(cv) and cv > (bv or 0)
                hard.append(f"seed {seed}: {k} {bv} → {cv}" + (" **worse**" if worse else ""))
        keys = sorted({k for v in [*stored.values(), *runs.values()] for k in v} - HARD.get(check, set()) - {"error"})
        same_seeds = set(runs) <= set(stored)
        for k in keys:
            before = [v.get(k) for v in stored.values() if not jammed(v)]
            after = [runs[s].get(k) for s in sorted(runs) if not jammed(runs[s])]
            if same_seeds and after == [stored[s].get(k) for s in sorted(runs) if not jammed(runs[s])]:
                continue
            cell = spread_cell(k, before, after, check)
            (out.append(cell) if cell else inside.append(k))
        seeds = ",".join(map(str, sorted(runs))) + f" (main: {len(stored)})"
        rows.append(f"| {line} | {check} | {seeds} | {'; '.join(out) or ('same' if not inside else '–')} | "
                    f"{', '.join(inside)} | {'; '.join(hard)} |")
    return rows


def seeds_of(spec):
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b) + 1)) if b else [int(a)]
    return out


def stop_server(p):
    """Reap only the child we started, including failed or interrupted startup."""
    if p.poll() is None:
        p.terminate()
    try:
        p.wait(timeout=5)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait(timeout=5)


def serve(port, startup_timeout=10):
    """(child, URL): a bound socket and a per-launch identity, never an existing listener (#116)."""
    identity = secrets.token_hex(16)
    with tempfile.TemporaryDirectory(prefix='tram-server-') as folder:
        ready = os.path.join(folder, 'ready.json')
        p = subprocess.Popen([sys.executable, '-I', os.path.join(ROOT, 'tools', 'serve.py'), str(port),
                              '--identity', identity, '--ready-file', ready], cwd=ROOT,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + startup_timeout
        try:
            while time.monotonic() < deadline:
                if os.path.exists(ready):
                    with open(ready, encoding='utf-8') as f:
                        info = json.load(f)
                    if info.get('error'):
                        raise SystemExit(f"tools/serve.py: {info['error']}; choose another --port or --port 0")
                    if p.poll() is not None:
                        raise SystemExit(f'tools/serve.py exited {p.returncode} before verified startup on port {port}')
                    if (info.get('identity') != identity or info.get('pid') != p.pid or not info.get('root') or
                            os.path.normcase(os.path.realpath(info.get('root', ''))) !=
                            os.path.normcase(os.path.realpath(ROOT))):
                        raise SystemExit('tools/serve.py readiness does not identify this child/checkout')
                    url = f"http://127.0.0.1:{info['port']}"
                    try:
                        with urllib.request.urlopen(url + '/index.html', timeout=1) as response:
                            if response.headers.get('X-Tram-Server-Identity') != identity:
                                raise SystemExit(f'server identity mismatch at {url}; refusing another listener')
                        if p.poll() is None:
                            return p, url
                    except OSError:
                        pass  # the child has bound, but may not have entered its request loop yet
                if p.poll() is not None:
                    if os.path.exists(ready):
                        continue  # child may have announced its bind error just before it exited
                    raise SystemExit(f'tools/serve.py exited {p.returncode} before verified startup on port {port}')
                time.sleep(.05)
            raise SystemExit(f'tools/serve.py did not verify its identity on port {port} within {startup_timeout} s')
        except BaseException:
            stop_server(p)
            raise


ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist",
        "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
        "--disable-backgrounding-occluded-windows"]


def worker(jobs, url, headed, timeout, done=None):
    """A batch of one line's jobs in a worker process, with a browser of its own (sync Playwright is one per
    process): one page load for all of them, the next shift started in the same page (#205: the load is ~60 s
    of a ~145 s run). A run that fails or times out leaves the page; the rest of the batch gets a fresh one.
    Each result also goes to the queue `done` as it comes, for the progress lines."""
    out = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed, args=ARGS)
        try:
            page = None
            for line, check, seed in jobs:
                if page is None:
                    page, errors, load = load_page(browser, url, line, timeout)
                r, secs = run_one(page, errors, check, seed, timeout, load)
                load = 0
                out.append(((line, check, seed), r, secs))
                if done is not None:
                    done.put(out[-1])
                if r.get("error") or r.get("pageErrors"):
                    page.close()
                    page = None
            if page is not None:
                page.close()
        finally:
            browser.close()
    return out


def load_page(browser, url, line, timeout):
    """A page with the line loaded: (page, its page errors, seconds or an error)."""
    page = browser.new_page(viewport={"width": 960, "height": 540})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    t0 = time.monotonic()
    try:
        page.goto(f"{url}/index.html?line={line}&keepgeo", timeout=min(120_000, timeout * 1000))
        # loaded: the loading screen is hidden and the title names the line (as batch.html waits)
        page.wait_for_function(
            f"() => document.getElementById('loading')?.classList.contains('hidden') && document.title.includes('{line}')",
            timeout=max(1, min(600_000, (timeout - (time.monotonic() - t0)) * 1000)), polling=1000)
    except PlaywrightTimeoutError:
        return page, errors, {"error": "timeout"}
    except Exception as e:  # noqa: BLE001 (a failed load is a result)
        return page, errors, {"error": f"{type(e).__name__}: {e}"}
    return page, errors, round(time.monotonic() - t0)


def run_single(browser, url, line, check, seed, timeout):
    """One run in a fresh page, closed after it."""
    page, errors, load = load_page(browser, url, line, timeout)
    try:
        return run_one(page, errors, check, seed, timeout, load)
    finally:
        page.close()


def run_one(page, errors, check, seed, timeout, load=0):
    """One check in a loaded page; its seconds include the page load when it is the first in the page."""
    if isinstance(load, dict):
        return dict(load, **({"pageErrors": errors[:20]} if errors else {})), 0
    errors.clear()
    t0 = time.monotonic()

    def remaining(cap):
        ms = (timeout - (time.monotonic() - t0)) * 1000
        if ms <= 0:
            raise PlaywrightTimeoutError("run deadline reached")
        return min(cap, ms)

    try:
        js = CALLS[check].replace("SEED", str(seed))
        # evaluate has no timeout: launch without returning the bench's promise, then wait outside it.
        page.evaluate(f"""() => {{
            window._job = {{ done: false }};
            (async () => {{ {js} }})().then(
                result => {{ window._job.result = result; window._job.done = true; }},
                error => {{ window._job.result = {{ error: String(error) }}; window._job.done = true; }});
        }}""")
        page.wait_for_function("() => window._job.done", timeout=remaining(timeout * 1000), polling=100)
        r = page.evaluate("() => window._job.result")
        r = json.loads(json.dumps(r, default=str)) if r is not None else {}
        if isinstance(r, dict):
            r.pop("watch", None)
    except PlaywrightTimeoutError:
        r = {"error": "timeout"}
    except Exception as e:  # noqa: BLE001 (a failed run is a result)
        r = {"error": f"{type(e).__name__}: {e}"}
    if errors:
        r["pageErrors"] = errors[:20]
    return r, round(time.monotonic() - t0) + load


def choose_baseline(base, stored_places, results, main_rev, want, measure=True, store=baseline_store):
    """What each run compares with, when no checkpoint is named (#282): main's own at the merge base, this machine's or
    published; for a seedless run without one, what this machine measured there, or a measurement now; for a seeded
    run without one, the latest world checkpoint's. Returns (base, places, the runs left on an older baseline)."""
    jobs = {key_of(*job): job for job in results}
    missing = lambda b: {j for j in jobs if (b.get(j) or {}).get("measured_on") != want}  # noqa: E731
    if missing(base):
        # (main's nightly baseline, measured on exactly the merge base's code and data)
        nightly, nightly_places = store.fetch(store.key(want))
        if nightly is not None:
            print(f"note: comparing with main's published baseline of {main_rev[:7]} (the local one is older)")
            base, stored_places = nightly, nightly_places or {}
    base, stored_places = dict(base), dict(stored_places)

    def take(counts, places, only):
        for j in only & set(counts):
            base[j] = counts[j]
            if j in places:
                stored_places[j] = places[j]
            else:
                stored_places.pop(j, None)

    def seedless():
        return {j for j in missing(base) if jobs[j][1] in SEEDLESS}

    if seedless():
        take(*store.kept(store.key(want)), seedless())
    if seedless() and measure:
        lines, checks = sorted({jobs[j][0] for j in seedless()}), sorted({jobs[j][1] for j in seedless()})
        counts, places = store.measure_at(main_rev, lines, checks, want)
        store.keep(store.key(want), counts, places)
        take(counts, places, seedless())
    seeded = {j for j in missing(base) if jobs[j][1] not in SEEDLESS}
    named = store.latest_checkpoint(store.checkpoints()) if seeded else None
    if named:
        counts, places = store.fetch_checkpoint(named)
        seeded &= set(counts or {})
        take(counts or {}, places or {}, seeded)
        print(f"note: {len(seeded)} seeded runs compare with checkpoint {named}: main has no baseline at {main_rev[:7]}")
    else:
        seeded = set()
    return base, stored_places, sorted(j for j in missing(base) - seeded if j in base)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lines", default="17")
    ap.add_argument("--checks", default="u3,redruns", help="u3, redruns, stops, autumn, traffic, lint, canted, crossing, surfaces, spacing, heights")
    ap.add_argument("--seeds", help=f"default 1-3; {SPREAD_SEEDS} with --baseline or --compare (the seed spread)")
    ap.add_argument("--port", type=int, default=8745, help="own server port; 0 chooses a free port atomically")
    ap.add_argument("--url", help="use a running server instead of starting tools/serve.py")
    ap.add_argument("--headed", action="store_true", help="show the browser (debugging)")
    ap.add_argument("--timeout", type=int, default=1800, help="seconds per run")
    ap.add_argument("--jobs", type=int, default=None,
                    help="pages at once (worker processes); default by cores and free memory, up to ~4 GB a page (line 17)")
    ap.add_argument("--separate", action="store_true",
                    help="u3 and redruns as two drives (default: one drive watched by both, the same counts)")
    ap.add_argument("--batch", type=int, default=6,
                    help="runs of one line per page load (1: a fresh page per run); the counts are the same (#205)")
    ap.add_argument("--out", default=os.path.join(ROOT, "reports", "headless"))
    ap.add_argument("--baseline", action="store_true",
                    help="store these runs' counts as the baseline (reports/baseline/headless.json)")
    ap.add_argument("--compare", action="store_true", help="compare these runs with the baseline (main's published one when the local one is older)")
    ap.add_argument("--publish", action="store_true", help="with --baseline: also publish it to the data store (the nightly run, #157)")
    ap.add_argument("--checkpoint", help="with --baseline --publish: also store it under this checkpoint's name (W1, #282)")
    ap.add_argument("--against", help="with --compare: compare with this checkpoint's run instead of main's")
    ap.add_argument("--no-measure-base", action="store_true",
                    help="with --compare: do not measure seedless runs at the merge base when it has no baseline")
    a = ap.parse_args()
    a.seeds = a.seeds or (SPREAD_SEEDS if a.baseline or a.compare else "1-3")
    if a.checkpoint and not (a.baseline and a.publish):
        ap.error("--checkpoint needs --baseline --publish")
    if a.against and not a.compare:
        ap.error("--against needs --compare")
    if a.checkpoint and not baseline_store.NAME.match(a.checkpoint):
        ap.error(f"not a checkpoint name: {a.checkpoint}")
    if a.checkpoint and a.checkpoint in baseline_store.checkpoints():
        raise SystemExit(f"checkpoint {a.checkpoint} is in the store: python -I tools/baseline_store.py rm-checkpoint {a.checkpoint} first")
    if a.against and baseline_store.fetch_checkpoint(a.against)[0] is None:  # (before the run, not after it)
        raise SystemExit(f"no checkpoint {a.against} in the store: python -I tools/baseline_store.py checkpoints")
    if a.timeout <= 0:
        ap.error("--timeout must be positive")
    checks = [c.strip() for c in a.checks.split(",") if c.strip()]
    for c in checks:
        if c not in CALLS:
            raise SystemExit(f"unknown check {c!r}: {', '.join(CALLS)}")
    jobs = [(line.strip(), c, s) for line in a.lines.split(",") for c in checks
            for s in ([0] if c in SEEDLESS else seeds_of(a.seeds))]
    lines = sorted({j[0] for j in jobs})
    if a.baseline:
        # (measured on what is committed and published, or the baseline would name the wrong trees)
        dirty = baseline_store.dirty()
        if dirty or (bad := data_matches(lines)):
            raise SystemExit(f"--baseline needs {', '.join(MEASURED)} committed and data/ matching the manifest: "
                             f"{dirty or 'data differs: ' + ', '.join(bad)}")
    if a.compare and (bad := data_matches(lines)):
        print(f"note: data/ differs from data/MANIFEST.json ({', '.join(bad)}): comparing unpublished data")
    results, found = {}, {}
    server, url = (None, a.url) if a.url else serve(a.port)
    failed, t0 = 0, time.time()

    def report(i, job, r, secs):
        nonlocal failed
        line, check, seed = job
        ok, text = judge(check, r)
        failed += not ok
        results[job] = counts(check, r)
        found[job] = places(check, r)
        name = f"line{line}-{check}" + ("" if check in SEEDLESS else f"-seed{seed}") + ".json"
        with open(os.path.join(a.out, name), "w", encoding="utf-8") as f:
            json.dump({"line": line, "check": check, "seed": seed, "seconds": secs, "ok": ok,
                       "time": time.strftime("%Y-%m-%dT%H:%M:%S"), "result": r}, f, ensure_ascii=False, indent=1)
        print(f"[{i}/{len(jobs)}] line {line} {check}" + ("" if check in SEEDLESS else f" seed {seed}")
              + f" … {'pass' if ok else 'FAIL'} ({secs} s) {text}", flush=True)

    def split(res):
        """A drive's result as the u3 and redruns results it holds (an error goes to both)."""
        (line, check, seed), r, secs = res
        if check != "drive":
            return [res]
        extra = {"pageErrors": r["pageErrors"]} if r.get("pageErrors") else {}
        return [((line, c, seed), {**r[c], **extra} if isinstance(r.get(c), dict) else dict(r), secs)
                for c in ("u3", "redruns")]

    heavy = HeavyJob("headless")  # (waits its turn among the heavy jobs, and the nightly baseline for it: #280)
    try:
        heavy.__enter__()
        t0 = time.time()  # (the run's time, not the wait's)
        if a.jobs is None:
            a.jobs = workers(4.0)  # (sized by the memory free once its turn comes)
        os.makedirs(a.out, exist_ok=True)
        # (u3 and redruns of a line and seed: one drive; then batches of one line's runs, each in one page)
        runs = list(jobs)
        if not a.separate:
            both = {(l, s) for l, c, s in jobs if c == "u3"} & {(l, s) for l, c, s in jobs if c == "redruns"}
            runs = [(l, "drive", s) if c == "u3" and (l, s) in both else (l, c, s) for l, c, s in jobs
                    if not (c == "redruns" and (l, s) in both)]
        batches = []
        for line in lines:
            mine = [j for j in runs if j[0] == line]
            batches += [mine[k:k + max(1, a.batch)] for k in range(0, len(mine), max(1, a.batch))]
        i = 0
        if a.jobs > 1 and len(batches) > 1:
            with ProcessPoolExecutor(min(a.jobs, len(batches))) as ex, multiprocessing.Manager() as mgr:
                done = mgr.Queue()
                futs = [ex.submit(worker, b, url, a.headed, a.timeout, done) for b in batches]
                while i < len(jobs):
                    try:
                        res = done.get(timeout=5)
                    except queue.Empty:
                        if all(fu.done() for fu in futs):
                            for fu in futs:
                                fu.result()  # (a worker that failed outside a run)
                            break
                        continue
                    for part in split(res):
                        i += 1
                        report(i, *part)
        else:
            for b in batches:
                for res in worker(b, url, a.headed, a.timeout):
                    for part in split(res):
                        i += 1
                        report(i, *part)
    finally:
        heavy.__exit__()
        if server:
            stop_server(server)
    print(f"{len(jobs) - failed}/{len(jobs)} passed in {time.time() - t0:.0f} s ({a.jobs} at once); "
          f"results in {os.path.relpath(a.out, ROOT)}")
    base = json.load(open(BASELINE, encoding="utf-8")) if os.path.exists(BASELINE) else {}
    stored_places = load_places()
    if a.compare:
        main_rev = git("merge-base", "HEAD", "origin/main") or git("rev-parse", "main")
        want = trees(main_rev)
        if a.against:
            base, stored_places = baseline_store.fetch_checkpoint(a.against)
            stored_places = stored_places or {}
            print(f"note: comparing with checkpoint {a.against} (measured at {sorted({v.get('commit') for v in base.values()})})")
            stale = []
        else:
            base, stored_places, stale = choose_baseline(base, stored_places, results, main_rev, want, not a.no_measure_base)
        if stale:
            print(f"\nWARNING: the baseline of {', '.join(stale)} was not measured on main ({main_rev[:7]}): "
                  "run --baseline on main first, or read the differences as main's changes plus yours")
        rows = ["| line | check | seeds | outside main's seed spread: mean [min–max] → now | moved inside it | per seed |",
                "|---|---|---|---|---|---|", *compare_rows(base, results)]
        prow = place_rows(stored_places, found)
        if prow:
            rows += ["", f"Places new on the branch and gone from it (none of main's stored runs, or none of the branch's, within {NEAR} m):",
                     "", "| line | check | count | new | gone |", "|---|---|---|---|---|", *prow]
        print("\n" + "\n".join(rows))
        with open(os.path.join(a.out, "compare.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(rows) + "\n")
    if a.baseline:
        rev = git("rev-parse", "HEAD")
        for job, c in results.items():
            base[key_of(*job)] = {"counts": c, "measured_on": trees(rev), "commit": rev[:7],
                                  "time": time.strftime("%Y-%m-%d %H:%M")}
        os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump(dict(sorted(base.items())), f, ensure_ascii=False, indent=1)
        stored = load_places()
        stored.update({key_of(*job): p for job, p in found.items()})
        with open(PLACES, "w", encoding="utf-8") as f:  # (one run per line: diffs stay readable)
            rows = (f"{json.dumps(k)}: {json.dumps(v, separators=(',', ':'))}" for k, v in sorted(stored.items()))
            f.write("{\n" + ",\n".join(rows) + "\n}\n")
        print(f"baseline: {len(results)} runs stored in {os.path.relpath(BASELINE, ROOT)}")
        if a.publish:
            t = trees(rev)
            mine = {k: v for k, v in base.items() if v.get("measured_on") == t}
            where = {k: v for k, v in stored.items() if k in mine}
            if not a.checkpoint or baseline_store.WORLD.match(a.checkpoint):
                baseline_store.publish(baseline_store.key(t), mine, where)
                print(f"published as baselines/{baseline_store.key(t)}.json ({len(mine)} runs of {rev[:7]})")
            if a.checkpoint:
                baseline_store.publish_checkpoint(a.checkpoint, baseline_store.key(t), mine, where, rev[:7])
                print(f"published as checkpoint {a.checkpoint} ({len(mine)} runs of {rev[:7]})")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
