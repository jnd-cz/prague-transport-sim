# SPDX-License-Identifier: AGPL-3.0-or-later
"""Name the hybrid T3's parts in its GLB, so its rig names them instead of placing them by coordinates (#525).

    python -I tools/edit_t3h_glb.py [--model assets/t3h/tatra-t3-hybrid-nc.glb] [--out PATH] [--check]

Rewrites the JSON chunk and appends to the binary buffer; nothing already in the file moves:
- the track-brake shoes and the coupler bars get names (`Track_Brake_Shoe_Front_Left`, `Coupler_Front`, ...);
- two empty nodes, `Headlight_Left` and `Headlight_Right`, mark the headlights' centres;
- the tail lamps the model lacked (the user, 2026-11-10, #436: on the rear panel 0.47 m either side) become lamp groups
  `Tail_left` and `Tail_right`, each a lens and a glow as the brake lamps (their materials);
- the saloon's parts, as the loader picked them by material and box until now, go under one `Saloon` node: those in the
  body; the box also caught the brake lamps' lenses and the side cards' backs, outside it, which stay where they are.
The places and the old names are this file's tables, read once: after the edit the model carries them. A model already
edited is left as it is (`--check` says whether it is). Left is the car's left (-Z with +X forward and +Y up).
"""
import argparse
import json
import math
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic import replacing  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "assets/t3h/tatra-t3-hybrid-nc.glb"
BASE_RIG = ROOT / "tools/t3h_base_rig.json"

RENAME = {  # the asset's generic mesh names (rig roles of #467/#471) -> the part's
    "Black_Metal_116": "Track_Brake_Shoe_Rear_Right", "Black_Metal_117": "Track_Brake_Shoe_Rear_Left",
    "Black_Metal_123": "Track_Brake_Shoe_Front_Right", "Black_Metal_124": "Track_Brake_Shoe_Front_Left",
    "Black_Metal_109": "Coupler_Front", "Black_Metal_111": "Coupler_Rear",
}
HEADLIGHTS = {"Headlight_Left": [7.0624, 1.2191, -0.4919], "Headlight_Right": [7.0624, 1.2191, 0.4857]}
TAILS = {"Tail_left": [-7.0204, 0.995, -0.47], "Tail_right": [-7.0204, 0.995, 0.47]}
TAIL_SIZE = [0.02, 0.07, 0.2]  # m along, up, across: the box the loader drew (#436)
GLOW_DEPTH = 0.002              # m: the glow is the lamp's outer face, the lens behind it
LENS, GLOW = "Rear_Brake_Red_Lens", "Rear_Brake_Red_Emission"
SALOON = {  # the loader's rule until #525 (src/rigged.js): these materials, or a part inside this box, in the car's frame
    "materials": ["Handles", "Control_Panel", "Red_Seat", "Blue_Seat", "Leather", "Material", "Inner_Plastic_Glass",
                  "Interior_Walls", "White_Ceiling"],
    "within": [[-6.95, 0.84, -1.25], [6.95, 3.1, 1.25]],
}
NOTE = ("Named the track-brake shoes and coupler bars; added headlight centre nodes and red tail lamps (a lens and "
        "a glow each) on the rear panel; grouped the saloon's parts under one Saloon node (#525).")


def read(path):
    data = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", data)
    if (magic, version) != (b"glTF", 2) or length != len(data):
        raise ValueError(f"{path}: not a GLB v2")
    size, kind = struct.unpack_from("<I4s", data, 12)
    if kind != b"JSON":
        raise ValueError(f"{path}: no JSON chunk first")
    glb = json.loads(data[20:20 + size])
    at = 20 + size
    bsize, bkind = struct.unpack_from("<I4s", data, at)
    if bkind != b"BIN\0":
        raise ValueError(f"{path}: no binary chunk")
    return glb, bytearray(data[at + 8:at + 8 + bsize])


def write(path, glb, bin_):
    js = json.dumps(glb, ensure_ascii=False, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    bin_ = bytes(bin_) + b"\0" * (-len(bin_) % 4)
    total = 12 + 8 + len(js) + 8 + len(bin_)
    with replacing(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, total))
        f.write(struct.pack("<I4s", len(js), b"JSON") + js)
        f.write(struct.pack("<I4s", len(bin_), b"BIN\0") + bin_)


def matrix(node):
    """The node's local transform as a column-major 4x4 (glTF's order)."""
    if "matrix" in node:
        return list(node["matrix"])
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    sx, sy, sz = node.get("scale", [1, 1, 1])
    tx, ty, tz = node.get("translation", [0, 0, 0])
    r = [1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w),
         2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w),
         2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y)]
    return [r[0] * sx, r[1] * sx, r[2] * sx, 0, r[3] * sy, r[4] * sy, r[5] * sy, 0,
            r[6] * sz, r[7] * sz, r[8] * sz, 0, tx, ty, tz, 1]


def mul(a, b):
    return [sum(a[k * 4 + i] * b[j * 4 + k] for k in range(4)) for j in range(4) for i in range(4)]


IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def box(glb, mesh, m):
    """A mesh's box in the frame m maps it to (three's Box3.applyMatrix4: its corners)."""
    lo, hi = [math.inf] * 3, [-math.inf] * 3
    for p in glb["meshes"][mesh]["primitives"]:
        a = glb["accessors"][p["attributes"]["POSITION"]]
        for c in range(8):
            q = [(a["max"] if c >> i & 1 else a["min"])[i] for i in range(3)]
            w = [m[i] * q[0] + m[4 + i] * q[1] + m[8 + i] * q[2] + m[12 + i] for i in range(3)]
            lo, hi = [min(u, v) for u, v in zip(lo, w)], [max(u, v) for u, v in zip(hi, w)]
    return lo, hi


def edited(glb):
    return any(n.get("name") == "Saloon" for n in glb["nodes"])


def add_box(glb, bin_, name, lo, hi, material):
    """A box mesh (24 vertices with their faces' normals, 36 indices) appended to the buffer; its index."""
    pos, nrm, idx = [], [], []
    for axis in range(3):
        for side in (0, 1):
            n = [0.0, 0.0, 0.0]
            n[axis] = 1.0 if side else -1.0
            u, v = (axis + 1) % 3, (axis + 2) % 3
            base = len(pos)
            for a, b in ((0, 0), (1, 0), (1, 1), (0, 1)):
                p = [0.0, 0.0, 0.0]
                p[axis] = hi[axis] if side else lo[axis]
                p[u] = hi[u] if a else lo[u]
                p[v] = hi[v] if b else lo[v]
                pos.append(p)
                nrm.append(n)
            # (counter-clockwise seen from outside)
            quad = [0, 1, 2, 0, 2, 3] if side else [0, 2, 1, 0, 3, 2]
            idx += [base + i for i in quad]
    views = glb["bufferViews"]

    def put(raw, target, count, kind, ctype, extra=None):
        bin_.extend(b"\0" * (-len(bin_) % 4))
        views.append({"buffer": 0, "byteOffset": len(bin_), "byteLength": len(raw), "target": target})
        bin_.extend(raw)
        glb["accessors"].append({"bufferView": len(views) - 1, "componentType": ctype, "count": count, "type": kind,
                                 **(extra or {})})
        return len(glb["accessors"]) - 1

    flat = [c for p in pos for c in p]
    p = put(struct.pack(f"<{len(flat)}f", *flat), 34962, len(pos), "VEC3", 5126,
            {"min": [min(q[i] for q in pos) for i in range(3)], "max": [max(q[i] for q in pos) for i in range(3)]})
    flat = [c for q in nrm for c in q]
    n = put(struct.pack(f"<{len(flat)}f", *flat), 34962, len(nrm), "VEC3", 5126)
    i = put(struct.pack(f"<{len(idx)}H", *idx), 34963, len(idx), "SCALAR", 5123)
    glb["meshes"].append({"name": name, "primitives": [
        {"attributes": {"POSITION": p, "NORMAL": n}, "indices": i, "material": material}]})
    return len(glb["meshes"]) - 1


def saloon_parts(glb, base):
    """The mesh nodes the loader merged into the saloon: in the car's frame (no moving part above them), neither an
    invisible helper, nor textured, nor glass, nor a card, a shoe or a coupler; of a saloon material or inside its box."""
    nodes, mats = glb["nodes"], glb["materials"]
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}
    names = {n.get("name"): i for i, n in enumerate(nodes)}
    p = base["pantograph"]
    movers = {*(x for d in base["doors"] for leaf in d["leaves"] for x in (leaf["outer"], leaf["inner"])),
              *(b["name"] for b in base["bogies"]), *(w["name"] for w in base["wheels"]),
              p["root"], p["head"], *(x for arm in p["linkages"] for x in (arm["lower"], arm["upper"])),
              *base["signals"]["left"], *base["signals"]["right"], *base["brakes"]}
    info = base["infoPlates"]
    cards = {*base["numberPlates"], *base["routeStyles"], info["frontDestination"], info["runNumber"], *info["sideBoards"]}
    root = names[base["root"]]
    lo, hi = SALOON["within"]
    out = []
    for i, node in enumerate(nodes):
        if "mesh" not in node or node.get("name") in movers:
            continue
        chain, q = [], i
        while q in parent:
            q = parent[q]
            chain.append(q)
        if root not in chain or any(nodes[q].get("name") in movers for q in chain[:chain.index(root)]):
            continue
        name = node.get("name", "")
        if name in cards or name.startswith((info["frontDestination"], info["runNumber"])) or name in RENAME:
            continue
        m = IDENTITY
        for q in reversed(chain[:chain.index(root)]):  # (the car's frame: the root's own transform left out)
            m = mul(m, matrix(nodes[q]))
        m = mul(m, matrix(node))
        prims = glb["meshes"][node["mesh"]]["primitives"]
        verdicts = set()
        for prim in prims:
            mat = mats[prim["material"]] if "material" in prim else {}
            pbr = mat.get("pbrMetallicRoughness", {})
            if pbr.get("baseColorFactor", [1, 1, 1, 1])[3] == 0 or mat.get("alphaMode") == "BLEND":
                verdicts.add(False)
                continue
            if "baseColorTexture" in pbr or "normalTexture" in mat or "emissiveTexture" in mat or any(mat.get("emissiveFactor", [0, 0, 0])):
                verdicts.add(False)
                continue
            a, b = box(glb, node["mesh"], m)
            inside = all(lo[k] <= a[k] and b[k] <= hi[k] for k in range(3))
            verdicts.add(mat.get("name") in SALOON["materials"] or inside)
        if len(verdicts) > 1:
            raise ValueError(f"{name}: its primitives are partly saloon, partly not")
        if verdicts == {True}:
            out.append(i)
    return out


def edit(glb, bin_, base):
    nodes = glb["nodes"]
    names = {}
    for i, n in enumerate(nodes):
        names.setdefault(n.get("name"), []).append(i)
    taken = [x for x in [*RENAME.values(), *HEADLIGHTS, *TAILS, "Saloon"] if x in names]
    if taken:
        raise ValueError(f"names already in the model: {', '.join(taken)}")
    for old, new in RENAME.items():
        if len(names.get(old, [])) != 1:
            raise ValueError(f"expected one node named {old!r}")
        node = nodes[names[old][0]]
        node["name"] = new
        glb["meshes"][node["mesh"]]["name"] = new
    root = names[base["root"]][0]
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}
    if any(k in nodes[root] for k in ("matrix", "translation", "rotation", "scale")):
        raise ValueError("the root has a transform: the places are in its frame")
    # the saloon: its parts under one node, where their parents left them (each parent's frame is the car's)
    # (the old rule's box also caught the brake lamps' lenses and the side cards' backs, outside the body: they stay)
    body = names[base["body"]][0]
    if any(k in nodes[body] for k in ("matrix", "translation", "rotation", "scale")):
        raise ValueError("the body has a transform: the places are in its frame")
    caught = saloon_parts(glb, base)
    parts = [i for i in caught if parent[i] == body]
    left = sorted(nodes[i].get("name") for i in caught if parent[i] != body)
    if not parts:
        raise ValueError("no saloon parts found")
    saloon = len(nodes)
    nodes.append({"name": "Saloon", "children": parts})
    for i in parts:
        nodes[parent[i]]["children"].remove(i)
    nodes[body]["children"].append(saloon)
    # the headlights' centres
    for name, at in HEADLIGHTS.items():
        nodes.append({"name": name, "translation": at})
        nodes[body]["children"].append(len(nodes) - 1)
    # the tail lamps: the outer face lit, the lens behind it (rear: -X is outwards)
    mat = {m.get("name"): i for i, m in enumerate(glb["materials"])}
    sx, sy, sz = [s / 2 for s in TAIL_SIZE]
    lens = add_box(glb, bin_, "Tail_Lens", [-sx + GLOW_DEPTH, -sy, -sz], [sx, sy, sz], mat[LENS])
    glow = add_box(glb, bin_, "Tail_Glow", [-sx, -sy, -sz], [-sx + GLOW_DEPTH, sy, sz], mat[GLOW])
    for name, at in TAILS.items():
        k = len(nodes)
        nodes.append({"name": name, "translation": at, "children": [k + 1, k + 2]})
        nodes.append({"name": f"{name}_Lens", "mesh": lens})
        nodes.append({"name": f"{name}_Glow", "mesh": glow})
        nodes[root]["children"].append(k)
    glb["buffers"][0]["byteLength"] = len(bin_)
    extras = glb.setdefault("asset", {}).setdefault("extras", {})
    extras["modifications"] = f"{extras.get('modifications', '')}; {NOTE}".lstrip("; ")
    return {"renamed": len(RENAME), "saloon": len(parts), "left": left, "headlights": len(HEADLIGHTS), "tails": len(TAILS)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", type=Path, default=MODEL)
    ap.add_argument("--base-rig", type=Path, default=BASE_RIG)
    ap.add_argument("--out", type=Path, help="where to write (default: over --model)")
    ap.add_argument("--check", action="store_true", help="only say whether the model is edited")
    a = ap.parse_args(argv)
    try:
        glb, bin_ = read(a.model)
        if edited(glb):
            print(f"{a.model}: already edited")
            return 0
        if a.check:
            print(f"{a.model}: not edited")
            return 1
        done = edit(glb, bin_, json.loads(a.base_rig.read_bytes()))
        write(a.out or a.model, glb, bin_)
    except (OSError, ValueError, KeyError, IndexError, struct.error) as exc:
        ap.exit(1, f"edit_t3h_glb: {exc}\n")
    print(f"{a.out or a.model}: {done['renamed']} parts named, {done['saloon']} saloon parts grouped, "
          f"{done['headlights']} headlights, {done['tails']} tail lamps; outside the body, not saloon: {', '.join(done['left'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
