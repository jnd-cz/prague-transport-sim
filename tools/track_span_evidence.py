"""Explicitly reviewed structure profiles; no proposal is applied automatically (#106)."""
import math

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
                        or not 0 < profile.get('radius_m',1) <= 1 or rule.get('type') not in ('archive','linear','constant')):
                    raise ValueError('span profile needs simple track path, DI IDs, <=1 m scope and explicit height rule')
                zs = rule.get('ends',[]) if rule['type']=='linear' else [rule.get('z')] if rule['type']=='constant' else []
                if ((rule['type']=='linear' and len(zs)!=2)
                        or any(not isinstance(z,(int,float)) or not math.isfinite(z) or not 100<z<500 for z in zs)):
                    raise ValueError('reviewed span heights must be finite Bpv rail heights')
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
            else:
                a,b = rule['ends']
                z = a+(b-a)*line.project(point)/line.length
            out.append({'id':review['id'], 'z':z, 'level':review['level'], 'kind':review['kind'],
                        'rule':rule['type'], 'source':review['source']})
        return out
