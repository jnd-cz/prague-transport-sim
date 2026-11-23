# SPDX-License-Identifier: AGPL-3.0-or-later
"""The page's ground reads on the ground file, for the build (#682): what Start places stands where the page stood it.

    python -P -E tools/ground_at.py --lines 37            # the rule beside the track, measured on the file (below)

The page answers (src/terrain.js makeGround, src/main.js useGroundLookup, src/world.js trackAt):
- `at(x, y, deck)`: on a track's bed off the survey, that bed (+ BED_BELOW - ROAD_BELOW: the level the OSM roads meet the
  rails at); on a span of our route the deck (`deck`, within 22 m) or the survey or the ground under it; within 4 m of the
  route the track's profile less its lift and ROAD_BELOW; the survey; within 9 m a blend from the profile to the
  ground; the ground (the file's highest triangle; past its tiles the line's terrain grid).
- `surface(x, y)`: the survey's height, else at + 0.12 (an OSM road ribbon's top).
- `track_at(x, y)`: the nearest drawn track's own height within TRACK_REACH, else the profile within 6 m of the route,
  else at(x, y, deck).
- `way_ends()`: each bridge's and road tunnel's chain (src/terrain.js chainWays) with the heights at its two ends, as
  ground.way reads them: a tunnel's portal the lowest ground within 12 m out of its mouth, a bridge's abutment the ground
  there.
- `mouths()`: the road tunnels' mouths (src/structures.js roadPortalMouths, src/world.js), each with the tunnel road's
  height inward of it: the ground file lowers the survey's streets in them (tools/ground_mesh.py fit_mouths).

The measure (main): within 9 m of the route, every 2 m along it and every 0.5 m across, `at` against the file's own
height (the bed or the survey or the ground there, the rule beside the track left out): how many points differ by over
1 cm and by how much, per band and per what the file has there.
"""
import argparse
import json
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from bed_surface import BED_BELOW, Beds, RouteNear, densify, poly_len, resample  # noqa: E402
import network  # noqa: E402

ROAD_BELOW = 0.012 + 0.12  # m: the ground under an OSM road ribbon next to the track (src/heights.js)
TRACK_ZONE = 1.4  # m past each track's centre the tilt carries (src/terrain.js)
TRACK_REACH = 6  # m from a drawn track within which track_at is its own height (src/world.js)
F32 = np.float32


def js_round(v):
    return math.floor(v + 0.5)


class Profile:
    """src/terrain.js Profile: the built top of rail every 2 m along the route (32-bit, as the page keeps it), across the
    street to the opposite track, the rails' lift and the route's spans."""

    def __init__(self, L, R):
        self.R = R
        step = self.step = 2
        n = self.n = math.ceil(R.rt.length / step) + 1
        h = L["heights"]
        z = resample(h["path"], h["step"], n, step).astype(F32)
        self.bridges = [tuple(b) for b in (L.get("spans") or [])]
        self.tunnels = [tuple(t) for t in (L.get("tunnels") or [])]
        self.back_off = self.back_dz = self.tilt = None
        if h.get("backOff"):
            off = resample(h["backOff"], h["step"], n, step).astype(F32)
            zb = resample(h["backZ"], h["step"], n, step).astype(F32)
            ok = ~np.isnan(off) & ~np.isnan(zb)
            fade, dz = 10, np.zeros(n, F32)
            i = 0
            while i < n:
                if not ok[i]:
                    i += 1
                    continue
                j = i
                while j + 1 < n and ok[j + 1]:
                    j += 1
                for k in range(i, j + 1):
                    dz[k] = (float(zb[k]) - float(z[k])) * min(1, (k - i) * step / fade, (j - k) * step / fade)
                i = j + 1
            self.back_off, self.back_dz = off, dz
            C = L.get("crossLevel")
            if C and C.get("path"):
                t = np.zeros(n, F32)
                for i in range(n):
                    k = js_round(i * step / C["step"])
                    t[i] = C["path"][k] * C["unit"] / 1.5 if k < len(C["path"]) else 0
                self.tilt = t
        self.z = z

    def _interp(self, arr, s):
        f = max(0.0, min(self.n - 1.001, s / self.step))
        i = int(math.floor(f))
        t = f - i
        return float(arr[i]) * (1 - t) + float(arr[i + 1]) * t

    def height(self, s):
        return self._interp(self.z, s)

    def _off(self, s):
        return float(self.back_off[max(0, min(self.n - 1, js_round(s / self.step)))])

    def height_at(self, s, lateral=0.0):
        z = self._interp(self.z, s)
        if self.back_off is None or not lateral:
            return z
        o = self._off(s)
        if not abs(o) > 0.5:
            return z
        dz, u = self._interp(self.back_dz, s), lateral / o
        t = self._interp(self.tilt, s) if self.tilt is not None else 0.0
        past = lateral if u < 0 else lateral - o if u > 1 else 0.0
        beyond = -t * math.copysign(1, past) * min(abs(past), TRACK_ZONE) if t and past else 0.0
        return z + dz * max(0.0, min(1.0, u)) + beyond

    def lift(self, s, lateral=0.0):
        return self.R.lift(s, lateral)

    def on_bridge(self, s):
        return any(a - 4 < s < b + 4 for a, b in self.bridges)


class Ground:
    """The page's ground reads (module docstring) on line `ln`'s ground file, or on `file` = (layout, blob) in memory."""

    def __init__(self, ln, L=None, file=None, survey=None):
        """`L`: the line as the page loads it (network.load_line: the tram streets widened); `survey`: the file's reader
        (network.Survey) when the caller has one."""
        if L is None:
            L = network.load_line(ln)
        self.ln, self.L = ln, L
        self.R = RouteNear(L)
        self.rt = self.R.rt
        self.profile = Profile(L, self.R)
        self.sv = survey or network.Survey(ln, L.get("terrain"), file=file)
        self._own = None

    # ---- the route
    def near(self, x, y):
        """src/terrain.js makeGround near: (s, d, l: left > 0) of the nearest route point, or None."""
        n = self.R.nearest(x, y)
        if n is None:
            return None
        px, py, hx, hy = self.rt.at(n[1])
        s = max(0.0, min(self.rt.length, n[1] + (x - px) * hx + (y - py) * hy))
        qx, qy, qhx, qhy = self.rt.at(s)
        return s, math.hypot(x - qx, y - qy), (y - qy) * qhx - (x - qx) * qhy

    def _under(self, n):
        s, _, l = n
        return self.profile.height_at(s, l) - self.profile.lift(s, l) - ROAD_BELOW

    # ---- the file
    def file_at(self, xs, ys):
        """Per point: (the survey's height or None, the ground's height (the grid's past the file), a bed off the survey's
        height or None): dtm.heightAt, terrain.height and lookup.bedOffSurvey as the page answers them."""
        xs, ys = np.asarray(xs, float), np.asarray(ys, float)
        cid, z, kk = self.sv.hit(xs, ys)
        bed = self.sv.kinds.index("bed") if "bed" in self.sv.kinds else -2
        off = np.isnan(z)
        zg = z.copy()
        if off.any() and self.sv.grid:
            zg[off] = self.sv.grid.height(xs[off], ys[off])
        out = []
        for i in range(len(xs)):
            zs = float(z[i]) if cid[i] > 0 else None
            zb = float(z[i]) if kk[i] == bed and cid[i] == 0 else None
            out.append((zs, float(zg[i]), zb))
        return out

    # ---- the page's reads
    def at_many(self, xs, ys, deck=False):
        out = []
        for x, y, (zs, zg, zb) in zip(xs, ys, self.file_at(xs, ys)):
            out.append(self._at(x, y, zs, zg, zb, deck))
        return out

    def _at(self, x, y, zs, zg, zb, deck=False):
        if not deck and zb is not None:
            return zb + BED_BELOW - ROAD_BELOW
        n = self.near(x, y)
        if n and self.profile.on_bridge(n[0]):
            if deck and n[1] < 22:
                return self._under(n)
            return zs if zs is not None else zg
        if n and n[1] < 4:
            return self._under(n)
        if zs is not None:
            return zs
        if n and n[1] < 9:
            k = (n[1] - 4) / 5
            return self._under(n) * (1 - k) + zg * k
        return zg

    def at(self, x, y, deck=False):
        return self.at_many([x], [y], deck)[0]

    def surface_many(self, xs, ys):
        """ground.surface: the survey's height, else at + 0.12."""
        out = []
        for x, y, (zs, zg, zb) in zip(xs, ys, self.file_at(xs, ys)):
            out.append(zs if zs is not None else self._at(x, y, zs, zg, zb) + 0.12)
        return out

    def surface(self, x, y):
        return self.surface_many([x], [y])[0]

    def _own_tracks(self):
        """The drawn tracks' segments with their own heights at the ends (src/world.js: ownHeights on densify(t.p, 1.5))."""
        if self._own is None:
            A, B, ZA, ZB = [], [], [], []
            step = self.L["heights"]["step"]
            for t in self.L.get("tracks") or []:
                sm = densify(t["p"])
                if len(sm) < 2:
                    continue
                z = Beds._own_heights(t, sm, step) if t.get("zs") else np.zeros(len(sm))
                A.append(sm[:-1])
                B.append(sm[1:])
                ZA.append(z[:-1])
                ZB.append(z[1:])
            self._own = tuple(np.concatenate(v) if v else np.zeros((0, 2) if k < 2 else 0) for k, v in enumerate((A, B, ZA, ZB)))
        return self._own

    def track_at(self, x, y):
        """ground.trackAt once the world is built: the nearest drawn track's own height within TRACK_REACH (the first of
        the nearest), else the profile within 6 m of the route, else the ground or the deck."""
        A, B, ZA, ZB = self._own_tracks()
        if len(A):
            d = B - A
            l2 = (d * d).sum(1)
            l2[l2 == 0] = 1e-9
            t = np.clip(((x - A[:, 0]) * d[:, 0] + (y - A[:, 1]) * d[:, 1]) / l2, 0, 1)
            q = (A[:, 0] + d[:, 0] * t - x) ** 2 + (A[:, 1] + d[:, 1] * t - y) ** 2
            k = int(np.argmin(q))
            if q[k] < TRACK_REACH * TRACK_REACH:
                return float(ZA[k] + (ZB[k] - ZA[k]) * t[k])
        n = self.near(x, y)
        if n and n[1] < 6:
            return self.profile.height_at(n[0], n[2])
        return self.at(x, y, True)

    # ---- the bridges' and road tunnels' ways
    def chains(self):
        """src/terrain.js chainTunnels: every road tunnel's and bridge's chain of ways, as [(the line, (open at its
        start, at its end), its ways' indexes in data.roads, its flag)], the tunnels' first."""
        if not hasattr(self, "_chains"):
            roads = self.L.get("roads") or []
            self._chains = [c + (flag,) for flag in ("t", "b") for c in chain_ways(roads, flag)]
            self.way_of = {}
            for k, c in enumerate(self._chains):
                for r in c[2]:
                    self.way_of[r] = k  # (a way both bridge and tunnel: the bridges' chain, set last as the page's r.way)
        return self._chains

    def way_ends(self):
        """{data.roads index: (the height at its chain's start, at its end)} as src/terrain.js settleWays leaves them: each
        chain's ends read once, by the rule of the first of its ways in data.roads order (a tunnel: its portals; a
        bridge: its abutments)."""
        self.chains()
        roads = self.L.get("roads") or []
        ends, out = {}, {}
        for k, r in enumerate(roads):
            if not (r.get("b") or r.get("t")) or len(r["p"]) <= 1:
                continue
            c = self.way_of.get(k)
            if c is None:
                continue
            if c not in ends:
                line, opened = self._chains[c][0], self._chains[c][1]
                ends[c] = self.tunnel_ends(line, opened) if r.get("t") else self.bridge_ends(line, opened)
            out[k] = ends[c]
        return out

    def tunnel_ends(self, line, opened):
        """ground.way's tunnel: a portal is the lowest ground within 12 m out of the mouth; an end cut off by the edge of
        the imported roads 8 m under the ground there."""
        def portal(p, q):
            dx, dy = p[0] - q[0], p[1] - q[1]
            ln = math.hypot(dx, dy) or 1
            pts = [(p[0] + (dx / ln) * d, p[1] + (dy / ln) * d) for d in range(0, 13, 3)]
            return min(self.at_many([a for a, _ in pts], [b for _, b in pts]))
        oa, ob = opened
        ha = portal(line[0], line[1]) if oa else self.at(line[0][0], line[0][1]) - 8
        hb = portal(line[-1], line[-2]) if ob else self.at(line[-1][0], line[-1][1]) - 8
        return ha, hb

    def bridge_ends(self, line, opened):
        """ground.way's bridge: the ground at its abutments; a cut-off end takes the other's (both: the higher)."""
        a, b = line[0], line[-1]
        ha, hb = self.at_many([a[0], b[0]], [a[1], b[1]])
        oa, ob = opened
        if not oa and ob:
            ha = hb
        elif oa and not ob:
            hb = ha
        elif not oa and not ob:
            ha = hb = max(ha, hb)
        return ha, hb

    # ---- the road tunnels' mouths
    def rock(self):
        """src/terrain.js rockTunnels: our route's tunnels through rock, the terrain grid more than 8 m over the track
        on average."""
        out = []
        g = self.sv.grid
        for a, b in self.profile.tunnels:
            acc, n, s = 0.0, 0, a
            while s <= b:
                x, y = self.rt.at(s)[:2]
                acc += float(g.height(np.array([x]), np.array([y]))[0]) - self.profile.height(s)
                n += 1
                s += 4
            if n and acc / n > 8:
                out.append((a, b))
        return out

    def mouths(self):
        """src/world.js and src/structures.js roadPortalMouths: the road tunnels below ground (not in our rock tunnel, a
        long one, a car road) with a mouth at each end that is a portal: per mouth its point, its unit inward (hx, hy) and
        across (nx, ny), its half width w, its depth D and zAt(d), the tunnel road's height d m inward."""
        roads = self.L.get("roads") or []
        self.chains()
        rock = self.rock()
        tun_w = 8.5

        def in_tunnel(x, y, pad):
            if not rock:
                return False
            n = self.R.nearest(x, y)
            return bool(n) and n[0] < tun_w + pad and any(a - 0.5 < n[1] < b + 0.5 for a, b in rock)
        portals = []
        for k, r in enumerate(roads):
            if not r.get("t") or r.get("z"):
                continue
            c = self._chains[self.way_of[k]] if k in self.way_of else None
            line = c[0] if c else r["p"]
            L = poly_len(line)
            inside = [p for p in densify(r["p"], 3) if in_tunnel(p[0], p[1], 2)]
            if len(inside) > 1 or L < 60:
                continue
            if r.get("c"):
                portals.append((k, r, c, L))
        ends = {}
        for _, r, _, _ in portals:
            for p in (r["p"][0], r["p"][-1]):
                ends[(p[0], p[1])] = ends.get((p[0], p[1]), 0) + 1
        out = []
        for k, r, c, L in portals:
            D = min(24, L / 2)
            line, opened = (c[0], c[1]) if c else (r["p"], (True, True))
            tf = self.tunnel_height(line, opened)
            for end in (0, 1):
                i, j = (len(r["p"]) - 1, len(r["p"]) - 2) if end else (0, 1)
                p = r["p"][i]
                if ends[(p[0], p[1])] > 1:
                    continue
                at0 = 0 if tuple(line[0][:2]) == (p[0], p[1]) else 1 if tuple(line[-1][:2]) == (p[0], p[1]) else -1
                if at0 < 0 or not opened[at0]:
                    continue
                dx, dy = r["p"][j][0] - p[0], r["p"][j][1] - p[1]
                ln = math.hypot(dx, dy) or 1
                hx, hy = dx / ln, dy / ln
                out.append({"road": k, "p": (p[0], p[1]), "hx": hx, "hy": hy, "nx": -hy, "ny": hx, "w": r["w"] / 2 + 0.8,
                            "D": D, "tf": tf})
        for m in out:
            m["zAt"] = z_inward(m)
        return out

    def tunnel_height(self, line, opened):
        """ground.way's tunnel road: graded along its chain between the heights at its ends."""
        ha, hb = self.tunnel_ends(line, opened)
        P = np.asarray(line, float)[:, :2]
        acc = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(P, axis=0).T))])
        L = acc[-1] or 1

        def f(x, y):
            best, s = math.inf, 0.0
            for i in range(1, len(P)):
                a, b = P[i - 1], P[i]
                ex, ey = b[0] - a[0], b[1] - a[1]
                l2 = ex * ex + ey * ey or 1e-9
                t = max(0.0, min(1.0, ((x - a[0]) * ex + (y - a[1]) * ey) / l2))
                d = (a[0] + ex * t - x) ** 2 + (a[1] + ey * t - y) ** 2
                if d < best:
                    best, s = d, acc[i - 1] + (acc[i] - acc[i - 1]) * t
            return ha + (hb - ha) * s / L
        return f


def z_inward(m):
    """A mouth's zAt(d): the tunnel road's height d m inward (at the mouth for d < 0)."""
    return lambda d: m["tf"](m["p"][0] + m["hx"] * max(0.0, d), m["p"][1] + m["hy"] * max(0.0, d))


def chain_ways(roads, flag):
    """src/terrain.js chainWays: each run of `flag` ways (a road tunnel: 't', a bridge: 'b') joined end to end while
    exactly one more continues; an end is open (a portal, an abutment) where an ordinary road comes within 4.5 m.
    Returns [(the line, (open at its start, at its end), its ways' indexes)]."""
    tun = [k for k, r in enumerate(roads) if r.get(flag) and len(r["p"]) > 1]
    at = {}
    for k in tun:
        p = roads[k]["p"]
        for q in (p[0], p[-1]):
            at.setdefault((q[0], q[1]), []).append(k)
    others = [np.asarray(r["p"], float)[:, :2] for r in roads if not r.get(flag) and len(r["p"]) > 1]
    pts = np.vstack(others) if others else np.zeros((0, 2))

    def road_end(p):
        d = np.abs(pts - (p[0], p[1]))
        m = (d[:, 0] < 4.5) & (d[:, 1] < 4.5)
        return bool(m.any() and (np.hypot(d[m, 0], d[m, 1]) < 4.5).any())

    done, out = set(), []
    for k0 in tun:
        if k0 in done:
            continue
        line, members = list(roads[k0]["p"]), [k0]
        done.add(k0)
        grew = True
        while grew:
            grew = False
            for front in (False, True):
                p = line[0] if front else line[-1]
                nxt = [k for k in at.get((p[0], p[1]), ()) if k not in done]
                if len(nxt) != 1:
                    continue
                k = nxt[0]
                rp = roads[k]["p"]
                seq = rp if (rp[0][0], rp[0][1]) == (p[0], p[1]) else rp[::-1]
                line = [*seq[::-1], *line[1:]] if front else [*line, *seq[1:]]
                members.append(k)
                done.add(k)
                grew = True
        out.append((line, (road_end(line[0]), road_end(line[-1])), members))
    return out


# ---------------------------------------------------------------- the rule beside the track, measured
def beside(ln, log=print):
    """`at` against the file's own height within 9 m of the route (module docstring): per band (0-4 m, 4-9 m) and per
    what the file has there (a bed off the survey, the survey, the ground), the points, those over 1 cm apart, p99 and
    the largest |difference| with its place."""
    g = Ground(ln)
    xs, ys, ds = [], [], []
    s = 0.0
    while s <= g.rt.length:
        x, y, hx, hy = g.rt.at(s)
        for o in np.arange(-9, 9.01, 0.5):
            xs.append(x - hy * o)
            ys.append(y + hx * o)
            ds.append(abs(o))
        s += 2
    rows = {}
    for x, y, dd, (zs, zg, zb) in zip(xs, ys, ds, g.file_at(xs, ys)):
        z = g._at(x, y, zs, zg, zb)
        n = g.near(x, y)
        if n is None:
            continue
        own = zb + BED_BELOW - ROAD_BELOW if zb is not None else zs if zs is not None else zg
        kind = "bed" if zb is not None else "survey" if zs is not None else "ground"
        band = "bridge" if g.profile.on_bridge(n[0]) else "0-4 m" if n[1] < 4 else "4-9 m" if n[1] < 9 else "9 m+"
        rows.setdefault((band, kind), []).append((abs(z - own), round(n[0]), round(n[2], 1), round(x, 1), round(y, 1)))
    out = {}
    for (band, kind), v in sorted(rows.items()):
        d = np.array([r[0] for r in v])
        w = max(v)
        out[f"{band} {kind}"] = {"points": len(v), "over 1 cm": int((d > 0.01).sum()), "p99 cm": round(float(np.percentile(d, 99)) * 100, 1),
                                 "max cm": round(w[0] * 100, 1), "at (s, l, x, y)": list(w[1:])}
        log(f"line {ln} {band:7s} {kind:6s}: {len(v):6d} points, {(d > 0.01).sum():6d} over 1 cm, p99 "
            f"{np.percentile(d, 99) * 100:6.1f} cm, max {w[0] * 100:6.1f} cm at s {w[1]} l {w[2]}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lines", default="9,17,22,23,37")
    ap.add_argument("--out", help="the measure as JSON")
    a = ap.parse_args(argv)
    res = {ln: beside(ln) for ln in a.lines.split(",")}
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
