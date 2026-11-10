# Vehicles: adding your own, changing one

**English** · [Česky](vehicles.cs.md)

For contributors and modders who want to bring a tram model into the game or change one that is there.
The game is plain ES modules and Three.js with no build step ([DEVELOPING.md](../DEVELOPING.md)); a vehicle
is a model file or code that draws one, and the code that hands it to the game. Changes come as a pull
request ([AGENTS.md](../AGENTS.md): an issue first, the checks below in the PR).

## The models today

The menu's *Tram model* picks one of three; a model that does not load falls back to the next simpler one.

| model | where | made of | licence | moves |
|---|---|---|---|---|
| detailed, animated (the default) | `src/t3h.js`, `assets/t3h/` | a glTF (`.glb`) and `rig.json` naming its moving parts | CC BY-NC 4.0 | doors, collector, bogies, wheels, couplers, track-brake shoes, brake lamps, indicators, high beams; a lighter level for AI trams far away |
| detailed, classic | `src/models.js` (`loadDetailedT3`), `assets/t3/` | a glTF, one texture; loaded when picked | CC BY-NC 4.0 | none |
| simple (built in) | `src/t3simple.js` | code: shapes measured on the T3's drawings and the user's photos, the livery painted on a canvas | GPL-3.0 | bogies, wheels, couplers, collector; the lamps by state (brake lamps, indicators, high beams) |

`makeT3({ line, cars, detailed, dest, run, variant })` in `src/models.js` builds a set with the chosen
model. Our tram is made in `src/main.js`, AI trams in `src/traffic.js`.

## What a set must be

- A `THREE.Group` holding one `Group` per car in `userData.cars`, in order from the front.
- Each car in metres, facing **+Z**, **+Y** up, the right side (the doors) at **−X**, its origin on the rail
  plane midway between the bogie pivots. Models from other tools usually face +X: turn them −90° about Y at
  load, as `src/t3h.js` does.
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
  `src/lamps.js`), the high beams. The hybrid takes all of it (`poseHybrid`), the built-in car all but the doors and
  the shoes (`poseSimple`). The headlights and tail lamps are lit whenever a tram is in service, a set's front on its
  leading car and its rear on the last; the brake lamps at the set's rear. Our driver works the indicators and high
  beams with keys; the autopilot and AI trams indicate by themselves (`src/indicators.js`), and an AI T3M shows its
  next stop (`setNextStop`).
- **AI trams** (`src/traffic.js`) fade in and out with `setOpacity`, per material: a material's own
  opacity under 1 stays in `userData.opacity`, a material blended from the start stays blended. Far from
  the camera the hybrid switches to its lighter level (`setHybridLevel`, 50–60 m). A set that leaves is freed
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
   [ASSETS.md](../ASSETS.md), and the credit line the game shows (as `T3H_CREDIT` in `src/t3h.js`).
   A non-commercial model cannot ship in a commercial release; the built-in one can.
2. **The file:** glTF or GLB in metres, the origin and axes as above or adapted at load. Keep it lean: the
   hybrid is 2.9 MB and 44,000 triangles a car, and several AI sets are in view at once. The deploy compresses
   `.glb` and `.gltf` (DEVELOPING.md, *Deploy*).
3. **The moving parts** (tier 2 and 3): separate, named nodes listed in a rig file like
   `assets/t3h/rig.json`: `doors` (their leaves), `bogies` (name and pivot), `wheels` (name and radius),
   `pantograph` (root, head, linkages, contact heights), `signals` (indicators), `brakes` (brake lamps),
   `numberPlates`, `routePlates`, `infoPlates` (destination, run number, side boards), and animation clips by
   name (`Door_Front_Open`, `Pantograph_Lower`, …). A model drawn in code instead gives each car a `gear` for
   `src/consist.js`, as `src/t3simple.js` does with instanced meshes (a car of it draws 8 meshes besides its
   plates).
4. **The code:** a module like `src/t3h.js` (load, build a set with each car's `gear`, pose it), a branch in
   `makeT3` and in `poseT3`
   (`src/models.js`), the files in the loading screen (`load.prefetch`,
   `load.get` in `src/main.js`), and a menu option (`optModel` in `index.html`, its names in both languages
   in `src/i18n.js`). There is no common vehicle interface yet: today a new model means these edits. A
   manifest per vehicle (#455) and a common interface, with vehicles found and checked at startup and
   installed by the player (#456), are planned.
5. **The checks:** a test like `tools/test_t3h.py` (levels, coupling, bogies, doors, cards, the fade), the
   frame time with `tools/frametime.py --models …`, and pictures of every model from the same views with
   `python -P -E tools/test_t3simple.py --shots DIR` (side, three-quarter, front, top, the bogie, the coupler; a
   two-car set on a 25 m curve and its running gear in plan; the collector lowered).

## Changing a model

- **The built-in T3** (`src/t3simple.js`): its measurements are named constants at the top of the file
  (`NOSE`, `CORNER`, `LIV`, `CUTOUT`, `HEADLIGHT`, `FLEET`, …), each with where it comes from; the livery is
  painted in `livery()`, the fixed parts in `partsGeometry()`, the moving ones in `bogie()`, `wheelset()`,
  `coupler()` and `pantoBars()` (the pantograph's frame for a contact height), the types and their fleet numbers in
  `T3_TYPES`. `tools/test_t3simple.py` checks it against those numbers.
- **The plates and cards** for every model: `src/models.js` (`routeBoxTexture`, `destinationTexture`,
  `numberTexture`, the T3M's dot-matrix `ledFace`).
- **The hybrid:** the asset comes from the project's asset lab; a change to the file goes through it, or is
  made at load in `src/t3h.js` (as its couplers, track-brake shoes, fleet numbers and tail lamps are).
- **Facts:** a dimension, colour or detail of the real car cites its source (a drawing, a photo with its
  fleet number, the user) in a comment or in [docs/knowledge.md](knowledge.md). The user's facts as a Prague
  tram expert win over a drawing or a guess.
