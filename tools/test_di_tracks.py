"""Track geometry from DI (#20): python -P -E tools/test_di_tracks.py."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import di_tracks as dt


def rec(i, pts):
    return {'id': str(i), 'coords': [(x, y, None) for x, y in pts], 'attrs': {}, 'sources': []}


def arc(cx, cy, r, a0, a1, n=40):
    return [(cx + r * math.cos(a0 + (a1 - a0) * k / n), cy + r * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]


def off_line(p, pts):
    """Distance of p to the polyline pts."""
    best = math.inf
    for a, b in zip(pts, pts[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        l2 = dx * dx + dy * dy or 1e-9
        t = max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
        best = min(best, math.dist(p, (a[0] + dx * t, a[1] + dy * t)))
    return best


class Matching(unittest.TestCase):
    def test_a_curve_drawn_as_a_chord_takes_the_di_curve(self):
        curve = arc(0, 0, 50, 0, math.pi / 6)
        di = dt.Source('di', [rec(1, [(-40, 0)] + [(50, 0)][:0] + curve)])
        # OSM: the curve's two ends, 0.5 m off, as one straight edge (sagitta 1.7 m)
        pos = {1: (curve[0][0] + 0.5, curve[0][1]), 2: (curve[-1][0] + 0.4, curve[-1][1] + 0.3)}
        geo = dt.TrackGeometry(pos, [(1, 2)], [di])
        pts = geo.points(1, 2)
        self.assertGreater(len(pts), 20)
        self.assertLess(max(off_line(p, curve) for p in pts), 0.01)
        self.assertEqual(geo.source(1, 2)['src'], 'di')
        self.assertEqual(geo.source(1, 2)['records'], ['1'])

    def test_each_track_of_a_double_track_keeps_its_own(self):
        # OSM draws the pair 2.5 m apart (Kobylisy), DI 3.5 m: each way still finds its own track
        di = dt.Source('di', [rec(1, [(0, 0), (100, 0)]), rec(2, [(0, 3.5), (100, 3.5)])])
        pos = {1: (0, 0.5), 2: (100, 0.5), 3: (0, 3.0), 4: (100, 3.0)}
        geo = dt.TrackGeometry(pos, [(1, 2), (3, 4)], [di])
        self.assertAlmostEqual(geo.at(1)[1], 0, places=6)
        self.assertAlmostEqual(geo.at(3)[1], 3.5, places=6)
        self.assertAlmostEqual(math.dist(geo.at(2), geo.at(4)), 3.5, places=6)

    def test_near_a_fork_the_edge_stays_on_one_track(self):
        # through track and a branch leaving it at the fork: right after it both lie within centimetres
        branch = [(50, 0)] + [(50 + 5 * k, 0.02 * k * k) for k in range(1, 11)]
        di = dt.Source('di', [rec(1, [(0, 0), (50, 0)]), rec(2, [(50, 0), (100, 0)]), rec(3, branch)])
        pos = {1: (0, 0.3), 2: (100, 0.3)}
        geo = dt.TrackGeometry(pos, [(1, 2)], [di])
        self.assertEqual(geo.source(1, 2)['src'], 'di')
        self.assertLess(max(abs(p[1]) for p in geo.points(1, 2)), 1e-6)

    def test_a_chord_between_both_tracks_takes_the_track_its_neighbours_are_on(self):
        # Křižovnická: a 60 m OSM edge cuts between the two tracks, 1-2 m from each
        a = arc(0, -100, 100, math.radians(80), math.radians(120), 60)
        b = arc(0, -100, 96.5, math.radians(80), math.radians(120), 60)
        di = dt.Source('di', [rec(1, a), rec(2, b)])
        # neighbours on track a at both ends; the middle edge a chord 2.7 m inside a, 0.8 m from b
        p0, p1, p2, p3 = a[0], a[10], a[50], a[60]
        mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        self.assertGreater(off_line(mid, a), 2.5)
        self.assertLess(off_line(mid, b), 1.0)
        geo = dt.TrackGeometry({1: p0, 2: p1, 3: p2, 4: p3}, [(1, 2), (2, 3), (3, 4)], [di])
        self.assertLess(max(off_line(p, a) for p in geo.points(2, 3)), 0.01)

    def test_the_archive_fills_where_di_has_no_track_and_osm_where_neither_has(self):
        di = dt.Source('di', [rec(1, [(0, 0), (100, 0)])])
        archive = dt.Source('dtmp', [rec(9, [(100, 0), (200, 0)])])
        pos = {1: (0, 0.5), 2: (100, 0.5), 3: (200, 0.5), 4: (300, 0.5)}
        geo = dt.TrackGeometry(pos, [(1, 2), (2, 3), (3, 4)], [di, archive])
        self.assertEqual([geo.source(*e)['src'] for e in [(1, 2), (2, 3), (3, 4)]], ['di', 'dtmp', 'osm'])
        self.assertEqual(geo.at(4), (300, 0.5))  # 100 m from the last match: beyond BLEND, OSM's own position

    def test_an_osm_fill_stretch_takes_up_its_neighbours_shift(self):
        di = dt.Source('di', [rec(1, [(0, 0), (100, 0)])])
        pos = {1: (0, 1.0), 2: (100, 1.0), 3: (110, 1.0), 4: (200, 1.0)}
        geo = dt.TrackGeometry(pos, [(1, 2), (2, 3), (3, 4)], [di])
        self.assertAlmostEqual(geo.at(2)[1], 0, places=6)
        self.assertAlmostEqual(geo.at(3)[1], 1.0 - 1.0 * (1 - 10 / dt.BLEND), places=6)  # half the shift at 10 m
        self.assertEqual(geo.at(4), (200, 1.0))

    def test_a_fork_moves_only_the_nearest_switch(self):
        # Palackého náměstí: two OSM switches 4-5 m apart near one DI fork
        di = dt.Source('di', [rec(1, [(0, 0), (50, 0)]), rec(2, [(50, 0), (100, 0)]), rec(3, [(50, 0), (90, 8)]),
                              rec(4, [(54, 0), (54, -1)])][:3])
        pos = {1: (0, 0.2), 2: (52.0, 0.2), 3: (56.5, 0.2), 4: (100, 0.2), 5: (90, 8.2), 6: (95, -6)}
        edges = [(1, 2), (2, 3), (3, 4), (2, 5), (3, 6)]
        geo = dt.TrackGeometry(pos, edges, [di])
        self.assertEqual(geo.at(2), (50.0, 0.0))
        self.assertNotEqual(geo.at(3), (50.0, 0.0))
        self.assertGreater(math.dist(geo.at(2), geo.at(3)), 4)

    def test_a_crossing_node_lands_where_the_tracks_cross(self):
        # Dlouhá třída: projected on the other track the node lay 0.5 m off ours
        di = dt.Source('di', [rec(1, [(0, 0), (100, 0)]), rec(2, [(50, -50), (50.5, 50)])])
        pos = {1: (0, 0.3), 2: (49.6, 0.4), 3: (100, 0.3), 4: (50.0, -50), 5: (50.4, 50)}
        geo = dt.TrackGeometry(pos, [(1, 2), (2, 3), (4, 2), (2, 5)], [di])
        x, y = geo.at(2)
        self.assertAlmostEqual(y, 0, places=3)
        self.assertAlmostEqual(x, 50.25, places=2)

    def test_a_switch_never_takes_the_other_tracks_fork_or_one_behind_its_neighbour(self):
        # a crossover: a fork on each track, 3.5 m apart; OSM's switch on track y=0 is nearer the other one
        di = dt.Source('di', [rec(1, [(0, 0), (60, 0)]), rec(2, [(60, 0), (120, 0)]),
                              rec(3, [(0, 3.5), (55, 3.5)]), rec(4, [(55, 3.5), (120, 3.5)]),
                              rec(5, [(60, 0), (55, 3.5)])])
        pos = {1: (0, 0.2), 2: (56.0, 0.6), 3: (120, 0.2), 4: (52.0, 3.2)}
        geo = dt.TrackGeometry(pos, [(1, 2), (2, 3), (2, 4)], [di])
        self.assertLess(abs(geo.at(2)[1]), 0.01)            # stays on its own track
        # a fork behind the previous node, a junction: the node keeps its own place (Holešovice: moving it turned
        # the route back)
        di2 = dt.Source('di', [rec(1, [(0, 0), (40, 0)]), rec(2, [(40, 0), (100, 0)]), rec(3, [(40, 0), (80, 10)]),
                               rec(4, [(41, 0), (41, -30)])])
        pos2 = {1: (0, 0.2), 2: (41.0, 0.2), 3: (44.0, 0.2), 4: (100, 0.2), 5: (80, 10.2), 6: (41, -30)}
        geo2 = dt.TrackGeometry(pos2, [(1, 2), (2, 3), (3, 4), (3, 5), (2, 6)], [di2])
        self.assertGreater(geo2.at(3)[0], geo2.at(2)[0] + 2)
        self.assertEqual(geo2.report['reversed_edges'], 0)

    def test_a_node_between_the_switch_and_its_fork_moves_with_it(self):
        # Křižovnická: OSM's node 0.5 m from the switch lies at the fork, 5 m on; both take the fork
        di = dt.Source('di', [rec(1, [(0, 0), (40, 0)]), rec(2, [(40, 0), (100, 0)]), rec(3, [(40, 0), (80, 10)])])
        pos = {1: (0, 0.2), 2: (41.0, 0.2), 3: (44.0, 0.2), 4: (100, 0.2), 5: (80, 10.2)}
        geo = dt.TrackGeometry(pos, [(1, 2), (2, 3), (3, 4), (3, 5)], [di])
        self.assertEqual(geo.at(3), (40.0, 0.0))
        self.assertEqual(geo.at(2), (40.0, 0.0))
        self.assertEqual(geo.report['reversed_edges'], 0)


def turnout(x0, side=1, n=12):
    """A branch leaving the x axis at x0 on a 50 m radius to the left (side 1) or right (-1), 20 m long."""
    return [(x0 + 50 * math.sin(k / n * 0.4), side * 50 * (1 - math.cos(k / n * 0.4))) for k in range(n + 1)]


class Pairing(unittest.TestCase):
    def test_a_switch_takes_its_fork_on_the_same_track_up_to_15_m(self):
        # Jiráskovo náměstí (s 12,941): DI's fork 7.3 m from OSM's switch, "likely a bit further than 5m"
        di = dt.Source('di', [rec(1, [(0, 0), (50, 0)]), rec(2, [(50, 0), (120, 0)]), rec(3, turnout(50))])
        pos = {1: (0, 0.2), 2: (57.3, 0.2), 3: (120, 0.2), 4: turnout(50)[-1]}
        geo = dt.TrackGeometry(pos, [(1, 2), (2, 3), (2, 4)], [di])
        self.assertEqual(geo.at(2), (50.0, 0.0))

    def test_a_fork_facing_the_other_way_is_not_the_switch(self):
        # a fork 6 m on whose branch leaves backwards: another switch
        back = [(56 - x, y) for x, y in [(p[0] - 50, p[1]) for p in turnout(50)]]
        di = dt.Source('di', [rec(1, [(0, 0), (56, 0)]), rec(2, [(56, 0), (120, 0)]), rec(3, back)])
        pos = {1: (0, 0.2), 2: (50.0, 0.2), 3: (120, 0.2), 4: turnout(50)[-1]}
        geo = dt.TrackGeometry(pos, [(1, 2), (2, 3), (2, 4)], [di])
        self.assertNotEqual(geo.at(2), (56.0, 0.0))

    def test_a_branch_ending_on_the_middle_of_a_track_is_a_fork(self):
        # Palackého náměstí: DI does not split the through record; the branch ends 19.8 m along it
        di = dt.Source('di', [rec(1, [(0, 0), (120, 0)]), rec(2, turnout(50))])
        self.assertEqual(len(di.forks), 1)
        self.assertLess(math.dist(di.forks[0], (50, 0)), 1e-6)
        pos = {1: (0, 0.2), 2: (54.4, 0.2), 3: (120, 0.2), 4: turnout(50)[-1]}
        geo = dt.TrackGeometry(pos, [(1, 2), (2, 3), (2, 4)], [di])
        self.assertLess(math.dist(geo.at(2), (50, 0)), 1e-6)

    def test_an_interlaced_branch_forks_where_it_starts_beside_the_track(self):
        # Čechův most: DI draws the branch 13 cm off the through track for 21 m from a record joint, then it leaves;
        # the switch is a tongue before it ("the fork starts and ends well in front of/behind the road junction")
        branch = [(29, 0.13), (50, 0.13)] + [(x, y + 0.13) for x, y in turnout(50)[1:]]
        di = dt.Source('di', [rec(1, [(0, 0), (29, 0)]), rec(2, [(29, 0), (120, 0)]), rec(3, branch)])
        self.assertEqual(len(di.forks), 1)
        self.assertLess(math.dist(di.forks[0], (29 - dt.TONGUE, 0)), 0.01)
        self.assertEqual(di.interlaced[0]['side'], 1)
        # Ohrada: the branch leaves the through track's middle, 12 cm off after 9 m, and runs on beside it
        ramp = [(20 + k, 0.012 * k) for k in range(10)] + [(50, 0.12)] + [(x, y + 0.12) for x, y in turnout(50)[1:]]
        di = dt.Source('di', [rec(1, [(0, 0), (120, 0)]), rec(2, ramp)])
        self.assertEqual(len(di.forks), 1)
        self.assertLess(math.dist(di.forks[0], (20, 0)), 0.01)

    def test_a_copy_running_on_the_track_forks_where_it_leaves(self):
        # Vozovna Kobylisy: two records 1-3 cm apart for 15 m, then they part
        branch = [(30, 0.02), (50, 0.02)] + [(x, y + 0.02) for x, y in turnout(50)[1:]]
        di = dt.Source('di', [rec(1, [(0, 0), (120, 0)]), rec(2, branch)])
        self.assertEqual(len(di.forks), 1)
        self.assertLess(abs(di.forks[0][0] - 50), 2.0)

    def test_a_branch_the_source_lacks_is_left_to_the_next_source(self):
        # Dvorce: DI has no track onto the new Dvorecký most; OSM's diverging edge lies within 2 m of the through
        # track only and took it; the archive has the branch
        di = dt.Source('di', [rec(1, [(0, 0), (120, 0)])])
        archive = dt.Source('dtmp', [rec(9, turnout(50)[:5])])
        end = turnout(50)[4]
        pos = {1: (0, 0.2), 2: (50, 0.2), 3: (120, 0.2), 4: (end[0], end[1] + 0.2)}
        geo = dt.TrackGeometry(pos, [(1, 2), (2, 3), (2, 4)], [di, archive])
        self.assertEqual(geo.source(2, 4)['src'], 'dtmp')
        self.assertEqual(geo.source(1, 2)['src'], 'di')

    def test_no_source_leaves_osm_unchanged_and_no_track_is_added(self):
        di = dt.Source('di', [rec(1, [(0, 0), (100, 0)]), rec(2, [(0, 10), (100, 10)])])
        pos = {1: (0, 0.3), 2: (100, 0.3)}
        geo = dt.TrackGeometry(pos, [(1, 2)], [di])
        self.assertEqual(len(geo.pts), 1)   # the DI track at y = 10 has no OSM edge: not added
        plain = dt.TrackGeometry(pos, [(1, 2)], [])
        self.assertEqual(plain.points(1, 2), [(0, 0.3), (100, 0.3)])
        self.assertEqual(plain.source(1, 2)['src'], 'osm')

    def test_record_ends_within_join_continue_each_other(self):
        di = dt.Source('di', [rec(1, [(0, 0), (50, 0)]), rec(2, [(50.3, 0), (100, 0)])])
        self.assertEqual(len(di.chains), 1)
        self.assertEqual(di.chains[0]['line'].length > 99, True)

    def test_an_older_record_lying_on_newer_ones_is_dropped_but_interlaced_track_stays(self):
        def dated(i, pts, day):
            return rec(i, pts) | {'attrs': {'DatumVkladu': day}}
        old = dated(1, [(0, 0), (100, 0)], '2025-01-30')               # re-entered later in two pieces, 6 cm off
        new = [dated(2, [(0, 0.06), (60, 0.06)], '2026-10-07'), dated(3, [(60, 0.06), (100, 0.06)], '2026-10-07')]
        partner = dated(4, [(20, 0.19), (50, 0.19), (60, 3)], '2025-01-30')   # interlaced, 13 cm beside the newer
        di = dt.Source('di', [old, *new, partner])
        self.assertEqual(di.superseded, 1)
        self.assertEqual(sorted(r['id'] for c in di.chains for r in c['records']), ['2', '3', '4'])


if __name__ == '__main__':
    unittest.main()
