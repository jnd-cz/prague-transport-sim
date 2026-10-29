# Static file server for this deployment copy (the project's tools/serve.py is not here):
# python -I .claude/serve_nocache.py 8743 [KB/s]  -- serves the current directory, never cached;
# with a rate, each response is sent no faster than that (to try the loading screen on a slow line)
import shutil
import sys
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8743
rate = float(sys.argv[2]) * 1024 if len(sys.argv) > 2 else 0


class NoCache(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def copyfile(self, source, outputfile):
        if not rate:
            return shutil.copyfileobj(source, outputfile)
        chunk = max(1024, int(rate / 10))
        while data := source.read(chunk):
            outputfile.write(data)
            time.sleep(len(data) / rate)


ThreadingHTTPServer(('127.0.0.1', port), partial(NoCache, directory='.')).serve_forever()
