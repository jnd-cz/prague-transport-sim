"""The performance log and test (src/perf.js, #350): python -P -E tools/test_perf.py [--line 17] [--runs N [--same-page]] [--headed]

tools/serve.py's handler on a free port, the notes in a temp folder, Chromium on the GPU (tools/gpu.py). Checks:
- a feedback note sent after some driving carries the machine (its GPU), the load times and the frame-time log;
- the menu's performance test (shortened to 8 s) drives, shows its result card, and Send stores a perftest note.
--runs N: N full one-minute tests instead (headed, so the GPU draws as it does for a player), and the spread of
their numbers: how comparable two runs on one machine are.
"""
import argparse
import faulthandler
import json
import os
import shutil
import statistics
import sys
import tempfile
import threading

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feedback  # noqa: E402
import gpu  # noqa: E402
import serve  # noqa: E402


class Quiet(serve.NoCache):
    def log_message(self, *args):
        pass


def menu(page, url, short):
    if short:
        page.add_init_script(f"window.perfTestMs = {short}")
    page.goto(url, timeout=180000)
    page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=180000)


def perf_test(page, timeout):
    page.evaluate("delete window.perfTestResult")  # (the last run's)
    page.click("#btnPerfTest")
    page.wait_for_function("window.perfTestResult", timeout=timeout)
    return page.evaluate("window.perfTestResult")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    ap.add_argument("--runs", type=int, default=0, help="full one-minute tests instead of the checks")
    ap.add_argument("--same-page", action="store_true", help="--runs one after another in one page")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    faulthandler.dump_traceback_later(600 + 120 * args.runs, exit=True)
    tmp = tempfile.mkdtemp()
    feedback.DEST = tmp
    server = serve.Server(("127.0.0.1", 0), lambda *a, **k: Quiet(*a, directory=serve.ROOT, **k))
    server.identity, server.rate, server.lan = None, 0, False
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/?line={args.line}"
    fails = []
    try:
        with sync_playwright() as p:
            browser, name = gpu.launch(p, headless=not (args.headed or args.runs))
            print(f"WebGL: {name}")
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            if args.runs:
                runs = []
                for i in range(args.runs):
                    # (a fresh page each run, as a player opens it; --same-page: the runs one after another in one
                    # page, which shows what a page carries over from shift to shift)
                    if i == 0 or not args.same_page:
                        if i:
                            page.close()
                            page = browser.new_page(viewport={"width": 1280, "height": 720})
                        menu(page, url, 0)
                    r = perf_test(page, 120000)
                    runs.append(r)
                    print(f"run {i + 1}: {r['fps']} fps, over 20/33/50 ms {r['over']['20']}/{r['over']['33']}/{r['over']['50']} %, "
                          f"p50/p90/p99 {r['ms']['p50']}/{r['ms']['p90']}/{r['ms']['p99']} ms, gpu {r.get('gpuMs')} ms, "
                          f"{r['calls']['mean']} calls, {r['triangles']['mean'] / 1e6:.2f} M triangles, heap {r.get('heapMB')} MB")
                    page.click("#ptMenu")
                fps = [r["fps"] for r in runs]
                if len(fps) > 1:
                    print(f"fps {min(fps)}-{max(fps)}, spread {max(fps) - min(fps):.1f} ({(max(fps) - min(fps)) / statistics.mean(fps) * 100:.1f} %)")
                browser.close()
                return
            menu(page, url, 8000)
            # some driving, then a note: the machine, the load times and the log go with it
            page.click("#btnStart")
            page.wait_for_function("window.game && document.body.classList.contains('shift')", timeout=60000)
            page.wait_for_timeout(4000)
            page.keyboard.press("F9")
            page.wait_for_selector("#rpBox.show")
            page.fill("#rpNote", "jerky here")
            page.click("#rpSend")
            page.wait_for_function("document.getElementById('rpMsg').textContent.includes('Sent as')", timeout=20000)
            page.wait_for_function("!document.getElementById('rpBox').classList.contains('show')", timeout=8000)
            page.keyboard.press("Escape")
            page.evaluate("document.getElementById('btnToMenu').click()")
            page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=20000)
            res = perf_test(page, 120000)
            card = page.text_content("#resultsCard")
            page.click("#ptSend")
            page.wait_for_function("document.getElementById('ptSend').textContent.includes('Sent')", timeout=20000)
            browser.close()
    finally:
        server.shutdown()
    notes = [n for _, n in feedback.notes(tmp)]
    shutil.rmtree(tmp, ignore_errors=True)
    note = next((n for n in notes if n.get("note") == "jerky here"), None)
    test = next((n for n in notes if n.get("kind") == "perftest"), None)
    print(json.dumps({"result": res, "note": {k: (note or {}).get(k) for k in ("machine", "load", "perf")},
                      "test": (test or {}).get("perftest")}, ensure_ascii=False)[:2000])
    if not note:
        fails.append("no note stored")
    else:
        if not (note.get("machine") or {}).get("gpu"):
            fails.append("the note names no GPU")
        if not (note.get("load") or {}).get("total"):
            fails.append("the note has no load times")
        if not ((note.get("perf") or {}).get("frames") or 0) > 10:
            fails.append(f"the note's frame log is empty: {note.get('perf')}")
    if not (res.get("frames", 0) > 10 and res.get("fps", 0) > 0 and res.get("test")):
        fails.append(f"the test measured nothing: {res}")
    if "Performance test" not in (card or "") or "Frames per second" not in card:
        fails.append("no result card")
    if not test or test["perftest"].get("frames") != res.get("frames"):
        fails.append("Send stored no perftest note with the result")
    if fails:
        sys.exit("; ".join(fails))
    print("perf: a note carries the machine, load times and frame log; the test drives, shows and sends: pass")


if __name__ == "__main__":
    main()
