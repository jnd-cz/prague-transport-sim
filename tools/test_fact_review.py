# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/fact_review.py: a card per fact a source matches, and the answers retiring them in data/truth.json.
    python -P -E tools/test_fact_review.py"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fact_review as FR  # noqa: E402
import stop_signs_review as R  # noqa: E402

# a truth.json in the file's mixed styles: one section dumped with indent 1, one written by hand
TRUTH = """{
 "stopSigns": {
  "note": "n",
  "signs": [
   {
    "stop": "A",
    "towards": "B",
    "x": 10.0,
    "y": 2.0,
    "how": "placed on the map",
    "source": "user"
   },
   {
    "stop": "C",
    "towards": "D",
    "x": 0.0,
    "y": 0.0,
    "how": "placed on the map",
    "source": "user"
   }
  ]
 },
 "trackSources": {"switchTips": [{"place": "P", "near": [1, 2], "tip": [3, 4]},
                                 {"place": "Q", "near": [5, 6], "tip": [7, 8]}],
  "other": [1, 2]}
}
"""


def fact(section, fid, state, at=None, src=None, off=None, lines=(("22", None),)):
    d = {k: v for k, v in (("at", at), ("src", src), ("off", off)) if v is not None}
    return {"section": section, "id": fid, "state": state, "detail": d, "lines": [[ln, s or state] for ln, s in lines]}


class Cards(unittest.TestCase):
    def test_a_card_per_match_with_a_point_farthest_first(self):
        got = FR.cards([
            fact("stopSigns", "A → B", "matches", [10.0, 2.0], [10.5, 2.0], 0.5, lines=(("22", None), ("23", None))),
            fact("stopSigns", "C → D", "matches", [0.0, 0.0], [0.0, 1.4], 1.4),
            fact("switchTips", "P", "matches", [3.0, 4.0], [3.1, 4.0], 0.1, lines=(("17", "holds"), ("37", None))),
            fact("stopSigns", "E → F", "holds", [0.0, 0.0], [5.0, 0.0], 5.0),  # holds: no card
            fact("postedSpeeds", "s", "matches"),  # no point: listed by fact_status, retired by hand
        ])
        self.assertEqual({k: [c["fact"] for c in v] for k, v in got.items()}, {"22": ["C → D", "A → B"], "37": ["P"]})
        a = got["22"][1]
        self.assertEqual((a["id"], a["mag"], a["lines"], a["options"][0]), ("fact-stopSigns-A → B", 50, ["22", "23"], FR.RETIRE_SIGN))
        self.assertEqual([m["color"] for m in a["marks"]], [FR.YOURS, FR.SOURCE])
        self.assertEqual(got["37"][0]["options"][0], FR.RETIRE)


class Truth(unittest.TestCase):
    def test_drop_cuts_the_item_alone(self):
        t = FR.drop(TRUTH, ("trackSources", "switchTips"), 0)
        self.assertEqual(json.loads(t)["trackSources"]["switchTips"], [{"place": "Q", "near": [5, 6], "tip": [7, 8]}])
        self.assertEqual(t.replace('{"place": "P", "near": [1, 2], "tip": [3, 4]},\n                                 ', ""), t)
        self.assertEqual(json.loads(FR.drop(TRUTH, ("trackSources", "switchTips"), 1))["trackSources"]["switchTips"][0]["place"], "P")
        self.assertIn('"switchTips": [],\n', FR.drop(t, ("trackSources", "switchTips"), 0))  # the last one: []
        # everything outside the item unchanged
        self.assertTrue(t.startswith(TRUTH[:TRUTH.index('{"place"')]))
        self.assertTrue(t.endswith(TRUTH[TRUTH.index('],\n  "other"'):]))

    def test_put_dumps_the_item_at_its_indent(self):
        old = json.loads(TRUTH)["stopSigns"]["signs"][0]
        t = FR.put(TRUTH, ("stopSigns", "signs"), 0, old)
        self.assertEqual(t, TRUTH)

    def test_retired_stop_sign_confirms_the_dtm_sign_other_facts_go(self):
        card = FR.cards([fact("stopSigns", "A → B", "matches", [10.0, 2.0], [10.5, 2.25], 0.56)])["22"][0]
        t = FR.retire(TRUTH, card, "2026-11-19")
        f = json.loads(t)["stopSigns"]["signs"][0]
        self.assertEqual((f["x"], f["y"], f["how"], f["pin"], f["pinFrom"]), (10.5, 2.25, R.BY_SOURCE["DTM"], [10.5, 2.25], "DTM"))
        self.assertIn("fact-match review", f["source"])
        self.assertIn(R.BY_SOURCE["DTM"], R.CONFIRMS)  # (a confirmation now: agrees while the DTM keeps the sign)
        self.assertEqual(json.loads(t)["stopSigns"]["signs"][1], json.loads(TRUTH)["stopSigns"]["signs"][1])
        tip = FR.cards([fact("switchTips", "Q", "matches", [7.0, 8.0], [7.1, 8.0], 0.1)])["22"][0]
        self.assertEqual([f["place"] for f in json.loads(FR.retire(TRUTH, tip, "2026-11-19"))["trackSources"]["switchTips"]], ["P"])

    def test_import_retires_what_the_user_answered_retire(self):
        with tempfile.TemporaryDirectory() as root:
            for d in ("data", "reports/review", "reports/reviews"):
                os.makedirs(os.path.join(root, d))
            with open(os.path.join(root, "data", "truth.json"), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(TRUTH)
            by_line = FR.cards([fact("stopSigns", "A → B", "matches", [10.0, 2.0], [10.5, 2.0], 0.5),
                                fact("stopSigns", "C → D", "matches", [0.0, 0.0], [0.0, 1.4], 1.4),
                                fact("switchTips", "P", "matches", [3.0, 4.0], [3.1, 4.0], 0.1)])
            FR.write_sets(by_line, root)
            store = {"items": {
                "fact-stopSigns-A → B": {"kind": "fact match", "id": "fact-stopSigns-A → B", "v": FR.RETIRE_SIGN, "t": 2},
                "fact-stopSigns-C → D": {"kind": "fact match", "id": "fact-stopSigns-C → D", "v": FR.KEEP, "t": 2},
                "fact-switchTips-P": {"kind": "fact match", "id": "fact-switchTips-P", "v": FR.RETIRE, "t": 2}}}
            with open(os.path.join(root, "reports", "reviews", "line22.json"), "w", encoding="utf-8") as fh:
                json.dump(store, fh)
            FR.do_import(["22"], os.path.join("reports", "reviews"), root)
            with open(os.path.join(root, "data", "truth.json"), encoding="utf-8") as fh:
                t = json.load(fh)
            self.assertEqual([(f["stop"], f["how"]) for f in t["stopSigns"]["signs"]],
                             [("A", R.BY_SOURCE["DTM"]), ("C", "placed on the map")])
            self.assertEqual([f["place"] for f in t["trackSources"]["switchTips"]], ["Q"])
            # a line without matches loses its set
            FR.write_sets({}, root)
            self.assertEqual(os.listdir(os.path.join(root, "reports", "review")), [])


if __name__ == "__main__":
    unittest.main()
