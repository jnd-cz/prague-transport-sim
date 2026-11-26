# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/ground_rules.py: the locality set, the rules' code and places, and what a diff of the ground tools changed
(#865).

    python -I tools/test_ground_rules.py
"""
import fnmatch
import json
import os
import subprocess
import sys
import tempfile
import unittest

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import ground_rules as gr  # noqa: E402


def places():
    with open(os.path.join(ROOT, "data", "truth.json"), encoding="utf-8") as f:
        return {k for k, v in json.load(f)["groundPlaces"].items() if isinstance(v, dict)}


class Tables(unittest.TestCase):
    def test_every_place_is_of_a_rule_and_every_rules_place_is_there(self):
        known, of = places(), set(gr.places_of(gr.RULES))
        self.assertEqual(sorted(known - of), [], "a groundPlace in no rule of tools/ground_rules.py RULES: give it its rules")
        self.assertEqual(sorted(of - known), [], "a rule names a place data/truth.json groundPlaces lacks (renamed?)")

    def test_the_locality_set_is_places_or_points(self):
        known = places()
        for k, v in gr.LOCALITY.items():
            if isinstance(v, dict):
                self.assertNotIn(k, known)
                self.assertEqual(k, f"line{v['line']}_{v['at'][0]:.0f}_{v['at'][1]:.0f}")  # (ground_place's name for --at)
            else:
                self.assertIn(k, known)
        self.assertLessEqual(len(gr.LOCALITY), 8)  # (its round in under 15 min, #865)

    def test_every_rules_code_names_what_its_tool_holds(self):
        defs = {}
        for p in gr.TOOLS:
            with open(os.path.join(ROOT, p), encoding="utf-8") as f:
                defs[os.path.basename(p)[:-3]] = gr.definitions(f.read())
        for r, v in gr.RULES.items():
            for pat in v["code"]:
                mod = pat.split(".")[0]
                self.assertIn(mod, defs, f"{r}: {pat} is in no ground tool (tools/ground_rules.py TOOLS)")
                self.assertTrue(any(fnmatch.fnmatchcase(f"{mod}.{n}", pat) for n in defs[mod]), f"{r}: {pat} names nothing (renamed?)")


OLD = '''import os
A, B = 1, 2  # (a pair)
C = 3


def kept():
    return 1


def edited():
    return 1


class Levels:
    def at(self):
        return 1

    def other(self):
        return 2
'''


class Changed(unittest.TestCase):
    def test_what_a_change_touches_by_name(self):
        new = (OLD.replace("A, B = 1, 2", "A, B = 1, 5").replace("def edited():\n    return 1", "def edited():\n    return 9")
               .replace("        return 2", "        return 7") + "\n\ndef added():\n    pass\n")
        self.assertEqual(gr.changed(OLD, new, "m"), ["m.A", "m.B", "m.Levels", "m.added", "m.edited"])

    def test_a_comment_between_definitions_and_a_moved_one_change_nothing(self):
        new = OLD.replace("C = 3\n", "C = 3\n# (a note)\n").replace("def kept():\n    return 1\n\n\n", "")
        new += "\n\ndef kept():\n    return 1\n"
        self.assertEqual(gr.changed(OLD, new, "m"), [])
        self.assertEqual(gr.changed(None, "def f():\n    pass\n", "m"), ["m.f"])  # (a new tool: all of it)

    def test_the_rules_of_names(self):
        rules, none = gr.rules_of(["ground_mesh.lowered_kerbs", "ground_mesh.build", "wall_lines.strips",
                                   "ground_partition.WATER_FAR", "ground_mesh.meet_raised"])
        self.assertEqual(rules, ["water", "walls", "kerbs"])  # (in the table's order)
        self.assertEqual(none, ["ground_mesh.build"])
        self.assertEqual(gr.places_of(["platforms", "stairs"])[:2], ["krejcarek-platform", "motol-platform"])
        self.assertEqual(len(gr.places_of(["stairs", "stairs"])), len(gr.RULES["stairs"]["places"]))

    def test_the_diff_against_the_merge_base_with_the_files_as_they_are(self):
        with tempfile.TemporaryDirectory() as d:
            def run(*a):
                subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=d, check=True, capture_output=True)
            os.makedirs(os.path.join(d, "tools"))
            for p, src in (("tools/ground_mesh.py", "def a():\n    pass\n\n\ndef b():\n    pass\n"), ("tools/tiers.py", "X = 1\n")):
                with open(os.path.join(d, p), "w", encoding="utf-8", newline="\n") as f:
                    f.write(src)
            run("init", "-q", "-b", "base")
            run("add", ".")
            run("commit", "-q", "-m", "base")
            run("checkout", "-q", "-b", "work")
            with open(os.path.join(d, "tools/ground_mesh.py"), "a", encoding="utf-8", newline="\n") as f:
                f.write("\n\nB = 2\n")  # (uncommitted: read as it is)
            with open(os.path.join(d, "tools/tiers.py"), "w", encoding="utf-8", newline="\n") as f:
                f.write("X = 2\n")
            self.assertEqual(gr.diff(["tools/ground_mesh.py", "tools/tiers.py"], base="base", root=d), ["ground_mesh.B"])
            self.assertIsNone(gr.diff(["tools/ground_mesh.py"], base="no-such-base", root=d))


if __name__ == "__main__":
    unittest.main()
