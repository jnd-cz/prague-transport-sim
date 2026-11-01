"""Group held heights into structure decisions, without approving a height (#106).

    python -P -E tools/track_structure_review.py --input reports/track-heights.json

The output loads in ?line=17&inspect&heightreview=reports/review/track-height-spans.json (F8).
Each structure has contiguous spans with stop names, lengths per direction, dated candidates and
proposed rules. Copy reviewed profiles to --evidence span_reviews; a proposal is never evidence.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import hashlib
import math
from pathlib import Path
import sys

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

sys.path.insert(0,str(Path(__file__).resolve().parent))
from dtmp_tracks import ROOT, load_line, write_json
from geo import Frame
from ipr_dtm import IprDtm
from track_context import load_context
from track_decks import load_decks
from track_heights import usable
from track_terrain_fallback import ordinary_fallback


def structure_kind(tags):
    if tags.get('review_kind'):
        return tags['review_kind']
    if tags.get('tunnel','no')!='no' or tags.get('covered')=='yes' or tags.get('layer','0').startswith('-'):
        return 'tunnel'
    if tags.get('bridge','no')!='no' or tags.get('layer','0')!='0':
        return 'bridge'
    return None


class Structures:
    def __init__(self, paths, records=()):
        self.paths = [p for p in paths if structure_kind(p['attrs'])]
        self.geoms = [LineString([v[:2] for v in p['coords']]) for p in self.paths]
        for r in records:
            if r['level']!=0 and r.get('class') in ('deck','tram','road','paved','parking'):
                geom = Polygon([p[:2] for p in r['ring']],r.get('holes',[]))
                if geom.is_valid and not geom.is_empty:
                    self.paths.append({'id':r['id'],'attrs':{'review_kind':'survey_level','level':r['level']}})
                    self.geoms.append(geom)
        self.tree = STRtree(self.geoms)
        parent = list(range(len(self.paths)))
        def root(i):
            while parent[i]!=i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for i,(p,g) in enumerate(zip(self.paths,self.geoms)):
            for j in self.tree.query(g.buffer(6)):
                j = int(j)
                q = self.paths[j]
                if (j>i and g.distance(self.geoms[j])<=6 and structure_kind(p['attrs'])==structure_kind(q['attrs'])
                        and p['attrs'].get('level')==q['attrs'].get('level')
                        and p['attrs'].get('layer','0')==q['attrs'].get('layer','0')
                        and not (p['attrs'].get('name') and q['attrs'].get('name')
                                 and p['attrs']['name']!=q['attrs']['name'])):
                    parent[root(j)] = root(i)
        self.groups, self.by_way = {}, {}
        for i,p in enumerate(self.paths):
            self.groups.setdefault(root(i),[]).append(p)
        self.catalog = {}
        for group in self.groups.values():
            ids = sorted((p['id'] for p in group),key=str)
            osm = [i for i in ids if isinstance(i,int)]
            identity = ('osm-'+str(min(osm)) if osm else
                        'survey-'+hashlib.sha256('|'.join(ids).encode()).hexdigest()[:12])
            names = sorted({p['attrs']['name'] for p in group if p['attrs'].get('name')})
            self.catalog[identity] = {'id':identity,'kind':structure_kind(group[0]['attrs']),
                'osm_ways':osm,'survey_records':[i for i in ids if isinstance(i,str)],
                'names':names,'tags':{str(p['id']):p['attrs'] for p in group}}
            for p in group:
                self.by_way[str(p['id'])] = identity

    def at(self, xy):
        point = Point(xy)
        hits = [(structure_kind(self.paths[int(i)]['attrs'])=='survey_level',
                 self.geoms[int(i)].distance(point),int(i)) for i in self.tree.query(point.buffer(5))]
        hits = [h for h in hits if h[1]<=(1.5 if h[0] else 5)]
        return self.by_way[str(self.paths[min(hits)[2]]['id'])] if hits else None


def stats(values):
    values = [float(v) for v in values if usable(v)]
    return {'n':len(values), 'min':round(min(values),3), 'max':round(max(values),3),
            'median':round(float(np.median(values)),3)} if values else {'n':0}


def record_date(source):
    attrs = source.get('attributes',{})
    date = attrs.get('DAT_ZMENA') or attrs.get('DAT_VZNIK')
    return datetime.fromtimestamp(date/1000,timezone.utc).date().isoformat() if isinstance(date,(int,float)) else date


def grouped(rows, structures):
    """Keep each traversal separate, including repeated path legs and changes of direction."""
    runs, run, last_key, last_end = [], [], None, None
    for r in rows:
        key = (r['line'],r['direction'],structures.at(r.get('di_xy') or r['xy']))
        held = r['status']=='review' and (key[2] is not None or any(
            f in r['review_flags'] for f in ('structure_unverified','tunnel_unverified','track_zps_level_unverified')))
        metadata = structures.catalog.get(key[2],{})
        passage = any(t.get('tunnel')=='building_passage' for t in metadata.get('tags',{}).values())
        # A building passage is a structure review item even when numeric DI already resolves it.
        held = held or passage
        start = r['s']-r['weight_m']/2
        if run and (not held or key!=last_key or abs(start-last_end)>.01):
            runs.append((last_key,run))
            run = []
        if held:
            run.append(r)
            last_key, last_end = key,r['s']+r['weight_m']/2
    if run:
        runs.append((last_key,run))
    return runs


def endpoint(rows, s, before):
    candidates = [r for r in rows if usable(r.get('raw_di_z')) and
                  (0<=s-r['s']<=50 if before else 0<=r['s']-s<=50)]
    if not candidates:
        return None
    r = min(candidates,key=lambda r:abs(r['s']-s))
    return {'di_id':r['di_id'],'xy':r['xy'],'z':r['raw_di_z'],'distance_m':round(abs(r['s']-s),3)}


def review(report, structures, terrain, lines):
    routes = defaultdict(list)
    di_sources = {str(g['id']):g['sources'] for g in report.get('geometry',[])}
    for r in report['route_samples']:
        routes[r['line'],r['direction']].append(r)
    spans, counters = [], defaultdict(int)
    for key,rows in grouped(report['route_samples'],structures):
        line,direction,structure = key
        counters[key] += 1
        a,b = rows[0]['s']-rows[0]['weight_m']/2,rows[-1]['s']+rows[-1]['weight_m']/2
        data = lines[line]
        stops = data.get('stops',[])
        if direction=='pathBack':
            forward,back = LineString([p[:2] for p in data['path']]),LineString([p[:2] for p in data['pathBack']])
            stops = [{'name':st['name'],'s':back.project(forward.interpolate(st['s']))} for st in stops]
        # Names are located on the direction's path, never using outward s on pathBack.
        nearest = lambda s: min(stops,key=lambda t:abs(t['s']-s))['name'] if stops else None
        ends = [endpoint(routes[line,direction],a,True),endpoint(routes[line,direction],b,False)]
        for end in ends:
            if end:
                end['sources'] = di_sources.get(str(end['di_id']),[])
        e,n = Frame().to_jtsk([r['xy'][0] for r in rows],[r['xy'][1] for r in rows])
        ground = [float(z) if math.isfinite(z) and 100<z<500 else None for z in terrain.sample(e,n)]
        archive, surfaces, profile = {}, {}, []
        for r,z in zip(rows,ground):
            archived, surveyed = [], []
            for c in r.get('candidates',[]):
                if c['dataset']=='archive':
                    source = report['archive_sources'].get(str(c['id']),{})
                    entry = archive.setdefault(str(c['id']),{'id':c['id'],'source':source,
                                                             'record_date':record_date(source),'zs':[]})
                    entry['zs'].append(c.get('z'))
                    archived.append({'id':c['id'],'z':c.get('z'),'excluded':c.get('excluded')})
                elif c['dataset'] in ('deck','survey'):
                    entry = surfaces.setdefault(c['id'],{'id':c['id'],'class':c['class'],'level':c['level'],
                        'source':c['provenance'],'excluded':c.get('excluded'),'zs':[]})
                    entry['zs'].append(c.get('z'))
                    if c.get('inside'):
                        surveyed.append({'id':c['id'],'class':c['class'],'z':c.get('z'),
                            'rail_height_eligible':r.get('construction',{}).get('kind')=='paved'
                                and c['class'] in ('deck','tram','road','paved','parking'),
                            'excluded':c.get('excluded')})
            profile.append({'s':round(r['s'],3),'xy':[round(v,3) for v in (r.get('di_xy') or r['xy'])],
                'di_id':r.get('di_id'),'archive':archived,'surfaces':surveyed,'ipr_terrain_z':z})
        for entries in (archive,surfaces):
            for entry in entries.values():
                entry['height'] = stats(entry.pop('zs'))
        metadata = structures.catalog.get(structure,{'id':'unmapped','kind':'unmapped','osm_ways':[],'names':[]})
        proposal = {'rule':'independent_height_required','reason':'No reviewed rail level or two numeric DI ends.'}
        complete_archive = all(any(usable(a['z']) and not a['excluded'] for a in p['archive']) for p in profile)
        if (complete_archive and all(c['record_date'] for c in archive.values()) and metadata['kind']=='bridge'
                and not any(f in r['review_flags'] for r in rows for f in
                            ('known_archive_disagreement','ambiguous_archive_match'))):
            proposal = {'rule':'review_archive_profile',
                        'reason':'Dated plan-matched archive covers this span. Confirm current alignment and physical level; not applied.'}
        if all(ends):
            proposal = {'rule':'linear_di_portals','ends':[p['z'] for p in ends],
                        'reason':'Proposal only; check portal positions, grades and physical level before approval.'}
        differences = [abs(a['z']-s['z']) for p in profile for a in p['archive'] for s in p['surfaces']
                       if usable(a['z']) and usable(s['z']) and not a['excluded'] and not s['excluded']
                       and s['rail_height_eligible']]
        if differences and max(differences)<=.3:
            proposal = {'rule':'archive_agrees_with_survey','max_delta_m':round(max(differences),3),
                        'reason':'Proposal only; verify that survey describes the tram deck.'}
        status = ('review' if any(r['status']!='selected' for r in rows) else
                  'di_numeric' if all(r.get('height_source',{}).get('dataset')=='di' for r in rows) else 'approved')
        if status=='di_numeric':
            proposal = {'rule':'retain_numeric_di','reason':'All samples already have authoritative numeric DI.'}
        elif status=='approved':
            proposal = {'rule':'retain_reviewed_height','reason':'Existing reviewed evidence already resolves this span.'}
        identity = f"{structure or 'unmapped'}:line{line}:{direction}:{counters[key]}"
        xy = [p['xy'] for p in profile]
        ux,uy = rows[0]['tangent'] if rows[0].get('tangent') else (1,0)
        start = [xy[0][0]-ux*rows[0]['weight_m']/2,xy[0][1]-uy*rows[0]['weight_m']/2]
        ux,uy = rows[-1]['tangent'] if rows[-1].get('tangent') else (1,0)
        end = [xy[-1][0]+ux*rows[-1]['weight_m']/2,xy[-1][1]+uy*rows[-1]['weight_m']/2]
        spans.append({'id':identity,'structure_id':metadata['id'],'structure':metadata,'status':status,
            'line':line,'direction':direction,'from_stop':nearest(a),'to_stop':nearest(b),
            'start_s':round(a,3),'end_s':round(b,3),'length_m':round(sum(r['weight_m'] for r in rows),3),
            'review_flags':sorted({f for r in rows for f in r['review_flags']}),'di_ends':ends,
            'archive_candidates':list(archive.values()),'survey_candidates':list(surfaces.values()),
            'terrain':{'dataset':'ipr-dtm','source':'raw/ipr-dtm/DTM/dtm_1m.tif',
                       'height_meaning':'bare_earth','datum':'Bpv_assumed_not_independent_rail_evidence',**stats(ground)},
            'proposal':proposal,'profile':profile,
            'approval_profile':{'xy':[start,*xy,end],'di_ids':sorted({str(r['di_id']) for r in rows if r.get('di_id')}),
                                'radius_m':1,'rule':{'type':'needs_explicit_review'}}})
    decisions = {}
    for span in spans:
        identity = span['structure_id']
        # Unmapped fragments are one corridor question, without claiming a common physical level.
        if identity=='unmapped':
            stops = sorted({span['from_stop'] or '?',span['to_stop'] or '?'})
            identity = 'unmapped-'+hashlib.sha256('|'.join(stops).encode()).hexdigest()[:12]
        d = decisions.setdefault(identity,{'id':identity,'structure':span['structure'],'span_ids':[],
                                          'length_per_direction_m':{},'status':span['status']})
        if span['status']=='review':
            d['status'] = 'review'
        if span['structure_id']=='unmapped':
            d['scope_note'] = 'Grouped by nearest stops for review; not evidence of one structure or level.'
        d['span_ids'].append(span['id'])
        key = f"line{span['line']}:{span['direction']}"
        d['length_per_direction_m'][key] = round(d['length_per_direction_m'].get(key,0)+span['length_m'],3)
    fallbacks = []
    eligible = [r for r in report['route_samples'] if 'no_usable_height' in r['review_flags']]
    if eligible:
        e,n = Frame().to_jtsk([r['xy'][0] for r in eligible],[r['xy'][1] for r in eligible])
        for r,z in zip(eligible,terrain.sample(e,n)):
            proposal = ordinary_fallback(r,float(z),report.get('rail_above_deck_facts',[]))
            if proposal:
                fallbacks.append({k:r[k] for k in ('line','direction','s','xy','di_id','weight_m')} | proposal)
    return {'schema':1,'snapshot':report['snapshot'],'frame':report['frame'],
            'scope':'Held structure heights; proposed rules require explicit dated review.',
            'decisions':list(decisions.values()),'spans':spans,'ordinary_terrain_fallbacks':fallbacks}


def markdown(result):
    spans = {s['id']:s for s in result['spans']}
    out = ['# Structure height decisions', '',f"Snapshot `{result['snapshot']}`. Proposed rules are not approvals.", '',
           'Open `?line=17&inspect&heightreview=reports/review/track-height-spans.json`; F8 toggles the spans.', '',
           'Each decision may cover several lines and directions. A dated reviewed rule can include all its',
           '`approval_profile` entries in one `span_reviews` record. The placeholder rule deliberately fails',
           'validation until a height rule is explicitly chosen. Numeric DI always keeps priority.', '']
    for d in result['decisions']:
        group = [spans[i] for i in d['span_ids']]
        names = ' / '.join(d['structure']['names']) or d['structure']['kind']
        out += [f"## {d['id']} · {names}", '',
                'OSM ways: '+(', '.join(f'[{i}](https://www.openstreetmap.org/way/{i})' for i in d['structure']['osm_ways']) or 'not tagged')+'.', '',
                '| Line / direction | Nearest stops at ends | Length (m) | Proposed rule |',
                '|---|---|---:|---|']
        for s in group:
            out.append(f"| {s['line']} / {s['direction']} | {s['from_stop']} → {s['to_stop']} | {s['length_m']:.1f} | {s['proposal']['rule']} |")
        archive = {str(c['id']):c for s in group for c in s['archive_candidates']}
        out += ['', 'Archive candidates: '+('; '.join(f"`{i}` ({c['record_date'] or 'date missing'}; median {c['height'].get('median','?')} m, range {c['height'].get('min','?')}–{c['height'].get('max','?')} m)" for i,c in archive.items()) or 'none')+'.',
                '', 'DI at span ends: '+('; '.join(f"{e['z']:.3f} m / {e['di_id']} / {e['distance_m']:.1f} m away" for s in group for e in s['di_ends'] if e) or 'no numeric DI within 50 m')+'.',
                '', 'Flags: '+', '.join(f'`{f}`' for f in sorted({f for s in group for f in s['review_flags']}))+'.', '']
    out += ['## Ordinary no-data proposals', '',
            f"{sum(r['weight_m'] for r in result['ordinary_terrain_fallbacks']):.3f} direction-metres use the documented IPR-terrain-plus-style proposal for #20.",
            'These are flagged approximations. No structure receives an earth-height fallback.', '']
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input',type=Path,required=True)
    ap.add_argument('--output',type=Path,default=ROOT/'reports/review/track-height-spans.json')
    ap.add_argument('--markdown-output',type=Path,default=ROOT/'reports/review/track-height-spans.md')
    a = ap.parse_args()
    report = json.loads(a.input.read_text(encoding='utf-8'))
    decks = load_decks(ROOT)
    context = load_context(decks)
    terrain = IprDtm()
    try:
        result = review(report,Structures(context.paths,decks.records),terrain,{n:load_line(n) for n in (9,17,22,23,37)})
    finally:
        terrain.f.close()
    write_json(a.output,result)
    from atomic import replacing
    a.markdown_output.parent.mkdir(parents=True,exist_ok=True)
    with replacing(a.markdown_output,'w',encoding='utf-8') as f:
        f.write(markdown(result))
    print(f"{len(result['decisions'])} structure decisions, {len(result['spans'])} contiguous direction spans")
    for d in result['decisions']:
        print(json.dumps({k:v for k,v in d.items() if k!='structure'},ensure_ascii=True))


if __name__=='__main__':
    main()
