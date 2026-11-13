# SPDX-License-Identifier: AGPL-3.0-or-later
"""DI's track network and routes matched over it (#237): python -P -E tools/test_di_network.py."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import di_network as dn  # noqa: E402
import di_tracks as dt  # noqa: E402

dn.SMOOTHED = []  # (the networks here are made up: none of the user's answers in data/truth.json applies to them)


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
        # (each track's joint lies in line and the other's 9 cm beside it: the records join along their own tracks,
        # di_tracks._meetings, #368, and the gauntlet never becomes one node to pull apart)
        net = net_of([(0, 0), (50, 0)], [(0, 3.5), (30, 0.09), (50, 0.09)],
                     [(50, 0), (100, 0)], [(50, 0.09), (70, 0.09), (100, 3.5)])
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
    def test_a_stretch_loses_its_2_mm_segment(self):
        # Národní divadlo, #514: a stretch's end node and its first sample 2 mm apart, read by lint as a 6.8 deg corner
        pts = [(-675.954, -552.49), (-675.954, -552.488), (-675.858, -551.679), (-675.752, -550.871)]
        self.assertEqual(dn._clean(pts), [pts[0], pts[2], pts[3]])

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

    def test_a_trailing_switch_from_its_straight_branch(self):
        net = net_of([(0, 0), (50, 0)], [(50, 0), (120, 0)], turnout(50))
        m = dn.Match(net, [(120, 0.4), (0, 0.4)])
        g = dn.Drawn(net, set(net.edges), fit=False)
        pts, ends = g.route(m)
        line = dn.LineString(pts)
        work = g.trackwork(m, ends, lambda s: (lambda p: (p.x, p.y))(line.interpolate(s)))
        self.assertEqual(len(work['trailing']), 1)
        self.assertAlmostEqual(work['trailing'][0]['s'], 70, delta=0.5)
        self.assertFalse(work['trailing'][0]['fromDiverging'])
        self.assertEqual(work['crossings'], [])

    def test_a_facing_switch_is_not_a_trailing_one(self):
        net = net_of([(0, 0), (50, 0)], [(50, 0), (120, 0)], turnout(50))
        m = dn.Match(net, [(0, 0.4), (50, 0.4), (120, 0.4)])
        g = dn.Drawn(net, set(net.edges), fit=False)
        pts, ends = g.route(m)
        line = dn.LineString(pts)
        self.assertEqual(g.trackwork(m, ends, lambda s: (lambda p: (p.x, p.y))(line.interpolate(s)))['trailing'], [])

    def test_the_frog_lies_where_the_other_leg_is_one_gauge_off(self):
        leg = dn.LineString([(0, 0), (40, 4)])        # parts at 1 in 10: 1.435 m at about 14.4 m along
        self.assertAlmostEqual(dn._frog(leg, lambda d: (d, 0.0)), 14.5, delta=0.5)
        self.assertIsNone(dn._frog(dn.LineString([(0, 0), (1, 5)]), lambda d: (d, 0.0)))    # parts at once: under 5 m
        self.assertIsNone(dn._frog(dn.LineString([(0, 0), (100, 0)]), lambda d: (d, 0.0)))   # never parts within 25 m

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

    def test_a_branch_ending_past_the_fork_reaches_the_track_it_joins(self):
        # 50.1324 N 14.4526 E: the through track runs 2.5 m past where the track from the east joins it, a branch ends there
        net = net_of([(-100, 0), (0, 0)], [(-2.5, 0.05), (100, 1)], [(0, 0.1), (-20, 0.3), (-60, 5)])
        self.assertEqual(net.report['folded stubs'], 1)
        east = next(e for e, ed in net.edges.items() if max(c[0] for c in ed['line'].coords) > 50)
        branch = next(e for e, ed in net.edges.items() if max(c[1] for c in ed['line'].coords) > 4)
        n = net.edges[east]['a']
        self.assertIn(branch, [f for f, _ in net.passes[(east, 0)]], n)
        self.assertEqual(len(net.at[n]), 3)

    def test_tracks_touching_at_a_shallow_angle_are_switches_back_to_back(self):
        # Dvorce: a loop's curve touches the main track, 2.8 m apart 15 m on both ways, no record end near
        curve = [(0, 30), (30, 8), (42, 2), (48, 0.02), (50, 0), (52, 0.02), (58, 2), (70, 8), (100, 30)]
        net = net_of([(-50, 0), (150, 0)], curve)
        self.assertEqual(net.report['tracks touching: switches back to back'], 1)
        n = next(k for k, v in net.nodes.items() if v['kind'] == 'touch')
        self.assertEqual(len(net.at[n]), 4)
        west = next(x for x in net.at[n] if net.out_dir(*x)[0] < 0 and abs(net.out_dir(*x)[1]) < 0.02)
        self.assertEqual(len(net.passes[west]), 2)

    def test_a_fork_drawn_through_is_no_touch(self):
        # one side stays together: not two tracks that only touch
        net = net_of([(0, 0), (200, 0)], [(50, 0.2), (80, -0.05), (100, 0.05), (200, 0.1)])
        self.assertEqual(net.report['tracks touching: switches back to back'], 0)

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


def sampled(corners, step=1.0):
    """A polyline with points every `step` m along its segments, as an edge's line has them."""
    out = [corners[0]]
    for a, b in zip(corners, corners[1:]):
        n = max(1, round(math.dist(a, b) / step))
        out += [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(1, n + 1)]
    return out


def arc(n, chord, turn_deg, start=(0.0, 0.0), heading=0.0):
    pts = [start]
    h = math.radians(heading)
    for _ in range(n):
        pts.append((pts[-1][0] + chord * math.cos(h), pts[-1][1] + chord * math.sin(h)))
        h += math.radians(turn_deg)
    return pts


class Chords(unittest.TestCase):
    def test_the_chords_of_a_curve_lose_their_inner_points(self):
        c = sampled(arc(8, 22.0, 5.0))
        self.assertEqual(len(dn.chords(c)), 6)  # (the first and the last have a corner at one end only)
        kept = dn.without_chords(c)
        self.assertLess(len(kept), 60)
        for q in arc(8, 22.0, 5.0)[1:-1]:
            self.assertLess(min(math.dist(q, p) for p in kept), 1e-6)

    def test_a_straight_meeting_a_curve_keeps_its_points(self):
        straight = [(-300.0, 0.0), (0.0, 0.0)]
        c = sampled(straight + arc(4, 20.0, 5.0)[1:])
        kept = dn.without_chords(c)
        self.assertGreater(sum(1 for p in kept if p[0] < 0), 290)

    def test_a_straight_between_opposite_curves_keeps_its_points(self):
        c = sampled([(0, 0), (20, 0), (40, 2), (60, 2), (80, 4)])  # (up, level, up again: its corners turn opposite ways)
        kept = dn.without_chords(c)
        self.assertGreater(sum(1 for p in kept if 41 < p[0] < 59), 15)

    def test_a_long_straight_between_small_corners_keeps_its_points(self):
        c = sampled(arc(1, 20, 0) + [(120.0, -0.5), (140.0, -1.5)])
        self.assertTrue(all(d - b <= 2 for b, d in [(i, j) for i, j in dn.chords(c)]) or not dn.chords(c))

    def test_a_chord_that_sags_under_the_tolerance_stays(self):
        self.assertEqual(dn.chords(sampled(arc(6, 10.0, 0.5))), [])  # (1.1 cm: the fit bends through it anyway)
        self.assertEqual(len(dn.chords(sampled(arc(6, 10.0, 2.0)))), 4)  # (4.4 cm)

    def test_a_chord_of_a_very_wide_curve_stays(self):
        self.assertEqual(dn.chords(sampled(arc(5, 36.0, 0.5))), [])  # (3.9 cm, but 4100 m: a straight with small corners)

    def test_a_large_corner_beside_a_small_one_is_no_chord(self):
        pts = arc(1, 20.0, 6.0)
        h = math.radians(6.0)
        pts.append((pts[-1][0] + 20 * math.cos(h), pts[-1][1] + 20 * math.sin(h)))
        h += math.radians(0.5)
        pts.append((pts[-1][0] + 20 * math.cos(h), pts[-1][1] + 20 * math.sin(h)))
        self.assertEqual(dn.chords(sampled(pts)), [])

    def test_a_straight_between_tight_curves_is_no_chord(self):
        pts = arc(25, 1.0, 2.2)  # (26 m of a curve of 26 m)
        h = math.degrees(math.atan2(pts[-1][1] - pts[-2][1], pts[-1][0] - pts[-2][0])) + 1.0
        lead = arc(2, 15.0, 1.0, pts[-1], h)  # (two chords with corners of 1 degree: 860 m, on their own they would count)
        h += 2.0
        rest = arc(25, 1.0, 2.2, lead[-1], h)
        self.assertEqual(dn.chords(sampled(pts + lead[1:] + rest[1:])), [])
        self.assertEqual(len(dn.chords(sampled(lead + [(lead[-1][0] + 15 * math.cos(math.radians(h)), lead[-1][1] + 15 * math.sin(math.radians(h)))]))), 1)

    def test_a_real_straight_has_no_chords(self):
        self.assertEqual(dn.chords(sampled([(0, 0), (100, 0), (300, 0)])), [])

    def test_a_place_answered_smooth_loses_its_points_and_keeps_the_lines_ends(self):
        # (the stepped-curve review, #368: 'smooth' frees DI's vertices within its reach, the fit draws one curve through)
        c = sampled([(0, 0), (50, 0), (100, 4)])
        old = dn.SMOOTHED
        dn.SMOOTHED = [((50.0, 0.0), 10.0)]
        try:
            kept = dn.without_steps(c)
            self.assertEqual((kept[0], kept[-1]), (c[0], c[-1]))
            self.assertFalse(any(math.dist(p, (50, 0)) <= 10 for p in kept))
            self.assertEqual(len(kept), sum(1 for p in c if math.dist(p, (50, 0)) > 10))
            # (an end walked back to its node is DI's record end, no node: inside the reach it goes too)
            walked = dn.without_steps(c[:52], (True, False))
            self.assertEqual(walked[0], c[0])
            self.assertTrue(all(math.dist(p, (50, 0)) > 10 for p in walked[1:]))
            dn.SMOOTHED = []
            self.assertEqual(dn.without_steps(c), c)
        finally:
            dn.SMOOTHED = old

    def test_nodes_at_a_smooth_answer_land_on_the_curve(self):
        # (#368: Čechovo náměstí, a fork on DI's zig-zag inside a 'smooth' answer)
        class Net:
            nodes = {1: {'kind': 'fork'}, 2: {'kind': 'crossing'}, 3: {'kind': 'fork'}, 4: {'kind': 'joint'}, 5: {'kind': 'fork'}}
        pos = {1: (0.0, 0.0), 2: (1.0, 0.0), 3: (200.0, 0.0), 4: (100.0, 0.0), 5: (300.0, 0.0)}
        pts = {(1, 4): [], (2, 4): [], (3, 4): [], (3, 5): []}
        old = dn.SMOOTHED
        dn.SMOOTHED = [((0.0, 0.0), 10.0)]
        try:
            loose = dn.smooth_nodes(pos, pts, Net())
        finally:
            dn.SMOOTHED = old
        # (the fork in reach, on the edge it ends; not the crossing in reach, nor nodes elsewhere)
        self.assertEqual(sorted(loose), [(1, (1, 4))])
        self.assertEqual(set(loose.values()), {0.0})


if __name__ == '__main__':
    unittest.main()
