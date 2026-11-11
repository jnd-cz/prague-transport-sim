"""Player feedback (#350): python -I tools/test_feedback.py

tools/feedback.py (the note's checks, saving with its screenshot, the listing), tools/serve.py's POST
/feedback.php, and the host's PHP scripts run under `php -S` on a free port: tools/feedback.php (it only takes
notes in, within its caps) and tools/review.php (read and merge). Without PHP on PATH the PHP part skips and
says so; CI's Ubuntu runners have it.
"""
import base64
import contextlib
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feedback  # noqa: E402
import serve  # noqa: E402

TOOLS = os.path.dirname(os.path.abspath(__file__))
JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0 a jpeg").decode()


def post(url, body, headers=None):
    """(status, parsed answer or None)"""
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except ValueError:
            return e.code, None


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


FB = {"X-Feedback": "1"}


class NoteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_invalid(self):
        self.assertIsNone(feedback.invalid({"note": "ok"}))
        self.assertIsNone(feedback.invalid({"note": "ok", "shot": None}))
        self.assertIsNone(feedback.invalid({"note": "ok", "shot": JPEG}))
        self.assertEqual(feedback.invalid([1]), "json")
        self.assertEqual(feedback.invalid({}), "note")
        self.assertEqual(feedback.invalid({"note": "x" * (feedback.MAX_NOTE + 1)}), "note")
        self.assertEqual(feedback.invalid({"note": "ok", "shot": "data:text/html,<b>"}), "shot")

    def test_save_splits_the_screenshot_and_lists(self):
        d = os.path.join(self.tmp, "alpha")
        a = {"id": "fb-20261111-100000-0000000a", "kind": "driving", "note": "brzdí  pozdě", "line": "17", "shot": JPEG,
             "tram": {"s": 120.5}, "machine": {"gpu": "Intel Arc A770"}}
        b = {"id": "fb-20261111-110000-0000000b", "kind": "driving", "note": "later", "line": "9", "errors": [{"msg": "x"}]}
        self.assertTrue(feedback.save(d, a) and feedback.save(d, b))
        self.assertIsNone(feedback.save(d, {"id": "../evil", "note": ""}))
        with open(os.path.join(d, a["id"] + ".jpg"), "rb") as fh:
            self.assertEqual(fh.read()[:2], b"\xff\xd8")
        with open(os.path.join(d, a["id"] + ".json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["shot"], a["id"] + ".jpg")
        self.assertEqual([n["id"] for _, n in feedback.notes(self.tmp)], [b["id"], a["id"]])
        open(os.path.join(d, b["id"] + ".done"), "w").close()
        self.assertEqual([n["id"] for _, n in feedback.notes(self.tmp)], [a["id"]])
        self.assertEqual(len(feedback.notes(self.tmp, everything=True)), 2)
        out = io.StringIO()
        with mock.patch.object(feedback, "DEST", self.tmp), contextlib.redirect_stdout(out):
            feedback.main(["--all"])
        self.assertIn("driving (2)", out.getvalue())
        self.assertIn("Intel Arc A770", out.getvalue())
        self.assertIn("brzdí pozdě", out.getvalue())
        self.assertRegex(feedback.new_id(), feedback.ID)


class Quiet(serve.NoCache):
    def log_message(self, *args):
        pass


class ServeTest(unittest.TestCase):
    """tools/serve.py takes notes as the host's feedback.php does, into reports/feedback/local/."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = mock.patch.object(feedback, "DEST", self.tmp)
        self.p.start()
        self.server = serve.Server(("127.0.0.1", 0), lambda *a, **k: Quiet(*a, directory=serve.ROOT, **k))
        self.server.identity, self.server.rate, self.server.lan = None, 0, True  # (also from the home network)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/feedback.php"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.p.stop()
        shutil.rmtree(self.tmp)

    def test_takes_a_note(self):
        code, ans = post(self.url, {"note": "the kerb floats", "kind": "city", "shot": JPEG}, FB)
        self.assertEqual(code, 200)
        self.assertRegex(ans["id"], feedback.ID)
        d = os.path.join(self.tmp, "local")
        self.assertEqual(sorted(os.listdir(d)), [ans["id"] + ".jpg", ans["id"] + ".json"])
        with open(os.path.join(d, ans["id"] + ".json"), encoding="utf-8") as fh:
            rec = json.load(fh)
        self.assertEqual((rec["note"], rec["kind"]), ("the kerb floats", "city"))
        self.assertTrue(rec["received"])

    def test_refuses(self):
        self.assertEqual(post(self.url, {"note": "x"}, {})[0], 405)
        self.assertEqual(post(self.url, b"not json", FB)[0], 400)
        self.assertEqual(post(self.url, {"note": "x", "shot": "data:text/html,x"}, FB)[0], 400)
        self.assertEqual(post(self.url, b"x" * (feedback.MAX_BODY + 1), FB)[0], 413)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "local")))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@unittest.skipUnless(shutil.which("php"), "no php on PATH: the host's PHP scripts are not run (CI runs them)")
class PhpTest(unittest.TestCase):
    """The host's scripts under PHP's own server, in a temp folder as the site's root."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp()
        for f in ("feedback.php", "review.php"):
            shutil.copy(os.path.join(TOOLS, f), cls.root)
        cls.port = free_port()
        cls.php = subprocess.Popen(["php", "-S", f"127.0.0.1:{cls.port}", "-t", cls.root],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", cls.port), timeout=0.2):
                break
            time.sleep(0.1)
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.php.terminate()
        cls.php.wait(10)
        shutil.rmtree(cls.root)

    def setUp(self):
        shutil.rmtree(os.path.join(self.root, "feedback"), ignore_errors=True)

    def stored(self):
        d = os.path.join(self.root, "feedback")
        return sorted(f for f in os.listdir(d) if f.endswith(".json")) if os.path.isdir(d) else []

    def test_feedback_takes_a_note_under_its_own_id(self):
        code, ans = post(f"{self.base}/feedback.php", {"note": "příliš rychle", "kind": "driving", "shot": JPEG, "id": "mine"}, FB)
        self.assertEqual(code, 200, ans)
        self.assertRegex(ans["id"], feedback.ID)
        self.assertEqual(self.stored(), [ans["id"] + ".json"])
        with open(os.path.join(self.root, "feedback", ans["id"] + ".json"), encoding="utf-8") as fh:
            rec = json.load(fh)
        self.assertEqual((rec["id"], rec["note"], rec["shot"]), (ans["id"], "příliš rychle", JPEG))
        # (the pull's own check of what it fetches)
        self.assertIsNone(feedback.invalid(rec))

    def test_feedback_refuses_and_reads_nothing_back(self):
        url = f"{self.base}/feedback.php"
        self.assertEqual(get(url)[0], 405)
        self.assertEqual(post(url, {"note": "x"})[0], 405)  # (no X-Feedback: a form from another site)
        self.assertEqual(post(url, b"{nope", FB)[0], 400)
        self.assertEqual(post(url, [1, 2], FB)[0], 400)
        self.assertEqual(post(url, {"kind": "x"}, FB)[0], 400)
        self.assertEqual(post(url, {"note": "č" * (feedback.MAX_NOTE + 1)}, FB)[0], 400)
        self.assertEqual(post(url, {"note": "x", "shot": "data:text/html,<script>"}, FB)[0], 400)
        self.assertEqual(post(url, b'{"note": "' + b"x" * feedback.MAX_BODY + b'"}', FB)[0], 413)
        self.assertEqual(self.stored(), [])

    def test_feedback_caps(self):
        url = f"{self.base}/feedback.php"
        d = os.path.join(self.root, "feedback")
        os.makedirs(d)
        # 20 notes within a minute from everyone: the next waits
        for i in range(20):
            with open(os.path.join(d, f"fb-20261111-000000-{i:08x}.json"), "w") as fh:
                fh.write("{}")
        self.assertEqual(post(url, {"note": "x"}, FB)[0], 429)
        # 3000 kept (older than a minute): full until a pull moves them off
        old = time.time() - 3600
        for i in range(3000):
            p = os.path.join(d, f"fb-20261111-000000-{i:08x}.json")
            with open(p, "w") as fh:
                fh.write("{}")
            os.utime(p, (old, old))
        self.assertEqual(post(url, {"note": "x"}, FB)[0], 507)
        for f in os.listdir(d)[:5]:
            os.remove(os.path.join(d, f))
        self.assertEqual(post(url, {"note": "x"}, FB)[0], 200)

    def test_review_reads_and_merges(self):
        url = f"{self.base}/review.php?f=line17"
        self.assertEqual(get(url), (200, b"{}"))
        rh = {"X-Review": "1"}
        self.assertEqual(post(url, {"items": {"a": {"v": 1, "t": 2}, "b": {"v": 1, "t": 1}}}, rh)[0], 200)
        self.assertEqual(post(url, {"items": {"a": {"v": 2, "t": 1}, "b": {"v": 3, "t": 5}}}, rh)[0], 200)
        items = json.loads(get(url)[1])["items"]
        self.assertEqual((items["a"]["v"], items["b"]["v"]), (1, 3))  # (the newer t wins)
        self.assertEqual(post(url, {"items": {}}, {})[0], 405)
        self.assertEqual(get(f"{self.base}/review.php?f=../x")[0], 400)


if __name__ == "__main__":
    unittest.main()
