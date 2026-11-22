# SPDX-License-Identifier: AGPL-3.0-or-later
"""The survey's area layers (tools/zps_layers.py, #703): every code a class or left out with why, any other stops the
build naming it; the per-class report.

    python -I tools/test_zps_layers.py
With the snapshot's survey packages (python -I tools/snapshot.py fetch) it also reads every package's layers.
"""
import os
import sys
import unittest

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import zps_layers as zl  # noqa: E402


class Layers(unittest.TestCase):
    def test_a_layer_is_a_class_left_out_or_a_stop(self):
        self.assertEqual(zl.classify("Dopravni#010000000503_Provozní_plocha_pozemní_komunikace"), "road")
        self.assertEqual(zl.classify("010000001503_Dělící_pás"), "median")
        self.assertIsNone(zl.classify("Stavby#010000017303_Rampa"))
        with self.assertRaises(ValueError) as e:
            zl.classify("Dopravni#010000009903_Nová_vrstva")
        self.assertIn("010000009903", str(e.exception))
        self.assertIn("Nová_vrstva", str(e.exception))

    def test_no_code_both_and_every_one_left_out_says_why(self):
        self.assertFalse(set(zl.CLASSES) & set(zl.LEFT_OUT))
        for c, why in zl.LEFT_OUT.items():
            self.assertRegex(c, r"^\d{12}$")
            name, _, what = why.partition(":")
            self.assertTrue(name.strip() and what.strip(), c)  # (the layer's name, then what it is or why it is out)

    def test_the_summary_counts_and_measures_each_class(self):
        sq = lambda x, y, n, c, h=None: {"c": c, "l": 0, "r": [[x, y, 0], [x + n, y, 0], [x + n, y + n, 0], [x, y + n, 0]],  # noqa: E731
                                         **({"h": [h]} if h else {})}
        hole = [[1, 1, 0], [2, 1, 0], [2, 2, 0], [1, 2, 0]]
        got = zl.summary([sq(0, 0, 10, "road"), sq(20, 0, 4, "road", hole), sq(0, 20, 3, "green")])
        self.assertEqual(got, {"green": {"areas": 1, "m2": 9}, "road": {"areas": 2, "m2": 115}})

    def test_every_layer_of_the_snapshot_is_known(self):
        """The 17 district packages of the five lines: none has a layer the table does not know."""
        import gpkg
        from dtm_packages import DTM, select_packages
        root = os.path.dirname(TOOLS)
        try:
            opls = {p.opl for d in DTM.values() for p in select_packages(root, districts=d)}
        except (OSError, SystemExit) as e:
            self.skipTest(f"no survey packages ({e})")
        if not opls:
            self.skipTest("no survey packages")
        for opl in sorted(opls):
            for t in gpkg.layers(opl):
                zl.classify(t)  # (raises on a layer neither a class nor left out)


if __name__ == "__main__":
    unittest.main()
