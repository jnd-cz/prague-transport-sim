# SPDX-License-Identifier: AGPL-3.0-or-later
"""A line's load by part and its download, in headless Chromium on the GPU (#509: the load before -> after).

Usage: python -P -E tools/bench/load_times.py [--lines 17,9] [--loads 5] [--out reports/load-times/main.json]
       python -P -E tools/bench/load_times.py --compare reports/load-times/main.json reports/load-times/509.json

Its own server on a free port; each load a fresh page (`headless.load_page`, `?keepgeo`), then `window.loadTimes`
(the loading screen's steps, src/loading.js), `window.worldTimes` (buildWorld's parts, src/world.js), `window.groundTimes`
(the ground file's worker: decode, lookup, meshes, src/groundWorker.js; off the page's thread, beside the rest) and the files
the page fetched with their bytes (the Resource Timing entries: the body as the server sent it, `serve.py` gzips
nothing, so raw). The median of `--loads` loads per part. Waits its turn among the heavy jobs: a load measured beside
another job's is not this machine's.
"""
import argparse
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

READ = """() => ({
  load: window.loadTimes || null, world: window.worldTimes || null, ground: window.groundTimes || null,
  files: performance.getEntriesByType('resource').filter((e) => /\\/(data|assets)\\//.test(e.name))
    .map((e) => [new URL(e.name).pathname, e.encodedBodySize || e.transferSize || 0]),
})"""


def summarize(runs):
    """{"load": {part: median ms}, "world": {part: median ms}, "files": {path: bytes}, "loads": n} from the runs'
    readings (a part missing from a run counts as absent there, not as 0)."""
    out = {"loads": len(runs)}
    for key in ("load", "world", "ground"):
        parts = {}
        for r in runs:
            for k, v in (r.get(key) or {}).items():
                parts.setdefault(k, []).append(v)
        out[key] = {k: round(statistics.median(v)) for k, v in parts.items()}
    files = {}
    for r in runs:
        for path, size in r.get("files") or []:
            files[path] = max(files.get(path, 0), int(size))
    out["files"] = dict(sorted(files.items()))
    out["download MB"] = round(sum(files.values()) / 1e6, 2)
    return out


def table(by_line, other=None):
    """Lines of text: each part's median per line (and the other run's, before -> after)."""
    rows = []
    for ln, s in by_line.items():
        o = (other or {}).get(ln)
        rows.append(f"line {ln} ({s['loads']} loads; download {s['download MB']} MB"
                    + (f", before {o['download MB']} MB" if o else "") + ")")
        for key in ("load", "world", "ground"):
            for k, v in s.get(key, {}).items():
                was = o.get(key, {}).get(k) if o else None
                rows.append(f"  {key:5} {k:28} {(f'{was} -> ' if was is not None else '')}{v} ms")
            if o:
                for k in o.get(key, {}):
                    if k not in s.get(key, {}):
                        rows.append(f"  {key:5} {k:28} {o[key][k]} -> gone")
    return rows


def measure(lines, loads, timeout=600):
    from playwright.sync_api import sync_playwright

    import gpu
    from headless import load_page, serve, stop_server
    server, url = serve(0)
    out = {}
    try:
        with sync_playwright() as pw:
            browser = gpu.launch(pw)[0]
            for ln in lines:
                runs = []
                for k in range(loads):
                    page, errors, load = load_page(browser, url, ln, timeout)
                    if isinstance(load, dict):
                        page.close()
                        raise SystemExit(f"line {ln}: the load failed: {load} {errors[:3]}")
                    runs.append(page.evaluate(READ))
                    page.close()
                    print(f"line {ln} load {k + 1}/{loads}: {runs[-1]['load'].get('total') if runs[-1]['load'] else '?'} ms",
                          flush=True)
                out[ln] = summarize(runs)
            browser.close()
    finally:
        stop_server(server)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lines", default="17")
    ap.add_argument("--loads", type=int, default=5)
    ap.add_argument("--out", help="write the medians here (JSON)")
    ap.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"), help="print two saved runs side by side")
    a = ap.parse_args()
    if a.compare:
        before, after = (json.load(open(p, encoding="utf-8")) for p in a.compare)
        print("\n".join(table(after, before)))
        return
    from baseline_store import HeavyJob
    with HeavyJob("load times"):
        res = measure([s.strip() for s in a.lines.split(",") if s.strip()], a.loads)
    print("\n".join(table(res)))
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1)
        print(a.out)


if __name__ == "__main__":
    main()
