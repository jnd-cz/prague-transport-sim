# SPDX-License-Identifier: AGPL-3.0-or-later
"""How many things to run at once: by cores and by free memory (the parallel tools cap themselves by it).

    from sysinfo import workers
    n = workers(gb_each=2.0, most=4)   # e.g. headless pages (~2 GB for line 17)
    with pool(n, initializer, big, data) as ex: ...   # each worker calls initializer(big, data) at its start
"""
from concurrent.futures import ProcessPoolExecutor
import ctypes
import os


def available_gb():
    """Physical memory free now, in GB (None if unknown)."""
    try:
        if os.name == "nt":
            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS()
            m.dwLength = ctypes.sizeof(m)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                return m.ullAvailPhys / 1e9
            return None
        return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 1e9
    except (OSError, ValueError, AttributeError):
        return None


def workers(gb_each, most=4):
    """At most half the cores, `most`, and what free memory holds at `gb_each` GB apiece (keeping 2 GB
    for the rest of the machine); at least 1."""
    n = min(most, max(1, (os.cpu_count() or 2) // 2))
    free = available_gb()
    if free is not None:
        n = min(n, int((free - 2) // gb_each))
    return max(1, n)


def pool(n, initializer, *payload):
    """A process pool of n workers, each calling initializer(*payload) at its start, the payload pickled once into a
    temporary file (outside the checkout) that they load. A spawned worker gets its arguments pickled for it alone: the
    heights' staging gave 12 workers 115 MB that took 2.7 s each to pickle, one after another (#516). The file goes
    when the pool shuts down."""
    import pickle
    import tempfile
    fd, path = tempfile.mkstemp(prefix="pool-", suffix=".pickle")
    with os.fdopen(fd, "wb") as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
    return Pool(path, n, initializer=_load, initargs=(path, initializer))


def _load(path, initializer):
    import pickle
    with open(path, "rb") as f:
        payload = pickle.load(f)
    initializer(*payload)


class Pool(ProcessPoolExecutor):
    """pool()'s executor: it removes its payload's file when it shuts down."""

    def __init__(self, path, *a, **k):
        super().__init__(*a, **k)
        self.path = path

    def shutdown(self, *a, **k):
        super().shutdown(*a, **k)
        try:
            os.remove(self.path)
        except OSError:
            pass


if __name__ == "__main__":
    print(f"free {available_gb():.1f} GB, cores {os.cpu_count()}; headless pages {workers(4.0, 8)}, line builds {workers(2.5, 5)}")
