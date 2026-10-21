"""Static dev server with caching disabled (so edited ES modules reload)."""
import http.server
import os
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8737
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class NoCache(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


http.server.ThreadingHTTPServer(("127.0.0.1", PORT), NoCache).serve_forever()
