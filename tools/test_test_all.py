# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/test_all.py: how it runs a test. python -I tools/test_all.py -k test_test_all"""
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_all  # noqa: E402


class Flags(unittest.TestCase):
    def test_a_test_writes_utf8_to_the_pipe_with_either_kind(self):
        # (#891: a commit title with "ř" on a cp1252 pipe stopped test_overview_page.py; PYTHONIOENCODING is ignored
        # under -I and -E)
        for kind in ("-I", "-P -E"):
            r = subprocess.run([sys.executable, *test_all.flags(kind), "-c", "print('Rašínovo nábřeží → Výtoň')"],
                               capture_output=True, env={**os.environ, "PYTHONIOENCODING": "cp1252"})
            self.assertEqual(r.returncode, 0, (kind, r.stderr))
            self.assertEqual(r.stdout.decode("utf-8").strip(), "Rašínovo nábřeží → Výtoň", kind)

    def test_the_kinds_keep_their_isolation(self):
        self.assertEqual(test_all.flags("-I")[0], "-I")
        self.assertEqual(test_all.flags("-P -E")[:2], ["-P", "-E"])
        self.assertEqual(test_all.flags("browser")[:2], ["-P", "-E"])


if __name__ == "__main__":
    unittest.main()
