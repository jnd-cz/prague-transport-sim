# OSM2World: railways, tram track and overhead line (#15)

OSM2World read at commit `1d31c252cbef964b489a55e5fb8242ee253375b1` (2026-11-02), MIT. Paths below are
under `core/src/main/java/org/osm2world/`. Its textures: OSM2World-default-style at `3d82b2e9`
(2026-10-25), see [assets.md](assets.md). Our side: main at 595514a. Prague counts from our extract
(`raw/osm/praha.osm.pbf`, snapshot of 2026-10-22), counted with pyosmium and shapely on 2026-11-05.
Feeds #65 (railway tracks), #277 (power data from the DTM) and #71 (catenary under overpasses).

## What OSM2World does

**Rails** (`world/modules/RailwayModule.java`): every segment of a way with `railway=rail|light_rail|tram|
subway|disused` is a `Rail`, a network way segment (outline mitred and cut back at junctions like a road,
`AbstractNetworkWaySegmentWorldObject`).

| constant | value | what |
|---|---|---|
| `DEFAULT_GAUGE_MM` | 1435 | `gauge` tag overrides |
| `RAIL_SHAPE` | 0.056 wide × 0.084 high box | the detailed I profile is in the file, replaced by the box ("overkill") |
| `RAIL_HEAD_WIDTH` | 0.067 | rail centres = gauge + 0.067 = 1.502 m apart (the box is 0.056: the comment "must match RAIL_SHAPE" no longer holds) |
| `SLEEPER_EXTRA_WIDTH` | 0.5 | sleeper = gauge + 2 × 0.067 + 2 × 0.5 = 2.569 m long |
| `SLEEPER_LENGTH` | 0.26 | along the track |
| `SLEEPER_HEIGHT` | 0.064 | 0.16 × 0.4, "sinking into the ballast" |
| `SLEEPER_DISTANCE` | 0.86 | 0.6 gap + 0.26 |
| `GROUND_EXTRA_WIDTH` | 0.2 | ballast = sleeper + 0.4 = 2.969 m wide |

- **Two levels of detail.** Far (LOD0–3): the ballast strip carries one repeating texture of ballast,
  sleepers and rails (`RAILWAY`: `custom/Railway`, 3.0 × 2.96 m per tile, `STRIP_FIT_HEIGHT` across), and
  the rails are extruded boxes on it. Near (LOD4): a plain ballast texture (`RAIL_BALLAST`: ambientCG
  `Gravel020`, 0.6 m tiles, world X/Z coordinates), sleepers as instances of one box model per sleeper
  width (`SleeperModel`, cached in `sleeperModelByWidth`), rails lifted by the sleeper height.
- A rail end with no other rail segment gets a capped, closed shape.
- **Junctions and switches: not drawn.** `RailJunction` (ballast polygon at a node with 3+ rails) is
  commented out ("reactivate after implementing proper rendering for rail junctions"); the rails of the
  two ways overlap.
- **Trams:** no ground mesh (`ownGround = false`, "tram is often part of a street"), no sleepers; only
  the two rails, drawn on whatever is under them. No groove, no paving between the rails.
- **Tunnels:** `railway=subway` (unless `tunnel=no`) and `tunnel=yes` are `GroundState.BELOW`.

**Overhead line: nothing.** No module reads `power=catenary_mast`, `power=portal`, `electrified`,
`voltage` or `contact_line`. The power module (`world/modules/PowerModule.java`) draws `power=line`
between towers with a parabolic sag, `(1 − (2t − 1)²) × 6.0 m` (`SLACK_SPAN`), sampled every 3 m (LOD3)
or 10 m (LOD4), cables 0.05 m thick; `power=minor_line` as a 0.05 m bar 7.5 m over the ground
(`DEFAULT_CLEARING_BL`, "power pole height is 8"); `power=pole` as an 8 m wooden column, r 0.15;
`power=tower` from billboard textures (`powertower_*.png`) or a lattice model.

**Nothing on clearance**: bridges and tunnels do not change anything hung over a track.

## What we do

- **Track** (`src/world.js`, "track bed + rails"): for every tram track of the line's data, a 2.7 m bed
  ribbon at the style's offset under top of rail, and two 0.1 m rail ribbons centred at ±0.72 m,
  `RAIL_HEAD` 0.012 m over TOR (`src/heights.js`), with side faces where the bed lies more than 3 cm
  under them. Cant tilts bed and rails together. One chunked geometry each for beds and rails.
- **Styles** (`src/heights.js` `trackStyleOffsets`, `data/truth.json` `railAboveDeck`): embedded 0,
  panels 0, grass 0.04, ballast 0.17 m between top of rail and the bed surface. No sleepers in any style.
- **The ±0.72 m rails** span 0.67–0.77 m: the gauge face (0.7175) lies 47 mm inside the inner edge, room
  for a grooved rail's groove and lip. A flat-bottomed rail's head (67–72 mm) centres at ±0.751–0.754.
- **Track support** (`buildTrackSupport`): the ballast top and stone sides where the profile stands
  over the ground.
- **Centrelines** from the DTM's DI layer, the archived DTMP axes, then OSM (`tools/di_tracks.py`,
  `docs/decisions/2026-10-27-track-source.md`); switches stay at OSM's nodes or move to a source fork.
- **Overhead line** (`src/world.js` `buildCatenary`): a contact wire `CONTACT_WIRE` = 5.34 m over TOR
  of every track (`src/models.js`), as line segments; spans every 12/18/25/32 m by curve radius
  (< 50 / 100 / 200 m / straight); each end on a kerb pole or a wall rosette (a building within 5.5 m
  behind the kerb), a bracket arm where only one side has an anchor within 9 m; spans hang level 6.74 m
  over TOR (0.4 m under the pole top), droppers down to the wires; poles one instanced 7.4 m cylinder
  scaled to their foot. Rule in `docs/knowledge.md` ("Catenary poles"). The spans are exported for
  signals and signs (`route.catenary`, `route.kerbAt`).
- No railway (`railway=rail`) is drawn; #65 asks for it with the tram track model.

**OSM in Prague**: `railway=tram` 2,625 ways, 354 km of track ways; `electrified=contact_line` on 2,551,
`electrified=no` on 37, `voltage=600` on 2,539, `gauge` on 2,624, `embedded_rails` on 23.
`power=catenary_mast` 2,793 nodes (42 also `highway=street_lamp`, 27 `material`, 10 `support`):

| nearest track within 15 m | masts | per km of tram track way |
|---|---|---|
| tram (< 3 m / 3–8 m / 8–15 m) | 988 (326 / 439 / 223) | 2.8 |
| railway | 1,729 | |
| neither | 76 | |

That is 5.6 masts per km of route (354 km of track ways, about 177 km of double track); our rule hangs
31–83 spans per km. The 326 within 3 m of a track centreline are centre poles between the tracks or
masts mapped on the track. `power=portal`: 238 nodes, 31 ways.

## Ideas: take or not

1. **Ballasted track with sleepers, two levels of detail.** **Take, reimplement** for #65 and for our own
   `ballast` style (rail 0.17 m over the bed, no sleepers drawn now): near, a ballast texture in world
   coordinates, sleepers as one instanced box per sleeper type, rails as extruded profiles; far, one strip
   texture with ballast, sleepers and rails painted (OSM2World's `custom/Railway`, CC0, fits standard
   gauge at 3.0 m across). Our numbers, not its: a concrete sleeper 2.6 m long, the spacing, the rail
   profile and the tram's open-track sleepers (wood or concrete, per place: the user's answer, as for
   Výtoň's wooden sleepers in `docs/research/prazsketramvaje/web-notes.md`). Flat-bottomed rail heads at
   ±0.753 m; grooved rail keeps ±0.72.
2. **Rail end caps** where a rail has no continuation (buffer stops, depot ends). **Take**: trivial.
3. **Junctions.** **Nothing to take**: OSM2World leaves switches undrawn; ours keep separate tracks too.
   A switch drawn with blades and frog is our own work (W4), from the switch geometry of #204.
4. **Trams without ground.** **Not taken**: we draw the bed and its styles; OSM2World has none.
5. **OSM catenary masts as a source.** **Not as a source** (5.6 per km of route against 31–83 spans).
   **Take as a check** in #277: per line, the share of OSM masts within 2 m of a pole
   our rule or the DTM places, and the distance; masts that also carry `highway=street_lamp` (42) mark
   the combined lamp-and-traction poles the DTM's lamp layer must not double.
6. **`electrified=no`** (37 tram ways). **Take**: a track tagged so gets no contact wire; list which ways
   they are first (depot fans, museum tracks).
7. **Sagging span wires.** **Take the formula, small**: a span between two anchors sags
   `(1 − (2t − 1)²) × f`; for our 10–20 m cross-spans f is centimetres to decimetres (to be measured on
   photos), and droppers keep the contact wire level. OSM2World's 6 m is for high-voltage spans.
8. **Clearance under bridges (#71).** **Nothing in OSM2World.** Ours: a per-place contact-wire height in
   `data/truth.json` (where the user or a source gives it) or the structure's underside minus a fixed
   clearance, interpolated along the track; `buildCatenary` and the pantograph read the same function.

No code is worth porting: the railway module is 309 lines over its own network classes. A close
translation of the sleeper/LOD scheme would carry OSM2World's MIT notice in the file.
