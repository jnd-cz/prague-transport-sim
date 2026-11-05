"""The stop-sign answers' import into data/truth.json: python -P -E tools/test_stop_signs_review.py."""
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


class Import(unittest.TestCase):
    def test_answers_become_facts(self):
        cards = [card("a", "A", "B"), card("b", "B", "C"), card("c", "C", None, "B"), card("d", "D", "E"),
                 card("e", "E", "F", line="23")]
        answers = {"22": [
            {"kind": "stop sign", "id": "a", "v": R.OPTIONS[0], "t": 1}, # the pin
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


if __name__ == "__main__":
    unittest.main()
