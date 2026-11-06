"""src/loading.js on responses as the test host sends them (#275): python -P -E tools/test_loading.py
The page comes from a small server on a free port: src/ from this checkout, and a data manifest and files the test
holds. The files stop halfway until the test lets them go, so it can read the sizes during the download."""
import faulthandler
import http.server
import json
import os
import sys
import threading

import brotli
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BODY = bytes(i % 251 for i in range(300000))
PACKED = brotli.compress(BODY, quality=5)
MANIFEST = json.dumps({"files": {"packed.bin": {"size": len(BODY), "sha256": "0"}}}).encode()
release = threading.Event()


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


def main():
    faulthandler.dump_traceback_later(120, exit=True)  # (page.evaluate has no time limit)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fails = []

    def check(what, ok):
        print(("ok   " if ok else "FAIL ") + what)
        if not ok:
            fails.append(what)

    with sync_playwright() as p:
        b = p.chromium.launch()
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
        b.close()
    server.shutdown()
    print(f"{len(fails)} failed" if fails else "all passed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
