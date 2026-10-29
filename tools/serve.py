"""Static dev server with caching disabled (so edited ES modules reload).

    python tools/serve.py 8742          # the project root on http://localhost:8742
    python tools/serve.py 8744 1500     # each response sent no faster than 1500 KB/s (the loading screen
                                        # on a slow connection; from the remote session's serve_nocache.py)
"""
import http.server
import os
import re
import shutil
import sys
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8737
RATE = float(sys.argv[2]) * 1024 if len(sys.argv) > 2 else 0  # bytes per second, 0 = no limit
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class NoCache(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def copyfile(self, source, outputfile):
        if not RATE:
            return shutil.copyfileobj(source, outputfile)
        chunk = max(1024, int(RATE / 10))
        while data := source.read(chunk):
            outputfile.write(data)
            time.sleep(len(data) / RATE)

    def do_POST(self):
        """Lint reports from the page: POST /report/<name>.json -> reports/<name>.json (local only)."""
        name = os.path.basename(self.path)
        if not self.path.startswith("/report/") or not re.fullmatch(r"[\w.-]+\.json", name):
            self.send_error(404)
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        os.makedirs("reports", exist_ok=True)
        with open(os.path.join("reports", name), "wb") as fh:
            fh.write(body)
        self.send_response(204)
        self.end_headers()


class Server(http.server.ThreadingHTTPServer):
    # (the default backlog of 5 overflows when headless.py --jobs loads several pages at once, and on
    # Windows a full backlog refuses the connection: every page then hung on "Loading the 3D engine")
    request_queue_size = 128


Server(("127.0.0.1", PORT), NoCache).serve_forever()
