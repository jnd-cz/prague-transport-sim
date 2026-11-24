# SPDX-License-Identifier: AGPL-3.0-or-later
"""Data older than the checkout's manifest (#835): a file of an earlier build is stale, one of no manifest is the
branch's own build."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import snapshot  # noqa: E402


def git(root, *a):
    subprocess.run(["git", *a], cwd=root, check=True, capture_output=True)


class Stale(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.mkdir(os.path.join(self.root, "data"))
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "t@t")
        git(self.root, "config", "user.name", "t")
        self.publish({"line9.json": b"old 9", "line17.json": b"17"})  # (an earlier build)
        self.publish({"line9.json": b"new 9", "line17.json": b"17", "line22.json": b"22"})

    def tearDown(self):
        self.tmp.cleanup()

    def publish(self, files):
        man = {"files": {f: {"sha256": hashlib.sha256(b).hexdigest(), "size": len(b)} for f, b in files.items()}}
        with open(os.path.join(self.root, "data", "MANIFEST.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(man, fh)
        git(self.root, "add", "data/MANIFEST.json")
        git(self.root, "commit", "-qm", "publish")

    def write(self, f, b):
        with open(os.path.join(self.root, "data", f), "wb") as fh:
            fh.write(b)

    def test_after_a_merge_the_old_files_are_stale(self):
        self.write("line9.json", b"old 9")
        self.write("line17.json", b"17")
        self.assertEqual(snapshot.stale_data(self.root), [("stale", "line9.json")])  # (line22.json missing: fails where read)
        with self.assertRaises(SystemExit) as e:
            snapshot.require_current_data(self.root)
        self.assertIn("stale    data/line9.json", str(e.exception.code))
        self.assertIn("data-fetch", str(e.exception.code))

    def test_the_branchs_own_build_and_its_outputs_run(self):
        self.write("line9.json", b"rebuilt 9")
        self.write("line17.json", b"17")
        self.write("line22.json", b"22")
        self.write("line9.extra.json", b"a tool's output")
        self.assertEqual(snapshot.data_diff(self.root), [("new", "line9.extra.json"), ("changed", "line9.json")])
        self.assertEqual(snapshot.stale_data(self.root), [])
        snapshot.require_current_data(self.root)

    def test_the_override_warns_and_runs(self):
        self.write("line9.json", b"old 9")
        self.write("line17.json", b"17")
        self.write("line22.json", b"22")
        with patch.dict(os.environ, {"TRAM_STALE_DATA": "1"}), patch("sys.stderr") as err:
            snapshot.require_current_data(self.root)
        self.assertIn("line9.json", "".join(c.args[0] for c in err.write.call_args_list))

    def test_no_manifest_no_check(self):
        os.remove(os.path.join(self.root, "data", "MANIFEST.json"))
        self.assertEqual(snapshot.stale_data(self.root), [])


if __name__ == "__main__":
    unittest.main()
