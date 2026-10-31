"""Pack the playable static site into dist/tatra-t3-prague.zip (no build tools, caches or tests).
The same files are what tools/deploy.py uploads."""
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DST = os.path.join(ROOT, "dist", "tatra-t3-prague.zip")
INCLUDE = ["index.html", "README.md", "src", "assets", "data"]


def files(root=ROOT):
    """The site's files, as paths relative to the root with forward slashes."""
    for item in INCLUDE:
        path = os.path.join(root, item)
        if os.path.isfile(path):
            yield item
            continue
        for base, _, names in os.walk(path):
            for f in sorted(names):
                yield os.path.relpath(os.path.join(base, f), root).replace(os.sep, "/")


def main():
    os.makedirs(os.path.dirname(DST), exist_ok=True)
    n = 0
    with zipfile.ZipFile(DST, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel in files():
            z.write(os.path.join(ROOT, rel), rel)
            n += 1
    print(f"{DST}: {n} files, {os.path.getsize(DST) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
