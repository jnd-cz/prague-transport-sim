# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/sysinfo.py: the pool whose workers load their payload from one file (#516).

    python -I tools/test_sysinfo.py
"""
import glob
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sysinfo  # noqa: E402

_GOT = {}


def _keep(big, small):
    _GOT.update(big=big, small=small)


def _ask(i):
    return len(_GOT["big"]), _GOT["small"][i]


class Pool(unittest.TestCase):
    def test_workers_load_the_payload_and_the_file_goes(self):
        before = set(glob.glob(os.path.join(tempfile.gettempdir(), "pool-*.pickle")))
        big, small = list(range(200000)), {i: i * i for i in range(10)}
        with sysinfo.pool(3, _keep, big, small) as ex:
            files = set(glob.glob(os.path.join(tempfile.gettempdir(), "pool-*.pickle"))) - before
            self.assertEqual(len(files), 1)
            self.assertEqual(list(ex.map(_ask, range(10))), [(200000, i * i) for i in range(10)])
        self.assertFalse(any(os.path.exists(f) for f in files))

    def test_workers(self):
        self.assertGreaterEqual(sysinfo.workers(1.0, most=3), 1)
        self.assertLessEqual(sysinfo.workers(1.0, most=3), 3)


if __name__ == "__main__":
    unittest.main()
