# SPDX-License-Identifier: AGPL-3.0-or-later
"""The borders between the bed's styles in the ground file, and how ragged they are (#676).

    python -P -E tools/bench/style_borders.py [--lines 9,17,22,23,37] [--json OUT] [--top N]

Reads data/lineN.ground.json and .bin (tools/ground_mesh.py decode). A style border is an edge between two bed
triangles drawn in different styles (panels against embedded, grass against panels, ...). Along the borders:
- **length**, m;
- **sharp turns:** border points where exactly two border edges meet and the border turns by more than TURN degrees.
  A straight border across a bed (where a style changes) or along a bed's edge turns by a few degrees at most; the
  saw-teeth of #676 (whole triangles taking one style or the other) turn at every tooth;
- **forks:** border points where three or more border edges meet (three styles, or one style's two borders meeting).
Prints a table per line and the CELL m squares with the most sharp turns (the places to look at).
"""
import argparse
import collections
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import ground_mesh  # noqa: E402

TURN = 45.0  # degrees
CELL = 20.0  # m: the squares the places are counted in


def borders(ln):
    lay = json.loads((ROOT / "data" / f"line{ln}.ground.json").read_text(encoding="utf-8"))
    V, F, D = ground_mesh.decode((ROOT / "data" / f"line{ln}.ground.bin").read_bytes(), lay, draw=True)
    tris, names = F.get("bed", np.zeros((0, 3), int)), D.get("bed")
    if names is None or not len(tris):
        return V, np.zeros((0, 2), int)
    # (vertices by their place only: a bed's triangles share a point's height, but a weld's step makes two vertices)
    _, place = np.unique(np.round(V[:, :2] * ground_mesh.Q).astype(np.int64), axis=0, return_inverse=True)
    place = place.ravel()
    t = place[tris]
    style_ids = {s: i for i, s in enumerate(sorted(set(names.tolist())))}
    sid = np.array([style_ids[s] for s in names.tolist()])
    e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    e.sort(1)
    es = np.concatenate([sid, sid, sid])
    key = e[:, 0].astype(np.int64) * (len(V) + 1) + e[:, 1]
    o = np.argsort(key, kind="stable")
    key, e, es = key[o], e[o], es[o]
    pair = np.flatnonzero(key[1:] == key[:-1])
    differ = pair[es[pair] != es[pair + 1]]
    # (a place's position: any of its vertices')
    pos = np.zeros((place.max() + 1, 2))
    pos[place] = V[:, :2]
    return pos, e[differ]


def measure(ln, top=10):
    pos, E = borders(ln)
    if not len(E):
        return {"line": ln, "border m": 0, "sharp turns": 0, "forks": 0, "places": []}
    length = float(np.hypot(*(pos[E[:, 0]] - pos[E[:, 1]]).T).sum())
    nb = collections.defaultdict(list)
    for a, b in E.tolist():
        nb[a].append(b)
        nb[b].append(a)
    sharp, forks = [], 0
    for v, ns in nb.items():
        if len(ns) >= 3:
            forks += 1
        elif len(ns) == 2:
            a, b = pos[ns[0]] - pos[v], pos[ns[1]] - pos[v]
            la, lb = math.hypot(*a), math.hypot(*b)
            if la < 1e-6 or lb < 1e-6:
                continue
            turn = 180 - math.degrees(math.acos(max(-1.0, min(1.0, float(a @ b) / (la * lb)))))
            if turn > TURN:
                sharp.append(pos[v])
    cells = collections.Counter((math.floor(x / CELL), math.floor(y / CELL)) for x, y in sharp)
    places = [{"at": [round((i + 0.5) * CELL), round((j + 0.5) * CELL)], "sharp turns": n} for (i, j), n in cells.most_common(top)]
    return {"line": ln, "border m": round(length), "sharp turns": len(sharp), "forks": forks, "places": places}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lines", default="9,17,22,23,37")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args()
    out = []
    print(f"{'line':>4} {'border m':>9} {'sharp turns':>11} {'per km':>7} {'forks':>6}")
    for ln in a.lines.split(","):
        r = measure(int(ln), a.top)
        out.append(r)
        per = r["sharp turns"] / (r["border m"] / 1000) if r["border m"] else 0
        print(f"{r['line']:>4} {r['border m']:>9} {r['sharp turns']:>11} {per:>7.0f} {r['forks']:>6}")
    for r in out:
        print(f"line {r['line']}: " + ", ".join(f"({p['at'][0]}, {p['at'][1]}) {p['sharp turns']}" for p in r["places"]))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
