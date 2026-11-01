"""Headless checks from the command line (issue #2): the in-page benches and lints in headless Chromium.

    python -P -E tools/headless.py --lines 17,23 --checks u3,redruns --seeds 1-3
    python -P -E tools/headless.py --lines 23 --checks traffic --seeds 22,7,1234
    python -P -E tools/headless.py --lines 17 --checks lint            # static lints (no seed)
    python -P -E tools/headless.py --lines 9,17,22,23,37 --checks u3,lint --jobs 4   # 4 pages at once

Each run gets a fresh page (`/?line=N&keepgeo`), waits for the loading screen to finish, imports the
check and awaits it, exactly like tools/bench/batch.html. Results: one JSON per run in reports/headless/
and a table; the exit code is 1 when a run fails its thresholds (docs/history/BUILD-TOOLS-HANDOFF.md
§4.2: u3 no red entries, collisions, stuck tram or signal penalty; redruns no red runs; traffic must
finish; lint has no thresholds here, compare with `python tools/lint_report.py`).

Needs Playwright (`python -m pip install --user playwright`, `python -m playwright install chromium`).
Starts its own tools/serve.py on --port (0 picks a free port) and verifies its launch identity before
any job; an occupied port fails. --url explicitly uses an existing server. WebGL runs on
SwiftShader (software): slower than a desktop browser, the same results (the checks step the
simulation themselves). --jobs N runs N pages at once, each in a worker process with its own
browser (default: half the cores, at most 4, and
what free memory holds at ~4 GB a page: line 17 measured 4.1 GB): every run is seeded in
its own fresh page, so the counts are the same as one after another.

Baseline (#89): `--baseline` stores each run's key counts in reports/baseline/headless.json (committed),
with what they were measured on (the git trees of the game, the in-page checks and the data manifest:
MEASURED; the data files must match the manifest and those paths be committed). `--compare` prints baseline -> now per
run as a table for the PR (reports/headless/compare.md) and warns when the baseline was not measured on
the code and data of main (the merge base). A PR that moves the numbers commits its new baseline, so
main's stays current:

    python -P -E tools/headless.py --lines 9,17,22,23,37 --checks u3,redruns,traffic,lint --seeds 1 --compare
"""
import argparse
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ProcessPoolExecutor, as_completed

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves it out)
from sysinfo import workers  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

# the page-side call per check; `seed` is substituted (static lints take none)
CALLS = {
    "u3": "const { run } = await import('/tools/bench/u3.js'); return await run(SEED);",
    "redruns": "const { run } = await import('/tools/bench/redruns.js'); return await run(SEED);",
    "traffic": "const { trafficRun } = await import('/tools/traffic_lint.js'); return await trafficRun({ seed: SEED });",
    "lint": "document.getElementById('btnStart').click(); await new Promise((r) => setTimeout(r, 2000));"
            "const { lint } = await import('/tools/lint.js'); return await lint({ save: false });",
    "crossing": "document.getElementById('btnStart').click(); await new Promise((r) => setTimeout(r, 2000));"
                "const { run } = await import('/tools/bench/crossingSlab.js'); return run();",
    "surfaces": "document.getElementById('btnStart').click(); await new Promise((r) => setTimeout(r, 2000));"
                "const { run } = await import('/tools/bench/surfaces.js'); return await run();",
}
SEEDLESS = {"lint", "surfaces", "crossing"}


def judge(check, r):
    """(ok, one-line summary): the thresholds of tools/bench/batch.html."""
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
# (what the counts depend on: the game, the in-page checks, the data; not the build tools, whose output
# the manifest covers, nor this harness)
MEASURED = ("src", "index.html", "tools/bench", "tools/lint.js", "tools/traffic_lint.js", "tools/autopilot.js",
            "data/MANIFEST.json")
# counts that are problems when they rise (the rest are context: yields, junction phases, holds)
BAD = {"u3": {"stuck", "hits", "red", "signalPenalty"},
       "redruns": {"stuck", "redRuns", "aheadRedRuns", "ourSignalPenalty"}}
# traffic counts move 10-20 % whenever trajectories change (tools/lint_report.py): a band of 15 % + 5
NOISY = {"slide", "jump", "overlap", "walkerHit", "heatingKnobs", "streetBot", "redRuns"}


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
    out = {k: v.get("count") if isinstance(v, dict) else v for k, v in (r.get("checks") or {}).items()
           if not isinstance(v, dict) or "count" in v}
    if check == "traffic":
        out["finished"] = int(bool((r.get("stats") or {}).get("finished")))
    return out


def git(*args):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def trees(rev):
    """The git objects the checks depend on, at a commit."""
    return {p: git("rev-parse", f"{rev}:{p}") for p in MEASURED}


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


def compare_rows(base, results):
    """Markdown rows: baseline -> now for each run, changed counts only; problems that rose are marked."""
    rows = []
    for (line, check, seed), c in sorted(results.items(), key=lambda kv: (int(kv[0][0]), kv[0][1], kv[0][2])):
        b = (base.get(key_of(line, check, seed)) or {}).get("counts")
        if b is None:
            rows.append(f"| {line} | {check} | {'' if check in SEEDLESS else seed} | no baseline |")
            continue
        moved = []
        for k in sorted(set(b) | set(c)):
            bv, cv = b.get(k), c.get(k)
            if bv == cv:
                continue
            band = bv * 0.15 + 5 if k in NOISY and isinstance(bv, (int, float)) else 0
            if k == "finished":
                worse = cv == 0
            elif k == "stuck":  # (a position: newly stuck is worse, stuck elsewhere is context)
                worse = bv is None
            elif check in ("lint", "traffic") or k in BAD.get(check, ()) or k == "error":
                worse = isinstance(cv, (int, float)) and cv > (bv or 0) + band
            else:
                worse = False
            moved.append(f"{k} {bv} → {cv}" + (" **worse**" if worse else ""))
        rows.append(f"| {line} | {check} | {'' if check in SEEDLESS else seed} | {'; '.join(moved) or 'same'} |")
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


def worker(job, url, headed, timeout):
    """One job in a worker process, with a browser of its own (sync Playwright is one per process)."""
    line, check, seed = job
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed, args=ARGS)
        try:
            r, secs = run_one(browser, url, line, check, seed, timeout)
        finally:
            browser.close()
    return job, r, secs


def run_one(browser, url, line, check, seed, timeout):
    page = browser.new_page(viewport={"width": 960, "height": 540})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    t0 = time.monotonic()

    def remaining(cap):
        ms = (timeout - (time.monotonic() - t0)) * 1000
        if ms <= 0:
            raise PlaywrightTimeoutError("run deadline reached")
        return min(cap, ms)

    try:
        page.goto(f"{url}/index.html?line={line}&keepgeo", timeout=remaining(120_000))
        # loaded: the loading screen is hidden and the title names the line (as batch.html waits)
        page.wait_for_function(
            f"() => document.getElementById('loading')?.classList.contains('hidden') && document.title.includes('{line}')",
            timeout=remaining(600_000), polling=1000)
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
    finally:
        page.close()
    if errors:
        r["pageErrors"] = errors[:20]
    return r, round(time.monotonic() - t0)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lines", default="17")
    ap.add_argument("--checks", default="u3,redruns", help="u3, redruns, traffic, lint, surfaces")
    ap.add_argument("--seeds", default="1-3")
    ap.add_argument("--port", type=int, default=8745, help="own server port; 0 chooses a free port atomically")
    ap.add_argument("--url", help="use a running server instead of starting tools/serve.py")
    ap.add_argument("--headed", action="store_true", help="show the browser (debugging)")
    ap.add_argument("--timeout", type=int, default=1800, help="seconds per run")
    ap.add_argument("--jobs", type=int, default=workers(4.0),
                    help="pages at once (worker processes); default by cores and free memory, up to ~4 GB a page (line 17)")
    ap.add_argument("--out", default=os.path.join(ROOT, "reports", "headless"))
    ap.add_argument("--baseline", action="store_true",
                    help="store these runs' counts as the baseline (reports/baseline/headless.json)")
    ap.add_argument("--compare", action="store_true", help="compare these runs with the baseline")
    a = ap.parse_args()
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
        dirty = git("status", "--porcelain", "--", *MEASURED)
        if dirty or (bad := data_matches(lines)):
            raise SystemExit("--baseline needs committed src/, tools/, index.html, data/MANIFEST.json and data/ "
                             f"matching the manifest: {dirty or 'data differs: ' + ', '.join(bad)}")
    if a.compare and (bad := data_matches(lines)):
        print(f"note: data/ differs from data/MANIFEST.json ({', '.join(bad)}): comparing unpublished data")
    results = {}
    server, url = (None, a.url) if a.url else serve(a.port)
    failed, t0 = 0, time.time()

    def report(i, job, r, secs):
        nonlocal failed
        line, check, seed = job
        ok, text = judge(check, r)
        failed += not ok
        results[job] = counts(check, r)
        name = f"line{line}-{check}" + ("" if check in SEEDLESS else f"-seed{seed}") + ".json"
        with open(os.path.join(a.out, name), "w", encoding="utf-8") as f:
            json.dump({"line": line, "check": check, "seed": seed, "seconds": secs, "ok": ok,
                       "time": time.strftime("%Y-%m-%dT%H:%M:%S"), "result": r}, f, ensure_ascii=False, indent=1)
        print(f"[{i}/{len(jobs)}] line {line} {check}" + ("" if check in SEEDLESS else f" seed {seed}")
              + f" … {'pass' if ok else 'FAIL'} ({secs} s) {text}", flush=True)

    try:
        os.makedirs(a.out, exist_ok=True)
        if a.jobs > 1 and len(jobs) > 1:
            with ProcessPoolExecutor(min(a.jobs, len(jobs))) as ex:
                futs = [ex.submit(worker, job, url, a.headed, a.timeout) for job in jobs]
                for i, fu in enumerate(as_completed(futs), 1):
                    report(i, *fu.result())
        else:
            for i, job in enumerate(jobs, 1):
                report(i, *worker(job, url, a.headed, a.timeout))
    finally:
        if server:
            stop_server(server)
    print(f"{len(jobs) - failed}/{len(jobs)} passed in {time.time() - t0:.0f} s ({a.jobs} at once); "
          f"results in {os.path.relpath(a.out, ROOT)}")
    base = json.load(open(BASELINE, encoding="utf-8")) if os.path.exists(BASELINE) else {}
    if a.compare:
        main_rev = git("merge-base", "HEAD", "origin/main") or git("rev-parse", "main")
        want = trees(main_rev)
        stale = sorted({key_of(*job) for job in results
                        if (base.get(key_of(*job)) or {}).get("measured_on") not in (None, want)})
        if stale:
            print(f"\nWARNING: the baseline of {', '.join(stale)} was not measured on main ({main_rev[:7]}): "
                  "run --baseline on main first, or read the differences as main's changes plus yours")
        rows = ["| line | check | seed | baseline → now |", "|---|---|---|---|", *compare_rows(base, results)]
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
        print(f"baseline: {len(results)} runs stored in {os.path.relpath(BASELINE, ROOT)} (commit it)")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
