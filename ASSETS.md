# Asset register

Every file in the repository that is not code written for this project, with its source and licence.
Nothing third-party goes into the repository without an entry here, and only under a licence that
allows redistribution (CC0, CC BY, CC BY-SA, CC BY-NC, …). The code is GPL-3.0 ([LICENSE](LICENSE));
the project's own assets are listed with their own licence.

| Files | What | Author / source | Licence | Changes |
|---|---|---|---|---|
| `assets/t3/t3.gltf`, `t3.bin`, `t3_color.jpg` | Detailed Tatra T3 tram model | "Tatra T3" by Jakub Vaja (conflig), [Sketchfab](https://sketchfab.com/3d-models/tatra-t3-76aa08d7c06340fc89229551c45e3c3a) | [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) | Maps reduced to one 2048 px colour map with baked AO; see `assets/t3/LICENSE.txt`. **Non-commercial**: not for a commercial release (the procedural model in `src/models.js` is). |

Generated in code, part of the GPL-3.0 code: the procedural tram, cars, people, signals, signs and
street furniture (`src/models.js`), textures drawn on canvas (plates, facades, signs), and all sound
(Web Audio synthesis, `src/audio.js`).

Not in the repository: the world data built from public sources (see [NOTICE.md](NOTICE.md)) and the
raw sources themselves, both in the data store ([DATA.md](DATA.md)).

**OSM2World** (planned study, #15): its code is MIT; any code ported from it keeps its copyright notice
here and in the file. Its bundled models and textures carry their own licences and get an entry each
before use.
