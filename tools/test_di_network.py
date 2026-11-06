"""DI's track network and routes matched over it (#237): python -P -E tools/test_di_network.py."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import di_network as dn  # noqa: E402
import di_tracks as dt  # noqa: E402


def rec(i, pts):
    return {'id': str(i), 'coords': [(x, y, None) for x, y in pts], 'attrs': {}, 'sources': []}


def turnout(x0, side=1, r=60.0, length=40.0, n=20):
    """A branch leaving the x axis at x0 tangentially on a circle of radius r."""
    return [(x0 + r * math.sin(length / r * k / n), side * r * (1 - math.cos(length / r * k / n))) for k in range(n + 1)]


def net_of(*recs, **kw):
    return dn.Network(dt.Source('di', [rec(i, p) for i, p in enumerate(recs)]), **kw)


def along(m):
    return [(p[0], p[1]) for p in m.pieces if p[0] != 'off']


def line_y(net, m, x):
    """The y of the matched line where it passes x."""
    pts = m.points
    for a, b in zip(pts, pts[1:]):
        if min(a[0], b[0]) <= x <= max(a[0], b[0]) and a[0] != b[0]:
            return a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0])
    return None


class Network(unittest.TestCase):
    def test_a_fork_splits_the_track_and_its_legs_pass_only_to_the_toe(self):
        net = net_of([(0, 0), (50, 0)], [(50, 0), (120, 0)], turnout(50))
        forks = [n for n, v in net.nodes.items() if len(net.at[n]) == 3]
        self.assertEqual(len(forks), 1)
        toe, thr, div = net.through(forks[0])
        self.assertEqual(set(net.passes[toe]), {thr, div})
        self.assertEqual(net.passes[thr], [toe])
        self.assertEqual(net.passes[div], [toe])

    def test_a_branch_ending_on_the_middle_of_a_track_joins_it_there(self):
        net = net_of([(0, 0), (120, 0)], turnout(50))
        self.assertEqual(net.report['branch joins'], 1)
        node = next(n for n in net.nodes if len(net.at[n]) == 3)
        self.assertAlmostEqual(net.nodes[node]['xy'][0], 50, delta=0.01)

    def test_a_square_crossing_goes_straight_on_only(self):
        net = net_of([(0, 0), (100, 0)], [(50, -50), (50, 50)])
        n = next(n for n, v in net.nodes.items() if v['kind'] == 'crossing')
        for x in net.at[n]:
            self.assertEqual(len(net.passes[x]), 1)
            y = net.passes[x][0]
            u, v = net.out_dir(*x), net.out_dir(*y)
            self.assertLess(u[0] * v[0] + u[1] * v[1], -0.99)

    def test_two_chains_crossing_shallowly_go_on_as_themselves(self):
        # Vozovna Kobylisy: 14-15°, within the angle a switch's leg may leave at
        a = math.radians(14)
        net = net_of([(0, 0), (100, 0)], [(50 - 50 * math.cos(a), -50 * math.sin(a)), (50 + 50 * math.cos(a), 50 * math.sin(a))])
        n = next(n for n, v in net.nodes.items() if v['kind'] == 'crossing')
        for x in net.at[n]:
            self.assertEqual(len(net.passes[x]), 1)
            self.assertEqual(net.edges[net.passes[x][0][0]]['chain'], net.edges[x[0]]['chain'])

    def test_a_switch_drawn_as_a_section_forks_at_its_tip(self):
        # Dvorecký most, Palackého náměstí: both legs as short records from the tip to where the tracks go on
        # (the legs 0.37 m apart at their ends: closer, the source drops one as a copy of the other)
        leg = turnout(50, r=30, length=4.7, n=3)
        net = net_of([(0, 0), (50, 0)], [(50, 0), (54.7, 0)], leg, [(54.7, 0), (120, 0)],
                     turnout(50, r=30, length=40, n=400)[47:])
        self.assertEqual(net.report['sections to their tips'], 1)
        forks = [n for n in net.nodes if len(net.at[n]) == 3]
        self.assertEqual(len(forks), 1)
        self.assertAlmostEqual(net.nodes[forks[0]]['xy'][0], 50, delta=0.01)

    def test_two_track_ends_facing_each_other_within_2_m_are_one_track(self):
        net = net_of([(0, 0), (50, 0)], [(51.1, 0), (100, 0)])
        self.assertEqual(net.report['gaps joined'], 1)
        m = dn.Match(net, [(0, 0.3), (100, 0.3)])
        self.assertEqual(m.report['off_m'], 0)

    def test_a_scrap_of_record_beside_the_track_is_not_a_switch(self):
        # Kobylisy: 0.6 m from a node where tracks meet
        net = net_of([(0, 0), (50, 0)], [(50, 0), (100, 0)], [(50, 0), (50.4, 0.6)])
        self.assertEqual(net.report['stubs dropped'], 1)
        self.assertFalse([n for n in net.nodes if len(net.at[n]) >= 3])

    def test_parallel_tracks_meeting_at_one_node_each_keep_their_side(self):
        # Malostranské náměstí's gauntlet: two tracks come together to 9 cm apart, their records ending together
        net = net_of([(0, 0), (50, 0)], [(0, 3.5), (30, 0.09), (50, 0.09)],
                     [(50, 0), (100, 0)], [(50, 0.09), (70, 0.09), (100, 3.5)])
        m = dn.Match(net, [(0, 0.0), (100, 0.0)])
        # (within the node's place: the four ends 9 cm apart meet at their mean)
        self.assertAlmostEqual(line_y(net, m, 20), 0, delta=0.05)
        self.assertAlmostEqual(line_y(net, m, 90), 0, delta=0.05)
        m = dn.Match(net, [(0, 3.5), (30, 0.09), (70, 0.09), (100, 3.5)])
        self.assertGreater(line_y(net, m, 90), 2)

    def test_a_gauntlets_tracks_never_touch(self):
        net = net_of([(0, 0), (50, 0)], [(0, 3.5), (30, 0.09), (50, 0.09)],
                     [(50, 0), (100, 0)], [(50, 0.09), (70, 0.09), (100, 3.5)])
        self.assertEqual(net.report['gauntlets kept apart'], 1)
        self.assertFalse([n for n in net.nodes if len(net.at[n]) > 2])
        for ed in net.edges.values():
            ys = [c[1] for c in ed['line'].coords if 40 < c[0] < 60]
            if ys and max(ys) < 0.05:
                self.assertLess(max(abs(y) for y in ys), 0.01)

    def test_every_edge_has_its_own_pair_of_nodes(self):
        # (the curve fit keys edges by their nodes: the gauntlet's two tracks between one pair are split)
        net = net_of([(0, 0), (50, 0)], [(0, 0.09), (50, 0.09)], [(50, 0), (100, 0)], [(50, 0.09), (100, 0.09)])
        pairs = [frozenset((ed['a'], ed['b'])) for ed in net.edges.values()]
        self.assertEqual(len(pairs), len(set(pairs)))
        self.assertTrue(all(ed['a'] != ed['b'] for ed in net.edges.values()))

    def test_a_forks_node_lies_on_the_straight_track(self):
        # the mean of three ends lay up to 12 cm off the straight track, which the fit then had to pass through
        net = net_of([(0, 0), (50, 0)], [(50, 0), (120, 0)], [(50.1, 0.4)] + turnout(50, r=60)[1:])
        n = next(n for n in net.nodes if len(net.at[n]) == 3)
        self.assertAlmostEqual(net.nodes[n]['xy'][1], 0, delta=0.001)

    def test_four_ends_crossing_meet_where_their_pairs_cross(self):
        net = net_of([(0, 0.1), (50, 0.1)], [(50, 0.1), (100, 0.1)], [(50, -50), (50.2, 0)], [(50.2, 0), (50.4, 50)])
        n = next(n for n in net.nodes if len(net.at[n]) == 4)
        self.assertAlmostEqual(net.nodes[n]['xy'][1], 0.1, delta=0.001)
        self.assertAlmostEqual(net.nodes[n]['xy'][0], 50.2, delta=0.01)

    def test_a_section_pairs_each_leg_with_the_track_on_its_side_and_leaves_out_their_meeting_point(self):
        # the legs end 0.37 m apart at Y; a track through Y's middle stepped 18 cm towards the other
        leg = turnout(50, r=30, length=4.7, n=3)
        net = net_of([(0, 0), (50, 0)], [(50, 0), (54.7, 0)], leg, [(54.7, 0), (120, 0)],
                     turnout(50, r=30, length=40, n=400)[47:])
        self.assertEqual(net.report['sections to their tips'], 1)
        straight = next(ed for ed in net.edges.values() if max(c[0] for c in ed['line'].coords) > 100)
        self.assertLess(max(abs(c[1]) for c in straight['line'].coords), 0.01)

    def test_a_chain_all_copy_of_the_track_goes(self):
        # Kobylisy, Ďáblice: both ends on the track, within centimetres of it all along: it ran out and back
        net = net_of([(0, 0), (100, 0)], [(40, 0.01), (60, 0.01)])
        self.assertEqual(net.report['chains wholly copies'] + net.report['stubs dropped'], 1)
        for ed in net.edges.values():
            self.assertLessEqual(ed['line'].length, 100.01)

    def test_a_track_beside_another_is_no_copy_where_an_end_faces_it(self):
        # Ohrada: 20 cm beside the through track for 30 m, its curve starts 5 m on: the track goes on across the gap
        curve = [(65, 0.8), (75, 3), (90, 10)]
        net = net_of([(0, 0), (30, 0)], [(30, 0), (100, 0)], [(30, 0), (60, 0.2)], curve)
        self.assertEqual(net.report['chains wholly copies'], 0)
        self.assertEqual(net.report['copies kept: an end faces them across a gap'], 1)
        self.assertEqual(net.report['crossing gaps filled'], 1)
        self.assertEqual(sum(ed['src'] == 'di' for ed in net.edges.values() if abs(ed['line'].interpolate(ed['line'].project(dn.Point(50, 0.15))).y - 0.15) < 0.1), 1)

    def test_a_branch_ending_beside_the_track_walks_back(self):
        # 40 cm beside the track, with its own points on from there: no point near the node, none put on the chord
        branch = [(50 + k, 0.4 + 0.02 * k * k) for k in range(30)]
        net = net_of([(0, 0), (120, 0)], branch)
        n = next(n for n in net.nodes if len(net.at[n]) == 3)
        e, end = next(x for x in net.at[n] if net.edges[x[0]].get('walk'))
        c = list(net.edges[e]['line'].coords)
        c = c if end == 0 else c[::-1]
        self.assertGreaterEqual(math.dist(c[0], c[1]), 3.0)
        drawn = dn.Drawn(net, set(net.edges), fit=False)
        self.assertEqual(drawn.net.edges[e].get('walk'), {end})

    def test_a_switch_whose_tip_the_user_placed_forks_there(self):
        net = net_of([(0, 0), (50, 0)], [(50, 0), (120, 0)], turnout(50), tips=[((50.5, 0.2), (46.7, -1.65))])
        self.assertEqual(net.report['switch tips placed'], 1)
        fork = next(n for n in net.nodes if len(net.at[n]) == 3)
        self.assertAlmostEqual(net.nodes[fork]['xy'][0], 46.7, delta=0.01)

    def test_a_track_measured_on_the_orthophoto_takes_its_edge(self):
        branch = turnout(50)
        photo = dt.Source('ortho', [rec(9, [(x, y + 0.3) for x, y in branch])])
        net = net_of([(0, 0), (50, 0)], [(50, 0), (120, 0)], branch, photo=photo)
        self.assertEqual(net.report['edges from the orthophoto'], 1)
        self.assertEqual(sum(ed['src'] == 'ortho' for ed in net.edges.values()), 1)


class Matching(unittest.TestCase):
    def test_each_track_of_a_double_track_keeps_its_own(self):
        # OSM draws the pair 2.5 m apart (Kobylisy), DI 3.5 m
        net = net_of([(0, 0), (100, 0)], [(0, 3.5), (100, 3.5)])
        a = dn.Match(net, [(0, 0.5), (100, 0.5)])
        b = dn.Match(net, [(100, 3.0), (0, 3.0)])
        self.assertAlmostEqual(line_y(net, a, 50), 0, places=6)
        self.assertAlmostEqual(line_y(net, b, 50), 3.5, places=6)

    def test_a_route_off_by_2_m_stays_on_its_track_through_crossings(self):
        # Anděl: OSM's track 2.2 m east of DI's through three crossings within 20 m
        recs = [[(0, -100), (0, 100)]] + [[(-60, y), (60, y)] for y in (-10, 0, 10)]
        net = net_of(*recs)
        m = dn.Match(net, [(2.2, -100), (2.2, 100)])
        self.assertEqual(m.report['off_m'], 0)
        self.assertTrue(all(abs(p[0]) < 1e-6 for p in m.points))

    def test_a_route_never_jumps_to_the_other_track_without_a_crossover(self):
        # the route drawn from one track to the other where no switch joins them: it stays on the network only
        # by its own track and goes off where it cannot follow
        net = net_of([(0, 0), (200, 0)], [(0, 3.5), (200, 3.5)])
        m = dn.Match(net, [(0, 0), (100, 0), (110, 3.5), (200, 3.5)])
        chains = {net.edges[e]['chain'] for e, _ in along(m)}
        self.assertTrue(chains == {0} or m.report['off_m'] > 0)

    def test_the_route_takes_the_leg_osm_takes(self):
        net = net_of([(0, 0), (50, 0)], [(50, 0), (120, 0)], turnout(50))
        straight = dn.Match(net, [(0, 0.4), (50, 0.4), (120, 0.4)])
        turning = dn.Match(net, [(0, 0.4), (50, 0.4)] + [(x, y + 0.4) for x, y in turnout(50)[1:]])
        self.assertAlmostEqual(line_y(net, straight, 100), 0, places=6)
        self.assertGreater(turning.points[-1][1], 10)

    def test_where_di_has_no_track_the_route_runs_on_osm(self):
        net = net_of([(0, 0), (100, 0)], [(200, 0), (300, 0)])
        m = dn.Match(net, [(0, 0), (300, 0)])
        self.assertGreater(m.report['off_m'], 80)
        self.assertLess(m.report['off_m'], 120)

    def test_each_route_node_gets_its_place_along_the_line(self):
        net = net_of([(0, 0), (100, 0)])
        m = dn.Match(net, [(0, 0.5), (40, 0.5), (100, 0.5)])
        self.assertEqual(len(m.node_s), 3)
        self.assertAlmostEqual(m.node_s[1], 40, delta=0.5)


class Drawing(unittest.TestCase):
    def test_a_facing_switch_on_the_route_and_its_other_leg(self):
        net = net_of([(0, 0), (50, 0)], [(50, 0), (120, 0)], turnout(50))
        m = dn.Match(net, [(0, 0.4), (50, 0.4), (120, 0.4)])
        edges = m.edges | {e for e in net.edges}
        g = dn.Drawn(net, edges, fit=False)
        pts, ends = g.route(m)
        line = dn.LineString(pts)
        sw = g.facing(m, ends, lambda s: (lambda p: (p.x, p.y))(line.interpolate(s)))
        self.assertEqual(len(sw), 1)
        self.assertAlmostEqual(sw[0]['s'], 50, delta=0.5)
        self.assertFalse(sw[0]['routeDiverging'])
        self.assertEqual(sw[0]['routeSide'], 'right')   # (the branch leaves to the left of travel)

    def test_a_trailing_switch_is_not_listed(self):
        net = net_of([(0, 0), (50, 0)], [(50, 0), (120, 0)], turnout(50))
        m = dn.Match(net, [(120, 0.4), (0, 0.4)])
        g = dn.Drawn(net, set(net.edges), fit=False)
        pts, ends = g.route(m)
        line = dn.LineString(pts)
        self.assertEqual(g.facing(m, ends, lambda s: (lambda p: (p.x, p.y))(line.interpolate(s))), [])

    def test_two_legs_of_a_switch_drawn_without_its_toe_are_two_chains(self):
        # (joined through the fork they made a V: the track ran back on itself)
        net = net_of([(0, 0), (50, 0)], [(50, 0), (120, 0)], turnout(50))
        legs = {e for e, ed in net.edges.items() if ed['line'].coords[0][0] >= 49.9 and ed['line'].coords[-1][0] > 60
                or ed['line'].coords[-1][0] >= 49.9 and ed['line'].coords[0][0] > 60}
        g = dn.Drawn(net, legs, fit=False)
        self.assertEqual(len(g.chains({})), 2)

    def test_an_edge_between_two_close_crossings_is_drawn(self):
        # Strossmayerovo náměstí: 1.3 m between two crossings, under MIN_SPAN: the rail must not break there
        net = net_of([(0, 0), (100, 0)], [(50, -30), (50, 30)], [(51.3, -30), (51.3, 30)])
        short = [e for e, ed in net.edges.items() if ed['line'].length < dn.MIN_SPAN]
        self.assertEqual(len(short), 1)
        spans, flags = dn.corridor(net, [{'id': 1, 'nodes': [1, 2]}], {1: (10, 0), 2: (90, 0)})
        self.assertIn(short[0], spans)
        self.assertEqual(spans[short[0]], (0.0, net.edges[short[0]]['line'].length))
        self.assertIn(short[0], flags)

    def test_a_drawn_track_does_not_end_in_the_air(self):
        # Ohrada: the ways run on the through track and past the gap, not on the branch between them: it is drawn too
        net = net_of([(0, 0), (300, 0)], [(100, 0), (110, 1), (130, 10)], [(133, 13), (150, 30), (170, 50)])
        self.assertEqual(net.report['gaps joined'] + net.report['crossing gaps filled'], 1)
        branch = next(e for e, ed in net.edges.items() if ed['line'].distance(dn.Point(110, 1)) < 0.01 and ed['line'].length < 40)
        ways = [{'id': 1, 'nodes': [1, 2]}, {'id': 2, 'nodes': [3, 4]}]
        pos = {1: (10, 0), 2: (290, 0), 3: (131, 11), 4: (165, 45)}
        spans, flags = dn.corridor(net, ways, pos)
        self.assertEqual(spans[branch], (0.0, net.edges[branch]['line'].length))
        self.assertIn(branch, flags)

    def test_a_corridor_way_draws_the_stretch_it_runs_on(self):
        # a DI edge running far past the corridor: only the stretch OSM's way covers is drawn
        net = net_of([(0, 0), (500, 0)])
        ways = [{'id': 1, 'nodes': [1, 2]}]
        spans, flags = dn.corridor(net, ways, {1: (100, 0.3), 2: (180, 0.3)})
        (e, (a, b)), = spans.items()
        self.assertAlmostEqual(a, 100, delta=1)
        self.assertAlmostEqual(b, 180, delta=1)
        g = dn.Drawn(net, set(spans), fit=False)
        (t,) = g.chains(flags, spans)
        self.assertAlmostEqual(t['p'][0][0], 100, delta=1)
        self.assertAlmostEqual(t['p'][-1][0], 180, delta=1)


if __name__ == '__main__':
    unittest.main()
