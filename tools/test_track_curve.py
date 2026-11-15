# SPDX-License-Identifier: AGPL-3.0-or-later
"""The drawn track as smooth curves (#204): python -P -E tools/test_track_curve.py."""
import math
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import track_curve as tc


def off(p, pts):
    """Distance of p to the polyline pts."""
    best = math.inf
    for a, b in zip(pts, pts[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy or 1e-12)))
        best = min(best, math.dist(p, (a[0] + t * dx, a[1] + t * dy)))
    return best


def heading(pts, at_start=True, d=1.0):
    """The direction of a polyline at an end, over its first d metres."""
    p = pts if at_start else pts[::-1]
    q = next(q for q in p if math.dist(q, p[0]) >= d)
    return math.atan2(q[1] - p[0][1], q[0] - p[0][0])


def arc(cx, cy, r, a0, a1, step):
    n = max(1, round(abs(a1 - a0) * r / step))
    return [(cx + r * math.cos(a0 + (a1 - a0) * k / n), cy + r * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]


class Fit(unittest.TestCase):
    def test_a_noisy_straight_comes_out_straight(self):
        # "even straight direction isn't really straight" (the user, 2026-11-03): DI's points scatter a centimetre
        random.seed(1)
        pts = [(x, random.uniform(-0.01, 0.01)) for x in range(0, 101, 2)]
        samples, at, tol, rad = tc.fit(pts, [tc.TOL] * len(pts))
        self.assertLess(max(abs(y) for _, y in samples), 0.006)
        self.assertGreater(min(rad), 2000)

    def test_a_curve_stays_on_its_points_and_does_not_cut_inside(self):
        # a 25 m curve between straights, points 3 m apart: within 2 cm of the arc (a 6 m Gaussian cut 0.2 m off an
        # 18 m one, #20)
        r = 25
        pts = [(-30 + 3 * i, 0.0) for i in range(10)] + arc(0, r, r, -math.pi / 2, 0, 3)[1:] + [(r, r + 3 * i) for i in range(1, 10)]
        samples, at, tol, rad = tc.fit(pts, [tc.TOL] * len(pts))
        self.assertLess(max(off(p, samples) for p in pts), tc.TOL + 0.002)
        mid = [q for q in samples if q[0] > 3 and q[1] < r - 3]
        self.assertLess(max(abs(math.dist(q, (0, r)) - r) for q in mid), 0.03)
        self.assertGreater(min(rad), 0.9 * r)

    def test_a_corner_is_eased_within_the_class_error(self):
        # a 10° corner at one point among points 0.5 m apart: within 2 cm it would bend at 5 m over a metre (a 5 m
        # window reads that as 29 m: the fit also measures over BEND); DI's class 3 lets its points move 0.14 m
        pts = [(x / 2, 0.0) for x in range(0, 61)] + [(30 + x / 2 * math.cos(math.radians(10)), x / 2 * math.sin(math.radians(10))) for x in range(1, 61)]
        errors = tc.class_errors()
        samples, at, tol, rad = tc.fit(pts, [tc.TOL] * len(pts), limit=[errors['3']] * len(pts))
        self.assertGreater(min(rad), tc.MIN_RADIUS * tc.SLACK)
        self.assertTrue(any(t > tc.TOL for t in tol))
        self.assertLessEqual(max(tol), errors['3'] + 1e-9)

    def test_a_curve_under_18_m_moves_past_its_class(self):
        # a 30° corner: within class 1 it bends under 18 m (`min-radius-network`, the user: "under 18m there
        # shouldn't be anything like that"), so its points move further, at most HOLD_LIMIT
        pts = [(x / 2, 0.0) for x in range(0, 61)] + [(30 + x / 2 * math.cos(math.radians(30)), x / 2 * math.sin(math.radians(30))) for x in range(1, 61)]
        errors = tc.class_errors()
        samples, at, tol, rad = tc.fit(pts, [tc.TOL] * len(pts), limit=[errors['1']] * len(pts))
        self.assertGreater(min(rad), tc.NETWORK_RADIUS * tc.SLACK)
        self.assertGreater(max(tol), errors['1'])
        self.assertLessEqual(max(tol), tc.HOLD_LIMIT + 1e-9)


    def test_a_branch_held_tangent_eases_off_without_a_corner(self):
        # line 9 s 15958, a trailing switch past Flora: DI's branch, its first 11 m from the switch (relative to it), held
        # tangent to the straight (`switch-start`). Held to 2 cm it turned 4.5° at the held sample a metre out (12.5 m
        # over its own two metres), a corner the windows near the end read as 18.9 m
        pts = [(0.0, 0.0), (-0.105, 1.985), (-0.145, 2.355), (-0.175, 2.735), (-0.205, 3.105), (-0.235, 3.475),
               (-0.255, 3.855), (-0.275, 4.225), (-0.295, 4.605), (-0.305, 4.975), (-0.315, 5.355), (-0.325, 5.725),
               (-0.335, 6.105), (-0.335, 6.475), (-0.335, 6.855), (-0.325, 7.225), (-0.325, 7.605), (-0.315, 7.975),
               (-0.295, 8.235), (-0.275, 8.495), (-0.255, 8.755), (-0.225, 9.015), (-0.195, 9.275), (-0.165, 9.535),
               (-0.125, 9.795), (-0.085, 10.045), (-0.045, 10.305), (0.005, 10.565), (0.045, 10.815), (0.105, 11.075)]
        straight = (-0.10756377715724001, 0.994198186401317)
        errors = tc.class_errors()
        samples, at, tol, rad = tc.fit(pts, [tc.TOL] * len(pts), fixed={0: pts[0]}, heading={0: straight},
                                       limit=[errors['3']] * len(pts))
        lead = (samples[1][0] - samples[0][0], samples[1][1] - samples[0][1])
        self.assertLess(abs(lead[0] * straight[1] - lead[1] * straight[0]) / math.hypot(*lead), 1e-4)   # leaves along it
        px, py = [q[0] for q in samples], [q[1] for q in samples]
        self.assertLessEqual(tc.corner_excess(px, py, 1, 1), tc.CORNER + 1e-6)   # no corner where the points begin
        turn = [abs(math.degrees(heading(samples[i:], d=1.0) - heading(samples[i + 1:], d=1.0))) for i in range(4)]
        self.assertLess(max(turn), 1.5)
        self.assertLessEqual(max(tol), errors['3'] + 1e-9)

    def test_a_switch_curving_from_its_blade_keeps_its_curve(self):
        # (Národní divadlo: a branch curving at 20 m from the switch is no corner; a limit on the radius at the held sample
        # pushed its turn into a 13 m bend further on, #477)
        r = 20.0
        pts = [(r * math.sin(a / 100), r * (1 - math.cos(a / 100))) for a in range(0, 101, 2)]
        samples, at, tol, rad = tc.fit(pts, [tc.TOL] * len(pts), fixed={0: pts[0]}, heading={0: (1.0, 0.0)},
                                       limit=[tc.class_errors()['3']] * len(pts))
        self.assertGreater(min(rad[2:-3]), tc.MIN_RADIUS * tc.SLACK)
        self.assertLess(max(off(p, samples) for p in pts), tc.TOL + 0.005)


class Network(unittest.TestCase):
    def test_a_diverging_track_leaves_tangent_to_the_through_track(self):
        # the branch's points run straight 4° off the through track from the switch node
        through = [(x, 0.0) for x in range(0, 101, 2)]
        branch = [(50 + d * math.cos(math.radians(4)), d * math.sin(math.radians(4))) for d in range(0, 41, 2)]
        pos = {1: (0, 0), 2: (50, 0), 3: (100, 0), 4: branch[-1]}
        pts = {(1, 2): through[:26], (2, 3): through[25:], (2, 4): branch}
        net = tc.Network(pos, pts, {(1, 2): 'di', (2, 3): 'di', (2, 4): 'di'})
        out = net.pts[(2, 4)]
        self.assertLess(abs(math.degrees(math.atan2(out[1][1] - out[0][1], out[1][0] - out[0][0]))), 1.0)
        self.assertGreater(math.degrees(heading(out[::-1], d=10.0)) % 180, 3.5)
        self.assertLess(math.dist(net.pos[2], (50, 0)), tc.TOL + 0.005)

    def test_the_straight_continues_through_a_switch_whose_branch_starts_tangent(self):
        # Strossmayerovo náměstí: DI bends the straight 0.9° at the switch, and over 3 m the branch (here R 150 m,
        # 0.57° off) reads straighter than it; over PAIR_LOOK the straight continues, within 2 cm of its points
        south = [(-50 + 2 * k, 0.0) for k in range(26)]
        north = [(x * math.cos(math.radians(0.9)), x * math.sin(math.radians(0.9))) for x in range(0, 51, 2)]
        branch = [(150 * math.sin(k / 20 * 0.2), -150 * (1 - math.cos(k / 20 * 0.2))) for k in range(21)]
        pos = {1: south[0], 2: (0.0, 0.0), 3: north[-1], 4: branch[-1]}
        net = tc.Network(pos, {(1, 2): south, (2, 3): north, (2, 4): branch}, {(1, 2): 'di', (2, 3): 'di', (2, 4): 'di'})
        straight = net.pts[(1, 2)] + net.pts[(2, 3)][1:]
        self.assertLess(max(off(p, straight) for p in south + north), tc.TOL + 0.005)
        h_in = heading(net.pts[(1, 2)], at_start=False) + math.pi
        h_out = heading(net.pts[(2, 3)])
        self.assertLess(abs(math.degrees(h_out - h_in)), 0.5)

    def test_an_interlaced_tip_is_a_y_both_tracks_leaving_the_approach(self):
        # (Čechův most, #368: the approach on the axis to the tip, the two tracks +4.7 and -8.7 cm off it from 7 m on; no
        # points between, DI's tongue chord. A Y: neither continues the approach, both leave along it)
        appr = [(x, 0.0) for x in range(-50, 1, 2)]
        up = [(0.0, 0.0)] + [(x, 0.047) for x in range(7, 51, 2)]
        down = [(0.0, 0.0)] + [(x, -0.087) for x in range(7, 51, 2)]
        pos = {1: appr[0], 2: (0.0, 0.0), 3: up[-1], 4: down[-1]}
        net = tc.Network(pos, {(1, 2): appr, (2, 3): up, (2, 4): down}, {(1, 2): 'di', (2, 3): 'di', (2, 4): 'di'},
                         approach={2: 1})
        self.assertLess(max(abs(y) for x, y in net.pts[(1, 2)]), 0.005)   # (the approach stays on its axis)
        for key, side in (((2, 3), 1), ((2, 4), -1)):
            out = net.pts[key]
            self.assertLess(abs(math.degrees(heading(out))), 0.3)          # (leaves along the approach)
            self.assertGreater(side * out[len(out) // 2][1], 0.03)        # (and off to its own side)
            turn = [abs(math.degrees(heading(out[i:], d=1.0) - heading(out[i + 1:], d=1.0))) for i in range(len(out) - 3)]
            self.assertLess(max(turn), 0.5)                                # (smoothly: no bend over 0.5 degree a metre)

    def test_where_the_order_deadlocks_the_end_fitted_first_takes_the_heading_of_the_track_through_it(self):
        # (line 37 s 3700, a facing switch) the branch leaves the straight at node 2 3° off and passes through node 3, where
        # the straight ends coming in at 10°: each passes through the other's end. The longer branch was fitted first, its
        # end at 2 free, and it left at 2.2° where the straight passed through later
        a, c = math.tan(math.radians(10)) / 3600, math.tan(math.radians(3)) / 3600
        west = [(x, 0.0) for x in range(-50, 1, 2)]
        straight = [(x, a * x * x * (x - 60)) for x in range(0, 61, 2)]
        b1 = [(x, c * x * (60 - x) ** 2) for x in range(0, 31, 2)]
        b2 = [(x, c * x * (60 - x) ** 2) for x in range(30, 61, 2)]
        east = [(x, 0.0) for x in range(60, 201, 2)]
        pos = {1: west[0], 2: (0.0, 0.0), 3: (60.0, 0.0), 4: east[-1], 5: b1[-1]}
        edges = {(1, 2): west, (2, 3): straight, (2, 5): b1, (3, 5): b2[::-1], (3, 4): east}
        net = tc.Network(pos, edges, {e: 'di' for e in edges})
        self.assertEqual(net.report['refitted'], 1)
        self.assertLess(abs(math.degrees(heading(net.pts[(2, 5)], d=1.0))), 1.0)

    def test_a_branch_starting_at_its_own_angle_keeps_it(self):
        # beyond START the branch leaves at its own angle (data/truth.json `switch-start`: some designs start abruptly)
        through = [(x, 0.0) for x in range(0, 101, 2)]
        branch = [(50 + d * math.cos(math.radians(15)), d * math.sin(math.radians(15))) for d in range(0, 41, 2)]
        pos = {1: (0, 0), 2: (50, 0), 3: (100, 0), 4: branch[-1]}
        pts = {(1, 2): through[:26], (2, 3): through[25:], (2, 4): branch}
        net = tc.Network(pos, pts, {(1, 2): 'di', (2, 3): 'di', (2, 4): 'di'})
        self.assertGreater(math.degrees(heading(net.pts[(2, 4)], d=3.0)), 13)
        self.assertLess(max(off(p, net.pts[(2, 4)]) for p in branch[1:]), tc.TOL + 0.005)

    def test_the_through_track_does_not_break_at_a_node(self):
        # a record joint on a 40 m curve: one through track, the same direction either side of the node
        a = arc(0, 40, 40, -math.pi / 2, -math.pi / 2 + 0.6, 1.5)
        mid = len(a) // 2
        pos = {1: a[0], 2: a[mid], 3: a[-1]}
        net = tc.Network(pos, {(1, 2): a[:mid + 1], (2, 3): a[mid:]}, {(1, 2): 'di', (2, 3): 'di'})
        h_in = heading(net.pts[(1, 2)], at_start=False) + math.pi
        h_out = heading(net.pts[(2, 3)])
        self.assertLess(abs(math.degrees((h_out - h_in + math.pi) % (2 * math.pi) - math.pi)), 3.0)

    def test_a_crossing_node_lies_on_both_curves(self):
        # the node 0.3 m off the long track and 0.13 m off the other (the point nearest all its tracks): the tracks
        # cross at their own point
        long = [(x, 0.0) for x in range(-60, 61, 2)]
        cross = [(0.3 + 0.5 * t, t) for t in range(-20, 21, 2)]
        pos = {1: (-60, 0), 2: (0.3, 0.3), 3: (60, 0), 4: cross[0], 5: cross[-1]}
        pts = {(1, 2): long[:30] + [(0.3, 0.3)], (2, 3): [(0.3, 0.3)] + long[31:], (2, 4): [(0.3, 0.3)] + cross[:10][::-1],
               (2, 5): [(0.3, 0.3)] + cross[11:]}
        kind = {e: 'di' for e in pts}
        net = tc.Network(pos, pts, kind, loose={(2, e) for e in pts})
        # both tracks' edges end where they cross (each keeps its own point at a node off its line)
        for e in pts:
            q = net.pts[e][0] if e[0] == 2 else net.pts[e][-1]
            self.assertLess(abs(q[1]), tc.TOL + 0.005)
            self.assertLess(off(q, cross), tc.TOL + 0.005)

    def test_a_turning_loop_comes_back_onto_its_switch(self):
        # Dvorce: the track runs through the switch, round a 13 m loop and back into the same switch; the loop's end
        # was free, and with the points eased for the tight loop it landed off the switch (a 13° kink here)
        random.seed(4)
        loop = [(x + random.uniform(-0.03, 0.03), y + random.uniform(-0.03, 0.03))
                for x, y in arc(5, 12, 13, math.atan2(-12, 5), math.atan2(-12, -5) + 2 * math.pi, 0.5)]
        loop[0], loop[-1] = (10, 0), (0, 0)
        line = [(x, 0.0) for x in range(-60, 11, 2)]
        m = len(loop) // 2
        pos = {1: (-60, 0), 2: (0, 0), 3: (10, 0), 4: loop[m]}
        pts = {(1, 2): line[:31], (2, 3): line[30:], (3, 4): loop[:m + 1], (2, 4): loop[m:][::-1]}
        net = tc.Network(pos, pts, {e: 'di' for e in pts})
        end = net.pts[(2, 4)]
        self.assertLess(math.dist(end[0], net.pos[2]), 0.001)
        u, v = (end[1][0] - end[0][0], end[1][1] - end[0][1]), (end[2][0] - end[1][0], end[2][1] - end[1][1])
        self.assertLess(abs(math.degrees(math.atan2(u[0] * v[1] - u[1] * v[0], u[0] * v[0] + u[1] * v[1]))), 3)

    def test_nodes_a_few_centimetres_apart_are_one(self):
        line = [(x, 0.0) for x in range(0, 41, 2)]
        pos = {1: (0, 0), 2: (20, 0), 3: (20.04, 0), 4: (40, 0)}
        pts = {(1, 2): line[:11], (2, 3): [(20, 0), (20.04, 0)], (3, 4): [(20.04, 0)] + line[11:]}
        net = tc.Network(pos, pts, {e: 'di' for e in pts})
        self.assertEqual(net.pos[2], net.pos[3])


class Misses(unittest.TestCase):
    def test_misses_at_once_as_nearest(self):
        """misses (numpy picks, math.hypot measures, #517) gives nearest's distance to its last bit: curves with repeated
        points, ties, zero-length segments and windows cut by the ends."""
        rng = random.Random(3)
        for trial in range(40):
            n = rng.choice([2, 3, 5, 40, 300])
            px = [rng.uniform(-50, 50) for _ in range(n)]
            py = [rng.uniform(-50, 50) * (trial % 3) for _ in range(n)]
            if n > 3:
                px[2], py[2] = px[1], py[1]  # (a zero-length segment)
            xs = [x + rng.choice([0.0, 0.1, -1e-9]) for x in px]
            ys = [y + rng.choice([0.0, 0.2]) for y in py]
            ss = list(range(n))
            self.assertEqual(tc.misses(px, py, xs, ys, ss), [tc.nearest(px, py, s - 3, s + 3, (xs[s], ys[s]))[0] for s in ss])
        self.assertEqual(tc.misses([0.0, 1.0], [0.0, 0.0], [0.5], [1.0], []), [])


if __name__ == '__main__':
    unittest.main()
