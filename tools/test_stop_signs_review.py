# SPDX-License-Identifier: AGPL-3.0-or-later
"""The stop-sign answers' import into data/truth.json, and a sign fact's state against the sign the sources give
(#670): python -P -E tools/test_stop_signs_review.py."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stop_signs_review as R  # noqa: E402


def card(i, stop, towards, frm=None, line="22", osm=True):
    marks = [{"x": 10.0, "y": 0.0, "label": "OSM stop position (the pin)", "color": R.OSM}] if osm else []
    marks.append({"x": 2.0, "y": 0.0, "label": "timetable (GTFS) point", "color": R.GTFS})
    return {"kind": "stop sign", "id": i, "line": line, "stop": stop, "towards": towards, "from": frm, "back": False,
            "x": 10.0, "y": 0.0, "marks": marks, **({"osm_node": 7} if osm else {})}


class State(unittest.TestCase):
    def fact(self, how, x=0.0, y=0.0, pin=None):
        return {"stop": "A", "towards": "B", "x": x, "y": y, "how": how, **({"pin": pin} if pin else {})}

    def test_a_correction_against_the_sign_the_sources_give(self):
        placed = self.fact("placed on the map")
        self.assertEqual(R.sign_state(placed, ("dtmpoints", 0.6, 0.6)),
                         {"id": "A → B", "state": "matches", "how": "placed on the map", "now": "dtmpoints", "off": 0.85,
                          "at": [0.0, 0.0], "src": [0.6, 0.6]})
        # in the plane, within 2 m of the DTM's sign (the user, 2026-11-18): 1.6 m along or across matches, 2.5 m holds
        self.assertEqual(R.sign_state(placed, ("dtmpoints", 0.0, 1.6))["state"], "matches")
        self.assertEqual(R.sign_state(placed, ("dtmpoints", 2.5, 0.0))["state"], "holds")
        # only the DTM's: OSM's stop position on the track's centre line never retires the user's sign
        self.assertEqual(R.sign_state(placed, ("osm", 0.3, 0.0))["state"], "holds")
        self.assertEqual(R.sign_state(self.fact(R.OPTIONS[1]), ("osm", 0.3, 0.0))["state"], "holds")
        self.assertEqual(R.sign_state(placed, None), {"id": "A → B", "state": "holds", "how": "placed on the map", "now": None,
                                                      "off": None, "at": [0.0, 0.0], "src": None})
        # placed 1.6 m from the DTM's sign the card showed (its pin): the user set theirs apart, it holds (Královka)
        self.assertEqual(R.sign_state(self.fact(R.PLACED, pin=[1.6, 0.0]), ("dtmpoints", 1.6, 0.05))["state"], "holds")
        # with the pin recorded: the source still there holds, gone elsewhere changed
        pinned = self.fact("placed on the map", pin=[5.0, 0.0])
        self.assertEqual(R.sign_state(pinned, ("osm", 5.4, 0.0))["state"], "holds")
        self.assertEqual(R.sign_state(pinned, ("osm", 9.0, 0.0))["state"], "changed")

    def test_a_confirmation_agrees_or_the_source_moved(self):
        for how in R.CONFIRMS:
            self.assertEqual(R.sign_state(self.fact(how), ("dtmpoints", 0.2, -0.1))["state"], "agrees", how)
            self.assertEqual(R.sign_state(self.fact(how), ("osm", 3.0, 0.0))["state"], "moved", how)
            self.assertEqual(R.sign_state(self.fact(how), None)["state"], "moved", how)


class Again(unittest.TestCase):
    def test_an_answered_stop_asked_again_gets_a_card_of_its_own(self):
        path = [(0.0, 0.0), (200.0, 0.0)]
        stops = [{"name": "A", "s": 50.0}, {"name": "B", "s": 150.0}]
        dtm = [(70.0, -2.5)]  # (20 m past A's timetable point, on the right: a card without the fact)
        fact = {"stop": "A", "towards": "B", "x": 52.0, "y": -2.2, "how": R.PLACED}
        a = lambda cards: [c for c in cards if c["stop"] == "A"]  # noqa: E731  (B, without a DTM sign, has its own card)
        self.assertEqual(a(R.review("17", path, stops, [], dtm, [fact], 5.0)[0]), [])
        cards = a(R.review("17", path, stops, [], dtm, [fact], 5.0, again={"A → B"})[0])
        self.assertEqual([c["id"] for c in cards], ["stop-sign-17-A-1-again"])
        self.assertIn({"x": 52.0, "y": -2.2, "label": "your sign now (data/truth.json)", "color": R.YOURS}, cards[0]["marks"])
        self.assertIn(R.OWN, cards[0]["options"])
        # its answer replaces the fact (the newest per stop)
        new = R.sign_facts(cards, {"17": [{"kind": "stop sign", "id": "stop-sign-17-A-1-again", "v": R.OWN, "px": 49.0, "py": -2.4, "t": 5}]})
        self.assertEqual([(f["stop"], f["towards"], f["x"], f["how"]) for f in new], [("A", "B", 49.0, R.PLACED)])


class Pole(unittest.TestCase):
    def test_a_placed_sign_or_a_dtm_signs_point_is_a_pole(self):
        dtm = [(10.0, 2.0)]
        f = lambda how, x, y: {"stop": "A", "towards": "B", "x": x, "y": y, "how": how}  # noqa: E731
        self.assertTrue(R.pole(f(R.PLACED, 50.0, 3.0), dtm))
        self.assertTrue(R.pole(f(R.BY_SOURCE["DTM"], 10.0, 2.0), dtm))
        self.assertTrue(R.pole(f(R.OPTIONS[0], 10.1, 2.1), dtm))  # (at the pin, the pin the DTM's)
        # OSM's stop position on the track's centre line, the GTFS point: no pole
        self.assertFalse(R.pole(f(R.OPTIONS[0], 30.0, 0.0), dtm))
        self.assertFalse(R.pole(f(R.BY_SOURCE["OSM"], 30.0, 0.0), dtm))
        self.assertFalse(R.pole(f(R.OPTIONS[1], 12.0, 2.0), dtm))


class Import(unittest.TestCase):
    def test_answers_become_facts(self):
        cards = [card("a", "A", "B"), card("b", "B", "C"), card("c", "C", None, "B"), card("d", "D", "E"),
                 card("e", "E", "F", line="23")]
        answers = {"22": [
            {"kind": "stop sign", "id": "a", "v": R.OPTIONS[0], "t": 1},  # the pin
            {"kind": "stop sign", "id": "b", "v": R.OPTIONS[1], "t": 1},  # the GTFS point
            {"kind": "stop sign", "id": "c", "v": "unsure", "t": 1},  # held
            {"kind": "stop sign", "id": "d", "v": "unsure", "px": 5.0, "py": 1.0, "note": "here", "t": 1},  # placed wins
            {"kind": "stop sign", "id": "a", "v": R.OPTIONS[1], "t": 0},  # older: ignored
        ], "23": [{"kind": "stop sign", "id": "e", "v": "placed on the map", "px": 3.0, "py": 0.5, "t": 2}]}
        f = {x["stop"]: x for x in R.sign_facts(cards, answers)}
        self.assertEqual(set(f), {"A", "B", "D", "E"})
        self.assertEqual((f["A"]["x"], f["A"]["how"]), (10.0, R.OPTIONS[0]))
        self.assertEqual(f["B"]["x"], 2.0)
        self.assertEqual((f["D"]["x"], f["D"]["y"], f["D"]["note"], f["D"]["towards"]), (5.0, 1.0, "here", "E"))
        self.assertIn("stop-signs-23.json", f["E"]["source"])
        self.assertNotIn("t", f["E"])

    def test_answers_name_their_source(self):
        # #310: the user picks the right source, or places an own mark
        cards = [card("o", "O", "P"), card("g", "G", "H"), card("m", "M", "N"), card("n", "Q", "R"), card("u", "U", "V")]
        cards[2]["marks"].insert(0, {"x": 7.0, "y": 0.5, "label": "DTM stop sign, state 2024", "color": R.DTM})
        answers = {"22": [
            {"kind": "stop sign", "id": "o", "v": R.BY_SOURCE["OSM"], "t": 1},
            {"kind": "stop sign", "id": "g", "v": R.BY_SOURCE["GTFS"], "t": 1},
            {"kind": "stop sign", "id": "m", "v": R.BY_SOURCE["DTM"], "t": 1},
            {"kind": "stop sign", "id": "n", "v": R.OWN, "t": 1},  # no point placed: held
            {"kind": "stop sign", "id": "u", "v": R.OWN, "px": 4.0, "py": 0.2, "t": 1},
        ]}
        f = {x["stop"]: x for x in R.sign_facts(cards, answers)}
        self.assertEqual(set(f), {"O", "G", "M", "U"})
        self.assertEqual((f["O"]["x"], f["G"]["x"], f["M"]["x"], f["M"]["y"]), (10.0, 2.0, 7.0, 0.5))
        self.assertEqual((f["U"]["x"], f["U"]["how"]), (4.0, "placed on the map"))
        # the card's pin is recorded with the answer, and which source it was (#670)
        self.assertEqual((f["O"]["pin"], f["O"]["pinFrom"], f["M"]["pinFrom"]), ([10.0, 0.0], "OSM", "DTM"))
        g = R.sign_facts([card("x", "X", "Y", osm=False)], {"22": [{"kind": "stop sign", "id": "x", "v": R.OWN, "px": 1.0, "py": 0.0, "t": 1}]})
        self.assertEqual(g[0]["pinFrom"], "GTFS")

    def test_same_sign_from_two_lines_keeps_the_newest(self):
        cards = [card("x22", "S", "T"), card("x23", "S", "T", line="23")]
        answers = {"22": [{"kind": "stop sign", "id": "x22", "v": "p", "px": 1.0, "py": 0.0, "t": 5}],
                   "23": [{"kind": "stop sign", "id": "x23", "v": "p", "px": 2.0, "py": 0.0, "t": 9}]}
        (f,) = R.sign_facts(cards, answers)
        self.assertEqual(f["x"], 2.0)

    def test_last_stop_is_keyed_by_the_previous_one(self):
        cards = [card("z", "Z", None, "Y")]
        (f,) = R.sign_facts(cards, {"22": [{"kind": "stop sign", "id": "z", "v": "p", "px": 1.0, "py": 0.0, "t": 1}]})
        self.assertEqual((f.get("towards"), f["from"]), (None, "Y"))

    def test_write_truth_replaces_its_own_section_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "truth.json"
            p.write_text('{\n "note": "x",\n "stops": [\n  {"name": "A"}\n ]\n}\n', encoding="utf-8")
            R.write_truth([{"stop": "A"}], str(p))
            R.write_truth([{"stop": "B"}], str(p))
            t = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(list(t), ["note", "stops", "stopSigns"])
            self.assertEqual(t["stopSigns"]["signs"], [{"stop": "B"}])
            self.assertTrue(p.read_text(encoding="utf-8").startswith('{\n "note": "x",\n "stops": [\n  {"name": "A"}'))

    def test_a_section_after_stop_signs_stays(self):
        # (#351 added substations behind stopSigns; the import cut everything after its own section)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "truth.json"
            p.write_text('{\n "note": "x",\n "stopSigns": {\n  "signs": []\n },\n "substations": {\n  "list": [1]\n }\n}\n',
                         encoding="utf-8")
            R.write_truth([{"stop": "B"}], str(p))
            text = p.read_text(encoding="utf-8")
            t = json.loads(text)
            self.assertEqual(list(t), ["note", "stopSigns", "substations"])
            self.assertEqual((t["stopSigns"]["signs"], t["substations"]), ([{"stop": "B"}], {"list": [1]}))
            self.assertTrue(text.endswith(',\n "substations": {\n  "list": [1]\n }\n}\n'))


if __name__ == "__main__":
    unittest.main()
