# SPDX-License-Identifier: AGPL-3.0-or-later
"""The street vehicles' models (#250): assets/cars/ against src/carTypes.js.

    python -I tools/test_cartypes.py

For every type CAR_TYPES lists: its near and far GLB present with the size and SHA-256 assets/cars/LICENSE.txt
states and a row in ASSETS.md; the near model's sizes as the table gives them (length, width over the tyres,
over the mirrors, height, wheelbase, track, wheel radius; within 3 mm), standing on the ground, centred between
its axles; its steering (steer_FL/FR at the front wheels' centres with the wheels under them, each wheel's
geometry centred on its node, so a yaw turns it about its own vertical axis and a turn about Z rolls it); its lamps
in their places (headlamps at the front and brake lamps at the rear on both sides; each side's indicator at the front,
on the wing and at the rear, the left on -Z); the plates at the front and rear; at most 14 primitives. The far
model: one primitive, within 3 cm of the near one's length and height. Without a browser: the GLBs are read here.
Exit code 1 on a failure.
"""
import hashlib
import json
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARS = os.path.join(ROOT, "assets", "cars")
TOL = 0.003
LAMPS = ("headlamp", "brake", "indicator_left", "indicator_right", "plate_text")
MATERIALS = {"paint", "glass", "trim", *LAMPS, "wheel_vertex"}
WHEELS = ("FL", "FR", "RL", "RR")


def car_types(path=os.path.join(ROOT, "src", "carTypes.js")):
    """CAR_TYPES as written in src/carTypes.js: one { key: value, ... } line per type."""
    src = open(path, encoding="utf-8").read()
    body = re.search(r"export const CAR_TYPES = \[(.*?)\n\];", src, re.S).group(1)
    out = []
    for line in re.findall(r"\{([^}]*)\}", body):
        t = {}
        for k, v in re.findall(r"(\w+): ('[^']*'|[-\d.]+)", line):
            t[k] = v.strip("'") if v.startswith("'") else float(v)
        out.append(t)
    return out


def listed(path=os.path.join(CARS, "LICENSE.txt")):
    """file name -> (bytes, sha256) as the licence file lists them"""
    out = {}
    for name, size, sha in re.findall(r"^(\S+\.glb)\s+([\d,]+) B\s+sha256 ([0-9a-f]{64})", open(path, encoding="utf-8").read(), re.M):
        out[name] = (int(size.replace(",", "")), sha)
    return out


def read_glb(path):
    b = open(path, "rb").read()
    magic, version, _ = struct.unpack_from("<III", b, 0)
    if magic != 0x46546C67 or version != 2:
        raise ValueError("not a glTF 2.0 binary")
    n, kind = struct.unpack_from("<II", b, 12)
    j = json.loads(b[20:20 + n])
    off = 20 + n
    bn, = struct.unpack_from("<I", b, off)
    return j, b[off + 8:off + 8 + bn]


def mat4(node):
    if "matrix" in node:
        m = node["matrix"]
        return [[m[c * 4 + r] for c in range(4)] for r in range(4)]
    t, (x, y, z, w), s = node.get("translation", [0, 0, 0]), node.get("rotation", [0, 0, 0, 1]), node.get("scale", [1, 1, 1])
    r = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    return [[r[i][0] * s[0], r[i][1] * s[1], r[i][2] * s[2], t[i]] for i in range(3)] + [[0, 0, 0, 1]]


def mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def apply(m, v):
    return [m[i][0] * v[0] + m[i][1] * v[1] + m[i][2] * v[2] + m[i][3] for i in range(3)]


class Model:
    """a GLB's nodes in the model's frame: each node's world matrix, and every primitive's points and material"""

    def __init__(self, path):
        self.j, self.bin = read_glb(path)
        nodes = self.j["nodes"]
        self.parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}
        self.world = {}
        self.names = {n.get("name"): i for i, n in enumerate(nodes)}
        mats = [m.get("name") for m in self.j.get("materials", [])]
        self.prims = []  # (node, material, points)
        for i, n in enumerate(nodes):
            if "mesh" not in n:
                continue
            for p in self.j["meshes"][n["mesh"]]["primitives"]:
                pts = [apply(self.W(i), v) for v in self.points(p["attributes"]["POSITION"])]
                self.prims.append((i, mats[p["material"]] if "material" in p else None, pts))

    def W(self, i):
        if i not in self.world:
            m = mat4(self.j["nodes"][i])
            self.world[i] = mul(self.W(self.parent[i]), m) if i in self.parent else m
        return self.world[i]

    def points(self, k):
        a = self.j["accessors"][k]
        v = self.j["bufferViews"][a["bufferView"]]
        start, stride = v.get("byteOffset", 0) + a.get("byteOffset", 0), v.get("byteStride", 12)
        return [struct.unpack_from("<3f", self.bin, start + i * stride) for i in range(a["count"])]

    def under(self, i):
        """the points of a node and everything under it"""
        out = []
        for k, _, pts in self.prims:
            j = k
            while j != i and j in self.parent:
                j = self.parent[j]
            if j == i:
                out += pts
        return out

    def material(self, name):
        return [q for _, m, pts in self.prims if m == name for q in pts]

    def all(self):
        return [q for _, _, pts in self.prims for q in pts]


def box(pts):
    return [min(q[a] for q in pts) for a in range(3)], [max(q[a] for q in pts) for a in range(3)]


def groups(pts, gap=0.25):
    """a material's points in separate places (a lamp each): [(lo, hi)]"""
    out = []
    for p in sorted(pts):
        for g in out:
            if any(all(abs(p[a] - q[a]) < gap for a in range(3)) for q in g[-40:]):
                g.append(p)
                break
        else:
            out.append([p])
    # (a lamp's two ends may be further apart than the gap: join groups whose boxes touch)
    boxes = [box(g) for g in out]
    merged = True
    while merged:
        merged = False
        for a in range(len(boxes)):
            for b in range(a + 1, len(boxes)):
                (la, ha), (lb, hb) = boxes[a], boxes[b]
                if all(la[k] - gap <= hb[k] and lb[k] - gap <= ha[k] for k in range(3)):
                    boxes[a] = ([min(la[k], lb[k]) for k in range(3)], [max(ha[k], hb[k]) for k in range(3)])
                    del boxes[b]
                    merged = True
                    break
            if merged:
                break
    return boxes


def place(lo, hi, length):
    """'front' / 'side' / 'rear' and 'left' (-Z) / 'right' (+Z) / 'middle' of a lamp's box"""
    x, z = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
    along = "front" if x > length / 2 - 0.6 else "rear" if x < -length / 2 + 0.6 else "side"
    return along, "right" if z > 0.15 else "left" if z < -0.15 else "middle"


def check_near(t, m, need):
    pts = m.all()
    (x0, y0, z0), (x1, y1, z1) = box(pts)
    low = [q for q in pts if q[1] < 0.9]  # (below the mirrors)
    sizes = {"length": x1 - x0, "mirrors": z1 - z0, "height": y1 - y0, "width": 2 * max(abs(q[2]) for q in low)}
    for k, v in sizes.items():
        need(abs(v - t[k]) <= TOL, f"{k} {v:.3f} m, the table {t[k]}")
    need(abs(y0) <= TOL, f"the lowest point {y0:.3f} m, not on the ground")
    # (the origin is midway between the axles, checked below; the body around it within 1 cm: the box truck's 4 mm forward)
    need(abs(x0 + x1) / 2 <= 0.01, f"the body not around the origin: {x0:.3f} .. {x1:.3f}")
    mats = {mt for _, mt, _ in m.prims}
    need(MATERIALS <= mats, f"materials missing: {sorted(MATERIALS - mats)}")
    need(len(m.prims) <= 14, f"{len(m.prims)} primitives")
    # the wheels: under their steer nodes, the front ones steered about their centres
    centre = {}
    for w in WHEELS:
        wi, si = m.names.get(f"wheel_{w}"), m.names.get(f"steer_{w}")
        if wi is None or si is None:
            need(False, f"wheel_{w} or steer_{w} missing")
            continue
        need(m.parent.get(wi) == si, f"wheel_{w} not under steer_{w}")
        o, so = apply(m.W(wi), [0, 0, 0]), apply(m.W(si), [0, 0, 0])
        need(all(abs(o[a] - so[a]) <= 1e-4 for a in range(3)), f"steer_{w} not at wheel_{w}'s centre")
        lo, hi = box(m.under(wi))
        c = [(lo[a] + hi[a]) / 2 for a in range(3)]
        need(all(abs(c[a] - o[a]) <= TOL for a in range(3)), f"wheel_{w}'s geometry not centred on its node")
        need(abs((hi[1] - lo[1]) / 2 - t["wheelRadius"]) <= TOL and abs(o[1] - t["wheelRadius"]) <= TOL,
             f"wheel_{w}: radius {(hi[1] - lo[1]) / 2:.3f}, centre {o[1]:.3f} m high, the table {t['wheelRadius']}")
        centre[w] = o
    if len(centre) == 4:
        need(abs(centre["FL"][0] - centre["RL"][0] - t["wheelbase"]) <= TOL, f"wheelbase {centre['FL'][0] - centre['RL'][0]:.3f}")
        need(abs(centre["FR"][2] - centre["FL"][2] - t["track"]) <= TOL, f"track {centre['FR'][2] - centre['FL'][2]:.3f}")
        need(centre["FL"][0] > 0 and centre["FL"][2] < 0, "wheel_FL not at the front left (+X, -Z)")
        need(abs(centre["FL"][0] + centre["RL"][0]) <= TOL, "not centred between the axles")
    # the lamps in their places
    length = x1 - x0
    want = {"headlamp": {("front", "left"), ("front", "right")}, "brake": {("rear", "left"), ("rear", "right")},
            "indicator_left": {("front", "left"), ("side", "left"), ("rear", "left")},
            "indicator_right": {("front", "right"), ("side", "right"), ("rear", "right")},
            "plate_text": {("front", "middle"), ("rear", "middle")}}
    for mt, places in want.items():
        got = {place(lo, hi, length) for lo, hi in groups(m.material(mt), 0.5 if mt == "plate_text" else 0.25)}
        need(got == places, f"{mt} at {sorted(got)}, wanted {sorted(places)}")
    return sizes


def main():
    fails = []
    types = car_types()
    files = listed()
    rows = [r for r in open(os.path.join(ROOT, "ASSETS.md"), encoding="utf-8").read().splitlines() if r.startswith("|")]
    stats = []
    if not types:
        fails.append("src/carTypes.js: no CAR_TYPES")
    for t in types:
        def need(ok, what, t=t):
            if not ok:
                fails.append(f"{t['id']}: {what}")
        need(t["weight"] > 0, "no weight")
        near = None
        for level in ("near", "far"):
            name = f"{t['id']}-{level}.glb"
            path = os.path.join(CARS, name)
            if not os.path.exists(path):
                need(False, f"{name} missing")
                continue
            data = open(path, "rb").read()
            need(name in files, f"{name} not in assets/cars/LICENSE.txt")
            if name in files:
                need(files[name] == (len(data), hashlib.sha256(data).hexdigest()), f"{name}: size or SHA-256 not as LICENSE.txt lists")
            need(any(f"assets/cars/{name}" in r or "assets/cars/" in r and "<type>" in r for r in rows), f"{name} has no row in ASSETS.md")
            m = Model(path)
            tris = sum(m.j["accessors"][p["indices"]]["count"] // 3 for mesh in m.j["meshes"] for p in mesh["primitives"])
            stats.append((name, len(m.prims), tris))
            if level == "near":
                near = check_near(t, m, need)
            else:
                (x0, y0, _), (x1, y1, _) = box(m.all())
                need(len(m.prims) == 1, f"far: {len(m.prims)} primitives")
                if near:
                    need(abs(x1 - x0 - near["length"]) <= 0.03 and abs(y1 - y0 - near["height"]) <= 0.03,
                         f"far: {x1 - x0:.3f} long, {y1 - y0:.3f} high, the near {near['length']:.3f}, {near['height']:.3f}")
    extra = {n for n in os.listdir(CARS) if n.endswith(".glb")} - {f"{t['id']}-{lv}.glb" for t in types for lv in ("near", "far")}
    if extra:
        fails.append(f"assets/cars: files no type names: {sorted(extra)}")
    # the sample lamp check finds a lamp out of place
    if not fails:
        m = Model(os.path.join(CARS, f"{types[0]['id']}-near.glb"))
        moved = [(i, mt, [[-q[0], q[1], q[2]] if mt == "headlamp" else q for q in pts]) for i, mt, pts in m.prims]
        m.prims = moved
        sample = []
        check_near(types[0], m, lambda ok, what: ok or sample.append(what))
        if not any(s.startswith("headlamp at") for s in sample):
            fails.append(f"the lamp check missed headlamps moved to the rear: {sample}")
    for name, prims, tris in stats:
        print(f"  {name:16} {prims:2} primitives {tris:5} triangles")
    for f in fails:
        print("FAIL", f)
    print(f"{len(types)} car types, {len(stats)} models, {len(fails)} failures")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
