"""Source registry and provenance stamps: python -I tools/test_sources.py."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import snapshot  # noqa: E402
import sources as S  # noqa: E402


class Registry(unittest.TestCase):
    def test_every_chain_names_known_sources_once(self):
        for layer, chain in S.LAYERS.items():
            self.assertTrue(chain, layer)
            self.assertEqual(len(set(chain)), len(chain), layer)
            for sid in chain:
                self.assertIn(sid, S.SOURCES, f"{layer}: {sid}")

    def test_sources_point_at_snapshot_groups_and_rules_have_none(self):
        groups = {g["name"] for g in snapshot.SOURCES}
        for sid, s in S.SOURCES.items():
            if sid.startswith("rule:"):
                self.assertIsNone(s.group, sid)
                self.assertEqual(s.attribution, "", sid)
            elif s.group:
                self.assertIn(s.group, groups, sid)
                self.assertIn(": ", s.attribution, sid)

    def test_snapshot_dates_resolve(self):
        for sid in S.SOURCES:
            self.assertTrue(S.dated(sid) or sid.startswith("rule:"), sid)


class Stamp(unittest.TestCase):
    def test_counts_must_cover_the_chain(self):
        with self.assertRaises(ValueError):
            S.entry("terrain", [1, 2])
        with self.assertRaises(KeyError):
            S.single("terrain", "osm", 3)

    def test_tools_writing_one_file_add_their_lists(self):
        p = S.stamp("a.py", {"terrain": S.single("terrain", "coarse", 100, "cells")})
        p = S.stamp("b.py", {"clearances": S.entry("clearances", [3, 2])}, p)
        self.assertEqual(set(p["lists"]), {"terrain", "clearances"})
        self.assertEqual(p["lists"]["terrain"]["tool"], "a.py")
        self.assertEqual(p["lists"]["clearances"]["levels"], ["osm", "rule:assumed"])
        self.assertEqual(list(p["sources"]), ["coarse", "osm", "rule:assumed"])
        self.assertNotIn("attribution", p["sources"]["rule:assumed"])

    def test_a_level_with_no_features_is_not_a_source(self):
        p = S.stamp("c.py", {"blocks": S.entry("terrain", [5, 0, 0], "blocks", {"x": 1})})
        self.assertEqual(list(p["sources"]), ["ipr-dtm"])
        self.assertEqual(p["lists"]["blocks"]["checks"], {"x": 1})

    def test_credits_once_per_source(self):
        a = S.stamp("a.py", {"roads": S.single("streets", "osm", 1), "green": S.single("areas", "osm", 1)})
        b = S.stamp("b.py", {"stop": S.single("signals", "osm", 1)})
        self.assertEqual(S.attribution(a, b), "Map data: © OpenStreetMap contributors (ODbL).")
        c = S.stamp("c.py", {"t": S.single("trees", "trees", 1), "w": S.single("walls", "walls", 1)})
        self.assertEqual(S.attribution(c), "Trees, Retaining walls: datový podklad © IPR Praha (CC BY 4.0).")


if __name__ == "__main__":
    unittest.main()
