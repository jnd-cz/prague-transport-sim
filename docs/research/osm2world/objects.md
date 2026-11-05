# OSM2World: placed objects (street furniture, signs, barriers, trees) (#15)

OSM2World read at commit `1d31c252cbef964b489a55e5fb8242ee253375b1` (2026-11-02), MIT. Paths below are
under `core/src/main/java/org/osm2world/`. Our side: main at 595514a. Tag counts are from our Prague
extract (`raw/osm/praha.osm.pbf`, snapshot of 2026-10-22), counted with pyosmium on 2026-11-05. Feeds #14
(the feature layer) and #252 (IPR street furniture with LODs).

## What OSM2World does

**One class per object, all procedural** (`world/modules/StreetFurnitureModule.java`, `applyToNode`):
a node's tags pick a class, the class draws boxes, columns and extrusions with a material from the style.
Sizes are constants, overridden by `height`, `width`, `seats`/`capacity`; `material` and `colour` recolour.

| tags | object, default size (m) | LOD |
|---|---|---|
| `amenity=bench` | seat at 0.5, 0.5 deep, backrest 0.5 high (none with `backrest=no`), 0.5 per seat (4 seats: 2.0 wide), wood | 3–4 |
| `amenity=waste_basket` | basket 0.5 high, r 0.2, on a 1.2 m post; on a wall or pole at 0.6 | 3–4 |
| `highway=street_lamp` | pole r 0.16 → 0.08, 5.0 overall with a 0.8 m head, steel | 2–4 |
| `man_made=pole` | column 5.0, r 0.1 | 2 (≥ 10 m) or 3–4 |
| `man_made=flagpole` | 10.0, r 0.15, flag from `flag:*` | |
| `advertising=column` / `billboard` | column 3.0; board 4 × 3.5 on supports | |
| `highway=bus_stop` (not on a road way) | pole 3.0, sign 0.7 × 0.4, timetable at 1.2 | 3–4 |
| `amenity=post_box`, `telephone` (with `operator`/`brand`) | 0.8 / 2.0; booth 2.1 × 0.8 | |
| `amenity=recycling` + `recycling_type=container`, `grit_bin`, `vending_machine`, `parcel_locker`, `clock` + `support=wall`, `man_made=street_cabinet`, `emergency=fire_hydrant` + `fire_hydrant:type=pillar` (1.0), `tourism=information` + `information=board`, `amenity=table`, crosses, obelisks, swings | | |

Other modules: `BarrierModule.java` (bollards every 2 m along a `barrier=bollard` way; guard rail 0.75 m
high, posts every 4 m, German B profile 0.303 m; jersey barrier 1.145 × 0.82 in 3.0 m elements with 0.3 m
gaps; fences by `fence_type`; chains; hedges), `BicycleParkingModule.java` (`bicycle_parking=stands`:
(capacity + 1) / 2 stands 1.0 m apart, each 1.0 long, 0.7 high), `MastModule.java` (mobile phone masts),
`TreeModule.java`, `traffic_sign/` (below). Shelters, railway signals and traffic lights are not drawn.

**Orientation** (`world/modules/common/WorldModuleParseUtil.parseDirection`): `direction` in degrees or
cardinal letters (`N`, `NNE` …), clockwise from north (`VectorXZ.fromAngle`: `(sin a, cos a)`, Z north).
The object's front faces that way. Without the tag nearly every object faces south (default `PI`); street
cabinets and obelisks use 0. Nothing turns an object to the street it stands at.

**Attachment** (`world/attachment/AttachmentUtil.getCompatibleSurfaceTypes`, `AttachmentConnector.java`,
`world/data/NoOutlineNodeWorldObject.java`):
- `support=wall` (with `level`: `wall<level>` first), any other `support=*` value is a surface type of its
  own (`pole`, `street_lamp` …); `location=roof|rooftop` gives `roof`; `level` alone gives `floor<level>`.
- Objects publish surfaces: a pole (`"pole"`), a lamp's post (`"street_lamp"`), a bus stop's post, walls.
- A connector that may move searches surfaces within 10 m horizontally (0.01 m when it must not move);
  vertical surfaces take it at the object's preferred height (a waste basket 0.6 m).
- Attached, the object faces the surface's normal and draws no post of its own
  (`NodeWorldObjectWithOptionalSupports`: bins, billboards, boards, vending machines); free, it stands on
  its post and faces `direction`.

**Traffic signs** (`world/modules/traffic_sign/TrafficSignModule.java`, `TrafficSignGroup.java`,
`TrafficSignType.java`):
- `traffic_sign=*` on a node of a road: the sign group stands one road width (`Road.getWidth()`, the whole
  width, not half) off the centre line, on the driving side for `forward`; `side=left|right|both` overrides.
- Facing: `direction` (angle), else `traffic_sign:forward|backward` / `direction=forward|backward` against
  the way, else for `highway=stop|give_way` away from the nearest junction, else facing traffic.
- `traffic_sign=*` on a way: signs at its start (and end) unless the neighbouring way has the same sign.
- Several signs stack on one post, 0.1 m apart. Default height 2.6 m and post r 0.038 come from the style
  (`defaultTrafficSignHeight`, `standardPoleRadius`); per sign `trafficSign_<ID>_numPosts|defaultHeight`.
- Destination signs from `type=destination_sign` relations: text, colours and arrow drawn per instance.

**Trees** (`TreeModule.java`):
- `natural=tree` nodes, `natural=tree_row` ways, `natural=wood`, `landuse=forest|orchard`, `landcover=trees`.
- Size (`TreeDimensions.fromTags`): `height`, `est_height`, `diameter_crown`, trunk `diameter` (plain
  numbers in mm) or `circumference` / π. Missing: height = crown × 2, or trunk × 30 × 2, else 10 m
  (20 m in a forest); crown = height / 2.
- Leaf type from `leaf_type`/`wood`, else a coin flip; `leaf_cycle`; `species` (apple for orchards).
- A tree row gets a tree every 4 m (`equallyDistributePointsAlong(4, …)`, a TODO says "derive from tree
  count"), minus those within 10 m of a mapped `natural=tree` node on the row.
- Forests: `treesPerSquareMeter` = 0.02 (style), size × 0.5–1.25 at random.
- Randomness seeded by position (`new Random(x * 10 + z * 10000)`); identical parameters share one model
  (`existingModels`), so trees are instances.
- Near: trunk column (0.5 of height broad-leaved, 0.3 conifer) and a cylinder or cone crown; with
  `useBillboards`, a cross of two textured quads (`common/WorldModuleBillboardUtil.java`).

**Models** (`scene/model/`, `output/gltf/GltfModel.java`, `style/PropertyStyle.java`,
`world/modules/ExternalModelModule.java`):
- An instance is `InstanceParameters(position, direction, height, color, lodRange)`; a glTF model is turned
  by direction + 180°, its scale is not applied (`// TODO provide scale`).
- External glTF models are named in the style (`model_CAR = …car.gltf; …car_hatchback.gltf`, one picked
  at random), or per OSM element by its id in the style, or from the `3dmr` tag (3D Model Repository,
  local directory or download).
- The style's conventions (default-style README): models face +Z; a material coloured FF00FF is the
  placeholder replaced by the instance's colour.
- Every mesh carries a LOD range (LOD0–LOD4); furniture is LOD3–4.

## What we do

- **Signals and track signs** (`src/game.js` `_mount`): at the kerb on the right when it is within 6.5 m
  (`route.kerbAt`, the catenary's anchor search), else hung from the nearest span wire (board top 5.04 m
  over TOR, beside the tram's clearance), else at a kerb within 12 m, else 2.6 m off the track.
- **Stop signs**: the DTM archive's sign beside the track (`tools/dtm_points.py --signs`,
  `tools/build_line.py` "stop signs": truth, dtmpoints, OSM in that order).
- **Shelters**: `tools/platforms.py` keeps OSM `shelter=yes`; `src/game.js` `makeShelter` is a glass box at
  the back of the platform.
- **Street detail** (`src/world.js` `buildStreetDetail`): DTM points (`tools/dtm_points.py` `KINDS`), one
  instanced mesh per kind: covers and caps as discs, hydrants as posts, gutter inlets turned along the
  nearest road segment, the rest turned by a hash of the position. `dtm_points.py` also reads poles,
  lamps, signals, traffic sign carriers, clocks, phone booths; none of them is drawn.
- **Trees** (`tools/geoportal.py` `trees`, `src/world.js` `buildTrees`): the IPR register (deciduous,
  conifer, bush, container) and tree rows sampled every 9 m; one plant per ~1.5 m cell; crowns shrink
  until clear of facades, are pruned next to the tracks; drawn as instanced crowns. Size is random per
  plant (0.75–1.35), not from data.
- **Model axes**: vehicles face +Z (`docs/assets-inventory.md`); the furniture lab's shelters have their
  back at −Z and poles attach at +X (#252).

**OSM in Prague** (nodes, plus ways where they matter): `highway=street_lamp` 21,324 (1,712 with
`support=pole`, 935 with `direction`), `natural=tree` 21,709 and 2,967 `tree_row` ways, `amenity=bench`
19,569 (5,111 `material=wood`, 672 with `direction`), `waste_basket` 6,411, `recycling` 4,845,
`tourism=information` 4,922, `public_transport=platform` 4,434 + 2,369 ways (`shelter=yes` 3,112,
`bench=yes` 3,351), `bicycle_parking` 2,692, `parcel_locker` 2,224, `vending_machine` 2,167,
`barrier=bollard` 2,082 + 457 ways, `post_box` 1,010, `emergency=fire_hydrant` 649, `flagpole` 600,
`advertising=billboard` 543, `clock` 344, `man_made=street_cabinet` 186 + 911 ways,
`advertising=column` 75, `traffic_sign=*` 493, `barrier=guard_rail` 551 ways.

## Ideas: take or not

1. **OSM as a feature source for what the DTM lacks.** **Take, reimplement** in a build tool feeding #14:
   benches, waste baskets, bicycle stands, bollards, advertising columns, post boxes, parcel lockers,
   recycling containers. The DTM is first where it has the kind (lamps, poles, hydrants, signals, stop
   signs: surveyed); OSM only fills kinds the DTM does not record. Before OSM lamps fill anything, measure
   them against the DTM's lamps along lines 17 and 22 (matched within 2 m, counts per 100 m), as #277 does
   for the two DTM layers.
2. **Orientation from `direction`, else from the street.** **Take the tag parsing** (compass degrees or
   letters, clockwise from north; front faces it: 672 benches have it). **Not the south default**: a
   bench, bin or board without `direction` turns to the nearest footway or street segment, as our gutter
   inlets do. Each guess goes in the layer with `heading_src: "street"` so the review can list it.
3. **Attachment as data.** **Take the idea** for #14's schema: a feature has a mount (`ground`, `wall`,
   `pole:<id>`, `span:<s>`), searched within a radius per kind (OSM2World: 10 m), with a preferred height;
   mounted it faces the surface's normal and draws no post. Our `_mount` and the catenary's wall rosettes
   are two cases of it; `support=wall|pole|street_lamp` and the DTM's "on building" codes (605251, 605241,
   606561) fill it.
4. **Traffic sign placement from OSM.** **Not taken**: 493 signed nodes in Prague, placed one road width
   off the centre line. The DTM's surveyed sign carriers (605270) are the candidate source; the facing rule (towards the
   traffic the sign is for, `forward`/`backward` against the way) is the same as ours.
5. **Tree rows minus mapped trees.** **Take the rule**: OSM2World drops a row's implicit tree within 10 m
   of a mapped one. Our 1.5 m cell keeps a row sample that lies 1.5–9 m from a register tree; how often
   both are one tree is not measured. Count such pairs per line against the orthophoto, then drop row
   samples within half the row spacing (4.5 m) of a register tree if they are.
6. **Tree sizes from data.** **Take the tag mapping** (`height`, `diameter_crown`, `circumference`, trunk
   `diameter` in mm; height = 2 × crown when only one is known) for a source that has them; first list
   which attributes the IPR register returns (`geoportal.py` asks for `*`, keeps only `kod_vp` and
   `kod_drevin`). The 30 × trunk ratio is unmeasured: not taken.
7. **Procedural default sizes** (bench 0.5 m per seat, lamp 5 m, bin 0.5 m). **Not taken**: #252 has the
   IPR mobiliář's real dimensions.
8. **Bicycle stands from capacity**: (capacity + 1) / 2 stands, 1.0 m apart. **Take** with #252's stand.
9. **Model conventions**: one model per parameter set, instanced; LOD range per mesh; FF00FF placeholder
   for an instance colour. **Take the placeholder colour** for #252's GLBs (one shelter model, the colour
   per place); the rest we already do (instanced meshes; near/middle/far in #252).
10. **Per-element model override** (style key = OSM id, `3dmr` tag). **Later**: a landmark kiosk or a
    station building could get its own model keyed by place in `data/truth.json`. The 3DMR's models each
    carry their own licence; none is used.

Nothing here needs ported code. A close translation (the attachment search, the tree row rule) would
carry OSM2World's MIT notice in the file's header.
