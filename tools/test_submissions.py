# SPDX-License-Identifier: AGPL-3.0-or-later
"""Package submissions (#580): python -I tools/test_submissions.py

tools/submissions.py (a submission's checks and caps, saving, the listing, --accept into a catalogue as hosted or
linked, --reject, --delete), tools/serve.py's POST /submit.php, and the host's tools/submit.php under `php -S` on a
free port with the same cases (it only takes submissions in, within its caps). Without PHP on PATH the PHP part
skips and says so; CI's Ubuntu runners have it. The page's side: tools/test_submission_check.py.
"""
import contextlib
import io
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
import zipfile
from unittest import mock

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serve  # noqa: E402
import submissions  # noqa: E402

TOOLS = os.path.dirname(os.path.abspath(__file__))


def pack(names=("package.json", "model.glb", "textures/a.webp")):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n in names:
            z.writestr(n, b"x")
    return buf.getvalue()


def meta(**more):
    m = {"schema": 1, "host": False, "licence": True, "contact": "author@example.org", "note": "my tram",
         "packages": [{"id": "sample.box-tram", "version": "1.0.0", "kind": "vehicle", "names": {"en": "Box", "cs": "Krabice"},
                       "authors": ["Sample Author"], "licence": "CC-BY-4.0"}]}
    m.update(more)
    return {k: v for k, v in m.items() if v is not ...}


def multipart(fields):
    """A multipart/form-data body as a browser's FormData sends it: (body, content type)."""
    b = uuid.uuid4().hex
    out = b""
    for name, value in fields.items():
        if isinstance(value, bytes):
            head = f'Content-Disposition: form-data; name="{name}"; filename="pack.zip"\r\nContent-Type: application/zip'
        else:
            head, value = f'Content-Disposition: form-data; name="{name}"', value.encode()
        out += f"--{b}\r\n{head}\r\n\r\n".encode() + value + b"\r\n"
    return out + f"--{b}--\r\n".encode(), f"multipart/form-data; boundary={b}"


def post(url, fields, submit=True):
    body, kind = multipart(fields)
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": kind, **({"X-Submit": "1"} if submit else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except ValueError:
            return e.code, None


class Rules(unittest.TestCase):
    def test_meta(self):
        self.assertIsNone(submissions.meta_problem(meta(), True))
        self.assertIsNone(submissions.meta_problem(meta(url="https://example.org/t/package.json"), False))
        self.assertIsNone(submissions.meta_problem(meta(url="https://example.org/t.zip?v=2", contact=None), False))
        for bad, want in ((meta(contact="x" * 201), "contact"), (meta(note=["x"]), "note"), (meta(host="yes"), "host"),
                          (meta(licence=False), "licence"), (meta(url="http://example.org/t.zip"), "url"),
                          (meta(url="https://example.org/t.exe"), "url"), (meta(packages=[]), "packages")):
            self.assertEqual(submissions.meta_problem(bad, bad.get("url") is None), want, bad)
        # (one of them: the archive, or its address)
        self.assertEqual(submissions.meta_problem(meta(), False), "pack or url")
        self.assertEqual(submissions.meta_problem(meta(url="https://example.org/t.zip"), True), "pack or url")

    def test_zip(self):
        self.assertIsNone(submissions.zip_problem(pack()))
        self.assertEqual(submissions.zip_problem(b"MZ not a zip"), "zip")
        self.assertEqual(submissions.zip_problem(pack(("package.json", "run.exe"))), "type")
        self.assertEqual(submissions.zip_problem(pack(("package.json", "../escape.json"))), "path")
        self.assertEqual(submissions.zip_problem(pack(("package.json", "noext"))), "type")
        r = submissions.rules()
        self.assertEqual(submissions.zip_problem(pack(), {**r, "caps": {**r["caps"], "package": 10}}), "size")


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.site = os.path.join(self.tmp, "local")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_take_saves_and_caps(self):
        code, ans = submissions.take(self.site, json.dumps(meta()).encode(), pack())
        self.assertEqual(code, 200)
        self.assertRegex(ans["id"], submissions.ID)
        self.assertEqual(sorted(os.listdir(os.path.join(self.site, ans["id"]))), ["meta.json", "pack.zip"])
        self.assertEqual(submissions.take(self.site, b"{half", pack()), (400, {"error": "meta"}))
        self.assertEqual(submissions.take(self.site, json.dumps(meta()).encode(), b"MZ"), (400, {"error": "zip"}))
        for _ in range(submissions.PER_HOUR - 1):
            self.assertEqual(submissions.take(self.site, json.dumps(meta(url="https://e.org/a.zip")).encode())[0], 200)
        # (ten an hour from everyone together)
        self.assertEqual(submissions.take(self.site, json.dumps(meta()).encode(), pack()), (429, {"error": "busy"}))
        later = time.time() + 7200
        with mock.patch.object(submissions, "MAX_KEPT", submissions.PER_HOUR):
            self.assertEqual(submissions.take(self.site, json.dumps(meta()).encode(), pack(), now=later), (507, {"error": "full"}))

    def test_accept_hosted_linked_and_reject(self):
        cat = os.path.join(self.tmp, "catalogue.json")
        with open(cat, "w", encoding="utf-8") as f:
            json.dump({"about": "x", "packages": []}, f)
        submissions.save(self.site, {**meta(host=True), "id": "sub-20261116-100000-0000000a"}, pack())
        linked = submissions.save(self.site, {**meta(), "id": "sub-20261116-100001-0000000b"}, pack())
        address = submissions.save(self.site, {**meta(url="https://example.org/t/package.json"), "id": "sub-20261116-100002-0000000c",
                                               "packages": [{**meta()["packages"][0], "id": "other.tram"}]})
        rows = submissions.submissions(self.tmp)
        self.assertEqual([r[2]["id"] for r in rows], ["sub-20261116-100002-0000000c", "sub-20261116-100001-0000000b", "sub-20261116-100000-0000000a"])
        # hosted: the pack goes to hosted/, the entry points there
        e = submissions.accept("sub-20261116-100000-0000000a", catalogue=cat, dest=self.tmp)
        self.assertEqual(e["url"], "hosted/sample.box-tram-1.0.0.zip")
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "hosted", "sample.box-tram-1.0.0.zip")))
        self.assertEqual((e["author"], e["licence"], e["names"]["cs"]), ("Sample Author", "CC-BY-4.0", "Krabice"))
        # linked: an uploaded pack needs its author's address; the upload is deleted with the verdict
        with self.assertRaises(SystemExit):
            submissions.accept("sub-20261116-100001-0000000b", catalogue=cat, dest=self.tmp)
        submissions.accept("sub-20261116-100001-0000000b", url="https://example.org/box/package.json", catalogue=cat, dest=self.tmp)
        self.assertFalse(os.path.exists(os.path.join(linked, "pack.zip")))
        submissions.accept("sub-20261116-100002-0000000c", catalogue=cat, dest=self.tmp)
        got = submissions.load(cat)["packages"]
        # (one entry per package id: the second accept of sample.box-tram replaced the first)
        self.assertEqual([(c["id"], c["url"]) for c in got], [("sample.box-tram", "https://example.org/box/package.json"),
                                                               ("other.tram", "https://example.org/t/package.json")])
        self.assertEqual(submissions.load(os.path.join(address, "verdict.json"))["verdict"], "accepted")
        # rejected: why, and the upload gone
        r = submissions.save(self.site, {**meta(), "id": "sub-20261116-100003-0000000d"}, pack())
        with mock.patch.object(submissions, "DEST", self.tmp), mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            submissions.main(["--reject", "sub-20261116-100003-0000000d", "too many triangles"])
            self.assertIn("author@example.org", out.getvalue())
            self.assertEqual(submissions.load(os.path.join(r, "verdict.json"))["reason"], "too many triangles")
            self.assertFalse(os.path.exists(os.path.join(r, "pack.zip")))
            submissions.main(["--delete", "sub-20261116-100003-0000000d"])
        self.assertFalse(os.path.exists(r))
        self.assertIsNone(submissions.save(self.site, {"id": "../x"}))

    def test_catalogue_entry_strictest_licence(self):
        m = {**meta(), "id": "sub-x", "packages": [{"id": "a.fleet", "kind": "fleet", "licence": "CC-BY-4.0"},
                                                  {"id": "a.tram", "kind": "vehicle", "licence": "CC-BY-NC-SA-4.0", "authors": ["A"]}]}
        e = submissions.entry(m, "hosted/a.zip")
        self.assertEqual((e["id"], e["licence"], e["packages"]), ("a.tram", "CC-BY-NC-SA-4.0", ["a.fleet", "a.tram"]))


class Quiet(serve.NoCache):
    def log_message(self, *args):
        pass


class ServeTest(unittest.TestCase):
    """tools/serve.py takes submissions as the host's submit.php does, into <submissions>/local/."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = mock.patch.object(submissions, "DEST", self.tmp)
        self.p.start()
        self.server = serve.Server(("127.0.0.1", 0), lambda *a, **k: Quiet(*a, directory=serve.ROOT, **k))
        self.server.identity, self.server.rate, self.server.lan = None, 0, True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/submit.php"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.p.stop()
        shutil.rmtree(self.tmp)

    def test_takes_both_forms_and_refuses(self):
        cases(self, self.url, lambda sid: os.path.join(self.tmp, "local", sid))


def cases(t, url, stored):
    """The same cases for serve.py and submit.php: stored(id) is where a submission lands."""
    code, ans = post(url, {"meta": json.dumps(meta()), "pack": pack()})
    t.assertEqual(code, 200, ans)
    t.assertRegex(ans["id"], submissions.ID)
    t.assertEqual(sorted(os.listdir(stored(ans["id"]))), ["meta.json", "pack.zip"])
    with open(os.path.join(stored(ans["id"]), "meta.json"), encoding="utf-8") as fh:
        m = json.load(fh)
    t.assertEqual((m["contact"], m["id"]), ("author@example.org", ans["id"]))
    t.assertTrue(m["received"])
    code, ans = post(url, {"meta": json.dumps(meta(url="https://example.org/t/package.json"))})
    t.assertEqual(code, 200, ans)
    t.assertEqual(os.listdir(stored(ans["id"])), ["meta.json"])
    for fields, want in (({"meta": json.dumps(meta())}, "pack or url"),
                         ({"meta": json.dumps(meta(licence=False)), "pack": pack()}, "licence"),
                         ({"meta": json.dumps(meta()), "pack": pack(("package.json", "x.exe"))}, "type"),
                         ({"meta": json.dumps(meta()), "pack": b"MZ\x90\x00 not a zip"}, "zip"),
                         ({"meta": "{half", "pack": pack()}, "meta")):
        code, ans = post(url, fields)
        t.assertEqual((code, ans and ans.get("error")), (400, want), fields.get("meta", "")[:40])
    t.assertEqual(post(url, {"meta": json.dumps(meta()), "pack": pack()}, submit=False)[0], 405)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@unittest.skipUnless(shutil.which("php"), "no php on PATH: the host's submit.php is not run (CI runs it)")
class PhpTest(unittest.TestCase):
    """submit.php under PHP's own server, in a temp folder as the site's root (with the game's src/packageRules.json)."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp()
        shutil.copy(os.path.join(TOOLS, "submit.php"), cls.root)
        os.makedirs(os.path.join(cls.root, "src"))
        shutil.copy(submissions.RULES, os.path.join(cls.root, "src"))
        cls.port = free_port()
        cls.php = subprocess.Popen(["php", "-S", f"127.0.0.1:{cls.port}", "-t", cls.root],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", cls.port), timeout=0.2):
                break
            time.sleep(0.1)
        cls.url = f"http://127.0.0.1:{cls.port}/submit.php"

    @classmethod
    def tearDownClass(cls):
        cls.php.terminate()
        cls.php.wait(10)
        shutil.rmtree(cls.root)

    def test_takes_both_forms_and_refuses(self):
        cases(self, self.url, lambda sid: os.path.join(self.root, "submissions", sid))

    def test_rate(self):
        d = os.path.join(self.root, "submissions")
        shutil.rmtree(d, ignore_errors=True)
        got = [post(self.url, {"meta": json.dumps(meta(url="https://e.org/a.zip"))})[0] for _ in range(submissions.PER_HOUR + 1)]
        self.assertEqual(got, [200] * submissions.PER_HOUR + [429])
        shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main(verbosity=2)
