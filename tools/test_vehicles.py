# SPDX-License-Identifier: AGPL-3.0-or-later
"""The vehicle registry's manifests (#455): assets/vehicles.json, each assets/<id>/vehicle.json and livery.json.

    python -I tools/test_vehicles.py

Checks every manifest the index lists: the fields the game reads (src/vehicles.js), the files present with the sizes
it states, the licence (a redistributable SPDX id, its LICENSE.txt, authors, sources, a credit line), a row in
ASSETS.md for its files, its fleet (types, ranges, sets), and that src/ names none of its files or its credit (the
manifest is the one place), its livery slots (#529: a glTF vehicle's slots name materials its model has). Each livery
the index lists (#529): its vehicle, the slots it paints among those the vehicle declares, its images WebP, PNG or JPEG
with power-of-two sides up to 2048 px, its licence, its files' rows in ASSETS.md. Docs: docs/vehicles.md, "The
manifest" and "Liveries". Each sound pack (#528), a package or a vehicle's `sounds`: its events and loops among the
game's (src/audio.js, read by tools/sound_lists.py), its files listed, present, WAV or MP3, a loop's reference. The
licences, movements and file types come from src/packageRules.json, the rules the game checks an installed package by
(#530, src/packages.js); every vehicle's files are of those types. The curated list of submitted packages
(assets/catalogue.json): each entry's id, names, author, licence and its package's https address. Exit code 1 on a
failure.
"""
import json
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
LOADERS = {"builtin", "gltf", "gltf-classic", "gltf-rigged"}
# what a package may hold, shared with the game's check of installed packages (#530)
RULES = json.load(open(os.path.join(ROOT, "src", "packageRules.json"), encoding="utf-8"))
# licences that allow the files to be redistributed with the game (ASSETS.md); NC ones not in a commercial release
LICENCES = set(RULES["licences"])
MOVES = set(RULES["moves"])
MODEL_EXT = {".gltf", ".glb"}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sound_lists  # noqa: E402



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

def model_materials(path):
    """The material names of a .glb or .gltf model (its JSON)."""
    raw = open(path, "rb").read()
    if raw[:4] == b"glTF":
        n = struct.unpack_from("<I", raw, 12)[0]
        raw = raw[20:20 + n]
    return {m.get("name") for m in json.loads(raw).get("materials", [])}


def image_size(path):
    """(kind, width, height) of a PNG, JPEG or WebP file, or (None, 0, 0)."""
    b = open(path, "rb").read()
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return ("png", *struct.unpack(">II", b[16:24]))
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        c = b[12:16]
        if c == b"VP8X":
            return ("webp", 1 + int.from_bytes(b[24:27], "little"), 1 + int.from_bytes(b[27:30], "little"))
        if c == b"VP8L":
            v = int.from_bytes(b[21:25], "little")
            return ("webp", 1 + (v & 0x3FFF), 1 + ((v >> 14) & 0x3FFF))
        if c == b"VP8 ":
            w, h = struct.unpack("<HH", b[26:30])
            return ("webp", w & 0x3FFF, h & 0x3FFF)
    if b[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(b):
            if b[i] != 0xFF:
                i += 1
                continue
            mark, size = b[i + 1], struct.unpack(">H", b[i + 2:i + 4])[0]
            if mark in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", b[i + 5:i + 9])
                return ("jpeg", w, h)
            i += 2 + size
    return (None, 0, 0)


def livery_problems(lv, lid, vehicles, files_on_disk=None, assets_md=""):
    """A livery's problems (docs/vehicles.md, Liveries; the game refuses it the same way: src/vehicles.js
    liveryProblems). vehicles: id -> its manifest. files_on_disk: its folder, None for a sample without files."""
    bad = []
    need = lambda cond, msg: cond or bad.append(msg)  # noqa: E731
    need(lv.get("schema") == 1, "schema is not 1")
    need(lv.get("kind") == "livery", f"kind {lv.get('kind')!r} is not livery")
    need(lv.get("id") == lid, f"id {lv.get('id')!r} is not its folder's {lid!r}")
    names = lv.get("names") or {}
    need(all(isinstance(names.get(k), str) and names[k].strip() for k in ("cs", "en")), "names in cs and en")
    req = list((lv.get("requires") or {}).keys())
    need(len(req) == 1, f"requires names {len(req)} vehicles, wants one")
    v = vehicles.get(req[0]) if req else None
    if not v:
        bad.append(f"its vehicle {req[0] if req else None} is not in assets/vehicles.json")
        return bad
    slots, paints = v.get("slots") or {}, v.get("colours") or []
    paths = [f.get("path") for f in lv.get("files", [])]
    for s, p in (lv.get("textures") or {}).items():
        need(s in slots, f"texture slot {s}: {v['id']} has no such slot")
        need(p in paths, f"texture {p} is not among its files")
    for s, c in (lv.get("colours") or {}).items():
        need(s in slots or s in paints, f"colour slot {s}: {v['id']} has no such slot")
        need(isinstance(c, str) and HEX.match(c), f"colour {s} {c!r} is not #rrggbb")
    num = lv.get("numbers") or {}
    need(not num.get("colour") or HEX.match(num["colour"]), f"numbers.colour {num.get('colour')!r} is not #rrggbb")
    ftypes = set((v.get("fleet") or {}).get("types", {}))
    for t in lv.get("types") or []:
        need(t in ftypes, f"type {t}: {v['id']}'s fleet has no such type")
    share = lv.get("share", 0)
    need(isinstance(share, (int, float)) and 0 <= share <= 1, f"share {share!r} is not between 0 and 1")
    lic = lv.get("licence") or {}
    need(lic.get("spdx") in LICENCES, f"licence {lic.get('spdx')!r} is none of the redistributable ones")
    need(bool(lic.get("authors")) and bool(lic.get("sources")), "licence without authors or sources")
    if files_on_disk is not None:
        rows = [r for r in assets_md.splitlines() if r.startswith("|") and f"assets/{lid}/" in r]
        for f in lv.get("files", []):
            p = os.path.join(files_on_disk, f.get("path", ""))
            if not os.path.isfile(p):
                bad.append(f"file {f.get('path')} missing")
                continue
            need(os.path.getsize(p) == f.get("bytes"), f"file {f['path']} is {os.path.getsize(p)} bytes, the manifest says {f.get('bytes')}")
            kind, w, h = image_size(p)
            need(kind is not None, f"file {f['path']} is no WebP, PNG or JPEG")
            if kind:
                need(all(0 < x <= 2048 and x & (x - 1) == 0 for x in (w, h)), f"image {f['path']} is {w} x {h} px, wants power-of-two sides up to 2048")
            need(any(f["path"] in r for r in rows), f"file {f['path']} has no row in ASSETS.md")
    return bad


def sound_problems(p, vehicles, files_on_disk=None, own=False):
    """A sound pack's problems (docs/vehicles.md, Sound packs; the game refuses it the same way: src/vehicles.js
    soundProblems). own: a vehicle's `sounds` (its files the vehicle's, no manifest fields of its own)."""
    bad = []
    need = lambda cond, msg: cond or bad.append(msg)  # noqa: E731
    ls = sound_lists.lists()
    events, loops = {a for a, _ in ls["EVENTS"]}, {a for a, _ in ls["LOOPS"]}
    if not own:
        need(p.get("schema") == 1, "schema is not 1")
        need(p.get("kind") == "sounds", f"kind {p.get('kind')!r} is not sounds")
        names = p.get("names") or {}
        need(all(isinstance(names.get(k), str) and names[k].strip() for k in ("cs", "en")), "names in cs and en")
        req = list((p.get("requires") or {}).keys())
        need(len(req) == 1 and req[0] in vehicles, f"requires {req}: wants one vehicle of assets/vehicles.json")
        lic = p.get("licence") or {}
        need(lic.get("spdx") in LICENCES, f"licence {lic.get('spdx')!r} is none of the redistributable ones")
        need(bool(lic.get("authors")) and bool(lic.get("sources")), "licence without authors or sources")
    paths = {f.get("path") for f in p.get("files", [])}

    def file(what, f):
        need(f in paths, f"{what}: {f} is not among its files")
        need(isinstance(f, str) and f.lower().endswith((".wav", ".mp3")), f"{what}: {f} is not WAV or MP3")
    for e, f in (p.get("events") or {}).items():
        need(e in events, f"event {e}: the game raises no such event")
        for x in f if isinstance(f, list) else [f]:
            file(f"event {e}", x)
    for name, lp in (p.get("loops") or {}).items():
        if name not in loops:
            bad.append(f"loop {name}: the game has no such loop")
            continue
        file(f"loop {name}", lp.get("file"))
        ref = {"mg": "refRpm", "flange": None}.get(name, "refSpeed")
        need(not ref or isinstance(lp.get(ref), (int, float)) and lp[ref] > 0, f"loop {name}: {ref} is not a positive number")
    if files_on_disk is not None:
        for f in p.get("files", []):
            q = os.path.join(files_on_disk, f.get("path", ""))
            if not os.path.isfile(q):
                bad.append(f"file {f.get('path')} missing")
                continue
            head = open(q, "rb").read(12)
            kind = "wav" if head[:4] == b"RIFF" and head[8:12] == b"WAVE" else "mp3" if head[:3] == b"ID3" or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2") else None
            need(kind is not None or not f["path"].lower().endswith((".wav", ".mp3")), f"file {f['path']} is no WAV or MP3")
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
    # the livery slots (#529): a glTF vehicle's name its model's materials; a built-in one's painted colours by name
    slots = v.get("slots") or {}
    need(isinstance(slots, dict) and all(isinstance(m, str) or isinstance(m, list) and all(isinstance(x, str) for x in m) for m in slots.values()),
         "slots is not slot -> material names")
    model = os.path.join(ASSETS, vid, v.get("model") or "")
    if slots and loader != "builtin" and os.path.isfile(model):
        have = model_materials(model)
        for s, ms in slots.items():
            for m in [ms] if isinstance(ms, str) else ms:
                need(m in have, f"slot {s}: its model has no material {m}")
    need(isinstance(v.get("colours", []), list), "colours is not a list of slot names")
    if v.get("sounds"):
        bad += [f"sounds: {b}" for b in sound_problems({**v["sounds"], "files": files}, {vid: v}, os.path.join(ASSETS, vid), own=True)]
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
    manifests = {}
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
        manifests[vid] = v
        for f in v.get("files", []):
            e = f.get("path", "").rsplit(".", 1)[-1].lower()
            if e not in RULES["types"]:
                fails.append(f"{vid}: file {f.get('path')}: .{e} is not a file type the game reads (src/packageRules.json)")
        bad = check(v, vid, types, assets_md, src)
        fails += [f"{vid}: {b}" for b in bad]
        print(f"{vid}: {v.get('loader')}, tier {v.get('tier')}, {len(v.get('files', []))} files, "
              f"{v.get('licence', {}).get('spdx')}{'' if bad else ', ok'}")
    # the liveries (#529)
    lids = index.get("liveries", [])
    need_l = {d for d in os.listdir(ASSETS) if os.path.isfile(os.path.join(ASSETS, d, "livery.json"))}
    for d in sorted(need_l - set(lids)):
        fails.append(f"assets/{d}/livery.json is not in assets/vehicles.json")
    for lid in lids:
        p = os.path.join(ASSETS, lid, "livery.json")
        if not os.path.isfile(p):
            fails.append(f"{lid}: assets/{lid}/livery.json missing")
            continue
        lv = json.load(open(p, encoding="utf-8"))
        bad = livery_problems(lv, lid, manifests, os.path.join(ASSETS, lid), assets_md)
        fails += [f"{lid}: {b}" for b in bad]
        print(f"{lid}: a livery of {next(iter(lv.get('requires', {})), None)}, {len(lv.get('files', []))} files{'' if bad else ', ok'}")
    # (none listed yet, the user, 2026-11-13: "For now I would keep only the default liveries"; the samples below and
    # tools/test_liveries.py's check the rules)
    # the curated list of submitted packages (#530)
    cat = json.load(open(os.path.join(ASSETS, "catalogue.json"), encoding="utf-8"))
    for i, c in enumerate(cat.get("packages", [])):
        what = c.get("id", f"entry {i}")
        if not re.match(RULES["id"], c.get("id", "")):
            fails.append(f"catalogue {what}: id is not author.package")
        if not all(isinstance((c.get("names") or {}).get(k), str) for k in ("cs", "en")):
            fails.append(f"catalogue {what}: names in cs and en")
        if c.get("licence") not in LICENCES:
            fails.append(f"catalogue {what}: licence {c.get('licence')!r} is none of the redistributable ones")
        if not str(c.get("url", "")).startswith("https://") or not re.search(r"(package\.json|\.zip)$", c.get("url", "")):
            fails.append(f"catalogue {what}: url is not an https address of a package.json or a .zip")
        if not c.get("author"):
            fails.append(f"catalogue {what}: no author")
    # the sound packs (#528)
    sids = index.get("sounds", [])
    for d in sorted({d for d in os.listdir(ASSETS) if os.path.isfile(os.path.join(ASSETS, d, "sounds.json"))} - set(sids)):
        fails.append(f"assets/{d}/sounds.json is not in assets/vehicles.json")
    for sid in sids:
        p = os.path.join(ASSETS, sid, "sounds.json")
        if not os.path.isfile(p):
            fails.append(f"{sid}: assets/{sid}/sounds.json missing")
            continue
        sp = json.load(open(p, encoding="utf-8"))
        bad = sound_problems(sp, manifests, os.path.join(ASSETS, sid))
        need_id = [] if sp.get("id") == sid else [f"id {sp.get('id')!r} is not its folder's {sid!r}"]
        fails += [f"{sid}: {b}" for b in need_id + bad]
    # (none listed yet: the built-in sounds; tools/test_sounds.py serves a sample pack) the check refuses what it should
    sbase = {"schema": 1, "kind": "sounds", "id": "x", "requires": {"t3h": ">=1"}, "names": {"cs": "x", "en": "x"},
             "licence": {"spdx": "CC0-1.0", "authors": ["a"], "sources": ["b"]}, "files": [{"path": "a.wav"}, {"path": "b.ogg"}]}
    ssamples = [
        ({**sbase, "events": {"bell": "a.wav", "points": ["a.wav", "a.wav"]}, "loops": {"motor": {"file": "a.wav", "refSpeed": 8.3}}}, None),
        ({**sbase, "events": {"gong": "a.wav"}}, "event gong: the game raises no such event"),
        ({**sbase, "events": {"bell": "c.wav"}}, "event bell: c.wav is not among its files"),
        ({**sbase, "events": {"bell": "b.ogg"}}, "event bell: b.ogg is not WAV or MP3"),
        ({**sbase, "loops": {"compressor": {"file": "a.wav"}}}, "loop compressor: the game has no such loop"),
        ({**sbase, "loops": {"mg": {"file": "a.wav"}}}, "loop mg: refRpm is not"),
        ({**sbase, "requires": {"t9": ">=1"}}, "requires ['t9']"),
    ]
    for sp, want in ssamples:
        got = sound_problems(sp, {"t3h": {}})
        if want is None and got or want is not None and not any(g.startswith(want) for g in got):
            fails.append(f"sound pack check on a sample: wanted {want or 'no problem'}, got {got}")
    # the livery check refuses what it should: a slot the vehicle lacks by its name
    vh = {"t3h": {"id": "t3h", "slots": {"body": ["Red_Hull"]}, "fleet": {"types": {"T3SUCS": {}}}}}
    base = {"schema": 1, "kind": "livery", "id": "x", "requires": {"t3h": ">=1"}, "names": {"cs": "x", "en": "x"},
            "licence": {"spdx": "CC0-1.0", "authors": ["a"], "sources": ["b"]}, "files": [{"path": "a.png"}]}
    lsamples = [
        ({**base, "textures": {"body": "a.png"}}, None),
        ({**base, "textures": {"roof": "a.png"}}, "texture slot roof: t3h has no such slot"),
        ({**base, "colours": {"wheels": "#000000"}}, "colour slot wheels: t3h has no such slot"),
        ({**base, "colours": {"body": "red"}}, "colour body 'red' is not"),
        ({**base, "types": ["T3M"]}, "type T3M: t3h's fleet has no such type"),
        ({**base, "requires": {"t9": ">=1"}}, "its vehicle t9 is not"),
    ]
    for lv, want in lsamples:
        got = livery_problems(lv, "x", vh)
        if want is None and got or want is not None and not any(g.startswith(want) for g in got):
            fails.append(f"livery check on a sample: wanted {want or 'no problem'}, got {got}")
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
    print(f"{len(ids)} vehicles, {len(lids)} liveries, {len(sids)} sound packs, {len(samples)} fleet, {len(lsamples)} livery "
          f"and {len(ssamples)} sound pack samples, {len(fails)} failures")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
