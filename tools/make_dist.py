"""Pack the playable static site into dist/tatra-t3-prague.zip (no build tools, caches or tests)."""
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DST = os.path.join(ROOT, "dist", "tatra-t3-prague.zip")
INCLUDE = ["index.html", "README.md", "src", "assets", "data"]

os.makedirs(os.path.dirname(DST), exist_ok=True)
n = 0
with zipfile.ZipFile(DST, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for item in INCLUDE:
        path = os.path.join(ROOT, item)
        if os.path.isfile(path):
            z.write(path, item); n += 1
            continue
        for base, _, files in os.walk(path):
            for f in files:
                full = os.path.join(base, f)
                z.write(full, os.path.relpath(full, ROOT).replace(os.sep, "/")); n += 1
print(f"{DST}: {n} files, {os.path.getsize(DST) / 1e6:.1f} MB")
