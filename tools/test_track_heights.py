"""Height-import guard regressions: python -P -E tools/test_track_heights.py."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from shapely.geometry import Point, box

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dtmp_tracks import Segments, ROOT, di_data, archive_data, surface_evidence
import dtmp_tracks as research
from track_heights import HeightGuard
import import_track_heights as stage


def path(identity, z, y=0):
    return {'id': identity, 'coords': [(0, y, z), (10, y, z)], 'attrs': {}, 'sources': []}


def match(*paths):
    return Segments(paths).match(5, 0, 1, 0, details=True)


def evidence(z=200, **updates):
    return {'id': 'survey-1', 'di_id': 'di-1', 'xy': [5, 0], 'radius_m': .5,
            'kind': 'surface', 'level': 0, 'reviewed': True, 'z': z,
            'vertical_datum': 'Bpv', 'height_meaning': 'top_of_rail',
            'source': {'dataset': 'independent-survey', 'record': 'point-1', 'date': '2026-09-01'}, **updates}


class Guard(unittest.TestCase):
    def test_repeated_di_geometry_keeps_each_packages_attributes_and_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            entries = []
            for code, quality in [('500054', '2'), ('500089', '3')]:
                name = code + '.zip'
                xml = f'''<obj:JVFDTM xmlns:obj="objtyp" xmlns:r="track" xmlns:atr="atr"
                    xmlns:di="dopinf" xmlns:gml="http://www.opengis.net/gml/3.2">
                    <di:ObvodDatoveSady><gml:Polygon><gml:posList>0 0 10 0 10 10 0 0</gml:posList>
                    </gml:Polygon></di:ObvodDatoveSady><obj:OsaKolejeTramvajoveDrahy><r:ZaznamObjektu>
                    <atr:ID>same</atr:ID><atr:TridaPresnostiVyska>{quality}</atr:TridaPresnostiVyska>
                    <gml:LineString srsName="EPSG:5514" srsDimension="3"><gml:posList>0 0 200 10 0 200</gml:posList>
                    </gml:LineString></r:ZaznamObjektu></obj:OsaKolejeTramvajoveDrahy></obj:JVFDTM>'''
                with zipfile.ZipFile(folder / name, 'w') as z:
                    z.writestr('DI.xml', xml)
                entries.append({'code':code, 'file':name, 'state':'2026-09-30',
                                'sha256':hashlib.sha256((folder/name).read_bytes()).hexdigest()})
            (folder / 'provenance.json').write_text(json.dumps({'packages':entries}), encoding='utf-8')
            with patch.object(research, 'DI', folder):
                _, paths = di_data()
        self.assertEqual(len(paths), 1)
        self.assertEqual([s['attributes']['TridaPresnostiVyska'] for s in paths[0]['sources']], ['2','3'])
        self.assertEqual([s['file'] for s in paths[0]['sources']], ['500054.zip','500089.zip'])

    def test_close_plan_fit_numeric_z_and_di_level_zero_do_not_validate_a_bridge(self):
        di = {'id': '1000413716080', 'z': 194.398, 'attrs': {'UrovenUmisteniObjektuDI': '0'}}
        m = match(path(5168282, 180.412, .137))
        result = HeightGuard().choose(di, m, 5, 0, structure_hint=True)
        self.assertIsNone(result['z'])
        self.assertEqual(result['confidence'], 'unvalidated')
        self.assertIn('di_archive_height_disagreement', result['review_flags'])
        self.assertEqual(result['candidates'][1]['id'], 5168282)

    def test_reviewed_deck_level_supports_di_and_preserves_archive_disagreement(self):
        e = evidence(194.45, di_id='1000413716080', kind='deck', level=1)
        result = HeightGuard([e]).choose({'id': e['di_id'], 'z': 194.398},
            match(path(5168282, 180.412, .137)), 5, 0, structure_hint=True)
        self.assertEqual(result['height_source'], {'dataset': 'di', 'id': e['di_id']})
        self.assertEqual(result['z'], 194.398)
        self.assertIn('di_archive_height_disagreement', result['review_flags'])
        self.assertEqual(result['evidence_ids'], [e['id']])

    def test_ordinary_agreeing_surface_preserves_geometry_and_separate_height_source(self):
        di, m = {'id': 'di-1', 'z': 200.05}, match(path(1, 200))
        original = deepcopy((di, m))
        result = HeightGuard([evidence()]).choose(di, m, 5, 0)
        self.assertEqual(result['z'], 200.05)
        self.assertEqual(result['height_source']['dataset'], 'di')
        self.assertEqual((di, m), original)

    def test_archive_can_supply_a_missing_or_disagreeing_current_height_only_with_evidence(self):
        for z in (None, 0, 224.93):
            result = HeightGuard([evidence()]).choose({'id': 'di-1', 'z': z}, match(path(1, 200)), 5, 0)
            self.assertEqual(result['z'], 200)
            self.assertEqual(result['height_source'], {'dataset': 'archive', 'id': 1})

    def test_untagged_surface_and_source_agreement_are_still_unvalidated_without_evidence(self):
        result = HeightGuard().choose({'id': 'di-1', 'z': 200}, match(path(1, 200)), 5, 0)
        self.assertEqual(result['status'], 'review')
        self.assertIsNone(result['z'])

    def test_ambiguous_levels_need_local_level_evidence(self):
        m = match(path(1, 200), path(2, 205, .1))
        self.assertEqual(m['status'], 'ambiguous')
        self.assertIsNone(HeightGuard().choose({'id': 'di-1', 'z': None}, m, 5, 0)['z'])
        result = HeightGuard([evidence(205, level=1, kind='deck')]).choose({'id': 'di-1', 'z': None}, m, 5, 0)
        self.assertEqual(result['height_source'], {'dataset': 'archive', 'id': 2})
        conflicting = [evidence(), evidence(205, id='survey-2', level=1, kind='deck')]
        self.assertIn('conflicting_level_evidence', HeightGuard(conflicting).choose(
            {'id': 'di-1', 'z': None}, m, 5, 0)['review_flags'])

    def test_nearest_missing_z_is_not_replaced_by_a_farther_numeric_track(self):
        m = match(path(1, 0), path(2, 200, .1))
        result = HeightGuard([evidence()]).choose({'id': 'di-1', 'z': None}, m, 5, 0)
        self.assertIsNone(result['z'])
        self.assertIn('nearest_archive_missing_z', result['review_flags'])
        self.assertEqual([(c['id'],c['excluded']) for c in result['candidates']],
                         [(1,'missing_z'), (2,'nearest_archive_missing_z')])

    def test_disagreement_record_is_flagged_even_where_current_z_is_missing(self):
        result = HeightGuard(conflicts=[1]).choose({'id': 'di-1', 'z': None}, match(path(1, 200)), 5, 0)
        self.assertIsNone(result['z'])
        self.assertIn('known_archive_disagreement', result['review_flags'])

    def test_obsolete_and_uncertain_alignments_cannot_be_selected(self):
        m = match(path(1, 200))
        for dataset, identity, status in [('archive', 1, 'obsolete'), ('di', 'di-1', 'obsolete'), ('di', 'di-1', 'uncertain')]:
            review = {'dataset': dataset, 'id': identity, 'status': status, 'source': 'reviewed reconstruction plan'}
            result = HeightGuard([evidence()], [review]).choose({'id': 'di-1', 'z': None}, m, 5, 0)
            self.assertIsNone(result['z'])
            self.assertIn(f'{dataset}_{status}_alignment', result['review_flags'])

    def test_evidence_cannot_be_reused_for_another_track_or_location(self):
        for e in (evidence(di_id='other'), evidence(xy=[7, 0])):
            result = HeightGuard([e]).choose({'id': 'di-1', 'z': None}, match(path(1, 200)), 5, 0)
            self.assertIsNone(result['z'])

    def test_structure_buffer_cannot_overrule_reviewed_surface_level(self):
        result = HeightGuard([evidence()]).choose({'id': 'di-1', 'z': None},
            match(path(1, 200)), 5, 0, structure_hint=True)
        self.assertEqual(result['z'], 200)
        self.assertEqual(result['confidence'], 'independent_level_match')

    def test_raw_deck_diagnostic_datum_or_unreviewed_evidence_cannot_approve_z(self):
        for e in (evidence(height_meaning='deck_surface'), evidence(vertical_datum='unknown'),
                  evidence(reviewed=False), evidence(source={'dataset':'compiled-zps','record':'vertex','date':'2026-09-30'})):
            with self.assertRaises(ValueError):
                HeightGuard([e])

    def test_short_large_disagreements_are_not_lost_below_the_ten_metre_screen(self):
        rows = [{'z': 214, 'weight': 1, 'archive': match(path(1, 200))}]
        self.assertEqual(stage.conflict_records(rows), {'1'})

    def test_staging_keeps_di_xy_raw_z_provenance_and_does_not_add_archive_only_geometry(self):
        di, archived = path('di-1', 0), [path(1, 200), path(99, 250, 20)]
        di['sources'] = [{'file':'DI.zip','sha256':'hash','state':'2026-09-30'}]
        original = deepcopy(di)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'snapshots').mkdir()
            (root / 'snapshots/CURRENT').write_text('test')
            with patch.multiple(stage, ROOT=root, di_data=lambda: ([{'polygon':box(-1,-1,11,1)}],[di]),
                    archive_data=lambda: ({'acquired':'2026-10-30'}, {}, archived),
                    structure_mask=lambda: (box(50,50,60,60), []),
                    load_line=lambda n: {'path':[[0,0],[10,0]]}, surface_evidence=lambda rows: None), redirect_stdout(io.StringIO()):
                result = stage.stage({})
        self.assertEqual(di, original)
        self.assertEqual(len(result['geometry']), 1)
        self.assertEqual(result['geometry'][0]['xy'], [(0,0),(10,0)])
        self.assertEqual(result['geometry'][0]['raw_z'], [0,0])
        self.assertEqual(result['geometry'][0]['sources'], di['sources'])
        self.assertTrue(all(r['z'] is None and r['confidence']=='unvalidated' for r in result['height_samples']))
        self.assertEqual(len(result['lines']), 5)


@unittest.skipUnless((ROOT / 'raw/dtmp-tracks/provenance.json').exists(), 'fetch snapshot for real source regression')
class PinnedBridge(unittest.TestCase):
    def test_trojsky_ids_and_compiled_deck_diagnostic_do_not_approve_archived_ground_z(self):
        _, di = di_data()
        _, _, archived = archive_data()
        current = Segments([p for p in di if p['id']=='1000413716080'])
        index = Segments([p for p in archived if p['id']==5168282])
        x, y = 1422.058, 2620.908
        row = min(zip(current.rows,current.geoms),key=lambda r:r[1].distance(Point(x,y)))[0]
        ux, uy = (row['b'][0]-row['a'][0])/row['length'], (row['b'][1]-row['a'][1])/row['length']
        hit = current.match(x,y,ux,uy)
        m = index.match(hit['x'],hit['y'],ux,uy,details=True)
        self.assertEqual(m['id'],5168282)
        self.assertAlmostEqual(hit['z'],194.398,delta=.02)
        self.assertAlmostEqual(m['z'],180.412,delta=.02)
        self.assertAlmostEqual(m['distance'],.137,delta=.02)
        result = HeightGuard().choose(hit,m,hit['x'],hit['y'],structure_hint=True)
        self.assertIsNone(result['z'])
        examples = [{'xy':[hit['x'],hit['y']]}]
        surface_evidence(examples)
        self.assertTrue(any(194.4 < z < 194.6 for e in examples[0]['compiled_survey_deck_evidence']
                            for z in e['nearest_vertex_z'] if z is not None))


if __name__ == '__main__':
    unittest.main(verbosity=2)
