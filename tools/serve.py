"""Static dev server with caching disabled (so edited ES modules reload).

    python tools/serve.py 8742          # the project root on http://localhost:8742
    python tools/serve.py 8744 1500     # each response sent no faster than 1500 KB/s (the loading screen
                                        # on a slow connection; from the remote session's serve_nocache.py)
    python tools/serve.py 8742 --lan    # also to the home network (a phone: review mode, #129): only what
                                        # the game loads, read-only apart from review verdicts;
                                        # prints the address to open
"""
import argparse
import functools
import http.server
import json
import os
import posixpath
import re
import shutil
import socket
import sys
import threading
import time
from pathlib import Path
from urllib.parse import unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reviews  # noqa: E402


# what --lan serves: the game and its data, not the sources in raw/, .git or the tools' caches
LAN_TOP = {"", "index.html", "src", "assets", "data", "tools", "reports", "favicon.ico"}


class NoCache(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        # (the first segment after normalising: /src/../raw/x is raw)
        top = posixpath.normpath(unquote(self.path.split("?", 1)[0].split("#", 1)[0])).lstrip("/").split("/")[0]
        if self.server.lan and top not in LAN_TOP:
            self.send_error(404)
            return None
        return super().send_head()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        if self.server.identity:
            self.send_header("X-Tram-Server-Identity", self.server.identity)
        super().end_headers()

    def copyfile(self, source, outputfile):
        rate = self.server.rate
        if not rate:
            return shutil.copyfileobj(source, outputfile)
        chunk = max(1024, int(rate / 10))
        while data := source.read(chunk):
            outputfile.write(data)
            time.sleep(len(data) / rate)

    def do_POST(self):
        """Lint reports from the page: POST /report/<name>.json -> reports/<name>.json (local only).
        Review verdicts (#136): POST /review/<name>.json merges into reports/reviews/<name>.json, also
        from the home network (with the page's X-Review header, which no cross-site form sends)."""
        name = os.path.basename(self.path)
        if self.path.startswith("/review/"):
            n = int(self.headers.get("Content-Length", 0))
            if not self.headers.get("X-Review") or not reviews.NAME.fullmatch(name.removesuffix(".json")) or n > reviews.MAX:
                self.send_error(400)
                return
            try:
                new = json.loads(self.rfile.read(n))
            except ValueError:
                self.send_error(400)
                return
            path = os.path.join(REVIEWS, name)
            with REVIEW_LOCK:
                out = reviews.merge(reviews.load(path), new if isinstance(new, dict) else {})
                reviews.save(path, out)
            body = json.dumps({"ok": True, "items": len(out["items"])}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.server.lan or not self.path.startswith("/report/") or not re.fullmatch(r"[\w.-]+\.json", name):
            self.send_error(404)
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        os.makedirs("reports", exist_ok=True)
        with open(os.path.join("reports", name), "wb") as fh:
            fh.write(body)
        self.send_response(204)
        self.end_headers()


REVIEWS = os.path.join(ROOT, "reports", "reviews")
REVIEW_LOCK = threading.Lock()


class Server(http.server.ThreadingHTTPServer):
    # (the default backlog of 5 overflows when headless.py --jobs loads several pages at once, and on
    # Windows a full backlog refuses the connection: every page then hung on "Loading the 3D engine")
    request_queue_size = 128
    # POSIX reuse permits restart after TIME_WAIT, not a second active listener. On Windows use
    # exclusive ownership instead: SO_REUSEADDR there can allow two listeners on one port.
    allow_reuse_address = not hasattr(socket, 'SO_EXCLUSIVEADDRUSE')

    def server_bind(self):
        # Windows SO_REUSEADDR can allow two listeners on one port. Never share a dev server's socket.
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('port', type=int, nargs='?', default=8737)
    ap.add_argument('rate', type=float, nargs='?', default=0)
    ap.add_argument('--lan', action='store_true', help='listen on every interface, read-only, the game files only')
    ap.add_argument('--identity', help=argparse.SUPPRESS)
    ap.add_argument('--ready-file', type=Path, help=argparse.SUPPRESS)
    args = ap.parse_args()
    ready = {'identity': args.identity, 'pid': os.getpid(), 'root': ROOT}

    def announce(value):
        if args.ready_file:
            tmp = args.ready_file.with_suffix('.part')
            tmp.write_text(json.dumps(value), encoding='utf-8')
            os.replace(tmp, args.ready_file)

    try:
        host = '0.0.0.0' if args.lan else '127.0.0.1'
        server = Server((host, args.port), functools.partial(NoCache, directory=ROOT))
    except OSError as e:
        announce({**ready, 'error': f'cannot bind {host}:{args.port}: {e}'})
        raise SystemExit(str(e)) from e
    server.identity, server.rate, server.lan = args.identity, args.rate * 1024, args.lan
    if args.lan:
        # (the address other devices reach: the interface that would route outwards; nothing is sent)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            try:
                s.connect(('10.255.255.255', 1))
                ip = s.getsockname()[0]
            except OSError:
                ip = '<this computer>'
        print(f'on the home network: http://{ip}:{server.server_port}/?review (read-only, review verdicts saved)', flush=True)
    # POST reports are relative to this checkout too, independent of the caller's cwd.
    os.chdir(ROOT)
    with server:
        announce({**ready, 'port': server.server_port})
        server.serve_forever()


if __name__ == '__main__':
    main()
