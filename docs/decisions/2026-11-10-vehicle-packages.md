# Vehicles, liveries and sound packs as data packages a player installs (#456)

Status: **proposed**. Questions for the user at the end. It builds on the registry of #455 (a `vehicle.json`
per model in `assets/<id>/`, listed in `assets/vehicles.json`, PR #461) and on tier 2 movement (#454).

The user, 2026-11-10 (PR #430): "build up common vehicle interface ... To make it easy to plug in new vehicles
that can be also automatically recognized and checked by the game on startup, so the player can install it
easily". And for this record (2026-11-10): sounds and sound packs and how they are triggered, with a basic and an
advanced tier; textures and repaints; a fleet number range to generate numbers in; to follow how similar games
already do it, SimT's repaints among them.

## How other simulators do it

Researched 2026-11-10 (the sources, one per claim, are in the PR's research comment). "Forum" marks what only
community forums document.

| | repaint / livery | fleet numbers | sounds | package and its check |
|---|---|---|---|---|
| **SIMT MHD** (the Czech online game simtrepainty.cz serves; [the T3R.P 8565+8409 repaint](https://simtrepainty.cz/index.php?title=%C4%8CKD_Tatra_T3R.P_DPP_ev._%C4%8D._8565%2B8409)) | overwrites a fixed vehicle slot's files (`scin-6-0041/`: sides, exterior, interior, door textures as XNA `.xnb`); no choice in the game, no uninstall without a backup | one `evidencniCislo (8565)` per slot in its `scintext.txt`, painted into the side texture; the set declared in the lead car (`souprava (6-0040/…)`) | separate mods for a sound slot (`zvuky (6-0048/1)`) | copy `Content/` over the game; `scintext.txt` mixes paint with mass, doors and displays, so a game update breaks old repaints |
| **OMSI 2** (forum) | the model names repaintable textures by keyword (`[CTCTexture]`); a repaint is a `.cti` file mapping keywords to images, plus `[setvar]` options (door type, ticket printer) | a `[number]` list file; plates from a parallel list or prefix + number + postfix | `sound.cfg`: `[loopsound]` pitched by a variable over a reference value, `[sound]`+`[trigger]` on script events, `[volcurve]`/`[pnt]` curves that multiply, `[3d]` position and full-volume radius, an interior/exterior/AI mask, a separate set for AI buses | folders copied in; errors in a log |
| **Train Simulator Classic** (forum) | a copied blueprint pointing at new textures | a CSV of numbers; digit quads in the model whose textures `primarynumber_0…9` the engine swaps | `.proxyxml` blueprints, curves over control values | `.ap` zips, no manifest |
| **OpenBVE** ([sound.cfg](https://openbve-project.net/documentation/HTML/train_sound_cfg.html), [train.dat](https://openbve-project.net/documentation_hugo/en/trains/train_dat.html)) | none | none | fixed slots (`[Run]` per track type pitched by speed from a 90 km/h recording, `[Flange]`, `[Motor]`, `[Switch]` per axle, `[Compressor]` attack/loop/release, doors, horn start/loop/end); a motor table with a row per 0.2 km/h giving the sound, pitch and volume; `sound.xml` adds a position and radius per sound | folders |
| **Open Rails** ([sound](https://open-rails.readthedocs.io/en/latest/sound.html)) | | | discrete triggers (doors, horn) and variable ones (speed or distance past a value); volume and frequency curves over speed, curve force, tractive effort, brake cylinder pressure; start/loop/release; rail joints by axle count; flange squeal below about 301 m radius; outside sounds heard inside at 0.75 | |
| **MSFS 2020/2024** ([liveries](https://docs.flightsimulator.com/msfs2024/retail/models-and-textures/modeling/aircraft/airframe/liveries/static-liveries/), [texture.cfg](https://docs.flightsimulator.com/msfs2024/retail/content-configuration/textures/texture.cfg/), [registration](https://docs.flightsimulator.com/msfs2024/retail/models-and-textures/modeling/aircraft/airframe/registration-numbers/), [wave sounds](https://docs.flightsimulator.com/msfs2024/retail/content-configuration/sounds/wave-data-sound-properties/)) | a livery ships only the textures it changes; the rest from `fallback.N` folders | the registration string drawn at run time into a decal material on placeholder meshes, its font and colour per livery | Wwise events fed by sim variables, or `.wav` files into fixed slots with pitch and volume curves, a random pick from a list, full-scale distance; a separate AI set | `manifest.json` (version, minimum game version, dependencies) and `layout.json` (every file with its size) |
| **ETS2 / ATS** ([paint jobs](https://modding.scssoft.com/wiki/Documentation/Engine/Units/accessory_paint_job_data), [engine sound](https://modding.scssoft.com/wiki/Documentation/Engine/Sound/TruckEngine), [mod manager](https://modding.scssoft.com/wiki/Documentation/Engine/Mod_manager)) | a mask texture whose R, G, B channels each take a colour the player picks (some locked) | | FMOD events the game drives with named parameters (`rpm`, `load`, `brake`); one small file per event points at `bank#event`, so a mod replaces one sound | `manifest.sii`: version, name, author, icon 276×162, localized description, compatible game versions with wildcards; the mod manager refuses an incompatible mod |
| **BeamNG** ([skins](https://documentation.beamng.com/modding/materials/vehicle/skinsystem)) | a skin part plus replacement materials; palette maps for three player colours | | | zips in `mods/` mirroring the game's folders, overriding by path |
| **glTF** | [`KHR_materials_variants`](https://github.com/KhronosGroup/glTF/blob/main/extensions/2.0/Khronos/KHR_materials_variants/README.md) (ratified): named material sets inside one file; three.js through a plugin | | [`KHR_audio_emitter`](https://github.com/KhronosGroup/glTF/pull/2137): a draft since 2022, not in three.js | [VRM's meta](https://github.com/vrm-c/vrm-specification/blob/master/specification/VRMC_vrm-1.0/meta.md): authors, licence URL, commercial use, credit, redistribution and modification, in the model |

What they share, and what the browser changes:
- **The base model declares slots; a package fills them by name** (OMSI's keywords, MSFS's fallback folders and
  placeholder materials, ETS2's events and parameters, OpenBVE's fixed sections). Nothing refers to an array index
  or a path inside another package.
- **A package ships only what it changes** and the rest comes from its base (MSFS `texture.cfg`).
- **No code in a package**: behaviour stays in the game, a package binds data to the game's named states and
  parameters (OpenBVE, MSFS's wave mode, ETS2's parameters). That is also the only safe choice for a web page.
- **Additive, not overwriting.** SimT shows the cost of overwriting: one repaint per slot, no uninstall, the paint
  tied to the game's version. ETS2, MSFS and BeamNG add packages under their own ids, with versions and
  compatibility, and refuse what does not fit.

## Proposal

### 1. Four kinds of package, one manifest

A package is a folder (in the repository, or a .zip the player installs) with `package.json` at its root:

```json
{
  "schema": 1,
  "kind": "vehicle | livery | sounds | fleet",
  "id": "jnd.t3-dpp-1990s",
  "version": "1.2.0",
  "game": ">=0.9",
  "requires": { "t3h": ">=1" },
  "names": { "cs": "…", "en": "…" },
  "description": { "cs": "…", "en": "…" },
  "thumbnail": "thumb.webp",
  "licence": { "spdx": "CC-BY-4.0", "commercial": true, "modification": "allowed", "authors": ["…"], "sources": ["…"], "credit": "…" },
  "files": [{ "path": "sides.webp", "bytes": 812034, "sha256": "…" }]
}
```

The rest of the file depends on its `kind`. `vehicle` is #455's `vehicle.json` grown into this format (#455's fields
stay; `version`, `game`, `requires`, `description`, `thumbnail` and the hashes are added). `livery`, `sounds` and
`fleet` packages name the vehicle they are for in `requires` and add to it; any number of them can be installed
side by side, and the player picks among them or lets the game deal them out. The ids are the author's name and
the package's (`jnd.t3-dpp-1990s`), so two authors never collide.

### 2. The vehicle interface: what a vehicle provides, by tier

The game drives every vehicle from **named nodes, materials and clips in its glTF**, listed in its rig (today
`assets/t3h/rig.json`), never from code in the package. What the game reads, by tier (`docs/vehicles.md`):

| tier | the rig names | the game does |
|---|---|---|
| 1 still | `bodyFront`, the pivots (or its type's), placeholders: `plate.route`, `plate.dest`, `plate.run`, `plate.rear`, `fleet.*` (meshes UV-mapped to a texture the game draws) | places each car on its pivots; draws route, destination, run and fleet numbers into the placeholders |
| 2 running | `bogie.N` (pivot), `wheel.N` (radius), `coupler.front/rear` (pin), `pantograph` (root, head, linkages, contact range), lamp groups `lamp.head`, `lamp.pos`, `lamp.tail`, `lamp.brake`, `lamp.rev`, `lamp.ind.left/right`, `lamp.high` | turns bogies, rolls wheels, swings couplers (`src/consist.js`), raises the collector to the wire, lights lamps by state (`src/lamps.js`) |
| 3 living | `door.N` leaves with clips `Door_N_Open`, `shoe.N`, `wiper.N`, `mirror`, cab and saloon lights, `display.side` (a dot-matrix display's size in dots) | opens doors at stops, drops the track-brake shoes, runs the wipers in the rain, the T3M's next stop |

Every tier also has its **distance levels** (`levels`: a lighter glTF or named nodes hidden far away) and a
**budget** the startup check holds it to (below). The built-in car keeps its own code, as #456 says; the hybrid's
code (`src/t3h.js`) becomes the general rigged loader, its asset-specific fixes (couplers refitted, tail lamps added)
moving into the asset.

### 3. Liveries (repaints)

The vehicle's manifest names its **texture slots** (`"slots": { "sides": "T3_body", "front": "T3_front", "roof": … }`:
a slot name and the glTF material whose `baseColorTexture` it replaces) and its **colour slots** (`"colours":
{ "body": "#c42b1c", "band": "#f2e2b4" }` where the model is painted by colour, as the built-in car).

**Basic livery** (what most repaints need):
```json
{ "kind": "livery", "requires": { "t3h": ">=1" },
  "textures": { "sides": "sides.webp", "front": "front.webp" },
  "colours": { "band": "#efe3c0" },
  "numbers": { "font": "fleet-dpp", "colour": "#e3b625" },
  "types": ["T3SUCS"], "era": [1990, 2010] }
```
Only what it changes; every other slot falls back to the vehicle's own. `types` limits it to some of the vehicle's
variants, `era` to the years it was on the street (for a timetable of that year, later).

**Advanced livery**, additions:
- `mask`: one RGB texture whose channels each take a `colours` entry (ETS2's colormask), so one file gives many
  liveries, and the player may recolour the unlocked ones;
- `numbers.only`: the fleet numbers it belongs to (an advertising wrap on 8544+8545, as SimT's BESIP repaint), so
  the game puts it on those cars only;
- `options`: values for switches the vehicle exposes (OMSI's `[setvar]`: destination display type, mirror, door
  type), limited to the vehicle's `options` list;
- `levels`: lighter textures for the far level;
- a vehicle author who ships every livery inside one GLB uses `KHR_materials_variants` and lists the variant names
  in the manifest instead.

Images: WebP, PNG or JPEG (KTX2 once the game uses it), power-of-two sides up to 2048 px, as MSFS recommends.

### 4. Fleet numbers

Numbers are **drawn by the game** into the placeholders (MSFS's way, and the built-in car's and the hybrid's today:
`src/t3simple.js`, `src/t3h.js` `fleetTexture`), never painted into a texture, so a livery is not one car.

A `fleet` (in the vehicle's manifest, or a `fleet` package for an operator or a period) lists what may appear:
```json
{ "kind": "fleet", "requires": { "t3h": ">=1" },
  "operator": "DPP", "year": 2005,
  "types": {
    "T3SUCS": { "ranges": [[7001, 7292]], "except": [7019, [7100, 7104]] },
    "T3M":    { "ranges": [[8005, 8106]] },
    "T3R.P":  { "list": [8409, 8544, 8545, 8565] }
  },
  "sets": [[8565, 8409], [8544, 8545]],
  "liveries": { "8544": "cvr.besip", "8545": "cvr.besip" } }
```
- `ranges` with `except` (holes: withdrawn cars, renumbered ones) or an explicit `list`;
- `sets`: pairs that run together (Prague's sets are not consecutive, SimT declares them in the lead car); a set
  not listed is two numbers dealt from the same type;
- `liveries`: the livery a number wears (an advertising wrap), by the livery's id;
- **dealing**: the run's seeded random stream (`src/random.js`) shuffles the numbers of each type and deals them
  without repeats, so no two sets on the street carry the same number, and a replay of the run deals the same;
  each type as often as it has numbers (the user, 2026-11-10: "roughly related to their range sizes"); when every
  number is out, it deals again from the start. Our own tram's number: the player's pick, or dealt the same way.
- today's `variants` in #455's manifest (`{ type, fleet: [[first, last]] }`) is the first step of this; the game
  picks by the run number now and moves to the dealing with this.

### 5. Sounds

Today every sound is synthesised in `src/audio.js` (motor whine, rolling, rail joints every 18 m, flange squeal
under 20 m radius, the motor-generator, contactor clicks, bell, door buzzer, the indicator relay, warnings). That
stays as the built-in sound pack, the fallback for any slot a pack leaves empty.

The game publishes two lists in `docs/vehicles.md`, generated from the code so they cannot drift:

- **Events** (one-shots): `door.open`, `door.close`, `door.buzzer`, `bell`, `gong`, `contactor`, `lineContactor`,
  `notch.up`, `notch.down`, `reverser`, `pantograph.up`, `pantograph.down`, `breaker.on`, `breaker.off`,
  `trackBrake.on`, `trackBrake.off`, `sand`, `joint` (per axle over a rail joint), `points` (per axle over a frog),
  `indicator.tick`, `indicator.tock`, `warning`, `crash`, `deadman`.
- **Parameters** (with units): `speed` (m/s), `wheelSpeed` (m/s, slipping wheels race), `motorCurrent` (A),
  `tractiveForce` (kN), `brakeForce` (kN), `controller` (the cam's position), `mgRpm` (the motor-generator),
  `curveRadius` (m), `slide` (0/1), `trackBrake` (0/1), `doors` (0–1), `wire` (0/1: on the wire), `rain` (0/1),
  `tunnel` (0/1), `view` (cab, saloon, outside).

**Basic sound pack**: a file (or a list, one picked at random each time) per event, and the loops the game
already plays, each with the speed it was recorded at:
```json
{ "kind": "sounds", "requires": { "t3h": ">=1" },
  "events": { "door.open": "door-open.mp3", "bell": ["bell1.mp3", "bell2.mp3"], "joint": "joint.mp3" },
  "loops": {
    "motor":   { "file": "motor-30kmh.mp3", "refSpeed": 8.3, "volume": "motorCurrent" },
    "rolling": { "file": "roll-40kmh.mp3", "refSpeed": 11.1 },
    "flange":  { "file": "squeal.mp3" },
    "mg":      { "file": "mg.mp3", "refRpm": 1800 } } }
```
A loop is pitched by its parameter over the reference (OpenBVE's `[Run]` at 90 km/h), its volume by the game's
built-in curve for that loop; each event sounds where the game puts it (the doors at the doors, joints at the
bogies); the same sounds inside and outside, the game's own filter for the cab.

**Advanced sound pack**, per sound:
- `files` and `pick` (random, in turn), `parts`: start, loop and stop (the compressor, the motor-generator
  running up and down; OpenBVE's attack/loop/release);
- `pitch` and `volume`: piecewise-linear curves over any parameter, several multiplied
  (`"volume": [["speed", [[0, 0], [2, 1]]], ["motorCurrent", [[0, 0.2], [450, 1]]]]`, OMSI's `[volcurve]`,
  MSFS's curves);
- **crossfade sets**: recordings at several speeds, each sounding around its own (OMSI's 722…1653 rpm example),
  for a motor whose tone changes with speed;
- `when`: conditions on parameters (`["slide", "=", 1]`, MSFS's `<Requires>`);
- `at`: a position in the car or a rig node name (`bogie.1`, `door.2`) and `radius`, the distance it stays at full
  volume (OMSI `[3d]`, OpenBVE `Radius`, Web Audio `PannerNode.refDistance`);
- `views`: `cab`, `saloon`, `outside`, `ai` (OMSI's viewpoint mask); an `ai` subset that is cheaper for the AI trams
  around (OMSI `[sound_ai]`, MSFS `soundai.xml`);
- `cabin`: an impulse response for sounds heard from inside (a Web Audio `ConvolverNode`), else the game's
  low-pass filter.

In Web Audio: a loop is an `AudioBufferSourceNode` with `loop` and its `playbackRate` set from the pitch curve, a
`GainNode` from the volume curves (both through `setTargetAtTime`, as `src/audio.js` does now), a `PannerNode` per
positioned sound with the camera as the listener. Files: WAV or MP3 (every browser decodes them); Ogg/Opus only
with an MP3 fallback.

Trigger rules the game owns, not the pack: a joint per axle where the track data has joints (today every 18 m),
points per axle at a frog, flange squeal by curve radius and speed (Open Rails' radius rule as a start), the door
events at the doors' clips' times.

### 6. Installing, listing, removing

- **In the game's menu** (*Vehicles…*): the player picks a .zip or a folder; it is unpacked into the browser's
  origin private file system (OPFS), checked (below) and listed. Each package can be switched off or removed; the
  list shows its version, author, licence and its check's warnings. Nothing leaves the browser.
- **By URL**: a package's `package.json` address; the game downloads its files into OPFS and can check for a newer
  version. Only with the player's click, and the files' hashes are checked.
- **In a self-hosted copy**: folders in `assets/` listed in `assets/vehicles.json`, as #455 has them; the repository's
  own vehicles stay this way.

### 7. The check at startup and at install

A package that fails is listed with its reasons and not offered; one with warnings is offered with them.
- the manifest against its JSON Schema (`schema` version), its `game` and `requires` versions met;
- every file listed, present, of an allowed type (glTF/GLB, WebP/PNG/JPEG, WAV/MP3/Ogg, JSON; nothing else is
  read), its size and hash as listed, within the caps (the package, a texture, a sound);
- the licence: a known SPDX id, authors, a credit line; non-commercial ones marked so;
- a vehicle's glTF: its axes and origin against its type (the bounding box within the type's length and width,
  the wheels' lowest points on the rail plane within 2 cm, the pivots where stated), the rig's nodes and clips for
  the tier it claims, the triangles and draw calls of each level within the budget (the hybrid's 44,000 triangles
  a car as the first one);
- a livery's slots, a sound pack's events and parameters, a fleet's types: all among those its vehicle and the
  game declare.

The same checks run in `tools/test_vehicles.py` for the repository's vehicles, from one shared description of the
schema.

### 8. Other vehicle types

A type is data: `src/tram.js`'s `T3` today (length, pivots, coupler pin, mass, the track-brake gap). A new type
brings the same numbers with their sources; the physics, the coupling and the clearance checks
(`tramClearance`) read them. Driving one needs its equipment model too (the T3's TR 37 in `src/tr37.js`): a type
without one runs only as an AI tram, until its equipment is built. Candidates once the T3 is complete: the
T3's relatives that share its equipment (T3SUCS, T3M, T3R.P differ in equipment and look) as variants, then other
Prague types (KT8D5, 14T, 15T) as types of their own.

### 9. Also worth deciding now

- **Which trams run where:** a fleet names the depots or lines it serves, so AI trams on a line are the types that
  ran there (line 23 the heritage T3s, #455's line rule today).
- **Destination and side displays** as data: a display's kind (roller blind, LED dot matrix with its dots, as
  SimT's `panel` blocks), its size and position, so the T3M's display is not code.
- **Our tram's choice:** vehicle, livery, number (or dealt) and sound pack picked in the menu and remembered.
- **Integrity across updates:** a package states the schema it was made for; the game migrates older schemas or
  refuses them with a reason, never guesses (SimT's repaints break with each game update because they carry the
  game's own config).

## Questions for the user

1. **Package kinds:** vehicle, livery, sounds and fleet as separate packages, each naming the vehicle it is for
   (section 1)? Or liveries and fleets only inside a vehicle's own package?
2. **Fleet numbers:** ranges with exceptions, explicit lists and explicit sets, dealt without repeats from the
   run's seed (section 4)? Should a fleet carry the year it describes, so a 1990s timetable shows 1990s numbers?
   Is there a source for Prague's real T3 sets (which cars ran together) we may use?
3. **Sounds:** the event and parameter lists of section 5, a basic and an advanced pack as proposed? Which T3
   sounds matter most to get from recordings first (motor, contactors, bell, doors)?
4. **Liveries:** the basic livery as texture and colour slots, the advanced adding the colour mask, per-number
   wraps and options (section 3)?
5. **Installing:** a .zip or folder picked in the menu and kept in the browser (OPFS), and a URL (section 6)? Any
   other way the players you have in mind would expect (a shared catalogue page, like simtrepainty.cz)?
6. **Hosting third-party packages:** may the project list packages others host (a catalogue with links), or only
   ship what is in the repository?
7. **The first step after this record:** the generic rigged loader with the hybrid moved onto it (section 2), or
   liveries and fleet numbers first (sections 3 and 4), or sounds (section 5)?
