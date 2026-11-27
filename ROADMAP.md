# Roadmap

The work is tracked in [GitHub issues](https://github.com/jnd-cz/prague-transport-sim/issues), one
milestone per architecture step ([docs/architecture.md](docs/architecture.md) §8). This file only says
what each milestone is for; the issues hold the tasks.

| Milestone | Goal |
|---|---|
| **M1 Hygiene** | Agent rules (AGENTS.md), headless benches (Python + Playwright), one coordinate module for every tool, seeded randomness, going public cleanly (licences, store details private). |
| **W1–W4** | The static world, one layer at a time (below); M2 "World compiler, line 17" is closed into them (2026-11-05). |
| **M3 Tiles and streaming** | One tram world built per tile and streamed around the player within a memory budget. |
| **M4 Track graph, several lines** | Vehicles on the track graph, one controller per junction, both directions drivable, line ends and depots. |
| **M5 Simulation tiers and Worker** | A deterministic fixed-step core without Three.js in a Worker; meso / macro tiers. |
| **M6 Buses and passengers** | Buses and trolleybuses on the lane graph; one passenger model. |
| **Backlog** | Realism and content not tied to a step: signals and traffic detail, sound, lighting, weather, assets, sources to obtain. |

## World checkpoints

The maintainer's plan of 2026-11-05: the static world is built bottom-up, one layer at a time on all five
lines, and each layer ends at a **checkpoint**: one run of every check on every line, a PR that explains
what moved, and a tag on main (`W1` …). Within a layer one branch rebuilds and publishes (the `rebuild`
label, AGENTS.md). The simulation lane waited for W2. GitHub's blocked-by links hold the order between
the issues.

| Checkpoint | The layer | Issues |
|---|---|---|
| **W1 Track network** | DI's chain graph as the network, the routes map-matched over it, all five lines | [milestone W1](https://github.com/jnd-cz/prague-transport-sim/milestone/8) |
| **W2 On the track** | the top-of-rail profile on all lines, the stop signs, the speed limits, placement rules and validation in the build; one rebuild at the end | [milestone W2](https://github.com/jnd-cz/prague-transport-sim/milestone/9) |
| **W3 The ground** | one ground surface built offline: survey, track beds, building plots and terrain; before it, the OSM2World study (#15) | [milestone W3](https://github.com/jnd-cz/prague-transport-sim/milestone/10) |
| **W4 Structures and scenery** | passages, bridge decks, railway tracks; the feature layer, buildings, street furniture, power data | [milestone W4](https://github.com/jnd-cz/prague-transport-sim/milestone/11) |

**W1 is done** (2026-11-06, #341): every check on every line is stored as checkpoint W1, measured on commit a3b4652, the tag `W1`.

**W2 is done** (2026-11-09, #414): every check on every line is stored as checkpoint W2, measured on commit d2c105c, the tag `W2`. The simulation lane resumes from it.

**W3 is done** (2026-11-19, [#731](https://github.com/jnd-cz/prague-transport-sim/issues/731)). The store holds the five-line checkpoint for the offline ground. The tag `W3` names the measured commit, `0a0a3b0`.

## After W3

The first public target is a T3 that can drive the whole Prague tram network in one world. Passengers need connected walks, stops and boarding. The work follows the order agreed in [#731](https://github.com/jnd-cz/prague-transport-sim/issues/731).

**First, the fused ground**, stable and free of issues as the immediate goal, with faster iteration over specific problem places ([#757](https://github.com/jnd-cz/prague-transport-sim/issues/757)). A ground rule is tried on named places, each built alone in about a minute (`tools/ground_place.py`, `data/truth.json` `groundPlaces`); the open ground issues are fixed through them and the lines rebuilt once for the batch. The loop is in place and #757 closed on batch E (2026-11-27); each later batch has its own issue, which holds `rebuild` ([batch F](https://github.com/jnd-cz/prague-transport-sim/issues/885)). A tile's ground is made to depend on the tile and its neighbours only, which step 2 builds on.

1. Make the existing build and checks reliable. Cache the ground and its dependent network together, identify their build, and measure raster error when the change calls for it. [Build integrity](https://github.com/jnd-cz/prague-transport-sim/issues/702) · [Raster checks](https://github.com/jnd-cz/prague-transport-sim/issues/704)
2. Agree on identities for track edges, areas and routes. Build the ground and lightweight network once per city tile, stream them around the player, and compare a streamed drive with the pinned five-line world. The five lines currently list 854 ground tiles at 561 distinct positions. [City data model](https://github.com/jnd-cz/prague-transport-sim/issues/714) · [City build](https://github.com/jnd-cz/prague-transport-sim/issues/715) · [Player-load check](https://github.com/jnd-cz/prague-transport-sim/issues/710)
3. Meet the load and frame-time budgets on weaker machines, then drive either direction over connected track edges, through termini and junctions. [Rendering budget](https://github.com/jnd-cz/prague-transport-sim/issues/705) · [Driving on the graph](https://github.com/jnd-cz/prague-transport-sim/issues/32)
4. Move the simulation core out of the renderer. Extend the track model to city railways, then add buses and trolleybuses on the road graph. Crossings, footways and stop access serve the passenger model across modes. [Simulation core](https://github.com/jnd-cz/prague-transport-sim/issues/722) · [Railways](https://github.com/jnd-cz/prague-transport-sim/issues/65) · [Footway network](https://github.com/jnd-cz/prague-transport-sim/issues/683) · [Passengers](https://github.com/jnd-cz/prague-transport-sim/issues/40)

The issue order within each step is recorded in [#731](https://github.com/jnd-cz/prague-transport-sim/issues/731). The small build and check fixes also include #701, #703, #708, #709, #711, #707 and #713. The city build incorporates the first two steps of #30, coverage in #712 and moving ground generation out of the runtime in #720. #706 and #723 accompany the rendering budget. Graph driving continues through #34 and #35 before #33. The simulation split continues with #226, #228 and #560 with #566 before #37. #69 accompanies the railway work and #249 the passenger model.

Vehicle and package work is tracked in #724–#726. Build-tool maintenance is tracked in #716–#719, and the working rules and tooling in #727–#729, #721 and #730.

The remaining ground work has two inputs to the city build. Streets outside survey coverage supply junction polygons and their sidewalks share the carriageway kerb ([streets](https://github.com/jnd-cz/prague-transport-sim/issues/301), [sidewalks](https://github.com/jnd-cz/prague-transport-sim/issues/302)). Where two surfaces meet at different heights, check both sides on the decoded mesh at the acceptance places (`data/truth.json` `groundPlaces`). The Rašínovo quay (#697) and the raised garden (#663) hold since batch E; the [Krejcárek ramp](https://github.com/jnd-cz/prague-transport-sim/issues/653) is open, as are the track's height against the roads beside it ([#876](https://github.com/jnd-cz/prague-transport-sim/issues/876)) and the areas on their own outline ([#638](https://github.com/jnd-cz/prague-transport-sim/issues/638)).

W4 scenery and the remaining Backlog wait until the tram city runs. The lane lists keep off-path findings for the next checkpoint. [World findings](https://github.com/jnd-cz/prague-transport-sim/issues/732) · [Asset findings](https://github.com/jnd-cz/prague-transport-sim/issues/734)

History of how the project got here: [docs/history/ at 35133a2](https://github.com/jnd-cz/prague-transport-sim/tree/35133a2/docs/history), the last commit that has them (not maintained).
