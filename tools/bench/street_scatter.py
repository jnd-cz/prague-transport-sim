# SPDX-License-Identifier: AGPL-3.0-or-later
"""The scatter of the street outlines' heights along straight kerbs, the survey's against IPR's lidar (#470).

    python -P -E tools/bench/street_scatter.py [--lines 9,17,22,23,37] [--dtm DIR] [--inset 1.0] [--json PATH]

--dtm reads lineN.dtm.json from DIR instead of data/ (main's copies, to compare); --inset is how far inside the area
IPR is read (m).

Every level-0 outline of a street class (lint's STREETS) is cut into 1 m samples, its height linear between the
vertices as the page draws the edge. A sample counts where its outline is straight over +-10 m (the chord between the
samples 10 m either side at least 19.5 m). At each, three heights:
- survey: the outline's;
- ipr: IPR's 1 m raster at --inset m inside the area, square to the outline (the candidate of #470's rule);
- ipr0: IPR on the outline itself.
Scatter: each sample against the 21 m running mean along its outline (lint streetWaviness' statistic), the share over 8
and 15 cm, per class.
Offset: survey - ipr, its median and the 5th / 95th percentile, per class.
Rails (the independent heights): samples within RAIL m of a DI track point (`tracks[src=di]`, their `zs`), each source's
height less the rail's, with its 21 m running mean of that difference taken off: the noise left against a smooth
surveyed line, per class (the 50th / 90th / 99th percentile of its magnitude).
"""
import json
import os
import sys
from collections import defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from geo import Frame  # noqa: E402
from ipr_dtm import IprDtm  # noqa: E402

F = Frame()
STREETS = ("road", "tram", "parking", "sidewalk", "island", "cycle", "paved", "platform")
HALF, CHORD, OVER, FAR = 10, 19.5, 0.08, 0.15  # samples either side; m
RAIL = 4.0  # m: a sample this near a DI track point is compared with the rail


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def samples(ring):
    """(n, 3) points every 1 m round a closed ring (n, 3), and the inward unit normals (n, 2) for a ring whose inside is
    on its left (counter-clockwise)."""
    r = np.asarray(ring, float)
    r = np.vstack([r, r[:1]])
    seg = np.hypot(*np.diff(r[:, :2], axis=0).T)
    cum = np.r_[0, np.cumsum(seg)]
    L = cum[-1]
    if L < 2 * HALF + 2:
        return None, None
    s = np.arange(0, L, 1.0)
    k = np.clip(np.searchsorted(cum, s, side="right") - 1, 0, len(seg) - 1)
    u = np.where(seg[k] > 0, (s - cum[k]) / np.where(seg[k] > 0, seg[k], 1), 0)
    p = r[k] + (r[k + 1] - r[k]) * u[:, None]
    d = (r[k + 1] - r[k])[:, :2] / np.where(seg[k] > 0, seg[k], 1)[:, None]
    return p, np.column_stack([-d[:, 1], d[:, 0]])


def straight(p):
    """Samples whose outline runs straight over +-HALF m (a closed ring: indices wrap)."""
    n = len(p)
    i = np.arange(n)
    a, b = p[(i - HALF) % n, :2], p[(i + HALF) % n, :2]
    return np.hypot(*(b - a).T) >= CHORD


def resid(z):
    """Each sample less the 21 m running mean along its closed ring (NaN where a sample in the window is NaN)."""
    w = np.stack([np.roll(z, k) for k in range(-HALF, HALF + 1)])
    return z - w.mean(axis=0)


def rails(line):
    """DI's track points (n, 3), local frame."""
    pts = []
    for t in line.get("tracks", []):
        if t.get("src") != "di" or not t.get("zs"):
            continue
        for q, z in zip(t["p"], t["zs"]):
            if z is not None:
                pts.append((q[0], q[1], z))
    return np.array(pts, float).reshape(-1, 3)


def near(grid, pts, x, y):
    """The nearest rail point's height within RAIL m of each (x, y), NaN where none."""
    out = np.full(len(x), np.nan)
    best = np.full(len(x), RAIL)
    for i, (xx, yy) in enumerate(zip(x, y)):
        for cell in ((int(xx // RAIL) + a, int(yy // RAIL) + b) for a in (-1, 0, 1) for b in (-1, 0, 1)):
            for j in grid.get(cell, ()):
                d = np.hypot(pts[j, 0] - xx, pts[j, 1] - yy)
                if d < best[i]:
                    best[i], out[i] = d, pts[j, 2]
    return out


def pct(v, qs):
    v = v[np.isfinite(v)]
    return [round(float(x), 3) for x in np.percentile(v, qs)] if len(v) else None


def run(ln, dtm_dir, inset, ipr):
    dtm = json.load(open(os.path.join(dtm_dir, f"line{ln}.dtm.json"), encoding="utf-8"))
    line = json.load(open(os.path.join(ROOT, "data", f"line{ln}.json"), encoding="utf-8"))
    rp = rails(line)
    grid = defaultdict(list)
    for j, (x, y, _) in enumerate(rp):
        grid[(int(x // RAIL), int(y // RAIL))].append(j)
    acc = defaultdict(lambda: defaultdict(list))
    for a in dtm["areas"]:
        if a["l"] != 0 or a["c"] not in STREETS:
            continue
        rings = [(a["r"], True)] + [(h, False) for h in a.get("h", [])]
        for ring, outer in rings:
            if len(ring) < 3 or any(q[2] is None for q in ring):
                continue
            r = np.asarray(ring, float)
            ccw = np.sum(r[:, 0] * np.roll(r[:, 1], -1) - np.roll(r[:, 0], -1) * r[:, 1]) > 0
            p, nin = samples(ring)
            if p is None:
                continue
            if ccw != outer:
                nin = -nin
            ok = straight(p)
            zi = np.asarray(ipr.sample(p[:, 0] + nin[:, 0] * inset + F.E0, p[:, 1] + nin[:, 1] * inset + F.N0), float)
            z0 = np.asarray(ipr.sample(p[:, 0] + F.E0, p[:, 1] + F.N0), float)
            c = acc[a["c"]]
            c["survey"].append(resid(p[:, 2])[ok])
            c["ipr"].append(resid(zi)[ok])
            c["ipr0"].append(resid(z0)[ok])
            c["off"].append((p[:, 2] - zi)[ok])
            if len(rp):
                zr = near(grid, rp, p[:, 0], p[:, 1]) if ok.any() else np.full(len(p), np.nan)
                for k, z in (("rs", p[:, 2]), ("ri", zi)):
                    c[k].append(resid(z - zr)[ok])
    out = {}
    for cls, c in acc.items():
        row = {}
        cat = {k: np.concatenate(v) for k, v in c.items()}
        n = int(np.isfinite(cat["survey"]).sum())
        row["km"] = round(n / 1000, 1)
        for k in ("survey", "ipr", "ipr0"):
            v = np.abs(cat[k][np.isfinite(cat[k])])
            row[k] = {"over8": round(float((v > OVER).mean() * 100), 2) if len(v) else None,
                      "over15": round(float((v > FAR).mean() * 100), 2) if len(v) else None}
        s, i = np.abs(cat["survey"]), np.abs(cat["ipr"])
        both = np.isfinite(s) & np.isfinite(i)
        s, i = s[both], i[both]
        # (over FAR in one, under OVER in the other: that source's own; over FAR in both: a shape both see)
        row["split15"] = ({"both": round(float(((s > FAR) & (i > FAR)).mean() * 100), 2),
                           "surveyOnly": round(float(((s > FAR) & (i < OVER)).mean() * 100), 2),
                           "iprOnly": round(float(((i > FAR) & (s < OVER)).mean() * 100), 2)} if len(s) else None)
        row["offset"] = pct(cat["off"], [5, 50, 95])
        for k in ("rs", "ri"):
            if k in cat:
                v = np.abs(cat[k])
                row[k] = {"n": int(np.isfinite(v).sum()), "p": pct(v, [50, 90, 99])}
        out[cls] = row
    return out


def main():
    lines = arg("--lines", "9,17,22,23,37").split(",")
    dtm_dir = arg("--dtm", os.path.join(ROOT, "data"))
    inset = float(arg("--inset", "1.0"))
    ipr = IprDtm()
    res = {}
    for ln in lines:
        res[ln] = r = run(ln, dtm_dir, inset, ipr)
        print(f"line {ln} (IPR {inset} m inside):")
        print("  class      km   survey >8/>15 %   ipr >8/>15 %   ipr0 >8/>15 %   survey-ipr p5/50/95 m"
              "   |res| vs rails p50/90/99: survey | ipr (n)")
        for cls in STREETS:
            if cls not in r or r[cls]["survey"]["over8"] is None:
                continue
            x = r[cls]
            f = lambda k, x=x: "   -     " if x[k]["over8"] is None else f"{x[k]['over8']:5.1f}/{x[k]['over15']:4.1f}"  # noqa: E731
            rails_ = (f"{x['rs']['p']} | {x['ri']['p']} ({x['rs']['n']})" if x.get("rs", {}).get("p") else "-")
            sp = x["split15"] or {}
            print(f"  {cls:9s} {x['km']:6.1f}   {f('survey')}        {f('ipr')}      {f('ipr0')}       "
                  f"{x['offset']}   {rails_}   >15 both/survey/ipr {sp.get('both')}/{sp.get('surveyOnly')}/{sp.get('iprOnly')}")
    if "--json" in sys.argv:
        with open(arg("--json", ""), "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"inset": inset, "lines": res}, fh, indent=1)


if __name__ == "__main__":
    main()
