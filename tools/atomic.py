"""Writing a file whole: to a temporary name next to it, then renamed over it (#77).

    from atomic import replacing
    with replacing(dst, "w", encoding="utf-8") as fh:
        json.dump(out, fh)

Two reasons. A reader at the same time (tools/rebuild.py's parallel steps, the dev server) never sees
half a file. And a file in data/ or raw/ may be a hard link into the machine's store cache
(tools/snapshot.py, TRAMDATA_CACHE), protected against writing its data: opening it for writing fails,
while the rename replaces only this checkout's link and leaves the cached copy alone.
"""
import os
from contextlib import contextmanager


@contextmanager
def replacing(path, mode="w", **kw):
    tmp = f"{path}.{os.getpid()}.part"
    try:
        with open(tmp, mode, **kw) as fh:
            yield fh
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
