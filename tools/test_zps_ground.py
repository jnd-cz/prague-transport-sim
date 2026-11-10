"""tools/zps_ground.py: the survey's ground-level areas judged against the lidar, the rails and DMR 5G (#446).

    python -P -E tools/test_zps_ground.py
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shapely  # noqa: E402

import zps_ground as zg  # noqa: E402

GROUND = 200.0


class Frame:
    """A stand-in for tools/geo.Frame: S-JTSK is the city frame shifted by 1000 m; lat/lon are y/x over 1000."""

    def to_jtsk(self, x, y):
        return np.asarray(x, float) + 1000, np.asarray(y, float) + 1000

    def ll(self, x, y):
        return y / 1000, x / 1000

    def xy(self, lat, lon):
        return lon * 1000, lat * 1000


def ground(E, N):
    return np.full(np.shape(E), GROUND)


def square(x0, y0, w, z, cls="road", level=0):
    zs = z if isinstance(z, list) else [z] * 4
    return {"c": cls, "l": level, "r": [[x0, y0, zs[0]], [x0 + w, y0, zs[1]], [x0 + w, y0 + w, zs[2]], [x0, y0 + w, zs[3]]]}


def rails_through(x0, y0, w, z, n=20):
    """Stations along the middle of a square."""
    xs = np.linspace(x0 + 1, x0 + w - 1, n)
    return xs, np.full(n, y0 + w / 2), np.full(n, z)


NONE = (np.zeros(0), np.zeros(0), np.zeros(0))
F = Frame()


def verdict(areas, rails=NONE, older=ground, cover=None, facts=(), changing=None, i=0):
    v = zg.judge(areas, ground, older, cover if cover is not None else zg.cover_union(areas), rails, F, facts, changing)
    return v[i]


class Judge(unittest.TestCase):
    def test_inner_points_lie_inside(self):
        xy = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float)
        pin, inside, poly = zg.inner_points(xy)
        self.assertTrue(inside.all())
        self.assertTrue(np.allclose(np.abs(pin - 5), 5 - zg.INNER / np.sqrt(2)))

    def test_fits(self):
        self.assertEqual(verdict([square(0, 0, 20, GROUND + 0.2)])["verdict"], "fits")

    def test_rails_confirm_ipr(self):
        """Kabešova (line 37): a street block 1.8 m under IPR, DMR 5G and DI's rails, the rails decide."""
        a = square(0, 0, 20, GROUND - 1.8)
        v = verdict([a], rails_through(0, 0, 20, GROUND))
        self.assertEqual((v["verdict"], v["by"]), ("lidar", "rails"))

    def test_rails_confirm_the_survey(self):
        a = square(0, 0, 20, GROUND - 1.8)
        v = verdict([a], rails_through(0, 0, 20, GROUND - 1.8))
        self.assertEqual((v["verdict"], v["by"]), ("survey", "rails"))

    def test_dmr5g_confirms_ipr(self):
        v = verdict([square(0, 0, 20, GROUND + 1.2)])
        self.assertEqual((v["verdict"], v["by"]), ("lidar", "dmr5g"))

    def test_neither_decides(self):
        """The two lidars differ (the ground changed between them) and no rail runs there: held for review."""
        v = verdict([square(0, 0, 20, GROUND + 1.2)], older=lambda E, N: np.full(np.shape(E), GROUND + 1.0))
        self.assertEqual(v["verdict"], "review")

    def test_the_users_rule_decides_what_nothing_else_does(self):
        """The user, 2026-11-10: courtyards to the lidar, greenery outside to the survey (paved outside: the lidar)."""
        rule = {"courtyard": "lidar", "outsideGreen": "survey", "outside": "lidar"}
        older = lambda E, N: np.full(np.shape(E), GROUND + 1.0)  # noqa: E731  (the lidars disagree: nothing else decides)
        ring_of_houses = shapely.box(-40, -40, 60, 60).difference(shapely.box(-20, -20, 40, 40))
        for area, buildings, want in ((square(0, 0, 20, GROUND + 1.2), ring_of_houses, "lidar"),
                                      (square(0, 0, 20, GROUND + 1.2, cls="green"), shapely.box(100, 100, 120, 120), "survey"),
                                      (square(0, 0, 20, GROUND + 1.2), shapely.box(100, 100, 120, 120), "lidar")):
            v = zg.judge([area], ground, older, zg.cover_union([area]), NONE, F, rule=rule, buildings=buildings)[0]
            self.assertEqual((v["verdict"], v["by"]), (want, "rule"))
        v = zg.judge([square(0, 0, 20, GROUND + 1.2)], ground, older, zg.cover_union([]), NONE, F)[0]
        self.assertEqual(v["verdict"], "review")  # (no rule: held)

    def test_small(self):
        """A planter or a light well: lidar's bare earth leaves it out."""
        self.assertEqual(verdict([square(0, 0, 5, GROUND + 1.5)])["verdict"], "small")

    def test_covered(self):
        """Under a deck (a survey area of level 1 over it) IPR interpolates: the survey stays."""
        areas = [square(0, 0, 20, GROUND - 5.3), square(-5, -5, 30, GROUND, cls="road", level=1)]
        self.assertEqual(verdict(areas)["verdict"], "covered")

    def test_construction_site(self):
        changing = shapely.box(-1, -1, 21, 21)
        self.assertEqual(verdict([square(0, 0, 20, GROUND + 1.7)], changing=changing)["verdict"], "changing")

    def test_uneven(self):
        """Off IPR, but a wall's top and foot by turns or a slope, not a steady offset: left as it is."""
        a = square(0, 0, 20, [GROUND - 1, GROUND + 1, GROUND + 1, GROUND + 1.5])
        self.assertEqual(verdict([a])["verdict"], "uneven")

    def test_fact_wins(self):
        facts = [{"lat": 0.01, "lon": 0.01, "verdict": "survey"}]
        v = verdict([square(0, 0, 20, GROUND - 1.8)], rails_through(0, 0, 20, GROUND), facts=facts)
        self.assertEqual((v["verdict"], v["by"]), ("survey", "fact"))

    def test_an_answer_takes_its_own_area_not_the_one_around_it(self):
        """A courtyard's lawn is a hole in the sidewalk around it: the answer is the lawn's, the sidewalk fits."""
        lawn = square(20, 20, 20, GROUND - 1.8, cls="green")
        walk = square(0, 0, 60, GROUND - 0.1, cls="sidewalk")
        walk["h"] = [[q[:] for q in lawn["r"]]]
        facts = [{"lat": 0.03, "lon": 0.03, "verdict": "lidar", "c": "green", "m2": 400}]
        v = zg.judge([walk, lawn], ground, ground, zg.cover_union([]), NONE, F, facts)
        self.assertEqual((v[1]["verdict"], v[1]["by"]), ("lidar", "fact"))
        self.assertEqual(v[0]["verdict"], "fits")

    def test_not_ground(self):
        v = zg.judge([square(0, 0, 20, GROUND + 3, cls="stairs"), square(0, 30, 20, GROUND + 3, cls="water")],
                     ground, ground, zg.cover_union([]), NONE, F)
        self.assertEqual(v, {})


class Apply(unittest.TestCase):
    def test_moves_the_area_and_the_same_heights_beside_it(self):
        """The neighbour took the same wrong heights from the same survey line at the shared corners; its own stay."""
        a = square(0, 0, 20, GROUND - 1.8)
        b = {"c": "sidewalk", "l": 0, "r": [[20, 0, GROUND - 1.8], [25, 0, GROUND], [25, 20, GROUND], [20, 20, GROUND - 1.8]]}
        areas = [a, b]
        v = zg.judge(areas, ground, ground, zg.cover_union(areas), rails_through(0, 0, 20, GROUND), F)
        self.assertEqual(v[0]["verdict"], "lidar")
        moved = zg.apply(areas, v)
        self.assertEqual(moved, 6)
        self.assertTrue(all(abs(q[2] - GROUND) < 0.01 for q in a["r"]))
        self.assertEqual([q[2] for q in b["r"]], [GROUND] * 4)

    def test_kept_areas_stay(self):
        a = square(0, 0, 20, GROUND - 1.8)
        v = {0: {"verdict": "survey", "offset": -1.8}}
        self.assertEqual(zg.apply([a], v), 0)
        self.assertEqual(a["r"][0][2], GROUND - 1.8)


class Rails(unittest.TestCase):
    def test_stations_skip_missing_heights(self):
        """DI writes 0 for a height it lacks."""
        x, y, z = zg.rail_points([{"coords": [(0, 0, 200.0), (10, 0, 201.0), (20, 0, 0.0)]}])
        self.assertEqual(len(x), 5)
        self.assertAlmostEqual(z[-1], 200.8)


if __name__ == "__main__":
    unittest.main()
