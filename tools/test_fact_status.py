# SPDX-License-Identifier: AGPL-3.0-or-later
"""The facts that override a source, by their state in the built data (tools/fact_status.py, #670):
python -I tools/test_fact_status.py.

Built files' provenance states facts per data/truth.json section; the report lists each fact once with its lines,
leads with the state to look at where lines differ, lists a fact no file states as not stated and a stated one no
longer in truth.json as retired, and prints the states to look at (matches, changed, moved) first. On the repository's
data it runs and names every section of sources.OVERRIDES that has facts.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fact_status as F  # noqa: E402
import sources  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRUTH = {"postedSpeeds": [{"id": "a", "way": 1, "osm": 60, "maxspeed": 65},
                          {"id": "b", "way": 2, "osm": 40, "maxspeed": 50},
                          {"id": "c", "way": 3, "osm": 30, "maxspeed": 25}]}


def prov(*facts, tool="tools/osm_speeds.py"):
    return sources.stamp(tool, {}, facts={"postedSpeeds": [dict(f) for f in facts]})


class Collect(unittest.TestCase):
    def test_each_fact_once_with_its_lines(self):
        files = [("line37.json", prov({"id": "a", "state": "matches", "now": 65}, {"id": "b", "state": "holds"})),
                 ("line9.json", prov({"id": "b", "state": "changed", "now": 45}, {"id": "gone", "state": "holds"}))]
        facts = {f["id"]: f for f in F.collect(files=files, truth=TRUTH)}
        self.assertEqual(facts["a"]["state"], "matches")
        self.assertEqual(facts["a"]["lines"], [("37", "matches")])
        self.assertEqual(facts["a"]["detail"], {"now": 65})
        # the lines differ: changed leads, its detail with it
        self.assertEqual(facts["b"]["state"], "changed")
        self.assertEqual(facts["b"]["lines"], [("37", "holds"), ("9", "changed")])
        self.assertEqual(facts["b"]["detail"], {"now": 45})
        self.assertEqual(facts["c"]["state"], "not stated")
        self.assertEqual(facts["c"]["tool"], "tools/osm_speeds.py")
        self.assertEqual(facts["gone"]["state"], "retired")
        self.assertEqual(F.counts(facts.values()), {"matches": 1, "changed": 1, "not stated": 1, "retired": 1})

    def test_the_report_leads_with_what_to_look_at(self):
        files = [("line37.json", prov({"id": "a", "state": "matches", "now": 65}, {"id": "b", "state": "holds"}))]
        text = F.report(F.collect(files=files, truth=TRUTH))
        self.assertTrue(text.startswith("facts that override a source: holds 1 · matches 1 · not stated 1"), text)
        self.assertIn("matches: the source gives the fact's value now", text)
        self.assertIn("  postedSpeeds a (lines 37; now 65)", text)
        self.assertNotIn("postedSpeeds b", text)  # holds: listed with --all only
        full = F.report(F.collect(files=files, truth=TRUTH), everything=True)
        self.assertIn("  postedSpeeds b (lines 37)", full)
        self.assertIn("  postedSpeeds c", full)

    def test_the_files_read(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "data"))
            for name, js in (("line37.json", {"provenance": prov({"id": "a", "state": "holds"})}),
                             ("line37.dtm.json", {"provenance": sources.stamp("x.py", {})}),
                             ("MANIFEST.json", {"files": {}}), ("truth.json", TRUTH), ("lines.json", [1, 2])):
                with open(os.path.join(d, "data", name), "w", encoding="utf-8") as fh:
                    json.dump(js, fh)
            self.assertEqual([n for n, _ in F.built_files(d)], ["line37.json"])
            self.assertEqual({f["id"]: f["state"] for f in F.collect(d)}, {"a": "holds", "b": "not stated", "c": "not stated"})

    def test_the_repository(self):
        if not os.path.exists(os.path.join(ROOT, "data", "line37.json")):
            self.skipTest("no data/: python -I tools/snapshot.py data-fetch")
        facts = F.collect()
        with open(os.path.join(ROOT, "data", "truth.json"), encoding="utf-8") as fh:
            truth = json.load(fh)
        have = {s for s in sources.OVERRIDES if sources.overriding(truth, s)}
        self.assertEqual({f["section"] for f in facts if f["state"] != "retired"}, have)
        self.assertTrue(F.report(facts).startswith("facts that override a source: "))


if __name__ == "__main__":
    unittest.main()
