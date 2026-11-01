"""Construction-sensitive survey guards: python -P -E tools/test_track_context.py."""
import unittest

from shapely.geometry import box

from track_context import TrackContext
from track_heights import HeightGuard
from track_decks import Decks
from test_track_heights import deck_record, offset_fact, match, path


class Construction(unittest.TestCase):
    def choose(self, kind, cls='tram', archived=200.7, conflicts=()):
        record = {**deck_record(z=200), 'class':cls, 'level':0}
        surfaces = Decks([record], [offset_fact(0)]).candidates(5,0,'di-1')
        return HeightGuard(conflicts=conflicts).choose({'id':'di-1','z':None},
            match(*([] if archived is None else [path(1,archived)])),5,0,
            decks=surfaces,construction={'kind':kind})

    def test_open_and_unknown_outlines_neither_supply_nor_veto_archive(self):
        for kind in ('open','unknown'):
            result = self.choose(kind)
            self.assertEqual(result['z'],200.7)
            self.assertIn('archive_surface_height_disagreement',result['review_flags'])
            self.assertIsNone(self.choose(kind,archived=None)['z'])
            self.assertIsNone(self.choose(kind,conflicts=['1'])['z'])
        decks = Decks([deck_record('a',200),deck_record('b',201)],[offset_fact(0)])
        r = HeightGuard().choose({'id':'di-1','z':None},match(path(1,200.7)),5,0,
                                  decks=decks.candidates(5,0,'di-1'),construction={'kind':'open'})
        self.assertEqual(r['z'],200.7)

    def test_paved_outline_supplies_missing_height_and_holds_stale_archive(self):
        self.assertIsNone(self.choose('paved')['z'])
        self.assertEqual(self.choose('paved',archived=None)['z'],200)
        self.assertEqual(self.choose('paved',archived=200.1)['z'],200.1)
        self.assertIsNone(self.choose('paved',cls='green',archived=None)['z'])
        self.assertEqual(self.choose('paved',cls='green')['z'],200.7)

    def test_rail_bridge_and_independently_wrong_level_deck_cannot_anchor(self):
        rail = {**deck_record('railway',210), 'class':'rail'}
        ground = {**deck_record('tram',200), 'class':'tram','level':0}
        decks = Decks([rail,deck_record('overpass',210),ground],[offset_fact(0)])
        candidates = decks.candidates(5,0,'di-1',di_z=200)
        self.assertEqual(candidates[0]['excluded'],'non_track_surface')
        self.assertEqual(candidates[1]['excluded'],'surface_on_other_level')
        self.assertEqual(candidates[2]['track_level'],0)
        self.assertEqual(candidates[2]['track_level_sources'],['tram'])

    def test_generic_tram_area_and_default_drawing_do_not_prove_pavement(self):
        context = TrackContext()
        survey = [{'id':'axis','class':'tram','level':0,'inside':True}]
        self.assertEqual(context.classify(0,0,surfaces=survey)['kind'],'unknown')
        survey[0]['class'] = 'road'
        self.assertEqual(context.classify(0,0,surfaces=survey)['kind'],'paved')
        survey[0]['excluded'] = 'surface_on_other_level'
        self.assertEqual(context.classify(0,0,surfaces=survey)['kind'],'unknown')

    def test_truth_grass_wins_over_generic_road_and_conflicts_stay_unknown(self):
        grass = {'style':'grass','polygon':box(-1,-1,1,1)}
        context = TrackContext(regions=[grass])
        self.assertEqual(context.classify(0,0,surfaces=[{'class':'road','inside':True,'level':0}])['kind'],'open')
        context = TrackContext(regions=[grass,{'style':'panels','polygon':box(-1,-1,1,1)}])
        self.assertEqual(context.classify(0,0)['kind'],'unknown')


if __name__ == '__main__':
    unittest.main(verbosity=2)
