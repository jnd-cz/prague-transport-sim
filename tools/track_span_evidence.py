"""Explicitly reviewed structure profiles; no proposal is applied automatically (#106)."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

from shapely.geometry import LineString, Point


class SpanEvidence:
    def __init__(self, reviews=()):
        self.profiles = []
        ids = set()
        for review in reviews:
            source = review.get('source', {})
            if (not review.get('id') or review['id'] in ids or review.get('reviewed') is not True
                    or review.get('vertical_datum') != 'Bpv' or review.get('height_meaning') != 'top_of_rail'
                    or review.get('kind') not in ('surface','deck','tunnel') or type(review.get('level')) is not int
                    or not all(source.get(k) for k in ('dataset','record','date')) or not review.get('profiles')):
                raise ValueError('span review needs unique id, reviewed Bpv rail level, source/date and profiles')
            if source['dataset'].lower() in ('di','archive','dtm-di','dtmp-tracks','compiled-zps'):
                raise ValueError('span rule approval needs an independent reviewed basis, not its raw candidate')
            ids.add(review['id'])
            for profile in review['profiles']:
                line = LineString(profile['xy'])
                rule = profile['rule']
                if (line.is_empty or line.length <= 0 or not line.is_simple or not profile.get('di_ids')
                        or not 0 < profile.get('radius_m',1) <= 1 or rule.get('type') not in ('archive','linear','constant','samples')):
                    raise ValueError('span profile needs simple track path, DI IDs, <=1 m scope and explicit height rule')
                zs = rule.get('ends',[]) if rule['type']=='linear' else [rule.get('z')] if rule['type']=='constant' else []
                if ((rule['type']=='linear' and len(zs)!=2)
                        or any(not isinstance(z,(int,float)) or not math.isfinite(z) or not 100<z<500 for z in zs)):
                    raise ValueError('reviewed span heights must be finite Bpv rail heights')
                if rule['type']=='samples':
                    samples = rule.get('samples',[])
                    if (len(samples)<2 or any(not isinstance(s,(int,float)) or not math.isfinite(s) or not 0<=s<=line.length
                            or not isinstance(z,(int,float)) or not math.isfinite(z) or not 100<z<500 for s,z in samples)
                            or any(b[0]<=a[0] or b[0]-a[0]>10 for a,b in zip(samples,samples[1:]))):
                        raise ValueError('survey profile needs ordered finite samples no more than 10 m apart')
                self.profiles.append((review,profile,line,{str(i) for i in profile['di_ids']}))

    def at(self, identity, x, y, archived):
        if not self.profiles:
            return []
        point, out = Point(x,y), []
        for review,profile,line,ids in self.profiles:
            if identity not in ids or line.distance(point) > profile.get('radius_m',1):
                continue
            rule = profile['rule']
            if rule['type']=='archive':
                zs = [a['z'] for a in archived]
                if not zs or max(zs)-min(zs)>.3:
                    continue
                z = zs[0]
            elif rule['type']=='constant':
                z = rule['z']
            elif rule['type']=='samples':
                s = line.project(point)
                samples = rule['samples']
                if s < samples[0][0]-3 or s > samples[-1][0]+3:
                    continue
                if s <= samples[0][0]: z = samples[0][1]
                elif s >= samples[-1][0]: z = samples[-1][1]
                else:
                    a,b = next((a,b) for a,b in zip(samples,samples[1:]) if a[0]<=s<=b[0])
                    z = a[1]+(b[1]-a[1])*(s-a[0])/(b[0]-a[0])
            else:
                a,b = rule['ends']
                z = a+(b-a)*line.project(point)/line.length
            out.append({'id':review['id'], 'z':z, 'level':review['level'], 'kind':review['kind'],
                        'rule':rule['type'], 'source':review['source']})
        return out


def hydrate_findings(findings, root=None):
    """Resolve a compact findings file against its exact generated span queue."""
    ref = findings.get('span_file')
    if not ref:
        return findings
    root = Path(root) if root else Path(__file__).resolve().parent.parent
    relative = Path(ref)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('invalid span queue path')
    raw = (root / relative).read_bytes()
    if hashlib.sha256(raw).hexdigest() != findings.get('span_sha256'):
        raise ValueError('span queue differs from the findings file; regenerate both')
    queue = json.loads(raw)
    if queue.get('snapshot') != findings.get('snapshot'):
        raise ValueError('span queue snapshot differs from the findings file')
    spans = {s['id']:s for s in queue['spans']}
    hydrated = []
    for f in findings['findings']:
        ids = f['decision']['span_ids']
        if any(i not in spans for i in ids):
            raise ValueError('span queue is missing a decision span')
        hydrated.append({**f,'spans':[spans[i] for i in ids]})
    return {**findings,'findings':hydrated}


# The answers that become evidence; the others ('other level (deck / under)', 'unsure') stay held.
ARCHIVE, BRIDGED, SURVEY = 'archive profile ok', 'archive, bridged over a dip', 'follows survey surface'
# A track climbs a few per cent: a step over 10 % between archive points ~5 m apart is the archive
# measuring something else there (Modřany: the street under the bridge, 201.2 -> 194.7 m in 5 m;
# Palackého most: the river bed, #176). A dip closes where the archive steps back up to within a track
# grade (4 %, plus 0.3 m) of where it left, at most 150 m on.
STEEP, GRADE, MAX_DIP = .10, .04, 150
SURVEY_SPREAD, MAX_GAP = .03, 10  # m: deck and road of one survey agree to 3 cm; samples at most 10 m apart


class Held(Exception):
    pass


def _valid(z):
    return isinstance(z,(int,float)) and math.isfinite(z) and 100<z<500


def _structure_level(structure):
    """(evidence kind, physical level) of a decision's structure, or Held."""
    kind = structure['kind']
    if kind=='unmapped':
        return 'surface',0  # (no bridge or tunnel mapped or surveyed here: the track lies on the street)
    key = 'level' if kind=='survey_level' else 'layer'
    try:
        levels = {int(t[key]) for t in structure.get('tags',{}).values() if t.get(key) is not None}
    except (TypeError,ValueError):
        raise Held('unrecognized structure layer')
    if kind=='survey_level':
        if len(levels)!=1 or 0 in levels:
            raise Held('ambiguous surveyed level')
        level = next(iter(levels))
        return ('deck' if level>0 else 'tunnel'),level
    if kind not in ('bridge','tunnel'):
        raise Held('structure level is not identified')
    if len(levels)>1 or (levels and ((kind=='bridge' and next(iter(levels))<=0) or (kind=='tunnel' and next(iter(levels))>=0))):
        raise Held('ambiguous structure layer')
    return ('deck' if kind=='bridge' else 'tunnel'),(next(iter(levels)) if levels else (1 if kind=='bridge' else -1))


def _rail_z(point):
    """Numeric DI where it is (it wins anyway), else the archive; None where neither."""
    if _valid(point.get('di_z')):
        return point['di_z']
    zs = [c['z'] for c in point.get('archive',[]) if _valid(c.get('z')) and not c.get('excluded')]
    if zs and max(zs)-min(zs)>.3:
        raise Held('archive rail heights conflict on part of the span')
    return zs[0] if zs else None


def _grade(a, b):
    return (b[1]-a[1])/max(b[0]-a[0],1e-6)


def dips(series):
    """The closed dips of a (s, z) series as index pairs (k, m): k the last point before the steep drop,
    m the first after the steep climb back; and the steep steps that are not part of one, (i, why)."""
    out, bad, i, n = [], [], 0, len(series)
    while i < n-1:
        g = _grade(series[i],series[i+1])
        if g > STEEP:
            bad.append((i,f'archive steps up {series[i+1][1]-series[i][1]:.1f} m at {series[i][0]:.0f} m without a dip before it'))
        elif g < -STEEP:
            k, (s0,z0) = i, series[i]
            m = next((j for j in range(k+2,n) if series[j][0]-s0 <= MAX_DIP
                      and _grade(series[j-1],series[j]) > STEEP
                      and (j==n-1 or abs(_grade(series[j],series[j+1])) <= STEEP)
                      and abs(series[j][1]-z0) <= GRADE*(series[j][0]-s0)+.3), None)
            if m is not None:
                out.append((k,m))
                i = m
                continue
            low = min(z for _,z in series[k+1:])
            bad.append((k,f'archive drops {z0-low:.1f} m at {s0:.0f} m and does not come back within 30 m of the span'))
        i += 1
    return out, bad


def _archive_profile(span, line, bridge):
    """The span's archive rule ({'type':'archive'}), or with bridge=True samples with each dip interpolated.
    The ~30 m of approach on both sides count for the dips (Hodkovičky's closes 5 m past the span)."""
    points = sorted([*(dict(p,inside=False) for p in span.get('approach',[])),*(dict(p,inside=True) for p in span['profile'])],
                    key=lambda p:p['s'])
    known = [(p,(p['s'],z)) for p in points if (z := _rail_z(p)) is not None]
    found, bad = dips([sz for _,sz in known])
    # (a step among the approach points alone is another span's business)
    bad = [why for i,why in bad if known[i][0]['inside'] or known[i+1][0]['inside']]
    if bad:
        raise Held(bad[0])
    found = [(k,m) for k,m in found if any(known[j][0]['inside'] for j in range(k,m+1))]
    inside = {id(known[j][0]) for k,m in found for j in range(k+1,m)}
    zs = {id(p):z for p,(_,z) in known}
    if any(id(p) not in zs for p in points if p['inside'] and id(p) not in inside):
        raise Held('archive rail height missing on part of the span')
    if not bridge:
        if found:
            k,m = found[0]
            (s0,z0),(s1,_) = known[k][1],known[m][1]
            low = min(sz[1] for _,sz in known[k+1:m])
            raise Held(f'the archive dips {z0-low:.1f} m between {s0-span["start_s"]:.0f} and {s1-span["start_s"]:.0f} m '
                       f'(what lies under the track): answer "{BRIDGED}" if the track bridges it')
        return {'type':'archive'},[]
    if not found:
        raise Held('the archive has no dip to bridge')
    for k,m in found:
        (a,za),(b,zb) = known[k][1],known[m][1]
        for p in points:
            if a < p['s'] < b:
                zs[id(p)] = za+(zb-za)*(p['s']-a)/(b-a)
    samples = [[round(line.project(Point(p['xy'])),3),round(zs[id(p)],3)] for p in points if p['inside'] and id(p) in zs]
    if any(b[0]-a[0]>MAX_GAP or b[0]<=a[0] for a,b in zip(samples,samples[1:])):
        raise Held('archive points are too far apart to sample')
    bridged = [[known[k][1][0],round(known[k][1][1],3),known[m][1][0],round(known[m][1][1],3)] for k,m in found]
    return {'type':'samples','samples':samples},bridged


def _survey_profile(span, line):
    """Samples of the survey's rail heights; points it misses are skipped while samples stay <= 10 m apart."""
    samples, ids = [], set()
    for point in span['profile']:
        candidates = [c for c in point['surfaces'] if c.get('rail_height_eligible')
                      and c.get('excluded') in (None,'track_zps_level_unverified') and _valid(c.get('z'))]
        if not candidates:
            continue
        zs = sorted(c['z'] for c in candidates)
        if zs[-1]-zs[0] > SURVEY_SPREAD:
            raise Held('survey rail heights disagree on part of the span')
        ids.update(str(c['id']) for c in candidates if c.get('id') is not None)
        samples.append([round(line.project(Point(point['xy'])),3),round(zs[len(zs)//2],3)])
    if not samples:
        raise Held('survey rail height missing')
    gaps = [samples[0][0],line.length-samples[-1][0],*(b[0]-a[0] for a,b in zip(samples,samples[1:]))]
    if len(samples)<2 or max(gaps)>MAX_GAP:
        raise Held(f'survey covers only part of the span (a gap of {max(gaps):.0f} m)')
    if any(abs(_grade(a,b))>STEEP for a,b in zip(samples,samples[1:])):
        raise Held('survey rail heights step steeply on part of the span')
    return {'type':'samples','samples':samples},sorted(ids)


def from_reviews(verdicts, findings, source_name):
    """Convert unambiguous user answers; notes, other levels and uncertain choices stay held."""
    findings = hydrate_findings(findings)
    by_id = {f['id']:f for f in findings['findings'] if f.get('kind')=='trackheight'}
    reviews, held, latest = [], [], {}
    for key,answer in verdicts.get('items',{}).items():
        identity = answer.get('decision_id')
        if not identity:
            continue
        t = answer.get('t') if isinstance(answer.get('t'),(int,float)) else 0
        if identity not in latest or t > latest[identity][0]:
            latest[identity] = (t,key,answer)
    for identity,(_,key,answer) in latest.items():
        item = by_id.get(identity)
        try:
            if (not item or set(answer.get('span_ids',[])) != set(item['decision']['span_ids'])
                    or (answer.get('span_sha256') and answer['span_sha256'] != findings.get('span_sha256'))):
                raise Held('missing or changed decision scope')
            if answer.get('note') or answer.get('v') not in (ARCHIVE,BRIDGED,SURVEY):
                raise Held('note, unsure or unspecified other level')
            if not isinstance(answer.get('t'),(int,float)):
                raise Held('missing answer date')
            kind,level = _structure_level(item['decision']['structure'])
            profiles, uncovered = [], []
            for span in item['spans']:
                p = dict(span['approval_profile'])
                if not p.get('di_ids'):
                    raise Held('span has no DI identities')
                line = LineString(p['xy'])
                if answer['v']==SURVEY:
                    try:
                        p['rule'],p['survey_ids'] = _survey_profile(span,line)
                    except Held:
                        # (a short end span the survey does not reach keeps the rules it had)
                        if span['length_m'] > MAX_GAP:
                            raise
                        uncovered.append(span['id']); continue
                else:
                    p['rule'],bridged = _archive_profile(span,line,answer['v']==BRIDGED)
                    if bridged:
                        p['bridged'] = bridged
                profiles.append(p)
            if not profiles:
                raise Held('survey rail height missing')
            entry = {'id':'review-'+identity,'kind':kind,'level':level,'reviewed':True,'vertical_datum':'Bpv',
                     'height_meaning':'top_of_rail','source':{'dataset':'expert_review','record':f'{source_name}#{key}',
                     'date':datetime.fromtimestamp(answer['t']/1000,timezone.utc).date().isoformat(),'who':'user'},
                     'answer':answer['v'],'profiles':profiles}
            if uncovered:
                entry['uncovered_spans'] = uncovered
            try:
                SpanEvidence([entry])
            except (ValueError,TypeError) as e:
                raise Held(str(e))
        except Held as e:
            held.append({'id':identity,'reason':str(e)}); continue
        reviews.append(entry)
    return {'span_reviews':reviews,'held':held}


def main():
    ap = argparse.ArgumentParser(description='Convert stored track-height review answers into dated evidence.')
    ap.add_argument('--from-reviews',type=Path,required=True)
    ap.add_argument('--findings',type=Path,default=Path('reports/review/track-heights.json'))
    ap.add_argument('--output',type=Path,default=Path('reports/review/track-height-evidence.json'))
    args = ap.parse_args()
    result = from_reviews(json.loads(args.from_reviews.read_text(encoding='utf-8')),
                          json.loads(args.findings.read_text(encoding='utf-8')),str(args.from_reviews))
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from atomic import replacing
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with replacing(args.output,'w',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print(f"{len(result['span_reviews'])} evidence records, {len(result['held'])} held")


if __name__=='__main__':
    main()
