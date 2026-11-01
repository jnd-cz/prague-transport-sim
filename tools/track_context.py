"""Track construction evidence for height checks; a default panel drawing is not survey proof."""
from shapely.geometry import Point

from dtmp_tracks import Segments
from geo import Frame

PAVED = {'asphalt', 'concrete', 'concrete:plates', 'paving_stones', 'sett', 'cobblestone', 'paved'}
OPEN = {'grass', 'gravel', 'fine_gravel', 'ballast', 'ground', 'dirt', 'sand'}


class TrackContext:
    def __init__(self, ways=(), regions=()):
        self.regions = regions
        self.tags, paths = {}, []
        for way in ways:
            x, y = Frame().xy([p['lat'] for p in way['geometry']], [p['lon'] for p in way['geometry']])
            self.tags[str(way['id'])] = way['tags']
            paths.append({'id': way['id'], 'coords': [(float(a), float(b), None) for a,b in zip(x,y)],
                          'attrs': way['tags']})
        self.paths = paths
        self.index = Segments(paths)

    def classify(self, x, y, ux=1, uy=0, surfaces=()):
        point = Point(x,y)
        marks = [r for r in self.regions if r['polygon'].covers(point)]
        styles = {r['style'] for r in marks}
        evidence, modes = [], set()
        if styles:
            modes = {'open' if s in ('grass','ballast') else 'paved' for s in styles}
            evidence = [{'kind':'truth_style', 'style':r['style'], 'source':r.get('source',{})} for r in marks]
        else:
            hit = self.index.match(x,y,ux,uy,radius=2,details=True)
            near = hit['candidates']
            for candidate in near:
                if candidate['distance'] > near[0]['distance'] + .25:
                    continue
                tags = self.tags[str(candidate['id'])]
                surface = tags.get('surface')
                mode = ('paved' if surface in PAVED or tags.get('embedded_rails') == 'tram'
                        else 'open' if surface in OPEN else None)
                if mode:
                    modes.add(mode)
                    evidence.append({'kind':'osm_track', 'way':candidate['id'], 'tags':tags,
                                     'distance_m':candidate['distance']})
            # A road/paved polygon at the axis is positive pavement evidence. The generic ZPS tram
            # outline is not: it can follow ditches and embankment toes around an open track bed.
            if not modes:
                for c in surfaces:
                    if (c.get('inside') and c.get('class') in ('road','paved','parking') and c.get('level') == 0
                            and c.get('excluded') not in ('survey_level_mismatch','track_zps_level_unverified',
                                                         'non_track_surface','surface_on_other_level')):
                        modes.add('paved')
                        evidence.append({'kind':'survey_pavement', 'record':c['id'], 'class':c['class']})
        return {'kind': next(iter(modes)) if len(modes) == 1 else 'unknown',
                'styles':sorted(styles), 'evidence':evidence,
                'reason':'conflicting_construction_evidence' if len(modes)>1 else
                         'explicit_construction_evidence' if modes else 'no_surface_material_evidence'}


def load_context(decks):
    from osm_local import ways
    return TrackContext(ways(lambda t:t.get('railway')=='tram' or t.get('embedded_rails')=='tram'), decks.style_regions)
