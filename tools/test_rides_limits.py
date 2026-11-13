# SPDX-License-Identifier: AGPL-3.0-or-later
"""The rides-against-limits comparison's parts on a made-up track: python -P -E tools/test_rides_limits.py (#451)"""
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rides_limits as R  # noqa: E402

# a straight track along x, a point every 2 m, 400 m
P = np.array([[x, 0.0] for x in range(0, 401, 2)], dtype=float)


def limits(eff, curve=None, osm=None, restr=None, stops=((0, "A"), (200, "B"), (400, "C"))):
    L = len(eff) - 1
    return {"L": L, "len": 15, "past": 0, "eff": eff, "raw": list(eff), "curve": curve or list(eff), "osm": osm or [0] * (L + 1),
            "restr": restr or [99] * (L + 1), "stops": [{"name": n, "s": s} for s, n in stops]}


class Rides(unittest.TestCase):
    def test_gpx_speed_in_kmh(self):
        gpx = ('<gpx><trk><trkseg><trkpt lat="50.08" lon="14.40"><ele>230.0</ele><time>2026-11-08T17:00:00Z</time><speed>5.000</speed></trkpt>'
               '<trkpt lat="50.08" lon="14.40"><time>2026-11-08T17:00:02Z</time><speed>10.000</speed><sat>20</sat></trkpt></trkseg></trk></gpx>')
        with tempfile.NamedTemporaryFile("w", suffix=".gpx", delete=False, encoding="utf-8") as f:
            f.write(gpx)
        try:
            t, lat, lon, kmh = R.read_gpx(f.name)
        finally:
            os.unlink(f.name)
        self.assertEqual(list(t), [0.0, 2.0])
        self.assertEqual(list(kmh), [18.0, 36.0])

    def test_only_the_lines_way(self):
        x = np.array([100.0, 102.0, 104.0, 106.0])
        s, d = R.project(P, x, np.array([1.0, 1.0, 1.0, 1.0]))
        self.assertEqual([round(v) for v in s], [100, 102, 104, 106])
        self.assertTrue(np.all(d < 1.5))
        s, d = R.project(P, x[::-1], np.array([1.0, 1.0, 1.0, 1.0]))   # the other way
        self.assertTrue(np.all(np.isinf(d)))

    def test_faster_than_ours(self):
        eff = [20.0] * 401
        real = np.full(401, 18.0)
        real[100:131] = 30.0                    # 31 m at 30 km/h where ours is 20
        real[300:305] = 30.0                    # 5 m: too short to count
        places, stretches = R.compare(limits(eff), real)
        self.assertEqual([(p["from"], p["to"], p["limit"], p["real"], p["cause"]) for p in places], [(100, 130, 20.0, 30.0, "curve")])
        self.assertEqual([x["to"] for x in stretches], ["B", "C"])
        self.assertLess(stretches[0]["quickRaised"], stretches[0]["quickOurs"])
        self.assertEqual(stretches[1]["quickRaised"], stretches[1]["quickOurs"])

    def test_what_sets_it(self):
        eff = [20.0] * 401
        osm = [20] * 401
        curve = [50.0] * 401
        real = np.full(401, 18.0)
        real[100:131] = 30.0
        places, _ = R.compare(limits(eff, curve=curve, osm=osm), real)
        self.assertEqual(places[0]["cause"], "posted")
        restr = [99] * 401
        for m in range(80, 140):   # (under the whole tram at the place's first metre)
            restr[m] = 20
        places, _ = R.compare(limits(eff, curve=curve, restr=restr), real)
        self.assertEqual(places[0]["cause"], "restriction")

    def test_quickest_run(self):
        # 100 m with no limit to speak of: up at RUN_A, down at RUN_B, a peak where the two meet
        v = (100 / (1 / (2 * R.RUN_A) + 1 / (2 * R.RUN_B))) ** 0.5
        t = R.quickest(np.full(101, 30.0), 0, 100)
        self.assertAlmostEqual(t, v / R.RUN_A + v / R.RUN_B, delta=1.0)


if __name__ == "__main__":
    unittest.main()
