# SPDX-License-Identifier: AGPL-3.0-or-later
"""src/loading.js on responses as the test host sends them (#275), and what its screen says when the page stops (#371):
python -P -E tools/test_loading.py
For the sizes the page comes from a small server on a free port: src/ from this checkout, and a data manifest and files
the test holds. The files stop halfway until the test lets them go, so it can read the sizes during the download.
For the messages it is the game's own page from tools/serve.py, with one file answered badly."""
import faulthandler
import http.server
import json
import os
import sys
import threading

import brotli
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from headless import serve, stop_server  # noqa: E402
import gpu  # noqa: E402  (Chromium on the GPU where it has one, #463)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BODY = bytes(i % 251 for i in range(300000))
PACKED = brotli.compress(BODY, quality=5)
MANIFEST = json.dumps({"files": {"packed.bin": {"size": len(BODY), "sha256": "0"}}}).encode()
release = threading.Event()
NAME = "loading.test"  # plain http at a name that is not this machine: not a secure context
LINE_FILE = "**/data/line23.json"
SHOT = os.environ.get("TRAM_LOADING_SHOT")  # (a picture of the https message goes here, for a PR)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, body, ctype, encoding=None):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if encoding:
            self.send_header("Content-Encoding", encoding)
        self.end_headers()
        if ctype != "application/octet-stream":
            self.wfile.write(body)
            return
        self.wfile.write(body[:len(body) // 2])
        self.wfile.flush()
        release.wait(60)
        self.wfile.write(body[len(body) // 2:])

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self.send(b"<!doctype html><title>t</title>", "text/html")
        elif path == "/data/MANIFEST.json":
            self.send(MANIFEST, "application/json")
        elif path == "/data/packed.bin":
            self.send(PACKED, "application/octet-stream", "br")
        elif path == "/data/notlisted.bin":
            self.send(PACKED, "application/octet-stream", "br")
        elif path == "/data/plain.bin":
            self.send(BODY, "application/octet-stream")
        elif path.startswith("/src/") and path.endswith(".js"):
            with open(os.path.join(ROOT, *path.split("/")), "rb") as f:
                self.send(f.read(), "text/javascript")
        else:
            self.send_error(404)


def messages(pw, check):
    """The screen when the page stops: a file that arrives as raw bytes, is refused or is not there, a build that throws,
    a module that does not arrive; and a normal load, which says none of it."""
    srv, url = serve(0)
    other = url.replace("127.0.0.1", NAME)
    b = gpu.launch(pw, args=[f"--host-resolver-rules=MAP {NAME} 127.0.0.1"])[0]

    def stopped(routes, base=url, locale="en-US", shot=None):
        ctx = b.new_context(locale=locale, viewport={"width": 1000, "height": 700})
        try:
            page = ctx.new_page()
            for pattern, handler in routes.items():
                page.route(pattern, handler)
            page.goto(f"{base}/?line=23")
            page.wait_for_function("['Cannot start', 'Nelze spustit'].includes(document.getElementById('loadPct')?.textContent)", timeout=60000)
            if shot:
                page.wait_for_timeout(1000)  # (the other files in their rows)
                page.screenshot(path=shot)
            return page.evaluate("""() => ({ title: document.getElementById('loadPct').textContent,
              message: document.getElementById('loadStep').textContent,
              link: document.querySelector('#loadStep a')?.href ?? null,
              shown: !document.getElementById('loading').classList.contains('hidden'),
              rows: Object.fromEntries([...document.querySelectorAll('#loadFiles tr')].map((r) => [r.children[0].textContent, r.children[2].textContent])) })""")
        finally:
            ctx.close()

    raw = lambda route: route.fulfill(status=200, body=b"\x1b\xff\x00 a packed file nobody unpacked", content_type="application/json")
    refused = lambda route: route.abort("failed")
    gone = lambda route: route.fulfill(status=404, body="missing")
    broken = lambda route: route.fulfill(status=200, body='{"line": "23"}', content_type="application/json")
    try:
        s = stopped({LINE_FILE: raw})
        check("raw bytes: the screen says stopped", s["title"] == "Cannot start" and s["shown"])
        check("raw bytes: it names the file and not the bytes", "data/line23.json could not be read" in s["message"] and "packed file" not in s["message"])
        check("http on this machine is no reason to go to https", s["link"] is None and "Reload the page" in s["message"])
        s = stopped({LINE_FILE: raw}, base=other, shot=SHOT)
        check("raw bytes over http: open it over https, not reload", "only over https" in s["message"] and "Reload the page" not in s["message"])
        check("raw bytes over http: the link keeps the address", s["link"] == other.replace("http:", "https:") + "/?line=23")
        s = stopped({LINE_FILE: refused}, base=other)
        check("a refused file over http leads to https too", "data/line23.json did not load" in s["message"] and (s["link"] or "").startswith("https://"))
        check("its row says failed", s["rows"].get("line23.json") == "failed")
        s = stopped({LINE_FILE: gone}, base=other)
        check("a file the server does not have stays that", "data/line23.json did not load" in s["message"] and s["link"] is None)
        s = stopped({LINE_FILE: broken})
        check("an error in the build reaches the screen", s["title"] == "Cannot start" and "Reload the page" in s["message"] and len(s["message"]) > len("Reload the page; if it persists, report this message."))
        s = stopped({"**/src/report.js": refused})
        check("a module that does not arrive", s["title"] == "Cannot start" and "code did not load" in s["message"])
        s = stopped({LINE_FILE: raw}, base=other, locale="cs-CZ")
        check("Czech: the file", s["title"] == "Nelze spustit" and "Soubor data/line23.json nejde přečíst" in s["message"] and "Otevřít přes https" in s["message"])
        s = stopped({"**/src/report.js": refused}, locale="cs-CZ")
        check("Czech: the module", s["title"] == "Nelze spustit" and "Kód hry se nenačetl" in s["message"])
        if os.path.exists(os.path.join(ROOT, "data/line23.json")):
            page = b.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"{url}/?line=23")
            page.wait_for_function("document.getElementById('loading').classList.contains('hidden')", timeout=240000)
            check("a normal load says nothing", page.locator("#loadPct").inner_text() != "Cannot start" and not errors)
            page.evaluate("setTimeout(() => { throw new Error('after the load'); })")
            page.wait_for_timeout(300)
            check("a later error does not bring the screen back", page.evaluate("document.getElementById('loading').classList.contains('hidden')"))
            page.close()
        else:
            print("skip a normal load: needs data/line23.json (python -I tools/snapshot.py data-fetch)")
    finally:
        b.close()
        stop_server(srv)


def main():
    faulthandler.dump_traceback_later(420, exit=True)  # (page.evaluate has no time limit)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fails = []

    def check(what, ok):
        print(("ok   " if ok else "FAIL ") + what)
        if not ok:
            fails.append(what)

    with sync_playwright() as p:
        b = gpu.launch(p)[0]
        page = b.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{server.server_address[1]}/")
        page.evaluate("""async () => {
          const { Loader } = await import('/src/loading.js');
          const l = window.l = new Loader();
          for (const f of ['packed', 'notlisted', 'plain']) l.prefetch(`data/${f}.bin`);
        }""")
        page.wait_for_function("""async () => { await window.l.sizes;
          return [...window.l.files.values()].every((d) => d.state === 'load') && window.l.files.get('data/packed.bin').total > 0; }""", timeout=30000)
        got = page.evaluate("() => Object.fromEntries([...window.l.files].map(([u, d]) => [u.slice(5, -4), { total: d.total, state: d.state }]))")
        check("a compressed file takes its real size from the manifest", got["packed"]["total"] == len(BODY))
        check("a compressed file the manifest does not list stays unknown", got["notlisted"]["total"] == 0)
        check("a plain file takes its Content-Length", got["plain"]["total"] == len(BODY))
        check("the bar is under way, not full", 0 <= page.evaluate("() => window.l.fraction()") < 1)
        release.set()
        done = page.evaluate("""async () => { const out = {};
          for (const [u, d] of window.l.files) { const buf = await d.promise; out[u.slice(5, -4)] = { n: buf.length, total: d.total, state: d.state, sum: buf.reduce((a, x) => a + x, 0) }; }
          return out; }""")
        want = sum(BODY)
        for f in ("packed", "notlisted", "plain"):
            check(f"{f}: whole and readable, its total the real size", done[f] == {"n": len(BODY), "total": len(BODY), "state": "done", "sum": want})
        check("no page errors", not errors)
        got = page.evaluate("""async () => {
          const { Loader } = await import('/src/loading.js');
          const l = new Loader();
          l.prefetch('data/none.bin');
          const waiting = l.fraction();
          l.files.get('data/none.bin').state = 'error';
          const nothing = l.fraction();
          dispatchEvent(new ErrorEvent('error', { message: 'ResizeObserver loop completed with undelivered notifications' }));
          return { waiting, nothing, failed: !!l.failed };
        }""")
        check("the bar has a number before the first byte", got["waiting"] == 0)
        check("and when no file arrived", abs(got["nothing"] - 0.05) < 1e-9)
        check("a browser's notice stops nothing", not got["failed"])
        b.close()
        messages(p, check)
    server.shutdown()
    print(f"{len(fails)} failed" if fails else "all passed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
