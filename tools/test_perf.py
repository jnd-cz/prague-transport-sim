"""The performance log and test (src/perf.js, #350): python -P -E tools/test_perf.py [--line 17] [--runs N [--same-page]] [--headed]
    python -P -E tools/test_perf.py --switch 17,9 --times 3     # line switches in one page, memory and CPU watched
    python -P -E tools/test_perf.py --switch 17,9 --firefox --address [--no-release]

tools/serve.py's handler on a free port, the notes in a temp folder, Chromium on the GPU (tools/gpu.py). Checks:
- a feedback note sent after some driving carries the machine (its GPU), the load times and the frame-time log;
- the menu's performance test (shortened to 8 s) drives, shows its result card, and Send stores a perftest note;
- the reference test started on line 9 opens line 17, runs there with the detailed model, and goes back to line 9.
--runs N: N full one-minute tests instead (headed, so the GPU draws as it does for a player), and the spread of
their numbers: how comparable two runs on one machine are.
--switch A,B: loads the lines in turn in one page as a player does (the menu's line choice: a navigation, with the
back/forward cache on as in a player's Chrome; Playwright turns it off by default), each
with a 20 s autopilot shift, --times rounds. After each run or load (--runs and --switch) it prints what the page
and the browser hold: the JS heap, the GPU geometries and textures three.js keeps, the main thread's busy time,
and the private memory and CPU of this browser's processes by type (Windows; the machine should be quiet, as
every Playwright browser of that kind on it is counted).
--firefox: --switch in Playwright's Firefox (its own back/forward cache on: browser.sessionhistory.max_total_viewers
-1, Firefox's default); no JS heap or main-thread time there (Chromium's DevTools protocol). --address: each line by
a new address in the same tab, as typed into the address bar, instead of the menu. --no-release: the page's
release of the graphics on leaving (src/main.js pagehide) left out, to compare.
"""
import argparse
import faulthandler
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time

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


PS = ("Get-CimInstance Win32_Process -Filter \"Name='{exe}'\" | Where-Object {{ $_.ExecutablePath -like '*ms-playwright*' }} | "
      "ForEach-Object {{ '{{0}}|{{1}}|{{2}}|{{3}}' -f $_.ProcessId, $_.PrivatePageCount, ($_.KernelModeTime + $_.UserModeTime), $_.CommandLine }}")
EXE = "chrome.exe"  # (firefox.exe with --firefox)


def kind_of(cmd):
    """renderer, gpu, browser or other, from a process's command line (Chromium's --type=, Firefox's last word)."""
    if "-contentproc" in cmd:  # (Firefox: "... tab", "... gpu", "... rdd" ...)
        k = cmd.split()[-1].strip('"')
        return "renderer" if k == "tab" else "gpu" if k == "gpu" else "other"
    m = re.search(r"--type=([\w-]+)", cmd)
    return "browser" if not m else "renderer" if m[1] == "renderer" else "gpu" if m[1] == "gpu-process" else "other"


def procs():
    """{pid: (type, private MB, CPU s)} of Playwright's browser processes (Windows; {} elsewhere)."""
    if sys.platform != "win32":
        return {}
    out = subprocess.run(["powershell", "-NoProfile", "-Command", PS.format(exe=EXE)], capture_output=True, text=True).stdout
    got = {}
    for ln in out.splitlines():
        parts = ln.split("|", 3)
        if len(parts) == 4 and parts[0].isdigit():
            got[int(parts[0])] = (kind_of(parts[3]), int(parts[1] or 0) / 1e6, int(parts[2] or 0) / 1e7)
    return got


class Watch:
    """What the page and the browser hold after each step, and the CPU spent since the last one."""

    def __init__(self, page):
        self.attach(page)
        self.t, self.cpu, self.task = time.time(), procs(), 0.0
        self.task = self.metrics().get("TaskDuration", 0)
        print(f"{'step':24} {'heap MB':>7} {'geom':>5} {'tex':>4} {'main s':>6} | {'renderer MB':>11} {'gpu MB':>6} "
              f"{'browser MB':>10} {'pages':>5} | cores busy: renderer gpu browser")

    def attach(self, page):
        self.page = page
        try:
            self.cdp = page.context.new_cdp_session(page)
        except Exception:  # (Firefox: no DevTools protocol)
            self.cdp = None

    def metrics(self):
        if not self.cdp:
            return {}
        self.cdp.send("Performance.enable")
        return {m["name"]: m["value"] for m in self.cdp.send("Performance.getMetrics")["metrics"]}

    def step(self, name):
        m, now, cur = self.metrics(), time.time(), procs()
        mem = self.page.evaluate("window.renderer ? window.renderer.info.memory : {}")
        by = {}
        for pid, (k, mb, cpu) in cur.items():
            b = by.setdefault(k, [0.0, 0.0, 0])
            b[0] += mb
            b[1] += cpu - self.cpu.get(pid, (k, 0, cpu))[2]
            b[2] += 1
        wall = now - self.t
        # (the counter starts over with each document: after a navigation the new page's whole count)
        cur_task = m.get("TaskDuration", 0)
        task, self.task = (cur_task - self.task if cur_task >= self.task else cur_task), cur_task
        busy = " ".join(f"{by.get(k, [0, 0])[1] / wall:.2f}" for k in ("renderer", "gpu", "browser"))
        print(f"{name:24} {m.get('JSHeapUsedSize', 0) / 1e6:>7.0f} {mem.get('geometries', 0):>5} {mem.get('textures', 0):>4} "
              f"{task:>6.1f} | {by.get('renderer', [0])[0]:>11.0f} {by.get('gpu', [0])[0]:>6.0f} {by.get('browser', [0])[0]:>10.0f} "
              f"{by.get('renderer', [0, 0, 0])[2]:>5} | {busy}", flush=True)
        self.t, self.cpu = now, cur


# (what the page does when it is left, src/main.js pagehide / pageshow, kept from being registered)
NO_RELEASE = """{ const add = window.addEventListener;
  window.addEventListener = function (type, ...rest) { if (type === 'pagehide' || type === 'pageshow') return; return add.call(this, type, ...rest); }; }"""


def switch(page, url, lines, times, address=False):
    """Line after line in one page, as the menu's line choice (or a new address) loads it, each with a short
    autopilot shift."""
    base = url.split("?")[0]
    menu(page, f"{base}?line={lines[0]}", 0)
    w = Watch(page)
    w.step(f"line {lines[0]} loaded")
    for r in range(times):
        for i, ln in enumerate(lines):
            if r or i:
                if address:
                    page.goto(f"{base}?line={ln}", timeout=180000)  # (as pasted into the address bar)
                else:
                    page.select_option("#selLine", ln)  # (a navigation: the page loads the other line's world)
                page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=180000)
                page.wait_for_timeout(3000)
                w.step(f"round {r + 1}: line {ln} loaded")
            page.evaluate("document.getElementById('optAuto').checked = true")
            page.click("#btnStart")
            page.wait_for_function("window.game && document.body.classList.contains('shift')", timeout=60000)
            page.wait_for_timeout(20000)
            w.step(f"round {r + 1}: line {ln} driven")
            page.evaluate("document.getElementById('btnToMenu').click()")
            page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=20000)


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
    ap.add_argument("--switch", help="lines to load in turn in one page, e.g. 17,9")
    ap.add_argument("--times", type=int, default=3, help="rounds of --switch")
    ap.add_argument("--firefox", action="store_true", help="--switch in Firefox")
    ap.add_argument("--address", action="store_true", help="--switch by a new address instead of the menu")
    ap.add_argument("--no-release", action="store_true", help="--switch without the page's release on leaving")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    faulthandler.dump_traceback_later(600 + 120 * args.runs + (240 * args.times if args.switch else 0), exit=True)
    tmp = tempfile.mkdtemp()
    feedback.DEST = tmp
    server = serve.Server(("127.0.0.1", 0), lambda *a, **k: Quiet(*a, directory=serve.ROOT, **k))
    server.identity, server.rate, server.lan = None, 0, False
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/?line={args.line}"
    fails = []
    try:
        with sync_playwright() as p:
            if args.switch and args.firefox:
                global EXE
                EXE = "firefox.exe"
                browser = p.firefox.launch(headless=False, firefox_user_prefs={"browser.sessionhistory.max_total_viewers": -1})
                name = gpu.renderer(browser)
            elif args.switch:
                # (Playwright turns the back/forward cache off; a player's Chrome keeps the left page there, and that
                # is what a line switch may pile up)
                browser = p.chromium.launch(headless=False, args=gpu.HARDWARE, ignore_default_args=["--disable-back-forward-cache"])
                name = gpu.renderer(browser)
            else:
                browser, name = gpu.launch(p, headless=not (args.headed or args.runs))
            print(f"WebGL: {name}")
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            if args.switch:
                if args.no_release:
                    page.add_init_script(NO_RELEASE)
                switch(page, url, args.switch.split(","), args.times, args.address)
                browser.close()
                return
            if args.runs:
                watch = None
                runs = []
                for i in range(args.runs):
                    # (a fresh page each run, as a player opens it; --same-page: the runs one after another in one
                    # page, which shows what a page carries over from shift to shift)
                    if i == 0 or not args.same_page:
                        if i:
                            page.close()
                            page = browser.new_page(viewport={"width": 1280, "height": 720})
                        menu(page, url, 0)
                        if watch:
                            watch.attach(page)
                    watch = watch or Watch(page)
                    r = perf_test(page, 120000)
                    runs.append(r)
                    print(f"run {i + 1}: {r['fps']} fps, over 20/33/50 ms {r['over']['20']}/{r['over']['33']}/{r['over']['50']} %, "
                          f"p50/p90/p99 {r['ms']['p50']}/{r['ms']['p90']}/{r['ms']['p99']} ms, gpu {r.get('gpuMs')} ms, "
                          f"{r['calls']['mean']} calls, {r['triangles']['mean'] / 1e6:.2f} M triangles, heap {r.get('heapMB')} MB")
                    watch.step(f"run {i + 1}")
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
            # the reference run from another line: line 17 with the detailed model, then back to the line left
            page.click("#ptMenu")
            page.goto(url.split("?")[0] + "?line=9", timeout=180000)
            page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=180000)
            page.evaluate("document.getElementById('optModel').value = 'simple'")
            page.click("#btnPerfRef")
            page.wait_for_function("window.perfTestResult", timeout=240000)
            ref = page.evaluate("window.perfTestResult")
            ref_title = page.text_content("#resultsCard h1")
            page.click("#ptMenu")
            page.wait_for_function("!document.getElementById('menu').classList.contains('hidden') && document.getElementById('selLine')", timeout=180000)
            back = page.evaluate("new URLSearchParams(location.search).get('line')")
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
    if not (ref.get("reference") and str(ref.get("line")) == "17" and ref.get("model") == "hybrid" and ref.get("frames", 0) > 10):
        fails.append(f"the reference run is not line 17 with the detailed model: {ref}")
    if ref.get("stop") != "Palackého náměstí":
        fails.append(f"the reference run starts at {ref.get('stop')!r}, not Palackého náměstí")
    # (10 s before the departure, measured from 5 s on for 8 s: the tram leaves within the run)
    if not (res.get("driven", 0) > 5 and ref.get("driven", 0) > 5):
        fails.append(f"the tram stood through the test: driven {res.get('driven')} m, the reference {ref.get('driven')} m")
    if "17" not in (ref_title or "") or back != "9":
        fails.append(f"the reference run: title {ref_title!r}, back on line {back!r} (wants 9)")
    if fails:
        sys.exit("; ".join(fails))
    print("perf: a note carries the machine, load times and frame log; the test drives, shows and sends; the reference "
          "runs line 17 detailed and goes back: pass")


if __name__ == "__main__":
    main()
