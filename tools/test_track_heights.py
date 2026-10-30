"""Height-import guard regressions: python -P -E tools/test_track_heights.py."""

from contextlib import redirect_stdout
from copy import deepcopy
import io
import math
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
from track_decks import Decks, load_decks


def path(identity, z, y=0):
    return {'id': identity, 'coords': [(0, y, z), (10, y, z)], 'attrs': {}, 'sources': []}


def match(*paths):
    return Segments(paths).match(5, 0, 1, 0, details=True)


def evidence(z=200, **updates):
    return {
        'id': 'survey-1',
        'di_id': 'di-1',
        'xy': [5, 0],
        'radius_m': 0.5,
        'kind': 'surface',
        'level': 0,
        'reviewed': True,
        'z': z,
        'vertical_datum': 'Bpv',
        'height_meaning': 'top_of_rail',
        'source': {'dataset': 'independent-survey', 'record': 'point-1', 'date': '2026-09-01'},
        **updates,
    }


class Guard(unittest.TestCase):
    def test_repeated_di_geometry_keeps_each_packages_attributes_and_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            entries = []
            for code, quality in [('500054', '2'), ('500089', '3')]:
                name = code + '.zip'
                xml = f"""<obj:JVFDTM xmlns:obj="objtyp" xmlns:r="track" xmlns:atr="atr"
                    xmlns:di="dopinf" xmlns:gml="http://www.opengis.net/gml/3.2">
                    <di:ObvodDatoveSady><gml:Polygon><gml:posList>0 0 10 0 10 10 0 0</gml:posList>
                    </gml:Polygon></di:ObvodDatoveSady><obj:OsaKolejeTramvajoveDrahy><r:ZaznamObjektu>
                    <atr:ID>same</atr:ID><atr:TridaPresnostiVyska>{quality}</atr:TridaPresnostiVyska>
                    <gml:LineString srsName="EPSG:5514" srsDimension="3"><gml:posList>0 0 200 10 0 200</gml:posList>
                    </gml:LineString></r:ZaznamObjektu></obj:OsaKolejeTramvajoveDrahy></obj:JVFDTM>"""
                with zipfile.ZipFile(folder / name, 'w') as z:
                    z.writestr('DI.xml', xml)
                entries.append(
                    {
                        'code': code,
                        'file': name,
                        'state': '2026-09-30',
                        'sha256': hashlib.sha256((folder / name).read_bytes()).hexdigest(),
                    }
                )
            (folder / 'provenance.json').write_text(json.dumps({'packages': entries}), encoding='utf-8')
            with patch.object(research, 'DI', folder):
                _, paths = di_data()
        self.assertEqual(len(paths), 1)
        self.assertEqual([s['attributes']['TridaPresnostiVyska'] for s in paths[0]['sources']], ['2', '3'])
        self.assertEqual([s['file'] for s in paths[0]['sources']], ['500054.zip', '500089.zip'])

    def test_trojsky_di_wins_and_archive_disagreement_remains_flagged(self):
        di = {'id': '1000413716080', 'z': 194.398, 'attrs': {'UrovenUmisteniObjektuDI': '0'}}
        m = match(path(5168282, 180.412, 0.137))
        result = HeightGuard().choose(di, m, 5, 0, structure_hint=True)
        self.assertEqual(result['z'], 194.398)
        self.assertEqual(result['height_source']['dataset'], 'di')
        self.assertIn('di_archive_height_disagreement', result['review_flags'])
        self.assertEqual(result['candidates'][1]['id'], 5168282)

    def test_reviewed_deck_level_supports_di_and_preserves_archive_disagreement(self):
        e = evidence(194.45, di_id='1000413716080', kind='deck', level=1)
        result = HeightGuard([e]).choose(
            {'id': e['di_id'], 'z': 194.398}, match(path(5168282, 180.412, 0.137)), 5, 0, structure_hint=True
        )
        self.assertEqual(result['height_source'], {'dataset': 'di', 'id': e['di_id']})
        self.assertEqual(result['z'], 194.398)
        self.assertIn('di_archive_height_disagreement', result['review_flags'])
        self.assertEqual(result['evidence_ids'], [e['id']])

    def test_ordinary_agreeing_surface_preserves_geometry_and_separate_height_source(self):
        di, m = {'id': 'di-1', 'z': 200.05}, match(path(1, 200))
        original = deepcopy((di, m))
        result = HeightGuard().choose(di, m, 5, 0)
        self.assertEqual(result['z'], 200.05)
        self.assertEqual(result['height_source']['dataset'], 'di')
        self.assertEqual((di, m), original)

    def test_archive_fills_missing_di_but_never_overrides_numeric_di(self):
        for z in (None, 0, 224.93):
            result = HeightGuard([evidence()]).choose({'id': 'di-1', 'z': z}, match(path(1, 200)), 5, 0)
            self.assertEqual(result['z'], 224.93 if z == 224.93 else 200)
            self.assertEqual(result['height_source']['dataset'], 'di' if z == 224.93 else 'archive')

    def test_ordinary_surface_archive_fills_without_a_reviewed_point(self):
        result = HeightGuard().choose({'id': 'di-1', 'z': None}, match(path(1, 200)), 5, 0)
        self.assertEqual(result['status'], 'selected')
        self.assertEqual(result['z'], 200)
        self.assertEqual(result['height_source']['dataset'], 'archive')

    def test_ambiguous_levels_need_local_level_evidence(self):
        m = match(path(1, 200), path(2, 205, 0.1))
        self.assertEqual(m['status'], 'ambiguous')
        self.assertIsNone(HeightGuard().choose({'id': 'di-1', 'z': None}, m, 5, 0)['z'])
        result = HeightGuard([evidence(205, level=1, kind='deck')]).choose({'id': 'di-1', 'z': None}, m, 5, 0)
        self.assertEqual(result['height_source'], {'dataset': 'archive', 'id': 2})
        conflicting = [evidence(), evidence(205, id='survey-2', level=1, kind='deck')]
        self.assertIn(
            'conflicting_level_evidence',
            HeightGuard(conflicting).choose({'id': 'di-1', 'z': None}, m, 5, 0)['review_flags'],
        )

    def test_nearest_missing_z_is_not_replaced_by_a_farther_numeric_track(self):
        m = match(path(1, 0), path(2, 200, 0.1))
        result = HeightGuard([evidence()]).choose({'id': 'di-1', 'z': None}, m, 5, 0)
        self.assertIsNone(result['z'])
        self.assertIn('nearest_archive_missing_z', result['review_flags'])
        self.assertEqual(
            [(c['id'], c['excluded']) for c in result['candidates']],
            [(1, 'missing_z'), (2, 'nearest_archive_missing_z')],
        )

    def test_disagreement_record_is_flagged_even_where_current_z_is_missing(self):
        result = HeightGuard(conflicts=[1]).choose({'id': 'di-1', 'z': None}, match(path(1, 200)), 5, 0)
        self.assertIsNone(result['z'])
        self.assertIn('known_archive_disagreement', result['review_flags'])

    def test_obsolete_and_uncertain_alignments_cannot_be_selected(self):
        m = match(path(1, 200))
        for dataset, identity, status in [
            ('archive', 1, 'obsolete'),
            ('di', 'di-1', 'obsolete'),
            ('di', 'di-1', 'uncertain'),
        ]:
            review = {
                'dataset': dataset,
                'id': identity,
                'status': status,
                'source': 'reviewed reconstruction plan',
            }
            result = HeightGuard([evidence()], [review]).choose({'id': 'di-1', 'z': None}, m, 5, 0)
            self.assertIsNone(result['z'])
            self.assertIn(f'{dataset}_{status}_alignment', result['review_flags'])

    def test_evidence_cannot_be_reused_for_another_track_or_location(self):
        for e in (evidence(di_id='other'), evidence(xy=[7, 0])):
            result = HeightGuard([e], conflicts=[1]).choose(
                {'id': 'di-1', 'z': None}, match(path(1, 200)), 5, 0
            )
            self.assertIsNone(result['z'])

    def test_structure_buffer_cannot_overrule_reviewed_surface_level(self):
        result = HeightGuard([evidence()]).choose(
            {'id': 'di-1', 'z': None}, match(path(1, 200)), 5, 0, structure_hint=True
        )
        self.assertEqual(result['z'], 200)
        self.assertEqual(result['confidence'], 'reviewed_level_match')

    def test_raw_deck_diagnostic_datum_or_unreviewed_evidence_cannot_approve_z(self):
        for e in (
            evidence(height_meaning='deck_surface'),
            evidence(vertical_datum='unknown'),
            evidence(reviewed=False),
            evidence(source={'dataset': 'compiled-zps', 'record': 'vertex', 'date': '2026-09-30'}),
        ):
            with self.assertRaises(ValueError):
                HeightGuard([e])

    def test_short_large_disagreements_are_not_lost_below_the_ten_metre_screen(self):
        rows = [{'z': 214, 'weight': 1, 'archive': match(path(1, 200))}]
        self.assertEqual(stage.conflict_records(rows), {'1'})

    def test_staging_keeps_di_xy_raw_z_provenance_and_does_not_add_archive_only_geometry(self):
        di, archived = path('di-1', 0), [path(1, 200), path(99, 250, 20)]
        di['sources'] = [{'file': 'DI.zip', 'sha256': 'hash', 'state': '2026-09-30'}]
        original = deepcopy(di)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'snapshots').mkdir()
            (root / 'snapshots/CURRENT').write_text('test')
            with (
                patch.multiple(
                    stage,
                    ROOT=root,
                    di_data=lambda: ([{'polygon': box(-1, -1, 11, 1)}], [di]),
                    archive_data=lambda: ({'acquired': '2026-10-30'}, {}, archived),
                    structure_mask=lambda **kw: (box(50, 50, 60, 60), [], box(50, 50, 60, 60)),
                    load_line=lambda n: {'path': [[0, 0], [10, 0]]},
                    load_decks=lambda root: Decks([]),
                    surface_evidence=lambda rows: None,
                ),
                redirect_stdout(io.StringIO()),
            ):
                result = stage.stage({})
        self.assertEqual(di, original)
        self.assertEqual(len(result['geometry']), 1)
        self.assertEqual(result['geometry'][0]['xy'], [(0, 0), (10, 0)])
        self.assertEqual(result['geometry'][0]['raw_z'], [0, 0])
        self.assertEqual(result['geometry'][0]['sources'], di['sources'])
        self.assertTrue(
            all(
                r['z'] == 200 and r['height_source']['dataset'] == 'archive' for r in result['height_samples']
            )
        )
        self.assertTrue(
            all(
                'record' in r['height_source'] and 'date' in r['height_source']
                for r in result['height_samples']
            )
        )
        self.assertEqual(result['overall']['selected_by_source_m'], {'di': 0, 'archive': 10, 'deck': 0})
        self.assertEqual(len(result['lines']), 5)

    def test_route_coverage_matches_archive_to_di_heading_not_route_heading(self):
        dy = math.tan(math.radians(14))
        di = {'id': 'di-1', 'coords': [(-1, -dy, 0), (1, dy, 0)], 'attrs': {}, 'sources': []}
        archived = {'id': 1, 'coords': [(-1, dy, 200), (1, -dy, 200)], 'attrs': {}, 'sources': []}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'snapshots').mkdir()
            (root / 'snapshots/CURRENT').write_text('test')
            with (
                patch.multiple(
                    stage,
                    ROOT=root,
                    di_data=lambda: ([{'polygon': box(-2, -2, 2, 2)}], [di]),
                    archive_data=lambda: ({'acquired': '2026-10-30'}, {}, [archived]),
                    structure_mask=lambda **kw: (box(50, 50, 60, 60), [], box(50, 50, 60, 60)),
                    load_line=lambda n: {'path': [[-1, 0], [1, 0]]},
                    load_decks=lambda root: Decks([]),
                    surface_evidence=lambda rows: None,
                ),
                redirect_stdout(io.StringIO()),
            ):
                result = stage.stage({})
        self.assertTrue(all(r['selected_by_source_m']['archive'] == 0 for r in result['lines']))


def deck_record(identity='deck-1', z=200):
    return {
        'id': identity,
        'ring': [(0, -2, z), (10, -2, z), (10, 2, z), (0, 2, z)],
        'level': 1,
        'source': {'record': identity, 'date': '2026-09-30', 'file': 'fixture.gpkg', 'sha256': 'fixture'},
    }


def offset_fact(value=0.2, **updates):
    return {
        'id': 'offset-1',
        'metres': value,
        'scope': 'all',
        'source': 'test fixture',
        'date': '2026-10-30',
        **updates,
    }


class DeckFallback(unittest.TestCase):
    def choose(self, decks, archived=(), di_z=None):
        return HeightGuard().choose(
            {'id': 'di-1', 'z': di_z},
            match(*archived),
            5,
            0,
            structure_hint=True,
            decks=decks.candidates(5, 0, 'di-1'),
        )

    def test_deck_only_uses_survey_height_plus_fact_and_keeps_provenance(self):
        result = self.choose(Decks([deck_record()], [offset_fact()]))
        self.assertAlmostEqual(result['z'], 200.2)
        self.assertEqual(result['height_source']['dataset'], 'deck')
        self.assertEqual(result['height_source']['record'], 'deck-1')
        self.assertEqual(result['height_source']['rail_above_deck_m'], 0.2)
        self.assertEqual(result['height_source']['offset_fact_ids'], ['offset-1'])

    def test_archive_has_priority_when_it_agrees_with_the_deck(self):
        result = self.choose(Decks([deck_record()], [offset_fact(0)]), [path(1, 200)])
        self.assertEqual(result['height_source']['dataset'], 'archive')

    def test_archive_only_structure_contradicted_by_deck_is_not_selected(self):
        result = self.choose(Decks([deck_record(z=214)], [offset_fact(0)]), [path(1, 200)])
        self.assertIsNone(result['z'])
        self.assertIn('archive_deck_height_disagreement', result['review_flags'])
        self.assertEqual({c['dataset'] for c in result['candidates']}, {'archive', 'deck'})

    def test_numeric_di_wins_even_when_archive_and_deck_disagree(self):
        result = self.choose(Decks([deck_record(z=214)], [offset_fact(0)]), [path(1, 200)], di_z=215)
        self.assertEqual(result['z'], 215)
        self.assertEqual(result['height_source']['dataset'], 'di')
        self.assertIn('archive_deck_height_disagreement', result['review_flags'])

    def test_several_deck_levels_stay_ambiguous(self):
        result = self.choose(Decks([deck_record('lower', 200), deck_record('upper', 210)], [offset_fact(0)]))
        self.assertIsNone(result['z'])
        self.assertIn('ambiguous_deck_levels', result['review_flags'])

    def test_missing_or_conflicting_offset_facts_are_not_guessed(self):
        for facts, flag in [
            ([], 'deck_rail_offset_missing'),
            ([offset_fact(0), offset_fact(0.2, id='offset-2')], 'ambiguous_rail_offset_facts'),
        ]:
            result = self.choose(Decks([deck_record()], facts))
            self.assertIsNone(result['z'])
            self.assertIn(flag, result['review_flags'])

    def test_slope_is_interpolated_from_survey_vertices(self):
        record = deck_record()
        record['ring'] = [(0, -2, 200), (10, -2, 201), (10, 2, 201), (0, 2, 200)]
        result = self.choose(Decks([record], [offset_fact()]))
        self.assertAlmostEqual(result['z'], 200.7)

    def test_nearby_deck_is_not_extrapolated_as_a_deck_only_fallback(self):
        decks = Decks([deck_record()], [offset_fact()])
        candidates = decks.candidates(5, 3, 'di-1')
        self.assertTrue(candidates)
        self.assertFalse(candidates[0]['inside'])
        result = HeightGuard().choose({'id': 'di-1', 'z': None}, match(), 5, 3, decks=candidates)
        self.assertIsNone(result['z'])

    def test_all_four_user_approved_style_facts_are_read_from_truth(self):
        facts = json.loads((ROOT / 'data/truth.json').read_text(encoding='utf-8'))['trackHeights'][
            'railAboveDeck'
        ]
        for style, value in [('embedded', 0), ('panels', 0), ('grass', 0.04), ('ballast', 0.17)]:
            regions = [{'style': style, 'polygon': box(-1, -3, 11, 3)}]
            result = self.choose(Decks([deck_record()], facts, regions))
            self.assertAlmostEqual(result['z'], 200 + value)
            self.assertEqual(result['height_source']['offset_fact_ids'], ['rail-above-deck-' + style])
        default = self.choose(Decks([deck_record()], facts))
        self.assertEqual(default['z'], 200)
        self.assertIn('track_style_defaulted_panels', default['review_flags'])

    def test_a_small_disagreement_does_not_blacklist_an_entire_archive_record(self):
        rows = [{'z': 200.5, 'weight': 20, 'archive': match(path(1, 200))}]
        self.assertEqual(stage.conflict_records(rows), set())

    def test_all_surface_classes_check_archive_at_the_surveyed_track_level(self):
        for cls in ('tram', 'road', 'sidewalk', 'island', 'paved', 'green'):
            record = {**deck_record(z=214), 'class': cls}
            decks = Decks([deck_record('track-level', 214), record], [offset_fact(0)])
            result = self.choose(decks, [path(1, 200)])
            self.assertIsNone(result['z'], cls)
            flag = (
                'archive_deck_height_disagreement' if cls == 'deck' else 'archive_surface_height_disagreement'
            )
            self.assertIn(flag, result['review_flags'])

    def test_ground_road_and_water_under_bridge_never_validate_archived_ground_z(self):
        ground = {**deck_record('road-under', 180), 'class': 'road', 'level': 0}
        water = {**deck_record('river', 180), 'class': 'water', 'level': 0}
        track = {**deck_record('tram-on-bridge', 194), 'class': 'tram'}
        decks = Decks([track, ground, water], [offset_fact(0)])
        candidates = decks.candidates(5, 0, 'di-1', structure_hint=True)
        self.assertEqual([c['track_level'] for c in candidates], [1, 1, 1])
        self.assertEqual(candidates[1]['excluded'], 'survey_level_mismatch')
        self.assertEqual(candidates[2]['excluded'], 'non_track_surface')
        result = HeightGuard().choose(
            {'id': 'di-1', 'z': None}, match(path(1, 180)), 5, 0, structure_hint=True, decks=candidates
        )
        self.assertIsNone(result['z'])
        self.assertIn('archive_surface_height_disagreement', result['review_flags'])

    def test_no_structure_level_proof_keeps_archive_for_review_even_if_ground_agrees(self):
        for cls in ('road', 'tram', 'water'):
            ground = {**deck_record('under', 180), 'class': cls, 'level': 0}
            decks = Decks([ground], [offset_fact(0)])
            candidates = decks.candidates(5, 0, 'di-1', structure_hint=True)
            result = HeightGuard().choose(
                {'id': 'di-1', 'z': None}, match(path(1, 180)), 5, 0, structure_hint=True, decks=candidates
            )
            self.assertIsNone(result['z'], cls)
            self.assertIn('structure_unverified', result['review_flags'])

    def test_nearby_wrong_level_surface_keeps_its_exclusion(self):
        record = {**deck_record('under', 180), 'class': 'road', 'level': 0}
        record['ring'] = [(x, y + 5, z) for x, y, z in record['ring']]
        decks = Decks([deck_record('bridge', 194), record], [offset_fact(0)])
        candidates = decks.candidates(5, 1.6, 'di-1', structure_hint=True)
        self.assertFalse(candidates[1]['inside'])
        result = HeightGuard().choose(
            {'id': 'di-1', 'z': None}, match(path(1, 180)), 5, 1.6, structure_hint=True, decks=candidates
        )
        self.assertEqual(result['candidates'][-1]['excluded'], 'survey_level_mismatch')
        self.assertIsNone(result['z'])

    def test_deck_above_covering_ground_tram_cannot_supply_that_tracks_level(self):
        ground = {**deck_record('ground-track', 180), 'class': 'tram', 'level': 0}
        decks = Decks([ground, deck_record('overhead', 194)], [offset_fact(0)])
        candidates = decks.candidates(5, 0, 'di-1', structure_hint=True)
        self.assertTrue(all(c['track_level'] is None for c in candidates))
        result = HeightGuard().choose(
            {'id': 'di-1', 'z': None}, match(path(1, 194)), 5, 0, structure_hint=True, decks=candidates
        )
        self.assertIsNone(result['z'])

    def test_roof_cannot_validate_track_height_even_with_the_same_level_code(self):
        track = {**deck_record('tram', 200), 'class': 'tram'}
        track['ring'] = [(x, y, None) for x, y, z in track['ring']]
        roof = {**deck_record('roof', 180), 'class': 'roof'}
        decks = Decks([track, roof], [offset_fact(0)])
        candidates = decks.candidates(5, 0, 'di-1', structure_hint=True)
        result = HeightGuard().choose(
            {'id': 'di-1', 'z': None}, match(path(1, 180)), 5, 0, structure_hint=True, decks=candidates
        )
        self.assertEqual(result['candidates'][-1]['excluded'], 'non_track_surface')
        self.assertIsNone(result['z'])

    def test_overlapping_tram_levels_stay_ambiguous_without_an_osm_structure_tag(self):
        lower = {**deck_record('lower', 180), 'class': 'tram', 'level': 0}
        upper = {**deck_record('upper', 194), 'class': 'tram', 'level': 1}
        decks = Decks([lower, upper], [offset_fact(0)])
        candidates = decks.candidates(5, 0, 'di-1')
        result = HeightGuard().choose({'id': 'di-1', 'z': None}, match(path(1, 180)), 5, 0, decks=candidates)
        self.assertIsNone(result['z'])
        self.assertIn('track_zps_level_unverified', result['review_flags'])

    def test_tunnel_without_di_stays_on_hold_and_local_review_can_resolve_it(self):
        args = ({'id': 'di-1', 'z': None}, match(path(1, 200)), 5, 0)
        result = HeightGuard().choose(*args, tunnel_hint=True)
        self.assertIsNone(result['z'])
        self.assertIn('tunnel_unverified', result['review_flags'])
        reviewed = HeightGuard([evidence(kind='tunnel', level=-1)]).choose(*args, tunnel_hint=True)
        self.assertEqual(reviewed['z'], 200)
        self.assertIn('tunnel_unverified', reviewed['review_flags'])
        numeric = HeightGuard().choose({'id': 'di-1', 'z': 201}, args[1], 5, 0, tunnel_hint=True)
        self.assertEqual(numeric['z'], 201)

    def test_non_deck_survey_can_validate_but_does_not_supply_deck_fallback(self):
        decks = Decks([{**deck_record(), 'class': 'tram'}], [offset_fact(0)])
        self.assertEqual(self.choose(decks, [path(1, 200)])['z'], 200)
        self.assertIsNone(self.choose(decks)['z'])

    def test_loader_discovers_new_lines_and_keeps_all_surface_classes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data').mkdir()
            (root / 'snapshots').mkdir()
            (root / 'data/MANIFEST.json').write_text(json.dumps({'snapshot': 'test', 'files': {}}))
            (root / 'snapshots/test.json').write_text(json.dumps({'groups': []}))
            (root / 'data/truth.json').write_text('{}')
            for line, cls in [(9, 'road'), (37, 'tram'), (123, 'water')]:
                record = deck_record()
                area = {'c': cls, 'l': 1, 'r': record['ring']}
                (root / f'data/line{line}.dtm.json').write_text(json.dumps({'areas': [area]}))
            decks = load_decks(root)
        self.assertEqual({r['class'] for r in decks.records}, {'road', 'tram', 'water'})
        self.assertEqual(len(decks.records), 3)

    def test_structure_masks_distinguish_bridge_tunnel_covered_and_negative_layer(self):
        from geo import Frame

        lat, lon = Frame().ll(0, 0)
        geometry = [{'lat': float(lat), 'lon': float(lon)}, {'lat': float(lat) + 0.0001, 'lon': float(lon)}]
        ways = [
            {'id': i, 'tags': tags, 'geometry': geometry}
            for i, tags in enumerate(
                [{'bridge': 'yes'}, {'tunnel': 'yes'}, {'covered': 'yes'}, {'layer': '-1'}]
            )
        ]
        with patch('osm_local.ways', return_value=ways):
            all_mask, ids, tunnel_mask = research.structure_mask(separate_tunnels=True)
        self.assertEqual(ids, [0, 1, 2, 3])
        self.assertFalse(all_mask.is_empty)
        self.assertFalse(tunnel_mask.is_empty)
        with patch('osm_local.ways', return_value=ways[:1]):
            _, _, tunnel_mask = research.structure_mask(separate_tunnels=True)
        self.assertTrue(tunnel_mask.is_empty)


@unittest.skipUnless(
    (ROOT / 'raw/dtmp-tracks/provenance.json').exists(), 'fetch snapshot for real source regression'
)
class PinnedBridge(unittest.TestCase):
    def test_trojsky_ids_use_di_and_do_not_import_archived_ground_z(self):
        _, di = di_data()
        _, _, archived = archive_data()
        current = Segments([p for p in di if p['id'] == '1000413716080'])
        index = Segments([p for p in archived if p['id'] == 5168282])
        x, y = 1422.058, 2620.908
        row = min(zip(current.rows, current.geoms), key=lambda r: r[1].distance(Point(x, y)))[0]
        ux, uy = (row['b'][0] - row['a'][0]) / row['length'], (row['b'][1] - row['a'][1]) / row['length']
        hit = current.match(x, y, ux, uy)
        m = index.match(hit['x'], hit['y'], ux, uy, details=True)
        self.assertEqual(m['id'], 5168282)
        self.assertAlmostEqual(hit['z'], 194.398, delta=0.02)
        self.assertAlmostEqual(m['z'], 180.412, delta=0.02)
        self.assertAlmostEqual(m['distance'], 0.137, delta=0.02)
        decks = load_decks(ROOT).candidates(hit['x'], hit['y'], hit['id'], structure_hint=True)
        self.assertTrue(decks)
        self.assertTrue(any(c.get('z') is not None for c in decks))
        result = HeightGuard().choose(hit, m, hit['x'], hit['y'], structure_hint=True, decks=decks)
        self.assertEqual(result['z'], hit['z'])
        self.assertEqual(result['height_source']['dataset'], 'di')
        missing_di = {**hit, 'z': None}
        fallback = HeightGuard().choose(missing_di, m, hit['x'], hit['y'], structure_hint=True, decks=decks)
        self.assertIsNone(fallback['z'])
        self.assertTrue(
            {
                'archive_surface_height_disagreement',
                'archive_deck_height_disagreement',
                'structure_unverified',
            }.intersection(fallback['review_flags'])
        )
        examples = [{'xy': [hit['x'], hit['y']]}]
        surface_evidence(examples)
        self.assertTrue(
            any(
                194.4 < z < 194.6
                for e in examples[0]['compiled_survey_deck_evidence']
                for z in e['nearest_vertex_z']
                if z is not None
            )
        )


if __name__ == '__main__':
    unittest.main(verbosity=2)
