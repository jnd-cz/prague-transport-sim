# SPDX-License-Identifier: AGPL-3.0-or-later
"""The project's overview page (overview.html, src/overview.js, #826) at phone and desktop width:
python -P -E tools/test_overview_page.py [--shots DIR]
A real snapshot (tools/overview.py, without uploading) and the real review sets (tools/review_sets.py, without GitHub,
no answers), served by the test on a free port (nothing written in the checkout): every section in its order, the
review sets counted, no sideways scroll, no page error. Then a made-up snapshot: an old one shows red, and a title
with markup stays text. --shots saves a full page at each width (the PR's pictures)."""
import copy
import faulthandler
import json
import os
import sys
import threading
import time

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gpu  # noqa: E402  (Chromium on the GPU where it has one, #463)
import overview  # noqa: E402
import review_sets  # noqa: E402
import serve  # noqa: E402

EVIL = '<img src=x onerror="window.pwned=1">'


class Quiet(serve.NoCache):
    def log_message(self, *args):
        pass


def route(page, files):
    def handle(r):
        path = r.request.url.split("/", 3)[3].split("?")[0]
        if path in files:
            return r.fulfill(status=200, content_type="application/json", body=json.dumps(files[path]))
        if path.startswith(("review.php", "reports/reviews/")):
            return r.fulfill(status=404, body="")
        return r.continue_()
    page.route("**/*", handle)


def main():
    faulthandler.dump_traceback_later(300, exit=True)  # (page.evaluate has no time limit)
    shots = sys.argv[sys.argv.index("--shots") + 1] if "--shots" in sys.argv else None
    snap = overview.snapshot()
    index = review_sets.build(github=False)
    server = serve.Server(("127.0.0.1", 0), lambda *a, **k: Quiet(*a, directory=serve.ROOT, **k))
    server.identity, server.rate, server.lan = None, 0, False
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/overview.html"
    fails = []

    def check(what, ok):
        print(("ok   " if ok else "FAIL ") + what)
        if not ok:
            fails.append(what)

    def open_page(b, size, s):
        page = b.new_page(viewport=size)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        route(page, {"overview.json": s, "reports/review/index.json": index})
        page.goto(url)
        page.wait_for_function("() => window.overview && !document.querySelector('#ov-waiting').textContent.includes('counting')",
                               timeout=60000)
        return page, errors

    with sync_playwright() as p:
        b = gpu.launch(p)[0]
        for size in ({"width": 390, "height": 844}, {"width": 1280, "height": 900}):
            w = size["width"]
            page, errors = open_page(b, size, snap)
            heads = page.eval_on_selector_all("h2", "hs => hs.map(h => h.textContent)")
            order = ["Waiting for you", "Heavy jobs", "Sessions", "The board"]
            check(f"{w}: the sections in order: {heads}", [next((i for i, o in enumerate(order) if h.startswith(o)), -1) for h in heads] == [0, 1, 2, 3])
            status = page.inner_text("#status")
            check(f"{w}: the snapshot's age and main's commit: {status!r}", status.startswith("updated") and snap["main"]["commit"][:7] in status)
            check(f"{w}: fresh, not red", page.get_attribute("#status", "class") == "dim")
            jobs = page.locator("#ov-heavy .card").count()
            check(f"{w}: a card per heavy job ({jobs})", jobs == len(snap["heavy"]["jobs"]))
            cards = page.locator("#ov-sessions .card").count()
            check(f"{w}: a card per session ({cards})", cards == len(snap["sessions"]))
            rows = page.locator("#ov-board .card").count()
            check(f"{w}: a card per board row ({rows})", rows == len(snap["board"]["rows"]))
            waiting = page.inner_text("#ov-waiting")
            check(f"{w}: the review sets counted", "did not load" not in waiting and ("findings in" in waiting or "no findings wait" in waiting))
            for q in snap["waiting"]["questions"]:
                check(f"{w}: PR #{q['pr']}'s questions listed", f"PR #{q['pr']}" in waiting)
            check(f"{w}: no sideways scroll", page.evaluate("() => document.documentElement.scrollWidth <= innerWidth"))
            check(f"{w}: no page errors: {errors}", not errors)
            if shots:
                os.makedirs(shots, exist_ok=True)
                page.screenshot(path=os.path.join(shots, f"overview-{w}.png"), full_page=True)
            page.close()
        # an old snapshot, and text with markup in it
        old = copy.deepcopy(snap)
        old["time"] = time.time() - 20 * 60
        old["waiting"]["needsUser"] = [{"number": 1, "title": EVIL}]
        old["board"]["rows"] = old["board"]["rows"][:1] + [{**old["board"]["rows"][0], "issueTitle": EVIL, "branch": EVIL}]
        page, errors = open_page(b, {"width": 390, "height": 844}, old)
        check("an old snapshot shows red, saying why", page.get_attribute("#status", "class") == "old"
              and "the build PC is off or its loop stopped" in page.inner_text("#status"))
        check("markup in the data stays text", page.locator("img").count() == 0 and EVIL in page.inner_text("#ov-waiting")
              and not page.evaluate("() => window.pwned"))
        check("no page errors", not errors)
        b.close()
    server.shutdown()
    print(f"{len(fails)} failed" if fails else "all passed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
