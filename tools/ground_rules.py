# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which ground places a ground change is tried on (#865): the fixed locality set, and the places of each rule.

A ground PR runs `ground_place.py --locality` (the set below with one ring of tiles and with two: a rule that reads
past the ring shows there) and `ground_place.py --rule R` for the rules its diff changes; `--all --rings` runs once a
batch, with the rebuild (#757). The places grew from 36 to 48 during #812 and its proof to 2 h 10 min of the queue
a round; a rule's places and the set take minutes.

- LOCALITY: one place per kind of defect #812 found reading past the ring (its "What a tile's ground reads" in
  docs/knowledge.md). A new kind adds its place here and a unit test that reproduces it without one.
- RULES: a rule's code (functions, classes and constants of the ground tools, as module.name patterns) and the
  places that guard it (data/truth.json groundPlaces). What is in no rule (`build`, the weld, the partition's frame)
  reaches every place: the set, places chosen by hand, and the batch's --all.

    python -I tools/ground_rules.py tools/ground_mesh.py ...   # the rules a diff against origin/main changes
Stdlib only: tools/tiers.py reads it under `python -I`.
"""
import ast
import fnmatch
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The tools a place's build runs (ground_mesh.build and what it imports at build time): a change to one is a ground
# rule's, tried on places (tools/tiers.py).
TOOLS = ("tools/ground_mesh.py", "tools/ground_partition.py", "tools/bed_surface.py", "tools/wall_lines.py",
         "tools/covers.py", "tools/ties.py", "tools/ipr_dtm.py", "tools/ipr_pits.py")

# (name: a place of groundPlaces, or {line, at} for one that is not; the kind of defect it showed, #812)
LOCALITY = {
    "rasinovo-quay": "water levels from the box's corner, banks from where a ring starts; bed edges' caps",
    "vysehrad-wall-over-the-ramp": "an island cut open by the water raster's extent; OSM's water from two corners",
    "hlavni-nadrazi-under-the-magistrala": "stacked walls' sides, the cover's cut lattice, half-mm vertices",
    "stairs-beside-a-building": "thin strips from the whole box's terrain, where a ring starts",
    "street-over-an-underpass": "ties by an STRtree's order, tile_faces' lines",
    "lattice-cell": "the cover's union for the whole box: needles, nodes by grouping",
    "sidewalk-under-a-road-wall": "lowered kerbs: the first road corner by the corners' order",
    "line22_-943_418": {"line": "22", "at": [-943.2, 417.6],
                        "why": "GEOS's hidden grid: the strips' 1 mm grid given to the plots, a union snap-rounded by its pairing"},
}

RULES = {
    "water": {
        "what": "water levels, banks and the cuts between them (#697, #812)",
        "code": ["ground_partition._wet", "ground_partition.osm_water", "ground_partition.water_cuts",
                 "ground_partition.bank_samples", "ground_partition.wet_cells", "ground_partition.WaterLevels",
                 "ground_partition.WATER_*", "ground_mesh.WATER_*", "ground_mesh.off_cuts"],
        "places": ["rasinovo-quay", "sidewalk-on-a-quay-wall", "letna-road-wall", "vysehrad-wall-over-the-ramp",
                   "vysehrad-tunnel-mouths"],
    },
    "walls": {
        "what": "walls: the survey's lines, faces and strips, a wall's sides and its foot and top (#697, #765, #770, #786)",
        "code": ["wall_lines.*", "ground_mesh.hold_at_walls", "ground_mesh.wall_areas", "ground_mesh.outline_edges",
                 "ground_mesh.turning", "ground_mesh.out_of", "ground_mesh.own_side", "ground_mesh.own_outline", "ground_mesh._sides",
                 "ground_mesh.across_outline", "ground_mesh.wall_width", "ground_mesh.two_sided", "ground_mesh.wall_like",
                 "ground_mesh.wall_face", "ground_mesh.standing", "ground_mesh.thin_walls", "ground_mesh.off_the_smear",
                 "ground_mesh.ring_segments", "ground_mesh.snap_to_walls", "ground_mesh.step_walls", "ground_mesh.is_wall",
                 "ground_mesh.WALL*", "ground_mesh.LOW_WALL", "ground_mesh.THIN_WALL",
                 "ground_mesh.SIDES_*", "ground_mesh.SMEAR_*"],
        "places": ["rasinovo-quay", "krejcarek-ramp", "lattice-cell", "letna-road-wall", "ohrada-cutting-walls",
                   "wall-end-in-a-path", "sidewalk-under-a-road-wall", "sidewalk-on-a-quay-wall", "branik-platform-ramps",
                   "cerny-kun-platform-wall", "modranska-skola-ramp", "na-vapence-garage-ramp", "modrany-viaduct-ramps",
                   "garden-beds", "zizkov-wall-at-the-kerb", "motol-wall-at-the-kerb", "wall-above-a-lower-walkway",
                   "hlavni-nadrazi-under-the-magistrala", "motol-bridge-parapets"],
    },
    "kerbs": {
        "what": "kerbs: raised edges, lowered kerbs, belts, parking bays (#606, #638, #800)",
        "code": ["ground_mesh.lowered_kerbs", "ground_mesh.lowered_heights", "ground_mesh.kerb_walls",
                 "ground_mesh.belt_kerbs", "ground_mesh.lowest_at", "ground_mesh.meet_raised", "ground_mesh.MEET*",
                 "ground_mesh.BELT_SIDE"],
        "places": ["vinohradska-parking-bay", "narodni-mikulandska-corner", "plzenska-bend-kerb", "zizkov-wall-at-the-kerb",
                   "vysehrad-wall-over-the-ramp", "motol-wall-at-the-kerb", "repy-parking-kerb", "vystaviste-flush-parking",
                   "verge-by-a-car-park-no-wall", "wall-above-a-lower-walkway", "belohorska-plain-kerb", "yard-at-a-sidewalk",
                   "sidewalk-under-a-road-wall", "vinohradska-raised-corridor", "vinohradska-crossing", "motol-platform",
                   "hlusickova-platforms", "kralovka-lawn-at-a-sidewalk"],
    },
    "beds": {
        "what": "track beds: their surface, edges and rails in the street (#539, #548, #606, #676)",
        "code": ["bed_surface.*", "ground_mesh.rail_top", "ground_mesh.bed_edges", "ground_mesh.cut_back",
                 "ground_mesh.rail_lines", "ground_mesh.across", "ground_mesh.on_rails", "ground_mesh.rail_band",
                 "ground_partition.bed_samples", "ground_partition.lift_at", "ground_partition.bed_pieces",
                 "ground_mesh.BED_*", "ground_mesh.RAIL_*"],
        "places": ["bertramka-track-level", "marjanka-track-level", "belohorska-median", "ballast-bed-off-the-route",
                   "marianske-hradby-upper-track", "vinohradska-raised-corridor", "vinohradska-crossing",
                   "zizkov-depot-paving", "rasinovo-quay"],
    },
    "stairs": {
        "what": "flights of stairs and ramps: their steps, sides and ends (#447, #653, #786)",
        "code": ["ground_mesh.flight", "ground_mesh.climbs", "ground_mesh.StairsHeights", "ground_mesh.stairs_sides",
                 "ground_mesh.STAIRS*", "ground_mesh.survey_edges", "ground_mesh.RISER*"],
        "places": ["stairs-reversed-ramp", "stairs-beside-a-building", "stairs-not-there", "stairs-belvedere-wall",
                   "stairs-dobeska", "krejcarek-ramp", "branik-platform-ramps"],
    },
    "platforms": {
        "what": "platforms: level along the track, their walls and kerbs (#776, #786)",
        "code": ["ground_mesh.platform_planes", "ground_mesh.PLATFORM*"],
        "places": ["krejcarek-platform", "motol-platform", "hlusickova-platforms", "branik-platform-ramps",
                   "modranska-skola-ramp", "cerny-kun-platform-wall"],
    },
    "structures": {
        "what": "what the ground meets at structures: decks, abutments, tunnels, covers over passages (#742, #763, #771, #783, #788, #824)",
        "code": ["covers.*", "ground_mesh.span_decks", "ground_mesh.rock_tunnels", "ground_mesh.in_the_rock",
                 "ground_mesh.portal_masonry", "ground_mesh.off_the_hill", "ground_mesh.bed_ends", "ground_mesh.abutments",
                 "ground_mesh.off_the_deck", "ground_mesh.under_decks", "ground_mesh.DECK_EDGE", "ground_mesh.fit_mouths",
                 "ground_partition.route_decks", "ground_mesh.ABUT_*", "ground_mesh.TUNNEL_*", "ground_mesh.PORTAL_*",
                 "ground_mesh.BRIDGE_NEAR", "ground_mesh.MOUTH_FIT"],
        "places": ["hlavni-nadrazi-under-the-magistrala", "vysehrad-tunnel-mouths", "street-over-an-underpass",
                   "krejcarek-abutment", "modrany-viaduct-ramps", "slanska-street-under-a-bridge",
                   "narodni-divadlo-bridgehead", "motol-bridge-parapets"],
    },
    "plots": {
        "what": "plots, lawns, yards and beds in a sidewalk: their heights, terraces, pits and thin strips, a lawn at a raised edge (#638, #663, #696, #738, #764, #770)",
        "code": ["ground_mesh.terraces", "ground_mesh.pits", "ground_mesh.bare_holes", "ground_mesh.over_lidar",
                 "ground_mesh.beside", "ground_mesh.meet_lidar", "ground_partition.plot_height", "ground_partition.plot_pieces",
                 "ground_partition.thin_parts", "ground_partition.thin_strips", "ground_mesh.TERRACE*",
                 "ground_mesh.PIT*", "ground_partition.PLOT_*"],
        "places": ["garden-beds", "yard-at-a-sidewalk", "garden-edgings", "bed-in-a-sidewalk", "lattice-cell",
                   "verge-by-a-car-park-no-wall", "vystaviste-flush-parking", "wall-end-in-a-path", "stairs-beside-a-building",
                   "kralovka-lawn-at-a-sidewalk"],
    },
    "lidar-pits": {
        "what": "IPR's pits under the survey's streets, filled from their rim in every reader of the raster (#867)",
        "code": ["ipr_pits.*", "ipr_dtm.IprDtm", "ipr_dtm.FILLS"],
        "places": ["taboritska-road-pit", "platnerska-road-pit", "belohorska-sidewalk-pit", "stairs-beside-a-building",
                   "yard-at-a-sidewalk", "na-vapence-garage-ramp"],
    },
}


def definitions(src):
    """{name: its source} of a module's top-level functions, classes and assigned names (a class whole, with its
    methods): what a rule's code patterns name."""
    tree, out = ast.parse(src), {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.Assign):  # (A = ..., and A, B = ...)
            names = [n.id for t in node.targets for n in ([t] if isinstance(t, ast.Name) else getattr(t, "elts", []))
                     if isinstance(n, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
        else:
            continue
        seg = ast.get_source_segment(src, node)
        for n in names:
            out[n] = seg
    return out


def changed(old, new, module):
    """The module.name of what differs between two sources of one module: changed, added or gone."""
    a, b = definitions(old or ""), definitions(new or "")
    return sorted(f"{module}.{n}" for n in set(a) | set(b) if a.get(n) != b.get(n))


def rules_of(names):
    """(the rules whose code the names fall in, the names in no rule)."""
    hit, none = [], []
    for n in names:
        rs = [r for r, v in RULES.items() if any(fnmatch.fnmatchcase(n, p) for p in v["code"])]
        hit += [r for r in rs if r not in hit]
        if not rs:
            none.append(n)
    return [r for r in RULES if r in hit], none


def places_of(rules):
    """The places of the rules, each once, in the rules' order."""
    out = []
    for r in rules:
        out += [p for p in RULES[r]["places"] if p not in out]
    return out


def git(*args, root=ROOT):
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, encoding="utf-8")
    return r.stdout if r.returncode == 0 else None


def diff(paths, base="origin/main", root=ROOT):
    """What the ground tools among paths changed against base's merge base: [module.name], in the files as they are
    now (uncommitted changes too). None where git cannot say (no merge base)."""
    mb = (git("merge-base", base, "HEAD", root=root) or "").strip()
    if not mb:
        return None
    out = []
    for p in paths:
        if p not in TOOLS:
            continue
        old = git("show", f"{mb}:{p}", root=root) or ""
        try:
            with open(os.path.join(root, p), encoding="utf-8") as f:
                new = f.read()
        except OSError:
            new = ""
        out += changed(old, new, os.path.basename(p)[:-3])
    return out


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    names = diff([p.replace(os.sep, "/") for p in argv] or list(TOOLS))
    if names is None:
        print("ground_rules: no merge base with origin/main", file=sys.stderr)
        return 2
    rules, none = rules_of(names)
    print("changed:", ", ".join(names) or "nothing")
    print("rules:", ", ".join(rules) or "none", f"({len(places_of(rules))} places)")
    if none:
        print("in no rule:", ", ".join(none))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
