# Roadmap

The work is tracked in [GitHub issues](https://github.com/jnd-cz/prague-transport-sim/issues), one
milestone per architecture step ([docs/architecture.md](docs/architecture.md) §8). This file only says
what each milestone is for; the issues hold the tasks.

| Milestone | Goal |
|---|---|
| **M1 Hygiene** | Agent rules (AGENTS.md), headless benches (Python + Playwright), one coordinate module for every tool, seeded randomness, going public cleanly (licences, store details private). |
| **W1–W4** | The static world, one layer at a time (below); M2 "World compiler, line 17" is closed into them (2026-11-05). |
| **M3 Tiles and streaming** | Preprocessed world tiles; a streaming loader with a memory budget and LOD. |
| **M4 Track graph, several lines** | Vehicles on the track graph, one controller per junction, both directions drivable, line ends and depots. |
| **M5 Simulation tiers and Worker** | A deterministic fixed-step core without Three.js in a Worker; meso / macro tiers. |
| **M6 Buses and passengers** | Buses and trolleybuses on the lane graph; one passenger model. |
| **Backlog** | Realism and content not tied to a step: signals and traffic detail, sound, lighting, weather, assets, sources to obtain. |

## The world first, one layer at a time

The user's plan of 2026-11-05: the static world is built bottom-up, one layer at a time on all five
lines, and each layer ends at a **checkpoint**: one run of every check on every line, a PR that explains
what moved, and a tag on main (`W1` …). Within a layer one branch rebuilds and publishes (the `rebuild`
label, AGENTS.md). The simulation lane waits for W2. GitHub's blocked-by links hold the order between
the issues.

| Checkpoint | The layer | Issues |
|---|---|---|
| **W1 Track network** | DI's chain graph as the network, the routes map-matched over it, all five lines | [milestone W1](https://github.com/jnd-cz/prague-transport-sim/milestone/8) |
| **W2 On the track** | the top-of-rail profile on all lines, the stop signs, the speed limits, placement rules and validation in the build; one rebuild at the end | [milestone W2](https://github.com/jnd-cz/prague-transport-sim/milestone/9) |
| **W3 The ground** | one ground surface built offline: survey, track beds, building plots and terrain; before it, the OSM2World study (#15) | [milestone W3](https://github.com/jnd-cz/prague-transport-sim/milestone/10) |
| **W4 Structures and scenery** | passages, bridge decks, railway tracks; the feature layer, buildings, street furniture, power data | [milestone W4](https://github.com/jnd-cz/prague-transport-sim/milestone/11) |
| then **M3** | tiles and streaming | [milestone M3](https://github.com/jnd-cz/prague-transport-sim/milestone/3) |

Deferred on purpose: walker "slides" and the line 17 regression checks wait for the rebuilt world; red
runs of oncoming trams wait for the junction controllers (M4).

History of how the project got here: [docs/history/](docs/history/) (not maintained).
