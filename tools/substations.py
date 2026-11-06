"""The tram network's traction substations from the local OSM extract, for the wire in src/electric.js (#351, #355):
python -P -E tools/substations.py            lists them
python -P -E tools/substations.py --write    sets data/truth.json's substations from them

A substation here: power=substation, substation=traction, 600 V on its voltage tag, operated by DPP (OSM spells it two
ways). Its place is the centroid of the way's nodes, or the node, in S-JTSK whole metres (tools/geo.py), which the game
turns into its frame with data.frame.origin; keyed by OSM id, which a rebuild does not renumber."""
import json
import os
import sys

import osmium

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves it out)
from atomic import replacing  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PBF = os.path.join(ROOT, "raw", "osm", "praha.osm.pbf")
TRUTH = os.path.join(ROOT, "data", "truth.json")
OPERATORS = ("DPP", "Dopravní podnik hl. m. Prahy")
SOURCE = ("OSM extract raw/osm/praha.osm.pbf (Geofabrik 2026-11-04): power=substation, substation=traction, voltage 22000;600, operator DPP; "
          "python -P -E tools/substations.py --write. e, n: S-JTSK (EPSG:5514) of the centroid, whole metres")
READER = "src/electric.js Feeding, through src/main.js and src/game.js (#351): the wire's feeds; tools/substations.py writes it"


def is_tram_substation(tags):
    """Whether these OSM tags are a tram network's traction substation."""
    if tags.get("power") != "substation" or tags.get("substation") != "traction":
        return False
    if tags.get("operator") not in OPERATORS:
        return False
    return "600" in tags.get("voltage", "").split(";")


class Handler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.found = []

    def _add(self, kind, oid, tags, lat, lon):
        t = {x.k: x.v for x in tags}
        if is_tram_substation(t):
            self.found.append({"osm": f"{kind}/{oid}", "ref": t.get("ref"), "lat": lat, "lon": lon})

    def node(self, n):
        if "power" in n.tags:
            self._add("node", n.id, n.tags, n.location.lat, n.location.lon)

    def way(self, w):
        if "power" not in w.tags:
            return
        pts = [(x.lat, x.lon) for x in w.nodes if x.location.valid()]
        if pts:
            self._add("way", w.id, w.tags, sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def read():
    from geo import Frame  # (needs the correction grid in raw/proj)
    h = Handler()
    h.apply_file(PBF, locations=True)
    f = Frame()
    out = []
    for s in sorted(h.found, key=lambda x: x["osm"]):
        x, y = f.xy(s["lat"], s["lon"])
        e, n = f.to_jtsk(x, y)
        out.append({"osm": s["osm"], "ref": s["ref"], "e": round(float(e)), "n": round(float(n))})
    return out


def write_truth(subs):
    """The section by text, the rest of the hand-made file as it is: json.dump would reflow all of it."""
    with open(TRUTH, encoding="utf-8", newline="") as fh:
        text = fh.read()
    lines = ",\n".join("   " + json.dumps(s, ensure_ascii=False) for s in subs)
    block = ' "substations": {\n  "source": ' + json.dumps(SOURCE, ensure_ascii=False) + ',\n  "list": [\n' + lines + "\n  ]\n }"
    start = text.find('\n "substations": {')
    if start >= 0:
        end = text.index("\n }", start) + 3
        text = text[:start + 1] + block + text[end:]
    else:
        tail = text[:text.rstrip().rfind("}")].rstrip()
        text = tail + ",\n" + block + "\n}\n"
    if '"substations":' not in text[:text.index('\n "stops": [')]:
        at = text.index('\n },\n "stops": [')
        text = text[:at] + ',\n  "substations": ' + json.dumps(READER, ensure_ascii=False) + text[at:]
    with replacing(TRUTH, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def main():
    subs = read()
    print(f"{len(subs)} tram substations")
    for s in subs:
        print(f"  {s['osm']:18} {s['ref'] or '-':14} {s['e']} {s['n']}")
    if "--write" in sys.argv:
        write_truth(subs)
        print("data/truth.json written")


if __name__ == "__main__":
    main()
