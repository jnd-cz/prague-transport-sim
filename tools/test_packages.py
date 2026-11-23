# SPDX-License-Identifier: AGPL-3.0-or-later
"""Vehicle packages a player installs (#530) in headless Chromium: the menu's Vehicles… page, the check, the store.

Usage: python -P -E tools/test_packages.py [--line 17]

Makes the sample packages here (a box the size of a T3 car as a tier-1 glTF vehicle, generated as a GLB):
- a bundle .zip holding three packages in their folders, the vehicle, a sound pack and a fleet for it, installed
  through the page's .zip input. The vehicle shows in the model menu after its check, credits itself when picked, and
  our tram runs as it with the fleet's numbers; all three survive a reload (the browser's origin private file system).
- nine broken ones, each refused with its reason: a bad manifest (no names), a missing file, a wrong hash, wrong axes
  (the box lying across the track), a claimed tier without its nodes (a rig naming bogies the model lacks), over the
  triangle budget, longer than a vehicle may be (34 m: the cap is 33 m), a file's name that is not a plain one, a
  model that links to an address outside the package.
- seven over the limits (#713), refused before they are unpacked or at their content: an archive whose directory
  understates a file, one of more files than the cap, a file declared over its type's cap, an image over 2048 px a
  side, a sound over 60 s, a pack's gain over 2, an id the store keeps for itself.
- a .gltf with its .bin beside it among the files installs; the loading screen writes any file's name as text.
- a 25 m box installs with a warning: longer than its type, it runs on the type's pivots (articulated types: #579).
- removing the vehicle takes it out of the menu, and its sound pack and fleet out of the registry.
- each glTF vehicle of the repository loads and measures within src/packageRules.json's fit and budget (the rules' calibration).
Needs the line's data (python -I tools/snapshot.py data-fetch); skips without it.
"""
import argparse
import faulthandler
import functools
import hashlib
import http.server
import io
import json
import math
import os
import struct
import sys
import threading
import wave
import zipfile
import zlib

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))  # (python -P leaves it out)
import gpu  # noqa: E402

RULES = json.load(open(os.path.join(ROOT, "src", "packageRules.json"), encoding="utf-8"))
VID = "sample.box-tram"
CREDIT = "Sample box tram (tools/test_packages.py), CC0"
MARKUP = "<img src=x onerror=window.marked=1>.txt"   # (a file's name that would be markup if it were written as such)


def glb(size=(2.4, 3.2, 14.0), cells=1, names=("body",), image=None, split=None):
    """A GLB of boxes (one node and mesh per name, each the whole box) of size (x across, y up, z along) standing on
    y = 0, each face cut into cells × cells squares: 12 × cells² triangles a box. image: an image the model links to by
    that uri; split: the name of a .bin beside it, and the result is (the .gltf, the .bin) instead of one GLB."""
    sx, sy, sz = size
    pos, idx = [], []
    for axis in range(3):
        for side in (0, 1):
            u, v = [a for a in range(3) if a != axis]
            base = len(pos)
            for i in range(cells + 1):
                for j in range(cells + 1):
                    p = [0.0, 0.0, 0.0]
                    p[axis] = side
                    p[u], p[v] = i / cells, j / cells
                    pos.append(((p[0] - 0.5) * sx, p[1] * sy, (p[2] - 0.5) * sz))
            for i in range(cells):
                for j in range(cells):
                    a, b, c, d = (base + i * (cells + 1) + j, base + (i + 1) * (cells + 1) + j,
                                  base + (i + 1) * (cells + 1) + j + 1, base + i * (cells + 1) + j + 1)
                    idx += [a, b, c, a, c, d] if side else [a, c, b, a, d, c]
    pb = b"".join(struct.pack("<3f", *p) for p in pos)
    ib = b"".join(struct.pack("<I", i) for i in idx)
    binary = pb + ib
    doc = {
        "asset": {"version": "2.0", "generator": "tools/test_packages.py"},
        "scene": 0, "scenes": [{"nodes": list(range(len(names)))}],
        "nodes": [{"name": n, "mesh": 0} for n in names],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(pos), "type": "VEC3",
             "min": [min(p[k] for p in pos) for k in range(3)], "max": [max(p[k] for p in pos) for k in range(3)]},
            {"bufferView": 1, "componentType": 5125, "count": len(idx), "type": "SCALAR"}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(pb)}, {"buffer": 0, "byteOffset": len(pb), "byteLength": len(ib)}],
        "buffers": [{"byteLength": len(binary)}],
    }
    if image:
        doc["images"] = [{"uri": image}]
    if split:
        doc["buffers"][0]["uri"] = split
        return json.dumps(doc).encode(), binary
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    binary += b"\0" * (-len(binary) % 4)
    body = struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(binary), 0x004E4942) + binary
    return struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body


def bell():
    b, out = io.BytesIO(), bytearray()
    for i in range(4410):
        out += int(8000 * math.sin(2 * math.pi * 1180 * i / 22050) * math.exp(-i / 4000)).to_bytes(2, "little", signed=True)
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(bytes(out))
    return b.getvalue()


def tone(seconds, rate=8000):
    """A quiet 8-bit mono WAV of that length (61 s: 488 kB)."""
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(rate)
        w.writeframes(bytes([128]) * int(seconds * rate))
    return b.getvalue()


def png(w, h):
    """A grey PNG of w x h px."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = (b"\x00" + b"\x80" * w) * h
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")


def understated(data, name, declared):
    """The .zip with `name`'s unpacked size in its directory (and its local header) set to `declared`."""
    out, at = bytearray(data), 0
    for sig, size_at, name_at, len_at in ((b"PK\x01\x02", 24, 46, 28), (b"PK\x03\x04", 22, 30, 26)):
        at = 0
        while (at := out.find(sig, at)) >= 0:
            n = struct.unpack_from("<H", out, at + len_at)[0]
            if bytes(out[at + name_at:at + name_at + n]) == name.encode():
                struct.pack_into("<I", out, at + size_at, declared)
            at += 4
    return bytes(out)


def manifest(kind, pid, files, **more):
    """A package.json: the fields every kind has, its files listed with their sizes and hashes."""
    return {"schema": 1, "kind": kind, "id": pid, "version": "1.0.0", "game": ">=1.0 <2",
            "names": {"cs": f"Ukázka {pid}", "en": f"Sample {pid}"},
            "description": {"cs": "Testovací balíček.", "en": "A test package."},
            "licence": {"spdx": "CC0-1.0", "commercial": True, "authors": ["the test"], "sources": ["tools/test_packages.py"], "credit": CREDIT},
            "files": [{"path": k, "bytes": len(v), "sha256": hashlib.sha256(v).hexdigest()} for k, v in files.items()], **more}


def zipped(packages):
    """A .zip of packages [(folder, manifest, files)]; folder '' puts one at the root."""
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for folder, m, files in packages:
            pre = f"{folder}/" if folder else ""
            z.writestr(pre + "package.json", json.dumps(m, indent=1))
            for k, v in files.items():
                z.writestr(pre + k, v)
    return b.getvalue()


def vehicle(pid=VID, model=None, **more):
    files = {"box.glb": model or glb(), **more.pop("extra", {})}
    m = manifest("vehicle", pid, files, type="T3", loader="gltf", model="box.glb", tier=1,
                 fleet={"operator": "Test", "types": {"T3": {"ranges": [[9001, 9010]]}}}, **more)
    return m, files


def samples():
    vm, vf = vehicle()
    sf = {"bell.wav": bell()}
    sm = manifest("sounds", "sample.box-sounds", sf, requires={VID: ">=1.0"}, events={"bell": "bell.wav"})
    fm = manifest("fleet", "sample.box-fleet", {"LICENSE.txt": b"CC0"}, requires={VID: ">=1.0"},
                  operator="Test", types={"T3": {"list": [9100, 9101, 9102]}}, sets=[[9100, 9101]])
    good = zipped([("box-tram", vm, vf), ("box-sounds", sm, sf), ("box-fleet", fm, {"LICENSE.txt": b"CC0"})])
    broken = {}
    m, f = vehicle("sample.no-names")
    del m["names"]
    broken["bad manifest"] = (zipped([("", m, f)]), "names in cs and en")
    m, f = vehicle("sample.missing")
    broken["missing file"] = (zipped([("", m, {})]), "file box.glb missing")
    m, f = vehicle("sample.wrong-hash")
    m["files"][0]["sha256"] = "0" * 64
    broken["wrong hash"] = (zipped([("", m, f)]), "its sha256 is not the one listed")
    m, f = vehicle("sample.across", model=glb(size=(14.0, 3.2, 2.4)))
    broken["wrong axes"] = (zipped([("", m, f)]), "wide, over its type's")
    rig = json.dumps({"root": "body", "bogies": [{"name": "bogie.1"}, {"name": "bogie.2"}]}).encode()
    m, f = vehicle("sample.no-rig", extra={"rig.json": rig}, rig="rig.json", moves=["bogies"])
    m["loader"], m["tier"] = "gltf-rigged", 2
    broken["claimed tier without its nodes"] = (zipped([("", m, f)]), "its rig lacks bogie: bogie.1")
    cells = math.ceil(math.sqrt(RULES["budget"]["triangles"] / 12)) + 1
    m, f = vehicle("sample.heavy", model=glb(cells=cells))
    broken["over budget"] = (zipped([("", m, f)]), "triangles a car, over the budget")
    m, f = vehicle("sample.too-long", model=glb(size=(2.4, 3.2, 34.0)))
    broken["too long"] = (zipped([("", m, f)]), f"over the {RULES['fit']['maxLength']} m a vehicle may be")
    # a file's name is a plain one (it is shown on the loading screen), and a model links only to its package's files
    m, f = vehicle("sample.markup", extra={MARKUP: b"x"})
    broken["markup in a file's name"] = (zipped([("", m, f)]), "not a path inside the package")
    m, f = vehicle("sample.linked", model=glb(image="https://example.invalid/t.png"))
    broken["a model linking elsewhere"] = (zipped([("", m, f)]), "links to https://example.invalid/t.png")
    # over the limits (#713). Before anything is unpacked: a directory that understates a file (1 MB of zeros declared
    # as 1 kB), more files than an archive may hold, a file declared over its type's cap
    m, f = vehicle("sample.bomb", extra={"notes.txt": bytes(100_000)})
    broken["an archive that understates a file"] = (understated(zipped([("", m, f)]), "notes.txt", 1000), "unpacks to more than the 1000 bytes its archive declares")
    m, f = vehicle("sample.many")
    broken["too many files"] = (zipped([("", m, {**f, **{f"x/{i}.txt": b"" for i in range(RULES["caps"]["entries"])}})]), f"files, over the cap of {RULES['caps']['entries']}")
    m, f = vehicle("sample.big-text", extra={"notes.txt": bytes(RULES["caps"]["text"] + 1)})
    broken["a file over its type's cap"] = (zipped([("", m, f)]), "unpacked, over the cap of")
    # at an install, what the files hold: an image's sides, a sound's length, a pack's gain
    side = RULES["image"]["maxSide"] * 2
    m, f = vehicle("sample.wide-image", extra={"wide.png": png(side, 16)})
    broken["an image over the side"] = (zipped([("", m, f)]), f"is {side} x 16 px, over {RULES['image']['maxSide']} px a side")
    lf = {"long.wav": tone(RULES["sound"]["maxSeconds"] + 1)}
    lm = manifest("sounds", "sample.long-sound", lf, requires={VID: ">=1.0"}, events={"bell": "long.wav"})
    broken["a sound over the length"] = (zipped([("", lm, lf)]), f"over the {RULES['sound']['maxSeconds']} s a sound may")
    gf = {"bell.wav": bell()}
    gm = manifest("sounds", "sample.loud", gf, requires={VID: ">=1.0"}, events={"bell": "bell.wav"}, gain=5)
    broken["a gain over the range"] = (zipped([("", gm, gf)]), f"gain 5 is not between 0 and {RULES['sound']['maxGain']}")
    m, f = vehicle("index.json")
    broken["an id the store keeps"] = (zipped([("", m, f)]), "a name the browser's store keeps for itself")
    gltf, binary = glb(split="box.bin")
    sf = {"box.gltf": gltf, "box.bin": binary}
    sm = manifest("vehicle", "sample.split", sf, type="T3", loader="gltf", model="box.gltf", tier=1,
                  fleet={"operator": "Test", "types": {"T3": {"ranges": [[9001, 9010]]}}})
    m, f = vehicle("sample.long", model=glb(size=(2.4, 3.2, 25.0)))
    return good, broken, zipped([("", m, f)]), zipped([("", sm, sf)])


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


REPORT = r"""() => [...document.querySelectorAll('#pkgReport > div')].map((d) => d.innerText.replace(/\n+/g, ' | '))"""
STATE = r"""async () => {
  const P = await import('/src/packages.js'), V = await import('/src/vehicles.js');
  return { state: [...P.state.values()].map((s) => ({ id: s.id, ok: s.ok, enabled: s.enabled, problems: s.problems })),
    models: [...document.getElementById('optModel').options].map((o) => o.value),
    sounds: [...V.soundPacks.keys()], fleet: V.byId.get('sample.box-tram')?.fleet?.package ?? null };
}"""
BUILTIN = r"""async () => {
  const V = await import('/src/vehicles.js'), M = await import('/src/models.js'), T = await import('/src/tram.js');
  const r = await (await fetch('/src/packageRules.json')).json(), out = {};
  for (const v of V.vehicles.filter((x) => !x.installed && x.loader !== 'builtin')) {   // (the built-in car is the game's code)
    try { await M.loadVehicle(v); } catch (e) { out[v.id] = { error: String(e) }; continue; }
    const f = M.vehicleFit(v), t = T.VEHICLE_TYPES[v.type] || T.VEHICLE_TYPES.T3;
    out[v.id] = { ...f, size: f.size.map((x) => +x.toFixed(3)), low: +f.low.toFixed(3),
      fits: f.size[2] <= t.length + r.fit.lengthOver && f.size[0] <= t.width + r.fit.widthOver && f.low >= -r.fit.railLow && f.low <= r.fit.railHigh,
      inBudget: f.triangles <= r.budget.triangles && f.drawCalls <= r.budget.drawCalls };
  }
  return out;
}"""
START = r"""async () => {
  const $ = (id) => document.getElementById(id), { startShift } = await import('/tools/bench/shift.js');
  $('optFleet').value = ''; $('optCars').value = '2';
  window.headless = true;
  await startShift({ timeout: 120 });
  const m = window.tramModel;
  window.headless = false;
  return { vehicle: m.userData.vehicle, fleet: m.userData.fleet, kind: m.userData.kind,
    credit: (document.getElementById('attrib').textContent || '').includes(%CREDIT%) };
}"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if not os.path.exists(os.path.join(ROOT, "data", f"line{args.line}.json")):
        print(f"skipped: no data/line{args.line}.json (python -I tools/snapshot.py data-fetch)")
        return 0
    faulthandler.dump_traceback_later(900, exit=True)  # the whole test: page.evaluate has no time limit
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    good, broken, long, split = samples()
    fails = []

    def need(ok, why):
        if not ok:
            fails.append(why)
            print("FAIL", why)

    def open_menu(page):
        page.goto(f"{base}/?line={args.line}", timeout=300000)
        page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=300000)

    def put(page, name, data):
        page.click("#btnVehicles")
        page.set_input_files("#pkgZip", files=[{"name": name, "mimeType": "application/zip", "buffer": data}])
        try:
            page.wait_for_function("document.querySelectorAll('#pkgReport > div').length > 0", timeout=120000)
        except Exception:
            print("no report; errors:", errors, page.evaluate("document.getElementById('pkgBody').innerText.slice(0, 600)"))
            raise
        got = page.evaluate(REPORT)
        page.click("#btnPkgClose")
        return got

    try:
        with sync_playwright() as p:
            browser = gpu.launch(p)[0]
            ctx = browser.new_context(viewport={"width": 1100, "height": 700})
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("dialog", lambda d: d.accept())
            page.on("console", lambda m: m.type in ("error", "warning") and "packages" in m.text and print("console:", m.text))
            open_menu(page)
            builtin = page.evaluate(BUILTIN)
            for vid, f in builtin.items():
                print(f"built-in {vid}: {json.dumps(f)}")
                need("error" not in f, f"built-in {vid} does not load: {f.get('error')}")
                need(f.get("fits") and f.get("inBudget"), f"built-in {vid} outside the rules' fit or budget: {f}")
            rep = put(page, "sample-bundle.zip", good)
            print("bundle:", rep)
            need(len(rep) == 3 and all(r.startswith("✓") for r in rep), f"the bundle's three packages not all installed: {rep}")
            s = page.evaluate(STATE)
            need(VID in s["models"], f"{VID} not in the model menu: {s['models']}")
            need("sample.box-sounds" in s["sounds"] and s["fleet"] == "sample.box-fleet", f"sound pack {s['sounds']}, fleet {s['fleet']}")
            for what, (data, want) in broken.items():
                rep = put(page, f"{what}.zip", data)
                print(f"{what}: {rep}")
                need(len(rep) == 1 and rep[0].startswith("✕") and want in rep[0], f"{what}: wants refused with '{want}', got {rep}")
            rep = put(page, "long.zip", long)
            print("long:", rep)
            need(len(rep) == 1 and rep[0].startswith("✓") and "runs on T3's bogie pivots" in rep[0], f"the 25 m box: wants installed with a warning, got {rep}")
            page.evaluate("async () => (await import('/src/packages.js')).remove('sample.long')")
            rep = put(page, "split.zip", split)
            print("split:", rep)
            need(len(rep) == 1 and rep[0].startswith("✓"), f"a .gltf with its .bin beside it among the files: wants installed, got {rep}")
            page.evaluate("async () => (await import('/src/packages.js')).remove('sample.split')")
            # the loading screen writes a file's name as text, whatever it is
            shown = page.evaluate("""async (name) => {
              const { Loader } = await import('/src/loading.js');
              const l = new Loader();
              l.prefetch('data/none-' + Date.now() + '.bin', 0, name);
              l.render(true);
              const cells = [...document.querySelectorAll('#loadFiles td:first-child')].map((c) => c.textContent);
              const out = { text: cells.includes(name), nodes: document.querySelectorAll('#loadFiles img').length };
              removeEventListener('error', l.onError);
              return out; }""", MARKUP)
            page.wait_for_timeout(300)
            need(shown == {"text": True, "nodes": 0} and page.evaluate("window.marked") is None, f"a file's name on the loading screen is not plain text: {shown}")
            s = page.evaluate(STATE)
            need(sorted(x["id"] for x in s["state"]) == sorted([VID, "sample.box-sounds", "sample.box-fleet"]),
                 f"installed after the broken ones: {[x['id'] for x in s['state']]}")
            # a reload: still there, checked again from the store
            open_menu(page)
            s = page.evaluate(STATE)
            print("after reload:", json.dumps(s["state"]))
            need(VID in s["models"] and all(x["ok"] for x in s["state"]) and len(s["state"]) == 3, f"after a reload: {s}")
            # picked: it loads, credits itself and our tram runs as it, numbered from the fleet package
            page.select_option("#optModel", VID)
            page.wait_for_function(f"document.getElementById('attrib').textContent.includes({json.dumps(CREDIT)})", timeout=60000)
            run = page.evaluate(START.replace("%CREDIT%", json.dumps(CREDIT)))
            print("drive:", run)
            need(run["vehicle"] == VID and run["kind"] == "gltf" and run["credit"], f"our tram as {run}")
            need(run["fleet"] == [9100, 9101] or all(n in (9100, 9101, 9102) for n in run["fleet"]), f"our tram's numbers {run['fleet']} not the fleet package's")
            # removed: out of the menu, its packages out of the registry
            open_menu(page)
            page.click("#btnVehicles")
            page.click(f".pkgRow[data-id='{VID}'] button:has-text('Remove'), .pkgRow[data-id='{VID}'] button:has-text('Odebrat')")
            page.wait_for_function(f"!document.querySelector(\".pkgRow[data-id='{VID}']\")", timeout=30000)
            s = page.evaluate(STATE)
            print("after removing:", json.dumps(s))
            need(VID not in s["models"], f"{VID} still in the model menu after removing")
            # (the game's own sound packs stay: assets/vehicles.json's, #636)
            need("sample.box-sounds" not in s["sounds"] and all(not x["ok"] for x in s["state"]), f"its packages still in use: {s}")
            open_menu(page)
            s = page.evaluate(STATE)
            need(VID not in s["models"] and len(s["state"]) == 2, f"after removing and a reload: {s}")
            need(not errors, f"page errors {errors}")
            ctx.close()
            browser.close()
    finally:
        server.shutdown()
    print(f"vehicle packages: bundle installed, {len(broken)} broken refused, a long one warned, a split one installed, reload, credit, drive, removal: "
          + ("pass" if not fails else f"{len(fails)} failures"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
