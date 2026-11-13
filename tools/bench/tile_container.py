# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tile container: GLB with KHR_mesh_quantization against integer differences, on terrain_mesh.py's greedy mesh (#307).

Encodes one tile's mesh both ways and measures the bytes (raw, gzip, brotli), the error of the quantized positions
against the source, and the load and decode time in a page (headless Chromium, its own server on a free port):
fetch, decode, typed arrays in a BufferGeometry, normals computed; the integer differences also in a worker, with
the longest stall of the page's thread during the loads. Three.js from the same CDN as the game.

    python -P -E tools/bench/tile_container.py --line 17 [--at X,Y] [--size 1024] [--runs 15]
(needs pydelatin and brotli, bench-only; writes reports/tile_container/)
"""
import gzip
import json
import os
import struct
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import terrain_mesh as tm  # noqa: E402

ROOT = tm.ROOT
OUT = os.path.join(ROOT, "reports", "tile_container")
RUNS = tm.arg("--runs", 15)


def zz(a):
    return ((a << 1) ^ (a >> 63)).astype(np.uint64)


def varint(a):
    out = bytearray()
    for v in a.tolist():
        while v >= 0x80:
            out.append(v & 0x7F | 0x80)
            v >>= 7
        out.append(v)
    return bytes(out)


def order(V, Tr):
    """Vertices row by row, triangles by their largest index: what both formats compress best on."""
    o = np.lexsort((V[:, 0], V[:, 1]))
    rank = np.empty(len(o), np.int64)
    rank[o] = np.arange(len(o))
    T2 = np.sort(rank[Tr], 1)  # (the winding is restored below)
    a, b, c = V[o][T2[:, 0]], V[o][T2[:, 1]], V[o][T2[:, 2]]
    flip = ((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])) > 0  # (rows go south: up is +)
    T2[flip] = T2[flip][:, [0, 2, 1]]
    return V[o], T2[np.lexsort((T2[:, 0], T2.max(1)))]


def delta(V, T):
    """[nv, nt] u32, then varints: x, y, z (cm) as differences to the previous vertex; each triangle's indices as differences
    to the previous triangle's first index."""
    q = np.column_stack([V[:, 0], V[:, 1], np.round(V[:, 2] * 100)]).astype(np.int64)
    dv = np.diff(q, axis=0, prepend=q[:1] * 0)
    prev = np.concatenate([[0], T[:-1, 0]])
    dt = T - prev[:, None]
    return struct.pack("<II", len(V), len(T)) + varint(zz(dv.ravel())) + varint(zz(dt.ravel()))


def glb(V, T):
    """A GLB of one mesh: POSITION as ushort with the node's scale and translation (KHR_mesh_quantization)."""
    lo, hi = V.min(0), V.max(0)
    scale = np.maximum((hi - lo) / 65535, 1e-6)
    scale[2] = max(scale[2], 0.01)  # (no finer than the source's cm)
    q = np.round((V - lo) / scale).astype("<u2")
    padded = np.zeros((len(q), 4), "<u2")  # (a vertex attribute starts on 4 bytes: ushort x, y, z and 2 B of padding)
    padded[:, :3] = q
    pos = padded.tobytes()
    idx = T.astype("<u2" if len(V) < 65536 else "<u4").tobytes()
    idx += b"\0" * (-len(idx) % 4)
    j = {"asset": {"version": "2.0"}, "extensionsUsed": ["KHR_mesh_quantization"], "extensionsRequired": ["KHR_mesh_quantization"],
         "scenes": [{"nodes": [0]}], "scene": 0,
         "nodes": [{"mesh": 0, "translation": lo.tolist(), "scale": scale.tolist()}],
         "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
         "buffers": [{"byteLength": len(pos) + len(idx)}],
         "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(pos), "byteStride": 8, "target": 34962},
                         {"buffer": 0, "byteOffset": len(pos), "byteLength": T.size * (2 if len(V) < 65536 else 4), "target": 34963}],
         "accessors": [{"bufferView": 0, "componentType": 5123, "count": len(V), "type": "VEC3",
                        "min": [int(v) for v in q.min(0)], "max": [int(v) for v in q.max(0)]},
                       {"bufferView": 1, "componentType": 5123 if len(V) < 65536 else 5125, "count": int(T.size), "type": "SCALAR"}]}
    js = json.dumps(j, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    body = pos + idx
    return struct.pack("<III", 0x46546C67, 2, 28 + len(js) + len(body)) + struct.pack("<I", len(js)) + b"JSON" + js + struct.pack("<I", len(body)) + b"BIN\0" + body, q * scale + lo


def sizes(b):
    import brotli
    return {"raw": len(b), "gzip": len(gzip.compress(b, 9)), "brotli": len(brotli.compress(b, quality=11))}


def browser():
    from playwright.sync_api import sync_playwright
    import secrets
    import tempfile
    identity = secrets.token_hex(8)
    with tempfile.TemporaryDirectory() as d:
        ready = os.path.join(d, "ready.json")
        srv = subprocess.Popen([sys.executable, "-I", os.path.join(ROOT, "tools", "serve.py"), "0", "--identity", identity, "--ready-file", ready],
                               cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            import time
            for _ in range(100):
                if os.path.exists(ready):
                    break
                time.sleep(0.1)
            with open(ready, encoding="utf-8") as f:
                port = json.load(f)["port"]
            with sync_playwright() as p:
                b = p.chromium.launch()
                page = b.new_page()
                page.goto(f"http://localhost:{port}/tools/bench/tile_container.html")
                r = page.evaluate(f"run({RUNS})")
                r["worker"] = page.evaluate(f"runWorker({RUNS})")
                b.close()
            return r
        finally:
            srv.kill()
            srv.wait()


def main():
    at = tm.arg("--at", "")
    p = tm.line["path"][len(tm.line["path"]) // 2]
    cx, cy = (float(v) for v in at.split(",")) if at else (p[0], p[1])
    Z, X, Y, _ = tm.tile(cx, cy, tm.SIZE)
    V, Tr = tm.m_delatin(Z, tm.distance(X, Y))
    V[:, 1] = -V[:, 1]  # (north up, as the world's y)
    V, T = order(V, Tr)
    d = delta(V, T)
    g, back = glb(V, T)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "tile.delta"), "wb") as f:
        f.write(d)
    with open(os.path.join(OUT, "tile.glb"), "wb") as f:
        f.write(g)
    err = np.abs(back - V)
    print(f"tile {tm.SIZE} m at ({cx:.0f}, {cy:.0f}): {len(T):,} triangles, {len(V):,} vertices")
    print(f"quantized positions, max error: x, y {100 * err[:, :2].max():.2f} cm, z {100 * err[:, 2].max():.2f} cm "
          f"(the differences: heights rounded to 1 cm, x, y on the source's cells)")
    res = {"delta": sizes(d), "glb": sizes(g), "triangles": len(T)}
    for k in ("delta", "glb"):
        print(f"{k:6s} " + "  ".join(f"{n} {v / 1024:,.0f} kB" for n, v in res[k].items()) + f"  ({res[k]['brotli'] / len(T):.2f} B/triangle brotli)")
    res["page"] = browser()
    print("page, median of", RUNS, "runs (ms, one tile, from a buffer in memory):", res["page"])
    with open(os.path.join(OUT, "result.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
