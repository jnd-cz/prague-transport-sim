# SPDX-License-Identifier: AGPL-3.0-or-later
"""Export the hybrid T3 rig from a GLB, its base rig and explicit part roles (#471).

    python -I tools/export_t3h_rig.py --out reports/t3h-rig.json

Use --model, --base-rig and --roles to check a different export. The base rig supplies the
original pivots and plate bindings. Review the role assignments and lamp coordinates in
t3h_rig_roles.json when the model changes. Coordinates use the GLB's frame and metres.
"""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic import replacing  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "assets/t3h"
ROLES = ROOT / "tools/t3h_rig_roles.json"


def read_glb(path):
    with path.open("rb") as f:
        header = f.read(20)
        if len(header) != 20:
            raise ValueError("truncated GLB header")
        magic, version, length, size, chunk = struct.unpack("<4sIII4s", header)
        if (magic, version, chunk) != (b"glTF", 2, b"JSON"):
            raise ValueError("expected a GLB v2 with a JSON chunk")
        if length != path.stat().st_size or size % 4 or size > length - 20:
            raise ValueError("invalid GLB length or JSON chunk size")
        return json.loads(f.read(size))


def vector(value, label, positive=False):
    if len(value) != 3 or any(
        type(v) not in (int, float) or not math.isfinite(v) or (positive and v <= 0)
        for v in value
    ):
        raise ValueError(f"{label}: expected three finite {'positive ' if positive else ''}coordinates")


def export_rig(glb, rig, roles):
    """Fill the asset-specific roles and validate them against the exported scene."""
    nodes = glb["nodes"]
    names = defaultdict(list)
    clips = defaultdict(list)
    for i, node in enumerate(nodes):
        names[node.get("name")].append(i)
    for clip in glb["animations"]:
        clips[clip.get("name")].append(clip)

    def descendants(indices):
        pending, visited = list(indices), set()
        while pending:
            i = pending.pop()
            if not 0 <= i < len(nodes):
                raise ValueError(f"invalid GLB node index {i}")
            if i not in visited:
                visited.add(i)
                pending.extend(nodes[i].get("children", []))
        return visited

    def node(name, role, scope, mesh=False):
        matches = names.get(name, [])
        if len(matches) != 1 or matches[0] not in scope:
            raise ValueError(f"{role}: expected one node named {name!r} in its assigned group")
        i = matches[0]
        if mesh and "mesh" not in nodes[i]:
            raise ValueError(f"{role}: {name!r} has no mesh")
        return i

    def animation(name, role, expected):
        matches = clips.get(name, [])
        if len(matches) != 1:
            raise ValueError(f"{role}: expected one clip named {name!r}")
        targets = {c["target"].get("node") for c in matches[0]["channels"]}
        if targets != expected:
            raise ValueError(f"{role}: clip {name!r} targets the wrong nodes")

    scene = glb["scenes"][glb.get("scene", 0)]
    root = node(rig["root"], "tram root", descendants(scene["nodes"]))
    scope = descendants([root])
    node(rig["body"], "body", scope)
    if rig["forward"] != roles["forward"] or rig["up"] != roles["up"]:
        raise ValueError("role coordinates and the base rig must use the same axes")
    if not rig["doors"] or len(rig["bogies"]) != 2 or not rig["wheels"]:
        raise ValueError("the hybrid needs doors, two bogies and wheels")
    door_clips = roles["doorClips"]
    if set(door_clips) != {d["name"] for d in rig["doors"]} or len(door_clips) != len(rig["doors"]):
        raise ValueError("doorClips must assign one clip to each named door")
    doors = []
    for door in rig["doors"]:
        name = door["name"]
        leaves = {node(leaf[part], f"door {name}", scope) for leaf in door["leaves"]
                  for part in ("outer", "inner")}
        if not leaves:
            raise ValueError(f"door {name}: no leaves")
        animation(door_clips[name], f"door {name}", leaves)
        doors.append({**door, "clip": door_clips[name]})

    panto = {**rig["pantograph"], "clip": roles["pantographClip"]}
    collector = descendants([node(panto["root"], "collector", scope)])
    linkage = [arm[key] for arm in panto["linkages"] for key in ("lower", "upper")]
    targets = {node(name, "collector", collector) for name in [panto["head"], *linkage]}
    animation(panto["clip"], "collector", targets)
    if not panto["maxContactHeight"] > panto["minContactHeight"]:
        raise ValueError("collector: invalid contact range")

    shoes = roles["shoes"]
    bogies = {b["name"]: descendants([node(b["name"], "bogie", scope)]) for b in rig["bogies"]}
    if set(shoes) != set(bogies):
        raise ValueError("shoes must be assigned to both bogies")
    for wheel in rig["wheels"]:
        node(wheel["name"], "wheel", set().union(*bogies.values()))
    for bogie, group in bogies.items():
        if not shoes[bogie]:
            raise ValueError(f"{bogie}: no track-brake shoes")
        for name in shoes[bogie]:
            node(name, f"shoe under {bogie}", group, mesh=True)
    couplers = roles["couplers"]
    if set(couplers) != {"front", "rear"} or not all(couplers.values()):
        raise ValueError("couplers must name front and rear meshes")
    for end, parts in couplers.items():
        for name in parts:
            node(name, f"{end} coupler", scope, mesh=True)
    bound_meshes = [n for group in [*shoes.values(), *couplers.values()] for n in group]
    if len(set(bound_meshes)) != len(bound_meshes):
        raise ValueError("each shoe and coupler mesh needs a single assignment")

    info = rig["infoPlates"]
    lamps = [*rig["signals"]["left"], *rig["signals"]["right"], *rig["brakes"]]
    if not all(rig["signals"].get(side) for side in ("left", "right")):
        raise ValueError("indicators must be named on both sides")
    plates = [*rig["numberPlates"], *rig["routePlates"], *rig["routeStyles"],
              info["frontDestination"], info["runNumber"], *info["sideBoards"]]
    for name in [*lamps, *plates]:
        node(name, "lamp or plate", scope, mesh=True)

    saloon = roles["saloon"]
    materials = {m.get("name") for m in glb["materials"]}
    missing = set(saloon["materials"]) - materials
    if missing:
        raise ValueError(f"saloon: missing materials {', '.join(sorted(missing))}")
    lo, hi = saloon["within"]
    vector(lo, "saloon minimum")
    vector(hi, "saloon maximum")
    if any(a >= b for a, b in zip(lo, hi)):
        raise ValueError("saloon: empty bounds")
    for role, points in (("beams", roles["beams"]), ("tail lamps", roles["tailLamps"]["at"])):
        if len(points) != 2:
            raise ValueError(f"{role}: expected two centres")
        for point in points:
            vector(point, role)
    vector(roles["tailLamps"]["size"], "tail lamp size", positive=True)
    digits = roles["fleetDigits"]
    if type(digits) not in (int, float) or not math.isfinite(digits) or digits <= 0:
        raise ValueError("fleetDigits must be a positive height in metres")

    result = {**rig, "doors": doors, "pantograph": panto}
    result.update({key: roles[key] for key in (
        "revision", "saloon", "shoes", "couplers", "beams", "tailLamps", "fleetDigits"
    )})
    result.pop("handWritten", None)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", type=Path, default=ASSET / "tatra-t3-hybrid-nc.glb")
    parser.add_argument("--base-rig", type=Path, default=ASSET / "rig.json")
    parser.add_argument("--roles", type=Path, default=ROLES)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        inputs = (args.model, args.base_rig, args.roles)
        if any(args.out.resolve() == path.resolve() for path in inputs):
            raise ValueError("--out must differ from the input files")
        result = export_rig(read_glb(args.model), json.loads(args.base_rig.read_bytes()),
                            json.loads(args.roles.read_bytes()))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with replacing(args.out, "w", encoding="utf-8", newline="\n") as f:
            json.dump(result, f, ensure_ascii=True, allow_nan=False, indent=2)
            f.write("\n")
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        parser.exit(1, f"export_t3h_rig: {exc}\n")
    print(f"{args.out}: revision {result['revision']}, {len(result['doors'])} doors, "
          f"{sum(map(len, result['shoes'].values()))} shoes")


if __name__ == "__main__":
    main()
