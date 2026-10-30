"""Height-matching checks: python -P -E tools/test_dtmp_tracks.py."""
from pathlib import Path
import sys
import unittest

from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dtmp_tracks import Segments, samples, quantile, summary


def path(identity, coords):
    return {'id': identity, 'coords': coords, 'attrs': {}}


class HeightMatch(unittest.TestCase):
    def test_linear_z_interpolation_in_either_travel_direction(self):
        index = Segments([path(1, [(0, 0, 200), (10, 0, 210)])])
        for ux in (1, -1):
            result = index.match(4, .2, ux, 0)
            self.assertEqual(result['status'], 'numeric')
            self.assertAlmostEqual(result['z'], 204)
            self.assertAlmostEqual(result['distance'], .2)

    def test_crossing_and_neighbouring_track_do_not_supply_height(self):
        index = Segments([path(1, [(0, -10, 250), (0, 10, 250)]),
                          path(2, [(-10, 3.5, 210), (10, 3.5, 210)])])
        self.assertEqual(index.match(0, 0, 1, 0)['status'], 'no_match')

    def test_overlapping_levels_are_ambiguous(self):
        index = Segments([path(1, [(0, 0, 200), (10, 0, 200)]),
                          path(2, [(0, .1, 205), (10, .1, 205)])])
        self.assertEqual(index.match(5, 0, 1, 0)['status'], 'ambiguous')

    def test_does_not_bridge_missing_z_or_substitute_farther_track(self):
        index = Segments([path(1, [(0, 0, 0), (10, 0, 210)]),
                          path(2, [(0, .8, 220), (10, .8, 220)])])
        self.assertEqual(index.match(5, 0, 1, 0)['status'], 'missing_z')

    def test_clip_and_length_weights_are_independent_of_vertex_density(self):
        index = Segments([path(1, [(0, 0, 200), (1, 0, 201), (20, 0, 220)])])
        observations = list(samples(index, box(.5, -1, 12.5, 1)))
        self.assertAlmostEqual(sum(o['weight'] for o in observations), 12)
        self.assertTrue(all(.5 <= o['x'] <= 12.5 for o in observations))
        self.assertTrue(all(abs(o['z'] - (200 + o['x'])) < 1e-9 for o in observations))
        self.assertAlmostEqual(quantile([0, 10], [9, 1], .5), 0)

    def test_comparison_and_fallback_have_different_denominators(self):
        observations = [
            {'weight': 10, 'z': 200, 'archive': {'status': 'numeric', 'z': 200.05, 'distance': .1}},
            {'weight': 30, 'z': None, 'archive': {'status': 'numeric', 'z': 210, 'distance': .2}},
            {'weight': 10, 'z': None, 'archive': {'status': 'no_match'}},
        ]
        result = summary(observations)
        self.assertEqual(result['lengths']['missing_z_m'], 40)
        self.assertEqual(result['fallback_percent_of_missing'], 75)
        self.assertEqual(result['height_comparison']['matched_m'], 10)
        self.assertAlmostEqual(result['height_comparison']['median_archive_minus_di_m'], .05)

    def test_known_height_disagreement_is_not_counted_as_screened_fallback(self):
        observations = [{'weight': 20, 'z': None, 'conflict': True,
                         'archive': {'status': 'numeric', 'z': 220, 'distance': .1}}]
        result = summary(observations)
        self.assertEqual(result['lengths']['fallback_candidate_m'], 20)
        self.assertEqual(result['lengths']['fallback_conflict_m'], 20)
        self.assertEqual(result['eligible_percent_of_missing'], 0)

    def test_matching_archive_z_on_a_structure_requires_separate_review(self):
        result = summary([{'weight': 30, 'z': None, 'structure': True,
                           'archive': {'status': 'numeric', 'z': 180, 'distance': .01}}])
        self.assertEqual(result['lengths']['fallback_structure_review_m'], 30)
        self.assertEqual(result['eligible_percent_of_missing'], 0)


if __name__ == '__main__':
    unittest.main()
