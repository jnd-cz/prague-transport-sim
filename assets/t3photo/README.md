# Tatra T3 6892 — original photo-based model

Created for [#437](https://github.com/jnd-cz/prague-transport-sim/issues/437).
Original geometry and generated lettering; no meshes or textures from the classic or hybrid assets.
The model is a separate asset study. It does not replace a game model or change simulation behaviour.

Serve the checkout with `python tools/serve.py 8743`, then open
<http://localhost:8743/tools/t3-model/>. Drag to orbit, scroll to zoom, and use the controls to inspect
the moving assemblies. **Download GLB** exports the current pose. The supplied `tatra-t3-6892.glb`
has closed doors and a raised collector. It imports into Blender and other glTF 2.0 applications as
rigid objects with local pivots; it does not need a skin or armature.
The hosted studio is <https://tatra-t3-model-studio.jnd-cz.chatgpt.site>. Entry, running-gear,
interior and collector camera buttons show the details at inspection distance.

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
| `15611.jpg`, `15609.jpg`, `15606.jpg` (2026-11-16 follow-up) | 6312: shallow centre bow, tighter corner windows, brow overhang and aligned route plate; bumper and sill trim |
| `17884.jpg` (2026-11-16 follow-up) | 7000: headlight pods, aluminium bumper with red inserts, cast coupler, collar, handle and chain |

The 874 mm floor height is corroborated by the
[Bratislava T3 technical table](https://imhd.sk/ba/vehicle-type-description/20/%C4%8CKD-Tatra-T3).
Prague gauge is modelled as 1,435 mm. Door positions and window sizes are scaled from the drawing;
the rounded end surfaces, glazing rake, collector linkage, coupler height, materials, interior and
small fittings are visual approximations. This is a reconstruction of the photographed T3 appearance,
not a measured restoration model of every fitting on 6892.
No source image or user photograph is embedded in the GLB or redistributed in this directory.

The 2026-11-16 review uses the user's requested **24-place early cushioned interior**, inspired by
6312/6102, under the 6892 exterior. There are 13 single seats on the left, nine on the door side,
and two at the rear. The arrangement is a simplified modelling choice, not a survey of 6892.
The user's quotes are retained in `data/truth.json`, section `t3PhotoModel`.
[DPP's October 2022 history](https://www.dpp.cz/data/leaflets/documents/2022-10-27-16-03-56_DP-kontakt-rijen-2022.pdf)
corroborates the padded leatherette seats fitted to early T3 cars 6102–6323.

The revised shells have a longer plan taper and rounder end sections with matching domed caps.
Steps have closed risers and side walls; door leaves end just above the first tread and fold to 84°.
The 84° stop is a visual interpretation of the user's “a bit less” than 90°, not a factory dimension.
Wheels have continuous profiled faces, dusty brown material and distinct running treads.
The four magnetic brakes include coil casings, pole shoes, spring hangers, reaction links and feed
cables, following the FC33 construction described in section 2.2.4 of
[Ondřej Kocourek's 2015 VUT thesis](https://www.vut.cz/www_base/zav_prace_soubor_verejne.php?file_id=104984).
Their detail dimensions remain estimates. They follow their bogies; brake application has no separate rig control yet.

Fleet lettering is enlarged, wraps the curved ends, and shares one side height. The right number sits
behind the front doorway; the left sits farther aft as in the supplied side views. There is an amber
repeater on each side. The end profile was also compared with
[DPP's 6892 photograph by Anna Kettnerová](https://muzeum.dpp.cz/data/Photo%20muzeum/6892.jpg).
Each of the four articulated collector frames has one diagonal; opposite frames overlap head-on.

The follow-up end study separates the gently bowed nose from its tighter corner glazing. The front
and rear have different glazing rake and upper-corner radii; the brows project over the glass and
meet a domed roof. The front route plate is centred and tilted with the brow, in a cream holder.
Red headlight pods, sill/drip trim and broad aluminium bumpers with red inserts follow the new photos;
the earlier 6892 rear photo supplies its rear lamps and upright wiper. Couplers have a bevelled, tapered
cast fork with bored eyes, a drawbar collar, lifting handle, side pins and safety chain. Their finished
coupling faces retain the drawing's 15.104 m overall length. All small casting dimensions are photo estimates.

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
| `Door_N_front_outer`, `Door_N_rear_outer` | Local Y jamb hinges; ±84° to fold inward |
| `Door_N_front_inner`, `Door_N_rear_inner` | Local Y edge hinges; opposite rotation, twice the outer angle |
| `Pantograph_lower_front/rear` | Local X at base; symmetric rotation |
| `Pantograph_upper_front/rear` | Local X at elbow; opposite relative angle, twice the lower angle |
| `Pantograph_contact_head` | Y translation; stays level at both arm tips |
| `Coupler_front`, `Coupler_rear` | Local Y yaw; shank pivot at z = ±6.25 m |
| `Wiper_left/right` → `Wiper_left/right_pivot` | Parent aligns the local Z axis to the raked windscreen |
| `Wiper_rear` → `Wiper_rear_pivot` | Upright rear blade, local Z sweep |
| `Route_plate` | Static plate and holder aligned to the front brow |
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

`python -P -E tools/test_t3photo.py --export` runs the short geometry/export checks.
For the full render sweep, use the shared queue:
`python -I tools/heavy.py "T3 photo render sweep" -- python -P -E tools/test_t3photo.py --export --screenshots`.

Uses the project's existing Python/Playwright and pinned Three.js 0.160.0, with its own server on a
free port and a whole-test timeout. It verifies physical dimensions, independent door movement,
wheel/bogie/coupler poses, folded and raised collector linkage closure, finite geometry, and a GLB
export/import round-trip retaining the hierarchy, materials and embedded lettering atlas.
The review checks also ray-test solid risers and wheels, the brow's projection beyond the glass,
and the coupler's open fork and bored eye, and check the route plate and 24 seats.
It writes the GLB and rig manifest above and the report and inspection renders to `reports/t3photo/`.
The studio works without world data. Its first load needs the same CDN as the game.

## Asset register

| Files | Author / origin | Licence |
|---|---|---|
| `tatra-t3-6892.glb`, generated lettering | Original model made for this project by Codex, 2026-11-09, revised 2026-11-16 | AGPL-3.0-or-later |
| `rig.json`, `preview.png`, `doors-open.png` | Rig manifest and renders of the original model | AGPL-3.0-or-later |
| `../../src/t3photo.js` | Reproducible geometry and pose source | AGPL-3.0-or-later |

Own-model licence follows the user's 2026-11-12 change recorded in
`docs/decisions/2026-10-29-tests-and-licences.md`. See the repository `LICENSE`.
