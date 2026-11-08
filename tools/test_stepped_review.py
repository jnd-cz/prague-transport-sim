"""Tests of the stepped-curve review cards (tools/stepped_review.py, #368) on synthetic tracks:
python -P -E tools/test_stepped_review.py"""
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geo  # noqa: E402
import stepped_review as sr  # noqa: E402


def arc(r, a0, a1, step=1.0):
    n = max(2, int(abs(a1 - a0) * r / step))
    return [(r * math.sin(a0 + (a1 - a0) * k / n), r - r * math.cos(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]


def kinked(r=500.0, corner=5.0, at=100.0, length=200.0):
    """A 500 m curve with an extra 5 degree corner at s=100: straight pieces turned at one point."""
    theta = math.radians(corner)
    pts, x, y, h = [(0.0, 0.0)], 0.0, 0.0, 0.0
    for k in range(1, int(length) + 1):
        h += 1 / r + (theta if k == int(at) else 0.0)
        x, y = x + math.cos(h), y + math.sin(h)
        pts.append((x, y))
    return pts


class Measure(unittest.TestCase):
    def test_a_smooth_curve_has_no_step(self):
        p = arc(127.0, 0, 1.2)
        m = sr.measure(p, 60.0)
        self.assertLess(m['offset_m'], .003)
        self.assertAlmostEqual(m['r25'], 127.0, delta=1.0)

    def test_an_s_bend_has_no_step(self):
        # (a 300 m curve left, then right: one circle read this as metres off it; the flanks' cubic follows it to 2 cm, the
        # curvature flipping in one point with no transition; the check does not flag it, its radii over 5 and 25 m alike)
        pts, x, y, h = [(0.0, 0.0)], 0.0, 0.0, 0.0
        for k in range(1, 81):
            h += (1 if k <= 40 else -1) / 300
            x, y = x + math.cos(h), y + math.sin(h)
            pts.append((x, y))
        self.assertLess(sr.measure(pts, 40.0)['offset_m'], .025)

    def test_a_corner_reads_as_its_angle_and_offset(self):
        m = sr.measure(kinked(), 100.0)
        self.assertGreater(m['corner_deg'], 3.0)
        self.assertGreater(m['offset_m'], .05)
        self.assertLess(m['offset_m'], .4)

    def test_the_checks_own_radii_are_kept(self):
        m = sr.measure(kinked(), 100.0, 'our track 33 m over 5 m in a 127 m curve')
        self.assertEqual((m['r5'], m['r25']), (33.0, 127.0))
        self.assertAlmostEqual(m['corner_deg'], math.degrees(5 / 33 - 5 / 127), places=6)


class Cards(unittest.TestCase):
    @unittest.skipUnless(geo.have_grid(), geo.NO_GRID)
    def test_places_of_one_curve_are_one_card_and_answered_ones_go(self):
        root = Path(tempfile.mkdtemp())
        (root / 'data').mkdir()
        (root / 'lint').mkdir()
        p = kinked()
        _, at = sr.along(p)
        back = [(x, y - 3.0) for x, y in p][::-1]
        far = kinked()  # (a second curve 2 km away)
        far = [(x + 2000, y) for x, y in far]
        (root / 'data' / 'line5.json').write_text(json.dumps({'path': p + far, 'pathBack': back, 'tracks': [], 'switches': []}))
        L, _ = sr.along(p + far)
        places = [{'kind': 'our', 's': 100, 'info': 'our track 40 m over 5 m in a 500 m curve'},
                  {'kind': 'opposite', 's': round(sr.along(back)[0] - 100), 'info': 'opposite track 41 m over 5 m in a 497 m curve'},
                  {'kind': 'our', 's': round(sr.along(p)[0] + math.dist(p[-1], far[0]) + 100)}]
        (root / 'lint' / 'line5-lint.json').write_text(json.dumps({'result': {'checks': {'steppedCurves': {'places': places}}}}))
        truth = root / 'truth.json'
        truth.write_text(json.dumps({'trackSources': {'steppedAnswers': []}}))
        cards = sr.build(root / 'lint', root, truth)
        self.assertEqual(len(cards), 2)
        one = next(c for c in cards if len(c['places']) == 2)
        self.assertEqual(sorted(q['track'] for q in one['places']), ['opposite', 'our'])
        self.assertEqual(one['options'], sr.OPTIONS)
        self.assertTrue(one['id'].startswith('stepped-'))
        truth.write_text(json.dumps({'trackSources': {'steppedAnswers': [{'place': one['place'], 'answer': 'keep'}]}}))
        self.assertEqual(len(sr.build(root / 'lint', root, truth)), 1)


if __name__ == '__main__':
    unittest.main()
