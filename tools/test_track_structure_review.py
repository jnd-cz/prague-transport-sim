"""Structure grouping and explicit approvals: python -P -E tools/test_track_structure_review.py."""
import unittest
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))

import numpy as np

from track_heights import HeightGuard
from track_structure_review import Structures, grouped, review, record_date, findings
from track_span_evidence import SpanEvidence, from_reviews
from track_terrain_fallback import ordinary_fallback
from test_track_heights import match, path, offset_fact


def approval(**updates):
    return {'id':'bridge-reviewed','kind':'tunnel','level':-1,'reviewed':True,
            'vertical_datum':'Bpv','height_meaning':'top_of_rail',
            'source':{'dataset':'expert_review','record':'review-url','date':'2026-11-01'},
            'profiles':[{'xy':[[0,0],[10,0]],'di_ids':['di-1'],
                         'rule':{'type':'linear','ends':[200,202]}}],**updates}


class SpanReviews(unittest.TestCase):
    def test_review_answers_import_as_scoped_evidence_or_stay_held(self):
        span = {'id':'s','profile':[{'xy':[0,0],'surfaces':[{'z':200,'rail_height_eligible':True}]},
                                  {'xy':[10,0],'surfaces':[{'z':202,'rail_height_eligible':True}]}],
                'approval_profile':{'xy':[[0,0],[10,0]],'di_ids':['di-1'],'rule':{'type':'needs_explicit_review'}}}
        finding = {'kind':'trackheight','id':'bridge-1','decision':{'span_ids':['s'],'structure':{'kind':'bridge'}},'spans':[span]}
        answer = {'decision_id':'bridge-1','span_ids':['s'],'v':'archive profile ok','note':'','t':1761955200000}
        get = lambda a:from_reviews({'items':{'pin':a}},{'findings':[finding]},'reviews/line17.json')
        imported = get(answer)['span_reviews'][0]
        expected = approval(id='review-bridge-1',kind='deck',level=1,
                            source={'dataset':'expert_review','record':'reviews/line17.json#pin','date':'2025-11-01','who':'user'},
                            profiles=[{'xy':[[0,0],[10,0]],'di_ids':['di-1'],'rule':{'type':'archive'}}])
        self.assertEqual(imported,expected)
        self.assertEqual(SpanEvidence([imported]).at('di-1',5,0,[{'z':201}]),SpanEvidence([expected]).at('di-1',5,0,[{'z':201}]))
        survey = get({**answer,'v':'follows survey surface'})['span_reviews'][0]
        self.assertEqual(SpanEvidence([survey]).at('di-1',5,0,[])[0]['z'],201)
        for changed in ({'note':'check level'}, {'v':'unsure'}, {'v':'other level (deck / under)'}, {'span_ids':['changed']}):
            self.assertFalse(get({**answer,**changed})['span_reviews'])
            self.assertTrue(get({**answer,**changed})['held'])

    def test_findings_keep_all_spans_and_pin_the_longest(self):
        spans = [{'id':'a','length_m':10,'profile':[{'xy':[0,0]}], 'from_stop':'A','to_stop':'B'},
                 {'id':'b','length_m':30,'profile':[{'xy':[4,5]},{'xy':[6,7]}], 'from_stop':'B','to_stop':'C'}]
        decision = {'id':'bridge-1','status':'review','span_ids':['a','b'], 'structure':{'kind':'bridge'}}
        result = findings({'snapshot':'test','spans':spans,'decisions':[decision]})
        self.assertEqual(len(result['findings']),1)
        item = result['findings'][0]
        self.assertEqual((item['x'],item['y']),(6,7))
        self.assertEqual([s['id'] for s in item['spans']],['a','b'])
        self.assertEqual(item['id'],'bridge-1')

    def test_terrain_last_fallback_has_provenance_and_never_fills_a_structure(self):
        row = {'status':'review','review_flags':['no_usable_height'],'di_id':'di-1','xy':[5,0],
               'construction':{'styles':['grass']}}
        r = ordinary_fallback(row,200,[offset_fact(.04,styles=['grass'])])
        self.assertEqual(r['z'],200.04)
        self.assertEqual(r['height_source']['dataset'],'ipr-dtm')
        self.assertIn('terrain_fallback_unvalidated',r['review_flags'])
        for flag in ('structure_hint','tunnel_unverified','track_zps_level_unverified','known_archive_disagreement'):
            self.assertIsNone(ordinary_fallback({**row,'review_flags':['no_usable_height',flag]},200,[offset_fact()]))
        self.assertIsNone(ordinary_fallback({**row,'status':'selected'},200,[offset_fact()]))

    def test_proposals_unreviewed_profiles_and_missing_source_cannot_approve(self):
        for value in (approval(reviewed=False),approval(source={}),approval(vertical_datum='unknown'),
                      approval(source={'dataset':'archive','record':'raw-candidate','date':'2026-11-01'})):
            with self.assertRaises(ValueError):
                SpanEvidence([value])

    def test_archive_record_dates_are_rendered_as_dates(self):
        self.assertEqual(record_date({'attributes':{'DAT_ZMENA':1205107200000}}),'2008-03-10')
        self.assertIsNone(record_date({}))

    def test_building_passage_with_numeric_di_is_kept_as_a_resolved_review_item(self):
        structures = Structures([{'id':1,'coords':[(0,0,None),(10,0,None)],
                                  'attrs':{'tunnel':'building_passage'}}])
        rows = [{'line':17,'direction':'path','s':2.5,'weight_m':5,'xy':[2.5,0],
                 'status':'selected','height_source':{'dataset':'di'},'review_flags':['tunnel_unverified']}]
        self.assertEqual(len(grouped(rows,structures)),1)

    def test_approved_profile_supplies_missing_height_but_never_overrides_di(self):
        guard = HeightGuard(span_reviews=[approval()])
        r = guard.choose({'id':'di-1','z':None},match(),5,0,tunnel_hint=True)
        self.assertEqual(r['z'],201)
        self.assertEqual(r['confidence'],'reviewed_span_rule')
        self.assertIn('tunnel_unverified',r['review_flags'])
        numeric = guard.choose({'id':'di-1','z':205},match(),5,0,tunnel_hint=True)
        self.assertEqual(numeric['z'],205)
        self.assertIn('reviewed_evidence_disagrees_with_di',numeric['review_flags'])
        for identity,x,y in [('other',5,0),('di-1',5,2),('di-1',-2,0)]:
            self.assertIsNone(guard.choose({'id':identity,'z':None},match(),x,y,tunnel_hint=True)['z'])

    def test_conflicting_profiles_stay_held_and_archive_review_preserves_source(self):
        a = approval()
        b = approval(id='other-review')
        b['profiles'][0]['rule']['ends'] = [210,212]
        r = HeightGuard(span_reviews=[a,b]).choose({'id':'di-1','z':None},match(),5,0,tunnel_hint=True)
        self.assertIn('conflicting_level_evidence',r['review_flags'])
        a['profiles'][0]['rule'] = {'type':'archive'}
        r = HeightGuard(span_reviews=[a]).choose({'id':'di-1','z':None},match(path(1,200)),5,0,tunnel_hint=True)
        self.assertEqual(r['z'],200)
        self.assertEqual(r['height_source']['dataset'],'archive')
        self.assertEqual(r['height_source']['id'],1)
        self.assertEqual(r['height_source']['review_source']['record'],'review-url')

    def test_adjacent_parallel_ways_group_but_other_structure_and_direction_do_not(self):
        ways = [{'id':i,'coords':[(0,y,None),(10,y,None)],'attrs':tags}
                for i,y,tags in [(1,0,{'bridge':'yes'}),(2,3,{'bridge':'yes'}),(3,0,{'tunnel':'yes'})]]
        structures = Structures(ways)
        self.assertEqual(structures.by_way['1'],structures.by_way['2'])
        self.assertNotEqual(structures.by_way['1'],structures.by_way['3'])
        rows = [{'line':17,'direction':direction,'s':s,'weight_m':5,'xy':[s,0],
                 'status':status,'review_flags':['structure_unverified']}
                for direction,s,status in [('path',2.5,'review'),('path',7.5,'selected'),
                                           ('pathBack',2.5,'review'),('pathBack',7.5,'review')]]
        runs = grouped(rows,structures)
        self.assertEqual([len(r) for _,r in runs],[1,2])

    def test_report_has_both_stop_names_and_does_not_turn_terrain_into_rail_evidence(self):
        structures = Structures([{'id':1,'coords':[(0,0,None),(10,0,None)],'attrs':{'tunnel':'yes'}}])
        rows = [{'line':17,'direction':direction,'s':s,'weight_m':5,'xy':[x,0],
                 'status':'review','review_flags':['tunnel_unverified'],'di_id':'di-1','raw_di_z':None,
                 'candidates':[]} for direction in ('path','pathBack') for s,x in [(2.5,2.5),(7.5,7.5)]]
        class Terrain:
            def sample(self,e,n):
                return np.full(len(e),190)
        result = review({'route_samples':rows,'archive_sources':{},'snapshot':'test','frame':{}},
            structures,Terrain(),{17:{'path':[[0,0],[10,0]],'pathBack':[[10,0],[0,0]],
                                     'stops':[{'name':'A','s':0},{'name':'B','s':10}]}})
        self.assertEqual(len(result['decisions']),1)
        self.assertEqual(result['spans'][0]['from_stop'],'A')
        self.assertEqual(result['spans'][1]['from_stop'],'B')
        self.assertEqual(result['spans'][1]['to_stop'],'A')
        self.assertEqual(result['spans'][0]['proposal']['rule'],'independent_height_required')
        self.assertEqual(result['spans'][0]['terrain']['height_meaning'],'bare_earth')


if __name__=='__main__':
    unittest.main(verbosity=2)
