"""tools/deploy.py against a fake FTP server in a temp folder: python -I tools/test_deploy.py"""
import ftplib
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deploy  # noqa: E402

SOME = ["index.html", "src/main.js", "src/route.js", "data/MANIFEST.json"]


class FakeFtp:
    """The FTP commands deploy.py uses, on a folder."""

    def __init__(self, root):
        self.root, self.log = root, []

    def _p(self, rel):
        return os.path.join(self.root, *rel.split("/"))

    def retrbinary(self, cmd, cb):
        p = self._p(cmd.split(" ", 1)[1])
        if not os.path.exists(p):
            raise ftplib.error_perm("550 not found")
        cb(open(p, "rb").read())

    def storbinary(self, cmd, fh):
        rel = cmd.split(" ", 1)[1]
        if not os.path.isdir(os.path.dirname(self._p(rel))):
            raise ftplib.error_perm("550 no such directory")
        with open(self._p(rel), "wb") as out:
            shutil.copyfileobj(fh, out)
        self.log.append(("STOR", rel))

    def mkd(self, d):
        if os.path.isdir(self._p(d)):
            raise ftplib.error_perm("550 exists")
        os.mkdir(self._p(d))

    def delete(self, rel):
        if not os.path.exists(self._p(rel)):
            raise ftplib.error_perm("550 not found")
        os.remove(self._p(rel))
        self.log.append(("DELE", rel))

    def rename(self, a, b):
        if os.path.exists(self._p(b)):
            raise ftplib.error_perm("550 exists")  # (as some servers: the target goes first)
        os.rename(self._p(a), self._p(b))

    def quit(self):
        pass


class DeployTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.server = os.path.join(self.tmp, "httpdocs")
        os.mkdir(self.server)
        cfg = os.path.join(self.tmp, "deploy.local.json")
        json.dump({"host": "ftp.example", "user": "u", "dir": "/httpdocs"}, open(cfg, "w"))
        self.patches = [mock.patch.object(deploy, "CONFIG", cfg), mock.patch.object(deploy, "files", lambda: iter(SOME)),
                        mock.patch.dict(os.environ, {"TRAM_DEPLOY_PASSWORD": "x"})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp)

    def run_deploy(self, *args):
        self.ftp = FakeFtp(self.server)
        deploy.main(["--dirty", *args], connect=lambda cfg, pw: self.ftp)
        up = [r for op, r in self.ftp.log if op == "STOR"]
        # (a replaced file is deleted before its .part is renamed: not a removal)
        return up, [r for op, r in self.ftp.log if op == "DELE" and r + ".part" not in up]

    def test_first_then_unchanged_then_changed(self):
        up, _ = self.run_deploy()
        for rel in SOME:
            with open(os.path.join(self.server, *rel.split("/")), "rb") as a, open(os.path.join(deploy.ROOT, *rel.split("/")), "rb") as b:
                self.assertEqual(a.read(), b.read(), rel)
        self.assertTrue(os.path.exists(os.path.join(self.server, ".htaccess")))
        self.assertFalse([f for _, _, fs in os.walk(self.server) for f in fs if f.endswith(".part")], "no .part left")
        self.assertEqual(up[-1], deploy.MANIFEST + ".part", "the manifest is written last")
        self.assertLess(up.index("data/MANIFEST.json.part"), up.index("index.html.part"), "data before the page")
        # nothing changed: only the version and the manifest go up
        up, gone = self.run_deploy()
        self.assertEqual(sorted(up), sorted(["version.json.part", deploy.MANIFEST + ".part"]))
        self.assertEqual(gone, [])
        # one file changed on the server's record, one file no longer in the site
        man = os.path.join(self.server, deploy.MANIFEST)
        m = json.load(open(man))
        m["src/route.js"] = "0" * 64
        m["src/old.js"] = "1" * 64
        json.dump(m, open(man, "w"))
        open(os.path.join(self.server, "src", "old.js"), "w").write("x")
        up, gone = self.run_deploy()
        self.assertIn("src/route.js.part", up)
        self.assertNotIn("src/main.js.part", up)
        self.assertEqual(gone, ["src/old.js"])
        self.assertNotIn("src/old.js", json.load(open(man)))

    def test_dry_run_writes_nothing(self):
        self.run_deploy("--dry-run")
        self.assertEqual(self.ftp.log, [])
        self.assertEqual(os.listdir(self.server), [])

    def test_version(self):
        self.run_deploy()
        v = json.load(open(os.path.join(self.server, "version.json"), encoding="utf-8"))
        self.assertEqual(len(v["commit"]), 40)
        self.assertIn("snapshot", v["data"])


if __name__ == "__main__":
    unittest.main()
