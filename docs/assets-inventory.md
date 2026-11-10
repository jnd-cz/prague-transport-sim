# The older asset labs: inventory

The user built prototypes and asset labs in ChatGPT sites (25–29 Oct 2026) before this repo existed. Six
unpacked archives sit outside the repo in `transport-assets-inbox/`: four labs, and two T3 archives the user
added on 2026-11-04. They were read on 2026-11-04 (#247). Nothing from them is in the repo or the data store.
Every file, including the members of the nested zips, was compared by SHA-256.

## The archives and which copy is current

| archive | files, size | what | current? |
|---|---|---|---|
| `street-life-boarding-v14/` | 158, 14 MB | the asset and passenger lab, v14 of 27 Oct: hybrid T3, cars, pedestrians, cabin metadata, boarding studies, Node tests | **current** for the T3, cars, people and passengers |
| `prague-street-assets-lab/` | 40, 15 MB | street furniture lab of 28 Oct: procedural furniture, shelters, traction poles, converted IPR GLBs, a viewer | **current** for furniture |
| `ipr-models-review/` | 28, 8.5 MB | IPR models and LOD scripts | duplicate: all 28 files are byte-identical to `prague-street-assets-lab/ipr-models-review.zip` and to the same 28 files in that lab |
| `prague-vehicle-and-pedestrian-integration-handoff/` | 45, 6.5 MB | handoff of 29 Oct: a patch of the old prototype, its bridge and tests, the T3 source zip, cabin metadata | current only for the patch, the bridge (`overlay/src/`) and its tests |
| `tatra_t3-SimonStrikesBack/` | 3, 7.4 MB | SimonStrikesBack's T3 as downloaded from Sketchfab (glTF + bin), CC BY 4.0 | the source of the hybrid's base |
| `tatra-t3-simplified/` | 8, 3.3 MB | a first simplification of that model, from before the hybrid work: two GLBs | the CC BY versions before the hybrid |

Duplicates inside the handoff:

- `traffic-integration/overlay/traffic/assets/`: the 13 GLBs and `catalog.json` are v14's `dist/traffic/assets/`. So are `definitions.js` and `plates.js` one level up.
- `presentation.js` differs from v14's in one place only: it exports the palettes for the bridge.
- `passenger-metadata/`: the five files are v14's `dist/traffic/assets/` (T3 cabin layout, navigation, floor space, NB12 fixture and plan image).
- `tram-input/tatra-t3-hybrid-nc-v20261025.zip` is v14's `dist/assets/t3/`:
  - the GLB is identical (SHA-256 `186460b2…`);
  - the zip adds 18 PNGs: 13 copies of the GLB's embedded textures and 5 preview images;
  - v14 adds `seat-detail-profile.json`;
  - `T3-INTEGRATION-GUIDE.html` is v14's `INTEGRATION-GUIDE.html`.
- The handoff calls the passenger lab "not recoverable". `street-life-boarding-v14/` is that lab: it has `passenger-core.js` and the boarding controller.
- three.js r160 is vendored three times. The game loads the same 0.160.0 from jsDelivr (`index.html` import map).

Inside v14:

- `docs/PASSENGER-TIMING.md` = `dist/traffic/passenger-tests.md`;
- `docs/CABIN-FLOOR-ANALYSIS.md` = `dist/traffic/floor-space-notes.md`;
- `tests/passenger-timing.json` = `dist/traffic/passenger-timing-results.json`.

## Assets

Units are metres. The labs' assets use **+X forward, +Y up, +Z right**, with the origin on the ground (for
the T3, the rail plane) under the body centre. The game's vehicles face **+Z** (`makeCar`, `makeT3`,
`placeConsist`), so the adapter is a −90° turn about Y, as the handoff's bridge does it. Triangle counts are
read from the GLBs and agree with the labs' catalogs.

### Tatra T3 hybrid (`street-life-boarding-v14/dist/assets/t3/`)

| | |
|---|---|
| file | `tatra-t3-hybrid-nc.glb`, 2,925,460 B, revision 5 of 2026-10-25; Khronos validator 0 errors, 0 warnings |
| geometry | 43,792 triangles, 262 meshes, 307 nodes, 47 materials. 13 embedded PNGs: 256–1024 px, 0.43 MB, for the lamps, collector, mirror and number and route cards |
| size | bounding box 14.86 m long, 2.69 m wide, 6.37 m high with the collector at its top |
| rig | rigid nodes, no skin (`rig.json`): 3 doors with 2 leaves each, 2 bogies and 8 wheels (r 0.396 m), the collector, and 3 indicators per side. 4 fleet numbers, 3 route plates, the destination, run number and 2 side boards |
| bogies | pivots 6.48 m apart (±3.24 m). The game's built-in model used 7.6 m until #427, now the drawing's 6.4 m, the `T3.bogies` that the physics and `tramClearance` (`src/tram.js`) use |
| collector | contact height 3.89–6.37 m, default 6.00 m (the game's wire is 5.34 m over the rail, `CONTACT_WIRE`) |
| clips | 13: Doors_Open / Doors_Close and one per door (2.2 s), Pantograph_Raise / Lower (3 s), Indicators_Left / Right / Hazard (0.8 s, loop), Brakes_On / Off (0.15 s), Bogies_Demo (6 s, illustrative) |
| controller | `t3-controller.js`: fleet number, route (5 displays), destination (2 lines, Czech), run number, side text, doors, collector height, brakes, indicators, `setTrackPose(curvature, distance)`. The texts are drawn on canvas at run time |
| LOD | none. The lab calls it a close-view asset, "not a background-fleet LOD". `seat-detail-profile.json` hides the 24 seat assemblies (72 meshes, 22,132 triangles) as a visibility study |
| status | A01 accepted by the user 2026-10-26 (a visual study, 8 copies on the user's device). I01 "integrate into the game" queued. No browser GPU check |
| source, licence | base, interior and cab: "Tatra T3" by SimonStrikesBack, CC BY 4.0. Collector, mirror arm, route-plate support, lamp geometry and textures: "Tatra T3" by conflig, CC BY-NC 4.0. **The whole is CC BY-NC 4.0** (`ATTRIBUTION.txt`). The NC parts carry the materials `conflig_Lamps_PBR_CC_BY_NC` and `conflig_Collector_Mirror_PBR_CC_BY_NC`. The "earlier CC BY-only version" (its README) is not in the archives |

For comparison, the game's detailed T3 today is conflig's model alone (`assets/t3/`, CC BY-NC 4.0 in
`ASSETS.md`): 19,886 triangles, 36 meshes, one 2048 px texture, one clip.

**The CC BY versions** (`tatra_t3-SimonStrikesBack/`, `tatra-t3-simplified/`). The hybrid's first 25
materials are this model's own.

| file | triangles | what |
|---|---|---|
| `scene.gltf` + `scene.bin`, 7.38 MB | 206,364; 223 meshes, 384 nodes, 25 materials | the original as downloaded. No textures, no rig, no clips |
| `tatra-t3-balanced.glb`, 1.56 MB | 64,188 | the 24 seat-frame tubes 6,524 → 600 triangles each (meshoptimizer); every other mesh, node and material unchanged; Khronos validator 0 errors |
| `tatra-t3-light.glb`, 1.55 MB | 54,588 | the same with 200 triangles per tube |

- **Parts:** the model has its own pantograph, mirrors, headlights, 8 wheels, doors and 24 seats as separate nodes, and number signs "6900" and "26".
- **Axes:** the length lies along X, but the origin is off the body: Y −0.74 to 4.89, Z −3.71 to −1.12. It needs recentring onto the rail plane, as the hybrid did.
- **Licence:** CC BY 4.0, both the original and the simplified versions (their `ATTRIBUTION.txt`: keep the credit, the licence link and the note that the geometry was simplified).
- **Still missing:** the "earlier CC BY-only version" with a rig, which the hybrid's README mentions, is not among these files either.

### Cars, vans and trucks (`dist/traffic/assets/`, `catalog.json` 0.2.0)

| type | near: triangles / meshes | far: triangles | L × W × H | wheelbase, wheel r | spawn weight |
|---|---|---|---|---|---|
| hatchback `car-*.glb` | 2,602 / 13 | 582 | 4.43 × 2.15 × 1.48 | 2.64, 0.315 | 42 |
| sedan | 2,602 / 13 | 582 | 4.85 × 2.23 × 1.47 | 2.82, 0.325 | 25 |
| estate | 2,602 / 13 | 582 | 4.93 × 2.23 × 1.52 | 2.82, 0.325 | 20 |
| panel van | 2,466 / 13 | 598 | 5.43 × 2.47 × 2.27 | 3.20, 0.36 | 10 |
| box truck | 2,514 / 14 | 622 | 6.44 × 2.69 × 2.85 | 3.70, 0.39 | 3 |

- **Files:** near GLBs are 140–144 kB, far ones 33–35 kB, made by `THREE.GLTFExporter` with no textures.
- **Near:** wheel and steering nodes, and materials for paint, brake, headlamp, both indicators and the plate. The plate is a 512 × 128 canvas per close car.
- **Far:** one primitive with the colours baked in, no moving parts.
- **Detail switch:** in the lab, near → far beyond 55 m and back inside 43 m. In the handoff, at most 8 near cars, within 65 m (out at 73 m). The far cars are instanced.
- **Spawn weights:** illustrative, not measured.
- **Status:** A02, appearance accepted by the user 2026-10-26; the final device review is open.
- **Source:** "original parametric study assets prepared offline for this project". The recipe is `tools/prepare-traffic-assets.mjs` (Node with three r160).

### Pedestrians (`dist/traffic/assets/`)

| file | triangles | rig, clips | notes |
|---|---|---|---|
| `person-near.glb`, 259 kB | 4,228, 3 primitives | skinned, 17 bones; 8 in-place clips of 1 s: Walk, Idle, Run, StairUp, StairDown, TramStepUp, TramStepDown, Sit | height 1.845 m. Stride: walking 1.067 m, running 2.15 m. Shirt and trousers can be tinted. One body family |
| `person-far.glb`, 27 kB | 840 | static, standing | slides at a distance |
| `person-seated-far.glb`, 27 kB | 840 | static, seated | seat surface 0.42 m |

- **Detail switch:** in the lab, near within 21 m (out at 27 m). In the handoff, at most 64 near people within 80 m (out at 88 m).
- **TramStepUp / Down:** illustrative 0.25 m steps, "not a measured T3 staircase". A two-leg target solver fits the feet to the T3's measured steps.
- **Status:** A02, pedestrian art and device motion review **pending**.
- **Source:** the same as the cars.

### Passenger metadata and code (v14 `dist/traffic/`, `docs/`)

| item | what | status |
|---|---|---|
| `assets/t3-cabin-layout.json`, 1.25 MB, schema 0.6 | tied to the hybrid's SHA-256: 24 seats with anchors and headings; 3 doors with their entry steps at 0.47 / 0.67 / 0.89 m; the cab exclusion; 5 standing layouts (adaptive 70 as default, 58, 60, 59, dense 86); the capacity reference | A03 accepted "good enough for now" 2026-10-27 |
| `assets/t3-cabin-navigation.json` | 2 cm floor grid, 720 × 140 cells, 7 categories; seated body outline | experimental |
| `assets/t3-floor-space.json` | floor areas: passenger deck 27.5 m², free with the aisle 17.7 m²; density scenarios | descriptive, "not a certified capacity" |
| capacity reference | 110 (DPMB Brno fleet page, checked 2026-10-26) = 24 seats + 86 standing. The game has the same: `T3.capacity` 110, crush 160 (`src/tram.js`) | reference |
| `assets/sor-nb12-fixture.json`, `sor-nb12-reference.jpg` | four-door SOR NB12 plan study: 28 seat symbols, 2 wheelchair places, 12.18 × 2.55 m (SOR brochure), 88 total (DPP fleet page). Positions are traced from a user-supplied plan of unknown source, without a scale | A04, provisional |
| `passenger-core.js`, `occupancy.js` | Three-free: passenger ids, seat and standing claims, door predicates, lifecycle | A05, a first extraction |
| `boarding-state.js`, `exit-flow.js`, `exit-routing.js`, `cabin-navigation.js`, `cabin-space.js`, `packing-geometry.js`, `passenger-tests.js` | Three-free: queues (2 streams per door), place choice, cooperative exit reservations, scenarios | accepted study |
| `boarding.js` | binds people and their foot targets to the T3 (three.js) | accepted study |
| `bus-fixture*.js`, `stop-study*.js` | NB12 fixture and a stop arrival / door-control study | accepted "good enough for now" 2026-10-27 |
| `presentation.js`, `definitions.js`, `plates.js`, `ring-flow.js` | car and person instances, near/far switch, instanced far batches, fictional plates, a demo lane follower | study API 0.6 |

- **Constants, tuned by hand:** walking 0.95 m/s, seated rise 0.70 s, foot transfer 0.64 s, entry gap 0.72 m.
- **Recorded times (simulation seconds, not calibrated):** 94 people board through 3 doors in 34.3 s (45.6 s settled) and alight in 46.3 s. A 10-out / 10-in exchange takes 21.3 s (`PASSENGER-TIMING.md`).
- **The game today:** 3 doors × 1.1 people/s per car, times 0.45–1 when crowded (`game.js`).
- **Open per the handoff:** body collision, door obstruction, multi-stop journeys and game integration.

### Street furniture (`prague-street-assets-lab/`, README of 28 Oct)

**Procedural factories** (JS on three r160 and BufferGeometryUtils). They are made for the project as
"studies of the IPR 2022 catalogue". Triangles per level:

| family | factory | near / middle / far |
|---|---|---|
| bench with backrest | `makeBenchDetailed`, `makeBenchLod('near' / 'mid')` | 2,148 / 708 / 204 |
| backless bench | `makeBacklessBenchLod` | 1,608 / 648 / 288 |
| large bin / small bin | `makeBinDetailed`, `makeBinLod` | 804 / 196 / 100; 804 / 296 / 140 |
| recycling bin | `makeRecyclingBinLod` | 728 / 392 / 280 |
| bicycle stand | `makeCycleStandLod` | 344 / 104 / 64 |
| bollard | `makeBollardLod` | 152 / 56 / 40 |
| railing, 2 m, bars or glass | `makeRailingLod` | glass: 450 / 130 / 82 |
| shelters P.1–P.4, P.12 | `makeIprShelter({passage, citylight, island, stopName, level, optimized})` | P.1: 346 / 322 / 280, 33 meshes (13 batched) |
| traction poles | `makeTractionPole({type: octagonal / three-stage / heb / historic-study, …})`, `makeWallAnchor` | ≈8.5 m. Three-stage 273 / 219 / 159 mm, HEB ≈300 × 320 mm. `historic-study` is an unverified concept |

- **Shelters:** P.1–P.4 are 4.04 × 1.86 × 2.46 m, P.12 (island) 4.04 × 1.44 m. Each has a stop-name canvas.
- **Axes:** ground at Y = 0. Shelters and railings run along local X, the shelter's back is −Z. A pole's attachment points to +X; a wall anchor's normal is +Z.
- **LOD policy** (`lod-policy.js`): out at 12 and 28 m, in at 10.8 and 25.2 m, "test values".
- **`makeIllustrativeOverhead`:** schematic scenery, not catenary.

**Converted IPR GLBs** (`models/`, `convert_ipr.py` and `convert-near.py`: rhino3dm, numpy, trimesh, from IPR's
Rhino `.3dm` files). These are full-detail references, not game assets. They have no textures, a metal and a
wood material, and some parts lie below Y = 0.

| GLB | triangles | | GLB | triangles |
|---|---|---|---|---|
| bench-2-arms | 49,860 | | bench-4-flat (-middle, -far) | 23,546 (13,366, 7,236) |
| bench-2-back | 42,068 | | bin-large (-near) | 11,664 (8,958) |
| bench-2-flat | 30,490 | | bin-small (-near) | 11,885 (8,294) |
| bench-4-arms (-near) | 57,036 (21,089) | | bin-recycling | 16,782 |
| bench-4-back | 31,528 | | cycle-rack | 3,738 |

- **Status:** the user reviewed the working set and an illustrative line 17 pilot (Kobylisy – Líbeznická, route m 20,630–21,300). WebGL and mobile frame times are unverified, and the placements are illustrative.
- **Other files:** `assets.js` holds the older simple furniture. `existing-models.js` is a copy of the game's `src/models.js` from the 2026-10-24 snapshot.

### Integration slice for the old prototype (handoff `traffic-integration/`)

`game.patch` changes the 2026-10-24 snapshot's `index.html` (rewritten whole), `src/main.js` and
`src/traffic.js`: 338 lines added, 283 removed. It adds:

- **A presentation bridge** (`overlay/src/traffic-visual-study.js`): the old traffic keeps the motion, and the new meshes copy its slots.
- **A vehicle type per road slot**, whose half length and width enter following, obstacles, track crossing and stop lines (`bumperGap`; the game has `CAR_HALF` 2.2 m for every car).
- **A profile recorder.**
- **Mirror modes:** the chosen one, 30 Hz and 300 m, is already the game's (`src/mirror.js`, #79).
- **A `?stress` mode** with 60 cars and 180 walkers.

The handoff measured on one of the user's devices, with the mirror at 30 Hz and 700 m in a crowded scene: 4 intervals
over 20 ms in 5,031 frames. Its tests (`tests/*.mjs`) need Node and `@napi-rs/canvas` at a machine-specific path.

## Mapping to the game today

| package | replaces / extends | integration needs | gap to the repo's rules |
|---|---|---|---|
| T3 model | `src/models.js`: `loadDetailedT3` (conflig glTF) and `makeT3` (procedural fallback); `placeConsist`. AI trams through `makeT3` (`src/traffic.js` ≈ l. 1547) | **Axes:** a −90° turn. **Bogies:** pivot spacing from a source fact (`data/truth.json`), not three different numbers. **Mechanisms from game state:** doors from `game.js` (#246's DVEŘE I/II), the collector at the catenary height (#71), brakes and indicators. **Cards** through the controller, in place of `setConsistLine`'s boxes. **LOD:** a lighter level for AI trams (none exists: 262 meshes per car). **Performance:** the frame time on line 17 before and after, a headed run (headless draws once a second, #205) | CC BY-NC, accepted (Q1); an `ASSETS.md` row; 2.9 MB: git (as `assets/t3/` today) or the store (DATA.md has no class for runtime assets) |
| passengers and boarding | `src/game.js`: passengers are counts (`tram.passengers`, `st.waiting`, a flow per door); only runners are figures (`makePerson`) | the Three-free core behind the counts; the cabin layout needs the hybrid T3 (hash-bound); the people need the pedestrian rig; doors per #246; demand from `demandAt`; figures only near our tram | the Node tests become Python + Playwright tests (`tools/test_*.py`); randomness from `src/random.js` |
| street vehicles | `src/traffic.js`: `makeCar` (3 boxes + 4 wheels, +Z), `MAX_CARS` 30, `CAR_HALF` 2.2 m; parked-car obstacles in `game.js` | **Axes:** a −90° turn. **Lengths:** half length and width per type in the traffic rules, redone on today's `traffic.js`. **Detail:** near and far meshes, the far ones instanced. Plates; brake lamps. **Checks:** u3, redruns, traffic and lint with `--compare` | the recipe is Node (`prepare-traffic-assets.mjs`): take the GLBs as prepared assets, or port the recipe (the 2026-10-29 decision allows no Node toolchain yet); own work, GPL-3.0 (Q3) |
| pedestrians | `src/traffic.js` walkers: one `InstancedMesh` of boxes, `MAX_WALKERS` 90, no animation. `game.js` stop crowds (`makeCrowd(120)`), runners, the driver, obstacle pedestrians | skinned near people (a clone and a mixer each), far people instanced. Walk phase from distance (the catalog's stride). The ground lookup under cars and walkers is already 23 % of a seeded run (#245) | the same as the vehicles; the user's art review comes first (A02 open) |
| street furniture | `game.js` `makeShelter` (glass box, where OSM tags a shelter); `world.js` catenary poles (an instanced 7.4 m cylinder) and wall rosettes. No benches, bins, bollards or railings | placement from a feature layer (#14: OSM tags, DTM points; `tools/dtm_points.py` reads poles and lights, not benches). One geometry per type and level, instanced. Distance bands rather than a `THREE.LOD` per object (#31). The pole type per place from a source | IPR's answer (Q2): the IPR-based studies are development only, out of git and the deploy; the made-up models ship. The converted GLBs (7–57k triangles each) stay references |

The patch itself does not apply: `src/traffic.js` has had 9 commits since 2026-10-24 (e.g. #100, #123,
#152, #154), `src/main.js` and `index.html` 22, and #220 (PR #231) has the car slots open. Two of its ideas
carry over: vehicle dimensions per type in the traffic rules, and a presentation that only reads the
simulation's state (#228).

## Licences

| asset | licence | allows | needs |
|---|---|---|---|
| hybrid T3: GLB, textures, `rig.json` | CC BY-NC 4.0 (combined) | copy, adapt and share; **non-commercial only** | both credits, licence links, the modification notice; accepted (Q1) |
| SimonStrikesBack's T3 (Sketchfab `2c08e2e3…`): `tatra_t3-SimonStrikesBack/`, `tatra-t3-simplified/` | CC BY 4.0 | any use, including commercial | the credit, the licence link, a note of the changes |
| conflig's T3 (Sketchfab `76aa08d7…`), already `assets/t3/` | CC BY-NC 4.0 | non-commercial | in `ASSETS.md` |
| 13 car, van, truck and person GLBs, `catalog.json`; the older made-up furniture (`assets.js`) | the project's own work, made by agents (the catalog: "original parametric study assets … for this project") | **GPL-3.0**, like the code (Q3) | an `ASSETS.md` entry when it enters the repo |
| lab code: presentation, passenger core, `t3-controller.js`, furniture factories, the patch | the project's own work, no licence stated | GPL-3.0 once in the repo | — |
| converted IPR furniture GLBs | **none stated.** Neither IPR's archive nor its pages (iprpraha.cz/mobiliar, /stranka/3413/3d-vykresy-mobiliare) give terms. The first names the design's author, Olgoj Chorchoj (with Aleš Kachlík), and says the City of Prague holds the licence | unknown: the user asks IPR (Q2) | references only |
| procedural furniture and shelters after IPR's drawings | own code; the shapes follow IPR's designs | unknown for the shapes (Q2) | development only until IPR answers |
| three.js r160, GLTFExporter, SkeletonUtils, OrbitControls | MIT | any use | not needed (the game loads r160) |
| `sor-nb12-reference.jpg` | unknown (a user-supplied plan) | — | stays out |
| DPMB T3 110, DPP NB12 88, SOR NB12 dimensions | facts | cite them | `data/truth.json` when used |

### The user's answers (Claude Code session, 2026-11-04)

- **Q1, the hybrid T3's CC BY-NC parts: accepted.** "I would start with option a since we already use the original model and accepted that game source is openly licensed while assets have each their own license and so far there's no plan to ship this game commercially. If we manage to rebuild the model cleanly then I would attempt it, but that's a backlog issue."
  - #248 brings in the hybrid as CC BY-NC 4.0.
  - The clean CC BY version is #254 (Backlog), from the two CC BY archives the user added.
- **Q2, IPR furniture: the user asks IPR.** The user sourced the models and drawings "mostly here https://iprpraha.cz/stranka/3413/3d-vykresy-mobiliare plus some other public IPR documents". The user "would like to keep the simplified models for development work". The older made-up models "can be stored for eventual use but those would be eventually replaced with more realistic representation".
  - The IPR-based studies (the procedural factories and shelters) stay out of git and the deploy until IPR answers. The repo is public; the test site is password-protected but still a distribution.
  - The older made-up furniture (`assets.js`) is own work (GPL-3.0) and can serve as the placeholder that ships.
  - The converted IPR GLBs stay references.
- **Q3, own assets: GPL-3.0.** "for the project's own models, made by chatgpt agent, I will choose the same as source, GPL 3.0."

### A model built from IPR's technical drawings

The user asked what licence impact a model made from the drawings has. This is not legal advice; the facts
for IPR's answer are these:

- **Two things can be protected:**
  - **the drawing and CAD files themselves.** A model we build ourselves from them, rather than converting the `.3dm` files, copies none of the files. Their terms then do not reach it.
  - **the furniture's design.** Czech copyright protects a work of applied art that is "the unique result of the author's creative activity" (Act 121/2000 Sb., § 2(1)); a registered design can protect a shape too. A faithful 3D model reproduces the design however it was built. So building it ourselves does not settle this part.
- **The public-space exception** (§ 33(1)) lets anyone depict a work that stands permanently in a street, "by drawing, painting, photography, film" or otherwise, and use that depiction. § 33(2) excludes making or distributing a three-dimensional copy. Whether a game's 3D model is such a copy, or a depiction like a drawing, is not settled.
- **So one question to IPR covers both:** may the project redistribute 3D models of the Prague furniture, converted or redrawn, in a free (GPL / CC) game? The City holds a "time- and territory-unlimited" licence from the designers (iprpraha.cz/mobiliar). Whether it may grant that to third parties is IPR's to say.
- **Generic furniture** (a bench, a bin, not the Prague design) needs no permission. That is what the made-up models are.

## Work packages, in the suggested order

1. **#250, street vehicles** (part of #66). No third-party licence (own work, GPL-3.0), and the user accepted their appearance. It adds the frame-time bench the others reuse. It goes after #220 (PR #231) and #168 (PR #186), which change `src/traffic.js`.
2. **#248, the T3 model** (part of #68), as CC BY-NC (Q1). It works in `src/models.js`, apart from #221's `src/tram.js`, and needs a lighter level for AI trams. The clean CC BY version is #254 (Backlog), after #248.
3. **#251, pedestrians** (part of #66), after the user's art review and #245.
4. **#249, passengers and boarding** (part of #68). It needs #248 (the hash-bound cabin layout), #251 (the rig) and #246's doors.
5. **#252, street furniture** (part of #67), after the feature layer (#14). It ships the made-up models; the IPR-based ones are development only until IPR answers.
