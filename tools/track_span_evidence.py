"""Explicitly reviewed structure profiles; no proposal is applied automatically (#106)."""
import argparse
from datetime import datetime, timezone
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


def from_reviews(verdicts, findings, source_name):
    """Convert unambiguous user answers; notes, other levels and uncertain choices stay held."""
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
        reason = None
        if not item or set(answer.get('span_ids',[])) != set(item['decision']['span_ids']):
            reason = 'missing or changed decision scope'
        elif answer.get('note') or answer.get('v') not in ('archive profile ok','follows survey surface'):
            reason = 'note, unsure or unspecified other level'
        elif not isinstance(answer.get('t'),(int,float)):
            reason = 'missing answer date'
        if reason:
            held.append({'id':identity,'reason':reason}); continue
        kind = item['decision']['structure']['kind']
        if kind not in ('bridge','tunnel'):
            held.append({'id':identity,'reason':'structure level is not identified'}); continue
        tags = item['decision']['structure'].get('tags',{})
        try:
            levels = {int(t['layer']) for t in tags.values() if t.get('layer') is not None}
        except (TypeError,ValueError):
            held.append({'id':identity,'reason':'unrecognized structure layer'}); continue
        if len(levels)>1 or (levels and ((kind=='bridge' and next(iter(levels))<=0) or (kind=='tunnel' and next(iter(levels))>=0))):
            held.append({'id':identity,'reason':'ambiguous structure layer'}); continue
        level = next(iter(levels)) if levels else (1 if kind=='bridge' else -1)
        profiles = []
        for span in item['spans']:
            p = dict(span['approval_profile'])
            if not p.get('di_ids'):
                reason = 'span has no DI identities'; break
            if answer['v']=='archive profile ok':
                p['rule'] = {'type':'archive'}
            else:
                line = LineString(p['xy']); samples, surface_ids = [], set()
                for point in span['profile']:
                    candidates = [c for c in point['surfaces'] if c.get('rail_height_eligible')
                                  and c.get('excluded') in (None,'track_zps_level_unverified')
                                  and isinstance(c.get('z'),(int,float)) and math.isfinite(c['z']) and 100<c['z']<500]
                    if not candidates or max(c['z'] for c in candidates)-min(c['z'] for c in candidates)>.01:
                        reason = 'survey rail height missing or ambiguous'; break
                    surface_ids.update(str(c['id']) for c in candidates if c.get('id') is not None)
                    samples.append([round(line.project(Point(point['xy'])),3),candidates[0]['z']])
                if reason: break
                p['rule'] = {'type':'samples','samples':samples}
                p['survey_ids'] = sorted(surface_ids)
            profiles.append(p)
        if reason:
            held.append({'id':identity,'reason':reason}); continue
        entry = {'id':'review-'+identity,'kind':'deck' if kind=='bridge' else 'tunnel',
                 'level':level,'reviewed':True,'vertical_datum':'Bpv',
                 'height_meaning':'top_of_rail','source':{'dataset':'expert_review','record':f'{source_name}#{key}',
                 'date':datetime.fromtimestamp(answer['t']/1000,timezone.utc).date().isoformat(),'who':'user'},'profiles':profiles}
        try:
            SpanEvidence([entry])
        except (ValueError,TypeError) as e:
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
