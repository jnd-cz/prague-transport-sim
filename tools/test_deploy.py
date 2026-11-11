"""tools/deploy.py against a fake FTP server in a temp folder: python -P -E tools/test_deploy.py"""
import base64
import ftplib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import brotli

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deploy  # noqa: E402
import reviews  # noqa: E402

SOME = ["index.html", "src/main.js", "src/route.js", "data/MANIFEST.json"]


class FakeFtp:
    """The FTP commands deploy.py uses, on a folder."""

    def __init__(self, root):
        self.root, self.log = root, []

    def _p(self, rel):
        return os.path.join(self.root, *rel.split("/"))

    def retrbinary(self, cmd, cb):
        self.log.append(("RETR", cmd.split(" ", 1)[1]))
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

    def nlst(self, d):
        if not os.path.isdir(self._p(d)):
            raise ftplib.error_perm("550 no such directory")
        return [f"{d}/{n}" for n in os.listdir(self._p(d))]

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

    def test_password_from_netrc_by_its_own_name(self):
        # two users on one FTP host (the test site and the alpha, #350): each reads its own .netrc machine
        rc = os.path.join(self.tmp, "netrc")
        with open(rc, "w", newline="\n") as fh:
            fh.write("machine ftp.example login u password test-site\nmachine sim.8b.cz login a password alpha\n")
        real = deploy.netrc.netrc
        with mock.patch.dict(os.environ, {"TRAM_DEPLOY_PASSWORD": ""}), \
                mock.patch.object(deploy.netrc, "netrc", lambda: real(rc)):
            self.assertEqual(deploy.password({"host": "ftp.example", "user": "u"}), "test-site")
            self.assertEqual(deploy.password({"host": "ftp.example", "user": "a", "netrc": "sim.8b.cz"}), "alpha")
            # (a login that doesn't match the entry is not given its password)
            with mock.patch.object(deploy.sys, "stdin", None), self.assertRaises(SystemExit) as e:
                deploy.password({"host": "ftp.example", "user": "a"})
            self.assertIn("machine ftp.example login a", str(e.exception))

    def test_first_then_unchanged_then_changed(self):
        up, _ = self.run_deploy()
        for rel in SOME:
            name = rel + deploy.PACKED_SUFFIX if deploy.packed(rel) else rel
            with open(os.path.join(self.server, *name.split("/")), "rb") as a, open(os.path.join(deploy.ROOT, *rel.split("/")), "rb") as b:
                self.assertEqual(brotli.decompress(a.read()) if deploy.packed(rel) else a.read(), b.read(), rel)
        self.assertTrue(os.path.exists(os.path.join(self.server, ".htaccess")))
        self.assertFalse([f for _, _, fs in os.walk(self.server) for f in fs if f.endswith(".part")], "no .part left")
        self.assertEqual(up[-1], deploy.MANIFEST + ".part", "the manifest is written last")
        self.assertLess(up.index("data/MANIFEST.json.brotli.part"), up.index("index.html.part"), "data before the page")
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

    def test_the_data_heavy_packs_go_up_only_compressed(self):
        for rel in ("data/line17.bld.bin", "data/line17.json", "data/MANIFEST.json", "assets/t3/t3.bin", "assets/t3/t3.gltf", "assets/t3h/t3h.glb"):
            self.assertTrue(deploy.packed(rel), rel)
        for rel in ("index.html", "reviews.html", "src/main.js", "README.md", "assets/t3/t3_color.jpg", "assets/t3/LICENCE.txt", "reports/review/a.json", "version.json"):
            self.assertFalse(deploy.packed(rel), rel)
        self.run_deploy()
        self.assertTrue(os.path.exists(os.path.join(self.server, "data", "MANIFEST.json.brotli")))
        self.assertFalse(os.path.exists(os.path.join(self.server, "data", "MANIFEST.json")), "no plain copy beside it")
        # the server's rule hands that file to a request for the plain name
        h = open(os.path.join(self.server, ".htaccess")).read()
        self.assertIn(f"AddEncoding br {deploy.PACKED_SUFFIX}", h)
        self.assertIn(f"RewriteRule ^(.*)$ $1{deploy.PACKED_SUFFIX} [L]", h)

    def test_a_site_with_plain_data_loses_it_after_the_compressed_copy_is_up(self):
        self.run_deploy()
        man = os.path.join(self.server, deploy.MANIFEST)
        m = json.load(open(man))
        m["data/MANIFEST.json"] = "0" * 64  # (as the deploys before #275 left it)
        json.dump(m, open(man, "w"))
        open(os.path.join(self.server, "data", "MANIFEST.json"), "w").write("{}")
        _, gone = self.run_deploy()
        self.assertEqual(gone, ["data/MANIFEST.json"])
        self.assertFalse(os.path.exists(os.path.join(self.server, "data", "MANIFEST.json")))
        self.assertTrue(os.path.exists(os.path.join(self.server, "data", "MANIFEST.json.brotli")))

    def test_dry_run_writes_nothing(self):
        self.run_deploy("--dry-run")
        self.assertEqual([e for e in self.ftp.log if e[0] != "RETR"], [])
        self.assertEqual(os.listdir(self.server), [])

    def test_version(self):
        self.run_deploy()
        v = json.load(open(os.path.join(self.server, "version.json"), encoding="utf-8"))
        self.assertEqual(len(v["commit"]), 40)
        self.assertIn("snapshot", v["data"])

    def test_version_stays_after_a_second_deploy(self):
        # the server's manifest lists version.json from the first deploy on (#207)
        self.run_deploy()
        self.assertIn("version.json", json.load(open(os.path.join(self.server, deploy.MANIFEST))))
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.run_deploy("--dry-run")
        self.assertNotIn("del version.json", out.getvalue())
        self.run_deploy()
        self.assertTrue(os.path.exists(os.path.join(self.server, "version.json")))
        self.assertIn("version.json", json.load(open(os.path.join(self.server, deploy.MANIFEST))))

    def test_review_php_and_pull(self):
        self.run_deploy()
        self.assertTrue(os.path.exists(os.path.join(self.server, "review.php")))
        self.assertEqual(open(os.path.join(self.server, "reviews", ".htaccess")).read().strip(), "Require all denied")
        # answers on the host (as review.php leaves them) and older and newer ones here
        host = {"meta": {"line": 17}, "items": {"a": {"v": "x", "t": 5}, "b": {"v": "new", "t": 9}}}
        json.dump(host, open(os.path.join(self.server, "reviews", "line17.json"), "w"))
        dest = os.path.join(self.tmp, "pulled")
        reviews.save(os.path.join(dest, "line17.json"), {"items": {"b": {"v": "old", "t": 3}, "c": {"v": "here", "t": 1}}})
        deploy.pull_reviews(FakeFtp(self.server), dest)
        got = reviews.load(os.path.join(dest, "line17.json"))["items"]
        self.assertEqual({k: v["v"] for k, v in got.items()}, {"a": "x", "b": "new", "c": "here"})
        # a report: fetched once, the screenshot as a file beside it
        jpg = "data:image/jpeg;base64," + base64.b64encode(b"JPEG bytes").decode()
        rep = {"meta": {"report": True}, "items": {"report-1": {"kind": "other", "note": "a bump", "line": 17, "shot": jpg}}}
        json.dump(rep, open(os.path.join(self.server, "reviews", "report-20261031-120000-ab12.json"), "w"))
        deploy.pull_reviews(FakeFtp(self.server), dest)
        self.assertEqual(open(os.path.join(dest, "report-20261031-120000-ab12.jpg"), "rb").read(), b"JPEG bytes")
        self.assertEqual(reviews.load(os.path.join(dest, "report-20261031-120000-ab12.json"))["items"]["report-1"]["shot"],
                         "report-20261031-120000-ab12.jpg")
        ftp = FakeFtp(self.server)
        deploy.pull_reviews(ftp, dest)
        self.assertNotIn("report-20261031-120000-ab12.json", str(ftp.log), "a report is fetched once")
        # the answers stay on the host through the next deploy
        self.run_deploy()
        self.assertTrue(os.path.exists(os.path.join(self.server, "reviews", "line17.json")))

    def test_merge_newer_wins(self):
        out = reviews.merge({"meta": {"a": 1}, "items": {"k": {"v": 1, "t": 5}}},
                            {"meta": {"b": 2}, "items": {"k": {"v": 2, "t": 4}, "j": {"v": 3, "t": 1}, 7: "bad"}})
        self.assertEqual(out, {"meta": {"a": 1, "b": 2}, "items": {"k": {"v": 1, "t": 5}, "j": {"v": 3, "t": 1}}})


if __name__ == "__main__":
    unittest.main()
