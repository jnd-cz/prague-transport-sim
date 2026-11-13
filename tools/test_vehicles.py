# SPDX-License-Identifier: AGPL-3.0-or-later
"""The vehicle registry's manifests (#455): assets/vehicles.json and each assets/<id>/vehicle.json.

    python -I tools/test_vehicles.py

Checks every manifest the index lists: the fields the game reads (src/vehicles.js), the files present with the sizes
it states, the licence (a redistributable SPDX id, its LICENSE.txt, authors, sources, a credit line), a row in
ASSETS.md for its files, its fleet (types, ranges, sets), and that src/ names none of its files or its credit (the
manifest is the one place). Docs: docs/vehicles.md, "The manifest". Exit code 1 on a failure.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
LOADERS = {"builtin", "gltf", "gltf-classic", "gltf-rigged"}
# licences that allow the files to be redistributed with the game (ASSETS.md); NC ones not in a commercial release
LICENCES = {"CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "CC-BY-NC-4.0", "CC-BY-NC-SA-4.0", "GPL-3.0", "GPL-3.0-only",
            "GPL-3.0-or-later", "AGPL-3.0-or-later", "MIT"}
MOVES = {"bogies", "wheels", "couplers", "collector", "lamps", "doors", "trackBrakes", "wipers", "mirror", "springs"}
MODEL_EXT = {".gltf", ".glb"}



def fleet_problems(fleet):
    """The fleet (#527, docs/vehicles.md): each type's ranges or list, exceptions inside their ranges, no number in two
    types, each set's numbers of one type and in no other set, liveries keyed by the fleet's numbers."""
    if fleet is None:
        return []
    bad = []

    def need(ok, why):
        if not ok:
            bad.append(why)

    types = fleet.get("types")
    need(isinstance(types, dict) and types, "fleet without types")
    if not isinstance(types, dict):
        return bad
    type_of = {}
    for name, t in types.items():
        numbers = []
        if "list" in t:
            need("ranges" not in t, f"fleet type {name}: both a list and ranges")
            ok = isinstance(t["list"], list) and t["list"] and all(isinstance(n, int) and n > 0 for n in t["list"])
            need(ok, f"fleet type {name}: list {t['list']!r} is not fleet numbers")
            numbers = t["list"] if ok else []
        else:
            rs = t.get("ranges")
            need(isinstance(rs, list) and rs, f"fleet type {name}: no ranges or list")
            for r in rs or []:
                ok = isinstance(r, list) and len(r) == 2 and all(isinstance(n, int) for n in r) and 0 < r[0] <= r[1]
                need(ok, f"fleet type {name}: range {r!r} is not [first, last]")
                if ok:
                    numbers += range(r[0], r[1] + 1)
            for n in t.get("except", []):
                need(n in numbers, f"fleet type {name}: except {n} is outside its ranges")
            numbers = [n for n in numbers if n not in set(t.get("except", []))]
        need(len(set(numbers)) == len(numbers), f"fleet type {name}: a number twice")
        for n in numbers:
            need(n not in type_of, f"fleet number {n} in types {type_of.get(n)} and {name}")
            type_of.setdefault(n, name)
    in_set = {}
    for st in fleet.get("sets", []):
        ok = isinstance(st, list) and len(st) >= 2 and all(isinstance(n, int) for n in st)
        need(ok, f"fleet set {st!r} is not two or more numbers")
        if not ok:
            continue
        for n in st:
            need(n in type_of, f"fleet set {st}: {n} is in none of the types")
            need(n not in in_set, f"fleet number {n} in sets {in_set.get(n)} and {st}")
            in_set.setdefault(n, st)
        need(len({type_of.get(n) for n in st}) == 1, f"fleet set {st}: numbers of different types")
    for n in fleet.get("liveries", {}):
        need(n.isdigit() and int(n) in type_of, f"fleet livery for {n}: not one of the fleet's numbers")
    return bad

def vehicle_types():
    """The types src/tram.js offers (VEHICLE_TYPES)."""
    s = open(os.path.join(ROOT, "src", "tram.js"), encoding="utf-8").read()
    m = re.search(r"export const VEHICLE_TYPES = \{([^}]*)\}", s)
    return {t.strip().split(":")[0].strip() for t in m.group(1).split(",") if t.strip()} if m else set()


def check(v, vid, types, assets_md, src):
    """The manifest's problems, as sentences."""
    bad = []
    need = lambda cond, msg: cond or bad.append(msg)  # noqa: E731
    need(v.get("schema") == 1, "schema is not 1")
    need(v.get("id") == vid, f"id {v.get('id')!r} is not its folder's {vid!r}")
    names = v.get("names") or {}
    need(all(isinstance(names.get(k), str) and names[k].strip() for k in ("cs", "en")), "names in cs and en")
    need(v.get("type") in types, f"type {v.get('type')!r} is none of src/tram.js VEHICLE_TYPES {sorted(types)}")
    loader = v.get("loader")
    need(loader in LOADERS, f"loader {loader!r} is none of {sorted(LOADERS)}")
    need(isinstance(v.get("preload"), bool), "preload is not true or false")
    files = v.get("files")
    need(isinstance(files, list), "files is not a list")
    files = files if isinstance(files, list) else []
    paths = [f.get("path") for f in files]
    for f in files:
        p = os.path.join(ASSETS, vid, f.get("path", ""))
        if not os.path.isfile(p):
            bad.append(f"file {f.get('path')} missing")
        elif os.path.getsize(p) != f.get("bytes"):
            bad.append(f"file {f['path']} is {os.path.getsize(p)} bytes, the manifest says {f.get('bytes')}")
    if loader == "builtin":
        need(not files, "a built-in vehicle has no files")
    else:
        need(v.get("model") in paths, f"model {v.get('model')!r} is not among its files")
        need(os.path.splitext(v.get("model") or "")[1].lower() in MODEL_EXT, "model is not .gltf or .glb")
    if loader == "gltf-rigged":
        need(v.get("rig") in paths, f"rig {v.get('rig')!r} is not among its files")
    if loader == "gltf":
        need(v.get("forward", "+Z") in {"+Z", "-Z", "+X", "-X"}, f"forward {v.get('forward')!r}")
    lic = v.get("licence") or {}
    spdx = lic.get("spdx")
    need(spdx in LICENCES, f"licence {spdx!r} is none of the redistributable ones {sorted(LICENCES)}")
    need(isinstance(lic.get("commercial"), bool), "licence.commercial is not true or false")
    if spdx and "-NC" in spdx:
        need(lic.get("commercial") is False, "a non-commercial licence with commercial true")
    need(bool(lic.get("authors")), "licence.authors empty")
    need(bool(lic.get("sources")), "licence.sources empty")
    if files:
        need(isinstance(lic.get("credit"), str) and lic["credit"].strip(), "files without a credit line")
        need(lic.get("file") and os.path.isfile(os.path.join(ASSETS, vid, lic["file"])), "no licence file (LICENSE.txt)")
        rows = [r for r in assets_md.splitlines() if r.startswith("|") and f"assets/{vid}/" in r]
        for p in paths:
            need(any(p in r for r in rows), f"file {p} has no row in ASSETS.md")
    need(v.get("tier") in (1, 2, 3), f"tier {v.get('tier')!r} is not 1, 2 or 3")
    moves = v.get("moves", [])
    need(set(moves) <= MOVES, f"moves {sorted(set(moves) - MOVES)} unknown (docs/vehicles.md, Tiers of movement)")
    need(isinstance(v.get("levels"), int) and v["levels"] >= 1, "levels is not a count")
    bad += fleet_problems(v.get("fleet"))
    # the manifest is the one place for its files and its credit (#455)
    for p in paths:
        need(p not in src, f"src/ names its file {p}")
    if lic.get("credit"):
        need(lic["credit"] not in src, "src/ repeats its credit line")
    return bad


def main():
    fails = []
    index = json.load(open(os.path.join(ASSETS, "vehicles.json"), encoding="utf-8"))
    ids = index.get("vehicles", [])
    if not ids:
        fails.append("assets/vehicles.json lists no vehicles")
    if len(set(ids)) != len(ids):
        fails.append("assets/vehicles.json lists a vehicle twice")
    on_disk = {d for d in os.listdir(ASSETS) if os.path.isfile(os.path.join(ASSETS, d, "vehicle.json"))}
    for d in sorted(on_disk - set(ids)):
        fails.append(f"assets/{d}/vehicle.json is not in assets/vehicles.json")
    types = vehicle_types()
    if not types:
        fails.append("src/tram.js has no VEHICLE_TYPES")
    assets_md = open(os.path.join(ROOT, "ASSETS.md"), encoding="utf-8").read()
    src = "\n".join(open(os.path.join(ROOT, "src", f), encoding="utf-8").read()
                    for f in sorted(os.listdir(os.path.join(ROOT, "src"))) if f.endswith(".js"))
    src += open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    for vid in ids:
        p = os.path.join(ASSETS, vid, "vehicle.json")
        if not os.path.isfile(p):
            fails.append(f"{vid}: assets/{vid}/vehicle.json missing")
            continue
        try:
            v = json.load(open(p, encoding="utf-8"))
        except ValueError as e:
            fails.append(f"{vid}: vehicle.json is not JSON: {e}")
            continue
        bad = check(v, vid, types, assets_md, src)
        fails += [f"{vid}: {b}" for b in bad]
        print(f"{vid}: {v.get('loader')}, tier {v.get('tier')}, {len(v.get('files', []))} files, "
              f"{v.get('licence', {}).get('spdx')}{'' if bad else ', ok'}")
    # the fleet check refuses what it should (each sample one fault, its sentence's start)
    good = {"types": {"T3": {"ranges": [[6400, 6410]], "except": [6405]}, "T3M": {"list": [8080, 8074]}},
            "sets": [[6401, 6402], [8080, 8074]], "liveries": {"6401": "wrap"}}
    samples = [
        (good, None),
        ({**good, "types": {**good["types"], "T3": {"ranges": [[6400, 6410]], "except": [6999]}}}, "fleet type T3: except"),
        ({**good, "types": {**good["types"], "X": {"ranges": [[6409, 6420]]}}}, "fleet number 6409 in types"),
        ({**good, "sets": [[6401, 8080]]}, "fleet set [6401, 8080]: numbers of different types"),
        ({**good, "sets": [[6401, 6402], [6402, 6403]]}, "fleet number 6402 in sets"),
        ({**good, "sets": [[6401, 7000]]}, "fleet set [6401, 7000]: 7000 is in none"),
        ({**good, "liveries": {"7000": "wrap"}}, "fleet livery for 7000"),
        ({**good, "types": {"T3": {"ranges": [[6410, 6400]]}}}, "fleet type T3: range"),
    ]
    for fleet, want in samples:
        got = fleet_problems(fleet)
        if want is None and got or want is not None and not any(g.startswith(want) for g in got):
            fails.append(f"fleet check on a sample: wanted {want or 'no problem'}, got {got}")
    for f in fails:
        print("FAIL", f)
    print(f"{len(ids)} vehicles, {len(samples)} fleet samples, {len(fails)} failures")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
