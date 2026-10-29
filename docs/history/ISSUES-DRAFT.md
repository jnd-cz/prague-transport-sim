# Issue draft (reviewed; on GitHub since 2026-10-29)

**Superseded by the GitHub issues** (jnd-cz/prague-transport-sim #1–#71); draft id → issue number in
`reports/issue-map.json`. Item 6 (going public, licence) waits for the licence choice. Kept for history.

Collected from PLAN.md (§1, §3), HANDOFF.md (§16–26), REMOTE-CHANGES.md, BUILD-TOOLS-HANDOFF.md,
ARCHITECTURE-PROPOSAL.md, TRACK-DATA-DECISION-2026-10-27.md, TERRAIN-REBUILD-HANDOFF-2026-10-29.md.
Done items are left out. Mark each line: keep / drop / merge / change, then I create them.

## Proposed labels

- **kind:** `bug` · `feature` · `data` (source or data quality) · `research` · `tooling` · `docs`
- **area:** `engine` (sim core, tram, autopilot) · `traffic` (cars, AI trams) · `pedestrians` · `signals` ·
  `stops` · `track` (geometry, profile, switches) · `structures` (bridges, tunnels, walls) · `terrain` ·
  `streets` (survey surfaces, lanes) · `scenery` (buildings, trees, furniture) · `vehicle` (models,
  plates) · `audio` · `ui` · `build` (pipeline, compiler) · `data-store`
- **where:** `line-9` · `line-17` · `line-22` · `line-23` · `line-37` · `network` (all / city-wide)
- **flags:** `from-user` (your observation or fact) · `recheck-after-rebuild` (likely changes with the new
  world; verify instead of fixing now) · `good-first`

## Proposed milestones (the architecture order, ARCHITECTURE-PROPOSAL §8)

- **M1 Hygiene**: conventions, shared modules, headless tests, CI.
- **M2 World compiler, line 17**: semantic model, rules in the build, validation report, new sources.
- **M3 Tiles and streaming**.
- **M4 Track graph, several lines, junction controllers**.
- **M5 Simulation tiers and Worker**.
- **M6 Buses, passengers, other modes**.
- **Backlog**: realism and content not tied to a step.

---

## M1 Hygiene

1. **CLAUDE.md: rules for every session and agent** — `docs`, `tooling`. Serving, data fetch, test lines,
   benches and expected results, branch per issue, commit/PR conventions, "never edit generated data",
   shared geo module, heuristics log their decisions, comment style.
2. **Headless benches from the command line (and later CI)** — `tooling`. Python + Playwright (agreed
   2026-10-29): run tools/bench (u3, redruns, walkers) and tools/lint.js in headless Chromium with fixed
   seeds, collect JSON, compare with thresholds. Deno or Node only when the simulation core is split out
   (M5).
3. **Every build tool on tools/geo.py** — `tooling`, `build`. build_line, platforms, clearances,
   fine_terrain, dtm, streets, geoportal, osm_speeds still carry their own (identical) conversion.
4. **Type checking of the game code** — `tooling`. JSDoc types + a checker (needs Deno or Node: with M5).
5. **Line endings and formatting** — `tooling`, `good-first`. .gitattributes rules (LF in the repo),
   one formatter config for JS and Python.
6. **Going public cleanly** — `docs`, `data-store`. Store host and port out of the tracked docs (shared
   privately); history scrubbed of them and of the old `data/` blobs before the repo is public; a code
   licence and a data attribution notice (OSM ODbL, IPR / ČÚZK / DTM CC BY, PID CC BY).
7. **Seeded randomness everywhere** — `engine`. No `Math.random` in the simulation (the benches override
   it today); one seeded RNG per run.

## M2 World compiler, line 17 (the rebuild)

To agree before the rebuild (your notes, 2026-10-29):
2a. **One city-wide frame: S-JTSK (EPSG:5514) metres, Bpv heights** — `build`, `track`, `from-user`. The
    per-line frame (110 574 m per degree of latitude, 111 320·cos lat0 per degree of longitude) squeezes
    the world 0.59 % north–south and 0.20 % east–west: line 17 is 100 m short (21 699 m vs 21 799 m), its
    N–S extent 86 m short over 14.5 km; every line has its own origin, so two lines' worlds do not
    meet. The build works in S-JTSK (native for DTM, IPR, ČÚZK; OSM converted with pyproj, the official
    correction grid for cm accuracy), the game in metres from one fixed city origin (per-tile offsets for
    precision). Replaces #26.
2b. **Layer registration check** (the "misplaced layers like trees"): every layer against the
    orthophoto / survey after the frame change (trees, buildings, OSM ways, poles), with a lint per layer
    — `data`, `scenery`, `from-user`.
2c. **What each height means** — `track`, `streets`, `from-user`: terrain (bare earth), street surface,
    deck top, top of rail; one vertical datum (Bpv; IPR raster's datum to confirm). The track ribbon is
    drawn 0.20 m (bed) and 0.26 m (rails) above the track reference: define the reference as top of rail
    and draw rails and bed down from it, terrain and street flush at the bed (merges #11).
2d. **Source per layer, with fallbacks and provenance** — `build`, `data`, `from-user`: terrain IPR 1 m →
    DMR 5G → coarse; streets current ZPS → archived DTMP → OSM widths; tracks current DTM centrelines →
    archived DTMP → OSM (reviewed); structures survey decks → Mosty 3D → OSM tags; furniture survey
    points → OSM → rules. Every built feature carries its source, date and fallback level.
2e. **Výtoň study conclusions into the build** — `build`, `streets`, `from-user`: surfaces on several
    levels (quay, embankment street, bridge, underpass), railway tracks (on their bridge) and footpaths on
    their own level, steep terrain features from terrain edges and walls (no smoothing across them).
2f. **Wavy and arching roads and paths: root cause first** — `streets`, `research`, `from-user`: per stage
    snapshots of the same street vertices (survey → street fit → flushDtm → carve → drawn), then a revised
    smoothing that never crosses a breakline or a level (merges #12).
2g. **Bridges: the surveyed deck surface has priority** — `structures`, `from-user`: the model contributes
    what is below the deck (girders, piers, sides) and its raised edges as parapets / railings; a clean
    planar cut instead of today's dropped triangles (the rough cutaway).
2h. **Feature layer for placed objects** — `build`, `scenery`, `from-user`: one metadata layer of placed
    features (benches, lamps, signals, shelters, signs, bins, covers …) with position, heading, level,
    source and an asset reference; the game draws what it has assets for, placeholders otherwise; assets
    added as they come.
2i. **OSM2World study** — `research`, `from-user`: how it builds roads with lanes, junction areas,
    street furniture from tags and models; what to take (approaches, tag coverage, asset conventions).
    Inspiration only unless its licence fits.
2j. **Road and footpath networks with smooth continuation across junctions** — `traffic`,
    `pedestrians`, `from-user`: junctions as areas, lanes and footways joined by curved connectors
    instead of a common node with tight turns; footway links without tiny pieces (ties in with #36).
2k. **Visual review of the networks** — `tooling`, `from-user`: drivable lanes, connectors and walkable
    ways drawn as an overlay (F8) and in the annotation map, with the flags from the lints.
2l. **Covers and caps at their usual sizes, reviewed on a pilot area** — `scenery`, `from-user`: revert
    the reduced valve (0.12 m) and hydrant (0.2 m) caps, look again at the pilot.
2m. **Pilot areas for the rebuild** — `build`: Výtoň (levels, quay, railway bridge), Kobylisy – Vozovna
    (track spacing, endpoint), Palackého náměstí (stop, signals, crossings), Trojský most (bridge, tunnel
    mouth); line 17 in full after them.

Sources and decisions:
8. **Track centrelines from the current DTM transport layer** — `data`, `track`, `build`.
   TRACK-DATA-DECISION: prefer current DTM tram centrelines, older technical map and OSM fill reviewed
   gaps; provenance per geometry and per height; switches and topology kept. Needs the district
   packages (transport infrastructure set 7) in a snapshot.
9. **Terrain from IPR's 1 m lidar raster (DMR 5G as fallback)** — `data`, `terrain`. TERRAIN-REBUILD
   handoff; vertical datum and capture date to confirm; adaptive mesh / constrained TIN offline.
10. **Level-aware street surfaces from the current ZPS (KR, PB, OPL)** — `data`, `streets`. Breaklines
    (kerbs, walls, terrain edges), no smoothing across levels; quay vs street vs deck vs tunnel.
11. ~~Decide the height reference~~ (merged into #2c) (Bpv vs EVRS, what each height measures, rail / bed / street
    offsets) — `research`, `track`. The +0.26 m rail and +0.20 m bed lifts are rendering offsets to
    revisit with the new model.
12. ~~Pipeline stage that finds which runtime step causes road waviness~~ (merged into #2f) (flushDtm, carve, street fit)
    — `research`, `streets`. Before replacing them (TERRAIN-REBUILD next step 3).

Compiler:
13. **Semantic model**: track graph, road lane graph, footway graph; stops, platforms, signals,
    crossings, doors as features on network edges with offsets — `build`.
14. **Placement rules move into the build** (`_placeSignals`, platform rule, `_stopLine`, `_bindSignals`,
    Vienna stop detection), the runtime keeps them as logged fallbacks — `build`, `signals`, `stops`.
15. **Validation report on every build** (BUILD-TOOLS §3: conversion fit, stops vs OSM, platform
    overlaps, crossings geometrically crossing both tracks, signal `cross`, OSM stop nodes vs lanes,
    missing approaches) — `build`.
16. **`lineN.built.geojson` from the build** (ARCHITECTURE §10.4 format, stable ids) — `build`.
17. **Crossings validated geometrically** (71 of 136 on line 17 have no OSM tram crossing; road-only
    crossings inside platforms) — `data`, `build`, `line-17`.
18. **Signal `cross` from the first real track crossing ahead**, grade-separated signals dropped in the
    build — `build`, `signals`.
19. **OSM signal import into build_line** (osm_signals.py → build; way ids for stop nodes) — `build`.
20. **Run numbers per trip (`data.runs`)**: PID GTFS block / run reference, else enthusiasts' lists;
    night runs single cars — `data`, `vehicle`.
21. **Doors and entrances from OSM** (entrance=*, subway_entrance) as walker spawns — `data`,
    `pedestrians`.
22. **Annotation editor + scoring** (ARCHITECTURE §10): truth / verdict / override, reviewed areas, ~20
    hand-checked places on line 17 as the first reviewed area — `tooling`, `build`.

Regressions to recheck on the rebuilt world (one checklist issue, `recheck-after-rebuild`, `from-user`):
23. **Rebuild regression checklist, line 17**:
    - Kobylisy – Březiněveská: both centrelines, spacing 3.5 m, no lateral kinks; Vozovna Kobylisy
      endpoint height;
    - Trojský most and the stretch after it: sloped roads, tunnel mouth (HANDOFF §24);
    - tunnel mouths' look (Letenský tunel) — waits for the fine terrain;
    - Štefánikův most, Čechův most ends, Nádraží Modřany overpass: decks vs models (deckClip 7);
    - Krejcárek viaduct lower end 1–2 m over the deck (line 37);
    - roads arching by the water at Podolská vodárna / Výtoň (B1);
    - Palackého náměstí stop and signal (REMOTE §18), Kublov, Staroměstská, Přístaviště;
    - signals kept short of the next conflict: 9729, 11050, 19718 (HANDOFF §26);
    - stops > 10 m from OSM: Právnická fakulta, Hercovka, Čechův most, Výstaviště;
    - Palackého most approach unlit (no inbound lane), Kobylisy side approaches unlit.

## M3 Tiles and streaming

24. **Preprocessed world tiles (500 m)**: ship decisions and edits, not finished meshes (PERF §6) —
    `build`, `engine`.
25. **Streaming loader with a GPU memory budget and LOD** — `engine`.
26. ~~City-wide coordinate frame~~ — moved to #2a.

## M4 Track graph, several lines

27. **Vehicles on (edge, offset)**, lines as paths over the graph, switches set by route requests —
    `engine`, `track`.
28. **One controller per junction** (trams of several lines, car and pedestrian heads, detectors,
    buttons) — `signals`.
29. **Both directions drivable** (symmetric track spacing, every placement follows) — `track`, `stops`.
30. **Line ends and depots** (terminus loops, layovers, depot runs; Vozovna Žižkov) — `track`, `network`.
31. **Sídliště Řepy: platforms per track and line** (C2) — `stops`, `line-9`, `from-user`.

## M5 Simulation tiers and Worker

32. **Fixed-step deterministic core without Three.js, in a Worker** — `engine`.
33. **Meso / macro tiers with state handoff** (delay, load, run number keep across tiers) — `engine`.

## M6 Buses and passengers

34. **Buses / trolleybuses on the lane graph** — `traffic`.
35. **One passenger model** (demand from timetable + land use, transfers) — `engine`.

## Backlog — engine and traffic (survive the rebuild)

36. **Walkers hop at footway joins** (slides ~1.5 m / 0.2 s repeating in place; seed 22 4 671; jumps
    892 → 284 after the side fix) — `bug`, `pedestrians`, `line-17` (after the rebuild, per your call).
37. **Walkers crossing the tracks at signalled crossings with push buttons** (on-demand tram signals
    get random requests today) — `feature`, `pedestrians`, `signals`.
38. **Pedestrian heads snapped to surveyed poles; walking / standing figures; blinking green** —
    `feature`, `signals`.
39. **Car heads on both sides / islands / repeaters (fit the sideways parameter to the survey)** —
    `feature`, `signals`.
40. **Turn arrows and turn phases for cars; the old `_crossTraffic` cars retired** — `feature`,
    `traffic`, `signals`.
41. **Lanes of different roads that touch (line 22: 45); turn lanes; orthophoto lane check** —
    `traffic`, `streets`.
42. **Vienna-type stops: the raised lane; cars stop behind a tram with open doors** — `feature`,
    `stops`, `traffic`, `from-user`.
43. **Snow: on trams and cars; traffic slower; icy junctions; temperature tied to the weather** —
    `feature`, `engine`.
44. **traffic_lint re-baselined after the merge; lint `signalsInPlatforms` updated for platform-head
    signals** — `tooling`.

## Backlog — content and realism

45. **Tram sound from samples / recordings** (motor and resistor steps, compressor, brakes, doors,
    bogies over joints, curve squeal; cab vs outside; your samples) — `feature`, `audio`, `from-user`.
46. **Time of day and lighting** — `feature`, `engine`.
47. **Track bed styles** (ballast, grass, panels, embedded asphalt, paving) from survey classes / OSM;
    covers in the track only where they occur — `feature`, `track`, `scenery`.
48. **Street detail models from your photos** (manholes, gutters, valve and hydrant caps, phone booths,
    transformers, fountains); street lights and catenary poles from the survey points — `feature`,
    `scenery`, `from-user`.
49. **Bridges as models by type** (stone arches, steel arch, viaduct) — `feature`, `structures`.
50. **Buildings: real types (RÚIAN), facades with window bays, street-facing detail; IPR's photoreal
    mesh as reference or far scenery** — `feature`, `scenery`.
51. **Street-level imagery as truth** (Mapillary detections, Panoramax) — `research`, `data`.
52. **Missing structures**: Výstaviště railway overpass (A4), Pobřežní cesta pedestrian underpass (A6),
    Karlovy lázně passage both directions (A7) — `data`, `structures`, `line-17`,
    `recheck-after-rebuild`.
53. **Survey layers not used yet** (with #2e): walls with heights, terrain edges, railings, guardrails, tunnel
    floors (B2) — `data`, `streets` (likely part of #10).
54. **Dispatcher operations**: delays, short turns, diversions, disruptions — `feature`, `engine`.

## Research / sources (snapshot inputs to obtain)

55. **Výtoň sample archive** (vyton-terrain-sample.zip: IPR 1 m crop, DMR 5G LAZ, full Praha 2 ZPS
    KR/PB/OPL, archived DTMP extracts) — `data`, from you.
56. **Current DTM transport-infrastructure packages** (tram centrelines per district) — `data`.
57. **IPR original 2023 lidar / finer DEM / breakline TIN**: ask IPR (vydej@ipr.praha.eu) — `research`.
58. **DTM successor (regional DTM) open downloads; JVF 1.5.0.2 format change 10–18 Nov 2026** —
    `research`, `data`.
59. **Traffic signal installation data (TSK / Golemio)** — `research`, `signals`.

---

## Docs cleanup proposal (for the same review)

Today: PLAN.md (§1 current, §2–7 history), HANDOFF.md (26 log sections), REMOTE-CHANGES.md,
BUILD-TOOLS-HANDOFF.md, PERF-ANALYSIS.md, ARCHITECTURE-PROPOSAL.md, two decision docs,
COMMIT-MAP, ISSUES (this). Proposal:

- **Root, current:** `README.md` (run, build, play), `DATA.md` (snapshots and store), `CLAUDE.md`
  (agent rules), `ROADMAP.md` (short: milestones and their goals, links to issues).
- **`docs/architecture.md`**: ARCHITECTURE-PROPOSAL.md, kept current as the design.
- **`docs/decisions/`**: dated decision records: the track source (2026-10-27), the terrain study
  (2026-10-29), the data store and snapshots (2026-10-29), "no Overpass", Overpass/OSM local, …
- **`docs/knowledge.md`**: the gotchas and findings worth keeping from HANDOFF (data quirks per source,
  coordinate rules, what each lint measures, why the main heuristics exist) — rewritten short.
- **`docs/history/`**: HANDOFF.md, PLAN.md, REMOTE-CHANGES.md, BUILD-TOOLS-HANDOFF.md, PERF-ANALYSIS.md,
  COMMIT-MAP as they are (searchable, not maintained).
- Every open item lives only in an issue; docs link to issues instead of listing tasks.
