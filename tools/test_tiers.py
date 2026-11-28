# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/tiers.py: the checks a change needs, picked from its files (#727). python -I tools/test_tiers.py"""
import glob
import os
import sys
import tempfile
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
        for t in ("tools/covers.py", "tools/wall_lines.py", "tools/ties.py", "tools/bed_surface.py"):
            self.assertEqual(k(t), ["ground rule"], t)  # (what a place's build runs, though a rebuild runs it too, #865)
        queue = ("tools/heavy.py", "tools/stepcache.py", "tools/board.py")  # (the queue, the cache, the label: no output)
        self.assertEqual(list(tiers.kinds(queue)), ["tool"])
        self.assertEqual(k("tools/line_heights.py"), ["track heights"])
        self.assertEqual(k("src/main.js"), ["drawing", "simulation"])  # (the loop: both)
        self.assertEqual(k("src/review.js"), ["review"])
        self.assertEqual(k("src/groundFile.js"), ["drawing", "loading"])  # (as a player loads it, #710)
        self.assertEqual(k("src/world.js"), ["drawn geometry", "loading"])
        self.assertEqual(k("tools/bench/redruns.js"), ["simulation"])
        self.assertEqual(k("src/new.js"), ["unplaced"])

    def test_a_bench_goes_by_the_checks_that_load_it(self):
        # (#891: tools/bench/* was simulation, so a static ground check's change asked for seeds 1-5 on every line)
        k = lambda *ps: list(tiers.kinds(ps, BUILD))  # noqa: E731
        self.assertEqual(k("tools/bench/surfaces.js"), ["static check"])
        self.assertEqual(k("tools/bench/street_pits.py"), ["tool"])  # (run by hand, loaded by no check)
        self.assertEqual(k("tools/bench/stuck.js"), ["simulation"])  # (through u3.js and redruns.js)
        self.assertEqual(k("tools/bench/shift.js"), ["simulation"])  # (no check loads it; tools/autopilot.js imports it)
        c = "\n".join(tiers.commands(tiers.kinds(["tools/bench/surfaces.js", "tools/bench/spacing.js"], BUILD)))
        self.assertIn("--checks spacing,surfaces --compare", c)
        self.assertNotIn("--seeds", c)
        c = "\n".join(tiers.commands(tiers.kinds(["tools/bench/giveway.js"], BUILD)))
        self.assertIn("-k test_giveway", c)  # (a bench's own test)
        self.assertIn("--checks giveway --compare", c)

    def test_bench_checks_follow_the_imports_not_the_comments(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "tools", "bench"))
            files = {
                "tools/headless.py": 'CALLS = {"a": "const { run } = await import(\'/tools/bench/a.js\'); return run();",\n'
                                     '         "b": "const { run } = await import(\'/tools/bench/b.js\'); return run(SEED);"}\n'
                                     'SEEDLESS = {"a"}\n',
                "tools/bench/a.js": "import { x } from './c.js';\n// const { y } = await import('/tools/bench/d.js');\n",
                "tools/bench/b.js": "", "tools/bench/c.js": "", "tools/bench/d.js": "", "tools/bench/e.js": "",
                "tools/run.js": "import { e } from './bench/e.js';\n",
            }
            for p, text in files.items():
                with open(os.path.join(root, p), "w", encoding="utf-8") as f:
                    f.write(text)
            loads, seedless, used = tiers.bench_checks(root)
            self.assertEqual(loads, {"tools/bench/a.js": {"a"}, "tools/bench/c.js": {"a"}, "tools/bench/b.js": {"b"}})
            self.assertEqual(seedless, {"a"})
            self.assertEqual(used, {"tools/bench/e.js": {"tools/run.js"}})

    def test_the_commands(self):
        c = "\n".join(tiers.commands(tiers.kinds(["src/tram.js"], BUILD)))
        self.assertIn("--checks u3,redruns,stops,traffic,lint,giveway --seeds 1-5 --compare", c)
        self.assertIn("--checks u3 --seeds 1 --player", "\n".join(tiers.commands(tiers.kinds(["src/groundWorker.js"], BUILD))))
        self.assertIn("-k test_traction", c)
        c = "\n".join(tiers.commands(tiers.kinds(["tools/tiers.py", "tools/test_tiers.py"], BUILD)))
        self.assertIn("python -I tools/test_all.py -k test_tiers", c)
        self.assertEqual(c.count("-k test_tiers"), 1)
        # (a page test runs only with --browser; the runner's own test is test_test_all, #891)
        c = tiers.commands(tiers.kinds(["tools/test_overview_page.py", "tools/test_all.py"], BUILD))
        self.assertIn("python -I tools/test_all.py -k test_overview_page --browser", c)
        self.assertIn("python -I tools/test_all.py -k test_test_all", c)
        self.assertNotIn("python -I tools/test_all.py -k test_all", c)
        self.assertEqual(tiers.commands(tiers.kinds(["AGENTS.md"], BUILD)), [])

    def test_a_ground_change_runs_the_locality_set_and_its_rules_places_not_all(self):
        found = tiers.kinds(["tools/ground_mesh.py"], BUILD)
        c = "\n".join(tiers.commands(found, ground=["ground_mesh.wall_face", "ground_mesh.lowered_kerbs"]))
        self.assertIn("ground_place.py --locality", c)
        self.assertIn("ground_place.py --rule walls,kerbs", c)
        self.assertNotIn("--all", c.replace("test_all", ""))
        self.assertNotIn("in no rule", c)
        c = "\n".join(tiers.commands(found, ground=["ground_mesh.build"]))
        self.assertIn("--locality", c)
        self.assertNotIn("--rule", c)
        self.assertIn("# in no rule (ground_mesh.build)", c)

    def test_the_lines_come_from_the_manifest(self):
        self.assertEqual(tiers.lines(os.path.join(ROOT, "no such checkout")), ["9", "17", "22", "23", "37"])
        self.assertTrue(set(tiers.lines()) >= {"9"})

    def test_agents_md_points_to_the_table(self):
        with open(os.path.join(ROOT, "AGENTS.md"), encoding="utf-8") as f:
            self.assertTrue("tools/tiers.py" in f.read(), "AGENTS.md's checks rule points to tools/tiers.py")


if __name__ == "__main__":
    unittest.main()
