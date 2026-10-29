"""Headless checks from the command line (issue #2): the in-page benches and lints in headless Chromium.

    python -P -E tools/headless.py --lines 17,23 --checks u3,redruns --seeds 1-3
    python -P -E tools/headless.py --lines 23 --checks traffic --seeds 22,7,1234
    python -P -E tools/headless.py --lines 17 --checks lint            # static lints (no seed)

Each run gets a fresh page (`/?line=N&keepgeo`), waits for the loading screen to finish, imports the
check and awaits it, exactly like tools/bench/batch.html. Results: one JSON per run in reports/headless/
and a table; the exit code is 1 when a run fails its thresholds (docs/history/BUILD-TOOLS-HANDOFF.md
§4.2: u3 no red entries, collisions, stuck tram or signal penalty; redruns no red runs; traffic must
finish; lint has no thresholds here, compare with `python tools/lint_report.py`).

Needs Playwright (`python -m pip install --user playwright`, `python -m playwright install chromium`).
Starts its own tools/serve.py on --port unless --url points at a running server. WebGL runs on
SwiftShader (software): slower than a desktop browser, the same results (the checks step the
simulation themselves).
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

# the page-side call per check; `seed` is substituted (static lints take none)
CALLS = {
    "u3": "const { run } = await import('/tools/bench/u3.js'); return await run(SEED);",
    "redruns": "const { run } = await import('/tools/bench/redruns.js'); return await run(SEED);",
    "traffic": "const { trafficRun } = await import('/tools/traffic_lint.js'); return await trafficRun({ seed: SEED });",
    "lint": "document.getElementById('btnStart').click(); await new Promise((r) => setTimeout(r, 2000));"
            "const { lint } = await import('/tools/lint.js'); return await lint({ save: false });",
}
SEEDLESS = {"lint"}


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


def seeds_of(spec):
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b) + 1)) if b else [int(a)]
    return out


def serve(port):
    p = subprocess.Popen([sys.executable, "-I", os.path.join(ROOT, "tools", "serve.py"), str(port)], cwd=ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://localhost:{port}/index.html", timeout=1).read(1)
            return p
        except OSError:
            time.sleep(0.2)
    p.kill()
    raise SystemExit(f"tools/serve.py did not come up on port {port}")


def run_one(browser, url, line, check, seed, timeout):
    page = browser.new_page(viewport={"width": 960, "height": 540})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    t0 = time.time()
    try:
        page.goto(f"{url}/index.html?line={line}&keepgeo", timeout=120_000)
        # loaded: the loading screen is hidden and the title names the line (as batch.html waits)
        page.wait_for_function(
            f"() => document.getElementById('loading')?.classList.contains('hidden') && document.title.includes('{line}')",
            timeout=600_000, polling=1000)
        js = CALLS[check].replace("SEED", str(seed))
        page.set_default_timeout(timeout * 1000)
        r = page.evaluate(f"async () => {{ {js} }}")
        r = json.loads(json.dumps(r, default=str)) if r is not None else {}
        if isinstance(r, dict):
            r.pop("watch", None)
    except Exception as e:  # noqa: BLE001 (a failed run is a result)
        r = {"error": f"{type(e).__name__}: {e}"}
    if errors:
        r["pageErrors"] = errors[:20]
    page.close()
    return r, round(time.time() - t0)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lines", default="17")
    ap.add_argument("--checks", default="u3,redruns", help="u3, redruns, traffic, lint")
    ap.add_argument("--seeds", default="1-3")
    ap.add_argument("--port", type=int, default=8745)
    ap.add_argument("--url", help="use a running server instead of starting tools/serve.py")
    ap.add_argument("--headed", action="store_true", help="show the browser (debugging)")
    ap.add_argument("--timeout", type=int, default=1800, help="seconds per run")
    ap.add_argument("--out", default=os.path.join(ROOT, "reports", "headless"))
    a = ap.parse_args()
    checks = [c.strip() for c in a.checks.split(",") if c.strip()]
    for c in checks:
        if c not in CALLS:
            raise SystemExit(f"unknown check {c!r}: {', '.join(CALLS)}")
    jobs = [(line.strip(), c, s) for line in a.lines.split(",") for c in checks
            for s in ([0] if c in SEEDLESS else seeds_of(a.seeds))]
    os.makedirs(a.out, exist_ok=True)
    server = None if a.url else serve(a.port)
    url = a.url or f"http://localhost:{a.port}"
    failed = 0
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not a.headed, args=[
                "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist",
                "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows"])
            for i, (line, check, seed) in enumerate(jobs, 1):
                print(f"[{i}/{len(jobs)}] line {line} {check}" + ("" if check in SEEDLESS else f" seed {seed}"),
                      end=" … ", flush=True)
                r, secs = run_one(browser, url, line, check, seed, a.timeout)
                ok, text = judge(check, r)
                failed += not ok
                name = f"line{line}-{check}" + ("" if check in SEEDLESS else f"-seed{seed}") + ".json"
                with open(os.path.join(a.out, name), "w", encoding="utf-8") as f:
                    json.dump({"line": line, "check": check, "seed": seed, "seconds": secs, "ok": ok,
                               "time": time.strftime("%Y-%m-%dT%H:%M:%S"), "result": r}, f, ensure_ascii=False,
                              indent=1)
                print(f"{'pass' if ok else 'FAIL'} ({secs} s) {text}")
            browser.close()
    finally:
        if server:
            server.terminate()
    print(f"{len(jobs) - failed}/{len(jobs)} passed; results in {os.path.relpath(a.out, ROOT)}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
