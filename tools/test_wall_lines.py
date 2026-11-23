# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/wall_lines.py: the survey's wall lines as stretches with a level on either side, and tools/ground_mesh.py
hold_at_walls: the corners beside a stretch at their side's level (#697).

    python -P -E tools/test_wall_lines.py
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ground_mesh as gm  # noqa: E402
import wall_lines as wl  # noqa: E402


def quay(x, y, top=196.9, foot=188.6, at=0.0, smear=1.0):
    """A raster like IPR's across a wall along the y axis at x = `at`: the top to its left (x < at), the foot to its
    right, the step spread over `smear` m either side."""
    t = np.clip((np.asarray(x, float) - at + smear) / (2 * smear), 0, 1)
    return top + (foot - top) * t


class Stretches(unittest.TestCase):
    def test_a_wall_line_across_a_step_is_one_stretch_with_its_two_levels(self):
        # (the line runs north: its left is west, the top)
        line = np.array([[0.0, 0.0, 188.58], [0.0, 30.0, 188.58]])
        st = wl.of_lines([line], quay)
        self.assertEqual(len(st), 1)
        s = st[0]
        self.assertAlmostEqual(float(np.hypot(*(s["p"][-1] - s["p"][0]))), 30.0)
        self.assertTrue(np.allclose(s["zl"], 196.9))
        self.assertTrue(np.allclose(s["zr"], 188.58))  # (the line's own height: the survey's reading of the foot)

    def test_the_sides_follow_the_lines_direction(self):
        st = wl.of_lines([np.array([[0.0, 30.0, np.nan], [0.0, 0.0, np.nan]])], quay)  # (running south: its left is east)
        self.assertTrue(np.allclose(st[0]["zl"], 188.6) and np.allclose(st[0]["zr"], 196.9))

    def test_a_wall_on_level_ground_is_no_stretch(self):
        flat = lambda x, y: np.full(np.shape(x), 200.0)  # noqa: E731
        self.assertEqual(wl.of_lines([np.array([[0.0, 0.0, 201.5], [0.0, 30.0, 201.5]])], flat), [])
        kerb = lambda x, y: np.where(np.asarray(x) < 0, 200.15, 200.0)  # noqa: E731
        self.assertEqual(wl.of_lines([np.array([[0.0, 0.0, 200.0], [0.0, 30.0, 200.0]])], kerb), [])

    def test_a_wall_stepped_along_part_of_it_is_cut_to_that_part(self):
        def half(x, y):  # (a step south of y = 20 only)
            return np.where(np.asarray(y) < 20, quay(x, y), 196.9)
        st = wl.of_lines([np.array([[0.0, 0.0, np.nan], [0.0, 40.0, np.nan]])], half)
        self.assertEqual(len(st), 1)
        self.assertAlmostEqual(float(st[0]["p"][-1][1]), 19.0, delta=1.01)

    def test_the_high_side_reads_past_the_smear(self):
        """IPR spreads the step over 2 m and more: SIDE alone read the quay's top 0.5-2.7 m low in places."""
        wide = lambda x, y: quay(x, y, smear=2.2)  # noqa: E731
        s = wl.of_lines([np.array([[0.0, 0.0, np.nan], [0.0, 30.0, np.nan]])], wide)[0]
        self.assertTrue(np.allclose(s["zl"], 196.9) and np.allclose(s["zr"], 188.6))

    def test_a_kerb_in_the_readings_does_not_tilt_a_level_side(self):
        """The Modřany ramp's foot, line 17 (-2385, -9250): a sidewalk, its kerb 3.2 m from the wall and the road beyond.
        The line through those readings fell 10 % and, carried back to the wall, stood the sidewalk 0.3 m high there."""
        def street(x, y):  # (the wall at x = 0, the ramp's top to its west; east the sidewalk at 198.2, the road 0.15 lower)
            x = np.asarray(x, float)
            return np.where(x < 0, 204.0, np.where(x < 3.2, 198.2, 198.05))
        s = wl.of_lines([np.array([[0.0, 0.0, np.nan], [0.0, 30.0, np.nan]])], street)[0]
        self.assertTrue(np.allclose(s["gr"], 0.0))
        self.assertTrue(np.all(np.abs(s["zr"] - 198.2) <= 0.15))

    def test_terraces_narrower_than_the_smear_take_the_lines_own_heights(self):
        """Under Chotkova, line 23 (-896, 720): a wall's foot and top lines 0.15 m apart (208.6, 211.6), its inner face
        0.5 m behind, the next wall 2.75 m on (214.0); IPR's raster is one slope through them. Readings 2.5-4 m off a
        line lay on the next terraces, and the walls stood 1.5-2.5 m with a wavy top."""
        def slope(x, y):  # (level 208.6 west of the walls, one slope through them, level 214 past them)
            return np.interp(np.asarray(x, float), [-1.0, 4.4], [208.6, 214.0])

        def line(x, z):  # (running north: its left is west, downhill)
            return np.array([[x, 0.0, z], [x, 30.0, z]])
        st = wl.of_lines([line(0.0, 208.6), line(0.15, 211.6), line(0.65, 211.4), line(3.4, 214.0)], slope)
        self.assertEqual([round(float(s["p"][0][0]), 2) for s in st], [0.15, 3.4])  # (the foot's line and the inner face: no step)
        self.assertTrue(np.allclose(st[0]["zl"], 208.6) and np.allclose(st[0]["zr"], 211.4))
        self.assertTrue(np.allclose(st[1]["zl"], 211.4) and np.allclose(st[1]["zr"], 214.0))

    def test_a_side_that_is_a_slot_says_so(self):
        # (#770: a stairwell's two wall lines, surveyed at 271.18 m and 272.93 m, 0.6 m apart, on ground the raster has
        # level at 272.6 m: the strip between them takes the lower, a surveyed height under the ground on both sides,
        # and each stretch marks that side; the sides read from the raster carry no mark, and neither does the strip
        # between a terrace's foot line and top line, level with the lower ground)
        def line(x, z):
            return np.array([[x, 0.0, z], [x, 12.0, z]])
        st = wl.of_lines([line(0.0, 271.18), line(0.6, 272.93)], lambda x, y: np.full(np.shape(x), 272.6))
        self.assertEqual(len(st), 2)
        self.assertTrue(np.allclose(st[0]["zr"], 271.18) and st[0]["sr"].all() and "sl" not in st[0])
        self.assertTrue(np.allclose(st[1]["zl"], 271.18) and st[1]["sl"].all() and "sr" not in st[1])
        plain = wl.of_lines([np.array([[0.0, 0.0, 200.0], [0.0, 12.0, 200.0]])], lambda x, y: np.where(np.asarray(x) < 0, 200.0, 203.0))
        self.assertTrue("sl" not in plain[0] and "sr" not in plain[0])
        terrace = wl.of_lines([line(0.0, 208.6), line(0.6, 211.6)], lambda x, y: np.where(np.asarray(x) < 0.3, 208.6, 211.6))
        self.assertTrue(len(terrace) and all("sl" not in s and "sr" not in s for s in terrace))

    def test_a_sides_readings_stop_at_a_wall_areas_outline(self):
        """A survey wall area's outline bounds a terrace as a wall line does: the readings past it are another level's."""
        def two(x, y):  # (a step of 3 m at x = 0 and another at x = 2, each smeared over a metre)
            x = np.asarray(x, float)
            return 200.0 + 3.0 * np.clip(x + 0.5, 0, 1) + 3.0 * np.clip(x - 1.5, 0, 1)
        wall = np.array([[0.0, 0.0, 203.0], [0.0, 30.0, 203.0]])
        area = np.array([[2.0, -5.0, 203.0], [2.0, 35.0, 203.0], [2.6, 35.0, 206.0], [2.6, -5.0, 206.0], [2.0, -5.0, 203.0]])
        alone = wl.of_lines([wall], two)[0]
        self.assertTrue(np.all(alone["zr"] > 205.5))  # (read 2.5-4 m off: the level past the second wall)
        st = wl.of_lines([wall], two, [area])[0]
        self.assertTrue(np.allclose(st["zl"], 200.0) and np.allclose(st["zr"], 203.0))

    def test_a_stretch_is_cut_at_a_turn_and_a_jog_is_none(self):
        """The Modřany abutment's corner, line 17 (-2392.7, -9250.8): the wall's line jogs 0.5 m north, then runs east
        along the ramp. West of the jog the street lies at 198.3 m, south of the run a ledge at 200.5, north of it the
        ramp's top: the ground steps across the jog too, and the ramp's top was carried round it."""
        def ramp(x, y):
            x, y = np.asarray(x, float), np.asarray(y, float)
            return np.where((x >= 0) & (y > 0.5), 204.0, np.where(x > 0, 200.5, 198.3))
        line = np.array([[0.0, 0.0, np.nan], [0.0, 0.5, np.nan], [30.0, 0.5, np.nan]])
        st = wl.of_lines([line], ramp)
        self.assertEqual(len(st), 1)
        self.assertEqual(st[0]["p"][0].tolist(), [0.0, 0.5])  # (the run alone, from the corner: the jog is under PIECE)
        self.assertTrue(np.all(st[0]["zl"] == 204.0) and np.allclose(st[0]["zr"][3:], 200.5))
        # (a wall round a terrace's corner: two stretches, each read square to its own side)
        def terrace(x, y):
            x, y = np.asarray(x, float), np.asarray(y, float)
            return np.where((x >= 0) & (y >= 0), 203.0, 200.0)
        st = wl.of_lines([np.array([[0.0, 20.0, np.nan], [0.0, 0.0, np.nan], [20.0, 0.0, np.nan]])], terrace)
        self.assertEqual(len(st), 2)
        for s in st:
            self.assertTrue(np.allclose(s["zl"], 203.0) and np.allclose(s["zr"], 200.0), (s["zl"], s["zr"]))

    def test_the_piece_after_a_turn_does_not_read_along_the_wall_before_it(self):
        """A stairwell's corner by street-over-an-underpass, line 17 (-1446.6, -9111.2), #812: the wall runs east, turns
        right and runs south, the stairwell inside the turn (210.5 m), the street outside (215.3 m), the wall's top in
        the raster (216.8 m). Square to the second piece at the corner, its right side is read along the first piece's
        wall: its floor stood 216.76 m there, 210.50 m beside it."""
        def stairwell(x, y):
            x, y = np.asarray(x, float), np.asarray(y, float)
            wall = ((np.abs(y) < 0.4) & (x < 0.4)) | ((np.abs(x) < 0.4) & (y < 0.4))
            return np.where(wall, 216.8, np.where((x < 0) & (y < 0), 210.5, 215.3))
        st = wl.of_lines([np.array([[-20.0, 0.0, np.nan], [0.0, 0.0, np.nan], [0.0, -20.0, np.nan]])], stairwell)
        self.assertEqual(len(st), 2)
        for s in st:
            self.assertTrue(np.allclose(s["zl"], 215.3) and np.allclose(s["zr"], 210.5), (s["p"][0], s["zl"], s["zr"]))
        # (a run that starts on a turn of its line: the same, though the run and not a cut put the end there)
        S = wl.sample(np.array([[-20.0, 0.0, np.nan], [0.0, 0.0, np.nan], [0.0, -20.0, np.nan]]))
        d = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(S[:, :2], axis=0).T))])
        self.assertEqual(wl.straight(S, d, 20, 40), [(20, 40, True, False)])
        self.assertEqual(wl.straight(S, d, 0, 40), [(0, 20, False, True), (20, 40, True, False)])
        self.assertEqual(wl.straight(S, d, 0, 10), [(0, 10, False, False)])

    def test_a_line_meeting_walls_at_its_ends_reads_them_from_the_points_beside(self):
        # (an abutment's line between its wing walls, #763: at its ends the high side's readings run along a wing wall,
        # through the raster's smear of it)
        def ramp(x, y):
            x, y = np.asarray(x, float), np.asarray(y, float)
            top = np.where((y < 0.3) | (y > 9.7), 203.0, 206.0)
            return np.where(x > 0, top, 200.0)
        line = np.array([[0.0, 0.0, np.nan], [0.0, 10.0, np.nan]])
        self.assertEqual(wl.of_lines([line], ramp)[0]["zr"][[0, 5, -1]].tolist(), [203.0, 206.0, 203.0])
        self.assertEqual(wl.of_lines([line], ramp, (), {0})[0]["zr"][[0, 5, -1]].tolist(), [206.0, 206.0, 206.0])

    def test_a_wall_of_another_source_counts_where_the_survey_has_none_near(self):
        # (#765: Geoportál's retaining wall along x = 0; the survey has the same wall 0.4 m beside it for y 10-20)
        geo = [np.array([[0.0, 0.0, np.nan], [0.0, 30.0, np.nan]])]
        survey = [np.array([[0.4, 10.0, 205.0], [0.4, 20.0, 205.0]])]
        got = wl.off_survey(geo, survey)
        self.assertEqual(wl.HOLD, gm.WALL_HOLD)
        self.assertEqual([(q[0, 1], q[-1, 1]) for q in got], [(0.0, 8.0), (22.0, 30.0)])
        self.assertEqual([(q[0, 1], q[-1, 1]) for q in wl.off_survey(geo, [])], [(0.0, 30.0)])
        self.assertEqual(wl.off_survey(geo, [np.array([[0.4, 1.0, 205.0], [0.4, 29.0, 205.0]])]), [])  # (1 m ends: no run)

    def test_a_wall_known_by_its_height_stands_that_tall_under_a_bank_the_raster_has_no_step_in(self):
        # (#765: under Letná, line 17 (150, 806): the road level at 191.2 m, the raster rising 1 m per metre behind the
        # line, the wall 3.5 m by Geoportál)
        def bank(x, y):
            return 191.2 + np.clip(np.asarray(x, float), 0, 6)
        line = np.array([[0.0, 30.0, np.nan], [0.0, 0.0, np.nan]])  # (running south: its left is east, the bank)
        s = wl.of_lines([line], bank, (), (), {0: 3.5})[0]
        self.assertTrue(np.allclose(s["zr"], 191.2) and np.allclose(s["zl"], 194.7))
        self.assertTrue(np.allclose(s["zl"] + s["gl"] * wl.HOLD, 192.7))  # (the raster where the hold ends)
        low = wl.of_lines([line], lambda x, y: 191.2 + np.clip(np.asarray(x, float), 0, 6) / 3, (), (), {0: 3.5})[0]
        self.assertTrue(np.allclose(low["zl"], 192.53, atol=0.01))  # (no higher than the ground 4 m behind)
        self.assertEqual(wl.of_lines([line], lambda x, y: np.full(np.shape(x), 191.2), (), (), {0: 3.5}), [])  # (nothing held: no wall)

    def test_a_strips_outline_is_a_wall_line_at_the_edge_the_ground_steps_at(self):
        # (#770: the west wall of the cutting north of Ohrada, line 37 (3397, 3): a strip 0.3 m across at the top's
        # 248.2 m, the road behind it at 248.1, the track 4.7 m under it; the raster smears the step over 2 m)
        ring = np.array([[0.0, 0.0, 248.2], [0.0, 30.0, 248.2], [-0.3, 30.0, 248.2], [-0.3, 0.0, 248.2], [0.0, 0.0, 248.2]])
        st = wl.of_lines([ring], lambda x, y: quay(x, y, 248.1, 243.5), (), (), None, {0: "r"})
        self.assertEqual(len(st), 1)  # (the edge to the track alone: the road's side has no step)
        self.assertTrue(np.allclose(st[0]["p"][:, 0], 0.0) and st[0]["out"] == "r")
        self.assertTrue(np.allclose(st[0]["zr"], 243.5) and np.allclose(st[0]["zl"], 248.2))

    def test_a_strip_on_the_lidar_is_a_wall_line_along_its_low_side(self):
        # (#770: the east wall there, area 1818: 0.5 m across, no heights to go by)
        ring = np.array([[0.0, 0.0, 245.2], [0.5, 0.0, 247.2], [0.5, 30.0, 247.2], [0.0, 30.0, 245.2], [0.0, 0.0, 245.2]])
        low = wl.low_edges(ring, lambda x, y: quay(x, y, 243.5, 249.5, at=0.2))
        self.assertEqual(len(low), 1)
        self.assertTrue(np.allclose(low[0][:, 0], 0.0) and np.isnan(low[0][:, 2]).all())
        self.assertEqual(sorted([low[0][0, 1], low[0][-1, 1]]), [0.0, 30.0])
        self.assertEqual(wl.low_edges(ring, lambda x, y: np.full(np.shape(x), 245.0)), [])  # (a kerb's strip: no low side)

    def test_runs_close_small_gaps_and_drop_short_ones(self):
        d = np.arange(12.0)
        on = np.array([1, 1, 1, 0, 1, 1, 0, 0, 0, 0, 1, 0], bool)
        self.assertEqual(wl.runs(on, d), [(0, 5)])


class Hold(unittest.TestCase):
    WALL = [{"p": np.array([[0.0, 0.0], [0.0, 30.0]]), "zl": np.array([196.9, 196.9]), "zr": np.array([188.6, 188.6])}]

    def test_corners_on_and_beside_the_line_take_their_sides_level(self):
        #          on the line, twice     1 m west    1 m east    3 m west (past the hold)
        cx = np.array([0.0, 0.0, -1.0, 1.0, -3.0])
        cy = np.full(5, 10.0)
        tx = np.array([-0.5, 0.5, -1.2, 1.2, -3.2])  # (their triangles' centres)
        z = np.array([192.0, 192.0, 195.0, 190.0, 196.8])
        got, held = gm.hold_at_walls(cx, cy, tx, cy, z, np.ones(5, bool), self.WALL)
        self.assertEqual(got.tolist(), [196.9, 188.6, 196.9, 188.6, 196.8])
        self.assertEqual(held.tolist(), [True, True, True, True, False])

    def test_only_eligible_corners_move(self):
        cx, cy = np.array([0.0, 0.0]), np.array([10.0, 10.0])
        got, held = gm.hold_at_walls(cx, cy, np.array([-0.5, -0.5]), cy, np.array([192.0, 192.0]), np.array([True, False]), self.WALL)
        self.assertEqual(got.tolist(), [196.9, 192.0])
        self.assertEqual(gm.hold_at_walls(cx, cy, cx, cy, np.array([1.0, 2.0]), np.ones(2, bool), [])[0].tolist(), [1.0, 2.0])

    def test_the_level_runs_along_a_sloping_wall(self):
        wall = [{"p": np.array([[0.0, 0.0], [0.0, 10.0]]), "zl": np.array([200.0, 202.0]), "zr": np.array([195.0, 195.0])}]
        got, _ = gm.hold_at_walls(np.array([-0.5]), np.array([2.5]), np.array([-0.6]), np.array([2.5]), np.array([0.0]), np.ones(1, bool), wall)
        self.assertAlmostEqual(float(got[0]), 200.5)

    def test_a_bank_behind_a_low_wall_keeps_its_slope_to_the_wall(self):
        """Chotkova, line 23 (-887, 721): a 1 m wall under a lawn rising 0.8 m a metre was drawn 4-7 m."""
        def bank(x, y):  # (the wall at x = 0: the road level at 199 to its east, the lawn from 200 rising westwards)
            x = np.asarray(x, float)
            return np.where(x > 0, 199.0, 200.0 + 0.8 * np.abs(x))
        s = wl.of_lines([np.array([[0.0, 0.0, np.nan], [0.0, 30.0, np.nan]])], bank)[0]
        self.assertTrue(np.allclose(s["zl"], 200.0) and np.allclose(s["gl"], 0.8))
        self.assertTrue(np.allclose(s["zr"], 199.0) and np.allclose(s["gr"], 0.0))
        got, _ = gm.hold_at_walls(np.array([0.0, -1.0, 1.0]), np.full(3, 10.0), np.array([-0.3, -1.2, 1.2]), np.full(3, 10.0),
                                  np.zeros(3), np.ones(3, bool), [s])
        self.assertTrue(np.allclose(got, [200.0, 200.8, 199.0]))

    def test_a_corner_past_a_stretchs_end_is_left(self):
        cx, cy = np.array([0.0, -0.5, -0.5]), np.array([31.0, -1.0, 15.0])
        got, held = gm.hold_at_walls(cx, cy, cx - 0.2, cy, np.full(3, 192.0), np.ones(3, bool), self.WALL)
        self.assertEqual(held.tolist(), [False, False, True])
        self.assertEqual(got.tolist(), [192.0, 192.0, 196.9])


if __name__ == "__main__":
    unittest.main(verbosity=1)
