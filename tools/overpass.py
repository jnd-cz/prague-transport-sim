"""Polite Overpass queries: small pieces, cached, slow, with retries.

The public servers refuse big queries when busy (the line 9 platforms came back empty, 504/502 "at
capacity"). Every query here is cached by its text in raw/overpass/ (a fetched piece is never asked
again), waits PAUSE s between requests, and retries with exponential backoff across the mirrors.
Meant to run in the background, ahead of the coverage we plan to build.

    from overpass import query, pieces
    for bbox in pieces(points_lat_lon, size=800): els += query(f"...({bbox})...")["elements"]
"""
import hashlib
import json
import math
import os
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "raw", "overpass")
# the free, keyless public instances with world data (wiki.openstreetmap.org/wiki/Overpass_API, 2026-10),
# last the French one: not on the list, answers fast, but its data lagged ~3 months (2026-07-28 in
# 2026-10); each answer's data date goes to the log
SERVERS = ["https://overpass-api.de/api/interpreter",
           "https://overpass.private.coffee/api/interpreter",
           "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
           "https://overpass.openstreetmap.fr/api/interpreter"]
PAUSE = 5.0  # s between requests
_last = [0.0]


def query(q, tries=12, log=print):
    """Overpass JSON for query q (cached). Raises after `tries` failed attempts."""
    os.makedirs(CACHE, exist_ok=True)
    f = os.path.join(CACHE, hashlib.sha1(q.encode()).hexdigest()[:16] + ".json")
    if os.path.exists(f):
        return json.load(open(f, encoding="utf-8"))
    wait = 10.0
    for k in range(tries):
        time.sleep(max(0.0, _last[0] + PAUSE - time.time()))
        url = SERVERS[k % len(SERVERS)]
        try:
            req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(),
                                         headers={"User-Agent": "tram-game-prototype/0.1"})
            with urllib.request.urlopen(req, timeout=200) as r:
                data = r.read()
            _last[0] = time.time()
            js = json.loads(data)  # (a busy server answers 200 with an HTML page sometimes)
            if "remark" in js and "runtime error" in js["remark"]:
                raise RuntimeError(js["remark"][:120])
            open(f, "wb").write(data)
            log(f"  overpass {url.split('/')[2]}: ok, data of {js.get('osm3s', {}).get('timestamp_osm_base', '?')}", flush=True)
            return js
        except Exception as e:  # noqa: BLE001
            _last[0] = time.time()
            # (429 / 406: the main server's policy asks for 30 s at least)
            code = getattr(e, "code", None)
            log(f"  overpass {url.split('/')[2]}: {str(e)[:80]}; retry in {max(wait, 30 if code in (429, 406) else 0):.0f} s", flush=True)
            time.sleep(max(wait, 30 if code in (429, 406) else 0))
            wait = min(wait * 2, 300)
    raise RuntimeError("overpass: no answer after %d tries" % tries)


def pieces(latlon, size=800.0, pad=40.0):
    """Bounding boxes 's,w,n,e' covering a polyline of (lat, lon) in pieces of ~size m, padded."""
    if not latlon:
        return []
    ky, kx = 110574.0, math.cos(math.radians(latlon[0][0])) * 111320.0
    out, cur, acc = [], [latlon[0]], 0.0
    for a, b in zip(latlon, latlon[1:]):
        acc += math.hypot((b[0] - a[0]) * ky, (b[1] - a[1]) * kx)
        cur.append(b)
        if acc >= size:
            out.append(cur)
            cur, acc = [b], 0.0
    if len(cur) > 1 or not out:
        out.append(cur)
    boxes = []
    for c in out:
        la, lo = [p[0] for p in c], [p[1] for p in c]
        boxes.append(f"{min(la) - pad / ky:.6f},{min(lo) - pad / kx:.6f},{max(la) + pad / ky:.6f},{max(lo) + pad / kx:.6f}")
    return boxes
