"""The one coordinate conversion of the line data (docs/history/BUILD-TOOLS-HANDOFF.md §1.1). Every tool imports it.

A line's local metres: x east, y north from `origin = [lat0, lon0]` of data/lineN.json, with 110574 m
per degree of latitude and 111320·cos(lat0) per degree of longitude. (The remote OSM signal import
re-typed it with 111320 for latitude too: nodes up to 45 m off at the line's ends.)

    from geo import Frame
    f = Frame.of_line("17")          # or Frame(lat0, lon0)
    x, y = f.xy(lat, lon); lat, lon = f.ll(x, y)
"""
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KY = 110574.0  # m per degree of latitude


class Frame:
    def __init__(self, lat0, lon0):
        self.lat0, self.lon0 = lat0, lon0
        self.kx, self.ky = 111320.0 * math.cos(math.radians(lat0)), KY

    @classmethod
    def of_line(cls, line):
        d = json.load(open(os.path.join(ROOT, "data", f"line{line}.json"), encoding="utf-8"))
        return cls(*d["origin"])

    def xy(self, lat, lon):
        return (lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky

    def ll(self, x, y):
        return self.lat0 + y / self.ky, self.lon0 + x / self.kx

    def bbox(self, pts, margin=0.0):
        """(s, w, n, e) around local points, `margin` m out."""
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        s, w = self.ll(min(xs) - margin, min(ys) - margin)
        n, e = self.ll(max(xs) + margin, max(ys) + margin)
        return s, w, n, e
