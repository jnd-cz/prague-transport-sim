"""The rules tools/platforms.py builds the tram platforms by (tools/platform_match.py, #407):
python -P -E tools/test_platform_match.py."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import platform_match as pm  # noqa: E402
from placement import Route  # noqa: E402

R = Route([[0, 0], [1000, 0]])           # our route along x; its right is -y
RB = Route([[1000, 3.5], [0, 3.5]])      # the opposite track, the other way; its right is +y


def plat(x0, x1, y):
    return {'p': [[x0, y], [x1, y]], 'area': 0}


def stop(x, y):
    return {'q': [x, y]}


class TramPlatform(unittest.TestCase):
    def test_tram_platforms_wherever_they_are(self):
        self.assertTrue(pm.tram_platform({'railway': 'platform', 'tram': 'yes'}))
        # Nádraží Zahradní Město under the railway viaduct
        self.assertTrue(pm.tram_platform({'railway': 'platform', 'tram': 'yes', 'bus': 'yes', 'tunnel': 'yes', 'layer': '-1'}))

    def test_metro_train_bus_and_underground_platforms_are_not(self):
        for t in ({'railway': 'platform', 'subway': 'yes', 'level': '-4', 'layer': '-4', 'tunnel': 'yes'},  # Náměstí Míru
                  {'railway': 'platform', 'train': 'yes'},
                  {'railway': 'platform', 'bus': 'yes'},
                  {'railway': 'platform', 'level': '-2', 'layer': '-2', 'tunnel': 'yes'},
                  {'railway': 'platform', 'indoor': 'yes'},
                  {'public_transport': 'platform'}):
            self.assertFalse(pm.tram_platform(t), t)

    def test_an_untagged_platform_on_the_street_is(self):
        self.assertTrue(pm.tram_platform({'railway': 'platform', 'public_transport': 'platform'}))
        self.assertTrue(pm.tram_platform({'railway': 'platform', 'level': '0'}))


class TramLines(unittest.TestCase):
    def test_the_route_list_s_lines_else_the_service_date_s_trips(self):
        tables = {
            'routes.txt': [{'route_id': 'L22', 'route_short_name': '22', 'route_type': '0'},
                           {'route_id': 'L11', 'route_short_name': '11', 'route_type': '0'},
                           {'route_id': 'L9', 'route_short_name': '9', 'route_type': '0'},
                           {'route_id': 'L180', 'route_short_name': '180', 'route_type': '3'}],
            'trips.txt': [{'trip_id': 'a', 'route_id': 'L22', 'service_id': 'wd'},
                          {'trip_id': 'b', 'route_id': 'L22', 'service_id': 'other day'},
                          {'trip_id': 'c', 'route_id': 'L180', 'service_id': 'wd'},
                          {'trip_id': 'd', 'route_id': 'L9', 'service_id': 'wd', 'exceptional': '1'},
                          {'trip_id': 'e', 'route_id': 'L22', 'service_id': 'wd'}],
            'stop_times.txt': [{'trip_id': 'a', 'stop_id': 'U598Z1P'}, {'trip_id': 'b', 'stop_id': 'U46Z3P'},
                               {'trip_id': 'c', 'stop_id': 'U1Z1'}, {'trip_id': 'd', 'stop_id': 'U598Z1P'},
                               {'trip_id': 'd', 'stop_id': 'U864Z4P'}, {'trip_id': 'e', 'stop_id': 'U301Z1P'}],
            # (no route at Pražský hrad U598Z1P; Krymská keeps 11, diverted on the service date)
            'route_stops.txt': [{'route_id': 'L11', 'stop_id': 'U301Z1P'}, {'route_id': 'L22', 'stop_id': 'U301Z1P'}],
        }
        self.assertEqual(pm.tram_lines(lambda n: iter(tables[n]), {'wd'}),
                         {'U598Z1P': {'22'}, 'U864Z4P': {'9'}, 'U301Z1P': {'11', '22'}})


class Match(unittest.TestCase):
    def test_the_nearest_pairs_first(self):
        # in the extract's order the first platform took the stop nearer the second and left the second without
        a, b = plat(100, 160, -3), plat(170, 230, -3)
        self.assertEqual(pm.match([a, b], [stop(168, -3), stop(240, -3)], [R, RB]), {1: 0})
        self.assertEqual(pm.match([a, b], [stop(158, -3), stop(232, -3)], [R, RB]), {0: 0, 1: 1})

    def test_a_stop_goes_to_the_platform_on_its_side_of_the_track(self):
        # Vršovické náměstí: B by distance alone went across the tracks to A's platform
        ours, theirs = plat(100, 160, -3), plat(100, 160, 6.5)
        self.assertEqual(pm.match([theirs, ours], [stop(150, -3.6)], [R, RB]), {1: 0})

    def test_a_stop_point_past_the_platform_s_end(self):
        # Klamovka A on line 9: the stop point 38 m past the end OSM drew; across the track it is not ours
        self.assertEqual(pm.match([plat(100, 170, -3)], [stop(208, -3)], [R, RB]), {0: 0})
        self.assertEqual(pm.match([plat(100, 170, -3)], [stop(208, 6.5)], [R, RB]), {})

    def test_a_point_on_the_track_has_no_side(self):
        # Pražský hrad B: 0.6 m off the back path's centre line
        self.assertEqual(pm.match([plat(100, 160, 6.5)], [stop(150, 4.1)], [R, RB]), {0: 0})


class Leftovers(unittest.TestCase):
    def test_pieces_of_a_platform_with_a_stop_are_twins_the_rest_unused(self):
        main = dict(plat(100, 160, -3), stop=[158, -3])
        overlap = plat(105, 160, -2.5)   # Flora, Malostranská: the platform as two ways
        apart = plat(75, 89, -3)         # Lazarská: 11 m before the piece with the stop
        across = plat(100, 160, 6.5)     # the opposite direction's, without a stop
        far = plat(400, 430, -3)
        ps = [main, overlap, apart, across, far]
        pm.leftovers(ps, [R, RB])
        self.assertEqual([('twin' in p, 'unused' in p) for p in ps],
                         [(False, False), (True, False), (True, False), (False, True), (False, True)])


if __name__ == '__main__':
    unittest.main(verbosity=2)
