# Prague Tatra T3 cars 6312 and 6892

Created for [#437](https://github.com/jnd-cz/prague-transport-sim/issues/437).
Original geometry and generated lettering; no meshes or textures from the classic or hybrid assets.
The model is a separate asset study. It does not replace a game model or change simulation behaviour.

Serve the checkout with `python tools/serve.py 8743`, then open
<http://localhost:8743/tools/t3-model/>. Drag to orbit, scroll to zoom, and use the controls to inspect
the moving assemblies. The car selector loads one model at a time. **Download GLB** exports the selected
car in its current pose. Both supplied GLBs have closed doors and a raised collector. Each imports into Blender as
rigid objects with local pivots; it does not need a skin or armature.
The hosted studio is <https://tatra-t3-model-studio.jnd-cz.chatgpt.site>. Entry, running-gear,
interior and collector camera buttons show the details at inspection distance. **Front** and
**Front quarter** approximate the eye-level sightlines of 17823.jpg and 15609.jpg.

| Car | Studio | Neutral GLB | Rig manifest |
|---|---|---|---|
| 6312 | [View car](https://tatra-t3-model-studio.jnd-cz.chatgpt.site/?car=6312) | [6312](tatra-t3-6312.glb) | [6312 rig](rig-6312.json) |
| 6892 | [View car](https://tatra-t3-model-studio.jnd-cz.chatgpt.site/?car=6892) | [6892](tatra-t3-6892.glb) | [6892 rig](rig.json) |

![Both cars from matching front and rear camera positions](fleet-comparison.jpg)

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
| `IMAG5950.jpg`, `FUJI3566.JPG`, `FUJI3032.JPG` | 6892 front and rear three-quarter views and 6921 door side. The skirt returns partly cover the outer wheel faces. |
| `C5R09032.JPG`, `C5R09035.JPG` (2026-11-20) | 6892 straight-on rear and open rear doorway. These show the top-mounted wiper, narrow cream sill and rounded quarter-light beside the last door. |
| `16806.jpg` | 6921: sloping windscreen, folding door leaves, steps, mirror and lamp housings |
| `16447.jpg` | 8080: left side windows, skirt, wheel recesses and louvres |
| `18347.jpg`, `18348.jpg` (2026-11-22) | 8053 bogie sides, used as the reference for 6892's wheel faces, hex nuts, rail brake and visible equipment between the wheels. |
| `16191.jpg` | 8015: three right-side doors, four leaves each, long body proportions |
| `15611.jpg`, `15609.jpg`, `15606.jpg` (2026-11-16 follow-up) | 6312: shallow centre bow, tighter corner windows, brow overhang and aligned route plate; bumper and sill trim |
| `17884.jpg` (2026-11-16 follow-up) | 7000: headlight pods, aluminium bumper with red inserts, cast coupler, collar, handle and chain |
| `17398.jpg`, `17399.jpg`, `17400.jpg` (2026-11-16 interior) | Red cushions, tall silver loop frames, round and electrical-box pedestals, pink-beige wall panels and ribbed floor |
| `17402.jpg` (2026-11-16 interior) | Silver inner folding-door faces, black seals, long handles and amber warning lamp |
| `18530.jpg`, `18531.jpg`, `18532.jpg`, `18535.jpg`, `18536.jpg` (2026-11-23) | 6312 saloon, single seats and their supports, facing pair, aisle poles, floor hatches and driver's partition. The number 6312 is visible above the cab gate. |
| `20261122_120509.jpg`, `20261122_120525.jpg` | 6312 rear glazing, blue plate, paired horizontal tail lamps, roof paint boundary, folding-door hinges, route card and door-side lettering. |
| `20261122_120722.jpg`, `20261122_120531.jpg` | 6312 front headlight spacing, fleet numerals, route board, brow and sill trim, roof disc, mirror stays and side repeaters. |

6312 carries narrow red inserts in raised aluminium strips. The lower side strip is 60 mm wide and
the strip below the windows is 30 mm wide. The cream front paint extends below the strip, while
the red rear panel rises to meet it. [DPP repair specification, pp. 5–6](https://smlouvy.gov.cz/smlouva/soubor/40397664/R%C3%81MCOV%C3%81%20SMLOUVA%20O%20D%C3%8DLO%20p%C5%99%C3%ADloha3.pdf)

The 874 mm floor height is corroborated by the
[Bratislava T3 technical table](https://imhd.sk/ba/vehicle-type-description/20/%C4%8CKD-Tatra-T3).
Prague gauge is modelled as 1,435 mm. Door positions and window sizes are scaled from the drawing;
the rounded end surfaces, glazing rake, collector linkage, coupler height, materials, interior and
small fittings are visual approximations. This is a reconstruction of the photographed T3 appearance,
not a measured restoration model of every fitting on 6892.
No source image or user photograph is embedded in the GLB or redistributed in this directory.

6312 has red upholstered seats with silver loop frames. 6892 has moulded shells on a provisional
24-place layout. Photos `20261121_123814.jpg`, `123807` and `123838` show the dished red and
grey shells, open slots and tubular grab rails. The model alternates colours along each bank.
The complete seat order and pitch are estimates.
The working 6312 layout puts 14 singles on the continuous window side and ten on the door side.
Four face forward between the middle and rear doors. Between the front and middle doors, five face
forward and the chair on the front box faces them. Both the aisle and the rear platform are open.
The full row count, placement of the facing pair, seat pitch and rear platform arrangement are modelling
estimates fitted to the requested capacity. The photographs show only parts of the car in each view.
The interior follow-up supplies the seats' loop frames and pedestal bases, red upholstery,
pink-beige lower wall panels with silver kick plates, red/silver sill trim and dark rubber ribs.
The model uses box bases for the frontmost chair in each file and flared pedestals for the others.
Door leaves have cream outer faces and silver inner faces, with long handles on the inner leaves.
The rubber pattern is an original generated 64-pixel tile, embedded alongside the lettering atlas.
The maintainer's statements are retained in `data/truth.json`, section `t3PhotoModel`.
[DPP's October 2022 history](https://www.dpp.cz/data/leaflets/documents/2022-10-27-16-03-56_DP-kontakt-rijen-2022.pdf)
corroborates the padded leatherette seats fitted to early T3 cars 6102–6323.

The revised shells have a longer plan taper and rounder end sections with matching domed caps.
Long faces are split at both shoulders before tapering, so the central walls and floor keep their
full width. The seat-frame check measures clearance against the actual side panels.
The view down through the end window (`20261121_124445.jpg`) supplies the broad centre bow before
the tighter corners. The stair photograph (`20261122_121753.jpg`) shows a projecting middle tread
with clipped corners. Both cars use that profile. Door tops align with the 2.63 m window heads.
The test samples the lower edges of every leaf at 25 angles through the 84° opening.
The 84° stop is a visual interpretation of the maintainer's “a bit less” than 90°, not a factory dimension.
Each wheel has a solid disc, a separate tyre and a single central hex nut. The side frame, layered suspension
pack, flared cover and inboard housings occupy the space above the brake. The two 8053 views establish their
silhouettes. The hidden geometry and hanger construction are estimates repeated on both bogies.
The four magnetic brakes include coil casings, pole shoes, spring hangers, reaction links and feed
cables, following the FC33 construction described in section 2.2.4 of
[Ondřej Kocourek's 2015 VUT thesis](https://www.vut.cz/www_base/zav_prace_soubor_verejne.php?file_id=104984).
Their detail dimensions remain estimates. They follow their bogies; brake application has no separate rig control yet.

6892 fleet lettering wraps the curved ends. The right number sits
behind the front doorway; the left sits farther aft as in the supplied side views. There is an amber
repeater on each side. The end profile was also compared with
[DPP's 6892 photograph by Anna Kettnerová](https://muzeum.dpp.cz/data/Photo%20muzeum/6892.jpg).
Each of the four articulated collector frames has one diagonal; opposite frames overlap head-on.

The follow-up end study separates the gently bowed nose from its tighter corner glazing. The front
and rear have different glazing rake and upper-corner radii. The brow lip tapers to the side
and rolls into the roof. The front glass meets the cream sill directly. The front route plate
is centred and tilted with the brow, in a cream holder. The head-on 6892 photo gives roughly
30 pixels of exposed lens for 185 pixels between centres. The lamp dimensions follow that ratio;
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
| `Wiper_left/right` → `_pivot`, `_link`, `_carrier` | Two spindles below each front pane move its blade from the divider towards the centre. The carrier keeps the blade upright. |
| `Wiper_rear` → `Wiper_rear_pivot` and `Wiper_rear_link` (6892) | Hand-operated from the rear driving position. Both arms park vertically and can be posed to either side (estimated ±0.65 rad). 6312 has a clear rear window in the supplied view. |
| `Wiper_rear_carrier` | Counter-rotates under the main arm to keep the blade upright. Link lengths and sweep are estimated from the parked position. |
| `Route_plate` | Static plate and holder aligned to the front brow |
| `Body` / `Interior` / `Exterior_details` | Static rigid assemblies |

`makePhotoT3({variant: '6312'})` or `makePhotoT3({variant: '6892'})` returns a Three.js group
with live references in `model.rig`. Omitting the variant preserves the 6892 API default.
`posePhotoT3(model, state)` sets an absolute pose, so repeated calls do not accumulate drift.
State fields: `doors` (scalar or three values 0–1), `bogies` (two yaw angles), `wheelAngle`
(radians), `pantograph` (0–1), `wipers` (front, 0–1), `rearWiper` (manual, −1 to +1, centred at 0),
`couplers` (two yaw angles). Omitted fields reset
to defaults. The preview exercises these transforms; no timed animation clips are baked.

For an imported GLB, call `bindPhotoT3(gltf.scene)` to reconnect the same pose API, or look up nodes
by the names above. Each car's manifest records its exported default transforms and parent hierarchy.
The exact linkage equations are in `posePhotoT3`; export the posed hierarchy or keyframe these rigid nodes in a DCC tool.
The default collector position is a display pose, not a simulation of contact with a wire.

## Reproduce and check

`python -P -E tools/test_t3photo.py --car 6312 --export` runs the geometry/export checks.
Repeat with `--car 6892`. The report counts model triangles and reads frame draw calls at a fixed camera,
then hides the car and subtracts the empty studio's draw calls to measure the car alone.
For the full render sweep, use the shared queue:
`python -I tools/heavy.py "T3 photo render sweep" -- python -P -E tools/test_t3photo.py --export --screenshots`.

Uses the project's existing Python/Playwright and pinned Three.js 0.160.0, with its own server on a
free port and a whole-test timeout. It verifies physical dimensions, independent door movement,
wheel/bogie/coupler poses, folded and raised collector linkage closure, finite geometry, and a GLB
export/import round-trip retaining the hierarchy, materials and embedded lettering and rubber textures.
The review checks also ray-test solid risers and wheels, the brow's projection beyond the glass,
and the coupler's open fork and bored eye, and check the route plate, 24 seat supports and opposite door finishes.
It writes the GLB and rig manifest above and the report and inspection renders to `reports/t3photo/`.
The studio works without world data. Its first load needs the same CDN as the game.

## Asset register

| Files | Author / origin | Licence |
|---|---|---|
| `tatra-t3-6312.glb`, `tatra-t3-6892.glb`, generated lettering | Original models made for this project by Codex, revised 2026-11-23 | AGPL-3.0-or-later |
| `rig-6312.json`, `rig.json`, `fleet-comparison.jpg`, `preview.png`, `doors-open.png` | Rig manifests and original studio renders | AGPL-3.0-or-later |
| `../../src/t3photo.js` | Reproducible geometry and pose source | AGPL-3.0-or-later |

Own-model licence follows the maintainer's 2026-11-12 change recorded in
`docs/decisions/2026-10-29-tests-and-licences.md`. See the repository `LICENSE`.
