"""Vertical track profile: the smallest change to the selected rail heights that keeps every change of grade
within the design radius (#188).

    python -P -E tools/track_profile.py --check          # the review queue's profiles before / after
    python -P -E tools/track_profile.py --calibrate      # against numeric DI (needs reports/track-heights.json)
    python -P -E tools/track_profile.py --steps          # where the curve cannot follow the selected heights, by cause

A tram track is built of grades joined by vertical curves of radius at least 500 m in a street in closed
built-up areas and 1000 m on open track and in switches (data/truth.json trackGeometry, ČSN 73 6412 as quoted
by Hradil 2020). The archived heights wiggle by 0.1-0.3 m at record joints and between vertices (a 0.27 m bump
over 7 m at Hlavní nádraží is a radius of ~75 m), which a driver would feel and the cab view would show. The fit
keeps the data where its curvature is within 1/R and bends it least where it is not; points that the curve
cannot follow lose weight (Tukey), so a lone bump is dropped rather than spread over its neighbours.
"""
import argparse
import json
import math
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parent.parent
ITERATIONS, ROBUST, TOL = 3000, 6, 1.02  # ADMM steps, robust reweighting rounds, radius tolerance
STEP = .3  # m: a point the curve misses by more is a step (#184's departure threshold), not a wiggle


def radii(truth=None):
    """The design minimum radii (street, open track, switch) from data/truth.json."""
    truth = truth or json.loads((ROOT/'data/truth.json').read_text(encoding='utf-8'))
    facts = {f['id']:f['value'] for f in truth['trackGeometry']['facts']}
    return {'street':facts['vertical-radius-street'],'open':facts['vertical-radius-open-track'],
            'switch':facts['vertical-radius-switch']}


def curvature(s, z):
    """Second derivative at the inner points of an uneven (s, z) series."""
    out = []
    for i in range(1,len(s)-1):
        h0, h1 = s[i]-s[i-1], s[i+1]-s[i]
        out.append(2*((z[i+1]-z[i])/h1-(z[i]-z[i-1])/h0)/(h0+h1))
    return out


def _second(s):
    """The rows of the second-difference operator: {column: coefficient} for each inner point."""
    rows = []
    for i in range(1,len(s)-1):
        h0, h1 = s[i]-s[i-1], s[i+1]-s[i]
        c = 2/(h0+h1)
        rows.append({i-1:c/h0, i:-c*(1/h0+1/h1), i+1:c/h1})
    return rows


def _factor(n, w, rows, lam):
    """Banded Cholesky of diag(w) + D^T diag(lam) D (pentadiagonal)."""
    A = [[0.0]*3 for _ in range(n)]  # A[i][k]: row i, column i+k
    for i in range(n):
        A[i][0] += w[i]
    for r,l in zip(rows,lam):
        for a,da in r.items():
            for e,de in r.items():
                if e >= a:
                    A[a][e-a] += l*da*de
    L = [[0.0]*3 for _ in range(n)]  # L[i][k]: row i, column i-k
    for i in range(n):
        for k in (2,1):
            j = i-k
            if j < 0:
                continue
            v = A[j][k] - sum(L[i][k+m]*L[j][m] for m in range(1,3-k) if j-m >= 0 and k+m <= 2)
            L[i][k] = v/L[j][0]
        v = A[i][0]-sum(L[i][k]**2 for k in (1,2) if i-k >= 0)
        L[i][0] = math.sqrt(max(v,1e-12))
    return L


def _back(L, b):
    n = len(L)
    y = [0.0]*n
    for i in range(n):
        y[i] = (b[i]-sum(L[i][k]*y[i-k] for k in (1,2) if i-k >= 0))/L[i][0]
    f = [0.0]*n
    for i in range(n-1,-1,-1):
        f[i] = (y[i]-sum(L[i+k][k]*f[i+k] for k in (1,2) if i+k < n))/L[i][0]
    return f


def _solve(s, z, w, lam):
    """argmin sum w (z-f)^2 + sum lam_i (f''_i)^2."""
    rows = _second(s)
    return _back(_factor(len(s),w,rows,lam[1:-1]),[a*b for a,b in zip(w,z)])


def _capped(s, z, w, cap, rows, f=None, u=None, y=None):
    """argmin sum w (z-f)^2 subject to |f''_i| <= cap_i, by ADMM on u = D f (one factorisation)."""
    n, m = len(s), len(rows)
    h = sorted(b-a for a,b in zip(s,s[1:]))[(n-1)//2]
    rho = max(h,.5)**4  # (D's entries ~ 1/h^2: rho D^T D ~ the data weights)
    L = _factor(n,w,rows,[rho]*m)
    f = f or list(z)
    Df = lambda f: [sum(c*f[j] for j,c in r.items()) for r in rows]
    u = u or [max(-c,min(c,v)) for v,c in zip(Df(f),cap)]
    y = y or [0.0]*m
    for it in range(ITERATIONS):
        q = [ui-yi for ui,yi in zip(u,y)]
        b = [wi*zi for wi,zi in zip(w,z)]
        for r,qi in zip(rows,q):
            for j,c in r.items():
                b[j] += rho*c*qi
        f = _back(L,b)
        d = Df(f)
        u = [max(-c,min(c,v+yi)) for v,yi,c in zip(d,y,cap)]
        y = [yi+v-ui for yi,v,ui in zip(y,d,u)]
        if it % 25 == 24 and all(abs(v) <= c*TOL for v,c in zip(d,cap)):
            break
    return f,u,y


def vertical_profile(s, z, rmin, weight=None, pins=(), scale=.05, pin_weight=1e6):
    """Heights along one track (s ascending, metres) bent least so that no change of grade is tighter than
    rmin (a number or one per point). weight: confidence per point (0 drops it), pins: indices held fixed (a
    junction's height, a reviewed DI point) with pin_weight, never dropped as outliers. scale: the noise the curve
    may ignore, Tukey's c = 4.685 scale; a point further off than c after a round no longer pulls the curve.
    Returns the heights, per point what was moved (> 2 cm) for the log, and the tightest radius left."""
    n = len(s)
    if n < 3:
        return {'z':list(z),'moved':[],'min_radius':math.inf}
    rmin = [rmin]*n if isinstance(rmin,(int,float)) else list(rmin)
    base = [1.0]*n if weight is None else [float(x) for x in weight]
    pinned = set(pins)
    for i in pinned:
        base[i] = pin_weight
    rows, cap = _second(s), [1/r for r in rmin[1:-1]]
    w, state, c = list(base), (None,None,None), 4.685*scale
    # A robust start: a plain first round bent the whole curve towards one bad record (Malovanka, an 83 m spike
    # over 25 m, moved 32 good points by over 0.3 m; #190), and Tukey then dropped them too. A point further than
    # 2c from the median of its 11 neighbours starts without a pull; the rounds below may bring it back.
    for i in range(n):
        near = sorted(z[max(0,i-5):i+6])
        if abs(z[i]-near[len(near)//2]) > 2*c and i not in pinned:
            w[i] = 1e-4*base[i]
    for _ in range(ROBUST):
        f,u,y = _capped(s,z,w,cap,rows,*state)
        state = (f,u,y)
        nw = [base[i] if i in pinned else base[i]*((1-((z[i]-f[i])/c)**2)**2 if abs(z[i]-f[i]) < c else 1e-4*base[i])
              for i in range(n)]
        if max(abs(a-b) for a,b in zip(nw,w)) < .01:
            break
        w = nw
    moved = [{'s':round(s[i],2),'from':round(z[i],3),'to':round(f[i],3)} for i in range(n) if abs(f[i]-z[i]) > .02]
    # (a point the curve misses by more than 0.3 m is not a wiggle but a step: another rule's business, #184)
    steps = [m for m in moved if abs(m['to']-m['from']) > STEP]
    return {'z':f,'moved':moved,'steps':steps,'min_radius':min(implied_radii(s,f),default=math.inf)}


SMOOTH = 1.0  # curvature penalty of the band rule, in h^4 (h the median spacing): smooths noise over ~h, not more


def banded_profile(s, z, rmin, tol, weight=None, smooth=SMOOTH):
    """Heights nearest z (least squares, `weight` per point) that stay within `tol` of it (a number or one per point;
    None: no band there, a held bin or a lone bad point) and turn no tighter than rmin, with a small penalty on
    curvature so that a short noisy stretch is not followed into humps (the band rule, #197, 2026-11-03: "If the
    curve >=500m fits within 10cm then it's solved"). ADMM on u = D f (the radius) and v = f (the band), one banded
    factorisation. Returns the heights, whether the band and the radius are met (`fits`), how far each point lies
    outside its band (`excess`) and the tightest radius."""
    n = len(s)
    rmin = [rmin]*n if isinstance(rmin,(int,float)) else list(rmin)
    tol = [tol]*n if tol is None or isinstance(tol,(int,float)) else list(tol)
    if n < 3:
        return {'z':list(z),'fits':True,'excess':[0.0]*n,'min_radius':math.inf}
    w = [1.0]*n if weight is None else [float(x) for x in weight]
    rows, cap = _second(s), [1/r for r in rmin[1:-1]]
    h = sorted(b-a for a,b in zip(s,s[1:]))[(n-1)//2]
    rho1, rho2 = max(h,.5)**4, 1.0
    L = _factor(n,[wi+rho2 for wi in w],rows,[(smooth+1)*rho1]*len(rows))
    Df = lambda f: [sum(c*f[j] for j,c in r.items()) for r in rows]
    box = lambda f, y: [fi+yi if t is None else max(zi-t,min(zi+t,fi+yi)) for fi,yi,zi,t in zip(f,y,z,tol)]
    f = list(z)
    u, v = [max(-c,min(c,d)) for d,c in zip(Df(f),cap)], box(f,[0.0]*n)
    y1, y2 = [0.0]*len(rows), [0.0]*n
    for it in range(ITERATIONS):
        last = f
        b = [wi*zi+rho2*(vi-yi) for wi,zi,vi,yi in zip(w,z,v,y2)]
        for r,ui,yi in zip(rows,u,y1):
            for j,c in r.items():
                b[j] += rho1*c*(ui-yi)
        f = _back(L,b)
        d = Df(f)
        u = [max(-c,min(c,di+yi)) for di,yi,c in zip(d,y1,cap)]
        v = box(f,y2)
        y1 = [yi+di-ui for yi,di,ui in zip(y1,d,u)]
        y2 = [yi+fi-vi for yi,fi,vi in zip(y2,f,v)]
        # (feasible is not yet optimal: the curvature penalty acts only as the curve settles, so it must stop moving)
        if (it % 25 == 24 and all(abs(di) <= c*TOL for di,c in zip(d,cap)) and max(abs(fi-vi) for fi,vi in zip(f,v)) < 1e-3
                and max(abs(fi-li) for fi,li in zip(f,last)) < 1e-6):
            break
    excess = [0.0 if t is None else max(0.0,abs(fi-zi)-t) for fi,zi,t in zip(f,z,tol)]
    fits = max(excess) <= .005 and all(abs(di) <= c*TOL for di,c in zip(Df(f),cap))
    return {'z':f,'fits':fits,'excess':excess,'min_radius':min(implied_radii(s,f),default=math.inf)}


def implied_radii(s, z):
    """The radius each inner point's change of grade implies (inf on a straight grade)."""
    return [1/abs(c) if c else math.inf for c in curvature(s,z)]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--check',action='store_true',help="the review queue's profiles: tightest radius before / after")
    ap.add_argument('--calibrate',action='store_true',help='fit the archive along DI paths and compare with numeric DI')
    ap.add_argument('--steps',action='store_true',help='steps of the selected heights by cause; exit 1 on unexplained ones over 1 m')
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    if not (args.check or args.calibrate or args.steps):
        ap.error('choose --check, --calibrate or --steps')
    if args.check:
        sys.exit(check())
    if args.steps:
        sys.exit(steps())
    calibrate()


def review_profiles():
    """(decision, place, span id, s, z) of every imported review profile: its samples, or its archive points."""
    sys.path.insert(0,str(ROOT/'tools'))
    import track_span_evidence as t
    from shapely.geometry import LineString, Point
    truth = json.loads((ROOT/'data/truth.json').read_text(encoding='utf-8'))
    queue = json.loads((ROOT/'reports/review/track-heights.json').read_text(encoding='utf-8'))
    result = t.from_reviews(t.truth_answers(truth),queue,'data/truth.json')
    spans = {(f['id'],tuple(map(tuple,s['approval_profile']['xy']))):s for f in t.hydrate_findings(queue)['findings'] for s in f['spans']}
    place = {a['decision']:a['place'] for a in truth['trackHeights']['reviewAnswers']}
    for e in result['span_reviews']:
        d = e['id'][len('review-'):]
        for p in e['profiles']:
            span = spans[(d,tuple(map(tuple,p['xy'])))]
            if p['rule']['type']=='samples':
                pts = p['rule']['samples']
            else:
                line = LineString(p['xy'])
                pts = [[line.project(Point(q['xy'])),z] for q,(_,z) in t._series(span)[1] if q['inside']]
            pts = [a for i,a in enumerate(pts) if i==0 or a[0]-pts[i-1][0] >= 1]  # (points under 1 m apart: one)
            if len(pts) >= 3:
                yield d,place.get(d,d),span['id'],[a[0] for a in pts],[a[1] for a in pts]


BIN, JOIN, TURN = 5.0, .3, 15  # m per calibration bin; DI path ends this close and this many degrees apart chain


def chains(paths):
    """DI paths joined end to end into tracks: at a shared end, the pair that continues straightest (within
    15 degrees) is joined; a switch's diverging path starts a chain of its own. [[(path id, reversed), ...]]"""
    ends = {}
    def key(p):
        return (round(p[0]/JOIN),round(p[1]/JOIN))
    def heading(xy, at_start):
        a, b = (xy[0],xy[min(2,len(xy)-1)]) if at_start else (xy[-1],xy[max(-3,-len(xy))])
        return math.atan2(b[1]-a[1],b[0]-a[0])  # (pointing into the path)
    for pid,xy in paths.items():
        if len(xy) < 2:
            continue
        ends.setdefault(key(xy[0]),[]).append((pid,0,heading(xy,True)))
        ends.setdefault(key(xy[-1]),[]).append((pid,1,heading(xy,False)))
    link = {}
    for group in ends.values():
        pairs = sorted(((abs(abs((a[2]-b[2]+math.pi)%(2*math.pi)-math.pi)-math.pi),i,j)
                        for i,a in enumerate(group) for j,b in enumerate(group) if i < j and a[0] != b[0]))
        used = set()
        for dev,i,j in pairs:
            if dev > math.radians(TURN) or i in used or j in used:
                continue
            used |= {i,j}
            a, b = group[i], group[j]
            link[(a[0],a[1])] = (b[0],b[1])
            link[(b[0],b[1])] = (a[0],a[1])
    seen, out = set(), []
    for pid in paths:
        if pid in seen or len(paths[pid]) < 2:
            continue
        # walk back to a chain's start, then forward
        cur, end = pid, 0
        for _ in range(len(paths)):
            nxt = link.get((cur,end))
            if not nxt or nxt[0] == pid:
                break
            cur, end = nxt[0], 1-nxt[1]
        chain, cur, rev = [], cur, end == 1
        while cur not in seen:
            seen.add(cur)
            chain.append((cur,rev))
            nxt = link.get((cur,0 if rev else 1))
            if not nxt:
                break
            cur, rev = nxt[0], nxt[1] == 1
        out.append(chain)
    return out


def calibrate(path=ROOT/'reports/track-heights.json', out=ROOT/'reports/track-profile-calibration.json'):
    """Smooth the archive alone along every chain of DI paths and compare the raw and the smoothed heights with
    numeric DI and, on paved track (rails flush with the surface), with the 2023 lidar: does the rule move the
    archive towards the independent surface where it acts?"""
    from shapely.geometry import LineString, Point
    from geo import Frame
    from ipr_dtm import IprDtm
    print(f'reading {path.name}', flush=True)
    staged = json.loads(path.read_text(encoding='utf-8'))
    paths = {g['id']:[tuple(p) for p in g['xy']] for g in staged['geometry'] if g['dataset']=='di'}
    lines = {pid:LineString(xy) for pid,xy in paths.items() if len(xy) >= 2}
    skip = {'structure_hint','structure_unverified','tunnel_unverified','known_archive_disagreement',
            'ambiguous_archive_match','di_archive_height_disagreement'}
    per = {}
    for h in staged['height_samples']:
        if h['di_id'] not in lines or skip & set(h.get('review_flags',[])):
            continue
        arch = [c for c in h.get('candidates',[]) if c['dataset']=='archive' and isinstance(c.get('z'),(int,float))]
        di = h.get('raw_di_z')
        if not arch and not isinstance(di,(int,float)):
            continue
        per.setdefault(h['di_id'],[]).append((lines[h['di_id']].project(Point(h['xy'])),
                                              arch[0]['z'] if arch else None,arch[0]['id'] if arch else None,
                                              di if isinstance(di,(int,float)) else None,h['xy'],
                                              (h.get('construction') or {}).get('kind')=='paved'))
    del staged
    r, F, ipr = radii(), Frame(), IprDtm()
    stats = {'chains':0}
    rows, where = [], []
    for chain in chains(paths):
        offset, pts = 0.0, []
        for pid,rev in chain:
            L = lines.get(pid)
            if L is None:
                continue
            for s,*rest in per.get(pid,[]):
                pts.append((offset+(L.length-s if rev else s),*rest))
            offset += L.length
        bins = {}
        for s,*rest in pts:
            bins.setdefault(int(s//BIN),[]).append(rest)
        series = []
        for b in sorted(bins):
            v = bins[b]
            med = lambda xs: sorted(xs)[len(xs)//2] if xs else None
            xy = v[len(v)//2][3]
            series.append(((b+.5)*BIN,med([x[0] for x in v if x[0] is not None]),med([x[2] for x in v if x[2] is not None]),
                           {x[1] for x in v if x[1] is not None},xy,all(x[4] for x in v)))
        run = []  # (runs of bins with the archive, cut at a gap over 10 m)
        for item in series+[None]:
            if item and item[1] is not None and (not run or item[0]-run[-1][0] <= 2*BIN+1e-6):
                run.append(item); continue
            if len(run) >= 5:
                s = [x[0] for x in run]; a = [x[1] for x in run]
                res = vertical_profile(s,a,r['street'])
                fit = res['z']
                stats['steps'] = stats.get('steps',0)+len(res['steps'])
                stats['runs_with_steps'] = stats.get('runs_with_steps',0)+bool(res['steps'])
                if res['steps']:
                    big = max(res['steps'],key=lambda m:abs(m['to']-m['from']))
                    at = next(x for x in run if abs(x[0]-big['s']) < 1e-6)
                    where.append({'xy':[round(v,1) for v in at[4]],'points':len(res['steps']),'largest_m':round(big['to']-big['from'],2),
                                  'di_chain':chain[0][0]})
                raw_r = [math.inf]+implied_radii(s,a)+[math.inf]
                paved = [i for i,x in enumerate(run) if x[5]]
                lidar = dict(zip(paved,ipr.sample([run[i][4][0]+F.E0 for i in paved],[run[i][4][1]+F.N0 for i in paved]).tolist())) if paved else {}
                for i,(si,ai,di,ids,xy,pv) in enumerate(run):
                    joint = i > 0 and not (ids & run[i-1][3]) or i < len(run)-1 and not (ids & run[i+1][3])
                    lz = lidar.get(i)
                    lid_r = math.inf
                    if 0 < i < len(run)-1 and all(lidar.get(j) is not None for j in (i-1,i,i+1)):
                        lid_r = implied_radii([run[j][0] for j in (i-1,i,i+1)],[lidar[j] for j in (i-1,i,i+1)])[0]
                    rows.append((ai,fit[i],di,raw_r[i] < r['street'],joint,lz if lz is not None and 100 < lz < 500 else None,
                                 lid_r,bool(res['steps'])))
                stats['chains'] += 1
            run = [item] if item and item[1] is not None else []
    stats['bins'] = len(rows)
    def dist(v):
        v = sorted(v)
        return {'n':len(v),**({k:round(v[min(len(v)-1,int(q*len(v)))],3) for k,q in (('p50',.5),('p90',.9),('p99',.99))} if v else {})}
    def compare(sel, k):
        both = [x for x in sel if x[k] is not None]
        return {'raw':dist([abs(x[0]-x[k]) for x in both]),'smoothed':dist([abs(x[1]-x[k]) for x in both]),
                'closer':round(sum(abs(x[1]-x[k]) < abs(x[0]-x[k])-.005 for x in both)/max(1,len(both)),3),
                'further':round(sum(abs(x[1]-x[k]) > abs(x[0]-x[k])+.005 for x in both)/max(1,len(both)),3)}
    groups = {'all':lambda x:True,'smoothed (raw radius < street radius)':lambda x:x[3],
              'smoothed at a record joint':lambda x:x[3] and x[4],'smoothed inside a record':lambda x:x[3] and not x[4],
              'moved over 0.05 m':lambda x:abs(x[1]-x[0]) > .05,
              'smoothed, runs without a step':lambda x:x[3] and not x[7]}
    lidar_rows = [x for x in rows if x[5] is not None and x[6] != math.inf]
    stats['paved_bins_with_lidar_radius'] = len(lidar_rows)
    stats['share_breaking_radius'] = {'archive':round(sum(x[3] for x in lidar_rows)/max(1,len(lidar_rows)),3),
                                      'lidar':round(sum(x[6] < r['street'] for x in lidar_rows)/max(1,len(lidar_rows)),3),
                                      'both':round(sum(x[3] and x[6] < r['street'] for x in lidar_rows)/max(1,len(lidar_rows)),3)}
    where.sort(key=lambda w:-abs(w['largest_m']))
    for w in where:
        w['lat'],w['lon'] = [round(float(v),6) for v in F.ll(*w['xy'])]
    report = {'bin_m':BIN,'radius_m':r['street'],**stats,'steps_at':where,'groups':{}}
    for name,keep in groups.items():
        sel = [x for x in rows if keep(x)]
        report['groups'][name] = {'bins':len(sel),'moved_m':dist([abs(x[1]-x[0]) for x in sel]),
                                  'vs_di':compare(sel,2),'vs_lidar_paved':compare(sel,5)}
    out.write_text(json.dumps(report,indent=1),encoding='utf-8')
    print({k:v for k,v in report.items() if k not in ('groups','steps_at')})
    for w in where[:12]:
        print('  step', w)
    for name,g in report['groups'].items():
        print(f"{name}: {g['bins']} bins, moved {g['moved_m']}")
        for k in ('vs_di','vs_lidar_paved'):
            c = g[k]
            print(f"  {k}: raw {c['raw']} -> smoothed {c['smoothed']}; closer {c['closer']}, further {c['further']}")


HELD_GAP = 60  # m: a held stretch up to this long is bridged by the curve from both sides (#184); a longer one cuts
BIG = 1.0  # m: a step this large needs its cause decided (#190)
STRUCTURE = {'structure_hint','structure_unverified','tunnel_unverified'}


def cause(points, misses, structure=False):
    """Why the curve misses these selected heights: 'structure' (next to a held structure the curve bridges: its
    deck level is the structure review's), 'di' (numeric DI, used as supplied), 'dip' (every point below the
    curve: the archive on the ground under a deck no source maps, which #184's rule bridges with a curve from both
    sides), 'survey', 'terrain' (the 2023 terrain has the same shape: no source disagrees, a question for review),
    'archive' (the archive departs from the terrain, by less than the import's hold threshold)."""
    if structure:
        return 'structure'
    src = [p['src'] for p in points]
    if all(s == 'di' for s in src):
        return 'di'
    if all(m < 0 for m in misses):
        return 'dip'
    if any(s in ('survey','deck') for s in src):
        return 'survey'
    off = sorted(abs(p['z']-p['terrain']) for p in points if p['terrain'] is not None)
    if off and off[len(off)//2] <= .5:
        return 'terrain'
    return 'archive'


def _held_runs(series):
    """Runs of bins no more than 10 m apart that start and end with a selected height; a held stretch over
    HELD_GAP cuts the run, a shorter one stays in it at weight 0."""
    runs, run = [], []
    for x in series:
        if run and x['s']-run[-1]['s'] > 2*BIN+1e-6:
            runs.append(run); run = []
        run.append(x)
        held = 0
        while held < len(run) and run[-1-held]['w'] == 0:
            held += 1
        if held and run[-1]['s']-run[-held]['s'] > HELD_GAP:
            runs.append(run[:-held]); run = []
    runs.append(run)
    for run in runs:
        while run and run[-1]['w'] == 0:
            run.pop()
        while run and run[0]['w'] == 0:
            run.pop(0)
    return [run for run in runs if len(run) >= 5]


def steps(path=ROOT/'reports/track-heights.json', out=ROOT/'reports/track-profile-steps.json'):
    """The import's selected heights along every chain of DI paths, held ones bridged by the curve at weight 0:
    where it cannot follow within 0.3 m, a step, counted by cause (#190). Fails on a step over 1 m that no rule
    explains: numeric DI is used as supplied, anything else that large is a question."""
    from shapely.geometry import LineString, Point
    from geo import Frame
    print(f'reading {path.name}', flush=True)
    staged = json.loads(path.read_text(encoding='utf-8'))
    paths = {g['id']:[tuple(p) for p in g['xy']] for g in staged['geometry'] if g['dataset']=='di'}
    lines = {pid:LineString(xy) for pid,xy in paths.items() if len(xy) >= 2}
    per = {}
    for h in staged['height_samples']:
        if h['di_id'] not in lines:
            continue
        ok = h['status']=='selected' and isinstance(h.get('z'),(int,float))
        per.setdefault(h['di_id'],[]).append((lines[h['di_id']].project(Point(h['xy'])),{
            'z':h['z'] if ok else None,'src':(h.get('height_source') or {}).get('dataset') if ok else None,
            'terrain':h.get('terrain_z'),'xy':h['xy'],'flags':h.get('review_flags',[])}))
    del staged
    r, F = radii(), Frame()
    med = lambda xs: sorted(xs)[len(xs)//2]
    found, stats = [], {'runs':0,'bins':0,'bridged_bins':0}
    for chain in chains(paths):
        offset, bins = 0.0, {}
        for pid,rev in chain:
            L = lines.get(pid)
            if L is None:
                continue
            for s,p in per.get(pid,[]):
                bins.setdefault(int((offset+(L.length-s if rev else s))//BIN),[]).append(p)
            offset += L.length
        series = []
        for b in sorted(bins):
            v = bins[b]
            sel = [p for p in v if p['z'] is not None]
            p = (sel or v)[len(sel or v)//2]
            series.append({'s':(b+.5)*BIN,'z':med([q['z'] for q in sel]) if sel else None,'w':1.0 if sel else 0.0,
                           'src':p['src'],'terrain':p['terrain'],'xy':p['xy'],'flags':p['flags']})
        for run in _held_runs(series):
            last = None
            for x in run:  # (a held bin's height does not pull the curve: any finite value)
                last = x['z'] if x['z'] is not None else last
                x['zf'] = last
            res = vertical_profile([x['s'] for x in run],[x['zf'] for x in run],r['street'],weight=[x['w'] for x in run])
            stats['runs'] += 1
            stats['bins'] += len(run)
            stats['bridged_bins'] += sum(x['w'] == 0 for x in run)
            groups = []
            for i,x in enumerate(run):
                if x['w'] and abs(res['z'][i]-x['z']) > STEP:
                    if groups and x['s']-run[groups[-1][-1]]['s'] <= 20:
                        groups[-1].append(i)
                    else:
                        groups.append([i])
            for g in groups:
                pts = [run[i] for i in g]
                near = [x for x in run if x['w'] == 0 and min(abs(x['s']-p['s']) for p in pts) <= 20]
                big = max(g,key=lambda i:abs(res['z'][i]-run[i]['z']))
                lat, lon = F.ll(*run[big]['xy'])
                t = run[big]['terrain']
                found.append({'cause':cause(pts,[run[i]['z']-res['z'][i] for i in g],
                                            any(STRUCTURE & set(x['flags']) for x in near)),'largest_m':round(run[big]['z']-res['z'][big],2),'points':len(g),
                              'lat':round(float(lat),5),'lon':round(float(lon),5),'di_chain':chain[0][0],
                              'height_minus_terrain_m':None if t is None else round(run[big]['z']-t,2),
                              'flags':sorted({f for p in pts for f in p['flags']})})
    found.sort(key=lambda f:-abs(f['largest_m']))
    by = {}
    for f in found:
        c = by.setdefault(f['cause'],{'runs':0,'points':0,'over_1m':0})
        c['runs'] += 1
        c['points'] += f['points']
        c['over_1m'] += abs(f['largest_m']) > BIG
    bad = [f for f in found if abs(f['largest_m']) > BIG and f['cause'] not in ('di','dip','structure')]
    out.write_text(json.dumps({'radius_m':r['street'],'held_gap_m':HELD_GAP,**stats,'by_cause':by,'steps':found},
                              indent=1),encoding='utf-8')
    print(stats)
    for k,c in sorted(by.items()):
        print(f'{k}: {c}')
    for f in bad:
        print(f"  {f['cause']} {f['largest_m']:+.2f} m, {f['points']} points at {f['lat']}, {f['lon']}"
              f" (height - terrain {f['height_minus_terrain_m']}) {[x for x in f['flags'] if x != 'track_style_defaulted_panels']}")
    print(f'{len(bad)} steps over {BIG:g} m without a rule to explain them')
    return 1 if bad else 0


def check():
    """Every review profile smoothed to the street radius: the tightest radius before and after, worst first.
    Exit 1 if any is left tighter than the radius (the check failing)."""
    r = radii()['street']
    rows = []
    for d,place,span,s,z in review_profiles():
        out = vertical_profile(s,z,r)
        before = min(implied_radii(s,z),default=math.inf)
        rows.append((before,out['min_radius'],max((abs(a-b) for a,b in zip(out['z'],z)),default=0),place,span,len(out['moved'])))
    rows.sort()
    print(f'{len(rows)} profiles smoothed to R >= {r} m; tightest radius before -> after, largest move:')
    for b,a,mv,place,span,n in rows[:15]:
        print(f'  {b:8.0f} -> {a:8.0f} m  {mv:5.2f} m ({n} points)  {place}  {span}')
    bad = [x for x in rows if x[1]*TOL < r]
    print(f'{sum(1 for x in rows if x[0] < r)} profiles broke the radius before, {len(bad)} after')
    return 1 if bad else 0


if __name__=='__main__':
    main()
