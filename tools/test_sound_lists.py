# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/sound_lists.py: the lists read from src/audio.js, and docs/vehicles.md up to date with them.

    python -I tools/test_sound_lists.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sound_lists  # noqa: E402

SAMPLE = """export const EVENTS = {
  'door.open': 'the doors start opening',
  'points': 'an axle over a switch\\'s frog',
};
export const LOOPS = {
  'motor': 'traction motors',
};
export const PARAMS = {
  'speed': 'm/s',
};
"""


class SoundLists(unittest.TestCase):
    def test_reads_entries(self):
        ls = sound_lists.lists(SAMPLE)
        self.assertEqual(ls["EVENTS"], [("door.open", "the doors start opening"), ("points", "an axle over a switch's frog")])
        self.assertEqual(ls["LOOPS"], [("motor", "traction motors")])
        self.assertEqual(ls["PARAMS"], [("speed", "m/s")])

    def test_the_game_lists(self):
        ls = sound_lists.lists()
        names = [a for a, _ in ls["EVENTS"]]
        for e in ("door.open", "door.close", "door.buzzer", "bell", "points", "crossing", "joint"):
            self.assertIn(e, names)
        self.assertEqual([a for a, _ in ls["LOOPS"]], ["motor", "rolling", "flange", "mg"])

    def test_docs_up_to_date(self):
        doc = open(sound_lists.DOC, encoding="utf-8").read()
        self.assertIn(sound_lists.section(sound_lists.lists()), doc, "python -I tools/sound_lists.py")


if __name__ == "__main__":
    unittest.main()
