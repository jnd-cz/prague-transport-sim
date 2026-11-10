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
| podrobný, pohyblivý (výchozí) | `src/t3h.js`, `assets/t3h/` | glTF (`.glb`) a `rig.json` s názvy pohyblivých dílů | CC BY-NC 4.0 | dveře, sběrač, podvozky, kola, spřáhla, čelisti kolejnicových brzd, brzdová světla, směrovky, dálková světla; lehčí úroveň pro vzdálené cizí tramvaje |
| podrobný, klasický | `src/models.js` (`loadDetailedT3`), `assets/t3/` | glTF s jednou texturou; stáhne se při výběru | CC BY-NC 4.0 | nic |
| jednoduchý (vestavěný) | `src/t3simple.js` | kód: tvary změřené na výkresech T3 a na fotkách uživatele, nátěr malovaný na plátno | GPL-3.0 | podvozky, kola, spřáhla, sběrač; světla podle stavu (brzdová, směrovky, dálková) |

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
| `loader` | `builtin` (kreslený kódem: `src/t3simple.js`), `gltf` (nehybný glTF, úroveň 1, bez kódu), `gltf-classic` (model od conflig: osy se najdou podle kol, `src/models.js`), `gltf-rigged` (glTF se souborem pohyblivých dílů: `src/t3h.js`) |
| `model`, `rig` | glTF nebo GLB mezi soubory; soubor pohyblivých dílů (`gltf-rigged`) |
| `forward` | jen `gltf`: osa, ke které model míří čelem, `+Z` (jako hra), jinak `+X`, `-X` nebo `-Z` |
| `files` | každý soubor s cestou `path` ve složce a velikostí `bytes` (nahrávací obrazovka je počítá) |
| `preload` | `true`: stáhne se s linkou; jinak až když ho hráč vybere |
| `licence` | `spdx` (licence, která dovoluje šíření), `commercial` (u NC false), `file` (jeho `LICENSE.txt`), `authors`, `sources` (adresy), `credit` (řádek, který hra ukazuje) |
| `tier` | úroveň pohybu (níže), `moves` díly, které hýbe, `levels` počet úrovní podle vzdálenosti |
| `variants` | typy, kterými může být (`type`, např. `T3SUCS`), a jejich evidenční čísla (`fleet`: rozsahy `[první, poslední]`); typ cizí tramvaje a čísla jejích vozů plynou z čísla pořadí (`src/vehicles.js`), každý typ tak často, kolik má čísel |

**glTF úrovně 1** nepotřebuje kód: nehybný model v metrech, počátek v rovině kolejnic uprostřed mezi čepy
podvozků, +Y nahoru, čelem k `forward`; čepy má podle svého typu. Menu ho nabídne, při výběru se načte a
poděkování ho uvede.

## Co musí souprava splňovat

- `THREE.Group` s jedním `Group` na vůz v `userData.cars`, popořadě od čela.
- Každý vůz v metrech, čelem k **+Z**, **+Y** nahoru, pravý bok (dveře) na **−X**, počátek v rovině
  kolejnic uprostřed mezi otočnými čepy podvozků. Modely z jiných nástrojů míří obvykle na +X: při načtení je
  otočte o −90° kolem Y, jako to dělá `src/t3h.js`.
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
  `src/lamps.js`), dálková světla. Podrobný model bere všechno (`poseHybrid`), vestavěný vše kromě dveří a čelistí
  (`poseSimple`). Světlomety a koncová světla svítí, kdykoli je tramvaj v provozu, čelo soupravy jen na prvním voze,
  červená světla zádi (koncová a brzdová) na každém voze. Náš řidič ovládá směrovky a dálková světla klávesami;
  autopilot a cizí tramvaje dávají směrovky samy (`src/indicators.js`) a cizí T3M ukazuje další zastávku
  (`setNextStop`).
- **Cizí tramvaje** (`src/traffic.js`) se objevují a mizí přes `setOpacity`, po materiálech: vlastní
  průhlednost materiálu pod 1 zůstává v `userData.opacity`, materiál od začátku prolínaný zůstává prolínaný.
  Daleko od kamery přepne podrobný model na lehčí úroveň (`setHybridLevel`, 50–60 m). Souprava, která odjede,
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
3. **Pohyblivé díly** (úroveň 2 a 3): samostatné pojmenované uzly, vyjmenované v souboru jako
   `assets/t3h/rig.json`: `doors` (křídla dveří), `bogies` (název a čep), `wheels` (název a poloměr),
   `pantograph` (kořen, hlava, ramena, výšky drátu), `signals` (směrovky), `brakes` (brzdová světla),
   `numberPlates`, `routePlates`, `infoPlates` (cíl, pořadí, boční tabule), a animace podle názvu
   (`Door_Front_Open`, `Pantograph_Lower`, …). Model kreslený kódem dá místo toho každému vozu `gear` pro
   `src/consist.js`, jako to dělá `src/t3simple.js` s instancovanými sítěmi (jeho vůz kreslí 8 sítí mimo
   tabule).
4. **Popis:** `assets/<id>/vehicle.json` (výše) a id v `assets/vehicles.json`. Nehybnému modelu (úroveň 1,
   loader `gltf`) to stačí. Model, který se hýbe, dnes potřebuje kód: modul jako `src/t3h.js` (načíst, postavit
   soupravu s `gear` každého vozu, nastavit stav) a svůj loader v `makeT3`, `loadVehicle` a `poseT3`
   (`src/models.js`). Chystá se společné rozhraní, které hýbe každým vozidlem podle jeho souboru pohyblivých dílů
   bez vlastního kódu, vozidla při startu samo najde a zkontroluje a hráč si je může nainstalovat (#456).
5. **Kontroly:** `python -I tools/test_vehicles.py` (popis), `tools/test_vehicles_game.py`, test jako `tools/test_t3h.py` (úrovně, spřáhla, podvozky, dveře, cedule, objevení), čas
   snímku přes `tools/frametime.py --models …` a obrázky všech modelů ze stejných pohledů přes
   `python -P -E tools/test_t3simple.py --shots ADRESÁŘ` (bok, tři čtvrtiny, čelo, shora, podvozek, spřáhlo;
   dvouvozová souprava v oblouku o poloměru 25 m a její pojezd v půdorysu; stažený sběrač).

## Úprava modelu

- **Vestavěná T3** (`src/t3simple.js`): rozměry jsou pojmenované konstanty na začátku souboru (`NOSE`,
  `CORNER`, `LIV`, `CUTOUT`, `HEADLIGHT`, `FLEET`, …), každá s uvedeným zdrojem; nátěr maluje `livery()`,
  pevné díly `partsGeometry()`, pohyblivé `bogie()`, `wheelset()`, `coupler()` a `pantoBars()` (rám sběrače
  pro danou výšku drátu), typy a jejich evidenční čísla v `variants` jejího popisu (`assets/t3simple/vehicle.json`). `tools/test_t3simple.py` ji
  kontroluje proti těmto číslům.
- **Tabule a cedule** všech modelů: `src/models.js` (`routeBoxTexture`, `destinationTexture`,
  `numberTexture`, bodový displej T3M `ledFace`).
- **Podrobný model:** soubor pochází z projektové dílny na modely; změna souboru jde přes ni, nebo se udělá
  při načtení v `src/t3h.js` (tak jsou upravená jeho spřáhla, čelisti kolejnicových brzd, evidenční čísla a koncová světla).
- **Fakta:** rozměr, barva nebo detail skutečného vozu uvádí zdroj (výkres, fotka s evidenčním číslem,
  uživatel) v komentáři nebo v [docs/knowledge.md](knowledge.md). Fakta od uživatele, znalce pražských
  tramvají, mají přednost před výkresem i odhadem.
