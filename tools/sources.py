"""Sources per layer, in fallback order, and the provenance every built file carries (#10).

The one table of what the world is built from: SOURCES (who, licence, the date of the data, the height
datum) and LAYERS (per layer the sources in the order they are used; a feature's fallback level is its
index there, 0 = the preferred source). Decision: docs/decisions/2026-10-30-source-per-layer.md.

A build tool stamps each output file, per list (JSON key) the layer and the count per level:
    out["provenance"] = stamp("fine_terrain.py", {"blocks": entry("terrain", [n_ipr, n_dmr5g, n_coarse], "blocks")})
    out["attribution"] = attribution(out["provenance"])
A list whose features come from several levels gives each feature its level (`fb`, or a parallel `fb`
array for lists of bare coordinates); a list from one level has no per-feature field: its counts say
which. Rules (no data behind them) are sources
too (`rule:…`), so a heuristic's output is never mistaken for data.

Stdlib only (tools run with -I). `python -I tools/sources.py` prints the table with the snapshot's dates.
"""
from dataclasses import dataclass
import json
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass(frozen=True)
class Source:
    title: str
    group: str | None  # snapshot group (snapshots/<id>.json) with the files; None: a rule, or not pinned yet
    attribution: str  # for the game's credits line, "what: holder" (grouped by holder); "" for rules
    date: str  # the data's date as far as it is known; "@…" is read from the snapshot (dated())
    date_kind: str  # state (the whole dataset as of), capture (observation years), fetched (no stated date)
    datum: str = ""  # height sources: what their heights are


IPR = "datový podklad © IPR Praha (CC BY 4.0)"
SOURCES = {
    # terrain
    "ipr-dtm": Source("IPR Praha digital terrain model, 1 m raster", "ipr-dtm", f"Terrain: {IPR}",
                      "lidar 2023, corrected and resampled 2025-07-10", "capture",
                      "Bpv assumed: the file states none; measured against DMR 5G on every build (fine_terrain.py), IPR asked (#62)"),
    "dmr5g": Source("ČÚZK DMR 5G, 2 m", "dem", "Terrain: ČÚZK DMR 5G (CC BY 4.0)",
                    "lidar 2009-2013, updated since; exported 2026-10-21..23", "capture", "Bpv"),
    "coarse": Source("the line's 10 m grid of DMR 5G (build_line.py)", "dem", "Terrain: ČÚZK DMR 5G (CC BY 4.0)",
                     "as dmr5g", "capture", "Bpv"),
    # surveyed streets, tracks, points
    "zps": Source("Prague DTM, ZPS street survey (OPL areas, KR 3D lines)", "dtm", f"Streets (DTM Praha): {IPR}",
                  "@zps", "state", "Bpv"),
    "dtm-di": Source("Prague DTM, DI set 7 tram track axes", "dtm-di", f"Tracks (DTM Praha): {IPR}",
                     "@dtm-di", "state", "Bpv"),
    "dtmp-tracks": Source("archived Prague technical map (DTMP), tram track axes", "dtmp-tracks",
                          f"Tracks (archived DTM Praha): {IPR}", "archive closed 2024-07; records changed up to 2024-04-18",
                          "state", "Bpv"),
    "dtmp": Source("archived Prague technical map (DTMP), street lines and surfaces", None,
                   f"Streets (archived DTM Praha): {IPR}", "archive closed 2024-07 (not in the snapshot yet)", "state", "Bpv"),
    "dtmpoints": Source("archived Prague technical map (DTMP), surface points", "dtmpoints",
                        f"Street furniture (archived DTM Praha): {IPR}", "state 2024-06-30", "state"),
    # IPR Geoportál layers
    "lod2": Source("IPR Praha 3D buildings (LOD2)", "geoportal", f"3D buildings: {IPR}", "fetched 2026-10-21..23", "fetched", "Bpv"),
    "mosty3d": Source("IPR Praha 3D bridges (Mosty 3D)", "geoportal", f"3D bridges: {IPR}",
                      "photogrammetry 2001-2008", "capture", "Bpv"),
    "walls": Source("IPR Praha retaining walls", "geoportal", f"Retaining walls: {IPR}", "fetched 2026-10-21..23", "fetched"),
    "trees": Source("IPR Praha tree register and tree rows", "geoportal", f"Trees: {IPR}", "fetched 2026-10-21..23", "fetched"),
    "ortho": Source("IPR Praha orthophoto, leaf-off", "ortho", f"Orthophoto: {IPR}", "flight 2026", "capture"),
    # open data
    "osm": Source("OpenStreetMap, Geofabrik extract", "osm", "Map data: © OpenStreetMap contributors (ODbL)", "@osm", "state"),
    "gtfs": Source("PID GTFS timetable", "gtfs", "Timetable: PID GTFS, data.pid.cz (CC BY 4.0)", "@gtfs", "state"),
    # rules: what a heuristic decided where no source says (knowledge.md, "Heuristics …")
    "rule:assumed": Source("a default value (no data)", None, "", "", ""),
    "rule:placement": Source("placement rules (spacing, offsets from tracks and kerbs)", None, "", "", ""),
    "rule:curvature": Source("limits from track curvature and switches", None, "", "", ""),
}

# Each layer's sources, preferred first. Levels not built yet stay in the chain: a file's counts show
# them as 0, so the report says what the layer still falls back to.
LAYERS = {
    "terrain": ("ipr-dtm", "dmr5g", "coarse"),
    "streets": ("zps", "dtmp", "osm"),  # areas and kerbs; OSM: road centre lines with widths
    "tracks": ("dtm-di", "dtmp-tracks", "osm"),  # centrelines (#20); OSM reviewed gaps only
    "structures": ("zps", "mosty3d", "osm"),  # bridge decks (survey) over the model over OSM tags (#13)
    "furniture": ("dtmpoints", "osm", "rule:placement"),  # survey points over OSM over rules (#14)
    "buildings": ("lod2", "osm"),
    "walls": ("zps", "walls", "rule:placement"),
    "trees": ("trees", "osm"),
    "stops": ("osm", "gtfs"),  # platforms and stop positions from OSM, names and lines from the timetable
    "timetable": ("gtfs",),
    "signals": ("osm", "rule:placement"),
    "speeds": ("osm", "rule:curvature"),
    "clearances": ("osm", "rule:assumed"),  # OSM maxheight, else the default per kind
    "crossings": ("osm",),  # where roads and paths cross the tracks (#24)
    "areas": ("osm",),  # water, green, landuse
}


def _snapshot(root=ROOT):
    sid = open(os.path.join(root, "snapshots", "CURRENT"), encoding="utf-8").read().strip()
    return json.load(open(os.path.join(root, "snapshots", f"{sid}.json"), encoding="utf-8"))


def _files(group, root=ROOT):
    return [f["path"] for g in _snapshot(root)["groups"] if g["name"] == group for f in g["files"]]


def dated(sid, root=ROOT):
    """The source's date; "@…" dates come from the snapshot's files (one place: the files themselves)."""
    d = SOURCES[sid].date
    if not d.startswith("@"):
        return d
    key = d[1:]
    if key == "osm":  # Geofabrik names the extract by its date: czech-republic-YYMMDD.osm.pbf
        ds = sorted(m.group(1) for p in _files("osm", root) if (m := re.search(r"-(\d{6})\.osm\.pbf$", p)))
        return f"state 20{ds[-1][:2]}-{ds[-1][2:4]}-{ds[-1][4:]}" if ds else "unknown"
    if key == "gtfs":
        with zipfile.ZipFile(os.path.join(root, "raw", "PID_GTFS.zip")) as z:
            rows = z.read("feed_info.txt").decode("utf-8-sig").splitlines()
        r = dict(zip(rows[0].split(","), rows[1].split(",")))
        f = lambda v: f"{v[:4]}-{v[4:6]}-{v[6:]}"  # noqa: E731
        return f"feed {f(r['feed_start_date'])}..{f(r['feed_end_date'])}"
    if key == "zps":
        ms = sorted({m.group(1) for p in _files("dtm", root) if (m := re.search(r"_\d{6}_(\d{8})_ZPS_", p))})
        return "state " + ", ".join(f"{m[:4]}-{m[4:6]}-{m[6:]}" for m in ms) if ms else "unknown"
    if key == "dtm-di":
        prov = json.load(open(os.path.join(root, "raw", "dtm-di", "provenance.json"), encoding="utf-8"))
        return "state " + ", ".join(sorted({p["state"][:10] for p in prov["packages"]}))
    raise KeyError(d)


def entry(layer, counts, unit="features", checks=None):
    """One list of a built file: its layer and how many of its features came from each level of the
    layer's chain. `checks`: what the tool measured to trust a source (the terrain datum check), kept
    with the data it vouches for."""
    chain = LAYERS[layer]
    if len(counts) != len(chain):
        raise ValueError(f"{layer}: {len(counts)} counts for the {len(chain)} levels {chain}")
    return {"layer": layer, "levels": list(chain), "count": [int(c) for c in counts], "unit": unit} | (
        {"checks": checks} if checks else {})


def single(layer, source, n, unit="features"):
    """A list of n features that all came from one level of the layer's chain."""
    if source not in LAYERS[layer]:
        raise KeyError(f"{source} is not in the {layer} chain {LAYERS[layer]}")
    return entry(layer, [n if s == source else 0 for s in LAYERS[layer]], unit)


def stamp(tool, lists, prev=None, root=ROOT):
    """A built file's provenance: per list (the file's JSON key) its layer, levels and counts, and the
    sources used with their dates. Several tools writing one file (lineN.json) each add their lists
    to the block already there (`prev`)."""
    out = {"lists": dict((prev or {}).get("lists", {}))}
    for key, e in lists.items():
        out["lists"][key] = {"tool": tool} | e
    used = []
    for e in out["lists"].values():
        used += [s for s, c in zip(e["levels"], e["count"]) if c and s not in used]
    out["sources"] = {s: {k: v for k, v in (("title", SOURCES[s].title), ("date", dated(s, root)),
                                            ("attribution", SOURCES[s].attribution), ("datum", SOURCES[s].datum)) if v}
                      for s in used}
    return out


def attribution(*provs):
    """The credits for the sources the files used, once per holder: "Terrain, Trees: © IPR …"."""
    by = {}
    for p in provs:
        for s in (p or {}).get("sources", {}).values():
            what, _, holder = s.get("attribution", "").partition(": ")
            if holder and what not in by.setdefault(holder, []):
                by[holder].append(what)
    return " ".join(f"{', '.join(w)}: {h}." for h, w in by.items())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for layer, chain in LAYERS.items():
        print(f"{layer:11} " + " -> ".join(chain))
    print()
    for sid, s in SOURCES.items():
        if s.group or s.attribution:
            print(f"{sid:12} {dated(sid)[:60]:60} {s.title}")
