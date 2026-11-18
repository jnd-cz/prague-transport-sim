# SPDX-License-Identifier: AGPL-3.0-or-later
"""Posted speeds along a line from the OSM tram ways, and the user's posted speeds over them (tools/osm_speeds.py,
#612): python -I tools/test_osm_speeds.py.

A way's correction in data/truth.json `postedSpeeds` holds over its `maxspeed`, and the log says whether OSM still
tags what the fact corrects, now tags the same (no longer needed) or tags something else (look again). Along a
synthetic track the samples read the way under them, the corrected one at its corrected speed, and not a parallel
way 3 m off or one crossing it. The repository's facts each name a way, the speed OSM tagged, the posted one, a
source and a quote, and the section names its reader.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import osm_speeds as O  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = {"id": "fact-65", "way": 2, "osm": 60, "maxspeed": 65}


def way(wid, nodes, maxspeed=None):
    return {"type": "way", "id": wid, "nodes": nodes, "tags": {"maxspeed": maxspeed} if maxspeed else {}}


class Corrections(unittest.TestCase):
    def test_keyed_by_way(self):
        self.assertEqual(O.corrections({"postedSpeeds": [FIX]}), {2: FIX})
        self.assertEqual(O.corrections({}), {})

    def test_the_correction_holds_and_says_what_osm_tags(self):
        fixes = O.corrections({"postedSpeeds": [FIX]})
        for tagged, said in (("60", "65 over OSM's 60 (fact-65)"),
                             ("65", "OSM tags 65 as fact-65 says: the correction is no longer needed"),
                             ("70", "OSM tags 70, not the 60 fact-65 corrects: 65 holds, look at the way again"),
                             (None, "OSM tags none, not the 60 fact-65 corrects: 65 holds")):
            log = []
            speeds = O.way_speeds([way(1, [], "50"), way(2, [], tagged), {"type": "node", "id": 9}], fixes, log.append)
            self.assertEqual(speeds, {1: 50, 2: 65}, tagged)
            self.assertEqual(len(log), 1, log)
            self.assertIn(said, log[0])
            self.assertTrue(log[0].startswith("way 2: "), log)

    def test_maxspeed_values(self):
        self.assertEqual([O.speed({"maxspeed": v}) for v in ("50", "40;30", "65 km/h", "none", "walk")], [50, 40, 65, 0, 0])
        self.assertEqual(O.speed(None), 0)


class Along(unittest.TestCase):
    def test_the_samples_read_the_corrected_way(self):
        # a straight 200 m track along x; way 1 under its first half (50), way 2 under the second (OSM 60, posted 65),
        # way 3 parallel 3 m off (80) and way 4 crossing at x 50 (30): neither is under the track
        nodes = {1: (0.0, 0.0), 2: (100.0, 0.0), 3: (200.0, 0.0), 4: (0.0, 3.0), 5: (200.0, 3.0),
                 6: (50.0, -20.0), 7: (50.0, 20.0)}
        els = [way(1, [1, 2], "50"), way(2, [2, 3], "60"), way(3, [4, 5], "80"), way(4, [6, 7], "30")]
        speeds = O.way_speeds(els, O.corrections({"postedSpeeds": [FIX]}), log=lambda m: None)
        osm, ded, by_way = O.along([[0.0, 0.0], [200.0, 0.0]], els, nodes, [], speeds)
        self.assertEqual(len(osm), 41)
        self.assertEqual(set(osm[:20]), {50})
        self.assertEqual(set(osm[21:]), {65})
        self.assertNotIn(80, osm)
        self.assertNotIn(30, osm)
        self.assertEqual(set(by_way), {1, 2})
        self.assertEqual(by_way[1] + by_way[2], 41)
        self.assertEqual(set(ded), {1})  # no road along it

    def test_a_road_along_it_is_not_dedicated(self):
        nodes = {1: (0.0, 0.0), 2: (200.0, 0.0)}
        els = [way(1, [1, 2], "50")]
        road = {"p": [[0.0, 2.0], [100.0, 2.0]], "w": 6, "c": 1}
        osm, ded, _ = O.along([[0.0, 0.0], [200.0, 0.0]], els, nodes, [road], {1: 50})
        self.assertEqual(set(ded[:20]), {0})
        self.assertEqual(set(ded[22:]), {1})
        self.assertEqual(set(osm), {50})


class Facts(unittest.TestCase):
    def test_the_repository_facts(self):
        with open(os.path.join(ROOT, "data", "truth.json"), encoding="utf-8") as fh:
            truth = json.load(fh)
        self.assertIn("tools/osm_speeds.py", truth["readers"]["postedSpeeds"])
        facts = truth["postedSpeeds"]
        self.assertEqual(len(O.corrections(truth)), len(facts), "one fact per way")
        for f in facts:
            self.assertTrue(isinstance(f["way"], int) and f["way"] > 0, f)
            self.assertTrue(isinstance(f["osm"], int) and isinstance(f["maxspeed"], int) and f["osm"] != f["maxspeed"], f)
            self.assertTrue(f["id"] and f["source"] and f["quote"] and f["text"], f)
        self.assertEqual(O.corrections(truth)[412908226]["maxspeed"], 65)


if __name__ == "__main__":
    unittest.main()
