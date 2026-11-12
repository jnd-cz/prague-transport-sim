# SPDX-License-Identifier: AGPL-3.0-or-later
"""Test build_line's terrain grid from the snapshot (#223): python -I tools/test_build_line.py."""
import json
import os
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# The terrain grid needs neither geometry packages nor OSM (a run's argv: no OSM relations at import).
with patch.object(sys, 'argv', ['build_line.py', '--line', '9', '--then', '10']), \
        patch.dict(sys.modules, {'geo': types.SimpleNamespace(Frame=object), 'osm_local': types.ModuleType('osm_local')}), \
        patch('os.makedirs'):
    import build_line  # noqa: E402


class Jtsk:
    """Game metres = S-JTSK (no offset): the box is the extent."""
    def to_jtsk(self, x, y):
        return x, y

    def from_jtsk(self, e, n):
        return e, n


def tiff(w, h, v):
    """An uncompressed float32 TIFF, one strip, every cell v."""
    tags = [(256, 4, w), (257, 4, h), (258, 3, 32), (259, 3, 1), (273, 4, 8 + 2 + 12 * 6 + 4), (278, 4, h)]
    ifd = struct.pack('<H', len(tags)) + b''.join(struct.pack('<HHII', t, typ, 1, val) for t, typ, val in tags)
    return b'II*\0' + struct.pack('<I', 8) + ifd + struct.pack('<I', 0) + struct.pack('<' + 'f' * (w * h), *[v] * (w * h))


def no_network(*a, **k):
    raise AssertionError('downloaded')


class Terrain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name, value in (('RAW', self.tmp.name), ('ROOT', self.tmp.name), ('FETCH', False), ('REFRESH', False)):
            p = patch.object(build_line, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(build_line.urllib.request, 'urlopen', no_network)
        p.start()
        self.addCleanup(p.stop)

    def cache(self, xmin, ymin, xmax, ymax):
        w, h = round((xmax - xmin) / 10), round((ymax - ymin) / 10)
        with open(os.path.join(self.tmp.name, 'terrain5514.tif'), 'wb') as f:
            f.write(tiff(w, h, 250.0))
        with open(os.path.join(self.tmp.name, 'terrain5514.json'), 'w') as f:
            json.dump({'extent': {'xmin': xmin, 'ymin': ymin, 'xmax': xmax, 'ymax': ymax}}, f)

    def test_missing_is_an_error_naming_the_file(self):
        with self.assertRaises(SystemExit) as e:
            build_line.fetch_terrain(Jtsk(), 0, 100, 0, 50)
        self.assertIn('terrain5514.tif: not in raw/', str(e.exception))
        self.assertIn('--fetch', str(e.exception))

    def test_cached_grid_is_read_without_a_download(self):
        self.cache(0, 0, 100, 50)
        t = build_line.fetch_terrain(Jtsk(), 0, 100, 0, 50)
        self.assertEqual((t['nx'], t['ny'], t['base']), (10, 5, 250))

    def test_a_few_cells_short_is_kept(self):
        # the route's ends moved: 20 m short of a 700 m margin
        self.cache(0, 0, 100, 50)
        t = build_line.fetch_terrain(Jtsk(), -20, 100, 0, 50)
        self.assertEqual(t['nx'], 10)

    def test_short_by_more_than_half_the_margin_is_an_error(self):
        self.cache(0, 0, 100, 50)
        with self.assertRaises(SystemExit) as e:
            build_line.fetch_terrain(Jtsk(), 0, 100 + build_line.DEM_MARGIN / 2 + 10, 0, 50)
        self.assertIn('short of its 700 m margin', str(e.exception))

    def test_refresh_without_fetch_keeps_the_cached_grid(self):
        self.cache(0, 0, 100, 50)
        with patch.object(build_line, 'REFRESH', True):
            self.assertEqual(build_line.fetch_terrain(Jtsk(), 0, 100, 0, 50)['nx'], 10)

    def test_fetch_downloads_the_missing_grid(self):
        calls = []

        class Reply:
            def __init__(self, body):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return self.body

        def urlopen(req, timeout=None):
            calls.append(req.full_url)
            if len(calls) == 1:
                return Reply(json.dumps({'href': 'https://example.invalid/t.tif',
                                         'extent': {'xmin': 0, 'ymin': 0, 'xmax': 100, 'ymax': 50}}).encode())
            return Reply(tiff(10, 5, 300.0))

        with patch.object(build_line, 'FETCH', True), patch.object(build_line.urllib.request, 'urlopen', urlopen):
            t = build_line.fetch_terrain(Jtsk(), 0, 100, 0, 50)
        self.assertEqual(len(calls), 2)
        self.assertEqual(t['base'], 300)
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, 'terrain5514.tif')))


if __name__ == '__main__':
    unittest.main()
