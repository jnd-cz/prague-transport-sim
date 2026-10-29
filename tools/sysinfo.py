"""How many things to run at once: by cores and by free memory (the parallel tools cap themselves by it).

    from sysinfo import workers
    n = workers(gb_each=2.0, most=4)   # e.g. headless pages (~2 GB for line 17)
"""
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


if __name__ == "__main__":
    print(f"free {available_gb():.1f} GB, cores {os.cpu_count()}; headless pages {workers(2.0)}, line builds {workers(1.5, 5)}")
