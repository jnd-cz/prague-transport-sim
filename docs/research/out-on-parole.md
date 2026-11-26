# Out on Parole: ideas from a small procedural city game (2026-11-26)

https://github.com/shaydex-codes/outonparole is a GTA-style open-world game in C with raylib: one commit (2026-11-23),
about 400 KB of source, a single binary under 1 MB. **It has no licence**: ideas only, no code. Read through the GitHub
API; nothing was cloned or run. Each claim about our own code below was checked against main `e040f22`.

Their city is a 10 × 10 street grid generated once at start (`world_build`). The lines are spaced at random, 0.86-1.14 of
the mean, and each block is typed from a small layout table. Everything is uploaded once; there is no streaming, LOD or
memory budget. Up to 96 cars (48 moving and 12 parked as targets) and 110 walkers (45 as the target).

## Traffic and walkers (lane:sim)

1. **Car following: the Intelligent Driver Model per obstacle** (`idm()` in car.c).
   - Every obstacle is a virtual leader with its own standstill gap: a car 2.0 m, a red light 0.5 m, a walker 1.5 m, a
     dead end 1.0 m. A car takes the least acceleration over all of them.
   - The constants: 2.0 m/s² up, 3.0 m/s² comfortable braking, exponent 4, headway 1.15 s.
   - Ours: `following()` (`src/traffic.js` ~116) is linear in the gap, `min(vLead + (gap - 8) * 0.4, (gap - 3.5) * 0.9)`,
     and `_approach` eases at fixed rates. The minimum over obstacles is already there (`terms`, ~921), so IDM fits in
     term by term. Its constants must be calibrated against Prague data first; the seeded baselines will move.
   - The cap before slower stretches ahead, sqrt(v² + 2·3·d), we already have (`vCurve`, ~890).
2. **Start-up delay at green and the yellow rule.** A car that waited at red moves off 0.35-0.95 s after green, so a
   queue discharges through the following model at a realistic rate. On yellow a car stops only if it can at 4 m/s²
   (v² / 8 < distance to the line). traffic.js has neither; both would draw from `src/random.js`.
3. **Spread per driver and walker.** Desired speed ×0.88-1.12 per driver. Per walker: a pace of 1.15-1.65 m/s, a
   sideways offset of 0.3-0.9 m on the footway, a 5 % chance of standing 3-9 s at a node, 8 % spawned as a talking
   pair for 25-70 s. For the walkers in traffic.js and `src/people.js`, taken from the agent's id so seeded runs compare.
4. **Parked cars as sleeping instances.** Placed by stepping sideways to the kerb 3.3-8 m out; a still car sleeps after
   1 s and costs nothing until touched. Prague streets are lined with them: OSM's `parking:lane` tags or IPR's
   paid-parking sections (`prague-open-data-transport.md`) could place them as static instances in `src/cars.js`.
5. **Round-robin despawn checks**, one car per tick (`ticks % MAX_CARS`), so the cost stays flat as the city grows.
6. **Gait phase shared across walk, jog and sprint clips**: each clip's offset is found once at start-up (the frame of
   the left foot's furthest reach) and playback runs at speed over the clip's own speed, clamped 0.5-1.7. For
   people.js if walkers blend between gaits.

Not for us: deadlock fixes by array order, ignoring crossing cars after 7 s blocked, reversing out, despawning wedged
cars (our waits-for graph, #560, is the principled version; despawn could at most be a logged last resort); spawning
outside the camera's view (it breaks seeded runs; our ring round the tram's front and `FADE` do that job); turns chosen
at random, 62 % straight on (per-street volumes, #864, should replace that); rigid-body physics with tyre curves and
damage; CPU skinning with one draw call per walker (people.js's instanced figures are ahead).

## The network's shape (lane:world, the city data model)

7. **Junction movements as lanes of their own.** A lane is one segment with up to 3 next lanes, a speed and the signal
   group at its end. Lanes along a street stop 4.9 m short of a junction; `connector()` fills the gap with one straight
   lane, or a turn as a Bézier curve cut into 3 pieces (right) or 4 (left), each its own lane, at 6.5 / 7.5 m/s. Which
   lane may turn is decided once at build time. For us: junction movements stored as edges of the city graph, each with
   its speed and signal, so nothing of a junction's geometry is worked out at run time (traffic.js `_fitRoad` does that
   today). Tram tracks fit the same scheme.
8. **A walking graph whose crossing edges carry their signal group.** Two nodes per junction corner on the kerb, long
   sidewalks cut every 20 m, a crossing as an edge tagged with its signal group; walkers cross only when their road is
   red and the crossing road green. Cars and walkers read one signal state. For `src/pedestrianCrossings.js` and people.js.
9. **One flat grid index for every "what is near" query**: 64 × 64 cells of 32 m, built in two passes as a prefix sum
   and an item list, with a stamp array instead of clearing between queries. No allocation per frame; a natural index
   per tile once tiles stream (#30, #31).

Not for us: fixed-cycle signals (33 s, 12 s green, 3 s amber, with no detectors and no tram priority; our controller is
already richer); a fixed 4 m sidewalk ring with a 0.10 m kerb; analytic ground height; axis-aligned collision boxes.

## Drawing and frame time (lane:assets, #705)

10. **Night.** We have none (`src/panel.js` notes "no night yet"; main.js has one hemisphere light, one directional
    light and a flat background). Theirs follows the sun's elevation: sky top and horizon, sun or moon colour, ambient,
    fog, exposure, all blended by smoothsteps over the elevation, and one night value every shader reads. That fits
    `applyWeather`'s table as an hour axis, at no cost per fragment.
11. **Lit windows without new textures.** The façade texture's alpha is the glass mask; the shader hashes the window
    cell (`floor(uv * cells)`) with the building's seed and lights the window when the hash is under 0.4 × night, in one
    of four warm or cool tints; by day the same mask adds a sky reflection with Fresnel. `src/buildings.js` tiles one
    window per texture repeat, so the cell is `floor(vUv)`: a glass alpha in the façade canvases and an `onBeforeCompile`
    patch like `weatherize` in `src/weather.js`. No extra draws.
12. **Street lamps as uniforms.** At night only, the 32 lamps nearest the camera within 110 m (21 m radius each) go to the
    shader as vec4s; the loop sits behind a night check, falloff (1 - q)², overlapping pools compressed. Moving lights
    the same way: the 24 nearest of up to 72 candidates. For us capped at 8-16 on weak GPUs, from `src/lamps.js` and
    street lights from OSM, patched into groundDraw.js's and buildings.js's materials.
13. **Markings without a logarithmic depth buffer.** Road paint is pulled towards the camera in the vertex shader
    (z -= w·3e-6) on a plain 24-bit depth buffer at near 0.25 m, far 2800 m. Ours is near 0.3 m, far about 950 m with
    `logarithmicDepthBuffer: true` (`src/main.js:179`), one of #705's suspects: the pull on the paint and rail layers
    would let it go.
14. **Shader work behind a uniform check.** The lamp loop runs only when night is on; every fragment takes the same
    branch. For #705: weather.js's two noise octaves (~83) behind `uSnow > 0`.
15. **Signal lamps from a state texture.** Each lamp is static geometry flagged with its group; the shader reads the
    group's state from a one-row texture updated each frame, so a change costs no instance update. Ours: models.js
    `makeTrafficLights` re-uploads its colour buffer per change. Minor now, useful city-wide.

Not for us: one shader and a texture array for all static geometry (fewer draws, but #705 finds draws are not the limit
on the weak machines); HDR bloom, ACES, FXAA and a 4096² shadow map over 160 m (too much fill for Intel HD and Vega; if we
ever add shadows: snap the map to texels and centre it ahead of the camera); a procedural sky with fbm clouds (the
gradient alone would be cheap); one draw per car with lamp codes in the vertex alpha (cars.js's instancing is ahead).

## Sound and camera (lane:assets)

16. **Street sound.** `src/audio.js` synthesises only our tram. Theirs is a software mixer:
    - the 6 nearest engines as live sources, plus 48 one-shot voices; a new sound replaces the voice of lowest
      priority × gain when all are busy;
    - gain (min / d)^1.25 faded to zero over the last 30 % of the range; a low-pass at 18000 / (1 + d / 12) Hz,
      floor 900 Hz, for air; equal-power pan; Doppler clamped 0.8-1.25;
    - an engine from firing pulses with jitter, its exhaust filter opening with rpm and load;
    - two low-passed noise beds for the street, a small reverb and a limiter on the master.
    In Web Audio: BiquadFilter and StereoPanner per near car, a pooled voice list, a noise bed, a DynamicsCompressor.
17. **Camera.** Every follow eases by 1 - exp(-k·dt) (horizontal 16, vertical 6, so bumps do not bob the view); shake is
    capped, decays by exp(-4·dt) and moves only the drawn matrices, never the game's camera. For the outside views and
    rail joints or crashes; the cab view stays as it is.
18. **Model preparation** (tools/prep_cars.py, in Blender): decimated to fixed budgets (body 1850 triangles), the
    texture baked into vertex colours, wheels replaced by a 16-segment lathe, the origin on the ground under the
    wheelbase's middle. For the far car models if the assets lane redoes them.

The cheapest wins: 2-3 (sim), 11 and 13-14 (looks and frame time).
