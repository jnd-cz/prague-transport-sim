"""Make a place-based review queue from held pedestrian patches (#146).

    python -I tools/crossing_review.py reports/headless/line17-crossing.json

Open ?line=17&review=reports/review/pedestrian-crossings.json for the scene, imagery links and
answers. Regenerate after a crossing check; array indexes are diagnostics, never approved facts.
"""
import argparse
import json
import math
from pathlib import Path
import sys
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic import replacing

ROOT = Path(__file__).resolve().parent.parent


def findings(reports, lines):
    grouped = {}
    for report in reports:
        line = str(report['line'])
        for site in report['result'].get('reviewCandidates', []):
            key = (line, round(site['x'], 1), round(site['y'], 1))
            grouped.setdefault(key, []).append(site)
    out = []
    for (line, x, y), sites in sorted(grouped.items()):
        site = sites[0]
        stops = lines[line].get('stops', [])
        stop = min(stops, key=lambda s: abs(s['s'] - site['s']))['name'] if stops and site.get('s') is not None else None
        yaw = math.degrees(math.atan2(site['ux'], site['uy']))
        query = urlencode({'line': line, 'review': 'reports/review/pedestrian-crossings.json',
                           'at': f'{x},{y},{yaw:.1f},55,30'})
        out.append({'kind': 'pedestrian crossing', 'id': f'crossing-{line}-{x}-{y}', 'line': line,
            'x': x, 'y': y, 's': site.get('s'), 'mag': len(sites), 'status': 'review',
            'info': f"{stop + ': ' if stop else ''}Survey marks a small pedestrian patch here. "
                    'Is this a crossing at rail level, a sidewalk/platform edge, or another level? '
                    'Its height stays held pending reviewed evidence.',
            'review_url': '?' + query,
            'candidates': [{k: v for k, v in s.items() if k not in ('recorded',)} for s in sites]})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('reports', nargs='+', type=Path)
    ap.add_argument('--output', type=Path, default=ROOT/'reports/review/pedestrian-crossings.json')
    args = ap.parse_args()
    reports = [json.loads(p.read_text(encoding='utf-8')) for p in args.reports]
    lines = {str(r['line']): json.loads((ROOT/f"data/line{r['line']}.json").read_text(encoding='utf-8')) for r in reports}
    rows = findings(reports, lines)
    result = {'schema': 1, 'issue': 146,
              'options': ['crossing at rail level', 'sidewalk / platform edge', 'another level', 'unsure'],
              'findings': rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with replacing(args.output, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
        f.write('\n')
    print(f"{sum(len(r['candidates']) for r in rows)} held patches at {len(rows)} places: {args.output}")


if __name__ == '__main__':
    main()
