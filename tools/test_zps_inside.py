# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/zps_inside.py: the lidar inside the survey's outline-only areas, the ground under the decks (#444).

    python -P -E tools/test_zps_inside.py
"""
import os
import sys
import unittest

import numpy as np
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zps_inside as zi  # noqa: E402

DECK, FLOOR = 193.3, 187.8


def area(pts, cls="road", level=0):
    return {"c": cls, "l": level, "r": [list(p) for p in pts]}


def rect(x0, y0, x1, y1, z, cls="road", level=0):
    zs = z if isinstance(z, list) else [z] * 4
    return area([(x0, y0, zs[0]), (x1, y0, zs[1]), (x1, y1, zs[2]), (x0, y1, zs[3])], cls, level)


def floor(x, y):
    return np.full(np.shape(x), FLOOR)


def mound(x, y):
    """IPR: 200 m with a mound 1 m high over the middle of the 50 m squares below."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    return 200 + 1.0 * ((np.abs(x - 25) < 15) & (np.abs(y - 25) < 15))


class Inside(unittest.TestCase):
    def test_lawns_drape_unless_held_and_yards_where_their_sheet_misses_the_ground(self):
        cls = ("rail", "green", "paved", "green", "green", "paved", "green", "road", "paved")
        areas = [rect(0, 0, 50, 50, 200, c) for c in cls] + [rect(0, 0, 50, 50, 205, "green", 1)]
        verdicts = dict(enumerate({"verdict": v, "m2": 2500} for v in
                                  ("fits", "lidar", "uneven", "small", "covered", "survey", "review", "fits", "covered")))
        out = zi.inside(areas, verdicts, mound)
        self.assertEqual([a.get("g") for a in areas], [1, 1, 1, 1, 1, None, None, None, None, None])
        self.assertEqual(out["kept"], {"survey": 1, "review": 1, "covered": 1})
        self.assertEqual(out["classes"]["green"], {"areas": 3, "m2": 7500})

    def test_a_yards_sheet_that_fits_stays(self):
        """A flat paved yard on flat ground: draped, it would follow the lidar's noise (the street check's waves)."""
        areas = [rect(0, 0, 50, 50, 200, "paved"), rect(0, 0, 3, 3, 200, "paved"), rect(0, 0, 50, 50, 200, "green")]
        flat = lambda x, y: np.full(np.shape(x), 200.1)  # noqa: E731
        out = zi.inside(areas, {0: {"verdict": "fits"}, 1: {"verdict": "fits"}, 2: {"verdict": "fits"}}, flat)
        self.assertEqual([a.get("g") for a in areas], [None, None, 1])  # (the lawn drapes as on main)
        self.assertEqual(out["fit"], {"paved": 2})  # (the small one: no lattice point inside)

    def test_a_paved_yard_misses_the_ground_sooner_than_a_railway_yard(self):
        """#638: a sheet 0.4 m off the ground: over the step a yard may have to a sidewalk beside it (MISS_PAVED), under
        MISS."""
        areas = [rect(0, 0, 50, 50, 200, "paved"), rect(0, 0, 50, 50, 200, "rail"), rect(0, 0, 50, 50, 200, "paved")]
        off = lambda x, y: np.full(np.shape(x), 200.4)  # noqa: E731
        zi.inside(areas, {k: {"verdict": "fits"} for k in range(2)}, off)
        self.assertEqual([a.get("g") for a in areas[:2]], [1, None])
        zi.inside(areas[2:], {0: {"verdict": "fits"}}, lambda x, y: np.full(np.shape(x), 200.25))
        self.assertIsNone(areas[2].get("g"))

    def test_a_parking_bay_is_held_as_a_paved_yard(self):
        """#800: a bay whose outline rises to one point of the survey's line 0.6 m over IPR (Vinohradská, area 3091: 0.38
        m) lies on the lidar; one whose sheet fits stays, a road never takes the lidar, one held off IPR keeps its sheet."""
        bay = lambda: rect(0, 0, 60, 8, [200.0, 200.0, 200.6, 200.0], "parking")  # noqa: E731
        areas = [bay(), rect(0, 0, 60, 8, 200.0, "parking"), rect(0, 0, 60, 8, [200.0, 200.0, 200.6, 200.0], "road"),
                 bay()]
        flat = lambda x, y: np.full(np.shape(x), 200.0)  # noqa: E731
        out = zi.inside(areas, {0: {"verdict": "fits", "m2": 480}, 1: {"verdict": "fits"}, 2: {"verdict": "fits"},
                                3: {"verdict": "survey"}}, flat)
        self.assertTrue(zi.MISS_PAVED < zi.misses(bay(), flat) < zi.MISS)
        self.assertEqual([a.get("g") for a in areas], [1, None, None, None])
        self.assertEqual(out["classes"], {"parking": {"areas": 1, "m2": 480}})
        self.assertEqual(out["fit"], {"parking": 1})

    def test_a_parking_area_under_a_cover_keeps_its_sheet(self):
        """#800: the car parks under the Magistrála's bridges at Hlavní nádraží lie within OFFSET of IPR at their outline
        (never judged covered) and IPR inside them is the bridges: one over a third under a cover keeps its sheet, one
        with a corner of it under a cover takes the lidar, and a paved yard is left as it was built."""
        import shapely

        class Cover:
            is_empty = False

            def __init__(self, box):
                self.box = shapely.box(*box)

            def contains_xy(self, x, y):
                return shapely.contains_xy(self.box, x, y)
        mk = lambda c: rect(0, 0, 60, 8, [200.0, 200.0, 200.6, 200.0], c)  # noqa: E731
        flat = lambda x, y: np.full(np.shape(x), 200.0)  # noqa: E731
        fits = {k: {"verdict": "fits"} for k in range(2)}
        half, corner = Cover((0, 0, 30, 8)), Cover((0, 0, 10, 8))
        self.assertAlmostEqual(zi.under_cover(mk("parking"), half), 0.5, 1)
        areas = [mk("parking"), mk("paved")]
        out = zi.inside(areas, fits, flat, half)
        self.assertEqual([a.get("g") for a in areas], [None, 1])
        self.assertEqual(out["kept"], {"under a cover": 1})
        areas = [mk("parking"), mk("paved")]
        zi.inside(areas, fits, flat, corner)
        self.assertEqual([a.get("g") for a in areas], [1, 1])


class UnderDecks(unittest.TestCase):
    """A deck 20 m wide (y 0-20) at DECK over a way running north-south (x 10) whose floor IPR shows at FLOOR."""

    def setup(self, way_len=60.0, cover_floor=FLOOR):
        deck = rect(-20, 0, 40, 20, DECK, "deck", 1)
        axis = shapely.LineString([(10, -way_len / 2 + 10), (10, way_len / 2 + 10)]).intersection(shapely.box(-20, -1, 40, 21))
        opening = {"way": 1, "axis": axis, "poly": shapely.box(4, -1, 16, 21), "decks": [0]}
        flat = {"openings": [{"way": 1, "gap": 5.4, "src": "maxheight"}]}
        ground = (lambda x, y: np.full(np.shape(x), cover_floor))
        return deck, opening, flat, ground

    def test_the_street_along_the_way_takes_the_floor_where_it_stands_at_the_deck(self):
        deck, o, flat, ground = self.setup()
        # the passage's road, its outline at the deck by the portals (the survey's lines shared with the deck), on the
        # floor inside
        road = area([(5, -10, FLOOR), (15, -10, FLOOR), (15, 0, DECK), (15, 20, DECK - 0.1), (15, 30, FLOOR), (5, 30, FLOOR),
                     (5, 20, DECK - 0.1), (5, 10, FLOOR + 0.05)])
        areas = [deck, road]
        out = zi.under_decks(areas, [o], flat, ground)
        zs = [q[2] for q in road["r"]]
        self.assertEqual(out["vertices"], 3)
        self.assertEqual(zs, [FLOOR, FLOOR, FLOOR, FLOOR, FLOOR, FLOOR, FLOOR, FLOOR + 0.05])  # (the floor's own stays)
        self.assertEqual(deck["r"][0][2], DECK)

    def test_a_vertex_nearer_the_top_than_the_floor_moves_its_twin_too(self):
        """Modřany: of two vertices 0.1 m apart 0.98 and 1.03 m under the deck's top, both stand at the deck (a fixed 1 m
        under the top moved one, a 1.6 m step); one over the floor is the floor's."""
        deck, o, flat, ground = self.setup()
        road = area([(5, -10, FLOOR), (15, -10, FLOOR), (15, 0, DECK - 0.98), (15, 0.1, DECK - 1.03), (15, 30, FLOOR),
                     (5, 30, FLOOR), (5, 10, FLOOR + 0.6), (5, 5, FLOOR + 0.1)])
        out = zi.under_decks([deck, road], [o], flat, ground)
        self.assertEqual(out["vertices"], 2)
        self.assertEqual([q[2] for q in road["r"]], [FLOOR, FLOOR, FLOOR, FLOOR, FLOOR, FLOOR, FLOOR + 0.6, FLOOR + 0.1])

    def test_a_level_over_the_passage_stays(self):
        """By Hlavní nádraží a paved strip of the forecourt at 205 m lies over the tram's tunnel (the tram at 198 m) along
        it, under the deck's underside at 207.7 m: a level between, not the deck's."""
        deck, o, flat, ground = self.setup()
        forecourt = rect(5, -10, 9, 30, DECK - 3.0, "paved")
        self.assertEqual(zi.under_decks([deck, forecourt], [o], flat, ground)["vertices"], 0)
        self.assertEqual({q[2] for q in forecourt["r"]}, {DECK - 3.0})

    def test_an_area_across_the_way_stays(self):
        """The tram over a footway's underpass at grade (line 37's east end): it runs across the way."""
        deck, o, flat, ground = self.setup()
        tram = rect(-20, 5, 40, 12, DECK, "tram")
        zi.under_decks([deck, tram], [o], flat, ground)
        self.assertEqual({q[2] for q in tram["r"]}, {DECK})

    def test_ipr_at_the_cover_moves_nothing(self):
        deck, o, flat, ground = self.setup(cover_floor=DECK - 0.5)
        road = rect(5, -10, 15, 30, DECK - 0.1, "road")
        out = zi.under_decks([deck, road], [o], flat, ground)
        self.assertEqual(out["vertices"], 0)

    def test_an_unseen_floor_or_a_stub_moves_nothing(self):
        deck, o, flat, ground = self.setup()
        road = rect(5, -10, 15, 30, DECK - 0.1, "road")
        unseen = {"openings": [{"way": 1, "gap": 1.0, "src": "unseen"}]}
        self.assertEqual(zi.under_decks([deck, road], [o], unseen, ground)["vertices"], 0)
        deck, o, flat, ground = self.setup()
        o["axis"] = shapely.LineString([(10, 8), (10, 11)])
        self.assertEqual(zi.under_decks([deck, road], [o], flat, ground)["vertices"], 0)

    def test_bearing(self):
        d, e = zi._bearing(shapely.box(0, 0, 40, 4))
        self.assertAlmostEqual(d, 0.0)
        self.assertAlmostEqual(e, 10.0)
        d, e = zi._bearing(shapely.LineString([(0, 0), (0, 5)]))
        self.assertAlmostEqual(d, np.pi / 2)


if __name__ == "__main__":
    unittest.main()
