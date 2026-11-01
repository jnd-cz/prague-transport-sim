"""Data comparison and reference regressions: python -I tools/test_datadiff.py."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import datadiff
import data_reference as reference


def area(z=200, cls='tram', level=0):
    return {'c': cls, 'l': level, 'r': [[0, 0, z], [10, 0, z], [10, 10, z], [0, 10, z], [0, 0, z]]}


class Diff(unittest.TestCase):
    def test_height_changes_count_closed_vertex_once_and_histogram_boundaries(self):
        old = {'areas': [area(200)]}
        new = {'areas': [area(200.5)]}
        result = datadiff.compare(old, new, 'dtm')
        self.assertEqual(result['classes']['tram']['changed_vertices'], 4)
        self.assertEqual(result['classes']['tram']['changed'], 1)
        self.assertEqual(result['abs_dz_histogram']['(0.3,1]'], 4)
        self.assertEqual(result['largest_places'][0]['dz'], .5)

    def test_reordered_reversed_rotated_outlines_and_holes_are_unchanged(self):
        a = area()
        a['h'] = [[[2, 2, 200], [3, 2, 200], [3, 3, 200], [2, 2, 200]]]
        b = deepcopy(a)
        b['r'] = [[10, 0, 200], [0, 0, 200], [0, 10, 200], [10, 10, 200], [10, 0, 200]]
        b['h'][0].reverse()
        r = datadiff.compare({'areas': [a, area(cls='road')]}, {'areas': [area(cls='road'), b]}, 'dtm')
        self.assertTrue(all(s['unchanged'] == 1 for s in r['classes'].values()))
        self.assertFalse(r['largest_places'])

    def test_duplicate_geometry_reordering_does_not_invent_height_changes(self):
        r = datadiff.compare({'areas': [area(200), area(202)]}, {'areas': [area(202), area(200)]}, 'dtm')
        self.assertEqual(r['classes']['tram']['unchanged'], 2)

    def test_duplicate_pairing_is_stable_when_each_outline_changes_its_start_vertex(self):
        a, b = area(200), area(202)
        rotated = deepcopy(a)
        pts = rotated['r'][:-1]
        rotated['r'] = pts[2:] + pts[:2] + [pts[2]]
        reversed_b = deepcopy(b)
        reversed_b['r'].reverse()
        r = datadiff.compare({'areas':[a,b]}, {'areas':[reversed_b,rotated]}, 'dtm')
        self.assertEqual(r['classes']['tram']['unchanged'], 2)

    def test_different_class_level_or_xy_is_added_and_removed_not_height_change(self):
        for b in (area(cls='road'), area(level=1), {**area(), 'r': [[0, 0, 201], [11, 0, 201], [0, 10, 201]]}):
            r = datadiff.compare({'areas': [area()]}, {'areas': [b]}, 'dtm')
            self.assertEqual(sum(s['removed'] for s in r['classes'].values()), 1)
            self.assertEqual(sum(s['added'] for s in r['classes'].values()), 1)
            self.assertFalse(r['largest_places'])

    def test_missing_heights_are_gained_and_lost_not_zero_metres(self):
        b = area()
        b['r'][0][2] = None
        b['r'][-1][2] = None
        r = datadiff.compare({'areas': [b]}, {'areas': [area()]}, 'dtm')
        self.assertEqual(r['classes']['tram']['height_gained'], 1)
        self.assertEqual(sum(r['abs_dz_histogram'].values()), 3)
        r = datadiff.compare({'areas': [area()]}, {'areas': [b]}, 'dtm')
        self.assertEqual(r['classes']['tram']['height_lost'], 1)

    def test_source_kind_indices_and_line_direction_do_not_change_identity(self):
        old = {'kinds': ['edge', 'wall'], 'lines': [[0, 0, 3, 0, 0, 200, 10, 0, 201]]}
        new = {'kinds': ['wall', 'edge'], 'lines': [[1, 0, 3, 10, 0, 201, 0, 0, 200]]}
        self.assertEqual(datadiff.compare(old, new, 'zps')['classes']['edge']['unchanged'], 1)
        new['lines'][0][-1] = 202
        self.assertEqual(datadiff.compare(old, new, 'zps')['largest_places'][0]['dz'], 2)

    def test_line_fields_and_array_counts_include_more_than_route_geometry(self):
        old = {'path': [[0, 0], [1, 0]], 'roads': [{'w': 3}], 'name': 'A'}
        new = {**old, 'roads': [{'w': 4}, {'w': 2}], 'name': 'B'}
        r = datadiff.compare(old, new, 'line')
        self.assertEqual(r['changed_fields'], ['name', 'roads'])
        self.assertEqual(r['field_counts']['roads'], {'before': 1, 'after': 2, 'changed_positions': 1})

    def test_largest_places_sorted_and_limited(self):
        a = area()
        a['r'][1][2] += 7
        a['r'][2][2] -= 9
        r = datadiff.compare({'areas': [area()]}, {'areas': [a]}, 'dtm', limit=1)
        self.assertEqual(len(r['largest_places']), 1)
        self.assertEqual(r['largest_places'][0]['dz'], -9)


class Files(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'data').mkdir()
        self.cache = self.root / 'cache'
        (self.cache / 'builds').mkdir(parents=True)
        self.old = json.dumps({'areas': [area()]}).encode()
        self.file = self.root / 'data/line17.dtm.json'
        self.file.write_bytes(self.old)
        self.hash = reference.digest(self.file)
        self.man = {'files': {self.file.name: {'size': len(self.old), 'sha256': self.hash}}}
        (self.root / 'data/MANIFEST.json').write_text(json.dumps(self.man))
        (self.cache / 'builds' / self.hash).write_bytes(self.old)

    def tearDown(self):
        self.tmp.cleanup()

    def test_cli_reads_published_blob_and_never_overwrites_working_or_cache(self):
        self.file.write_text(json.dumps({'areas': [area(201)]}))
        current = self.file.read_bytes()
        with redirect_stdout(io.StringIO()):
            r = datadiff.main(['--line', '17', '--cache', str(self.cache)], self.root)
        self.assertEqual(r['classes']['tram']['changed_vertices'], 4)
        self.assertEqual(self.file.read_bytes(), current)
        self.assertEqual((self.cache / 'builds' / self.hash).read_bytes(), self.old)

    def test_corrupt_or_missing_cache_never_becomes_the_modified_working_reference(self):
        self.file.write_text('{}')
        for value in (b'x' * len(self.old), None):
            blob = self.cache / 'builds' / self.hash
            if value is None:
                blob.unlink()
            else:
                blob.write_bytes(value)
            with self.assertRaises(FileNotFoundError):
                reference.published(self.root, self.file.name, self.man, self.cache)

    def test_matching_working_copy_can_supply_a_reference_without_a_cache(self):
        with patch.dict('os.environ', {'TRAMDATA_CACHE': ''}):
            self.assertEqual(reference.published(self.root, self.file.name, self.man), self.file)

    def test_point_search_respects_holes_and_long_source_segments(self):
        a = area()
        a['h'] = [[[3, 3, 200], [7, 3, 200], [7, 7, 200], [3, 7, 200], [3, 3, 200]]]
        self.file.write_text(json.dumps({'areas': [a]}))
        (self.root / 'data/line17.zps.json').write_text(json.dumps({
            'kinds': ['boundary'], 'lines': [[0, 1, 3, -100, 5, 200, 100, 5, 201]]}))
        r = datadiff.near_point(self.root, 17, (5, 5), 1)
        self.assertFalse(r['areas'])
        self.assertEqual(r['source_lines'][0]['distance_m'], 0)
        self.assertEqual(r['source_lines'][0]['level'], 1)
        r = datadiff.near_point(self.root, 17, (3.5, 5), 1)
        self.assertEqual(r['areas'][0]['distance_m'], .5)

    def test_different_frames_fail_before_reporting_a_height_comparison(self):
        self.file.write_text(json.dumps({'frame': {'origin': [10, 20]}, 'areas': [area()]}))
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as e:
            datadiff.main(['--line', '17', '--cache', str(self.cache)], self.root)
        self.assertEqual(e.exception.code, 1)

    def test_at_accepts_negative_xy_as_a_separate_argument(self):
        with redirect_stdout(io.StringIO()):
            r = datadiff.main(['--line','17','--cache',str(self.cache),'--at','-5,-7'], self.root)
        self.assertEqual(r['at']['xy'], [-5,-7])

    def test_survey_comparison_checks_the_parent_lines_frame(self):
        path = self.root/'data/line17.json'
        path.write_text(json.dumps({'frame':{'origin':[1,2]}}))
        old = path.read_bytes()
        h = reference.digest(path)
        (self.cache/'builds'/h).write_bytes(old)
        self.man['files'][path.name] = {'size':len(old),'sha256':h}
        (self.root/'data/MANIFEST.json').write_text(json.dumps(self.man))
        path.write_text(json.dumps({'frame':{'origin':[3,4]}}))
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as e:
            datadiff.main(['--line','17','--cache',str(self.cache)], self.root)
        self.assertEqual(e.exception.code, 1)

    def test_git_reference_export_uses_its_manifest_and_cleans_up(self):
        def run(*args):
            subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True)
        run('init', '-q')
        run('add', 'data/MANIFEST.json')
        run('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'reference')
        self.file.write_text('{}')
        with reference.checkout(self.root, 'HEAD', str(self.cache)) as other:
            exported = other
            self.assertEqual((other / 'data' / self.file.name).read_bytes(), self.old)
        self.assertFalse(exported.exists())
        # Another line's file, not in the cache: a one-line export skips it, a full one needs it.
        self.man['files']['line9.json'] = {'size': 1, 'sha256': '0' * 64}
        (self.root / 'data/MANIFEST.json').write_text(json.dumps(self.man))
        run('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qam', 'two lines')
        with reference.checkout(self.root, 'HEAD', str(self.cache), line=17) as other:
            self.assertEqual(sorted(p.name for p in (other / 'data').iterdir()), ['MANIFEST.json', self.file.name])
        with self.assertRaises(FileNotFoundError), reference.checkout(self.root, 'HEAD', str(self.cache)):
            pass
        self.assertEqual(self.file.read_text(), '{}')


if __name__ == '__main__':
    unittest.main(verbosity=2)
