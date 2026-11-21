# SPDX-License-Identifier: AGPL-3.0-or-later
"""The survey's area layers (DTM ZPS OPL, by the type code that starts a layer's name) and what tools/dtm.py makes of
each (#703): a class of the world (CLASSES), or left out on purpose (LEFT_OUT, with why). A layer in neither stops the
build and names it: the survey's JVF 1.5.0.2 export appears from 2026-11-18 (#63), and a renamed code used to drop its
class from the world without a word (dtm.py skipped any code it did not know).

The layers of the 17 district packages of the five lines' snapshot (2026-11-18), counted 2026-11-21: 24 codes are
classes, 37 are left out."""

CLASSES = {
    "010000000503": "road", "010000001703": "road", "010000001103": "parking", "010000000903": "cycle",
    "010000000703": "sidewalk", "010000001303": "island", "010000002403": "tram", "010000005303": "platform",
    "010000005803": "deck", "010000006203": "tunnel", "010000006603": "underpass", "010000031203": "rail",
    "010000021503": "green", "010000020903": "green", "010000015203": "green", "010000018703": "paved",
    "010000018903": "paved", "010000005503": "paved", "010000016603": "stairs", "010000031503": "roof",
    "010000016803": "wall", "010000020303": "water",
    # (#555: the median strip between carriageways, tools/zps_medians.py; the road's associated area, paved)
    "010000001503": "median", "010000032003": "paved",
}

# the layers left out, as dtm.py has left them; a reason that names an issue is a layer to take in there
LEFT_OUT = {
    "010000000103": "Budova: buildings come from IPR's LOD2 (tools/geoportal.py)",
    "010000002803": "Pozemní lanová dráha: the funicular, no tram runs on it",
    "010000003503": "Speciální dráha: not ground the tram world draws yet",
    "010000005103": "Příkop, násep, zářez dopravní stavby: ditches and embankments of roads and tracks; the lidar has "
                    "their shape (#548's troughs)",
    "010000006003": "Portál tunelu: the tunnels' mouths are drawn from OSM and the structures (#682)",
    "010000006403": "Portál podchodu: the passages' mouths, as the tunnels'",
    "010000007003": "Mostní váha: a weighbridge",
    "010000007203": "Nádrž, zdrž se vzdouvacím objektem: water held by a weir; the rivers are `water`",
    "010000007603": "Stupeň: a step in a watercourse",
    "010000007803": "Stavebně upravené koryto: a built channel",
    "010000008003": "Meliorační příkop, žlab: a drainage ditch",
    "010000008503": "Protipovodňová zábrana: a flood barrier",
    "010000008703": "Suchá nádrž: a dry reservoir",
    "010000011603": "Zařízení vodovodní přípojky: a water connection's fitting",
    "010000012403": "Zařízení kanalizační přípojky: a sewer connection's fitting",
    "010000014203": "Plocha rekultivace: land being reclaimed",
    "010000015403": "Drobná sakrální stavba: a wayside shrine or cross",
    "010000015703": "Hřbitov: a cemetery's extent; its paths and green are their own areas",
    "010000015903": "Drobná kulturní stavba: a small monument",
    "010000016303": "Podezdívka: a building's plinth",
    "010000017303": "Rampa: a ramp; the stops' ramps are paved strips and platforms (#786)",
    "010000017503": "Terasa: a terrace (#663's terraces come from the lidar)",
    "010000017703": "Komín: a chimney",
    "010000017903": "Skleník: a greenhouse",
    "010000018103": "Zahradní bazén: a garden pool",
    "010000018303": "Patka, deska, monolit, pilíř: a footing, a slab or a pillar (a gantry's base in a road, #548)",
    "010000019303": "Čelo propustku: a culvert's head",
    "010000019703": "Podzemní objekt ZPS: underground, not on the ground",
    "010000020503": "Jezero: a lake",
    "010000020703": "Zemědělská plocha: farmland, the terrain from the lidar",
    "010000021103": "Les: a wood, the terrain from the lidar",
    "010000021303": "Hospodářsky nevyužívaná plocha: unused land, the terrain from the lidar",
    "010000031403": "Ostatní zastřešená stavba: a roofed structure",
    "010000033003": "Nádrž bez vzdouvacího objektu: a pond",
    "010000033103": "Hráz: a dam",
    "010000033803": "Vegetační mísa: a tree pit; pits in a sidewalk lie flush with it from the sidewalk's own area (#696)",
}


def summary(areas):
    """{class: {"areas": count, "m2": area}} of dtm.py's areas (outer ring less its holes; every level), for the build's
    report: tools/datadiff.py and a reader of the report see a class that shrank or went."""
    def m2(r):
        return abs(sum(x0 * y1 - x1 * y0 for (x0, y0, *_), (x1, y1, *_) in zip(r, r[1:] + r[:1]))) / 2 if len(r) >= 3 else 0.0
    out = {}
    for a in areas:
        c = out.setdefault(a["c"], {"areas": 0, "m2": 0.0})
        c["areas"] += 1
        c["m2"] += m2(a["r"]) - sum(m2(h) for h in a.get("h", ()))
    return {k: {"areas": v["areas"], "m2": round(v["m2"])} for k, v in sorted(out.items())}


def code(layer):
    """A layer's type code: its name after the package's prefix (`Dopravni#010000000503_Provozní…` -> 010000000503)."""
    return layer.split("#")[-1].split("_")[0]


def classify(layer):
    """The world's class for a survey layer, None for one left out on purpose; ValueError, naming it, for any other."""
    c = code(layer)
    if c in CLASSES:
        return CLASSES[c]
    if c in LEFT_OUT:
        return None
    raise ValueError(f"survey layer {layer!r}: its code {c} is neither a class nor left out "
                     f"(tools/zps_layers.py: add it to CLASSES or to LEFT_OUT with why, #703)")
