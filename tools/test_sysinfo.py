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


class Available(unittest.TestCase):
    """Linux: MemAvailable, not MemFree (#897)."""
    def meminfo(self, text):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        p = os.path.join(d.name, "meminfo")
        with open(p, "w", encoding="ascii", newline="\n") as f:
            f.write(text)
        return p

    def test_mem_available_not_mem_free(self):
        p = self.meminfo("MemTotal:       32000000 kB\nMemFree:         1500000 kB\nMemAvailable:   24000000 kB\n"
                         "Buffers:          200000 kB\nCached:         21000000 kB\n")
        self.assertAlmostEqual(sysinfo.meminfo_available_gb(p), 24000000 * 1024 / 1e9)

    def test_no_field_or_no_file_is_unknown(self):
        self.assertIsNone(sysinfo.meminfo_available_gb(self.meminfo("MemTotal: 32000000 kB\nMemFree: 1500000 kB\n")))
        self.assertIsNone(sysinfo.meminfo_available_gb(os.path.join(tempfile.gettempdir(), "no-such-meminfo")))

    def test_available_gb_reads_meminfo_off_windows(self):
        p = self.meminfo("MemFree: 1000 kB\nMemAvailable: 2000000 kB\n")
        if os.name == "nt":
            self.assertGreater(sysinfo.available_gb(), 0)  # (GlobalMemoryStatusEx: meminfo is not read)
            return
        old = sysinfo.MEMINFO
        try:
            sysinfo.meminfo_available_gb.__defaults__ = (p,)
            self.assertAlmostEqual(sysinfo.available_gb(), 2000000 * 1024 / 1e9)
        finally:
            sysinfo.meminfo_available_gb.__defaults__ = (old,)


if __name__ == "__main__":
    unittest.main()
