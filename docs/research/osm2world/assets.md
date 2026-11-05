# OSM2World: models, textures and their licences (#15)

OSM2World read at commit `1d31c252cbef964b489a55e5fb8242ee253375b1` (2026-11-02). Its assets live in a
separate repository, [tordanik/OSM2World-default-style](https://github.com/tordanik/OSM2World-default-style),
read through the GitHub API (file tree, `README.md`, `COPYING.txt`, `standard.properties`, the sign
catalogues' headers, per-file commit history) at commit `3d82b2e97ae924b8e6599ed6664e407e9fe5ed30`
(2026-10-25). Nothing was downloaded beyond those text files. Our rules: `ASSETS.md` (register, only
licences that allow redistribution) and `docs/decisions/2026-10-29-tests-and-licences.md` (our code is
GPL-3.0; MIT code may be included with its notice; each OSM2World asset checked before use).

## What is where

**The code repository bundles no assets for the world.** `resources/osm2world_definitions.inc` (POV-Ray
macros, part of the MIT code) and `desktop/src/main/resources/logo.png` (the program's logo) are all.
Materials without a texture are colours in code (`scene/material/DefaultMaterials.java`). The README:
"OSM2World's textures, 3D models and visual configuration live in a separate repository … It is included
in the pre-built releases, but needs to be downloaded separately if you clone the source code."

**The style repository**: 1,199 files, 433 MB; 405 MB of it the ambientCG PBR sets.
- `standard.properties`: materials (`material_<NAME>_texture0_dir|file|width|height|…`), models
  (`model_CAR`), includes of the sign catalogues; header: "dedicated all copyright and related and
  neighboring rights to this configuration file to the public domain" (CC0), written 2011–2021 by Tobias
  Knerr.
- `README.md`: "The largest subset of PBR textures is sourced from ambientCG (formerly CC0Textures).
  Many other textures were contributed by members of the OpenStreetMap community to the OSM Wiki Texture
  Library and released into the Public Domain. The configuration file and all additional textures have
  likewise been released into the Public Domain."
- `COPYING.txt`: the CC0 1.0 legal code. GitHub reports the repository's licence as CC0-1.0.
- No per-file credits: provenance is the README's three groups, the file names (ambientCG IDs, Texture
  Library contributors' prefixes) and the commit history.

## Inventory and licences

Texture sizes are the style's tile size in metres. PBR sets are `<ID>_Color.jpg`, `_Normal.jpg`,
`_Displacement.jpg` and `_ORM.jpg` (occlusion, roughness, metalness packed into one image: a change
from ambientCG's separate maps).

| asset | what | licence | source | usable by us |
|---|---|---|---|---|
| `textures/cc0textures/*` (40 sets: Asphalt003/010, Bricks008/029, Concrete034, CorrugatedSteel005, Fabric023/032, Facade005, Fence006, Gravel004/020, Ground003/026/033/042, Ice003, ManholeCover004, Marble001, Metal002, Paper001, PavingStones016/033/053/072, Plaster002, Plastic010, Rock034, Rocks008/022, RoofingTiles003/010, Shells001, Snow006, SolarPanel001, ThatchedRoof001A, Tiles036, Wood026, WoodChips002, WoodSiding008) | PBR materials: ballast (`Gravel020`, 0.6 m), steel (`Metal002`, 1.5 m), asphalt (`Asphalt010`), sett (`PavingStones033`), paving (`PavingStones072`), concrete, brick, roof tiles … | CC0 1.0 | [ambientCG](https://ambientcg.com) (`https://ambientcg.com/view?id=<ID>`), added 2021-03-12 ("from cc0textures.com") | **yes**; take them from ambientCG itself (the original maps and resolutions, the download page as provenance), not the repacked copies |
| `textures/sky/DaySkyHDRI041B.*` (.hdr, .env, .jpg, cube) | day sky HDRI | CC0 1.0 | ambientCG `DaySkyHDRI041B`, added 2024-09-23 | yes, from ambientCG |
| `textures/custom/Railway/*` | ballast, sleepers and two rails in one strip, 3.0 × 2.96 m, PBR | CC0 (README: "all additional textures") | the style repository (maintainer Tobias Knerr); stored as jpg since 2026-08-26 | **yes**: the far level of #65's track ([railways.md](railways.md)) |
| `textures/custom/Glass`, `Glass_Transparent_Color.png`, `Window`, `Windows` | glass, single window, window rows (PBR) | CC0 | the style repository (maintainer Tobias Knerr) | yes; facades are #55's |
| `textures/arbaro_tree_broad_leaved.png`, `arbaro_tree_coniferous.png`, `apfelbaum_alpha.png` | tree billboards (alpha cut-out) | CC0 / public domain per README | in the first commit (2012-09-07); arbaro is a tree generator, the renders' author is not named | yes, as far-level tree cards; generic species |
| `textures/KnerrKerb0001.png`, `DE19F1FreisingDoor00005_small.png`, `DE20F1GarageDoor00001.jpg`, `Fabi2-putz1.png`, `PedaGabionStone.png`, `P1140080E_Water.jpg`, `Grass-2048.JPG`, `clay.jpg` | kerb (1.6 × 0.2 m), entrance and garage door, plaster (used for tartan), gabion stone, water, hedge grass, clay | public domain per README | [OSM Wiki Texture Library](https://wiki.openstreetmap.org/wiki/Texture_Library) contributors (file name prefixes) | yes; the kerb and doors are German, check against Prague before use |
| `textures/road_marking_*.png`, `road_arrow_*.png`, `runway_centerline_stripes.png`, `helipad_markings.svg` | road markings and arrows | CC0 | the style repository (maintainer Tobias Knerr) | yes; Czech arrows differ in shape (to compare with the decree's drawings) |
| `textures/OSM2World_Domposter.png` | advertising poster (OSM2World's own) | CC0 | the style repository (maintainer Tobias Knerr) | no use |
| `textures/pitch*.png`, `tennis_net.png`, `SolarPanel.jpg`, `powertower_*.png`, `white.jpg` | sports pitches, net, solar panel, power tower billboards, white | CC0 | the style repository (maintainer Tobias Knerr) | no use |
| `models/car/car.gltf`, `car_hatchback.gltf` (+ .bin) | two low-poly cars, FF00FF placeholder for the body colour | CC0 | Tobias Knerr, 2024-10-16, PBR 2026-09-05 | no: our own cars are drawn (`src/models.js`) and the lab has better ones (`docs/assets-inventory.md`) |
| `textures/signs-DE/**` (682 files; DE and PL together 951 SVG, 22 PNG), `locales/DE-trafficSigns.properties` | German traffic signs (StVO catalogue), sizes per sign; `defaultTrafficSignHeight = 2.6`, `standardPoleRadius = 0.038` | CC0 per README; added 2019-08-25 by JayGhb, upstream drawings not named | the style repository | **no**: Czech signs (vyhláška 294/2015 Sb.) differ in design and font; draw our own |
| `textures/signs-PL/**` (291 files), `locales/PL-trafficSigns.properties` | Polish traffic signs | as DE | as DE | no, as DE |
| `locales/DE-defaults.properties`, `PL-defaults.properties` | country defaults | CC0 | the style repository | no |
| 3DMR models (`3dmr` tag, `ExternalModelModule.java`) | per-object models downloaded from the 3D Model Repository | per model | [3dmr.eu](https://3dmr.eu) | not used; each model would need its own check |

## Verdict

- **Everything in the style repository is CC0** by its own statement (README, `COPYING.txt`, the
  properties header, GitHub's licence field). CC0 allows redistribution without attribution, so each file
  qualifies for `ASSETS.md`; we credit anyway (author, source URL, CC0) as the register requires.
- The weak point is provenance, not licence: the README's "OSM Wiki Texture Library … Public Domain"
  covers files whose original pages are not linked, and the sign SVGs' upstream drawings are not named.
  Of those, only the kerb and door textures could interest us; take a Texture Library file only after
  finding its wiki page and its stated licence.
- **What to take:** ambientCG sets from ambientCG (ballast `Gravel020`, steel `Metal002`, sett
  `PavingStones033`, paving `PavingStones072`, asphalt `Asphalt010`, concrete `Concrete034`), the
  `custom/Railway` strip for far track, possibly the tree cards for far trees. Not the cars, signs,
  posters, pitches or power towers.
- **How:** a new source file goes into a snapshot or the repo with its URL and date (AGENTS.md, Data);
  a texture into `ASSETS.md` with its row before it is used. Resized or repacked maps say so in the
  register's "Changes" column.
