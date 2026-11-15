# SPDX-License-Identifier: AGPL-3.0-or-later
"""Turning loops by the user's rule (tools/track_loops.py, #211): python -P -E tools/test_track_loops.py."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import di_network as dn  # noqa: E402
import di_tracks as dt  # noqa: E402
import track_loops as tl  # noqa: E402

dn.SMOOTHED = []  # (made-up networks: none of the user's answers in data/truth.json applies to them)


def rec(i, pts):
    return {'id': str(i), 'coords': [(x, y, None) for x, y in pts], 'attrs': {}, 'sources': []}


def net_of(*chains):
    return dn.Network(dt.Source('di', [rec(i, p) for i, p in enumerate(chains)]))


def bezier(p0, c0, c1, p1, n=80):
    out = []
    for k in range(n + 1):
        t = k / n
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
        out.append((a * p0[0] + b * c0[0] + c * c1[0] + d * p1[0], a * p0[1] + b * c0[1] + c * c1[1] + d * p1[1]))
    return out


def terminus(spread=3.5, reach=120.0):
    """A double track ending in a loop: the arrival track (y = +spread/2, eastbound) leaves at a switch at x = -60, swings
    out east and comes back on the departure track's switch; both tracks run on a little past their switches."""
    y = spread / 2
    h = math.radians(8)
    loop = bezier((-60, y), (-60 + reach * math.cos(h), y + reach * math.sin(h)),
                  (-60 + reach * math.cos(h), -y - reach * math.sin(h)), (-60, -y))
    return net_of([(-300, y), (-60, y)], [(-60, y), (0, y)], loop, [(-300, -y), (-60, -y)], [(-60, -y), (0, -y)])


class Loops(unittest.TestCase):
    def test_a_terminus_loop_is_found_from_switch_to_switch(self):
        net = terminus()
        loops = tl.find(net, radius=18)
        self.assertTrue(loops)
        best = min(loops, key=lambda c: c['len'])
        self.assertAlmostEqual(abs(best['turn']), 180, delta=3)
        self.assertLess(best['neck'], 4)
        self.assertEqual(len(best['path']), 1)

    def test_a_circuit_round_a_block_is_not_a_loop(self):
        # out at a switch, round a 100 x 200 m block, back on the other track 200 m on: turns 180°, but its switches lie
        # 200 m apart
        y = 1.75
        block = [(0, y), (10, y + 1.4), (20, y + 5), (27, y + 12), (30, y + 25), (30, 75), (33, 88), (40, 95), (55, 100),
                 (205, 100), (220, 95), (227, 88), (230, 75), (230, -y + 25), (227, -y + 12), (220, -y + 5), (210, -y + 1.4), (200, -y)]
        net = net_of([(-300, y), (0, y)], [(0, y), (400, y)], block, [(-300, -y), (200, -y)], [(200, -y), (400, -y)])
        cands = tl.candidates(net)
        self.assertTrue(any(abs(abs(c['turn']) - 180) < 10 for c in cands))
        self.assertEqual(tl.find(net, radius=18), [])
        self.assertTrue(all('from its start' in (tl.why_not(c, radius=18) or 'from its start') for c in cands))

    def test_a_turn_too_tight_for_a_tram_is_a_drawing(self):
        c = {'turn': 276.0, 'len': 52.0, 'neck': 45.0}
        self.assertIn('mean radius', tl.why_not(c, radius=18))
        self.assertIsNone(tl.why_not({**c, 'len': 100.0}, radius=18))

    def test_the_turn_counts_from_street_to_street(self):
        # from the switch's leg it would fall short by the switch's angle (Divoká Šárka 173°)
        self.assertIsNone(tl.why_not({'turn': -172.0, 'len': 200.0, 'neck': 87.0}, radius=18))
        self.assertIn('turns', tl.why_not({'turn': 160.0, 'len': 200.0, 'neck': 10.0}, radius=18))


class OnRoute(unittest.TestCase):
    LOOP = [{'path': [(1, 1), (2, 1), (3, -1)]}]

    @staticmethod
    def route(*edges):
        pieces = [(e, d, 0.0, 10.0) if e != 'off' else ('off', [(0, 0), (10, 0)]) for e, d in edges]
        return pieces, [10.0 * (i + 1) for i in range(len(edges))]

    def test_a_route_through_the_whole_loop(self):
        p, e = self.route((9, 1), (1, 1), (2, 1), (3, -1), (8, 1))
        self.assertEqual(tl.on_route(p, e, self.LOOP), [{'from': 10.0, 'to': 40.0}])

    def test_a_route_over_part_of_it_is_not_in_it(self):
        # a through route sharing one street of a circuit
        p, e = self.route((9, 1), (1, 1), (2, 1), (7, 1))
        self.assertEqual(tl.on_route(p, e, self.LOOP), [])
        p, e = self.route((9, 1), (2, 1), (3, -1), (8, 1))
        self.assertEqual(tl.on_route(p, e, self.LOOP), [])

    def test_a_route_starting_or_ending_in_it(self):
        p, e = self.route((2, 1), (3, -1), (8, 1))
        self.assertEqual(tl.on_route(p, e, self.LOOP), [{'from': 0.0, 'to': 20.0}])
        p, e = self.route((9, 1), (1, 1), (2, 1))
        self.assertEqual(tl.on_route(p, e, self.LOOP), [{'from': 10.0, 'to': 30.0}])

    def test_the_other_way_round_is_not_the_loop(self):
        p, e = self.route((9, 1), (3, 1), (2, -1), (1, -1), (8, 1))
        self.assertEqual(tl.on_route(p, e, self.LOOP), [])

    def test_a_route_off_the_network_ends_its_run(self):
        # (an 'off' piece between: the route's part on OSM's own track is not the loop's path)
        p, e = self.route((9, 1), (1, 1), ('off', None), (2, 1), (3, -1), (8, 1))
        self.assertEqual(tl.on_route(p, e, self.LOOP), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
