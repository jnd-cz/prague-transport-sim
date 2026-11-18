# SPDX-License-Identifier: AGPL-3.0-or-later
"""Source registry and provenance stamps: python -I tools/test_sources.py."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import snapshot  # noqa: E402
import sources as S  # noqa: E402

RAW = Path(__file__).resolve().parent.parent / 'raw'


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

    @unittest.skipUnless((RAW / 'dtm-di/provenance.json').exists(), 'fetch the snapshot: raw/dtm-di/')
    def test_snapshot_dates_resolve(self):
        for sid, s in S.SOURCES.items():
            self.assertTrue(S.dated(sid) or sid.startswith("rule:") or s.date_kind == "records", sid)

    def test_a_source_dated_per_record_dates_every_record(self):
        # the user's facts have no snapshot date: each record names when and where it was said (#239)
        per_record = [sid for sid, s in S.SOURCES.items() if s.date_kind == "records"]
        self.assertEqual(per_record, ["truth"])
        self.assertEqual((S.SOURCES["truth"].group, S.SOURCES["truth"].date), (None, ""))
        truth = json.loads((RAW.parent / 'data/truth.json').read_text(encoding='utf-8'))
        undated = []

        def walk(v, path):
            if isinstance(v, list):
                for i, x in enumerate(v):
                    walk(x, f"{path}[{i}]")
            elif isinstance(v, dict):
                # a record: a fact's text, an answer or a value; it must carry its source
                if any(k in v for k in ("text", "answer", "value")) and not v.get("source"):
                    undated.append(path)
                for k, x in v.items():
                    walk(x, f"{path}.{k}")
        walk(truth, "")
        self.assertEqual(undated, [])


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

    def test_facts_are_kept_per_section_and_dropped_when_none_applies(self):
        p = S.stamp("a.py", {"clearances": S.entry("clearances", [3, 2])})
        self.assertNotIn("facts", p)  # no tool stated one: the provenance is as before #670
        f = [{"id": "b", "state": "holds"}, {"id": "a", "state": "matches"}]
        p = S.stamp("speeds.py", {}, p, facts={"postedSpeeds": f})
        p = S.stamp("signs.py", {}, p, facts={"stopSigns": [{"id": "s", "state": "agrees"}]})
        self.assertEqual(p["facts"]["postedSpeeds"], {"tool": "speeds.py", "facts": sorted(f, key=lambda e: e["id"])})
        self.assertEqual(set(p["facts"]), {"postedSpeeds", "stopSigns"})
        self.assertEqual(set(p["lists"]), {"clearances"})
        p = S.stamp("speeds.py", {}, p, facts={"postedSpeeds": []})
        self.assertEqual(set(p["facts"]), {"stopSigns"})
        with self.assertRaises(ValueError):
            S.stamp("x.py", {}, facts={"postedSpeeds": [{"id": "a", "state": "fine"}]})

    def test_fact_states(self):
        st = S.fact_state
        self.assertEqual([st(65, 60, 60), st(65, 60, 65), st(65, 60, 70), st(65, 60, None)],
                         ["holds", "matches", "changed", "changed"])
        self.assertEqual([st(65, None, 70), st(65, None, None)], ["holds", "holds"])  # nothing recorded: no change seen
        near = lambda a, b: abs(a - b) <= 1  # noqa: E731
        self.assertEqual([st(10, 3, 10.8, near), st(10, 3, 3.5, near), st(10, 3, 6, near)], ["matches", "holds", "changed"])
        # the source as when the user answered holds, even within the fact's tolerance: the user set theirs apart from it
        self.assertEqual([st(10, 9.5, 9.5, near), st(10, 9.5, 9.6, near), st(10, 9.5, 9.6, near, unchanged=near)],
                         ["holds", "matches", "holds"])
        self.assertEqual([st(10, 10, 10.5, near, confirms=True), st(10, 10, 12, near, confirms=True),
                          st(10, 10, None, confirms=True)], ["agrees", "moved", "moved"])

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
