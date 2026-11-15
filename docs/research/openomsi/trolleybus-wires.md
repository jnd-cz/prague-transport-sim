# openOMSI: how trolleybus wires are built and drawn (#520)

openOMSI read at commit `b2dc640b4db64a09ddfc0d00b8e78c463c81c842` (2026-11-12), licence **AGPL-3.0-only**. Paths
below are under `crates/`. Our side: main at 619e0e9. Prague counts from our extract `raw/osm/praha.osm.pbf` (cut
from `czech-republic-261104.osm.pbf`) and the 17 districts' ZPS in `raw/dtm/`, counted with pyosmium and sqlite on
2026-11-13. The poles, dewiring, frogs' switching, sections, arcs and drives are in
[vehicles-and-wire.md](vehicles-and-wire.md) ("Trolleybus gear", "Supply"); this note is the wire as a thing in the
world, asked by the user (2026-11-13): "how does the project draw trolleybus wires which I would like to have
eventually implemented since Prague has real trolleybus lines".

## How the network is authored

- **`trolley.txt` beside the map's `global.cfg`** (`omsi-trolley/src/wire.rs:319-561`, `docs/TROLLEYBUS.md`): written
  by hand. A `[trolley_span]` is the **centre line of the pair** as points `p x y z`, ordered so that the positive
  wire is on the right; one point per hanger and bend, the sag "is in the points". `spacing` 0.6 m by default
  (0.2–2.0). Sections, `[trolley_switch]` (a frog: a node where exactly three span ends meet) and
  `[trolley_insulator]` blocks complete it. Ends within `JOIN` 1.2 m become one node at their mean (`wire.rs:279`,
  `build_nodes` 563-671); spans of different sections meeting give a 0.8 m insulator by themselves.
- **Read off an OMSI 2 map's wire splines** when there is no `trolley.txt` (`omsi-scene/src/trolley_derive.rs`):
  a spline type whose profile has exactly two strips ≤ 0.2 m wide, ≥ 3 m high, ≤ 0.25 m thick and 0.2–1.2 m
  apart is a pair (`wire_profile`, 16-39). Each such spline is sampled every 3 m and every 1.5° of turn, at most
  600 points (68). A branch whose end lies on another span's middle cuts that span there (`split_t_junctions`,
  87-188: 2 m margin, ends at another height left alone); three ends within 1.2 m are a frog worked by current,
  plate 9 m before it (271). The result is written as `trolley.txt` text and parsed the same way. The map draws
  these wires itself (`drawn_by_map`); Bronitsyn's are 2 × 2 cm strips at 5.04–5.06 m, 0.52 m apart
  (`docs/TROLLEY_MODS.md`).
- **`catenary.cfg`** in a map's `transport` folder (`omsi-transit/src/electric.rs`): the same spans for trams,
  railways and trolleybuses (`wires 2`), `height 5.5` when a point has no z. Read for the supply only
  (`omsi-app/src/rail_drive.rs:517`); nothing draws it.
- **Nothing is generated.** A map with neither file nor wire splines has no trolleybus wire; the map generator
  (`omsi-scene/src/mapgen.rs`) places none. Hangers, span wires, masts and frogs' hardware are the map's own scenery
  objects (Bronitsyn: 98 hanger and bend objects, street-lamp poles as masts).

## How it becomes geometry

- **Two wires from one centre line** (`wire.rs:57-68`, `Span::wire_at` 91-99): each point gets a horizontal
  right-hand vector **mitred** at a bend, the mean of the two segments' normals scaled by 1/cos of half the bend
  (capped at 2×), so both wires stay `spacing` apart through a bend with no jump.
- **Offsets shared at joints** (`share_offsets_at_nodes`, 706-722): every span leaving a node takes the offset
  direction of one reference end (a frog's toe), so the wires of a frog leave from one point whatever way the spans
  were drawn.
- **Curves are straight pulls** between the points as given: a hand-written span has a point at each hanger, a
  spline-derived one every 3 m. No stagger (a shoe's groove holds the wire), no computed sag, no catenary curve.
- **Crossings with other wires** (a tram wire, another pair) are not modelled: two spans that cross without a common
  node are not connected, and a crossing at another height never makes a junction (test at
  `trolley_derive.rs:343`). No crossing piece is drawn.

## How it is drawn

`omsi-scene/src/trolley_view.rs`, built when the first trolleybus of a map is placed, left in the scene for later
buses (`scene.trolley_wire_drawn`), skipped when the map draws its own wire:

- each wire is a **tube of radius 8.5 mm** ("the real one is 6 to 7 mm"), **5 sides**, a ring of vertices per point
  with smooth normals (`tube`, 18-49): 10 triangles per segment and wire, 20 per segment of the pair;
- spans are grouped by their middle point into **160 m cells**, one mesh and one instance per cell (113-145);
- one opaque, lit material, RGB (0.20, 0.17, 0.15), double-sided; the wires **cast no shadow**;
- **no LOD and no distance of its own**: a cell is dropped only by the engine's frustum test, its screen-size rule on
  the cell's bounding sphere and `performance_maxObjDist` (`omsi-render/src/passes/cull.rs:150-206`). Nothing keeps
  a far wire a pixel wide (the rain streaks have that rule, the wire does not);
- **frogs** (spline-derived networks, or `OMSI_DEBUG_TROLLEY`): a box of two 0.6 m tubes of r 45 mm ±0.3 m apart on
  0.35 m hangers, a 1.8 m tongue (r 22 mm, amber) turned to the way set, a corona 0.75 m above, green straight and
  amber to the branch (148-177, 368-372);
- **section insulators**: two light grey tubes of r 28 mm, as long as the dead stretch (at least 0.5 m), at nodes
  between sections (178-191).

| | openOMSI | ours, tram wire |
|---|---|---|
| contact wire height | in the points (Bronitsyn 5.05 m; `catenary.cfg` default 5.5 m) | 5.34 m over the rails (`src/models.js:306`) |
| wires and spacing | two, 0.6 m (spline maps 0.52 m) | one per track |
| supports | the map's objects | spans every 12, 18, 25, 32 m (R < 50, < 100, < 200 m, more) |
| drawn as | tubes r 8.5 mm, 5 sides, lit | `LineSegments`, one pixel, unlit `0x222222` |
| triangles per 30 m of pair | 20 (one pull) to 200 (3 m sampling) | none (2 vertices per segment) |
| distance cut | engine's culling of a 160 m cell | none: one object per line |

## What we draw for trams

`buildCatenary` (`src/world.js:1969-2095`): the contact wire 5.34 m over every track of the line's data, every
second point of `t.smooth`, no stagger. Span stations every 12–32 m by radius (2017-2021); `anchor` (1997-2015) puts
a pole at the kerb outside the carriageway, a rosette on a facade within 5.5 m behind it, a bracket arm from the
near side where the far anchor is missing or over 9 m beyond the outer track (2039-2061). The span wire is drawn
at 6.34 m over the rails (`za - 0.4`; the comment at 2047 says 6.74), droppers down to 5.6 m over each track within
6 m. Poles (`CylinderGeometry` 0.12/0.17 × 7.4 m, 6 sides) and rosettes are instanced; wires and droppers are one
`LineSegments`. Supports from data wait in #277; the height under overpasses in #71; the module in #422. Nothing
reads `trolley_wire`: `tools/build_line.py:1110-1154` keeps a road's width, lanes and one-way, not the wire.

## Prague data for trolleybus wires

- **OSM `trolley_wire`** on street ways: 415 ways `yes` (29.8 km), 2 `forward`, and the directional keys
  `trolley_wire:forward` (7 yes, 13 no) and `:backward` (19 yes, 6 no); 442 wired ways, **31.2 km of street centre
  line**. `trolley_wire=no` is on 335 ways (23.3 km), 19.7 km of them on the routes: their stretches without wire.
- **Routes:** 10 `route=trolleybus` relations (DPP), lines **51** Hradčanská–Bořislavka, **52** Na Knížecí–
  Jinonice, **53** Stadion Strahov–Karlovo náměstí, **58** Miškovice–Palmovka, **59** Letiště–Nádraží Veleslavín:
  675 ways, 49.0 km, of it 29.0 km wired. 108 wired ways (5.9 km) are in no route. The relations give the turns a
  bus makes at a junction, which the way tags do not: a frog belongs to a turn some route takes.
- **Shared with trams:** 5.1 km of wired street lies within 8 m of tram track: Evropská 3.4 km (trams 20, 26 and
  91), Zenklova 0.75 km. A wired street crosses tram track at **23 places** (merged within 30 m).
- **Our lines:** only **line 9** meets a trolleybus wire: 140 m within 60 m of its track (náměstí Kinských 74 m,
  Holečkova 67 m, trolleybus 53) and one crossing of the two wires. Lines 17, 22 and 23: none.
- **Supports:** `power=catenary_mast` 2,797 nodes in Prague (13 with `operator=DPP`), of them 17 within 15 m of a
  wired street and over 20 m from tram track: OSM does not map the trolleybus supports.
- **No wire anywhere else:** no `power=line`, `minor_line` or `cable` at 600 or 750 V or run by DPP (the three DC
  ones are 3 kV railway feeders, the `line=busbar`/`bay` ways 110 kV substations). The ZPS (KR and OPL, 17
  districts) has no overhead-line layer; its only electric layer is `Trasa_odběrného_elektrického_zařízení` (692
  service lines). DPP's own supports are in the current DTM's TI set (`PodperneZarizeni`), which #277 snapshots for
  the tram.

## How we would draw them: take or not

1. **The pair as one centre line with a spacing, mitred at bends and sharing its offset at joints.** **Take the
   rule** (rewritten): the pair from the street's wired direction, the two wires always `spacing` apart, frogs
   without a jump.
2. **Where the centre line comes from:** openOMSI needs an author; we have the tags. **Ours:** `build_line.py`
   keeps `trolley_wire`, `:forward` and `:backward` on its roads; the game puts one pair per wired direction over its
   outer lane (the DTM carriageway's edge where the street is surveyed, OSM width and lanes else). Height and
   spacing come from a source or the user into `data/truth.json`, not openOMSI's 0.6 m or our tram's 5.34 m.
3. **Straight pulls between supports.** **Take**: the pair as chords between the span stations `buildCatenary`
   already places (12–32 m by radius), the polygon a curve's wire makes in the street. No sag, as openOMSI.
4. **Supports:** openOMSI leaves them to the map. **Ours:** on a tram street the pair hangs from the tram's span
   wires (droppers to the pair, as to the tram wire); elsewhere `anchor` along the street instead of the track
   (pole at the kerb, rosette on a facade, bracket arm); from #277's data where it lists DPP supports.
5. **Frogs and crossings as objects.** **Take the idea**, our own meshes, instanced: a frog where a route's turn
   leaves a wired way for another, an insulated crossing piece where the pair crosses a tram wire (line 9: one).
   Not the frog's lamp: a Prague source decides whether there is one.
6. **Tubes of 8.5 mm, 160 m cells.** **Not taken**: the trolleybus wire is drawn as our tram wire is (`LineSegments`,
   one pixel, nothing to cull); a later look for both wires (lit, a real width near, a pixel far) is one change for
   both, with `tools/frametime.py`.
7. **Reading wire splines, `trolley.txt`, `catenary.cfg`.** **Not taken**: no OMSI content and no hand-written
   network; the wire comes from data like the track.

## Proposed issue

**Trolleybus wires drawn from OSM `trolley_wire`: pairs over the bus lane, on the tram's spans or their own, frogs and
crossings with the tram wire** (`lane:world`, W4 Structures and scenery, blocked by #422 and #277; feeds #39).
- Now: no trolleybus wire; `tools/build_line.py` drops `trolley_wire`. Prague: 31.2 km of wired street, routes 51,
  52, 53, 58, 59; on our lines line 9 at náměstí Kinských (140 m, one crossing with the tram wire).
- What: the build keeps the tags per road and direction; the game draws a pair per wired direction over the outer
  lane, height and spacing from `data/truth.json` (a cited source or the user), chords between support stations,
  offsets mitred and shared at joints; hung from the tram's spans on shared streets, on its own poles, rosettes or
  arms elsewhere; frogs at the turns the route relations take; an insulated crossing piece over each tram crossing;
  the F8 overlay says which supports and offsets came from a rule.
- Done when: line 9's náměstí Kinských shows the pair and the crossing in their places against the orthophoto and a
  photo; every line's build reads the tags; the crossing's place is available to `lane:sim` for SIG-W6 and D12-V7
  (coast under it, 15 km/h).
- Checks: `tools/test_build_line.py`; `lint,surfaces,crossing,canted` on line 9; a smoke drive on line 9
  (`--checks u3 --seeds 1`); screenshots main vs branch; `tools/frametime.py`.
- Questions for the user: the pair's height and spacing in Prague; whether the pair is centred over the outer lane;
  whether trolleybus frogs and crossings carry lamps or signs.
