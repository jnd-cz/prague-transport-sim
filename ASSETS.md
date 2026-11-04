# Asset register

Every file in the repository that is not code written for this project, with its source and licence.
Nothing third-party goes into the repository without an entry here, and only under a licence that
allows redistribution (CC0, CC BY, CC BY-SA, CC BY-NC, …). The code is GPL-3.0 ([LICENSE](LICENSE));
the project's own assets are listed with their own licence.

| Files | What | Author / source | Licence | Changes |
|---|---|---|---|---|
| `assets/t3/t3.gltf`, `t3.bin`, `t3_color.jpg` | Detailed Tatra T3 tram model, classic (the player's choice in the menu, #248) | "Tatra T3" by Jakub Vaja (conflig), [Sketchfab](https://sketchfab.com/3d-models/tatra-t3-76aa08d7c06340fc89229551c45e3c3a) | [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) | Maps reduced to one 2048 px colour map with baked AO; see `assets/t3/LICENSE.txt`. **Non-commercial**: not for a commercial release (the procedural model in `src/models.js` is). |
| `assets/t3h/tatra-t3-hybrid-nc.glb`, `rig.json` | Detailed Tatra T3 tram model (hybrid, rigged) | base body, interior and cab: "Tatra T3" by SimonStrikesBack, [Sketchfab](https://sketchfab.com/3d-models/tatra-t3-2c08e2e39ace45569c45a2fdbb4052c0) ([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)); collector, mirror, route-plate support, lamps: "Tatra T3" by Jakub Vaja (conflig), [Sketchfab](https://sketchfab.com/3d-models/tatra-t3-76aa08d7c06340fc89229551c45e3c3a) ([CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)); combined and rigged in the project's asset lab (street-life-boarding v14) | [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) (accepted by the user, #247 Q1) | The lab's modifications are listed in `assets/t3h/LICENSE.txt`; the game merges its parts at load, moves the track-brake shoes to 12 mm and refits the couplers (`src/t3h.js`, #248). **Non-commercial**: not for a commercial release (the procedural model in `src/models.js` is). |

Generated in code, part of the GPL-3.0 code: the procedural tram, cars, people, signals, signs and
street furniture (`src/models.js`), textures drawn on canvas (plates, facades, signs), and all sound
(Web Audio synthesis, `src/audio.js`). Models made for the project by agents are GPL-3.0 as well
([decision](docs/decisions/2026-10-29-tests-and-licences.md)), each with an entry here.

Not in the repository yet: the older asset labs' T3, cars, pedestrians and street furniture, listed with
their licences in [docs/assets-inventory.md](docs/assets-inventory.md).

Not in the repository: the world data built from public sources (see [NOTICE.md](NOTICE.md)) and the
raw sources themselves, both in the data store ([DATA.md](DATA.md)).

**OSM2World** (planned study, #15): its code is MIT; any code ported from it keeps its copyright notice
here and in the file. Its bundled models and textures carry their own licences and get an entry each
before use.
