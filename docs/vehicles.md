# Vehicles: adding your own, changing one

**English** · [Česky](vehicles.cs.md)

For contributors and modders who want to bring a tram model into the game or change one that is there.
The game is plain ES modules and Three.js with no build step ([DEVELOPING.md](../DEVELOPING.md)); a vehicle
is a model file or code that draws one, and the code that hands it to the game. Changes come as a pull
request ([AGENTS.md](../AGENTS.md): an issue first, the checks below in the PR).

## The models today

The menu's *Tram model* picks one of three, listed in `assets/vehicles.json` with a manifest each (below);
a model that does not load falls back to the first loaded one in that list.

| model | where | made of | licence | moves |
|---|---|---|---|---|
| detailed, animated (the default) | `assets/t3h/`, the rigged loader `src/rigged.js` | a glTF (`.glb`) and `rig.json` naming its moving parts | CC BY-NC 4.0 | doors, collector, bogies, wheels, couplers, track-brake shoes, brake lamps, indicators, high beams; a lighter level for AI trams far away |
| detailed, classic | `src/models.js` (`loadDetailedT3`), `assets/t3/` | a glTF, one texture; loaded when picked | CC BY-NC 4.0 | none |
| simple (built in) | `src/t3simple.js` | code: shapes measured on the T3's drawings and the user's photos, the livery painted on a canvas | AGPL-3.0 | bogies, wheels, couplers, collector; the lamps by state (brake lamps, indicators, high beams) |

`makeT3({ line, cars, vehicle, dest, run, variant })` in `src/models.js` builds a set as the vehicle with that id. Our tram is made in `src/main.js`, AI trams in `src/traffic.js`.

## The manifest

Every model is a folder `assets/<id>/` with a `vehicle.json`, listed in `assets/vehicles.json`. The index's order
is the menu's (the first is the default) and the fallback's: a vehicle that does not load gives way to the first
loaded one in that order, and the built-in car always loads. The game builds its menu, its loading screen and its
credits from the manifests (`src/vehicles.js`, `src/main.js`); `tools/test_vehicles.py` checks them, and
`tools/test_vehicles_game.py` loads each one in the game, with a sample added as a folder alone.

| field | what |
|---|---|
| `schema` | 1 |
| `id` | the folder's name |
| `names` | `cs` and `en`: the menu's text |
| `type` | the vehicle type whose dimensions it has (`VEHICLE_TYPES` in `src/tram.js`: today `T3`) |
| `loader` | `builtin` (drawn in code: `src/t3simple.js`), `gltf` (a still glTF, tier 1, no code), `gltf-classic` (conflig's model: its axes found from its wheels, `src/models.js`), `gltf-rigged` (a glTF with a rig file, no code: `src/rigged.js`, below) |
| `model`, `rig` | the glTF or GLB among its files; the rig file (`gltf-rigged`) |
| `forward` | `gltf` only: the axis the model faces, `+Z` (the game's) unless `+X`, `-X` or `-Z` |
| `files` | every file with its `path` in the folder and its size in `bytes` (the loading screen counts them) |
| `preload` | `true`: downloaded with the line; else when the player picks it |
| `licence` | `spdx` (a licence that allows redistribution), `commercial` (false for NC), `file` (its `LICENSE.txt`), `authors`, `sources` (URLs), `credit` (the line the game shows) |
| `tier` | its tier of movement (below), `moves` the parts it moves, `levels` its distance levels |
| `fleet` | the numbers its sets run as (#527): `types`, per type (e.g. `T3SUCS`) its `ranges` `[first, last]` with `except` (holes), or a `list`; `sets`, the pairs that run together and with no other car, though either car may run alone where a line runs single cars, its partner then free for another single car (a set not listed is two numbers of one type); `liveries`, number → livery id (#529). The run deals them (`src/vehicles.js` `FleetDealer`): a deck of every number shuffled by the run's seed, so each type comes up as often as it has numbers, none twice on the street, given back when a set leaves; our tram runs as the player's preferred set from the menu, else as a T3SUCS dealt the same way, and no AI tram is dealt its numbers. `tools/test_fleet.py` checks the dealing |
| `slots` | a glTF vehicle's livery slots (#529): a slot's name and the materials it paints, e.g. the hybrid's `body` (`Red_Hull`) and `band` (`Beige`, `Beige_wbackface`); the rigged loader keeps their parts apart (with their uv) so a livery can give them a texture or a colour |
| `colours` | a model painted by colour: the names of the colours a livery may replace (the built-in car's `body`, `band`, `roof`) |

A **tier-1 glTF** needs no code: a still model in metres, its origin on the rail plane midway between the bogie
pivots, +Y up, facing `forward`; its pivots are its type's. The menu offers it, it loads when picked and the
credits name it.

## Liveries

A livery (#529; the decision record `docs/decisions/2026-11-10-vehicle-packages.md`, section 3) is a folder
`assets/<id>/` with a `livery.json`, listed under `liveries` in `assets/vehicles.json`; its id is its author's name and
its own (`sample.t3h-blue`). The menu offers our tram the vehicle's own look, one of its liveries, or one dealt as an AI
tram's; AI trams are dealt one (`src/vehicles.js` `liveryOf`). `tools/test_vehicles.py` checks the manifests,
`tools/test_liveries.py` the looks and the dealing in the game.

| field | what |
|---|---|
| `schema`, `id`, `names`, `licence`, `files` | as a vehicle's |
| `kind` | `livery` |
| `requires` | `{ "<vehicle id>": ">=1" }`: the vehicle it paints |
| `textures` | slot → an image among its files: replaces the slot's materials' texture and colour; WebP, PNG or JPEG, power-of-two sides up to 2048 px |
| `colours` | slot or painted colour → `#rrggbb`: replaces the slot's materials' colour, or the built-in car's colour |
| `numbers` | the fleet numbers' `font` (a CSS font family, Arial where it is missing) and `colour` |
| `types` | the fleet types it fits (default: all) |
| `share` | the part of AI sets of those types that wear it, 0 to 1 (default 0: only our tram's, or a number's in the fleet's `liveries`) |

Every slot it leaves out keeps the vehicle's own. A livery naming a slot or a type its vehicle lacks is left out with
the slot's name (`livery x left out: texture slot roof: t3h has no such slot`). The game ships none yet, so the menu
row stays hidden (the user, 2026-11-13: "For now I would keep only the default liveries, with future possibility to
add more variety"); `tools/test_liveries.py` serves two samples of its own, a texture and a colour on the hybrid and
the built-in car's three colours.

## The rig

A vehicle that moves without code of its own (loader `gltf-rigged`, `src/rigged.js`) names its parts in a rig file
(`assets/t3h/rig.json` is the hybrid's), in the model's own frame (its `forward` axis, +Y up). The game drives them by
name; a part its manifest's `moves` claims and the model lacks makes the game refuse the vehicle, naming the part.

| moves | the rig names | the game does |
|---|---|---|
| `bogies` | `bogies`: each `name` (a node) and `pivot` | puts them at the type's pivots (`T3`: 3.2 m from the centre), turns each to the chord between its axles |
| `wheels` | `wheels`: each `name` (a node under its bogie) and `radius` | rolls them by the distance; half a bogie's wheelbase comes from where they stand |
| `couplers` | `couplers`: `front` and `rear`, the bar's meshes | turns each about the type's pin (6.25 m), its bar refitted from the pin to the coupling plane, along the link to the next car |
| `collector` | `pantograph`: `root`, `head`, `linkages`, `clip` (lowering it, 0 raised .. 1 down), `minContactHeight`, `maxContactHeight` | scrubs the clip to the wire's height, lowers it below its range |
| `lamps` | `signals`: `left`, `right` (glow nodes); `brakes`; `beams` (the headlights' centres, for the high beams' glow); `tailLamps` (`size`, `at`: lamps the model lacks) | lights them by state (`src/lamps.js`) |
| `doors` | `doors`: each `name`, `clip` (opening it) and `leaves` (`outer`, `inner` nodes) | scrubs the clips by the doors' openness |
| `trackBrakes` | `shoes`: a bogie's name and the shoes' meshes under it | hangs them at the type's gap over the rail (12 mm), drops them when the magnets are on |

Also by name: `root` (the car's node), `saloon` (`materials`, and `within`: a box whose parts belong to the saloon;
left out far away), `numberPlates` (drawn with the fleet number, its digits `fleetDigits` m tall), `routeStyles`
(each route plate and its style: `normal`, `inverted`, `mirror`), `infoPlates` (`frontDestination`, `runNumber`,
`sideBoards`). Transparent materials are the glass. The lighter level for AI trams far away is built at load: the
doors shut, the collector at the wire, everything but the saloon merged by material. `tools/test_rigged.py` makes a
sample vehicle with every part and checks each of them moves.

The hybrid is maintained in the repo: the asset lab it came from is retired (the user, 2026-11-12: the lab "is
just website for viewing the model and it's animations, it doesn't export anything on its own and most likely won't
be used anymore"). Its rig is generated by [`tools/export_t3h_rig.py`](../tools/export_t3h_rig.py) from
[`tools/t3h_rig_roles.json`](../tools/t3h_rig_roles.json) and the base rig, with its bindings checked
against the GLB (#471). When the model changes, update the part assignments in the roles file and the
base rig as needed, then regenerate `assets/t3h/rig.json` and update its byte count in `vehicle.json`.
`revision` records the asset revision and `rigRevision` versions the generated rig.

```sh
python -I tools/export_t3h_rig.py --out assets/t3h/rig.json
```

## What a set must be

- A `THREE.Group` holding one `Group` per car in `userData.cars`, in order from the front.
- Each car in metres, facing **+Z**, **+Y** up, the right side (the doors) at **−X**, its origin on the rail
  plane midway between the bogie pivots. Models from other tools usually face +X: turn them −90° about Y at
  load, as the rigged loader does by the manifest's `forward`.
- `userData.bogie` (half the pivot distance), `userData.bodyFront` (the body's front from the car's origin),
  `userData.mats` (the plates' and cards' materials), `userData.kind`, `line`, `dest`, `run`.
- The T3's numbers in `src/tram.js` (`T3`: 15.2 m over the couplers, body 14.0 m, pivots 6.4 m apart, the
  coupler's pin 6.25 m from the centre, the track-brake shoes 12 mm over the rail) are what the physics, the
  coupling and the clearances use. A model fits them; a new vehicle type brings its own, with their source.

## What the game does with a set

- **Every frame** `placeConsist(model, s, at)` sets each car on its two bogie pivots, so it yaws, pitches
  and leans with the track. For the hybrid and the built-in car it hangs the next car on the coupling and
  poses each car's running gear (`hangConsist`, `src/consist.js`): a car with moving gear carries
  `userData.gear`, which turns its bogies to the chord between their axles, rolls its wheels by the distance
  and swings its couplers along the link between the cars (the free ones straight ahead). The hybrid's gear
  moves its rig's nodes, the built-in car's its instanced meshes.
- **Its texts:** `setConsistLine(model, line, dest, run)` redraws the route plates, the destination and run
  cards (canvas textures, `src/models.js`), `setNextStop` a T3M's side display.
- **Its state:** `poseT3(model, { doors, collector, braking, track, indicate, clock, highBeam })` (`src/models.js`):
  the doors 0–1, the collector's contact height over the rail (below its working range it lowers), the brake lamps,
  the track brakes' magnets, the indicators (`'left'`, `'right'`, `'hazard'` or none, blinking by `clock`:
  `src/lamps.js`), the high beams. A rigged vehicle takes all of it its rig names (`poseRigged`), the built-in car all but the doors and
  the shoes (`poseSimple`). The headlights and tail lamps are lit whenever a tram is in service, a set's front on its
  leading car only, the rear red lamps (tail and brake) on every car. Our driver works the indicators and high
  beams with keys; the autopilot and AI trams indicate by themselves (`src/indicators.js`), and an AI T3M shows its
  next stop (`setNextStop`).
- **AI trams** (`src/traffic.js`) fade in and out with `setOpacity`, per material: a material's own
  opacity under 1 stays in `userData.opacity`, a material blended from the start stays blended. Far from
  the camera a rigged vehicle switches to its lighter level (`setRiggedLevel`, 50–60 m). A set that leaves is freed
  with `disposeModel`; geometry and textures marked `userData.shared` are kept for the next one.

## Tiers of movement

What a model can offer and the game drives. A model states its tier; the game asks no more of it.

1. **Still:** the body and running gear as one, the plates and cards parametric (route, destination, run,
   fleet numbers); the car rests on its pivots. The classic model today.
2. **Running:** the bogies swivel to the track, the wheels roll, the couplers swing between cars, the
   collector rides the wire's height and lowers, brake lamps, indicators and headlights by state. The hybrid
   and the built-in car have it (#454, #436).
3. **Living:** the doors open and close at stops, the track-brake shoes drop, the wipers run in the rain,
   roof vents and hatches open, the mirror arm folds, the body moves on its springs (leaning in curves,
   pitching as it brakes), the saloon and cab lights, the driver, sparks at the collector on a frosty wire.

Apart from the tiers, a model can have **distance levels**: the full one near the camera and a lighter one
(merged meshes, no saloon) for AI trams farther away, as the hybrid has.

## Adding a vehicle

1. **The licence first.** Only what may be redistributed (CC0, CC BY, CC BY-SA, CC BY-NC, …). The files go
   into `assets/<name>/` with a `LICENSE.txt` (author, source URL, licence, what you changed), a row in
   [ASSETS.md](../ASSETS.md), and the credit line the game shows (the manifest's `licence.credit`).
   A non-commercial model cannot ship in a commercial release; the built-in one can.
2. **The file:** glTF or GLB in metres, the origin and axes as above or adapted at load. Keep it lean: the
   hybrid is 2.9 MB and 44,000 triangles a car, and several AI sets are in view at once. The deploy compresses
   `.glb` and `.gltf` (DEVELOPING.md, *Deploy*).
3. **The moving parts** (tier 2 and 3): separate, named nodes and clips listed in its rig (*The rig*, above). A
   model drawn in code instead gives each car a `gear` for
   `src/consist.js`, as `src/t3simple.js` does with instanced meshes (a car of it draws 8 meshes besides its
   plates).
4. **The manifest:** `assets/<id>/vehicle.json` (above) and the id in `assets/vehicles.json`. A still model
   (tier 1, loader `gltf`) needs nothing more, nor does one that moves by its rig (loader `gltf-rigged`). Vehicles
   found and checked at startup and installed by the player are planned (#456).
5. **The checks:** `python -I tools/test_vehicles.py` (the manifest), `tools/test_vehicles_game.py`, `tools/test_rigged.py`, a test like `tools/test_t3h.py` (levels, coupling, bogies, doors, cards, the fade), the
   frame time with `tools/frametime.py --models …`, and pictures of every model from the same views with
   `python -P -E tools/test_t3simple.py --shots DIR` (side, three-quarter, front, top, the bogie, the coupler; a
   two-car set on a 25 m curve and its running gear in plan; the collector lowered).

## Changing a model

- **The built-in T3** (`src/t3simple.js`): its measurements are named constants at the top of the file
  (`NOSE`, `CORNER`, `LIV`, `CUTOUT`, `HEADLIGHT`, `FLEET`, …), each with where it comes from; the livery is
  painted in `livery()`, the fixed parts in `partsGeometry()`, the moving ones in `bogie()`, `wheelset()`,
  `coupler()` and `pantoBars()` (the pantograph's frame for a contact height), the types and their fleet numbers in
  its manifest's `fleet` (`assets/t3simple/vehicle.json`). `tools/test_t3simple.py` checks it against those numbers.
- **The plates and cards** for every model: `src/models.js` (`routeBoxTexture`, `destinationTexture`,
  `numberTexture`, the T3M's dot-matrix `ledFace`).
- **The hybrid:** maintained in the repo (its asset lab is retired): a change to the model is made by a repo tool and
  listed in `assets/t3h/LICENSE.txt`, as CC BY-NC 4.0 asks; a change to its part assignments goes into its rig's roles
  (its shoes, couplers, saloon, headlights, tail lamps and the fleet numbers' size, #467, #471).
- **Facts:** a dimension, colour or detail of the real car cites its source (a drawing, a photo with its
  fleet number, the user) in a comment or in [docs/knowledge.md](knowledge.md). The user's facts as a Prague
  tram expert win over a drawing or a guess.
