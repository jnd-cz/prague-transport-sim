# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tile container for a tile's objects: what the game has today, GLB with KHR_mesh_quantization, integer differences (#307).

Cuts each line's objects into tiles and encodes them every way, keeping every format on the data's own lattice, so none loses
position against the source:
- buildings and bridges (lineN.bld.bin, 5 cm): today's int16 triangles with their JSON table; GLB as triangles and as an indexed
  mesh welded per building (positions padded to 8 B, as glTF requires); integer differences welded the same way.
- trees and the other placed things (lineN.geo.json, 10 cm): today's JSON; GLB with EXT_mesh_gpu_instancing (float32, the
  extension's plain form: a quantized one needs a scale that would also scale the mesh); integer differences.

Sizes are per tile, summed: what a game loading tiles would fetch. The densest tile then goes through a page (headless Chromium,
its own server on a free port): decode, then the triangles with flat normals, which is what the buildings end up as in every
format (src/world.js buildLod2: per-face normals, a colour and uv per wall). The page checks that all formats give the same data.

    python -P -E tools/bench/object_container.py [--lines 17,22,9,23,37] [--size 1024] [--runs 15] [--no-page]
(needs brotli, bench-only, and data/; writes reports/object_container/)
"""
import argparse
import gzip
import json
import math
import os
import secrets
import struct
import subprocess
import sys
import tempfile
import time
from collections import defaultdict

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(ROOT, "reports", "object_container")
TREE_Q = 0.1  # m: geo.json's trees are written to one decimal


def zz(a):
    a = np.asarray(a, dtype=np.int64)
    return ((a << 1) ^ (a >> 63)).astype(np.uint64)


def varint(a):
    out = bytearray()
    for v in a.tolist():
        while v >= 0x80:
            out.append(v & 0x7F | 0x80)
            v >>= 7
        out.append(v)
    return bytes(out)


def sizes(b):
    import brotli
    return {"raw": len(b), "gzip": len(gzip.compress(b, 9)), "brotli": len(brotli.compress(b, quality=11))}


def line_tiles(line, size):
    """{(i, j): {"b": [(points on the lattice, kind)], "t": [(x, y, kind)]}}, a building in the tile of its middle."""
    with open(os.path.join(ROOT, "data", f"line{line}.geo.json"), encoding="utf-8") as f:
        geo = json.load(f)
    b, q = geo["buildings"], geo["buildings"]["q"]
    arr = np.fromfile(os.path.join(ROOT, "data", b["file"]), dtype="<i2").reshape(-1, 3).astype(np.int64)
    tiles = defaultdict(lambda: {"b": [], "t": []})
    for ch in b["chunks"]:
        o = np.round(np.array(ch["o"]) / q).astype(np.int64)
        assert np.abs(o * q - np.array(ch["o"])).max() < 1e-6, "a chunk's origin off the lattice"
        v = ch["v"]
        for i, n in enumerate(ch["b"]):
            pts = arr[v:v + n] + o
            v += n
            c = pts[:, :2].mean(0) * q
            tiles[(math.floor(c[0] / size), math.floor(c[1] / size))]["b"].append((pts, (ch.get("k") or [0] * len(ch["b"]))[i]))
    for x, y, k in geo["trees"]:
        tiles[(math.floor(x / size), math.floor(y / size))]["t"].append((x, y, k))
    return tiles, q


def soup(bs):
    P = np.concatenate([p for p, _ in bs])
    lo = P.min(0)
    assert (P - lo).max() < 65536, "a tile wider than ushort at this lattice"
    return P - lo, lo


def weld(bs, lo):
    """Vertices in order of first use, one set per building (a building's walls and roofs are its own); the order of the
    triangles and their winding stay."""
    V, I, nv, nt = [], [], [], []
    for pts, _ in bs:
        seen, start = {}, len(V)
        for p in (pts - lo).tolist():
            p = tuple(p)
            k = seen.get(p)
            if k is None:
                k = seen[p] = len(V)
                V.append(p)
            I.append(k)
        nv.append(len(V) - start)
        nt.append(len(pts) // 3)
    return np.array(V, dtype=np.int64), np.array(I, dtype=np.int64), nv, nt


def table(bs):
    return json.dumps({"b": [len(p) for p, _ in bs], "k": [k for _, k in bs]}, separators=(",", ":")).encode()


def enc_today(bs):
    """The game's own form, cut to a tile: the JSON table (in geo.json today), then the triangles as 16-bit integers."""
    P, _ = soup(bs)
    js = table(bs)
    js += b" " * (-(len(js) + 4) % 2)
    return struct.pack("<I", len(js)) + js + P.astype("<u2").tobytes()


def glb_file(j, body):
    js = json.dumps(j, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    body += b"\0" * (-len(body) % 4)
    return (struct.pack("<III", 0x46546C67, 2, 28 + len(js) + len(body)) + struct.pack("<I", len(js)) + b"JSON" + js
            + struct.pack("<I", len(body)) + b"BIN\0" + body)


def enc_glb(bs, q, indexed):
    """One mesh, the lattice as the node's scale (nothing lost), the per-building table in the node's extras."""
    P, lo = soup(bs)
    V, I = P, None
    if indexed:
        V, I, _, _ = weld(bs, lo)
    pos = np.zeros((len(V), 4), "<u2")  # (a vertex attribute starts on 4 bytes: ushort x, y, z and 2 B of padding)
    pos[:, :3] = V
    body = pos.tobytes()
    views = [{"buffer": 0, "byteOffset": 0, "byteLength": len(body), "byteStride": 8, "target": 34962}]
    accessors = [{"bufferView": 0, "componentType": 5123, "count": len(V), "type": "VEC3",
                  "min": [int(v) for v in V.min(0)], "max": [int(v) for v in V.max(0)]}]
    prim = {"attributes": {"POSITION": 0}}
    if indexed:
        small = len(V) < 65536
        idx = I.astype("<u2" if small else "<u4").tobytes()
        pad = b"\0" * (-len(idx) % 4)
        views.append({"buffer": 0, "byteOffset": len(body), "byteLength": len(idx), "target": 34963})
        accessors.append({"bufferView": 1, "componentType": 5123 if small else 5125, "count": len(I), "type": "SCALAR"})
        prim["indices"] = 1
        body += idx + pad
    j = {"asset": {"version": "2.0"}, "extensionsUsed": ["KHR_mesh_quantization"], "extensionsRequired": ["KHR_mesh_quantization"],
         "scenes": [{"nodes": [0]}], "scene": 0,
         "nodes": [{"mesh": 0, "translation": (lo * q).tolist(), "scale": [q] * 3, "extras": json.loads(table(bs))}],
         "meshes": [{"primitives": [prim]}], "buffers": [{"byteLength": len(body)}], "bufferViews": views, "accessors": accessors}
    return glb_file(j, body)


def enc_delta(bs, q):
    """The ground's format (tile_container.py) with the lattice in the header and a varint table per building: vertices as
    differences to the previous one, each triangle's indices as differences to the previous triangle's first index."""
    P, lo = soup(bs)
    V, I, nv, nt = weld(bs, lo)
    assert (V[I] == P).all(), "welding changed the triangles"
    T = I.reshape(-1, 3)
    tab = np.array([[a, b, k] for a, b, (_, k) in zip(nv, nt, bs)], dtype=np.uint64)
    dv = np.diff(V, axis=0, prepend=V[:1] * 0)
    dt = T - np.concatenate([[0], T[:-1, 0]])[:, None]
    head = struct.pack("<III3i3d", len(bs), len(V), len(T), *[int(v) for v in lo], q, q, q)  # (doubles: 0.05 in float32 turned slivers over)
    return head + varint(tab.ravel()) + varint(zz(dv.ravel())) + varint(zz(dt.ravel()))


def placed(ts):
    """The placed things on the 10 cm lattice, by kind, then row by row: what both binary forms keep."""
    A = np.array([(k, round(y / TREE_Q), round(x / TREE_Q)) for x, y, k in ts], dtype=np.int64)
    A = A[np.lexsort((A[:, 2], A[:, 1], A[:, 0]))]
    return A[:, 0], A[:, 2], A[:, 1]


def enc_trees_json(ts):
    return json.dumps([list(t) for t in ts], separators=(",", ":")).encode()


def enc_trees_delta(ts):
    K, X, Y = placed(ts)
    kinds, counts = np.unique(K, return_counts=True)
    lo = (int(X.min()), int(Y.min()))
    xy = np.column_stack([X - lo[0], Y - lo[1]])
    d = np.diff(xy, axis=0, prepend=xy[:1] * 0)
    head = struct.pack("<II2i", len(K), len(kinds), *lo)
    return head + varint(np.column_stack([kinds, counts]).astype(np.uint64).ravel()) + varint(zz(d.ravel()))


def enc_trees_glb(ts):
    """One node per kind with EXT_mesh_gpu_instancing, on one placeholder triangle (the game draws its own crown and trunk)."""
    K, X, Y = placed(ts)
    lo = np.array([X.min(), Y.min()]) * TREE_Q
    tri = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], "<f4")
    body = tri.tobytes()
    views = [{"buffer": 0, "byteOffset": 0, "byteLength": len(body), "target": 34962}]
    accessors = [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [0, 0, 0], "max": [1, 1, 0]}]
    nodes = []
    for k in np.unique(K):
        m = K == k
        t = np.column_stack([X[m] * TREE_Q - lo[0], Y[m] * TREE_Q - lo[1], np.zeros(m.sum())]).astype("<f4")
        views.append({"buffer": 0, "byteOffset": len(body), "byteLength": t.size * 4})
        accessors.append({"bufferView": len(views) - 1, "componentType": 5126, "count": len(t), "type": "VEC3"})
        nodes.append({"mesh": 0, "translation": [float(lo[0]), float(lo[1]), 0], "extras": {"k": int(k)},
                      "extensions": {"EXT_mesh_gpu_instancing": {"attributes": {"TRANSLATION": len(accessors) - 1}}}})
        body += t.tobytes()
    j = {"asset": {"version": "2.0"}, "extensionsUsed": ["EXT_mesh_gpu_instancing"], "extensionsRequired": ["EXT_mesh_gpu_instancing"],
         "scenes": [{"nodes": list(range(len(nodes)))}], "scene": 0, "nodes": nodes,
         "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
         "buffers": [{"byteLength": len(body)}], "bufferViews": views, "accessors": accessors}
    return glb_file(j, body)


BUILDINGS = {"today": lambda b, q: enc_today(b), "glb": lambda b, q: enc_glb(b, q, False), "glb-indexed": lambda b, q: enc_glb(b, q, True), "delta": enc_delta}
TREES = {"json": enc_trees_json, "glb": enc_trees_glb, "delta": enc_trees_delta}
FILES = {"today": "bld.today", "glb": "bld.glb", "glb-indexed": "bld-indexed.glb", "delta": "bld.delta"}
TREE_FILES = {"json": "trees.json", "glb": "trees.glb", "delta": "trees.delta"}


def add(total, name, s):
    for k, v in s.items():
        total[name][k] = total[name].get(k, 0) + v


def row(name, s, tris):
    per = f"  ({s['brotli'] / tris:.2f} B/triangle)" if tris else ""
    return f"  {name:12s} raw {s['raw'] / 1024:9,.0f} kB  gzip {s['gzip'] / 1024:9,.0f} kB  brotli {s['brotli'] / 1024:9,.0f} kB{per}"


def browser(runs):
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory() as d:
        ready = os.path.join(d, "ready.json")
        srv = subprocess.Popen([sys.executable, "-I", os.path.join(ROOT, "tools", "serve.py"), "0", "--identity", secrets.token_hex(8), "--ready-file", ready],
                               cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                if os.path.exists(ready):
                    break
                time.sleep(0.1)
            with open(ready, encoding="utf-8") as f:
                port = json.load(f)["port"]
            with sync_playwright() as p:
                b = p.chromium.launch()
                page = b.new_page()
                page.goto(f"http://localhost:{port}/tools/bench/object_container.html")
                r = {"buildings": page.evaluate(f"runBuildings({runs})"), "trees": page.evaluate(f"runTrees({runs})"), "worker": page.evaluate(f"runWorker({runs})")}
                b.close()
            return r
        finally:
            srv.kill()
            srv.wait()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lines", default="17")
    ap.add_argument("--size", type=float, default=1024)
    ap.add_argument("--runs", type=int, default=15)
    ap.add_argument("--no-page", action="store_true")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    res, densest, densest_t = {}, (0, None, None), (0, None)
    for line in args.lines.split(","):
        tiles, q = line_tiles(line, args.size)
        tb, tt = defaultdict(dict), defaultdict(dict)
        tris = instances = 0
        for tile in tiles.values():
            if tile["b"]:
                n = sum(len(p) for p, _ in tile["b"]) // 3
                tris += n
                for name, enc in BUILDINGS.items():
                    add(tb, name, sizes(enc(tile["b"], q)))
                if n > densest[0]:
                    densest = (n, tile["b"], q)
            if tile["t"]:
                instances += len(tile["t"])
                for name, enc in TREES.items():
                    add(tt, name, sizes(enc(tile["t"])))
                if len(tile["t"]) > densest_t[0]:
                    densest_t = (len(tile["t"]), tile["t"])
        print(f"line {line}: {len(tiles)} tiles of {args.size:.0f} m, {tris:,} building triangles, {instances:,} placed things")
        print(" buildings")
        for name, s in tb.items():
            print(row(name, s, tris))
        print(" placed things")
        for name, s in tt.items():
            print(row(name, s, 0))
        res[line] = {"tiles": len(tiles), "triangles": tris, "instances": instances, "buildings": dict(tb), "trees": dict(tt)}
    n, bs, q = densest
    for name, enc in BUILDINGS.items():
        with open(os.path.join(OUT, FILES[name]), "wb") as f:
            f.write(enc(bs, q))
    for name, enc in TREES.items():
        with open(os.path.join(OUT, TREE_FILES[name]), "wb") as f:
            f.write(enc(densest_t[1]))
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"q": q, "instances": densest_t[0], "triangles": n}, f)
    res["densest"] = {"triangles": n, "buildings": len(bs), "instances": densest_t[0],
                      "sizes": {name: sizes(enc(bs, q)) for name, enc in BUILDINGS.items()},
                      "treeSizes": {name: sizes(enc(densest_t[1])) for name, enc in TREES.items()}}
    print(f"densest tile: {n:,} building triangles in {len(bs):,} buildings; {densest_t[0]:,} placed things in the densest for those")
    for name, s in res["densest"]["sizes"].items():
        print(row(name, s, n))
    for name, s in res["densest"]["treeSizes"].items():
        print(row(name, s, 0))
    if not args.no_page:
        res["page"] = browser(args.runs)
        print(f"page, median of {args.runs} runs (ms):", json.dumps(res["page"]))
    with open(os.path.join(OUT, "result.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
