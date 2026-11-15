# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/survey_ground_answers.py: review answers into data/truth.json surveyGround, the rest of the file untouched (#446).

    python -I tools/test_survey_ground_answers.py
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import survey_ground_answers as sga  # noqa: E402
from survey_ground_answers import ANSWERS, KIND  # noqa: E402

SURVEY, LIDAR = (k for k, v in sorted(ANSWERS.items(), key=lambda kv: kv[1] != "survey"))


class Answers(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.dir, "review"))
        cards = {"line": "37", "findings": [
            {"kind": KIND, "x": 100.04, "y": -20.0, "lat": 50.1, "lon": 14.5, "info": "road, 400 m²"},
            {"kind": KIND, "x": 200.0, "y": 30.0, "lat": 50.2, "lon": 14.6, "info": "green, 150 m²"}]}
        json.dump(cards, open(os.path.join(self.dir, "review", "survey-ground-37.json"), "w", encoding="utf-8"))
        self.answers = os.path.join(self.dir, "line37.json")
        json.dump({"items": {
            f"file|{KIND}|100.0,-20.0": {"v": SURVEY, "note": "a new car park", "t": 1793484169871},
            f"file|{KIND}|200.0,30.0": {"v": "unsure", "t": 1793484169871},
            "kerbs|sidewalk foot|1.0,2.0": {"v": "yes"}}}, open(self.answers, "w", encoding="utf-8"))

    def test_options_become_facts_others_stay_held(self):
        new, held = sga.facts([self.answers], sga.cards(os.path.join(self.dir, "review")))
        self.assertEqual([(p["lat"], p["verdict"], p["line"]) for p in new], [(50.1, "survey", "37")])
        self.assertIn("a new car park", new[0]["said"])
        self.assertEqual(len(held), 1)
        self.assertIn("unsure", held[0][1])

    def test_a_new_answer_replaces_the_one_at_its_place(self):
        old = [{"lat": 50.1, "lon": 14.5, "verdict": "lidar"}, {"lat": 50.3, "lon": 14.7, "verdict": "survey"}]
        out = sga.merged(old, [{"lat": 50.1, "lon": 14.5, "verdict": "survey"}])
        self.assertEqual([(p["lat"], p["verdict"]) for p in out], [(50.1, "survey"), (50.3, "survey")])

    def test_only_the_section_is_rewritten(self):
        """data/truth.json is formatted by hand: the other sections stay byte for byte."""
        text = '{\n "a": [1, 2,\n   3],\n "surveyGround": {\n  "note": "n",\n  "places": []\n },\n "z": {"k": 1}\n}\n'
        out = sga.rewrite_section(text, {"note": "n", "places": [{"lat": 50.1}]})
        self.assertTrue(out.startswith('{\n "a": [1, 2,\n   3],\n "surveyGround": {'))
        self.assertTrue(out.endswith(',\n "z": {"k": 1}\n}\n'))
        self.assertEqual(json.loads(out)["surveyGround"]["places"], [{"lat": 50.1}])


if __name__ == "__main__":
    unittest.main()
