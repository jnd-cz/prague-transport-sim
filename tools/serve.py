"""Static dev server with caching disabled (so edited ES modules reload)."""
import http.server
import os
import re
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8737
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class NoCache(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

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


http.server.ThreadingHTTPServer(("127.0.0.1", PORT), NoCache).serve_forever()
