"""Height priority for #20: numeric DI, matched archive, surveyed deck + truth fact (#106).

Flags retain disagreements even when DI wins. Local reviewed evidence resolves flagged fallback
cases; it is not a gate for ordinary track and cannot override a numeric DI height.
"""

import math

TOLERANCE = 0.3


def usable(z):
    return isinstance(z, (int, float)) and math.isfinite(z) and 100 < z < 500


class HeightGuard:
    def __init__(self, evidence=(), alignment_reviews=(), conflicts=()):
        self.evidence = list(evidence)
        self.by_di = {}
        self.conflicts = {str(i) for i in conflicts}
        self.reviews = {}
        for review in alignment_reviews:
            if (
                review.get('dataset') not in ('di', 'archive')
                or review.get('status') not in ('obsolete', 'uncertain', 'current')
                or not review.get('source')
            ):
                raise ValueError('alignment review needs dataset, id, status and source')
            key = (review['dataset'], str(review['id']))
            if key in self.reviews:
                raise ValueError(f'duplicate alignment review: {key}')
            self.reviews[key] = review
        ids = set()
        for e in self.evidence:
            source = e.get('source', {})
            if (
                not e.get('id')
                or e['id'] in ids
                or not e.get('di_id')
                or e.get('reviewed') is not True
                or e.get('vertical_datum') != 'Bpv'
                or e.get('height_meaning') != 'top_of_rail'
                or not usable(e.get('z'))
                or e.get('kind') not in ('surface', 'deck', 'tunnel')
                or type(e.get('level')) is not int
                or not source.get('record')
                or not source.get('date')
                or source.get('dataset', '').lower()
                in ('', 'di', 'archive', 'dtm-di', 'dtmp-tracks', 'compiled-zps')
                or len(e.get('xy', [])) != 2
                or not all(math.isfinite(v) for v in e['xy'])
                or not 0 < e.get('radius_m', 0) <= 1
            ):
                raise ValueError(
                    'height evidence needs unique id, track/point scope, reviewed independent source, Bpv rail height and physical level'
                )
            ids.add(e['id'])
            self.by_di.setdefault(str(e['di_id']), []).append(e)

    def choose(self, di, match, x, y, structure_hint=False, decks=(), tunnel_hint=False):
        flags, candidates = [], []
        identity = str(di['id'])
        review = self.reviews.get(('di', identity), {})
        if usable(di.get('z')):
            candidates.append({'dataset': 'di', 'id': identity, 'z': di['z']})
        near = match.get('candidates', [])
        if near:
            near = [c for c in near if c['distance'] <= near[0]['distance'] + 0.25]
        # A farther numeric track must never replace the nearest one with missing Z.
        for c in near:
            candidate = {'dataset': 'archive', **c}
            if not usable(c.get('z')):
                candidate['excluded'] = 'missing_z'
            elif match['status'] == 'missing_z':
                candidate['excluded'] = 'nearest_archive_missing_z'
            candidates.append(candidate)
        for deck in decks:
            candidate = {'dataset': 'deck' if deck.get('class', 'deck') == 'deck' else 'survey', **deck}
            if not usable(candidate.get('z')):
                candidate['excluded'] = candidate.get('excluded', 'deck_rail_offset_missing')
            elif not candidate.get('inside', True) and 'excluded' not in candidate:
                candidate['excluded'] = 'outside_surveyed_deck'
            candidates.append(candidate)
        if structure_hint:
            flags.append('structure_hint')
        if match['status'] == 'ambiguous':
            flags.append('ambiguous_archive_match')
        if match['status'] == 'missing_z':
            flags.append('nearest_archive_missing_z')
        if any(str(c['id']) in self.conflicts for c in near):
            flags.append('known_archive_disagreement')
        if usable(di.get('z')) and any(
            abs(c['z'] - di['z']) > TOLERANCE
            for c in candidates
            if c['dataset'] == 'archive' and usable(c['z'])
        ):
            flags.append('di_archive_height_disagreement')
        surveyed = [
            c
            for c in candidates
            if c['dataset'] in ('deck', 'survey')
            and usable(c.get('z'))
            and c.get('excluded') in (None, 'outside_surveyed_deck')
        ]
        if surveyed and max(c['z'] for c in surveyed) - min(c['z'] for c in surveyed) > TOLERANCE:
            flags.append(
                'ambiguous_deck_levels'
                if all(c['dataset'] == 'deck' for c in surveyed)
                else 'ambiguous_survey_heights'
            )
        archived = [
            c for c in candidates if c['dataset'] == 'archive' and usable(c.get('z')) and 'excluded' not in c
        ]
        if (
            surveyed
            and archived
            and all(abs(a['z'] - d['z']) > TOLERANCE for a in archived for d in surveyed)
        ):
            flags.append(
                'archive_deck_height_disagreement'
                if all(c['dataset'] == 'deck' for c in surveyed)
                else 'archive_surface_height_disagreement'
            )
        if structure_hint and not surveyed:
            flags.append('structure_unverified')
        if tunnel_hint:
            flags.append('tunnel_unverified')
        if any(c.get('excluded') == 'deck_rail_offset_missing' for c in candidates):
            flags.append('deck_rail_offset_missing')
        for reason in (
            'ambiguous_rail_offset_facts',
            'deck_surface_height_unavailable',
            'survey_surface_height_unavailable',
            'track_zps_level_unverified',
        ):
            if any(c.get('excluded') == reason for c in candidates):
                flags.append(reason)
        if any(c.get('style_defaulted') for c in candidates):
            flags.append('track_style_defaulted_panels')
        for c in candidates:
            r = self.reviews.get((c['dataset'], str(c['id'])), {})
            if r.get('status') in ('obsolete', 'uncertain'):
                c['excluded'] = r['status'] + '_alignment'
                flags.append(c['dataset'] + '_' + c['excluded'])
        out = {
            'status': 'review',
            'z': None,
            'height_source': None,
            'confidence': 'unvalidated',
            'review_flags': sorted(set(flags)),
            'candidates': candidates,
            'evidence_ids': [],
        }
        if review.get('status') in ('obsolete', 'uncertain'):
            out['status'] = 'rejected' if review['status'] == 'obsolete' else 'review'
            out['review_flags'] = sorted(set(out['review_flags'] + ['di_' + review['status'] + '_alignment']))
            return out
        evidence = [e for e in self.by_di.get(identity, []) if math.dist(e['xy'], (x, y)) <= e['radius_m']]
        out['evidence_ids'] = [e['id'] for e in evidence]

        def select(candidate, confidence):
            out.update(
                status='selected',
                z=candidate['z'],
                height_source={'dataset': candidate['dataset'], 'id': candidate['id']},
                confidence=confidence,
            )
            if candidate.get('provenance'):
                out['height_source'].update(candidate['provenance'])
            if candidate['dataset'] == 'deck':
                out['height_source'].update(
                    rail_above_deck_m=candidate['rail_above_deck_m'],
                    offset_fact_ids=candidate['offset_fact_ids'],
                    track_styles=candidate.get('track_styles', []),
                    style_sources=candidate.get('style_sources', []),
                )
            return out

        # The current DI height is used as supplied. Archive/deck disagreements remain visible,
        # but neither the archive nor the optional review file substitutes a different DI value.
        if usable(di.get('z')):
            if evidence and any(abs(e['z'] - di['z']) > TOLERANCE for e in evidence):
                out['review_flags'].append('reviewed_evidence_disagrees_with_di')
            return select(candidates[0], 'di_numeric')
        if evidence and (
            len({e['level'] for e in evidence}) != 1
            or max(e['z'] for e in evidence) - min(e['z'] for e in evidence) > TOLERANCE
        ):
            out['review_flags'].append('conflicting_level_evidence')
            return out
        blocking = {
            'ambiguous_archive_match',
            'known_archive_disagreement',
            'ambiguous_deck_levels',
            'ambiguous_survey_heights',
            'track_zps_level_unverified',
            'archive_deck_height_disagreement',
            'archive_obsolete_alignment',
            'archive_uncertain_alignment',
            'ambiguous_rail_offset_facts',
            'archive_surface_height_disagreement',
            'structure_unverified',
            'tunnel_unverified',
        }
        # A surveyed structure without the rail-above-deck fact cannot validate an archive level.
        if decks and 'deck_rail_offset_missing' in out['review_flags']:
            blocking.add('deck_rail_offset_missing')
        if evidence:
            supported = [
                c
                for c in candidates
                if c['dataset'] != 'survey'
                and 'excluded' not in c
                and all(abs(c['z'] - e['z']) <= TOLERANCE for e in evidence)
            ]
            if not supported or max(c['z'] for c in supported) - min(c['z'] for c in supported) > TOLERANCE:
                out['review_flags'].append('no_unique_supported_height')
                return out
            return select(supported[0], 'reviewed_level_match')
        if blocking.intersection(out['review_flags']):
            return out
        available = [c for c in candidates if c['dataset'] != 'survey' and 'excluded' not in c]
        if not available:
            out['review_flags'].append('no_usable_height')
            return out
        selected = next((c for c in available if c['dataset'] == 'archive'), available[0])
        return select(
            selected, 'archive_plan_match' if selected['dataset'] == 'archive' else 'surveyed_deck_plus_fact'
        )
