# SPDX-License-Identifier: AGPL-3.0-or-later
"""How far a line's drawn tracks lie from DI's own records, where DI has the track (#237):
    python -P -E tools/bench/track_deviation.py --lines 17,37 [--top 10] [--json reports/track-deviation.json]

Every 0.5 m along each drawn track (data/lineN.json `tracks`, the fitted curves), the distance to the nearest DI
record (tools/di_tracks.py `Source`, the records as delivered). Points farther than COVER from any record are where
DI has no track (fills, the orthophoto's tracks) and are not counted. Prints per line the share within 2 / 5 / 10 cm,
p99 and the largest deviation, and the worst places (one per GROUP m) with their distance.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import shapely  # noqa: E402
import di_tracks  # noqa: E402
from geo import Frame  # noqa: E402

COVER = 1.0    # m: farther from every DI record, DI has no track there
GROUP = 20.0   # m: one worst place per this


def deviation(tracks, tree, lines):
    out = []   # (d, x, y)
    for t in tracks:
        l = shapely.LineString(t['p'])
        n = max(1, int(l.length / 0.5))
        pts = shapely.line_interpolate_point(l, [l.length * i / n for i in range(n + 1)])
        for p in pts:
            near = tree.query(p.buffer(COVER))
            if len(near):
                d = min(lines[int(j)].distance(p) for j in near)
                if d <= COVER:
                    out.append((d, p.x, p.y))
    return out


def main():
    args = sys.argv[1:]
    root = Path(__file__).resolve().parent.parent.parent
    lines_ = args[args.index('--lines') + 1].split(',') if '--lines' in args else ['9', '17', '22', '23', '37']
    top = int(args[args.index('--top') + 1]) if '--top' in args else 10
    di, _ = di_tracks.load_sources()
    lines = [c['line'] for c in di.chains]
    tree = shapely.STRtree(lines)
    frame, report = Frame(), {}
    for line in lines_:
        data = json.loads((root / 'data' / f'line{line}.json').read_text(encoding='utf-8'))
        dev = deviation(data['tracks'], tree, lines)
        ds = sorted(d for d, _, _ in dev)
        q = lambda f, ds=ds: ds[min(len(ds) - 1, int(f * len(ds)))] if ds else 0.0
        worst = []
        for d, x, y in sorted(dev, reverse=True):
            if all(math.dist((x, y), w[1:]) > GROUP for w in worst):
                worst.append((d, x, y))
            if len(worst) >= top:
                break
        share = lambda lim, ds=ds: sum(d <= lim for d in ds) / (len(ds) or 1)
        report[line] = {'points': len(ds), 'within_2cm': round(share(0.02), 4), 'within_5cm': round(share(0.05), 4),
                        'within_10cm': round(share(0.10), 4), 'p99_m': round(q(0.99), 3), 'max_m': round(ds[-1], 3) if ds else 0,
                        'worst': [{'m': round(d, 3), 'll': [round(float(v), 5) for v in frame.ll(x, y)]} for d, x, y in worst]}
        r = report[line]
        print(f"line {line}: {r['points']} points; within 2 cm {r['within_2cm']:.1%}, 5 cm {r['within_5cm']:.1%}, "
              f"10 cm {r['within_10cm']:.1%}; p99 {r['p99_m']} m, max {r['max_m']} m")
        for w in r['worst']:
            print(f"   {w['m']:.3f} m  {w['ll'][0]:.5f} N {w['ll'][1]:.5f} E")
    if '--json' in args:
        Path(args[args.index('--json') + 1]).write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
