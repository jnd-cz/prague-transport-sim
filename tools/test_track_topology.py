# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests of the graph cross-check: python -P -E tools/test_track_topology.py"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'bench'))
import track_topology as tt  # noqa: E402


class Frame:
    def xy(self, lat, lon):
        return (lon, lat)


def net_of(*recs):
    from test_di_network import net_of as make
    return make(*recs)


def osm(*ways):
    """OSM's answer: ways as lists of (x, y), a node per distinct point."""
    ids, els = {}, []
    for w in ways:
        for p in w:
            if p not in ids:
                ids[p] = len(ids) + 1
                els.append({'type': 'node', 'id': ids[p], 'lat': p[1], 'lon': p[0]})
    els += [{'type': 'way', 'id': 100 + i, 'nodes': [ids[p] for p in w]} for i, w in enumerate(ways)]
    return tt.OsmGraph({'elements': els}, Frame())


class Compare(unittest.TestCase):
    THROUGH = [(0, 0), (100, 0)]
    BRANCH = [(50, 0), (70, 3), (100, 20)]
    GENTLE = [(50, 0), (60, 2), (75, 6), (100, 25)]

    def both(self, net, graph):
        g = tt.DiGraph(net, set(net.edges))
        return tt.compare(graph, g, g, lambda p: True)[0]

    def test_the_same_fork_differs_nowhere(self):
        net = net_of(self.THROUGH, self.BRANCH)
        found = self.both(net, osm([(0, 0), (50, 0), (100, 0)], [(50, 0), (70, 3), (100, 20)]))
        self.assertEqual(found, {'osm-only': [], 'di-only': [], 'no-osm': [], 'no-di': []})

    def test_a_fork_40_m_from_osms_on_tracks_beside_each_other_still_agrees(self):
        # (Ohrada: the branch runs beside the track from the tip, the fork's place is no difference of connection)
        net = net_of(self.THROUGH, [(50, 0), (70, 3), (100, 20)])
        found = self.both(net, osm([(0, 0), (48, 0), (100, 0)], [(48, 0), (70, 3), (100, 20)]))
        self.assertEqual(found['osm-only'], [])
        self.assertEqual(found['di-only'], [])

    def test_a_connection_the_network_lacks_is_listed(self):
        # the branch stops 2 m beside the track in the network: OSM connects them
        net = net_of(self.THROUGH, self.GENTLE[1:])
        found = self.both(net, osm([(0, 0), (50, 0), (100, 0)], self.GENTLE))
        self.assertEqual(len(found['osm-only']), 1)

    def test_a_track_the_network_lacks_is_listed(self):
        net = net_of(self.THROUGH)
        found = self.both(net, osm([(0, 0), (50, 0), (100, 0)], self.GENTLE))
        self.assertEqual(len(found['no-di']), 1)

    def test_a_connection_osm_lacks_is_listed(self):
        net = net_of(self.THROUGH, self.GENTLE)
        found = self.both(net, osm([(0, 0), (100, 0)], [(60, 2), (75, 6), (100, 25)]))
        self.assertEqual(len(found['di-only']), 1)

    def test_a_track_osm_does_not_have_is_no_reading_of_the_connection(self):
        net = net_of(self.THROUGH, self.GENTLE)
        found = self.both(net, osm([(0, 0), (100, 0)]))
        self.assertEqual(found['di-only'], [])
        self.assertEqual(len(found['no-osm']), 1)

    def test_a_crossing_node_is_straight_on_only(self):
        graph = osm([(0, 0), (50, 0), (100, 0)], [(50, -50), (50, 0), (50, 50)])
        graph.tags[next(n for n, p in graph.xy.items() if p == (50, 0))] = {'railway': 'railway_crossing'}
        self.assertEqual(len(graph.movements(lambda p: True)), 2)


if __name__ == '__main__':
    unittest.main()
