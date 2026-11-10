"""tools/zps_decks.py: the survey's decks against their structures, flat over the openings, their thickness (#445).

    python -P -E tools/test_zps_decks.py
"""
import os
import sys
import unittest
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zps_decks as zd  # noqa: E402

GROUND = 200.0
DECK = 210.0


def ground(x, y):
    return np.full(np.shape(x), GROUND)


def bridge(x0, y0, x1, y1, z, fid=7):
    """A Mosty 3D stand-in: one flat top over a rectangle."""
    tris = np.array([[[x0, y0, z], [x1, y0, z], [x1, y1, z]], [[x0, y0, z], [x1, y1, z], [x0, y1, z]]], float)
    return SimpleNamespace(tris=tris, ids=[fid], owner=np.array([0, 0]))


def area(pts, cls="road", level=1):
    return {"c": cls, "l": level, "r": [list(p) for p in pts]}


def square(x0, y0, w, z, cls="road", level=1):
    zs = z if isinstance(z, list) else [z] * 4
    return area([(x0, y0, zs[0]), (x0 + w, y0, zs[1]), (x0 + w, y0 + w, zs[2]), (x0, y0 + w, zs[3])], cls, level)


NO_RAILS = zd.Rails((np.zeros(0), np.zeros(0), np.zeros(0)), ground)


class Frame:
    """tools/geo.Frame's xy: lat/lon are y/x over 1000."""

    def xy(self, lat, lon):
        return np.asarray(lon, float) * 1000, np.asarray(lat, float) * 1000


def way(wid, pts, **tags):
    return {"id": wid, "tags": {"highway": "residential", **tags}, "geometry": [{"lat": y / 1000, "lon": x / 1000} for x, y in pts]}


class Check(unittest.TestCase):
    def test_a_sag_takes_the_model_and_its_decks_offset(self):
        """Krejcárek: a deck vertex at the ground under the model's top takes the top less the deck's own offset."""
        model = zd.Model(bridge(0, 0, 40, 20, DECK))
        a = square(0, 0, 10, [DECK - 0.7, DECK - 0.7, DECK - 0.7, GROUND])  # (one corner took the ground's line)
        out = zd.check([a], model, NO_RAILS)
        self.assertEqual(out["vertices"], {"model": 1, "rails": 0, "inside": 0})
        self.assertAlmostEqual(a["r"][3][2], DECK - 0.7)

    def test_the_neighbours_offset_where_the_area_has_none_on_it(self):
        model = zd.Model(bridge(0, 0, 40, 20, DECK))
        good = square(0, 0, 10, DECK - 0.5, cls="tram")
        sunk = square(10, 0, 10, GROUND, cls="tram")  # (touches the good one: the same deck)
        zd.check([good, sunk], model, NO_RAILS)
        self.assertEqual([q[2] for q in sunk["r"]], [DECK - 0.5] * 4)

    def test_an_area_partly_under_a_structure_is_another_deck(self):
        """A level-1 area at the ground running under a bridge and past it, no vertex of its deck on the bridge: it stays."""
        model = zd.Model(bridge(0, 0, 40, 20, DECK + 6))
        a = area([(30, 0, GROUND + 0.2), (39, 0, GROUND + 0.2), (39, 10, GROUND + 0.2), (30, 10, GROUND + 0.2),
                  (30, 30, GROUND + 0.2), (20, 30, GROUND + 0.2), (20, 10, GROUND + 0.2)], cls="rail")
        out = zd.check([a], model, NO_RAILS)
        self.assertEqual(len(out["heldAreas"]), 1)
        self.assertEqual(a["r"][0][2], GROUND + 0.2)

    def test_an_area_inside_a_model_with_the_grounds_heights_takes_its_top(self):
        """Výtoň: the railway and its walkway on Železniční most's land span carry the street's heights, 5 m under the
        model's slab; a portal's face over one corner (a truss, a pylon) is not the deck."""
        tris = bridge(0, 0, 40, 20, 197.5).tris
        portal = bridge(8, 8, 12, 12, 210.4).tris
        model = zd.Model(SimpleNamespace(tris=np.concatenate([tris, portal]), ids=[7], owner=np.zeros(4, int)))
        a = square(0, 0, 10, [192.0, 192.1, 192.2, 191.9], cls="rail")
        out = zd.check([a], model, NO_RAILS)
        self.assertEqual((out["vertices"]["inside"], out["held"]), (4, 0))
        self.assertEqual([q[2] for q in a["r"]], [197.5] * 4)

    def test_a_piece_under_the_portal_takes_its_decks_level(self):
        """Výtoň's walkway: a small piece of the deck lies wholly under a portal's face; the deck's level is the slab's."""
        tris = bridge(0, 0, 40, 20, 197.5).tris
        portal = bridge(8, 4, 13, 9, 210.4).tris
        model = zd.Model(SimpleNamespace(tris=np.concatenate([tris, portal]), ids=[7], owner=np.zeros(4, int)))
        track = area([(x_, 0, 192.0) for x_ in range(0, 21, 4)] + [(x_, 4, 192.0) for x_ in range(20, -1, -4)], cls="rail")
        walk = square(9, 4, 3, 191.0, cls="sidewalk")
        zd.check([track, walk], model, NO_RAILS)
        self.assertEqual([q[2] for q in walk["r"]], [197.5] * 4)

    def test_where_two_features_meet_the_decks_own_one_counts(self):
        """Libeň: two viaducts side by side at 210.3 and 212.0 m; a corner at the seam belongs to the deck's own one."""
        a_, b_ = bridge(0, 0, 20, 20, 212.0).tris, bridge(20.5, 0, 40, 20, 210.3).tris
        model = zd.Model(SimpleNamespace(tris=np.concatenate([a_, b_]), ids=[551, 548], owner=np.array([0, 0, 1, 1])))
        a = area([(5, 5, 211.8), (19, 5, 211.8), (20.6, 15, 195.7), (5, 15, 211.8)], cls="rail")
        out = zd.check([a], model, NO_RAILS)
        self.assertEqual(out["held"], 0)
        self.assertAlmostEqual(a["r"][2][2], 211.8)

    def test_the_models_edge_reaches_past_its_faces(self):
        """Krejcárek's road deck: its outline runs a few decimetres off the model's edge; the corner there is on it."""
        model = zd.Model(bridge(0, 0, 40, 20, DECK))
        a = area([(10, 5, DECK - 0.3), (20, 5, DECK - 0.3), (20, 20.8, GROUND), (10, 20.8, DECK - 0.3)])
        zd.check([a], model, NO_RAILS)
        self.assertAlmostEqual(a["r"][2][2], DECK - 0.3)

    def test_the_rails_where_no_model_is(self):
        """Divadelní: no Mosty 3D model, the rails on the deck 5.3 m over IPR's floor."""
        x = np.linspace(-5, 25, 31)
        rails = zd.Rails((x, np.full(31, 5.0), np.full(31, 193.25)), lambda x, y: np.full(np.shape(x), 187.95))
        a = square(0, 0, 10, [193.2, 193.2, 187.9, 193.2])
        out = zd.check([a], zd.Model(), rails)
        self.assertEqual(out["vertices"], {"model": 0, "rails": 1, "inside": 0})
        self.assertAlmostEqual(a["r"][2][2], 193.2)

    def test_past_the_models_side_the_rails_of_the_same_deck(self):
        """Krejcárek: the deck's corners on the model also agree with the rails; a tram area past the model's side sags."""
        model = zd.Model(bridge(0, 0, 40, 5, DECK))
        x = np.linspace(-5, 45, 51)
        rails = zd.Rails((x, np.full(51, 4.0), np.full(51, DECK + 0.6)), ground)
        on = square(0, 0, 10, DECK)  # (on the model and 0.6 m under the rails)
        past = area([(10, 0, DECK), (20, 0, DECK), (20, 12, GROUND + 8.5), (10, 12, GROUND + 8.5)], cls="tram")
        zd.check([on, past], model, rails)
        self.assertEqual([q[2] for q in past["r"]], [DECK] * 4)

    def test_a_deck_over_the_track_is_not_the_tracks_deck(self):
        """A footbridge 6 m over raised rails: not lowered to them."""
        x = np.linspace(-5, 25, 31)
        rails = zd.Rails((x, np.full(31, 5.0), np.full(31, DECK)), ground)
        a = square(0, 0, 10, DECK + 6)
        zd.check([a], zd.Model(), rails)
        self.assertEqual(a["r"][0][2], DECK + 6)

    def test_rails_at_grade_check_nothing(self):
        x = np.linspace(-5, 25, 31)
        rails = zd.Rails((x, np.full(31, 5.0), np.full(31, GROUND + 0.2)), ground)
        a = square(0, 0, 10, [GROUND + 6, GROUND + 6, GROUND, GROUND + 6])
        zd.check([a], zd.Model(), rails)
        self.assertEqual(a["r"][2][2], GROUND)

    def test_not_decks(self):
        model = zd.Model(bridge(0, 0, 40, 20, DECK))
        walls = [square(0, 0, 10, GROUND, cls=c) for c in ("wall", "stairs", "roof", "underpass", "tunnel")]
        walls.append(square(0, 0, 10, GROUND, level=0))
        out = zd.check(walls, model, NO_RAILS)
        self.assertEqual(out["vertices"], {"model": 0, "rails": 0, "inside": 0})


class Split(unittest.TestCase):
    def test_an_area_over_two_viaducts_is_two_decks(self):
        """Libeň: a railway area spans two viaducts side by side at 205.7 and 212 m with a 4 m gap between them; each
        piece lies on its own deck, straight across the span, and the gap goes."""
        low, high = bridge(0, 0, 40, 10, 205.7).tris, bridge(0, 14, 40, 24, 212.0).tris
        model = zd.Model(SimpleNamespace(tris=np.concatenate([low, high]), ids=[548, 551], owner=np.array([0, 0, 1, 1])))
        a = area([(5, 2, 205.5), (35, 2, 205.5), (35, 22, 211.8), (5, 22, 211.8)], cls="rail")
        areas = [a]
        out = zd.split(areas, model)
        self.assertEqual((out["areas"], out["pieces"]), (1, 2))
        levels = sorted(round(float(np.mean([q[2] for q in p["r"]])), 1) for p in areas)
        self.assertEqual(levels, [205.5, 211.8])
        for p in areas:
            zs = [q[2] for q in p["r"]]
            self.assertLess(max(zs) - min(zs), 0.01)  # (flat on its deck)
        ys = sorted(max(q[1] for q in p["r"]) for p in areas)
        self.assertLessEqual(ys[0], 10 + zd.EDGE + 0.1)  # (the lower piece ends at its viaduct's edge)

    def test_an_area_on_one_deck_stays_whole(self):
        model = zd.Model(bridge(0, 0, 40, 20, 212.0))
        a = area([(5, 2, 211.8), (35, 2, 211.0), (35, 12, 210.5), (5, 12, 211.5)], cls="rail")
        areas = [a]
        self.assertEqual(zd.split(areas, model), {"areas": 0, "pieces": 0})
        self.assertEqual(len(areas), 1)

    def test_a_sloping_deck_stays_whole(self):
        """Most Legií: the road falls 2.9 m over 139 m and the survey's outline has vertices only at its two ends; the
        ends are more than TOL apart but one deck slopes between them."""
        x0, x1, z0, z1 = 0.0, 140.0, 193.3, 196.3
        tris = np.array([[[x0, 0, z0], [x1, 0, z1], [x1, 20, z1]], [[x0, 0, z0], [x1, 20, z1], [x0, 20, z0]]], float)
        model = zd.Model(SimpleNamespace(tris=tris, ids=[9], owner=np.array([0, 0])))
        a = area([(1, 2, 193.3), (1, 18, 193.3), (139, 18, 196.3), (139, 2, 196.3)])
        areas = [a]
        self.assertEqual(zd.split(areas, model), {"areas": 0, "pieces": 0})
        self.assertEqual(len(areas), 1)


class Openings(unittest.TestCase):
    def divadelni(self):
        """The street under the deck 5.26 m under its top, maxheight 4.4; the deck's portal corners sag to the floor."""
        floor = lambda x, y: np.full(np.shape(x), 187.95)  # noqa: E731
        deck = area([(0, 0, 193.21), (20, 0, 193.21), (20, 20, 193.21), (15, 20, 187.9), (5, 20, 187.9), (0, 20, 193.21)])
        road = square(5, -30, 10, 187.95, level=0)
        road["r"][2][1] = road["r"][3][1] = 50  # (the street runs on under the deck: 5-15 m wide, -30 to 50 m)
        w = way(141140410, [(10, -30), (10, 50)], tunnel="yes", layer="-1", maxheight="4.4", name="Divadelní")
        return [deck, road], w, floor

    def test_the_deck_stays_on_its_plane_and_leaves_maxheight_and_the_margin(self):
        areas, w, floor = self.divadelni()
        op = zd.openings([w], areas, Frame())
        self.assertEqual([(o["way"], o["width"], o["decks"]) for o in op], [(141140410, "survey", [0])])
        out = zd.flatten(areas, op, floor)
        o = out["openings"][0]
        self.assertEqual(o["sagging"], 2)
        self.assertEqual([q[2] for q in areas[0]["r"]], [193.21] * 6)
        self.assertAlmostEqual(o["gap"], 5.16)  # (5.26 under the plane, less SAG)
        self.assertEqual((o["t"], o["src"]), (0.66, "maxheight"))
        self.assertAlmostEqual(areas[0]["t"], 0.66)
        self.assertAlmostEqual(o["clearance"], 4.5)

    def test_a_sidewalk_passes_under_with_its_street(self):
        """Divadelní: OSM's sidewalk beside the street lies under its own piece of the deck; that piece is the street's."""
        areas, w, floor = self.divadelni()
        areas.append(square(17, 0, 3, 193.21))  # (a piece of the deck by the street)
        kerb = square(15, -30, 8, 188.1, cls="sidewalk", level=0)
        kerb["r"][2][1] = kerb["r"][3][1] = 50
        areas.append(kerb)
        side = way(805407405, [(18.5, -30), (18.5, 50)], highway="footway", footway="sidewalk", tunnel="yes", layer="-1")
        op = zd.openings([w, side], areas, Frame())
        self.assertEqual([(o["way"], o["decks"]) for o in op], [(141140410, [0, 2])])
        zd.flatten(areas, op, floor)
        self.assertEqual((areas[0]["t"], areas[2]["t"]), (0.66, 0.66))

    def test_without_maxheight_the_deck_is_a_metre(self):
        areas, w, floor = self.divadelni()
        del w["tags"]["maxheight"]
        zd.flatten(areas, zd.openings([w], areas, Frame()), floor)
        self.assertNotIn("t", areas[0])

    def test_a_walkway_without_maxheight_keeps_room_to_walk(self):
        """A footway 3.0 m under a deck's top: a metre would leave 2.0 m, the deck leaves 2.2 m and the margin."""
        floor = lambda x, y: np.full(np.shape(x), 190.0)  # noqa: E731
        areas = [square(0, 0, 20, 193.0), square(5, -30, 10, 190.0, cls="sidewalk", level=0)]
        areas[1]["r"][2][1] = areas[1]["r"][3][1] = 50
        w = way(805407405, [(10, -30), (10, 50)], highway="footway", tunnel="yes", layer="-1")
        o = zd.flatten(areas, zd.openings([w], areas, Frame()), floor)["openings"][0]
        self.assertEqual((o["t"], o["src"], o["clearance"]), (0.6, "walk", 2.3))

    def test_the_plane_leaves_what_a_structure_checks(self):
        """By Hlavní nádraží two decks over the same way stand 6 m apart: the lower one, held by its model, stays."""
        areas, w, floor = self.divadelni()
        low = area([(2, 2, 189.0), (8, 2, 189.0), (8, 8, 189.0), (2, 8, 189.0)])  # (under the plane's deck, over the way)
        areas.append(low)
        op = zd.openings([w], areas, Frame())
        zd.flatten(areas, op, floor, checked={(2, 0, i): 189.0 for i in range(4)})
        self.assertEqual([q[2] for q in low["r"]], [189.0] * 4)
        self.assertEqual([q[2] for q in areas[0]["r"]], [193.21] * 6)

    def test_no_way_under_no_opening(self):
        """A ramp to an abutment: its low corners stand on the ground, nothing passes under them."""
        areas, w, floor = self.divadelni()
        self.assertEqual(zd.openings([], areas, Frame()), [])
        self.assertEqual(areas[0]["r"][3][2], 187.9)

    def test_which_ways_pass_under(self):
        self.assertTrue(zd.is_under({"highway": "footway", "tunnel": "yes", "layer": "-1"}))
        self.assertTrue(zd.is_under({"highway": "cycleway", "covered": "yes"}))
        self.assertFalse(zd.is_under({"railway": "subway", "tunnel": "yes", "layer": "-3"}))
        self.assertFalse(zd.is_under({"highway": "footway", "tunnel": "yes", "layer": "-4"}))
        self.assertFalse(zd.is_under({"highway": "residential", "bridge": "yes"}))

    def test_maxheight(self):
        self.assertEqual([zd.maxheight({"maxheight": v}) for v in ("4.4", "3,9", "4 m", "default", "none")],
                         [4.4, 3.9, 4.0, None, None])
        self.assertIsNone(zd.maxheight({}))


class Ramps(unittest.TestCase):
    def test_a_deck_down_to_the_ground(self):
        areas = [square(0, 0, 20, [GROUND + 6, GROUND + 6, GROUND + 0.5, GROUND + 0.5], cls="deck"),
                 square(0, 40, 20, GROUND + 6, cls="deck")]
        self.assertEqual(zd.ramps(areas, ground), 1)


if __name__ == "__main__":
    unittest.main()
