# SPDX-License-Identifier: AGPL-3.0-or-later
"""The scatter of the street outlines' heights along straight kerbs, the survey's against IPR's lidar (#470).

    python -P -E tools/bench/street_scatter.py [--lines 9,17,22,23,37] [--dtm DIR] [--inset 1.0] [--json PATH]
    python -P -E tools/bench/street_scatter.py --lines 17 --plot X,Y [--ref DIR] [--out PNG]

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
Places: the survey's samples over 15 cm off their mean, the largest per 50 m square, by cause: `lidar too` (IPR at the
sample over 8 cm off its own mean: a shape both see), `face` (within 2 m of a face the survey drew: two vertices under
0.5 m apart, more than 8 cm apart in height), `no lidar` (IPR missing in the window), `survey alone` (the rest).

--plot X,Y draws the outline nearest the point (local frame), 30 m either side along it, to a PNG (default
reports/street_scatter/<line>_<x>_<y>.png): the survey's heights in this data, in --ref DIR's (main's copies) and IPR
1 m inside, with the vertices marked.
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
FACE, FACE_NEAR, PLACE = 0.5, 2.0, 50.0  # m
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
    places = {}
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
            dz = np.abs(np.roll(r[:, 2], -1) - r[:, 2])
            dxy = np.hypot(*(np.roll(r[:, :2], -1, axis=0) - r[:, :2]).T)
            faces = r[(dxy < FACE) & (dz > OVER), :2]
            zi = np.asarray(ipr.sample(p[:, 0] + nin[:, 0] * inset + F.E0, p[:, 1] + nin[:, 1] * inset + F.N0), float)
            z0 = np.asarray(ipr.sample(p[:, 0] + F.E0, p[:, 1] + F.N0), float)
            c = acc[a["c"]]
            rsv, rip = resid(p[:, 2]), resid(zi)
            for k in np.flatnonzero(ok & (np.abs(rsv) > FAR)):
                if np.isfinite(rip[k]) and abs(rip[k]) > OVER:
                    cause = "lidar too"
                elif not np.isfinite(rip[k]):
                    cause = "no lidar"
                elif len(faces) and np.hypot(*(faces - p[k, :2]).T).min() <= FACE_NEAR:
                    cause = "face"
                else:
                    cause = "survey alone"
                key = (a["c"], int(p[k, 0] // PLACE), int(p[k, 1] // PLACE))
                if abs(rsv[k]) > places.get(key, {}).get("mag", 0):
                    places[key] = {"c": a["c"], "x": round(float(p[k, 0]), 1), "y": round(float(p[k, 1]), 1),
                                   "mag": round(float(abs(rsv[k])), 2), "cause": cause}
            c["survey"].append(rsv[ok])
            c["ipr"].append(resid(zi)[ok])
            c["ipr0"].append(resid(z0)[ok])
            c["off"].append((p[:, 2] - zi)[ok])
            if len(rp):
                zr = near(grid, rp, p[:, 0], p[:, 1]) if ok.any() else np.full(len(p), np.nan)
                for k, z in (("rs", p[:, 2]), ("ri", zi)):
                    c[k].append(resid(z - zr)[ok])
    out = {}
    for cls, c in acc.items():
        row = {}  # (the per-class rows; "_places" below)
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
    pl = sorted(places.values(), key=lambda q: -q["mag"])
    for q in pl:
        q["lat"], q["lon"] = (round(float(v), 6) for v in F.ll(q["x"], q["y"]))
    causes = defaultdict(lambda: defaultdict(int))
    for q in pl:
        causes[q["c"]][q["cause"]] += 1
    out["_places"] = {"byClass": {c: dict(v) for c, v in causes.items()}, "list": pl}
    return out


def plot(ln, at, dtm_dir, ref_dir, ipr, path):
    """The outline nearest `at`, 30 m either side along it: this data's heights, the reference's, IPR 1 m inside."""
    import shapely
    from PIL import Image, ImageDraw

    def nearest(d):
        best = None
        for a in d["areas"]:
            if a["l"] != 0 or a["c"] not in STREETS:
                continue
            for ring in [a["r"]] + a.get("h", []):
                r = np.asarray([[q[0], q[1], np.nan if q[2] is None else q[2]] for q in ring], float)
                k = int(np.argmin(np.hypot(r[:, 0] - at[0], r[:, 1] - at[1])))
                dd = float(np.hypot(r[k, 0] - at[0], r[k, 1] - at[1]))
                if best is None or dd < best[0]:
                    best = (dd, a, r, k)
        return best

    def load(d):
        return json.load(open(os.path.join(d, f"line{ln}.dtm.json"), encoding="utf-8"))

    _, a, r, k = nearest(load(dtm_dir))
    rings = [np.asarray(a["r"], float)[:, :2]] + [np.asarray(h, float)[:, :2] for h in a.get("h", [])]
    poly = shapely.Polygon(rings[0], rings[1:]).buffer(0)
    seg = np.hypot(*np.diff(np.vstack([r, r[:1]])[:, :2], axis=0).T)
    d = np.r_[0, np.cumsum(seg)[:-1]]
    L = seg.sum()
    rel = (d - d[k] + L / 2) % L - L / 2
    order = np.argsort(rel)
    keep = order[np.abs(rel[order]) <= 30]
    series = [("this data", (200, 40, 40), rel[keep], r[keep, 2])]
    if ref_dir:
        rr = nearest(load(ref_dir))[2]
        rd = np.array([float(rel[np.argmin(np.hypot(*(r[:, :2] - q[:2]).T))])
                       if np.hypot(*(r[:, :2] - q[:2]).T).min() < 0.05 else np.nan for q in rr])
        m = np.isfinite(rd) & (np.abs(rd) <= 30)
        o = np.argsort(rd[m])
        series.insert(0, ("reference", (120, 120, 120), rd[m][o], rr[m][o, 2]))
    ts = np.arange(-30, 30.01, 0.5)  # (IPR 1 m inside, every 0.5 m along the outline)
    inn = []
    for t in ts:
        dd = (d[k] + t) % L
        j = int(np.searchsorted(d, dd, side="right") - 1)
        tv = (r[(j + 1) % len(r), :2] - r[j, :2]) / max(seg[j], 1e-9)
        q = r[j, :2] + tv * (dd - d[j])
        nv = np.array([-tv[1], tv[0]])
        inn.append(q + nv if poly.contains(shapely.Point(*(q + nv))) else q - nv)
    inn = np.asarray(inn)
    gi = np.asarray(ipr.sample(inn[:, 0] + F.E0, inn[:, 1] + F.N0), float)
    series.append(("IPR 1 m inside", (40, 110, 200), ts, gi))
    W, H, M = 960, 420, 50
    allz = np.concatenate([z[np.isfinite(z)] for *_, z in series])
    z0, z1 = float(allz.min()) - 0.1, float(allz.max()) + 0.1

    def X(t):
        return M + (t + 30) / 60 * (W - 2 * M)

    def Y(z):
        return H - M - (z - z0) / (z1 - z0) * (H - 2 * M)

    im = Image.new("RGB", (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(im)
    dr.rectangle([M, M, W - M, H - M], outline=(0, 0, 0))
    step = 0.1 if z1 - z0 < 1.5 else 0.5 if z1 - z0 < 6 else 2.0
    for z in np.arange(np.ceil(z0 / step) * step, z1, step):
        dr.line([M, Y(z), W - M, Y(z)], fill=(230, 230, 230))
        dr.text((4, Y(z) - 6), f"{z:.1f}", fill=(0, 0, 0))
    for t in range(-30, 31, 10):
        dr.text((X(t) - 8, H - M + 6), f"{t} m", fill=(0, 0, 0))
    for i, (name, col, t, z) in enumerate(series):
        m = np.isfinite(z)
        if m.sum() > 1:
            dr.line([(X(a_), Y(b_)) for a_, b_ in zip(t[m], z[m])], fill=col, width=2)
        if not name.startswith("IPR"):
            for a_, b_ in zip(t[m], z[m]):
                dr.ellipse([X(a_) - 3, Y(b_) - 3, X(a_) + 3, Y(b_) + 3], outline=col)
        dr.text((M + 10 + 170 * i, 10), name, fill=col)
    lat, lon = F.ll(r[k, 0], r[k, 1])
    dr.text((M + 10, 26), f"line {ln}, {a['c']} outline at ({r[k, 0]:.1f}, {r[k, 1]:.1f}), "
            f"{float(lat):.5f} N {float(lon):.5f} E; along the outline", fill=(0, 0, 0))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path)
    print("wrote", path)


def main():
    lines = arg("--lines", "9,17,22,23,37").split(",")
    dtm_dir = arg("--dtm", os.path.join(ROOT, "data"))
    inset = float(arg("--inset", "1.0"))
    ipr = IprDtm()
    if "--plot" in sys.argv:
        x, y = (float(v) for v in arg("--plot", "").split(","))
        out = arg("--out", os.path.join(ROOT, "reports", "street_scatter", f"{lines[0]}_{x:.0f}_{y:.0f}.png"))
        plot(lines[0], (x, y), dtm_dir, arg("--ref", None), ipr, out)
        return
    res = {}
    for ln in lines:
        res[ln] = r = run(ln, dtm_dir, inset, ipr)
        print(f"line {ln} (IPR {inset} m inside):")
        print("  class      km   survey >8/>15 %   ipr >8/>15 %   ipr0 >8/>15 %   survey-ipr p5/50/95 m"
              "   |res| vs rails p50/90/99: survey | ipr (n)")
        print("  places over 15 cm by cause:", r["_places"]["byClass"])
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
