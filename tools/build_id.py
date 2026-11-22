# SPDX-License-Identifier: AGPL-3.0-or-later
"""One build ID in every file of a line (#702): data/lineN.json's CRC-32 as its last step wrote it, stamped into the
provenance (`build`) of the line's other files the page loads, as the last step of tools/rebuild.py's chain.

    python -P -E tools/build_id.py --line 37     # stamp them (tools/rebuild.py runs it last for each line)
    python -I tools/build_id.py --check 37        # which files carry the line file's ID; exit 1 when one does not

The line file carries none of its own: its CRC-32 is the ID, and the page computes it (src/buildId.js). A tool that
rewrites it (cant, placement and others load it, change it and write it back) so makes every other file's ID another.
A tool that writes one of the others stamps its provenance afresh (tools/sources.py stamp keeps only the lists, the
sources and the facts), so the ID goes with it: a network file built by hand after a rebuild carries none. The page
refuses a set in which a file carries another ID or none, and names the command that rebuilds it (MESSAGE); a set in
which no file carries one was built before #702 and loads with a note in the console.

The network points into the line file's arrays by index (data.signals, data.platforms, data.roads, tools/network.py),
and the ground and the network were built by hand after a rebuild until #702: a set of two builds loaded and bound the
signals to the wrong lanes. In tools/rebuild.py the steps before this one put their files back unstamped (the step
cache keeps each step's own output) and this one stamps them again.
"""
import argparse
import json
import os
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

# the line's files the page loads besides data/lineN.json (src/main.js `built`; test_build_id holds the two to each other)
FILES = ("geo.json", "dtm.json", "signals.json", "dtmpoints.json", "network.json", "ground.json")
MESSAGE = "python -P -E tools/rebuild.py {line}"  # (the command the page names, src/buildId.js)


def line_id(ln, root=ROOT):
    """The line's build ID: data/lineN.json's CRC-32, 8 hex digits."""
    with open(os.path.join(root, "data", f"line{ln}.json"), "rb") as f:
        return f"{zlib.crc32(f.read()):08x}"


def ids(ln, root=ROOT):
    """{file: the build ID its provenance carries, None for none} of the line's FILES that are there."""
    out = {}
    for name in FILES:
        p = os.path.join(root, "data", f"line{ln}.{name}")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                out[f"line{ln}.{name}"] = (json.load(f).get("provenance") or {}).get("build")
    return out


def stamp(ln, root=ROOT):
    """The line file's ID into every one of FILES that is there, each written whole (also one that carries it: the
    step's outputs are then the same files whatever was there). Returns (the ID, the files stamped)."""
    from atomic import replacing
    want, done = line_id(ln, root), []
    for name in FILES:
        p = os.path.join(root, "data", f"line{ln}.{name}")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        d.setdefault("provenance", {})["build"] = want
        with replacing(p, "w", encoding="utf-8") as f:
            json.dump(d, f, separators=(",", ":"), ensure_ascii=False)
        done.append(f"line{ln}.{name}")
    return want, done


def check(ln, root=ROOT):
    """(the line's ID, {file: its ID} of those that carry another or none)."""
    want = line_id(ln, root)
    return want, {f: v for f, v in ids(ln, root).items() if v != want}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", help="stamp this line's files")
    ap.add_argument("--check", metavar="LINE", help="which of the line's files carry its ID")
    a = ap.parse_args(argv)
    if a.check:
        want, off = check(a.check)
        print(f"line {a.check}: build {want}")
        for f, v in ids(a.check).items():
            print(f"  {f:28s} {v or 'none'}{'' if v == want else '  (another build: ' + MESSAGE.format(line=a.check) + ')'}")
        return 1 if off else 0
    if not a.line:
        ap.error("--line or --check")
    want, done = stamp(a.line)
    print(f"line {a.line}: build {want} in {', '.join(done) or 'no file'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
