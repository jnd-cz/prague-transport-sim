# World build: what to change and how to check it (for the computer with the build tools)

Written from the remote session, which had only the deployed game (no `tools/`, no `raw/`). What
changed in the game itself is in `REMOTE-CHANGES.md` (by section); performance and preprocessing
numbers are in `PERF-ANALYSIS.md`. This file is the to-do list and test procedure for the **build
side** (`tools/build_line.py` and friends), generalized from what the remote session found.

Order of work: §1 (rules every import follows) → §2 (build changes, by priority) → §3 (validation
the build should print) → §4 (checks in the browser after each rebuild) → §5 (known issues to
re-check).

---

## 1. Rules for every import step

1. **One coordinate conversion, shared by every tool.** The line data uses, from `lineN.json`
   `origin = [lat0, lon0]`:

   ```python
   KY = 110574                                   # m per degree of latitude
   KX = 111320 * math.cos(math.radians(lat0))    # m per degree of longitude
   to_xy = lambda lat, lon: ((lon - lon0) * KX, (lat - lat0) * KY)
   to_ll = lambda x, y: (lat0 + y / KY, lon0 + x / KX)
   ```

   The remote OSM signal import used 111320 for latitude as well. Its nodes ended up as much as 45 m
   off north–south at the line's ends, and only ~1 m near the centre, so it looked right where it was
   first checked. Put the conversion in one module (e.g. `tools/geo.py`) that every tool imports.
   Never re-type it.
2. **Fit check after every import:** convert the OSM `railway=tram` ways of the corridor and measure
   each point's distance to the line's own tracks (`path` / `pathBack` / `tracks`). The median must be
   under 0.5 m (it is 0.05 m with the right conversion). Print it in the build log (§3).
3. **Overpass etiquette:** query in boxes of ~1.5 km of route with a 120 m margin, 5 s apart.
   Rotate two servers (`overpass-api.de`, `overpass.kumi.systems`) with backoff. Send a
   descriptive User-Agent. **Cache the raw responses** under `raw/osm/lineN/` with the date, so
   rebuilds are reproducible and offline.
4. **Attribution:** every OSM-derived file adds "OpenStreetMap contributors (ODbL)" to the line's
   `attribution`.
5. **Deterministic output:** sorted keys and lists, rounded to cm. Diffs between builds then show
   real changes only.

---

## 2. Changes to the build, by priority

### 2.1 Fold the OSM signal import into the build (high)

The prototype is `tools/osm_signals.py` (run as `python -P -E tools/osm_signals.py 17`).
It writes `data/lineN.signals.json`, which `src/main.js` loads optionally as `data.osmSignals`:

| key | OSM source | used by | line 17 |
|---|---|---|---|
| `stop: [{x, y, hx, hy, both}]` | `highway=traffic_signals` on roads; direction from `traffic_signals:direction` (forward/backward along the way; none = `both`) | car stop lines (`traffic._stopLine`) | 201 |
| `peds: [{x, y}]` | `crossing=traffic_signals` off the tram track | not yet (pedestrian heads / push buttons, §2.7) | 198 |
| `tram: [{x, y, sig}]` | `railway=tram_crossing`, or a crossing node on a tram way; `sig` = signalled | route conflicts (`game._routeConflicts`) | 319 (64 signalled) |

To do:
- Move it into `build_line.py`, using the shared conversion (§1.1) and the cached raw data (§1.3).
  Keep the separate file (the client treats it as optional) or merge it into `lineN.json` as
  `osmSignals`; either works with `main.js` after a one-line change.
- Drop `stop` nodes within 6 m of a road junction node. The game already ignores these: they are
  the old one-node-per-junction tagging and say nothing about the stop line.
- Optional: for each `stop` node, also store the OSM way id it lies on. The client then matches
  lanes by way instead of by distance and heading.
- There are **no tram signal nodes** (`railway=signal`) for Prague trams in OSM. Tram signal
  positions keep coming from the line data (§2.3).

### 2.2 Validate the pedestrian crossings on the route (`crossings`) (high)

71 of line 17's 136 `crossings` have no OSM `railway=tram_crossing` within 5 m. Some are real
crossings tagged otherwise; others look like crossings of a parallel road projected onto the
route. Example: Palackého náměstí has a crossing at s 12353 inside the platform; the real track
crossing (OSM) is at 12363 and the platform ends at 12365.
- For each crossing, keep it only if a footway / `highway=crossing` way **actually intersects the
  tram tracks** (both tracks, at street level, not over a bridge or under a tunnel). Projecting the
  nearest point onto the route is not enough.
- Log the dropped ones, with s and the OSM id, for a manual look.
- Mark zebra paint (`crossing=zebra` / `crossing:markings`) and signalled crossings separately.
  The game draws zebras from roads tagged `z` and stops cars before them.

### 2.3 Tram signal data (`signals: [{s, cross}]`) (medium)

The client now places each signal itself (`game._placeSignals`, log line `signals placed: …`): at the
junction edge, before platform ends, never hung over the junction. It works around bad input that
the build should fix at the source:
- `cross` sometimes comes from a road junction **beside** the track, not one crossing it. At
  Přístaviště the signal stood mid-platform, 72 m before the crossing, and matched nothing. Derive
  `cross` from the first real track crossing ahead (car or pedestrian) using the same
  geometry as §2.2.
- Optionally precompute what the client computes and ship it, so the client only checks it:
  - `edge`: near edge of the first conflict;
  - stop point = edge − 4 m, or the platform end when the crossing follows the platform;
  - `demand`: no conflict within 30 m;
  - `drop`: a far-side crossing of a junction that has its own signal.
- Grade separation: signals where the track is on a bridge belong to the road underneath. The client
  already drops them (`profile.overBridge`); the build could do it too.

### 2.4 Stops and platforms (medium)

With the right conversion, 27 of 38 line 17 stops have their tram stop point within 3 m of OSM's
`public_transport=stop_position`. Most of the others are 3–8 m past it, because the game stops the
front at the platform end. The build should report, per stop:
- the distance to the OSM `stop_position` on **our** track (list over 10 m). Look at these
  first: Právnická fakulta +13 m, Hercovka +92 m, Vozovna Kobylisy −84 m (the loop?);
- **platform vs crossing overlaps**: a crossing that starts before the platform's end (Staroměstská:
  4 m; Palackého: see §2.2). The client now moves the stop point back to the signal's stop point,
  but the data should not have the overlap;
- staggered platforms are real (Hodkovičky: ours ends at 5976, crossing at 5981, the opposite
  platform starts at 5986). Don't "fix" those.

### 2.5 Lane graph inputs (medium)

- **Palackého most:** no inbound lane comes off the bridge (the road seems one-way in our data),
  so that approach has no car light although OSM has its stop line. Check `oneway` and lane tags on
  the bridge ways and whether `chainTunnels`/bridge chaining drops a direction.
- **Kobylisy:** several approaches end more than 25 m from the signal's crossing point and have no
  OSM stop node, so they are not bound to the junction and stay unlit. Either map/add the stop
  nodes, or ship a junction id per OSM junction cluster (all road nodes of one signalled junction)
  so the client binds approaches by id instead of by distance.

### 2.6 Run numbers (`runs`) (low, needs the PID GTFS)

The client is ready for `data.runs[tripIndex] = {depot, run}` (REMOTE-CHANGES §9):
- run number = depot digit + two-digit run;
- night and late-evening runs are numbered from 51 and are single cars.

The PID GTFS has no `block_id` as far as we know: check again, else use the run lists published by
enthusiasts.

### 2.7 Pedestrians (low)

- Doors (building entrances as walker spawns) are found at run time (1,597 of 2,214 buildings on
  line 17). OSM `entrance=*`, metro exits (`railway=subway_entrance`) and station entrances would be
  better spawn points: ship them as `doors: [{x, y, kind}]`.
- Push buttons / pedestrian signals need walkers that cross the tracks at signalled crossings (`peds`
  above). That is game work, but the build can supply which crossing belongs to which signal.

### 2.7b Open data for signals, poles and markings (checked 2026-10-24)

**Found: surveyed street furniture points in Prague's technical map**
- **What:** layer "Archivní DTM Prahy – inženýrské sítě – povrchové znaky zobrazené symbolem" (open
  data hub item `d4418172a31b46b7b875668eaa354f22`, CC BY 4.0, "datový podklad © IPR Praha").
- **Service:** `https://mp.iprpraha.cz/arcgis/rest/services/Hosted/DTMP_CUR_TMISZNAK_B/FeatureServer/0`.
- **Status:** state as of 30 June 2024, no longer updated. Points, no heights.
- **Useful feature codes (`ctmtp_kod`):**
  - `605250` semafor (traffic signal heads: cars, pedestrians and **trams**), `605251` semafor on a
    building, `605161` světelné návěstidlo (light signal; none at Palackého náměstí);
  - `605240` **zastávka MHD** (the stop sign / post), `605241` on a building;
  - `606010` stožár, sloup (poles: lighting, catenary and signal poles are not told apart),
    `606021` lattice mast;
  - `606560` light on a pole, `606570` decorative light on a pole, `606561` light on a building;
  - `605270` traffic sign carrier (the sign type is not recorded), `605280` warning beacon,
    `606780` clock.
- **Checked at Palackého náměstí:**
  - the stop sign is ~3 m from our post, which matches OSM's stop position and the user's photo;
  - a semafor is ~1 m from the tram signal pole at the island's tip (the user's photo);
  - in a 170 × 200 m box: 19 semafor points, 4 stop signs, 30 poles, 29 lights on poles.
- **Fetch tool:** `tools/dtm_points.py N` writes `data/lineN.dtmpoints.json`
  (`{k, x, y}` in local metres, with the shared conversion). Move it into `tools/`.
- **Line 17 corridor (60 m around the route):** 3,326 lights on poles, 538 poles, 444 semafor,
  393 sign carriers, 86 stop signs, 70 lights on buildings, 59 warning beacons, 36 low-voltage poles,
  24 decorative lights, 8 lattice masts, 5 light signals, 5 clocks.
- **Coverage is patchy:** what earlier surveys recorded.
  - Stops matched to a surveyed stop sign right of our track: 21 of 37, 14 of them within 5 m of our
    stop (median 0 m). The others are 6–8 m off (Podolská vodárna, Výtoň, Čechův most, Veletržní
    palác, Líbeznická) or further (Nádraží Holešovice +28 m, Březiněveská −20 m).
  - Nothing at Hodkovičky, Levského or most of Modřany.
  - Around Národní divadlo the layer has 682 points (valves, manholes, 26 lights on poles) but no
    semafor and no stop sign near our track.
  - Use it as truth where present, not as the only source.

**Uses:**
- **truth for the rules:** stop posts, tram signal positions, car signal heads; the annotation scoring
  of ARCHITECTURE-PROPOSAL §10 can use these points as automatic truth;
- **placing poles and lamps** where they really stand instead of by rule: catenary poles near the
  track, street lights along streets;
- **which heads are tram signals:** a semafor near our track, facing along it, just before a
  conflict.

**Open questions:**
- **The successor:** since 2024 the regional DTM (Prague with the Central Bohemian Region,
  `portal.dtm-praha-sck.cz`, `map.dtm-praha-sck.cz`; nationally ČÚZK's IS DMVS) holds the current
  data. Whether it offers open downloads or WFS was not established. Contact at IPR for DTM data:
  `hribal@ipr.praha.eu` (from the Geoportál DTM page); general data requests: `vydej@ipr.praha.eu`.
- **The autorizovaná data správců layer** (`DTMP_CUR_TMISZNAK_ADS_B`, item
  `44e6148cd9c34542b1202525ebec06de`) may hold the network operators' own points (DPP traction poles?).
  Not checked.

**Not found as open data:**
- **No traffic signal installation dataset:** TSK reports ~610–684 signal installations, but no
  device or position dataset is published that I could find. Golemio may have real-time signal data;
  not confirmed.
- **No road markings dataset:** our survey file keeps only surfaces, and a public comment on the
  regional DTM decree notes that sign carriers are recorded but not the sign type. Options: OSM
  (`crossing=zebra` / `crossing:markings`, `highway=stop` lines are rare), or detecting zebra stripes
  in the orthophoto (high-contrast parallel stripes; feasible offline later).
- **OSM for poles:** `highway=street_lamp`, `power=pole` and catenary masts exist in OSM but coverage in
  Prague is patchy. The technical map is the better source.

### 2.7c Plan: fitting placement rules to the surveyed points (prototype done)

**Approach (agreed with the user):** fit the parameters of readable rules to the survey, not a black
box model.
- The rules stay explainable and work where the survey has holes.
- They are checked against the annotations (ARCHITECTURE-PROPOSAL §10).
- **Fit on some districts and test on others**, so the rules capture Prague practice rather than
  memorising one line.
- Older data is fine (streets change slowly). Where OSM or the orthophoto clearly disagree, the newer
  source wins.

**Step 1: label what each surveyed head is for.**
- **Prototype:** `tools/bench/heads.js`, run in the page during a shift (needs
  `data/lineN.dtmpoints.json`).
- Heads within 1.2 m are one pole. Each pole is labelled by context:
  - **tram:** within 6 m of our track and 0–25 m past one of our tram signals' stop points;
  - **car:** within 12 m of an OSM car stop-line node, not more than 6 m behind it;
  - **ped:** within 8 m of a signalled pedestrian crossing node;
  - otherwise **other**.
- **Line 17:** 444 heads on 433 poles (the survey records about one point per pole, not per head):
  145 car, 144 ped, 21 tram, 123 other.
  - Of the "other", 22 are within 6 m of our track: likely the opposite direction's tram signals, or
    crossings OSM lacks.

**Step 2: measure, then fit. First results on line 17:**

| | median | 10–90 % |
|---|---|---|
| car pole past the OSM stop line (along the approach) | **+4.2 m** | −0.7 … +7.1 m |
| car pole, sideways (right +) | +3.6 m | −7.2 … +7.2 m (both sides, islands) |
| ped pole to its crossing node | 4.0 m | 2.8 … 6.8 m |
| tram pole past the stop point (n = 21, labels uncertain) | +9.4 m | +2.3 … +11.9 m |
| tram pole, sideways from our track | +3.1 m | −2.8 … +5.9 m |

- **Applied:** car heads now stand 4 m past the stop line (`traffic._bindSignals`), never past the lane
  end.
  - Their distance to the nearest surveyed car pole: median 5.5 → **4.7 m**, 10th percentile
    3.0 → **0.7 m** (44 of 71 heads have a surveyed pole within 20 m).
  - The rest is mostly sideways: ours are always 2.2 m right of the lane, while real ones stand on
    both sides, on islands, and as repeaters across wide junctions. That is the next parameter to fit
    (per approach: left/right/both, by number of lanes and island presence).
- **Not applied:** tram signal placement. 21 samples with uncertain labels; the game's 16 signals with a
  surveyed tram pole within 20 m are a median 7.7 m from it. Annotate verdicts at a few junctions
  first, then fit.

**Step 3: poles and their roles (no data from the transport company, inferred).** From the user: tram
poles are separate from light poles in some places and shared in others; new stretches favour shared
poles; separate corridors use various styles, e.g. a single pole between the tracks. Inference:
- a pole 2–4 m from the track at regular spacing: catenary;
- with a surveyed light within ~1 m: shared;
- a light pole away from the track: lighting only;
- a pole between the two tracks: centre pole.

Compare with the catenary poles the game generates (`route.catenary`, `buildCatenary`) to fit spacing,
offsets and where each style applies; the rules then carry the style where the survey is silent.

**Step 4: street detail from the same layer** (cheap, visible from the cab):
- manhole covers, gutter inlets along the kerbs ("vpusť"), hydrants, valve caps;
- clocks, phone booths, transformer kiosks.

Draw them as instanced meshes or ground decals within ~150 m of the camera: a few draw calls.
Line 17 has thousands of such points; extend `dtm_points.py`'s code list. All codes with their
descriptions come from the service:
`…/DTMP_CUR_TMISZNAK_B/FeatureServer/0/query?where=1%3D1&outFields=ctmtp_kod,ctmtp_popis&returnDistinctValues=true&returnGeometry=false&f=json`
- e.g. `106300` vpusť (gutter inlet), `106200` kanalizační šachta (manhole), `406130` / `406120`
  underground / above-ground hydrant, `406140` water valve, `306140` gas valve, `736750` phone booth,
  `606650` transformer station, `408170` fountain.

### 2.7d Notes for future rebuilds (user, 2026-10-24)

**Track bed styles.** Tram track should eventually be built in its real styles: open ballast bed,
grassy bed, concrete panel sections, rails embedded flush in asphalt, set in paving stones (junctions),
and others.
- **Where the style could come from:**
  - the street survey's surface classes (it already tells `tram`, `road`, `green`, `paved` areas
    apart);
  - OSM tags on the tram ways (embedded rails / surface tags where mapped; coverage to be checked);
  - the orthophoto for verification.
- **It affects other things:**
  - covers in the track (manholes between the rails exist in embedded and paved track, rarely in open
    or grassy beds);
  - the track bed height the covers sit on (now track height + 0.16 m, `buildStreetDetail`);
  - adhesion, sound and the look from the cab.

**Cover and cap sizes:** pipe and valve caps are smaller than real manholes; now about 0.12 m and
0.2 m across. The user will supply reference photos of the cover types (manhole, gutter inlet, valve
and hydrant caps) for proper models and textures.

**IPR's 3D model of Prague.** The project uses the LOD2 buildings so far. IPR also publishes more
detailed 3D data, including a **photorealistic textured mesh** of the city (part of the "digital twin"
on the new Geoportál). Look at it at the next test rebuild:
- as a reference for heights, facades and street furniture;
- possibly as distant scenery or a source of facade textures.

Check the licence and the size per tile before planning on it.

**DTM exchange format change (notice on the Geoportál):**
- **The notice:** IS DMVS / IS DTM move to **JVF 1.5.0.2** (Jednotný výměnný formát).
  - Updates stop being accepted on **10 Nov 2026, 22:00** (the old JVF 1.4.3 submissions are
    rejected).
  - Full operation resumes on **18 Nov 2026, 23:59**, after which only JVF 1.5.0.2 is accepted.
- **Who it is aimed at:** surveyors and infrastructure owners **submitting** updates to the regional
  DTM.
- **Does it apply to our data?**
  - It does not affect what this session fetched: the **archived** DTMP layers over ArcGIS REST
    (`dtm_points.py`, frozen at 30 June 2024).
  - **Check `tools/dtm.py`** (the street surfaces, "Streets: DTM Praha"):
    - if it reads **JVF exports** of the current regional DTM (XML/GML), its parser must handle
      JVF 1.5.0.2 after 18 Nov 2026 (schema and element changes); test a fresh export then;
    - if it reads IPR's S-JTSK download packages or REST layers, only the content may change, not
      the format.
  - **Data frozen for a week:** expect no new survey updates between 10 and 18 Nov 2026; don't
    schedule a "fresh data" rebuild in that window.

### 2.8 Preprocessing for chunked loading (later)

See `PERF-ANALYSIS.md` §6. In short:
- ship the decisions and edits (terrain heights after lowering and carving, buildings already
  trimmed and classed, the DTM ground mesh simplified offline), not the finished meshes (~3x the
  download);
- 500 m tiles, ~0.1–0.2 MB each on average, ~1 MB in the centre;
- startup needs only the tiles within ~1 km of the start.

---

## 3. Validation the build should print (every line, every build)

| check | how | pass |
|---|---|---|
| conversion fit | OSM tram ways vs our tracks (§1.2) | median < 0.5 m |
| stops | distance of the stop point to the OSM `stop_position` on our track | list > 10 m |
| platform overlaps | crossing near edge < platform end | list all |
| crossings | each crossing has a footway geometrically crossing both tracks | list the rest |
| signal `cross` | a real track crossing within 40 m ahead of `s` | list the rest |
| signals on platforms | `s` between platform start and end | list (the client handles them; the data should not need it) |
| OSM stop nodes | matched to an approach lane (within 4.5 m, heading within ~45°) | report the count; list the unmatched near signalled junctions |
| one-way / missing approaches | a road with OSM stop nodes but no lane toward the junction | list |

---

## 4. Checks in the browser after a rebuild

Test on **line 17**: fine terrain plus the detailed survey. Line 22 is secondary until its world is
rebuilt at higher detail. Serve without caching (`tools/serve.py`, launch entry `tram` on port 8742;
`tram-slow` on 8744 limits each response to 1500 KB/s), because the browser otherwise keeps stale
modules.

### 4.1 Console log lines to read

- `signals placed: …`: each signal's move (`a→b`), `on demand`, `kept (its junction edge N m on)`
  (forward moves are capped at 25 m; anything kept is suspect), `dropped (…)`.
- `traffic lights: N car heads at M junctions (stop lines: X from OSM, Y at the junction edge)`.
  Line 17 now gives 72 heads, 53 from OSM.
- `footways: … ends open`, `doors: N of M buildings`.
- `load times (ms)`, `world build (ms)`: compare with `PERF-ANALYSIS.md` §1 and §7 (load ~21 s,
  heap ~680 MB on line 17).

### 4.2 Bench scripts (in the page, after loading, menu still open)

```js
const { run } = await import('/tools/bench/u3.js');      await run(1)   // also 2, 3
const { run } = await import('/tools/bench/redruns.js'); await run(1)   // result in window._res
const { run } = await import('/tools/bench/walkers.js'); await run(1)
```

Each drives the whole line headless with the autopilot (~3 min); reload the page between runs. The
harnesses keep the camera at the cab, because cars spawn around the camera. Expected on line 17
after REMOTE-CHANGES §17b (seeds 1/2/3):

| | expected |
|---|---|
| cars into lit junctions on red (`carsIntoJunctions.red`) | 0 |
| collisions with crossing cars (`hits`) | 0 |
| deadlocks (`stuck`) | null |
| our signal penalties (`signalPenalty`) | 0 |
| AI tram red runs (`redruns`, `red`) | [] |
| cars giving way to our tram (`yielded`) | ~45-60 |
| close cut-ins | 0-5 |

If anything fails, re-run that seed with `run(seed, {watch: s})` for the route position in the
collision or event record. That logs every car within 40 m of it while the tram approaches:
lane, speed, crossing seen, yielding.

### 4.3 Other tools

- **`tools/lint.js` must load the page with `?keepgeo`.** The player now frees the CPU copies of
  the geometry after upload; tools that read `window.world`'s meshes need them kept. `?bot`
  keeps them too.
- **`tools/traffic_lint.js`:**
  - re-baseline it: AI braking, signal decisions, give-way rules, crossing stops, spawn distance and
    walker heights all changed, so its counts move;
  - check that it moves the camera with the tram like the benches do;
  - check that it passes `?keepgeo` if it reads geometry.
- `src/world.js` was saved with LF line endings (it may have had CRLF); `terrain.js` still has
  CRLF. Normalize if the tools care.

### 4.4 Visual check of signals and stop lines

**Built in now:** press **F8** during a shift (or load with `?debug`). `src/debugOverlay.js` draws the
same markers as the snippet below and more: route conflicts, platform ends, passenger stop points.
For data checks without the game, run `python -P -E tools/osm_validate.py 17`, which covers §3
from the data files and a cached OSM download. For many seeds unattended, open
`tools/bench/batch.html` (REMOTE-CHANGES §18).

The manual snippet, for reference: load line 17, start a shift, then in the console:

```js
const inp = { throttle: 0, brake: 0, notch: 0, sand: false, bell: false };
for (let i = 0; i < 30; i++) game.update(0.05, inp);            // so the controllers have a state
window.freeCam = true; game.paused = true;
for (const id of ['top','assist','msgs','action','minimap','help','dash','inspectPanel','cab','mirror','pausePanel'])
  document.getElementById(id).style.display = 'none';
window._aerial = (s, back = 45, up = 60, side = 0) => { const R = game.route, q = R.at(s), o = R.offset(s - back, side);
  camera.position.set(o.x, game.profile.height(s) + up, -o.y); camera.lookAt(q.x, game.profile.height(s), -q.y);
  camera.fov = 55; camera.updateProjectionMatrix(); traffic.update(0.001, camera, true); };
const THREE = await import('three'), grp = new THREE.Group(); scene.add(grp);
const M = (c) => new THREE.MeshBasicMaterial({ color: c, depthTest: false });
const add = (g, m, x, y, z, ry = 0) => { const o = new THREE.Mesh(g, m); o.position.set(x, y, z); o.rotation.y = ry; o.renderOrder = 999; grp.add(o); };
const ball = new THREE.SphereGeometry(0.9, 10, 8), bar = new THREE.BoxGeometry(3, 0.2, 0.6), tbar = new THREE.BoxGeometry(5, 0.25, 0.6);
for (const l of traffic.lightLanes) { const q = l.path.at(l.path.length - l.light.back);       // car stop lines: cyan OSM, yellow edge
  add(bar, M(l.light.src === 'osm' ? 0x00ffff : 0xffee00), q.x, traffic.ground.surface(q.x, q.y) + 0.3, -q.y, Math.atan2(-q.hx, q.hy)); }
for (const s of game.signals) { const p = new THREE.Vector3(); s.mesh.getWorldPosition(p);   // tram signal (ball) and its stop point (bar)
  add(ball, M(0xff00ff), p.x, p.y + 1.5, p.z); const b = game.route.at(s.s - 3);
  add(tbar, M(0xff00ff), b.x, game.profile.height(s.s) + 0.3, -b.y, Math.atan2(-b.hx, b.hy)); }
for (const o of game.data.osmSignals?.stop || []) add(new THREE.SphereGeometry(0.6), M(0xff2020), o.x, traffic.ground.surface(o.x, o.y) + 1, -o.y);
_aerial(12435);   // Palackého náměstí; also 12719, 13363, 14636, 15587, 20361 (Kobylisy), 10261 (Kublov)
```

What to look for:
- tram signals (magenta) at or before their stop point and outside the junction, never on a span
  over it;
- car stop lines (cyan/yellow bars) at the junction mouth, before the zebra and clear of the
  tracks;
- red dots (raw OSM nodes) on the approach lanes. If the dots are offset from the roads, the
  conversion is wrong (§1.1).

---

## 5. Known issues to re-check after a rebuild

- Palackého náměstí: the tram stops 15 m before the platform end (crossing at 12353 in the data, §2.2).
- Palackého most approach unlit (no inbound lane, §2.5).
- Kobylisy side approaches unlit (§2.5).
- Stops off by more than 10 m from OSM: Právnická fakulta, Hercovka, Vozovna Kobylisy (§2.4).
- After §2.1–2.3 land in the build, the client's workarounds can stay as a safety net. They log what
  they do (`signals placed`), so a clean build should show few `kept` / `on demand` entries.
