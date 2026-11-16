# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/bench/load_times.py: the medians by part and the download from a set of loads (#509).

    python -P -E tools/test_load_times.py
(the loads themselves need a browser: python -P -E tools/bench/load_times.py --lines 37 --loads 1)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "bench"))
import load_times as lt  # noqa: E402


class Summary(unittest.TestCase):
    RUNS = [{"load": {"total": 1000, "world": 600}, "world": {"terrain mesh": 100, "DTM streets": 300},
             "files": [["/data/line17.json", 500], ["/data/line17.dtm.json", 2000]]},
            {"load": {"total": 1200, "world": 700}, "world": {"terrain mesh": 120},
             "files": [["/data/line17.json", 500]]},
            {"load": {"total": 1100, "world": 650}, "world": {"terrain mesh": 110, "DTM streets": 320},
             "files": [["/data/line17.json", 500], ["/data/line17.dtm.json", 2000]]}]

    def test_medians_per_part_and_the_files_once(self):
        s = lt.summarize(self.RUNS)
        self.assertEqual(s["loads"], 3)
        self.assertEqual(s["load"], {"total": 1100, "world": 650})
        self.assertEqual(s["world"], {"terrain mesh": 110, "DTM streets": 310})  # (the two runs that had it)
        self.assertEqual(s["files"], {"/data/line17.dtm.json": 2000, "/data/line17.json": 500})
        self.assertEqual(s["download MB"], 0.0)

    def test_the_table_shows_before_and_after_and_what_is_gone(self):
        before = {"17": lt.summarize(self.RUNS)}
        after = {"17": lt.summarize([{"load": {"total": 500}, "world": {"ground": 50}, "files": []}])}
        text = "\n".join(lt.table(after, before))
        self.assertIn("1100 -> 500 ms", text)
        self.assertIn("terrain mesh                 110 -> gone", text)
        self.assertIn("ground", text)


if __name__ == "__main__":
    unittest.main()
