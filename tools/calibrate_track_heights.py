"""Independent DI-minus-survey calibration, split by construction evidence (#106).

    python -P -E tools/calibrate_track_heights.py --input reports/track-heights.json

Does not choose heights or change truth facts. Unknown material stays unknown, even when the game
draws panels by default. Histograms retain diagnostics from excluded surfaces, including overpasses.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from atomic import replacing
from dtmp_tracks import ROOT, quantile
from track_context import load_context
from track_decks import load_decks
from track_heights import usable
from shapely.geometry import Point, LineString
from shapely.ops import unary_union


def summarize(rows):
    values, weights = [v for v,w in rows], [w for v,w in rows]
    return {'samples':len(rows), 'metres':round(sum(weights),3),
            **{k:round(quantile(values,weights,p),4) for k,p in [('p10',.1),('median',.5),('p90',.9)]},
            'over_03m':sum(abs(v)>.3 for v in values), 'over_1m':sum(abs(v)>1 for v in values),
            'over_3m':sum(abs(v)>3 for v in values)}


def calibrate(report, context):
    groups, raw_groups, examples = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in report['height_samples']:
        if not usable(r['raw_di_z']):
            continue
        surfaces = [c for c in r['candidates'] if c['dataset'] in ('survey','deck') and usable(c.get('surface_z'))]
        if 'tangent' not in r:
            raise ValueError('regenerate staging with DI tangents before calibration')
        ux,uy = r['tangent']
        kind = context.classify(*r['xy'],ux,uy,surfaces)
        seen = set()
        for c in surfaces:
            if not c.get('inside'):
                continue
            identity = (c.get('class','deck'), c['level'], round(c['surface_z'],6))
            if identity in seen:
                continue
            seen.add(identity)
            delta = r['raw_di_z'] - c['surface_z'] - c.get('rail_above_deck_m',0)
            # Deduplicate repeated coverage from several compiled lines, per sample and class/level/Z.
            key = (kind['kind'], ','.join(kind['styles']) or 'unmarked', c.get('class','deck'), c['level'])
            groups[key].append((delta,r['weight_m']))
            raw_groups[key].append((r['raw_di_z'] - c['surface_z'],r['weight_m']))
            if c.get('class') == 'green' or abs(delta)>3:
                examples[str(key)].append({'di_id':r['di_id'],'xy':r['xy'],'di_z':r['raw_di_z'],
                                          'surface':c,'delta_m':delta,'construction':kind})
    return {'groups':[{'construction':k[0],'styles':k[1],'class':k[2],'level':k[3],**summarize(v),
                       'di_minus_raw_surface':summarize(raw_groups[k])} for k,v in sorted(groups.items())],
            'examples':dict(examples)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input',type=Path,required=True)
    ap.add_argument('--output',type=Path,default=ROOT/'reports/track-height-calibration.json')
    ap.add_argument('--summary-output',type=Path,help='Small review artifact with groups and green-surface sites')
    a = ap.parse_args()
    report = json.loads(a.input.read_text(encoding='utf-8'))
    result = calibrate(report,load_context(load_decks(ROOT)))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with replacing(a.output,'w',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    if a.summary_output:
        from dtmp_tracks import load_line
        stops = {}
        for n in (9,17,22,23,37):
            data = load_line(n)
            route = LineString([p[:2] for p in data['path']])
            for st in data['stops']:
                p = route.interpolate(st['s'])
                stops[(st['name'],round(p.x),round(p.y))] = p
        green = [e for rows in result['examples'].values() for e in rows if e['surface']['class']=='green']
        clusters = unary_union([Point(e['xy']).buffer(25) for e in green])
        sites = []
        for polygon in getattr(clusters,'geoms',[clusters]):
            rows = [e for e in green if polygon.covers(Point(e['xy']))]
            if not rows:
                continue
            p = polygon.centroid
            names = []
            for (name,x,y),distance in sorted(((key,point.distance(p)) for key,point in stops.items()),key=lambda r:r[1]):
                if name not in names:
                    names.append(name)
                if len(names)==2:
                    break
            sites.append({'xy':[round(p.x,3),round(p.y,3)],'near_stops':names,'samples':len(rows),
                          'di_ids':sorted({str(e['di_id']) for e in rows}),
                          'construction':sorted({e['construction']['kind'] for e in rows}),
                          'explicit_styles':sorted({s for e in rows for s in e['construction']['styles']}),
                          'di_minus_raw_green':summarize([(e['di_z']-e['surface']['surface_z'],1) for e in rows])})
        summary = {'snapshot':report['snapshot'],'groups':result['groups'],'green_sites':sites,
                   'construction_assessments':json.loads((ROOT/'data/truth.json').read_text(encoding='utf-8')).get('trackHeights',{}).get('surveyCalibrationSites',[]),
                   'survey_grass_offset_adopted':False,
                   'reason':'Green survey class alone does not identify grass track. Keep drawing offset separate.'}
        a.summary_output.parent.mkdir(parents=True,exist_ok=True)
        with replacing(a.summary_output,'w',encoding='utf-8') as f:
            json.dump(summary,f,ensure_ascii=False,indent=2)
    print(json.dumps(result['groups'],indent=2))


if __name__=='__main__':
    main()
