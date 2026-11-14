# SPDX-License-Identifier: AGPL-3.0-or-later
"""Paved track against IPR's ground, as built (#539).

    python -P -E tools/bench/paved_ipr.py [--lines 9,17,22,23,37] [--json OUT] [--top N]

Along each line's route (`path`, every heights.step), on paved track only (the styles' grass and ballast left out):
the track's surface (top of rail less the style's lift) against IPR's 1 m bare-earth DTM at the track's centre.
- **Runs:** where the surface lies more than UNDER under IPR for MIN_RUN m or more.
- **Left out:** our bridges (`spans`), tunnels, and samples more than DEEP under IPR, where IPR reads the ground above a
  structure (line 9 at Hlavní nádraží, line 17 under the Barrandov bridge); these are counted apart.
- **Causes:** each run gets one, by the medians over it:
  - held: the staged heights there (DI, the archive, the survey, a reviewed span: heights.staged; this track's, else the
    other track's within NEAR m; where neither is in the data but heightSource names a measurement, the built surface)
    are themselves more than UNDER under IPR. The source holds the track under IPR. Split
    by the survey's level-0 height at the track (data/lineN.dtm.json, an independent measurement):
    - held, survey with the source: the survey within UNDER of the staged surface: IPR is the one apart (its cell
      reads something else there: a crown, a kerb, a lower bed's higher sides);
    - held, survey with IPR: the survey within UNDER of IPR: the source is the one apart;
    - held, no survey: no survey there, or it agrees with neither;
  - radius: the staged heights within UNDER of IPR, the built curve more than FOLLOW under them: the vertical curve
    could not follow;
  - no source: no staged height within reach: the height is the curve's between sources further away;
  - other: none of these.
  IPR across the track (`trough`: the lower side's lowest cell at 3-6 m less the centre; negative where the track
  stands higher than its sides) and the survey's class at the centre are listed with each run.

Prints a table per line (paved km, metres under, p1 / p99 of surface - IPR, metres by cause) and the largest runs.
"""
import argparse
import json
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from scipy.spatial import cKDTree  # noqa: E402

from cross_level import sample_tris, survey_tris  # noqa: E402
from geo import Frame  # noqa: E402
from ipr_dtm import IprDtm  # noqa: E402
from placement import Survey  # noqa: E402

F = Frame()
UNDER = 0.10   # m: under IPR by more than this
MIN_RUN = 6.0  # m: for this long at least
DEEP = 2.0     # m: deeper than this under IPR, IPR reads the ground over a structure
FOLLOW = 0.05  # m: the built curve under the staged heights by more than this: it did not follow them
NEAR = 6.0     # m: the other track's staged heights count within this
MEASURED = {"di", "dtmp", "review", "zps"}  # (heightSource codes of a measured height, line_heights.LEVELS)
CAUSES = ("held, survey with the source", "held, survey with IPR", "held, no survey", "radius", "no source", "other")
NOT_PAVED = {"grass", "ballast"}
LINES = "9,17,22,23,37"


def along(path, step, n):
    """(x, y, hx, hy) every `step` m along the polyline `path`, n samples (the build's heights grid)."""
    p = np.asarray([q[:2] for q in path], float)
    seg = np.hypot(*np.diff(p, axis=0).T)
    cum = np.concatenate([[0], np.cumsum(seg)])
    s = np.arange(n) * step
    i = np.clip(np.searchsorted(cum, s, side="right") - 1, 0, len(seg) - 1)
    t = np.clip((s - cum[i]) / np.where(seg[i] > 0, seg[i], 1), 0, 1)
    d = (p[i + 1] - p[i]) / np.where(seg[i] > 0, seg[i], 1)[:, None]
    xy = p[i] + d * (t * seg[i])[:, None]
    return s, xy, d


def in_ranges(s, ranges):
    out = np.zeros(len(s), bool)
    for a, b in ranges:
        out |= (s >= a) & (s <= b)
    return out


def measure(line, ipr):
    """One line's numbers and runs (data/lineN.json, its survey data/lineN.dtm.json)."""
    d = json.load(open(os.path.join(ROOT, "data", f"line{line}.json"), encoding="utf-8"))
    dtm = os.path.join(ROOT, "data", f"line{line}.dtm.json")
    areas = json.load(open(dtm, encoding="utf-8"))["areas"] if os.path.exists(dtm) else []
    return measure_data(line, d, areas, ipr)


def measure_data(line, d, areas, ipr):
    """As measure, from a line's data and survey areas; `ipr` has sample(E, N) (S-JTSK)."""
    H = d["heights"]
    step, z = H["step"], np.asarray(H["path"], float)
    s, xy, dirs = along(d["path"], step, len(z))
    lift = np.zeros(len(z))
    if d.get("lift"):
        lv = np.asarray(d["lift"]["v"], float) * d["lift"].get("unit", 1)
        ls = np.arange(len(lv)) * d["lift"]["step"]
        lift = np.interp(s, ls, lv)
    surf = z - lift
    paved = ~in_ranges(s, [(x["s0"], x["s1"]) for x in d.get("styles", []) if x["style"] in NOT_PAVED])
    out_of = in_ranges(s, [tuple(b) for b in d.get("spans", [])] + [(t[0], t[1]) if isinstance(t, list) else (t["s0"], t["s1"])
                                                                    for t in d.get("tunnels", [])])
    E, N = F.to_jtsk(xy[:, 0], xy[:, 1])
    g = ipr.sample(E, N).astype(float)
    diff = surf - g
    deep = paved & ~out_of & (diff < -DEEP)
    use = paved & ~out_of & ~deep & np.isfinite(g)
    # IPR across the track: the centre against the higher of the two sides' lowest cells at 3-6 m (the street beside)
    nx, ny = -dirs[:, 1], dirs[:, 0]
    sides = []
    for sg in (-1, 1):
        cols = [ipr.sample(*F.to_jtsk(xy[:, 0] + sg * o * nx, xy[:, 1] + sg * o * ny)).astype(float) for o in (3, 4, 5, 6)]
        sides.append(np.nanmin(np.stack(cols), axis=0))
    trough = np.minimum(sides[0], sides[1]) - g   # (> 0: both sides higher than the centre)
    staged = np.asarray(H.get("staged", {}).get("path", []), float).reshape(-1, 2)
    # (the other track's staged heights by place: their surface (lift as this track's, paved: none) against IPR there)
    other = np.asarray(H.get("staged", {}).get("pathBack", []), float).reshape(-1, 2)
    if len(other) and d.get("pathBack"):
        _, bxy, _ = along(d["pathBack"], 1.0, int(max(other[:, 0].max(), 1)) + 2)
        oxy = bxy[np.clip(np.round(other[:, 0]).astype(int), 0, len(bxy) - 1)]
        o_ipr = ipr.sample(*F.to_jtsk(oxy[:, 0], oxy[:, 1])).astype(float)
        o_tree, o_surf = cKDTree(oxy), other[:, 1]
    else:
        o_tree = None
    src = [(a, b, c) for a, b, c in d.get("heightSource", {}).get("path", [])]
    survey_cls = Survey(areas) if areas else None

    def source_at(si):
        for a, b, c in src:
            if a <= si <= b:
                return c
        return None

    under = use & (diff < -UNDER)
    runs = []
    i = 0
    while i < len(s):
        if not under[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(s) and under[j + 1]:
            j += 1
        if (j - i + 1) * step >= MIN_RUN:
            k = slice(i, j + 1)
            st = staged[(staged[:, 0] >= s[i] - step) & (staged[:, 0] <= s[j] + step)] if len(staged) else np.zeros((0, 2))
            whose = "this track"
            if len(st):
                gi = np.interp(st[:, 0], s, g)
                zi = np.interp(st[:, 0], s, surf)
                st_surf = st[:, 1] - np.interp(st[:, 0], s, lift)
                src_under = float(np.median(st_surf - gi))   # (the staged surface - IPR)
                not_followed = float(np.median(st_surf - zi))  # (staged - built)
            else:
                src_under = not_followed = math.nan
                if o_tree is not None:
                    near = sorted({q for qs in o_tree.query_ball_point(xy[k], NEAR) for q in qs})
                    if near:
                        whose = "the other track"
                        src_under = float(np.median(o_surf[near] - o_ipr[near]))
            sources = sorted({source_at(v) for v in s[k]} - {None})
            if not np.isfinite(src_under) and set(sources) & MEASURED:
                # (heights.staged keeps only the bins within 0.3 m of the route (line_heights.staged_along): line 22's
                # west end has the archive's chain farther off. The built surface stands for it: elsewhere it follows
                # its source within FOLLOW)
                whose, src_under = "not in the data: the built surface", float(np.median(diff[k]))
            # (the survey's level-0 height at the track, against the staged surface and IPR)
            tris = survey_tris(areas, near=xy[k][::3], r=3.0) if areas else np.zeros((0, 3, 3))
            zs = sample_tris(tris, xy[k, 0], xy[k, 1]) if len(tris) else np.full(j - i + 1, np.nan)
            sv = float(np.nanmedian(zs - g[k])) if np.isfinite(zs).any() else math.nan     # (survey - IPR)
            sv_src = sv - src_under if np.isfinite(sv) and np.isfinite(src_under) else math.nan  # (survey - staged)
            tr = float(np.nanmedian(trough[k]))
            if np.isfinite(src_under) and src_under < -UNDER:
                if np.isfinite(sv_src) and abs(sv_src) <= UNDER:
                    cause = CAUSES[0]
                elif np.isfinite(sv) and abs(sv) <= UNDER:
                    cause = CAUSES[1]
                else:
                    cause = CAUSES[2]
            elif np.isfinite(not_followed) and not_followed > FOLLOW:
                cause = "radius"
            elif not np.isfinite(src_under):
                cause = "no source"
            else:
                cause = "other"
            m = i + int(np.argmin(diff[k]))
            runs.append({"line": line, "s0": float(s[i]), "s1": float(s[j]), "m": float((j - i + 1) * step),
                         "worst": round(float(diff[m]), 3), "at": [round(float(xy[m, 0]), 1), round(float(xy[m, 1]), 1)],
                         "cause": cause, "staged": whose, "staged_minus_ipr": round(src_under, 3),
                         "staged_minus_built": round(not_followed, 3), "survey_minus_ipr": round(sv, 3),
                         "survey_class": survey_cls.class_at(*xy[m]) if survey_cls else None,
                         "trough": round(tr, 3), "staged_n": int(len(st)), "sources": sources})
        i = j + 1
    v = diff[use]
    by = {}
    for r in runs:
        by[r["cause"]] = by.get(r["cause"], 0) + r["m"]
    return {"line": line, "paved_km": round(float(paved.sum() * step) / 1000, 1), "under_m": round(sum(r["m"] for r in runs)),
            "p1": round(float(np.percentile(v, 1)), 2), "p99": round(float(np.percentile(v, 99)), 2),
            "deep_m": round(float(deep.sum() * step)), "by_cause": {k: round(m) for k, m in sorted(by.items())}, "runs": runs}


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    a.add_argument("--lines", default=LINES)
    a.add_argument("--json")
    a.add_argument("--top", type=int, default=5)
    a = a.parse_args(argv)
    ipr = IprDtm()
    res = [measure(n, ipr) for n in a.lines.split(",")]
    causes = CAUSES
    print("| line | paved km | under by >10 cm | p1 / p99 of surface - IPR | " + " | ".join(causes) + " | left out (>2 m under) |")
    print("|---|---|---|---|" + "---|" * len(causes) + "---|")
    for r in res:
        print(f"| {r['line']} | {r['paved_km']} | {r['under_m']} m | {r['p1']:+.2f} / {r['p99']:+.2f} m | "
              + " | ".join(f"{r['by_cause'].get(c, 0)} m" for c in causes) + f" | {r['deep_m']} m |")
    for r in res:
        print(f"\nline {r['line']}, the largest:")
        for x in sorted(r["runs"], key=lambda x: x["worst"] * x["m"])[:a.top]:
            print(f"  s {x['s0']:.0f}-{x['s1']:.0f} ({x['m']:.0f} m) at ({x['at'][0]:.0f}, {x['at'][1]:.0f}): {x['worst']:+.2f} m, {x['cause']}"
                  f" (staged ({x['staged']}) - IPR {x['staged_minus_ipr']:+.2f}, staged - built {x['staged_minus_built']:+.2f},"
                  f" survey ({x['survey_class']}) - IPR {x['survey_minus_ipr']:+.2f}, trough {x['trough']:+.2f}, {'/'.join(x['sources'])})")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
