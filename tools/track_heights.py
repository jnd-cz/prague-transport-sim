"""Guarded height selection for #20's importer (#106). Geometry is never selected by its Z.

No candidate becomes an importable height without local, reviewed, independent physical-level
evidence. A plan match or an OSM structure buffer supplies a review flag, never that evidence.
"""
import math

TOLERANCE = 0.3


def usable(z):
    return isinstance(z, (int, float)) and math.isfinite(z) and 100 < z < 500


class HeightGuard:
    def __init__(self, evidence=(), alignment_reviews=(), conflicts=()):
        self.evidence = list(evidence)
        self.conflicts = {str(i) for i in conflicts}
        self.reviews = {}
        for review in alignment_reviews:
            if review.get('dataset') not in ('di', 'archive') or review.get('status') not in ('obsolete', 'uncertain', 'current') or not review.get('source'):
                raise ValueError('alignment review needs dataset, id, status and source')
            key = (review['dataset'], str(review['id']))
            if key in self.reviews:
                raise ValueError(f'duplicate alignment review: {key}')
            self.reviews[key] = review
        ids = set()
        for e in self.evidence:
            source = e.get('source', {})
            if (not e.get('id') or e['id'] in ids or not e.get('di_id') or
                    e.get('reviewed') is not True or e.get('vertical_datum') != 'Bpv' or
                    e.get('height_meaning') != 'top_of_rail' or not usable(e.get('z')) or
                    e.get('kind') not in ('surface', 'deck', 'tunnel') or
                    type(e.get('level')) is not int or
                    not source.get('record') or not source.get('date') or
                    source.get('dataset', '').lower() in ('', 'di', 'archive', 'dtm-di', 'dtmp-tracks', 'compiled-zps') or
                    len(e.get('xy', [])) != 2 or not all(math.isfinite(v) for v in e['xy']) or
                    not 0 < e.get('radius_m', 0) <= 1):
                raise ValueError('height evidence needs unique id, track/point scope, reviewed independent source, Bpv rail height and physical level')
            ids.add(e['id'])

    def choose(self, di, match, x, y, structure_hint=False):
        flags, candidates = [], []
        identity = str(di['id'])
        review = self.reviews.get(('di', identity), {})
        if usable(di.get('z')):
            candidates.append({'dataset': 'di', 'id': identity, 'z': di['z']})
        near = match.get('candidates', [])
        if near:
            near = [c for c in near if c['distance'] <= near[0]['distance'] + .25]
        # A farther numeric track must never replace the nearest one with missing Z.
        if match['status'] in ('numeric', 'ambiguous'):
            for c in near:
                if usable(c.get('z')):
                    candidates.append({'dataset': 'archive', **c})
        if structure_hint:
            flags.append('structure_requires_level_evidence')
        if match['status'] == 'ambiguous':
            flags.append('ambiguous_archive_match')
        if match['status'] == 'missing_z':
            flags.append('nearest_archive_missing_z')
        if any(str(c['id']) in self.conflicts for c in near):
            flags.append('known_archive_disagreement')
        if usable(di.get('z')) and any(abs(c['z'] - di['z']) > TOLERANCE for c in candidates if c['dataset'] == 'archive'):
            flags.append('di_archive_height_disagreement')
        for c in candidates:
            r = self.reviews.get((c['dataset'], str(c['id'])), {})
            if r.get('status') in ('obsolete', 'uncertain'):
                c['excluded'] = r['status'] + '_alignment'
                flags.append(c['dataset'] + '_' + c['excluded'])
        out = {'status': 'review', 'z': None, 'height_source': None, 'confidence': 'unvalidated',
               'review_flags': sorted(set(flags)), 'candidates': candidates, 'evidence_ids': []}
        if review.get('status') in ('obsolete', 'uncertain'):
            out['status'] = 'rejected' if review['status'] == 'obsolete' else 'review'
            out['review_flags'] = sorted(set(out['review_flags'] + ['di_' + review['status'] + '_alignment']))
            return out
        evidence = [e for e in self.evidence if str(e['di_id']) == identity and
                    math.dist(e['xy'], (x, y)) <= e['radius_m']]
        out['evidence_ids'] = [e['id'] for e in evidence]
        if not evidence:
            out['review_flags'].append('independent_level_evidence_required')
            return out
        if len({e['level'] for e in evidence}) != 1 or max(e['z'] for e in evidence) - min(e['z'] for e in evidence) > TOLERANCE:
            out['review_flags'].append('conflicting_level_evidence')
            return out
        supported = [c for c in candidates if 'excluded' not in c and
                     all(abs(c['z'] - e['z']) <= TOLERANCE for e in evidence)]
        if not supported or max(c['z'] for c in supported) - min(c['z'] for c in supported) > TOLERANCE:
            out['review_flags'].append('no_unique_supported_height')
            return out
        # Geometry preference is used only after independent height/level validation.
        selected = next((c for c in supported if c['dataset'] == 'di'), supported[0])
        out.update(status='selected', z=selected['z'],
                   height_source={'dataset': selected['dataset'], 'id': selected['id']},
                   confidence='independent_level_match')
        return out
