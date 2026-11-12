# SPDX-License-Identifier: AGPL-3.0-or-later
"""The review directory (reviews.html, src/reviewIndex.js, #288) on a phone-sized and a desktop page:
python -P -E tools/test_review_index.py
The page comes from tools/serve.py's handler on a free port; the index, the sets and the answer store are
fixtures the test serves (nothing written). Then the page once more with the real sets of
reports/review/ (tools/review_sets.py, without GitHub) and no answers: every set counted, no page error."""
import faulthandler
import json
import os
import sys
import threading

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import review_sets  # noqa: E402
import serve  # noqa: E402
import gpu  # noqa: E402  (Chromium on the GPU where it has one, #463)

A = {"issue": 258, "findings": [{"x": 1.0, "y": 2.0, "kind": "stop"}, {"x": 3.0, "y": 4.0, "kind": "stop"}, {"x": 5.0, "y": 6.0, "kind": "stop"}]}
# (the second answered in data/truth.json, not on the page: #379)
B = {"issue": 106, "findings": [{"x": 7.0, "y": 8.0, "kind": "z"},
                                {"x": 7.5, "y": 8.5, "kind": "z", "recorded": {"v": "archive profile ok", "t": 5, "source": "data/truth.json"}}]}
OLD = {"issue": 107, "findings": [{"x": 9.0, "y": 9.0, "kind": "old"}]}  # (its issue closed, nothing answered: out of date)
# (the deploy's time from version.json, #386: the index carries none)
VERSION = {"commit": "abc1234", "deployed": "2026-11-05T15:00:42+01:00"}
INDEX = {"commit": "abc1234", "repo": "jnd-cz/prague-transport-sim", "lines": ["9", "17"],
         "sets": [{"file": "reports/review/test-a.json", "title": "Stop signs, line 17", "issue": 258, "waitsFor": 258,
                   "issueInfo": {"title": "Stop point at the stop sign", "state": "OPEN"}, "waitsForInfo": {"title": "Stop point at the stop sign", "state": "OPEN"},
                   "lines": ["17"], "findings": 3, "unknown": []},
                  {"file": "reports/review/test-b.json", "title": None, "issue": 106, "waitsFor": 106,
                   "issueInfo": {"title": "Track z", "state": "CLOSED"}, "waitsForInfo": {"title": "Track z", "state": "CLOSED"},
                   "lines": ["9"], "findings": 2, "unknown": []},
                  {"file": "reports/review/test-old.json", "title": "Old", "issue": 107, "waitsFor": 107,
                   "issueInfo": {"title": "Done long ago", "state": "CLOSED"}, "waitsForInfo": {"title": "Done long ago", "state": "CLOSED"},
                   "lines": ["9"], "findings": 1, "unknown": []},
                  {"file": "reports/review/test-gone.json", "title": "Gone", "issue": None, "waitsFor": None, "issueInfo": None,
                   "waitsForInfo": None, "lines": [], "findings": 2, "unknown": ["issue", "lines"]},
                  # (#334: no file of its own, counted from the ids)
                  {"file": "data/line17.dtm.json", "title": "Kerb review list", "issue": 142, "waitsFor": 142,
                   "issueInfo": {"title": "Kerbs", "state": "OPEN"}, "waitsForInfo": {"title": "Kerbs", "state": "OPEN"},
                   "lines": ["17"], "findings": 2, "unknown": [], "ids": ["kerbs|sidewalk foot|1.0,2.0", "kerbs|island top|3.0,4.0"]}],
         "questions": [{"pr": 270, "title": "Wheel spin and sand", "url": "https://github.com/jnd-cz/prague-transport-sim/pull/270",
                        "draft": True, "sections": [{"title": "Questions for the user", "items": ["**Autumn costs time:** `3-5 min`"]}]}]}
# answers as review mode stores them (src/reviewFindings.js fid: file|kind|x,y), in the line each set was opened with
STORES = {"line17": {"items": {"file|stop|1.0,2.0": {"v": "right", "t": 1}, "file|stop|3.0,4.0": {"v": "unsure", "note": "hm", "t": 2},
                               "kerbs|sidewalk foot|1.0,2.0": {"v": "matches reality", "t": 1}}},
          "line9": {"items": {"file|z|7.0,8.0": {"v": "ok", "t": 1}}}}


class Quiet(serve.NoCache):
    def log_message(self, *args):
        pass


def fulfil(page, files, stores):
    def handle(route):
        path = route.request.url.split("/", 3)[3].split("?")[0]
        if path.startswith("review.php"):
            return route.fulfill(status=404, body="")
        if path.startswith("reports/reviews/"):
            name = os.path.basename(path)[:-5]
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(stores.get(name, {})))
        if path in files:
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(files[path]))
        if path.startswith("reports/review/") and path not in files and files.get("_only"):
            return route.fulfill(status=404, body="")
        return route.continue_()
    page.route("**/*", handle)


def main():
    faulthandler.dump_traceback_later(300, exit=True)  # (page.evaluate has no time limit)
    server = serve.Server(("127.0.0.1", 0), lambda *a, **k: Quiet(*a, directory=serve.ROOT, **k))
    server.identity, server.rate, server.lan = None, 0, False
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/reviews.html"
    fails = []

    def check(what, ok):
        print(("ok   " if ok else "FAIL ") + what)
        if not ok:
            fails.append(what)

    with sync_playwright() as p:
        b = gpu.launch(p)[0]
        for size in ({"width": 390, "height": 844}, {"width": 1280, "height": 800}):
            page = b.new_page(viewport=size)
            errors = []
            page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
            fulfil(page, {"reports/review/index.json": INDEX, "reports/review/test-a.json": A, "reports/review/test-b.json": B,
                          "reports/review/test-old.json": OLD, "data/line17.dtm.json": {"findings": []}, "version.json": VERSION,
                          "_only": True}, STORES)
            page.goto(url)
            page.wait_for_function("() => window.reviewIndex", timeout=30000)
            sets = page.evaluate("() => window.reviewIndex.sets.map((s) => [s.file.split('/').pop(), s.c || null, s.error || null])")
            c = {n: (cc, err) for n, cc, err in sets}
            w = size["width"]
            check(f"{w}: set A counted (3 findings, 2 answered, 1 unsure, 1 note)",
                  c["test-a.json"][0] == {"total": 3, "answered": 2, "unsure": 1, "noted": 1, "waiting": 1})
            check(f"{w}: set B answered in line 9's store and in data/truth.json",
                  c["test-b.json"][0] == {"total": 2, "answered": 2, "unsure": 0, "noted": 0, "waiting": 0})
            check(f"{w}: a missing set shows its error", c["test-gone.json"][1] == "HTTP 404")
            waiting = page.inner_html("#waiting")
            check(f"{w}: A's link opens line 17 with only the unanswered", 'href="index.html?line=17&amp;review=reports%2Freview%2Ftest-a.json&amp;todo"' in waiting)
            check(f"{w}: the kerb list counted from its ids, not its survey file",
                  c["line17.dtm.json"][0] == {"total": 2, "answered": 1, "unsure": 0, "noted": 0, "waiting": 1})
            check(f"{w}: its link opens line 17's review mode with only the unanswered", 'href="index.html?line=17&amp;review&amp;todo"' in waiting)
            check(f"{w}: A under its issue, with its title and state", "#258</a> Stop point at the stop sign" in waiting and ">open<" in waiting)
            check(f"{w}: an unknown issue and lines are said", "No issue known" in waiting and "unknown: issue, lines" in waiting)
            answered = page.inner_html("#answered")
            check(f"{w}: B among the answered, its closed issue marked", "test-b.json" in answered and "CLOSED" in answered and "test-b.json" not in waiting)
            q = page.inner_html("#questions")
            check(f"{w}: the PR's question without its Markdown", "PR #270" in q and "Autumn costs time: 3-5 min" in q and "**" not in q)
            check(f"{w}: the status sums the waiting, not the out of date", "2 findings waiting in 3 of 5 sets" in page.inner_text("#status"))
            check(f"{w}: the deploy's time from version.json", "index of the deploy of 2026-11-05 15:00 (abc1234)" in page.inner_text("#status")
                  and "at the deploy of 2026-11-05 15:00" in q)
            old = page.evaluate("() => window.reviewIndex.old")
            check(f"{w}: a set with a closed issue and findings waiting is out of date",
                  old == ["reports/review/test-old.json"] and "Out of date" in waiting and waiting.index("test-old.json") > waiting.index("Out of date"))
            check(f"{w}: no sideways scroll", page.evaluate("() => document.documentElement.scrollWidth <= innerWidth"))
            check(f"{w}: no page errors", not errors)
            page.close()
        # the real sets, no answers
        index = review_sets.build(github=False)
        page = b.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        fulfil(page, {"reports/review/index.json": index}, {})
        page.goto(url)
        page.wait_for_function("() => window.reviewIndex", timeout=120000)
        real = page.evaluate("() => window.reviewIndex.sets.map((s) => [s.file, s.findings, s.c && s.c.total, s.error || null])")
        check(f"the real sets: all {len(index['sets'])} read", len(real) == len(index["sets"]) and not any(r[3] for r in real))
        check("the real sets: the page counts what the index lists", all(r[1] == r[2] for r in real))
        heights = page.evaluate("() => window.reviewIndex.sets.find((s) => s.file.endsWith('/track-heights.json'))?.c")
        check(f"the real track-height decisions are answered in data/truth.json: {heights}", heights and heights["waiting"] == 0)
        check("the real sets: no page errors", not errors)
        status = page.inner_text("#status")
        check(f"the real sets without version.json (tools/serve.py): the commit alone: {status!r}",
              f"index ({index['commit']})" in status and "deploy of" not in status)
        b.close()
    server.shutdown()
    print(f"{len(fails)} failed" if fails else "all passed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
