"""Server ownership regressions (#116): python -P -E tools/test_headless_server.py."""
from contextlib import contextmanager, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
from pathlib import Path
import shutil
import sys
import tempfile
from threading import Thread
import time
import unittest
from unittest.mock import patch
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
import headless

SERVE = Path(__file__).with_name('serve.py')


@contextmanager
def fixture_listener():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'foreign fixture')

        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread = Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        yield server.server_port, f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def read(url):
    with urllib.request.urlopen(url+'/index.html',timeout=2) as response:
        return response.read(), response.headers.get('X-Tram-Server-Identity')


class Ownership(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def checkout(self, name, body):
        root = self.root / name
        (root/'tools').mkdir(parents=True)
        shutil.copyfile(SERVE,root/'tools/serve.py')
        (root/'index.html').write_text(body,encoding='utf-8')
        return root

    def start(self, root, port=0, **kw):
        with patch.object(headless,'ROOT',str(root)):
            return headless.serve(port,**kw)

    def test_free_port_serves_target_checkout_and_cleanup_reaps_child(self):
        root = self.checkout('target checkout','target index')
        child, url = self.start(root)
        try:
            body, identity = read(url)
            self.assertEqual(body,b'target index')
            self.assertTrue(identity)
            self.assertIsNone(child.poll())
            self.assertNotIn(':0',url)
        finally:
            headless.stop_server(child)
        self.assertIsNotNone(child.poll())
        with self.assertRaises(OSError):
            read(url)

    def test_two_automatic_ports_have_distinct_launch_identities(self):
        root = self.checkout('target','index')
        a, first = self.start(root)
        try:
            b, second = self.start(root)
            try:
                self.assertNotEqual(first,second)
                self.assertNotEqual(read(first)[1],read(second)[1])
            finally:
                headless.stop_server(b)
        finally:
            headless.stop_server(a)

    def test_occupied_port_fails_before_jobs_or_baseline_writes(self):
        root = self.checkout('target','target index')
        baseline = root/'baseline.json'
        baseline.write_bytes(b'unchanged baseline')
        out = root/'results'
        with fixture_listener() as (port,url):
            argv = ['headless.py','--lines','17','--checks','lint','--jobs','1','--baseline',
                    '--port',str(port),'--out',str(out)]
            with patch.object(headless,'ROOT',str(root)), patch.object(headless,'BASELINE',str(baseline)), \
                    patch.object(sys,'argv',argv), patch.object(headless,'git',return_value=None), \
                    patch.object(headless,'data_matches',return_value=[]), patch.object(headless,'worker') as worker:
                with self.assertRaises(SystemExit) as error:
                    headless.main()
                self.assertIn('cannot bind',str(error.exception))
                worker.assert_not_called()
            self.assertEqual(baseline.read_bytes(),b'unchanged baseline')
            self.assertFalse(out.exists())
            self.assertEqual(read(url)[0],b'foreign fixture')

    def test_other_checkout_server_survives_collision(self):
        other = self.checkout('other checkout','other index')
        target = self.checkout('target checkout','target index')
        child, url = self.start(other)
        try:
            port = int(url.rsplit(':',1)[1])
            with self.assertRaises(SystemExit):
                self.start(target,port)
            self.assertIsNone(child.poll())
            self.assertEqual(read(url)[0],b'other index')
        finally:
            headless.stop_server(child)

    def test_live_child_readiness_cannot_vouch_for_another_listener(self):
        root = self.checkout('fake child','unused')
        # Simulate a child announcing readiness while the port still belongs to a foreign listener.
        # The HTTP identity check must reject it and terminate only this child.
        (root/'tools/serve.py').write_text('''import json,os,sys,threading
from pathlib import Path
identity=sys.argv[sys.argv.index('--identity')+1]
ready=Path(sys.argv[sys.argv.index('--ready-file')+1])
ready.write_text(json.dumps({'identity':identity,'pid':os.getpid(),'root':str(Path(__file__).resolve().parent.parent),'port':int(sys.argv[1])}),encoding='utf-8')
threading.Event().wait()
''',encoding='utf-8')
        with fixture_listener() as (port,url):
            with self.assertRaises(SystemExit) as error:
                self.start(root,port)
            self.assertIn('identity mismatch',str(error.exception))
            self.assertEqual(read(url)[0],b'foreign fixture')

    def test_startup_timeout_reaps_its_own_child(self):
        root = self.checkout('silent child','unused')
        (root/'tools/serve.py').write_text('import threading; threading.Event().wait()',encoding='utf-8')
        popen, children = headless.subprocess.Popen, []
        def launch(*args,**kw):
            child = popen(*args,**kw)
            children.append(child)
            return child
        with patch.object(headless.subprocess,'Popen',side_effect=launch):
            start = time.monotonic()
            with self.assertRaises(SystemExit):
                self.start(root,startup_timeout=.3)
            self.assertLess(time.monotonic()-start,3)
        self.assertEqual(len(children),1)
        self.assertIsNotNone(children[0].poll())

    def test_readiness_must_name_the_child_pid_and_checkout(self):
        for field in ('root','pid'):
            with self.subTest(field=field), fixture_listener() as (port,url):
                root = self.checkout('bad '+field,'unused')
                (root/'tools/serve.py').write_text('''import json,os,sys,threading
from pathlib import Path
ready=Path(sys.argv[sys.argv.index('--ready-file')+1])
info={'identity':sys.argv[sys.argv.index('--identity')+1],'pid':os.getpid(),'root':str(Path(__file__).resolve().parent.parent),'port':int(sys.argv[1])}
''' + ("info['root']=''\n" if field=='root' else "info['pid']+=1\n") + '''ready.write_text(json.dumps(info),encoding='utf-8')
threading.Event().wait()
''',encoding='utf-8')
                with self.assertRaises(SystemExit) as error:
                    self.start(root,port)
                self.assertIn('child/checkout',str(error.exception))
                self.assertEqual(read(url)[0],b'foreign fixture')

    def test_output_setup_failure_also_closes_owned_server(self):
        root = self.checkout('output failure','index')
        blocked = root/'blocked'
        blocked.write_bytes(b'keep this file')
        argv = ['headless.py','--lines','17','--checks','lint','--port','0','--out',str(blocked)]
        serve, started = headless.serve, []
        def launch(*args,**kw):
            result = serve(*args,**kw)
            started.append(result)
            return result
        with patch.object(headless,'ROOT',str(root)), patch.object(sys,'argv',argv), \
                patch.object(headless,'serve',side_effect=launch), patch.object(headless,'worker') as worker:
            with self.assertRaises(FileExistsError):
                headless.main()
            worker.assert_not_called()
        self.assertEqual(len(started),1)
        self.assertIsNotNone(started[0][0].poll())
        self.assertEqual(blocked.read_bytes(),b'keep this file')

    def test_explicit_url_bypasses_owned_server_checks(self):
        out = self.root/'results'
        with fixture_listener() as (_,url):
            argv = ['headless.py','--lines','17','--checks','lint','--jobs','1','--url',url,'--out',str(out)]
            def worker(job, actual_url, headed, timeout):
                self.assertEqual(actual_url,url)
                return job, {'checks':{}}, 0
            with patch.object(sys,'argv',argv), patch.object(headless,'BASELINE',str(self.root/'absent.json')), \
                    patch.object(headless,'serve') as own, patch.object(headless,'worker',side_effect=worker), \
                    redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    headless.main()
                self.assertEqual(result.exception.code,0)
                own.assert_not_called()
            self.assertTrue((out/'line17-lint.json').exists())


if __name__=='__main__':
    unittest.main(verbosity=2)
