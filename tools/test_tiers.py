# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/tiers.py: the checks a change needs, picked from its files (#727). python -I tools/test_tiers.py"""
import glob
import os
import sys
import unittest

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import tiers  # noqa: E402

BUILD = {"tools/rebuild.py", "tools/build_line.py", "tools/track_styles.py", "tools/ground_mesh.py"}


class Rows(unittest.TestCase):
    def test_every_game_file_is_in_a_row(self):
        files = [os.path.relpath(p, ROOT).replace(os.sep, "/") for p in glob.glob(os.path.join(ROOT, "src", "*"))]
        files += ["index.html", "reviews.html", "app.webmanifest"]
        unplaced = tiers.kinds(files, BUILD).get("unplaced", [])
        self.assertEqual(unplaced, [], "a game file in no row of tools/tiers.py KINDS: add it to the row its change needs")

    def test_every_file_a_row_names_is_there(self):
        for k, pats, *_ in tiers.KINDS:
            for p in pats:
                if not any(c in p for c in "*?["):
                    self.assertTrue(os.path.exists(os.path.join(ROOT, p)), f"{k}: {p} is gone (renamed?)")

    def test_the_kinds_of_a_change(self):
        k = lambda *ps: list(tiers.kinds(ps, BUILD))  # noqa: E731
        self.assertEqual(k("AGENTS.md", "docs/knowledge.md"), ["docs"])
        self.assertEqual(k("AGENTS.md", "src/traffic.js"), ["simulation"])  # (docs beside code: the code's checks)
        self.assertEqual(k("tools/build_line.py"), ["world"])
        self.assertEqual(k("tools/ground_mesh.py"), ["ground rule"])  # (a ground rule: no line rebuilt, #757)
        queue = ("tools/heavy.py", "tools/stepcache.py", "tools/board.py")  # (the queue, the cache, the label: no output)
        self.assertEqual(list(tiers.kinds(queue)), ["tool"])
        self.assertEqual(k("tools/line_heights.py"), ["track heights"])
        self.assertEqual(k("src/main.js"), ["drawing", "simulation"])  # (the loop: both)
        self.assertEqual(k("src/review.js"), ["review"])
        self.assertEqual(k("src/groundFile.js"), ["drawing", "loading"])  # (as a player loads it, #710)
        self.assertEqual(k("src/world.js"), ["drawn geometry", "loading"])
        self.assertEqual(k("tools/bench/redruns.js"), ["simulation"])
        self.assertEqual(k("src/new.js"), ["unplaced"])

    def test_the_commands(self):
        c = "\n".join(tiers.commands(tiers.kinds(["src/tram.js"], BUILD)))
        self.assertIn("--checks u3,redruns,stops,traffic,lint --seeds 1-5 --compare", c)
        self.assertIn("--checks u3 --seeds 1 --player", "\n".join(tiers.commands(tiers.kinds(["src/groundWorker.js"], BUILD))))
        self.assertIn("-k test_traction", c)
        c = "\n".join(tiers.commands(tiers.kinds(["tools/tiers.py", "tools/test_tiers.py"], BUILD)))
        self.assertIn("python -I tools/test_all.py -k test_tiers", c)
        self.assertEqual(c.count("-k test_tiers"), 1)
        self.assertEqual(tiers.commands(tiers.kinds(["AGENTS.md"], BUILD)), [])

    def test_the_lines_come_from_the_manifest(self):
        self.assertEqual(tiers.lines(os.path.join(ROOT, "no such checkout")), ["9", "17", "22", "23", "37"])
        self.assertTrue(set(tiers.lines()) >= {"9"})

    def test_agents_md_points_to_the_table(self):
        with open(os.path.join(ROOT, "AGENTS.md"), encoding="utf-8") as f:
            self.assertTrue("tools/tiers.py" in f.read(), "AGENTS.md's checks rule points to tools/tiers.py")


if __name__ == "__main__":
    unittest.main()
