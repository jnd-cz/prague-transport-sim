"""The route's radius and cant built offline (tools/cant.py, #478): python -I tools/test_cant.py."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cant as C  # noqa: E402
from route import Route  # noqa: E402


def arc_route(r=50.0, side=1):
    """A straight of 400 m, a quarter turn of radius r (left for side 1), a straight of 400 m, points every metre."""
    pts = [(float(x), 0.0) for x in range(0, 401)]
    t = 1 / r
    while t < math.pi / 2:
        pts.append((400 + r * math.sin(t), side * (r - r * math.cos(t))))
        t += 1 / r
    pts += [(400.0 + r, side * (r + y)) for y in range(0, 401)]
    return Route(pts), 400, 400 + r * math.pi / 2


class Cant(unittest.TestCase):
    def test_the_design_speed_with_full_cant(self):
        # the speed a dedicated curve's cant is laid out for, in 5 km/h (src/route.js until #478)
        self.assertEqual(C.design_speed(0, True, 54), 30)
        self.assertEqual(C.design_speed(0, False, 1000), 50)
        self.assertEqual(C.design_speed(40, True, 1000), 40)

    def test_the_radius_reads_the_curve(self):
        rt, a, b = arc_route(50)
        k = C.curvature(rt)
        mid = round((a + b) / 2)
        self.assertAlmostEqual(1 / (k[mid] / C.K), 50, delta=0.5)
        self.assertEqual(k[100], 0)   # straight
        self.assertEqual(len(k), math.ceil(rt.length) + 1)

    def test_banked_on_dedicated_track_only_away_from_stops_and_ends(self):
        rt, a, b = arc_route(50)
        n = math.ceil(rt.length / 5) + 1
        mid = (a + b) / 2
        on = C.cant(rt, {"step": 5, "osm": [0] * n, "dedicated": [1] * n}, [])
        self.assertGreater(on[round(mid / 2)], 0.05)            # left turn: + (the left rail lower)
        self.assertLessEqual(max(abs(v) for v in on), C.CANT_MAX + 1e-6)
        right = C.cant(arc_route(50, -1)[0], {"step": 5, "osm": [0] * n, "dedicated": [1] * n}, [])
        self.assertLess(right[round(mid / 2)], -0.05)
        street = C.cant(rt, {"step": 5, "osm": [0] * n, "dedicated": [0] * n}, [])
        self.assertEqual(max(map(abs, street)), 0)
        stop = C.cant(rt, {"step": 5, "osm": [0] * n, "dedicated": [1] * n}, [(mid - 10, mid + 10)])
        self.assertAlmostEqual(stop[round(mid / 2)], 0, places=6)   # level at the platform
        # the ramp: at most CANT_MAX per 30 m (before the ±6 m smoothing a little steeper at its corners)
        steep = max(abs(on[i + 1] - on[i]) for i in range(len(on) - 1)) / C.STEP
        self.assertLessEqual(steep, C.CANT_MAX / 30 + 1e-6)

    def test_build_writes_both_paths(self):
        rt, _, _ = arc_route(50)
        data = {"path": [list(p) for p in rt.p], "pathBack": [list(p) for p in reversed(rt.p)],
                "stops": [{"s": 10.0}], "speed": None}
        cant, curv = C.build(data)
        self.assertEqual(cant["step"], C.STEP)
        self.assertEqual(set(curv), {"step", "unit", "path", "pathBack"})
        self.assertEqual(len(curv["path"]), len(curv["pathBack"]))


if __name__ == "__main__":
    unittest.main()
