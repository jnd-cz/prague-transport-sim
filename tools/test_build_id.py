# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/build_id.py: the line file's CRC-32 in every other file of the line the page loads (#702).

    python -I tools/test_build_id.py

A made-up line in a temporary checkout. The page's side (src/buildId.js: the same CRC-32, a file of another build stops
the load) is in tools/test_loading.py.
"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
import zlib

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import build_id  # noqa: E402
import sources  # noqa: E402


class BuildId(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="test_build_id_")
        self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, "data"))
        self.put("line9.json", {"line": "9", "signals": [1, 2], "provenance": {"lists": {}}})
        for name in ("geo.json", "dtm.json", "dtmpoints.json", "network.json", "ground.json"):  # (no signals.json: line 9 has none)
            self.put(f"line9.{name}", {"what": name, "příliš": "žluťoučký", "provenance": {"lists": {"x": {"tool": "t", "levels": [], "count": []}}}})

    def put(self, name, d):
        with open(os.path.join(self.root, "data", name), "w", encoding="utf-8") as f:
            json.dump(d, f, separators=(",", ":"), ensure_ascii=False)

    def get(self, name):
        with open(os.path.join(self.root, "data", name), encoding="utf-8") as f:
            return json.load(f)

    def test_the_id_is_the_line_files_crc32(self):
        with open(os.path.join(self.root, "data", "line9.json"), "rb") as f:
            want = f"{zlib.crc32(f.read()):08x}"
        self.assertEqual(build_id.line_id("9", self.root), want)
        self.assertRegex(want, r"^[0-9a-f]{8}$")

    def test_stamp_puts_it_into_every_file_there_and_leaves_the_rest(self):
        want, done = build_id.stamp("9", self.root)
        self.assertEqual(done, ["line9.geo.json", "line9.dtm.json", "line9.dtmpoints.json", "line9.network.json", "line9.ground.json"])
        for f in done:
            d = self.get(f)
            self.assertEqual(d["provenance"], {"lists": {"x": {"tool": "t", "levels": [], "count": []}}, "build": want})
            self.assertEqual(d["příliš"], "žluťoučký")
        self.assertEqual(build_id.line_id("9", self.root), want)  # (the line file itself as it was)
        self.assertEqual(build_id.check("9", self.root), (want, {}))
        self.assertFalse(os.path.exists(os.path.join(self.root, "data", "line9.signals.json")))
        self.assertEqual(build_id.stamp("9", self.root), (want, done))  # (again: the same files, the same bytes)

    def test_a_file_written_by_hand_after_the_build_carries_none(self):
        """A tool stamps its file's provenance afresh (sources.stamp keeps the lists, the sources and the facts), so a
        network built by hand after a rebuild has no build ID: the set is two builds."""
        want, _ = build_id.stamp("9", self.root)
        old = self.get("line9.network.json")
        self.put("line9.network.json", {"what": "again", "provenance": sources.stamp("network.py", {}, prev=old["provenance"], root=self.root)})
        self.assertEqual(build_id.check("9", self.root), (want, {"line9.network.json": None}))

    def test_a_line_file_written_again_makes_every_file_another_build(self):
        """cant, placement and others load the line file, change it and write it back: no ID of its own to keep."""
        old, _ = build_id.stamp("9", self.root)
        d = self.get("line9.json")
        d["signals"] = [2, 1]  # (renumbered: the network's indexes now point at other signals)
        self.put("line9.json", d)
        want, off = build_id.check("9", self.root)
        self.assertNotEqual(want, old)
        self.assertEqual(set(off.values()), {old})
        self.assertEqual(len(off), 5)

    def test_the_files_are_those_the_page_loads(self):
        """FILES and src/main.js's `built` (the files the page loaded, src/buildId.js checkBuild) name the same ones."""
        with open(os.path.join(os.path.dirname(TOOLS), "src", "main.js"), encoding="utf-8") as f:
            page = f.read()
        self.assertIn("const built = { [`line${lineId}.json`]: data };", page)  # (the line file: its CRC-32 is the ID)
        self.assertEqual(set(re.findall(r"built\[`line\$\{lineId\}\.([a-z.]+)`\]", page)), set(build_id.FILES))


if __name__ == "__main__":
    unittest.main()
