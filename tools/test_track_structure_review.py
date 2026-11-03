"""Structure grouping and explicit approvals: python -P -E tools/test_track_structure_review.py."""
import unittest
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parent))

import numpy as np

from track_heights import HeightGuard
from track_structure_review import Structures, grouped, review, record_date, findings, queue_text
from track_span_evidence import SpanEvidence, from_reviews, hydrate_findings, truth_answers, dips
from track_terrain_fallback import ordinary_fallback
from test_track_heights import match, path, offset_fact


def approval(**updates):
    return {'id':'bridge-reviewed','kind':'tunnel','level':-1,'reviewed':True,
            'vertical_datum':'Bpv','height_meaning':'top_of_rail',
            'source':{'dataset':'expert_review','record':'review-url','date':'2026-11-01'},
            'profiles':[{'xy':[[0,0],[10,0]],'di_ids':['di-1'],
                         'rule':{'type':'linear','ends':[200,202]}}],**updates}


class SpanReviews(unittest.TestCase):
    def test_referenced_span_queue_checks_hash_and_scope(self):
        queue = {'snapshot':'test','spans':[{'id':'s','profile':[]}]}
        raw = queue_text(queue).encode('utf-8')
        payload = {'snapshot':'test','span_file':'queue.json','span_sha256':hashlib.sha256(raw).hexdigest(),
                   'findings':[{'id':'one','decision':{'span_ids':['s']}}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'queue.json'
            path.write_bytes(raw)
            self.assertEqual(hydrate_findings(payload,tmp)['findings'][0]['spans'][0]['id'],'s')
            path.write_bytes(raw+b' ')
            with self.assertRaisesRegex(ValueError,'differs'):
                hydrate_findings(payload,tmp)
            changed = queue_text({'snapshot':'other','spans':queue['spans']}).encode('utf-8')
            path.write_bytes(changed)
            with self.assertRaisesRegex(ValueError,'snapshot'):
                hydrate_findings({**payload,'span_sha256':hashlib.sha256(changed).hexdigest()},tmp)
            missing = queue_text({'snapshot':'test','spans':[]}).encode('utf-8')
            path.write_bytes(missing)
            with self.assertRaisesRegex(ValueError,'missing'):
                hydrate_findings({**payload,'span_sha256':hashlib.sha256(missing).hexdigest()},tmp)

    def test_real_findings_explain_every_offered_answer(self):
        path = Path(__file__).resolve().parent.parent/'reports/review/track-heights.json'
        if not path.exists():
            self.skipTest('generate the review findings first')
        source = json.loads(path.read_text(encoding='utf-8'))
        if source.get('span_file'):
            hydrated = hydrate_findings(source)
            self.assertEqual(len(hydrated['findings']),len(source['findings']))
        else:
            queue = json.loads(path.with_name('track-height-spans.json').read_text(encoding='utf-8'))
            hydrated = findings(queue,inline=True)
        for item in hydrated['findings']:
            self.assertIn('archive profile ok',item['options'])
            self.assertIn('unsure',item['options'])
            for choice in ('archive profile ok','archive, bridged over a dip','follows survey surface'):
                answer = {'decision_id':item['id'],'span_ids':item['decision']['span_ids'],
                          'v':choice,'note':'','t':1793577600000}
                result = from_reviews({'items':{'pin':answer}},{'findings':[item]},'test')
                reason = result['held'][0]['reason'] if result['held'] else None
                self.assertEqual(item['answer_explanations'][choice],reason,(item['id'],choice))
                if choice != 'archive profile ok':
                    self.assertEqual(choice in item['options'],reason is None,item['id'])
                elif reason:
                    self.assertTrue(reason,item['id'])
            for choice in ('other level (deck / under)','unsure'):
                answer = {'decision_id':item['id'],'span_ids':item['decision']['span_ids'],
                          'v':choice,'note':'','t':1793577600000}
                self.assertTrue(from_reviews({'items':{'pin':answer}},{'findings':[item]},'test')['held'])

    def test_review_answers_import_as_scoped_evidence_or_stay_held(self):
        span = {'id':'s','start_s':0,'length_m':10,
                'profile':[{'s':0,'xy':[0,0],'archive':[{'z':200}],'surfaces':[{'z':200,'rail_height_eligible':True}]},
                           {'s':10,'xy':[10,0],'archive':[{'z':200.2}],'surfaces':[{'z':200.2,'rail_height_eligible':True}]}],
                'approval_profile':{'xy':[[0,0],[10,0]],'di_ids':['di-1'],'rule':{'type':'needs_explicit_review'}}}
        finding = {'kind':'trackheight','id':'bridge-1','decision':{'span_ids':['s'],'structure':{'kind':'bridge'}},'spans':[span]}
        answer = {'decision_id':'bridge-1','span_ids':['s'],'v':'archive profile ok','note':'','t':1761955200000}
        get = lambda a:from_reviews({'items':{'pin':a}},{'findings':[finding]},'reviews/line17.json')
        imported = get(answer)['span_reviews'][0]
        expected = approval(id='review-bridge-1',kind='deck',level=1,
                            source={'dataset':'expert_review','record':'reviews/line17.json#pin','date':'2025-11-01','who':'user'},
                            answer='archive profile ok',
                            profiles=[{'xy':[[0,0],[10,0]],'di_ids':['di-1'],'rule':{'type':'archive'}}])
        self.assertEqual(imported,expected)
        self.assertEqual(SpanEvidence([imported]).at('di-1',5,0,[{'z':201}]),SpanEvidence([expected]).at('di-1',5,0,[{'z':201}]))
        span['profile'][0]['archive'].append({'z':201})
        self.assertFalse(get(answer)['span_reviews'])
        span['profile'][0]['archive'].pop()
        survey = get({**answer,'v':'follows survey surface'})['span_reviews'][0]
        self.assertAlmostEqual(SpanEvidence([survey]).at('di-1',5,0,[])[0]['z'],200.1)
        self.assertAlmostEqual(HeightGuard(span_reviews=[survey]).choose({'id':'di-1','z':None},match(),5,0,structure_hint=True)['z'],200.1)
        self.assertEqual(HeightGuard(span_reviews=[survey]).choose({'id':'di-1','z':205},match(),5,0,structure_hint=True)['z'],205)
        span['profile'][0]['surfaces'].append({'id':'different','z':200.05,'rail_height_eligible':True})
        self.assertFalse(get({**answer,'v':'follows survey surface'})['span_reviews'])
        span['profile'][0]['surfaces'].pop()
        for changed in ({'note':'check level'}, {'v':'unsure'}, {'v':'other level (deck / under)'}, {'span_ids':['changed']}):
            self.assertFalse(get({**answer,**changed})['span_reviews'])
            self.assertTrue(get({**answer,**changed})['held'])
        stale = from_reviews({'items':{'pin':{**answer,'span_sha256':'old'}}},
                             {'span_sha256':'new','findings':[finding]},'reviews/line17.json')
        self.assertEqual(stale['held'][0]['reason'],'missing or changed decision scope')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'answers.json').write_text(json.dumps({'items':{'pin':answer}}),encoding='utf-8')
            (root/'findings.json').write_text(json.dumps({'findings':[finding]}),encoding='utf-8')
            subprocess.run([sys.executable,'-P','-E',str(Path(__file__).with_name('track_span_evidence.py')),
                '--from-reviews',str(root/'answers.json'),'--findings',str(root/'findings.json'),
                '--output',str(root/'out.json')],check=True,capture_output=True,text=True)
            self.assertEqual(json.loads((root/'out.json').read_text(encoding='utf-8'))['span_reviews'][0]['id'],'review-bridge-1')

    def test_a_dip_in_the_archive_is_bridged_only_when_answered_so(self):
        # (#176: the archive under Modřany's bridge measures the street below, 6 m down for 40 m)
        zs = [200+.02*s for s in range(0,105,5)]
        for s in (40,45,50):
            zs[s//5] = 194
        span = {'id':'s','start_s':0,'length_m':100,
                'profile':[{'s':s,'xy':[s,0],'archive':[{'z':z}],'surfaces':[]} for s,z in zip(range(0,105,5),zs)],
                'approval_profile':{'xy':[[0,0],[100,0]],'di_ids':['di-1'],'rule':{'type':'needs_explicit_review'}}}
        finding = {'kind':'trackheight','id':'bridge-1','decision':{'span_ids':['s'],'structure':{'kind':'bridge'}},'spans':[span]}
        get = lambda v:from_reviews({'items':{'pin':{'decision_id':'bridge-1','span_ids':['s'],'v':v,'note':'','t':1761955200000}}},
                                    {'findings':[finding]},'reviews/line17.json')
        self.assertIn('dips 6.7 m between 35 and 55 m',get('archive profile ok')['held'][0]['reason'])
        entry = get('archive, bridged over a dip')['span_reviews'][0]
        self.assertEqual([b[:4] for b in entry['profiles'][0]['bridged']],[[35,200.7,55,201.1]])
        self.assertAlmostEqual(SpanEvidence([entry]).at('di-1',45,0,[])[0]['z'],200.9)
        self.assertAlmostEqual(SpanEvidence([entry]).at('di-1',80,0,[])[0]['z'],201.6)
        # a drop that never comes back is not a dip: the river under Palackého most
        for p in span['profile'][8:]:
            p['archive'] = [{'z':187.27}]
        self.assertIn('does not come back',get('archive, bridged over a dip')['held'][0]['reason'])
        self.assertTrue(get('archive profile ok')['held'])

    def test_a_dip_is_crossed_on_a_curve_continuing_the_grade_on_both_sides(self):
        # (#184, Hodkovičky: the archive climbs 3 % to the bridge and falls 3 % after it, the street 6 m below)
        zs = [200+.03*s if s <= 50 else 201.5-.03*(s-50) for s in range(0,105,5)]
        for s in (40,45,50,55,60):
            zs[s//5] = 194.5
        span = {'id':'s','start_s':0,'length_m':100,
                'profile':[{'s':s,'xy':[s,0],'archive':[{'z':z}],'surfaces':[]} for s,z in zip(range(0,105,5),zs)],
                'approval_profile':{'xy':[[0,0],[100,0]],'di_ids':['di-1'],'rule':{'type':'needs_explicit_review'}}}
        finding = {'kind':'trackheight','id':'h','decision':{'span_ids':['s'],'structure':{'kind':'bridge'}},'spans':[span]}
        entry = from_reviews({'items':{'pin':{'decision_id':'h','span_ids':['s'],'v':'archive, bridged over a dip','note':'','t':1761955200000}}},
                             {'findings':[finding]},'reviews/line17.json')['span_reviews'][0]
        self.assertEqual(entry['profiles'][0]['bridged'][0][:4],[35,201.05,65,201.05])
        top = SpanEvidence([entry]).at('di-1',50,0,[])[0]['z']
        self.assertAlmostEqual(top,201.05+.03*30/4,places=2)  # (a crest, where the chord is flat)

    def test_a_direction_leaving_the_smooth_other_one_takes_its_heights(self):
        # (#184, Hlavní nádraží: one direction's archive climbs 6.9 m over the tunnel, the other 3.5 m away stays smooth)
        def span(name, direction, y, hump):
            zs = [200+.01*s+(6 if hump and 30 <= s <= 50 else 0) for s in range(0,85,5)]
            return {'id':name,'line':9,'direction':direction,'start_s':0,'length_m':80,
                    'profile':[{'s':s,'xy':[s,y],'archive':[{'z':z}],'surfaces':[]} for s,z in zip(range(0,85,5),zs)],
                    'approval_profile':{'xy':[[0,y],[80,y]],'di_ids':['di-'+name],'rule':{'type':'needs_explicit_review'}}}
        out, back = span('a','path',0,True), span('b','pathBack',3.5,False)
        finding = {'kind':'trackheight','id':'t','decision':{'span_ids':['a','b'],'structure':{'kind':'tunnel'}},'spans':[out,back]}
        get = lambda: from_reviews({'items':{'pin':{'decision_id':'t','span_ids':['a','b'],'v':'archive profile ok','note':'','t':1761955200000}}},
                                   {'findings':[finding]},'reviews/line9.json')
        entry = get()['span_reviews'][0]
        self.assertEqual(entry['profiles'][0]['from_parallel'],[[25,55]])
        self.assertAlmostEqual(SpanEvidence([entry]).at('di-a',40,0,[])[0]['z'],200.4)
        self.assertEqual(entry['profiles'][1]['rule'],{'type':'archive'})  # (the smooth one keeps its archive)
        # (Brusnice: the departure starts 0.15 m off at 25 m, under the 0.3 m trigger; the repair reaches
        # back to where the two are at their usual offset, so no 6 % step is left there)
        out['profile'][5]['archive'] = [{'z':out['profile'][5]['archive'][0]['z']-.15}]
        entry = get()['span_reviews'][0]
        self.assertEqual(entry['profiles'][0]['from_parallel'],[[20,55]])
        samples = entry['profiles'][0]['rule']['samples']
        grades = [(b[1]-a[1])/(b[0]-a[0]) for a,b in zip(samples,samples[1:])]
        self.assertLess(max(abs(g-.01) for g in grades),1e-6)
        for p in back['profile']:  # (the other direction 9 m away is another track: nothing to compare)
            p['xy'] = [p['xy'][0],9]
        self.assertIn('steps up',get()['held'][0]['reason'])

    def test_survey_track_areas_count_on_a_bridge_only_where_they_meet_the_archive(self):
        # (#184, Černý kůň: the tram areas and the deck carry on across the dip, within 0.2 m of the archive)
        zs = [197+.01*s for s in range(0,105,5)]
        for s in (40,45,50,55):
            zs[s//5] = 192.5
        points = [{'s':s,'xy':[s,0],'archive':[{'z':z}],
                   'surfaces':[{'id':f'tram{s}','class':'tram' if s < 40 or s > 55 else 'deck','level':0 if s < 40 or s > 55 else 1,
                                'z':197.1+.01*s,'rail_height_eligible':False,'excluded':'track_zps_level_unverified' if s < 40 or s > 55 else None}]}
                  for s,z in zip(range(0,105,5),zs)]
        span = {'id':'s','start_s':0,'length_m':100,'profile':points,
                'approval_profile':{'xy':[[0,0],[100,0]],'di_ids':['di-1'],'rule':{'type':'needs_explicit_review'}}}
        finding = {'kind':'trackheight','id':'c','decision':{'span_ids':['s'],'structure':{'kind':'bridge'}},'spans':[span]}
        get = lambda: from_reviews({'items':{'pin':{'decision_id':'c','span_ids':['s'],'v':'follows survey surface','note':'','t':1761955200000}}},
                                   {'findings':[finding]},'reviews/line17.json')
        entry = get()['span_reviews'][0]
        self.assertEqual(entry['profiles'][0]['survey_rule'],'track_area_agrees_with_archive')
        self.assertAlmostEqual(SpanEvidence([entry]).at('di-1',50,0,[])[0]['z'],197.6)
        for p in points[12:]:  # (Hodkovičky: the tram area lies 2 m below the archive)
            p['surfaces'][0]['z'] -= 2
        self.assertIn('from the smooth archive',get()['held'][0]['reason'])

    def test_a_dip_starts_where_the_archive_starts_down_the_abutment(self):
        # (#184, Černý kůň inbound: 4-5 % down for 14 m before the steep drop, then 5 m below the deck)
        zs = [200,200,200,199.75,199.5,199.25,195,195,195,200,200,200]
        found,_ = dips([(5*i,z) for i,z in enumerate(zs)])
        self.assertEqual(found,[(2,9)])

    def test_answers_recorded_in_truth_are_scoped_by_lines_not_span_ids(self):
        span = {'id':'s:line22:path:3','line':22,'direction':'path','start_s':0,'length_m':10,
                'profile':[{'s':s,'xy':[s,0],'archive':[{'z':250}],'surfaces':[]} for s in (0,5,10)],
                'approval_profile':{'xy':[[0,0],[10,0]],'di_ids':['di-1'],'rule':{'type':'needs_explicit_review'}}}
        finding = {'kind':'trackheight','id':'unmapped-1','decision':{'span_ids':[span['id']],'structure':{'kind':'unmapped'}},'spans':[span]}
        truth = lambda lines: {'trackHeights':{'reviewAnswers':[{'decision':'unmapped-1','answer':'archive profile ok','lines':lines,
                                                                 'quote':'q','source':'s','date':'2026-11-02'}]}}
        entry = from_reviews(truth_answers(truth([22])),{'findings':[finding]},'data/truth.json')['span_reviews'][0]
        self.assertEqual((entry['source']['date'],entry['source']['record']),('2026-11-02','data/truth.json#trackHeights.reviewAnswers/unmapped-1'))
        self.assertIn('changed decision scope',from_reviews(truth_answers(truth([22,23])),{'findings':[finding]},'t')['held'][0]['reason'])
        # (and the committed answers import on the committed queue)
        root = Path(__file__).resolve().parent.parent
        result = from_reviews(truth_answers(json.loads((root/'data/truth.json').read_text(encoding='utf-8'))),
                              json.loads((root/'reports/review/track-heights.json').read_text(encoding='utf-8')),'data/truth.json')
        self.assertEqual((len(result['span_reviews']),result['held']),(27,[]))

    def test_survey_answer_skips_short_gaps_and_takes_one_height_of_deck_and_road(self):
        # (Palackého most: deck and road at level 1 within 1 cm; an abutment and a point without survey)
        points = [{'s':s,'xy':[s,0],'archive':[{'z':187.27}],
                   'surfaces':[] if s==60 else [{'id':'deck','z':197.8-.001*s,'rail_height_eligible':True},
                                               {'id':'road','z':197.81-.001*s,'rail_height_eligible':True}]}
                  for s in range(0,105,5)]
        span = {'id':'s','start_s':0,'length_m':100,'profile':points,
                'approval_profile':{'xy':[[0,0],[100,0]],'di_ids':['di-1'],'rule':{'type':'needs_explicit_review'}}}
        abutment = {'id':'a','start_s':100,'length_m':6,
                    'profile':[{'s':100+s,'xy':[100+s,0],'archive':[{'z':197.7}],
                                'surfaces':[{'z':197.76,'rail_height_eligible':False,'excluded':'track_zps_level_unverified'}]} for s in (2,5)],
                    'approval_profile':{'xy':[[100,0],[106,0]],'di_ids':['di-2'],'rule':{'type':'needs_explicit_review'}}}
        finding = {'kind':'trackheight','id':'b','decision':{'span_ids':['s','a'],'structure':{'kind':'bridge'}},'spans':[span,abutment]}
        get = lambda: from_reviews({'items':{'pin':{'decision_id':'b','span_ids':['s','a'],'v':'follows survey surface','note':'','t':1761955200000}}},
                                   {'findings':[finding]},'reviews/line17.json')
        entry = get()['span_reviews'][0]
        self.assertEqual(entry['uncovered_spans'],['a'])
        self.assertEqual(entry['profiles'][0]['survey_ids'],['deck','road'])
        self.assertAlmostEqual(SpanEvidence([entry]).at('di-1',60,0,[])[0]['z'],197.75,places=3)  # (55 and 65 m interpolated)
        for s in (55,65):
            points[s//5]['surfaces'] = []
        self.assertIn('a gap of 20 m',get()['held'][0]['reason'])  # (50 to 70 m)

    def test_street_spans_import_at_level_zero_and_a_surveyed_deck_at_its_level(self):
        span = {'id':'s','start_s':0,'length_m':10,
                'profile':[{'s':s,'xy':[s,0],'archive':[{'z':250}],'surfaces':[]} for s in (0,5,10)],
                'approval_profile':{'xy':[[0,0],[10,0]],'di_ids':['di-1'],'rule':{'type':'needs_explicit_review'}}}
        for structure,kind,level in (({'kind':'unmapped'},'surface',0),
                                     ({'kind':'survey_level','tags':{'line22.dtm.json#areas/697':{'level':1}}},'deck',1)):
            finding = {'kind':'trackheight','id':'d','decision':{'span_ids':['s'],'structure':structure},'spans':[span]}
            entry = from_reviews({'items':{'pin':{'decision_id':'d','span_ids':['s'],'v':'archive profile ok','note':'','t':1761955200000}}},
                                 {'findings':[finding]},'reviews/line17.json')['span_reviews'][0]
            self.assertEqual((entry['kind'],entry['level']),(kind,level))
            self.assertEqual(SpanEvidence([entry]).at('di-1',5,0,[{'z':250}])[0]['z'],250)

    def test_the_reviewed_decisions_offer_what_the_user_asked_for(self):
        # (the committed queue: Modřany's bridge over the street, Palackého most over the river; 2026-11-02 session)
        path = Path(__file__).resolve().parent.parent/'reports/review/track-height-spans.json'
        items = {f['id']:f for f in findings(json.loads(path.read_text(encoding='utf-8')),inline=True)['findings']}
        self.assertIn('archive, bridged over a dip',items['osm-4722520']['options'])
        self.assertNotIn('follows survey surface',items['osm-4722520']['options'])
        self.assertIn('follows survey surface',items['osm-476017592']['options'])
        self.assertNotIn('archive, bridged over a dip',items['osm-476017592']['options'])
        for spans in items['osm-4722520']['bridged'].values():
            self.assertTrue(all(200.5 < z < 201.6 for b in spans for z in b[1::2]), spans)

    def test_findings_keep_all_spans_and_pin_the_longest(self):
        spans = [{'id':'a','length_m':10,'profile':[{'xy':[0,0]}], 'from_stop':'A','to_stop':'B'},
                 {'id':'b','length_m':30,'profile':[{'xy':[4,5]},{'xy':[6,7]}], 'from_stop':'B','to_stop':'C'}]
        decision = {'id':'bridge-1','status':'review','span_ids':['a','b'], 'structure':{'kind':'bridge'}}
        result = findings({'snapshot':'test','spans':spans,'decisions':[decision]},inline=True)
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

    def test_a_mosty3d_bridge_joins_the_osm_bridge_beside_it_or_is_its_own_decision(self):
        ways = [{'id':7,'coords':[(0,0,None),(10,0,None)],'attrs':{'bridge':'yes','layer':'1'}}]
        bridges = [{'id':'mosty3d:540','xy':[[10,0],[30,0]]},{'id':'mosty3d:99','xy':[[100,0],[120,0]]}]
        structures = Structures(ways,bridges=bridges)
        self.assertEqual(structures.at((20,0)),'osm-7')
        self.assertEqual(structures.at((110,0)),'mosty3d-99')
        self.assertEqual(structures.catalog['mosty3d-99']['kind'],'bridge')
        self.assertEqual(structures.catalog['osm-7']['mosty3d_features'],[540])
        self.assertNotIn('mosty3d:540',structures.catalog['osm-7']['tags'])

    def test_report_has_both_stop_names_and_does_not_turn_terrain_into_rail_evidence(self):
        structures = Structures([{'id':1,'coords':[(0,0,None),(10,0,None)],'attrs':{'tunnel':'yes'}}])
        rows = [{'line':17,'direction':direction,'s':s,'weight_m':5,'xy':[x,0],
                 'status':'review','review_flags':['tunnel_unverified'],'di_id':'di-1','raw_di_z':None,
                 'candidates':[]} for direction in ('path','pathBack') for s,x in [(2.5,2.5),(7.5,7.5)]]
        rows[0]['raw_di_z'] = 205
        rows.append({'line':17,'direction':'path','s':12.5,'weight_m':5,'xy':[12.5,0],
                     'status':'selected','review_flags':[],'di_id':'di-2','raw_di_z':206,'candidates':[]})
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
        self.assertEqual(result['spans'][0]['profile'][0]['di_z'],205)
        self.assertEqual(result['spans'][0]['approach'][0]['di_z'],206)
        self.assertNotIn('di-2',result['spans'][0]['approval_profile']['di_ids'])


if __name__=='__main__':
    unittest.main(verbosity=2)
