# SPDX-License-Identifier: AGPL-3.0-or-later
"""The page's side of the feature layer (src/features.js, #14): python -P -E tools/test_features_page.py [--line 17]

The reader on a made-up file (no data needed):
- a kind's records come back from the file's groups with their columns, a record without a heading has none;
- the counts per kind and source; a file of another version is not read;
- `yaw` turns a model's +Z to the heading: 0 faces north (the world's -z), 90 east (+x).
The page (needs data/line<N>.features.json; skipped without it, and says so):
- loads the layer, and the street detail draws as many covers, caps, grates and hydrants as the file has;
- the dev overlay (F8) shows a placeholder per record of every kind no model draws, the shelters as boxes of their
  footprints, and takes them away again.
"""
import argparse
import faulthandler
import os
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gpu  # noqa: E402
from shot import site  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

READER = """async () => {
  const { Features, readFeatures, yaw, VERSION } = await import('/src/features.js');
  const file = { version: VERSION, groups: [
    { kind: 'gutter_inlet', source: 'dtmpoints', mount: 'ground', id: ['dtmp:3', 'dtmp:2'], xy: [20, 900, 30, 1], headingFrom: 'street', heading: [null, 90] },
    { kind: 'light_on_building', source: 'dtmpoints', mount: 'wall', id: ['dtmp:4'], xy: [5, 5] },
    { kind: 'shelter', source: 'zps', mount: 'ground', id: ['shelter:zps:-742766,-1043022'], xy: [40, 2], headingFrom: 'footprint', heading: [0],
      z: [193.2], length: [4.07], width: [1.43], stop: ['U110Z2P'] },
    { kind: 'shelter', source: 'osm', mount: 'ground', id: ['osm:node/1'], xy: [1, 2] }] };
  const f = new Features(file);
  // (a turn by a about +Y takes +Z to (sin a, 0, cos a))
  const face = (h) => [Math.sin(yaw(h)), 0, Math.cos(yaw(h))].map((v) => Math.round(v * 1000) / 1000 + 0);
  return { kinds: f.kinds(), inlets: f.of('gutter_inlet'), wall: f.of('light_on_building'), shelters: f.of('shelter'), none: f.of('bench'),
    count: [f.count('gutter_inlet'), f.count('shelter'), f.count('bench')], counts: f.counts(),
    other: readFeatures({ version: VERSION + 1, groups: [] }), read: !!readFeatures(file), north: face(0), east: face(90), south: face(180) };
}"""

PAGE = """async () => {
  const { PLACEHOLDER } = await import('/src/features.js');
  const feats = window.game.data.features, drawn = {}, shown = {};
  window.world.traverse((o) => { if (o.userData.counts) Object.assign(drawn, { counts: o.userData.counts, meshes: o.children.map((m) => m.instanceMatrix.count).sort((a, b) => a - b) }); });
  // (the overlay's placeholders, named by their kind)
  window.scene.traverse((o) => { if (o.isInstancedMesh && o.name.startsWith('placeholder:')) shown[o.name.slice(12)] = o.count; });
  const want = {};
  for (const k of feats.kinds()) if (PLACEHOLDER[k]) want[k] = feats.count(k);
  const none = feats.kinds().filter((k) => !PLACEHOLDER[k] && !(k in (drawn.counts || {})));
  return { drawn, shown, want, none, kinds: feats.kinds().length, shelters: feats.count('shelter') };
}"""


def reader(page, fails):
    r = page.evaluate(READER)
    if r["inlets"] != [{"id": "dtmp:3", "kind": "gutter_inlet", "x": 20, "y": 900, "mount": "ground", "source": "dtmpoints"},
                       {"id": "dtmp:2", "kind": "gutter_inlet", "x": 30, "y": 1, "mount": "ground", "source": "dtmpoints", "heading": 90, "headingFrom": "street"}]:
        fails.append(f"a kind's records: {r['inlets']}")
    if r["wall"][0]["mount"] != "wall" or "heading" in r["wall"][0] or r["none"] != []:
        fails.append(f"a wall record, a kind the file has not: {r['wall']}, {r['none']}")
    s = r["shelters"]
    if not (len(s) == 2 and s[0] | {"x": 0, "y": 0} == {"id": "shelter:zps:-742766,-1043022", "kind": "shelter", "x": 0, "y": 0, "mount": "ground", "source": "zps",
                                                      "heading": 0, "headingFrom": "footprint", "z": 193.2, "length": 4.07, "width": 1.43, "stop": "U110Z2P"}
            and s[1] == {"id": "osm:node/1", "kind": "shelter", "x": 1, "y": 2, "mount": "ground", "source": "osm"}):
        fails.append(f"a kind from two sources: {s}")
    if r["count"] != [2, 2, 0] or r["counts"] != {"gutter_inlet": {"dtmpoints": 2}, "light_on_building": {"dtmpoints": 1}, "shelter": {"zps": 1, "osm": 1}}:
        fails.append(f"counts {r['count']}, {r['counts']}")
    if r["other"] is not None or not r["read"]:
        fails.append(f"a file of another version read: {r['other']}, this one: {r['read']}")
    if (r["north"], r["east"], r["south"]) != ([0, 0, -1], [1, 0, 0], [0, 0, 1]):
        fails.append(f"yaw: a model's +Z at headings 0, 90, 180 faces {r['north']}, {r['east']}, {r['south']}")


def pages(context, url, line, fails):
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)[:200]))
    page.goto(f"{url}/?line={line}", timeout=180000)
    page.wait_for_function("!document.getElementById('menu').classList.contains('hidden') && window.renderer && window.world", timeout=180000)
    page.click("#btnStart")
    page.wait_for_function("window.game && window.scene", timeout=120000)
    off = page.evaluate(PAGE)
    counts = off["drawn"].get("counts") or {}
    if not counts or sorted(v for v in counts.values() if v) != off["drawn"]["meshes"]:  # (as built: the near batches then show the near ones)
        fails.append(f"the street detail's meshes {off['drawn'].get('meshes')} against the layer's counts {counts}")
    if not (counts.get("manhole", 0) > 1000 and counts.get("gutter_inlet", 0) > 500):
        fails.append(f"line {line}'s covers and grates: {counts}")
    if off["none"]:
        fails.append(f"kinds with neither a model nor a placeholder: {off['none']}")
    if off["shown"]:
        fails.append(f"placeholders without the overlay: {off['shown']}")
    page.keyboard.press("F8")
    on = page.evaluate(PAGE)
    if not on["want"] or on["shown"] != on["want"]:
        fails.append(f"the overlay's placeholders {on['shown']}, the layer's records {on['want']}")
    page.keyboard.press("F8")
    again = page.evaluate(PAGE)
    if again["shown"]:
        fails.append(f"placeholders left after the overlay: {again['shown']}")
    if errors:
        fails.append(f"page errors: {errors[:3]}")
    page.close()
    return f"line {line}: {off['kinds']} kinds, {sum(counts.values())} drawn, {sum(on['want'].values())} placeholders ({on['shelters']} shelters)"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    args = ap.parse_args()
    faulthandler.dump_traceback_later(600, exit=True)  # the whole test
    fails, said = [], ""
    with sync_playwright() as pw, site(ROOT) as url:
        browser, _ = gpu.launch(pw, quiet=True)
        try:
            context = browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
            page = context.new_page()
            page.goto(f"{url}/src/features.js")
            reader(page, fails)
            page.close()
            if os.path.exists(os.path.join(ROOT, "data", f"line{args.line}.features.json")):
                said = "; " + pages(context, url, args.line, fails)
            else:
                said = f" (the page part skipped: no data/line{args.line}.features.json; python -I tools/snapshot.py data-fetch)"
        finally:
            browser.close()
    faulthandler.cancel_dump_traceback_later()
    if fails:
        sys.exit("; ".join(fails))
    print(f"feature layer: the reader, the street detail from it, the overlay's placeholders: pass{said}")


if __name__ == "__main__":
    main()
