# Vozidla: přidat vlastní, upravit stávající

[English](vehicles.md) · **Česky**

Pro přispěvatele a tvůrce modů, kteří chtějí do hry přinést model tramvaje nebo upravit některý ze
stávajících. Hra jsou obyčejné ES moduly a Three.js bez sestavování ([DEVELOPING.md](../DEVELOPING.md));
vozidlo je soubor s modelem nebo kód, který ho kreslí, a kód, který ho předá hře. Změny přicházejí jako pull
request ([AGENTS.md](../AGENTS.md): nejdřív issue, v PR kontroly níže).

## Modely dnes

Volba *Model tramvaje* v menu vybírá jeden ze tří, uvedených v `assets/vehicles.json`, každý se svým popisem
(níže); model, který se nenačte, nahradí první načtený v tomto seznamu.

| model | kde | z čeho | licence | co se hýbe |
|---|---|---|---|---|
| podrobný, pohyblivý (výchozí) | `assets/t3h/`, loader `src/rigged.js` | glTF (`.glb`) a `rig.json` s názvy pohyblivých dílů | CC BY-NC 4.0 | dveře, sběrač, podvozky, kola, spřáhla, čelisti kolejnicových brzd, brzdová světla, směrovky, dálková světla; lehčí úroveň pro vzdálené cizí tramvaje |
| podrobný, klasický | `src/models.js` (`loadDetailedT3`), `assets/t3/` | glTF s jednou texturou; stáhne se při výběru | CC BY-NC 4.0 | nic |
| jednoduchý (vestavěný) | `src/t3simple.js` | kód: tvary změřené na výkresech T3 a na fotkách uživatele, nátěr malovaný na plátno | AGPL-3.0 | podvozky, kola, spřáhla, sběrač; světla podle stavu (brzdová, směrovky, dálková) |

`makeT3({ line, cars, vehicle, dest, run, variant })` v `src/models.js` postaví soupravu jako vozidlo s tímto id. Naši tramvaj vytváří `src/main.js`, cizí tramvaje `src/traffic.js`.

## Popis vozidla (manifest)

Každý model je složka `assets/<id>/` se souborem `vehicle.json`, uvedená v `assets/vehicles.json`. Pořadí v seznamu
je pořadí v menu (první je výchozí) i pořadí náhrad: vozidlo, které se nenačte, nahradí první načtené v tomto
pořadí, a vestavěný vůz se načte vždy. Hra z popisů skládá menu, nahrávací obrazovku i poděkování
(`src/vehicles.js`, `src/main.js`); `tools/test_vehicles.py` je kontroluje a `tools/test_vehicles_game.py` každé
načte ve hře, i se vzorkem přidaným jen jako složka.

| pole | co |
|---|---|
| `schema` | 1 |
| `id` | název složky |
| `names` | `cs` a `en`: text v menu |
| `type` | typ vozidla, jehož rozměry má (`VEHICLE_TYPES` v `src/tram.js`: zatím `T3`) |
| `loader` | `builtin` (kreslený kódem: `src/t3simple.js`), `gltf` (nehybný glTF, úroveň 1, bez kódu), `gltf-classic` (model od conflig: osy se najdou podle kol, `src/models.js`), `gltf-rigged` (glTF se souborem pohyblivých dílů, bez kódu: `src/rigged.js`, níže) |
| `model`, `rig` | glTF nebo GLB mezi soubory; soubor pohyblivých dílů (`gltf-rigged`) |
| `forward` | jen `gltf`: osa, ke které model míří čelem, `+Z` (jako hra), jinak `+X`, `-X` nebo `-Z` |
| `files` | každý soubor s cestou `path` ve složce a velikostí `bytes` (nahrávací obrazovka je počítá) |
| `preload` | `true`: stáhne se s linkou; jinak až když ho hráč vybere |
| `licence` | `spdx` (licence, která dovoluje šíření), `commercial` (u NC false), `file` (jeho `LICENSE.txt`), `authors`, `sources` (adresy), `credit` (řádek, který hra ukazuje) |
| `tier` | úroveň pohybu (níže), `moves` díly, které hýbe, `levels` počet úrovní podle vzdálenosti |
| `fleet` | evidenční čísla, pod kterými jeho soupravy jezdí (#527): `types`, pro každý typ (např. `T3SUCS`) jeho `ranges` `[první, poslední]` s `except` (díry), nebo `list`; `sets`, dvojice, které jezdí spolu a s žádným jiným vozem, ale každý z vozů může jezdit sám, kde linka jezdí sólo vozy, a jeho druhý vůz je pak volný pro jiný sólo vůz (souprava mimo seznam jsou dvě čísla jednoho typu); `liveries`, číslo → id nátěru (#529). Jízda je rozdává (`src/vehicles.js` `FleetDealer`): balíček všech čísel zamíchaný semínkem jízdy, takže každý typ přijde na řadu tak často, kolik má čísel, žádné dvakrát na ulici, a vrací se, když souprava odjede; naše tramvaj jezdí jako hráčova oblíbená souprava z menu, jinak jako T3SUCS rozdaná stejně, a žádná cizí tramvaj její čísla nedostane. Rozdávání kontroluje `tools/test_fleet.py` |
| `slots` | sloty nátěru vozidla z glTF (#529): jméno slotu a materiály, které barví, např. hybridovy `body` (`Red_Hull`) a `band` (`Beige`, `Beige_wbackface`); načítač s rigem nechává jejich díly zvlášť (i s uv), aby jim nátěr mohl dát texturu nebo barvu |
| `colours` | model barvený barvami: jména barev, které nátěr smí nahradit (vestavěného vozu `body`, `band`, `roof`) |

**glTF úrovně 1** nepotřebuje kód: nehybný model v metrech, počátek v rovině kolejnic uprostřed mezi čepy
podvozků, +Y nahoru, čelem k `forward`; čepy má podle svého typu. Menu ho nabídne, při výběru se načte a
poděkování ho uvede.

## Nátěry

Nátěr (#529; rozhodnutí `docs/decisions/2026-11-10-vehicle-packages.md`, oddíl 3) je složka `assets/<id>/` se souborem
`livery.json`, uvedená pod `liveries` v `assets/vehicles.json`; jeho id je jméno autora a jeho vlastní
(`sample.t3h-blue`). Menu nabízí naší tramvaji původní vzhled vozidla, jeden z jeho nátěrů, nebo nátěr přidělený jako
cizím tramvajím; cizím tramvajím se přiděluje (`src/vehicles.js` `liveryOf`). Popisy kontroluje
`tools/test_vehicles.py`, vzhled a přidělování ve hře `tools/test_liveries.py`.

| pole | co |
|---|---|
| `schema`, `id`, `names`, `licence`, `files` | jako u vozidla |
| `kind` | `livery` |
| `requires` | `{ "<id vozidla>": ">=1" }`: vozidlo, které barví |
| `textures` | slot → obrázek mezi jeho soubory: nahradí texturu i barvu materiálů slotu; WebP, PNG nebo JPEG, strany mocniny dvou do 2048 px |
| `colours` | slot nebo barva → `#rrggbb`: nahradí barvu materiálů slotu, nebo barvu vestavěného vozu |
| `numbers` | evidenčních čísel `font` (rodina písma CSS, kde chybí, Arial) a `colour` |
| `types` | typy vozového parku, na které se hodí (výchozí: všechny) |
| `share` | podíl cizích souprav těch typů, které jej nosí, 0 až 1 (výchozí 0: jen naše, nebo čísla ve `liveries` vozového parku) |

Sloty, které vynechá, si nechají vzhled vozidla. Nátěr, který jmenuje slot nebo typ, jejž vozidlo nemá, je vynechán se
jménem slotu (`livery x left out: texture slot roof: t3h has no such slot`). Hra zatím žádný nemá, řádek menu je
skrytý (uživatel, 2026-11-13: „For now I would keep only the default liveries, with future possibility to add more
variety“); `tools/test_liveries.py` podává dva vlastní ukázkové, texturu a barvu na hybridu a tři barvy vestavěného vozu.

## Zvukové balíčky

Zvuky hry jsou události a smyčky (#528; rozhodnutí, oddíl 5): hra vyvolá událost (`bell`, `door.close`, `points`,
když náprava přejede srdcovku) a nastaví veličiny, kterými se řídí smyčky; `src/audio.js` přehraje každou nahrávkou
zvukového balíčku, kde ji má, jinak vestavěným zvukem, který syntetizuje (zvuky, které hra měla před balíčky). Balíček
je `sounds` v popisu vozidla (jeho soubory mezi soubory vozidla), nebo složka `assets/<id>/` se souborem `sounds.json`
(`kind` `sounds`, `requires` jeho vozidlo, `names`, `licence`, `files`), uvedená pod `sounds` v `assets/vehicles.json`.
Hra zatím žádný nemá; `tools/test_sounds.py` podává vlastní ukázkový. Pole, seznam událostí, smyček a veličin a pravidla
srdcovek: anglická verze, [Sound packs](vehicles.md#sound-packs) (seznamy píše `tools/sound_lists.py` z kódu).

## Soubor pohyblivých dílů (rig)

Vozidlo, které se hýbe bez vlastního kódu (loader `gltf-rigged`, `src/rigged.js`), jmenuje své díly v souboru
pohyblivých dílů (podrobného modelu `assets/t3h/rig.json`), v souřadnicích modelu (jeho osa `forward`, +Y nahoru).
Hra jimi hýbe podle jmen; díl, který jeho popis tvrdí v `moves` a model nemá, vozidlo vyřadí a hra ten díl jmenuje.

| moves | rig jmenuje | hra |
|---|---|---|
| `bogies` | `bogies`: každý `name` (uzel) a `pivot` | dá je na čepy typu (`T3`: 3,2 m od středu), natočí každý k tětivě mezi jeho nápravami |
| `wheels` | `wheels`: každé `name` (uzel pod podvozkem) a `radius` | otáčí je podle ujeté dráhy; polovinu rozvoru podvozku zjistí z jejich polohy |
| `couplers` | `couplers`: `front` a `rear`, sítě tyče | otáčí každé kolem čepu typu (6,25 m), tyč natažená od čepu k rovině spojení, ve směru spojnice k dalšímu vozu |
| `collector` | `pantograph`: `root`, `head`, `linkages`, `clip` (stažení, 0 nahoře .. 1 dole), `minContactHeight`, `maxContactHeight` | posune animaci na výšku drátu, pod rozsahem ho stáhne |
| `lamps` | `signals`: `left`, `right` (uzly svitu); `brakes`; `beams` (středy světlometů, pro záři dálkových); `tailLamps` (`size`, `at`: světla, která model nemá) | rozsvítí je podle stavu (`src/lamps.js`) |
| `doors` | `doors`: každé `name`, `clip` (otevření) a `leaves` (uzly `outer`, `inner`) | posune animace podle otevření dveří |
| `trackBrakes` | `shoes`: jméno podvozku a sítě čelistí pod ním | zavěsí je v mezeře typu nad kolejnicí (12 mm), spustí je při zapnutých magnetech |

Dále podle jmen: `root` (uzel vozu), `saloon` (`materials` a `within`: kvádr, jehož díly patří k interiéru; zdálky
se vynechá), `numberPlates` (s evidenčním číslem, číslice vysoké `fleetDigits` m), `routeStyles` (každá tabule linky
a její styl: `normal`, `inverted`, `mirror`), `infoPlates` (`frontDestination`, `runNumber`, `sideBoards`). Průhledné
materiály jsou sklo. Lehčí úroveň pro vzdálené cizí tramvaje vznikne při načtení: dveře zavřené, sběrač na drátu,
vše kromě interiéru sloučené podle materiálu. `tools/test_rigged.py` vyrobí vzorové vozidlo se všemi díly a zkontroluje,
že se každý hýbe.

Podrobný model se udržuje v repozitáři: projektová dílna na modely, ze které pochází, už se nepoužívá (uživatel,
12. 11. 2026: dílna je jen web na prohlížení modelu a jeho animací, sama nic neexportuje a nejspíš se už používat
nebude). Jeho rig generuje [`tools/export_t3h_rig.py`](../tools/export_t3h_rig.py) z
[`tools/t3h_rig_roles.json`](../tools/t3h_rig_roles.json) a základního rigu s kontrolou vazeb proti
GLB (#471). Při změně modelu uprav přiřazení částí v souboru rolí a podle potřeby základní rig.
Pak znovu vygeneruj `assets/t3h/rig.json` a aktualizuj jeho velikost v bajtech v `vehicle.json`.
`revision` označuje revizi modelu a `rigRevision` revizi vygenerovaného rigu.

```sh
python -I tools/export_t3h_rig.py --out assets/t3h/rig.json
```

## Co musí souprava splňovat

- `THREE.Group` s jedním `Group` na vůz v `userData.cars`, popořadě od čela.
- Každý vůz v metrech, čelem k **+Z**, **+Y** nahoru, pravý bok (dveře) na **−X**, počátek v rovině
  kolejnic uprostřed mezi otočnými čepy podvozků. Modely z jiných nástrojů míří obvykle na +X: při načtení je
  otočte kolem Y, jako to podle `forward` v popisu dělá loader `gltf-rigged`.
- `userData.bogie` (polovina rozteče čepů), `userData.bodyFront` (čelo skříně od počátku vozu),
  `userData.mats` (materiály tabulí a cedulí), `userData.kind`, `line`, `dest`, `run`.
- Rozměry T3 v `src/tram.js` (`T3`: 15,2 m přes spřáhla, skříň 14,0 m, čepy 6,4 m od sebe, čep spřáhla
  6,25 m od středu, čelisti kolejnicových brzd 12 mm nad kolejnicí) používá fyzika, spřáhla i průjezdné
  profily. Model do nich musí sedět; nový typ vozidla přináší vlastní, se zdrojem.

## Co hra se soupravou dělá

- **Každý snímek** `placeConsist(model, s, at)` posadí každý vůz na jeho dva otočné čepy, takže se stáčí,
  naklápí a klopí s kolejí. Podrobnému a vestavěnému modelu věší další vůz na spřáhlo a nastaví každému vozu
  pojezd (`hangConsist`, `src/consist.js`): vůz s pohyblivým pojezdem nese `userData.gear`, které natočí
  podvozky do tětivy mezi jejich nápravami, otočí kola podle ujeté dráhy a vychýlí spřáhla podél spojení
  mezi vozy (volná rovně vpřed). Podrobný model tím hýbe uzly svého rigu, vestavěný svými instancovanými
  sítěmi.
- **Nápisy:** `setConsistLine(model, line, dest, run)` překreslí tabule s číslem linky, směrovou ceduli
  a pořadí (textury z plátna, `src/models.js`), `setNextStop` boční panel T3M.
- **Stav:** `poseT3(model, { doors, collector, braking, track, indicate, clock, highBeam })` (`src/models.js`):
  dveře 0–1, výška trolejového drátu nad kolejnicí pro sběrač (pod jeho pracovním rozsahem se stáhne), brzdová
  světla, magnety kolejnicových brzd, směrovky (`'left'`, `'right'`, `'hazard'` nebo nic, blikají podle `clock`:
  `src/lamps.js`), dálková světla. Vozidlo s rigem bere vše, co rig jmenuje (`poseRigged`), vestavěný vše kromě dveří a čelistí
  (`poseSimple`). Světlomety a koncová světla svítí, kdykoli je tramvaj v provozu, čelo soupravy jen na prvním voze,
  červená světla zádi (koncová a brzdová) na každém voze. Náš řidič ovládá směrovky a dálková světla klávesami;
  autopilot a cizí tramvaje dávají směrovky samy (`src/indicators.js`) a cizí T3M ukazuje další zastávku
  (`setNextStop`).
- **Cizí tramvaje** (`src/traffic.js`) se objevují a mizí přes `setOpacity`, po materiálech: vlastní
  průhlednost materiálu pod 1 zůstává v `userData.opacity`, materiál od začátku prolínaný zůstává prolínaný.
  Daleko od kamery přepne vozidlo s rigem na lehčí úroveň (`setRiggedLevel`, 50–60 m). Souprava, která odjede,
  se uvolní přes `disposeModel`; geometrie a textury s `userData.shared` zůstanou pro další.

## Úrovně pohybu

Co model umí nabídnout a co mu hra řídí. Model uvede svou úroveň; víc po něm hra nechce.

1. **Nehybný:** skříň a podvozky v jednom, tabule a cedule podle hry (linka, cíl, pořadí, evidenční čísla);
   vůz sedí na svých čepech. Dnes klasický model.
2. **Jedoucí:** podvozky se natáčejí do koleje, kola se točí, spřáhla mezi vozy se vychylují, sběrač drží
   výšku trolejového drátu a umí se stáhnout, brzdová světla, směrovky a světlomety podle stavu. Podrobný
   i vestavěný model to umějí (#454, #436).
3. **Živý:** dveře se ve stanici otevírají a zavírají, čelisti kolejnicových brzd dosedají, v dešti jedou
   stěrače, otevírají se větrací klapky a poklopy, sklápí se rameno zrcátka, skříň pruží (náklon v obloucích,
   předklon při brzdění), světla v salonu a v kabině, řidič, jiskry na sběrači při námraze.

Nezávisle na úrovních může model mít **úrovně podle vzdálenosti**: plnou u kamery a lehčí (sloučené díly, bez
interiéru) pro vzdálené cizí tramvaje, jako podrobný model.

## Přidání vozidla

1. **Nejdřív licence.** Jen to, co se smí šířit (CC0, CC BY, CC BY-SA, CC BY-NC, …). Soubory patří do
   `assets/<název>/` s `LICENSE.txt` (autor, zdrojová adresa, licence, co jste změnili), k nim řádek
   v [ASSETS.md](../ASSETS.md) a řádek s poděkováním, který hra ukazuje (`licence.credit` v popisu).
   Model s licencí NC nesmí do komerčního vydání; vestavěný smí.
2. **Soubor:** glTF nebo GLB v metrech, počátek a osy jako výše, nebo upravené při načtení. Ať je lehký:
   podrobný model má 2,9 MB a 44 000 trojúhelníků na vůz a cizích souprav je na očích několik naráz. Nasazení
   soubory `.glb` a `.gltf` komprimuje (DEVELOPING.md, *Deploy*).
3. **Pohyblivé díly** (úroveň 2 a 3): samostatné pojmenované uzly a animace, vyjmenované v rigu (výše). Model
   kreslený kódem dá místo toho každému vozu `gear` pro
   `src/consist.js`, jako to dělá `src/t3simple.js` s instancovanými sítěmi (jeho vůz kreslí 8 sítí mimo
   tabule).
4. **Popis:** `assets/<id>/vehicle.json` (výše) a id v `assets/vehicles.json`. Nehybnému modelu (úroveň 1,
   loader `gltf`) to stačí, stejně jako modelu, který se hýbe podle rigu (loader `gltf-rigged`). Chystá se, že hra
   vozidla při startu sama najde a zkontroluje a hráč si je může nainstalovat (#456).
5. **Kontroly:** `python -I tools/test_vehicles.py` (popis), `tools/test_vehicles_game.py`, `tools/test_rigged.py`, test jako `tools/test_t3h.py` (úrovně, spřáhla, podvozky, dveře, cedule, objevení), čas
   snímku přes `tools/frametime.py --models …` a obrázky všech modelů ze stejných pohledů přes
   `python -P -E tools/test_t3simple.py --shots ADRESÁŘ` (bok, tři čtvrtiny, čelo, shora, podvozek, spřáhlo;
   dvouvozová souprava v oblouku o poloměru 25 m a její pojezd v půdorysu; stažený sběrač).

## Úprava modelu

- **Vestavěná T3** (`src/t3simple.js`): rozměry jsou pojmenované konstanty na začátku souboru (`NOSE`,
  `CORNER`, `LIV`, `CUTOUT`, `HEADLIGHT`, `FLEET`, …), každá s uvedeným zdrojem; nátěr maluje `livery()`,
  pevné díly `partsGeometry()`, pohyblivé `bogie()`, `wheelset()`, `coupler()` a `pantoBars()` (rám sběrače
  pro danou výšku drátu), typy a jejich evidenční čísla v `fleet` jejího popisu (`assets/t3simple/vehicle.json`). `tools/test_t3simple.py` ji
  kontroluje proti těmto číslům.
- **Tabule a cedule** všech modelů: `src/models.js` (`routeBoxTexture`, `destinationTexture`,
  `numberTexture`, bodový displej T3M `ledFace`).
- **Podrobný model:** udržuje se v repozitáři (dílna na modely se už nepoužívá): změnu modelu dělá nástroj
  v repozitáři a uvede ji v `assets/t3h/LICENSE.txt`, jak licence CC BY-NC 4.0 žádá; změna přiřazení dílů jde do rolí
  jeho rigu (čelisti, spřáhla, interiér, světlomety, koncová světla a velikost evidenčních čísel, #467, #471).
- **Fakta:** rozměr, barva nebo detail skutečného vozu uvádí zdroj (výkres, fotka s evidenčním číslem,
  uživatel) v komentáři nebo v [docs/knowledge.md](knowledge.md). Fakta od uživatele, znalce pražských
  tramvají, mají přednost před výkresem i odhadem.
