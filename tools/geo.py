"""The one coordinate conversion of the world (docs/decisions/2026-10-29-city-frame-and-tiles.md, #7).
Every tool imports it.

Game metres: S-JTSK / Krovak East North (EPSG:5514) minus one city origin, the Marian column on
Staroměstské náměstí: x east, y north; heights Bpv. Lat/lon (OSM, GTFS; taken as ETRS89) converts
through ČÚZK's correction grid (35 mm) as a pinned PROJ pipeline, never PROJ's own choice of operation
(those differ by up to 10 m and depend on what is installed). The grid file is a snapshot input:
raw/proj/cz_cuzk_table_-y-x_3_v1710.tif.

    from geo import Frame
    f = Frame()                       # (every line and tile shares it)
    x, y = f.xy(lat, lon)             # scalars or numpy arrays
    lat, lon = f.ll(x, y)
    x, y = f.from_jtsk(E, N)          # survey data (DTM, DMR 5G, IPR) is native S-JTSK
"""
import json
import math
import os

import numpy as np
import pyproj
from pyproj import Transformer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGIN = (-742806.0, -1043024.0)  # S-JTSK E, N of the Marian column (OSM way 815041625, whole metres)
GRID = "cz_cuzk_table_-y-x_3_v1710.tif"
GRID_DIR = os.path.join(ROOT, "raw", "proj")
# ETRS89 lat/lon -> S-JTSK (EPSG:5514) with the ČÚZK grid, as PROJ 9 builds it ("Inverse of ETRS89 to
# S-JTSK / Krovak East North", accuracy 0.035 m)
PIPELINE = (
    "+proj=pipeline +step +proj=axisswap +order=2,1 +step +proj=unitconvert +xy_in=deg +xy_out=rad"
    " +step +proj=push +v_3 +step +proj=cart +ellps=GRS80"
    " +step +inv +proj=helmert +x=572.213 +y=85.334 +z=461.94 +rx=-4.9732 +ry=-1.529 +rz=-5.2484"
    " +s=3.5378 +convention=coordinate_frame +step +inv +proj=cart +ellps=bessel +step +proj=pop +v_3"
    " +step +proj=mod_krovak +lat_0=49.5 +lon_0=24.8333333333333 +alpha=30.2881397222222 +k=0.9999"
    " +x_0=5000000 +y_0=5000000 +ellps=bessel +step +inv +proj=gridshift +grids=" + GRID
)
R_EARTH = 6378137.0  # Web Mercator (EPSG:3857) sphere

_T = None


def _transformer():
    global _T
    if _T is None:
        if not os.path.exists(os.path.join(GRID_DIR, GRID)):
            raise SystemExit(f"missing {GRID} in raw/proj/: fetch the snapshot (python -I tools/snapshot.py fetch)")
        pyproj.datadir.append_data_dir(GRID_DIR)
        _T = Transformer.from_pipeline(PIPELINE)  # input (lat, lon), output (E, N)
    return _T


class Frame:
    """The city frame: S-JTSK minus ORIGIN."""

    E0, N0 = ORIGIN

    @classmethod
    def of_line(cls, line=None):
        return cls()  # one frame for every line

    def xy(self, lat, lon):
        e, n = _transformer().transform(_arr(lat), _arr(lon), errcheck=True)
        return e - self.E0, n - self.N0

    def ll(self, x, y):
        lat, lon = _transformer().transform(_arr(x) + self.E0, _arr(y) + self.N0, direction="INVERSE", errcheck=True)
        return lat, lon

    def from_jtsk(self, e, n):
        return _arr(e) - self.E0, _arr(n) - self.N0

    def to_jtsk(self, x, y):
        return _arr(x) + self.E0, _arr(y) + self.N0

    def from_merc(self, mx, my):
        """Web Mercator (Geoportál's I3S) to game metres."""
        lat = [math.degrees(2 * math.atan(math.exp(v / R_EARTH)) - math.pi / 2) for v in _seq(my)]
        lon = [math.degrees(v / R_EARTH) for v in _seq(mx)]
        if not hasattr(mx, "__len__"):
            return self.xy(lat[0], lon[0])
        return self.xy(lat, lon)

    def bbox(self, pts, margin=0.0):
        """(s, w, n, e) lat/lon around local points, `margin` m out (the frame is rotated against
        lat/lon by ~8°: the box is taken over the corners and edge midpoints)."""
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        x0, x1, y0, y1 = min(xs) - margin, max(xs) + margin, min(ys) - margin, max(ys) + margin
        xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
        cx = [x0, xm, x1, x1, x1, xm, x0, x0]
        cy = [y0, y0, y0, ym, y1, y1, y1, ym]
        lat, lon = self.ll(cx, cy)
        return min(lat), min(lon), max(lat), max(lon)

    def origin_ll(self):
        return self.ll(0.0, 0.0)


def _arr(v):
    return np.asarray(v, dtype=float) if isinstance(v, (list, tuple)) else v


def _seq(v):
    return v if hasattr(v, "__len__") else [v]


def load_line(line):
    with open(os.path.join(ROOT, "data", f"line{line}.json"), encoding="utf-8") as f:
        return json.load(f)
