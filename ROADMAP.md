# Roadmap

The work is tracked in [GitHub issues](https://github.com/jnd-cz/prague-transport-sim/issues), one
milestone per architecture step ([docs/architecture.md](docs/architecture.md) §8). This file only says
what each milestone is for; the issues hold the tasks.

| Milestone | Goal |
|---|---|
| **M1 Hygiene** | Agent rules (AGENTS.md), headless benches (Python + Playwright), one coordinate module for every tool, seeded randomness, going public cleanly (licences, store details private). |
| **M2 World compiler, line 17** | The rebuild: one city-wide frame (S-JTSK, Bpv), a source per layer with fallbacks and provenance, the meaning of every height, level-aware streets, bridges on their surveyed decks, road / footway networks and a feature layer, placement rules and validation in the build. Pilot areas first (Výtoň, Kobylisy – Vozovna, Palackého náměstí, Trojský most), then line 17 in full and its regression checklist. |
| **M3 Tiles and streaming** | Preprocessed world tiles; a streaming loader with a memory budget and LOD. |
| **M4 Track graph, several lines** | Vehicles on the track graph, one controller per junction, both directions drivable, line ends and depots. |
| **M5 Simulation tiers and Worker** | A deterministic fixed-step core without Three.js in a Worker; meso / macro tiers. |
| **M6 Buses and passengers** | Buses and trolleybuses on the lane graph; one passenger model. |
| **Backlog** | Realism and content not tied to a step: signals and traffic detail, sound, lighting, weather, assets, sources to obtain. |

Deferred on purpose: walker "slides" and the line 17 regression checks wait for the rebuilt world; red
runs of oncoming trams wait for the junction controllers (M4).

History of how the project got here: [docs/history/](docs/history/) (not maintained).
