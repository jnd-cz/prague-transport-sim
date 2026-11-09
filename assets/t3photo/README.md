# Tatra T3 6892 — original photo-based model

Created for [#437](https://github.com/jnd-cz/prague-transport-sim/issues/437).
Original geometry and generated lettering; no meshes or textures from the classic or hybrid assets.
The model is a separate asset study. It does not replace a game model or change simulation behaviour.

Serve the checkout with `python tools/serve.py 8743`, then open
<http://localhost:8743/tools/t3-model/>. Drag to orbit, scroll to zoom, and use the controls to inspect
the moving assemblies. **Download GLB** exports the current pose. The supplied `tatra-t3-6892.glb`
has closed doors and a raised collector. It imports into Blender and other glTF 2.0 applications as
rigid objects with local pivots; it does not need a skin or armature.

## References and limits

The [general arrangement drawing](https://drawingdatabase.com/tatra-t3/), specifically
[`Tatra-T3-1.gif`](https://drawingdatabase.com/wp-content/uploads/2014/03/Tatra-T3-1.gif),
was inspected on 2026-11-09. Its original publisher is not identified by the host.
The drawing supplies body length, width, roof height, bogie spacing, axle spacing, wheel diameter
and length over couplers. These dimensions are in `T3_PHOTO` in `src/t3photo.js`, in metres.
The 552 mm horizontal annotation is the coupler's extension past the body, **not its height**.
The [colour elevations](https://drawingdatabase.com/wp-content/uploads/2014/03/trams_t3_01.png)
help establish the window/door pattern, but the supplied photographs take precedence for appearance.

The five user photographs supplied in the 2026-11-09 session are visual references:

| File | Used for |
|---|---|
| `17823.jpg` | 6892 front: cream brow, two headlights, number, blue route board, orange collector |
| `17824.jpg` | 6892 rear: window, cream skirt, red face, coupler recess |
| `16806.jpg` | 6921: sloping windscreen, folding door leaves, steps, mirror and lamp housings |
| `16447.jpg` | 8080: left side windows, skirt, wheel recesses and louvres |
| `16191.jpg` | 8015: three right-side doors, four leaves each, long body proportions |

The 874 mm floor height is corroborated by the
[Bratislava T3 technical table](https://imhd.sk/ba/vehicle-type-description/20/%C4%8CKD-Tatra-T3).
Prague gauge is modelled as 1,435 mm. Door positions and window sizes are scaled from the drawing;
the rounded end surfaces, glazing rake, collector linkage, coupler height, materials, interior and
small fittings are visual approximations. This is a reconstruction of the photographed T3 appearance,
not a measured restoration model of every fitting on 6892. Seat layout is a simplified saloon.
No source image or user photograph is embedded in the GLB or redistributed in this directory.

## Animation contract

Coordinates: **metres, +Y up, +Z front, -X door side**, origin at the centre on the rail plane.
Body is 14 m long; mirrors, couplers and the collector extend beyond its envelope.
All meshes use ordinary glTF materials. Static parts are merged by material within their rigid
assemblies; movable groups retain their pivots and stable names. `userData` becomes glTF extras.

| Nodes | Pivot / motion |
|---|---|
| `Bogie_1`, `Bogie_2` | Y yaw at z = +3.2 / -3.2 m, y = 0.35 m |
| `Wheelset_1_1` … `Wheelset_2_2` | Local X rotation; ±0.95 m relative to each bogie |
| `Door_1` … `Door_3` | Front to rear; each contains front and rear bi-fold pairs |
| `Door_N_front_outer`, `Door_N_rear_outer` | Local Y jamb hinges; ±90° to fold inward |
| `Door_N_front_inner`, `Door_N_rear_inner` | Local Y edge hinges; opposite rotation, twice the outer angle |
| `Pantograph_lower_front/rear` | Local X at base; symmetric rotation |
| `Pantograph_upper_front/rear` | Local X at elbow; opposite relative angle, twice the lower angle |
| `Pantograph_contact_head` | Y translation; stays level at both arm tips |
| `Coupler_front`, `Coupler_rear` | Local Y yaw; shank pivot at z = ±6.25 m |
| `Wiper_left/right` → `Wiper_left/right_pivot` | Parent aligns the local Z axis to the raked windscreen |
| `Body` / `Interior` / `Exterior_details` | Static rigid assemblies |

The source API returns a Three.js group with live references in `model.rig` (not serialized).
`posePhotoT3(model, state)` sets an absolute pose, so repeated calls do not accumulate drift.
State fields: `doors` (scalar or three values 0–1), `bogies` (two yaw angles), `wheelAngle`
(radians), `pantograph` (0–1), `wipers` (0–1), `couplers` (two yaw angles). Omitted fields reset
to defaults. The preview exercises these transforms; no timed animation clips are baked.

For an imported GLB, call `bindPhotoT3(gltf.scene)` to reconnect the same pose API, or look up nodes
by the names above. `rig.json` records their exported default transforms and parent hierarchy.
The exact linkage equations are in `posePhotoT3`; export the posed hierarchy or keyframe these rigid nodes in a DCC tool.
The default collector position is a display pose, not a simulation of contact with a wire.

## Reproduce and check

`python -P -E tools/test_t3photo.py --export --screenshots`

Uses the project's existing Python/Playwright and pinned Three.js 0.160.0, with its own server on a
free port and a whole-test timeout. It verifies physical dimensions, independent door movement,
wheel/bogie/coupler poses, folded and raised collector linkage closure, finite geometry, and a GLB
export/import round-trip retaining the hierarchy, materials and embedded lettering atlas.
It writes the GLB and rig manifest above and the report and inspection renders to `reports/t3photo/`.
The studio works without world data. Its first load needs the same CDN as the game.

## Asset register

| Files | Author / origin | Licence |
|---|---|---|
| `tatra-t3-6892.glb`, generated lettering | Original model made for this project by Codex, 2026-11-09 | GPL-3.0 |
| `rig.json`, `preview.png`, `doors-open.png` | Rig manifest and renders of the original model | GPL-3.0 |
| `../../src/t3photo.js` | Reproducible geometry and pose source | GPL-3.0 |

Own-model licence follows the user's 2026-11-04 choice recorded in
`docs/decisions/2026-10-29-tests-and-licences.md`. See the repository `LICENSE`.
