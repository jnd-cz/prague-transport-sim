# Prague's open-data catalogue, transport theme: what is there for us (2026-11-26)

The catalogue is https://lkod.cz/catalog/praha/datasets with the transport theme (`themeIris=…/data-theme/TRAN`). It lists **51 datasets**. Each was compared with what the build reads (`tools/sources.py`) and with what earlier research found.

**How the numbers were taken.** Counts and fields come from each layer's ArcGIS REST service, `?f=json` and `query?returnCountOnly=true`. The IPR layers are hosted at `https://mp.iprpraha.cz/arcgis/rest/services/Hosted/<name>/FeatureServer/0`. Their catalogue entries say CC BY, as do the IPR layers we already use.

## Already used or found before

- **The PID timetable (GTFS).** DPP's "Jízdní řády" dataset is the same timetable feed we take from data.pid.cz (`gtfs`).
- **Paid-parking sections:** "Úseky parkování v ZPS", `DOP_CUR_DOP_ZPS_USEKY_P`, 16,876 polygons with stall counts. Measured along our lines on 2026-11-13 in `profily-ulic/README.md` (#556).

  Note the name clash: this ZPS means "zóna placeného stání" (paid parking zone). The DTM's ZPS (`zps` in `tools/sources.py`) is "základní prostorová situace", the street survey.
- **Not in the catalogue:** traffic volumes per street and signal locations. TSK publishes volumes on its own website (`prague-traffic-2025.md`); signals are #64.

## New and useful

| layer (service name) | what, measured 2026-11-26 | for |
|---|---|---|
| Pěší trasy (`DOP_CUR_DOP_PESITRASY_L`) | 101,520 polylines; fields: type (`vrstva`, e.g. "mimoúrovně" for underpasses and footbridges, passages through buildings), walking minutes (`min`) | the footway network (#683): passages and underpasses OSM may lack; compare with OSM on one line first |
| PID vstupy do metra (`DOP_CUR_DOP_PID_VSTUPY_B`) | 341 points: node and vestibule name, entrance name and label (E1…), metro line, numbers of stairs, escalators and lifts, out of service from/to | passengers changing between metro and tram (#40, #249); the "M" signs at the entrances |
| Uliční úseky TSK včetně zatřídění (`DOP_CUR_DOP_TSK_ULICUSPAKOM_L`) | 50,623 polylines: section name, motorway / road class / city-road class, road type, one-way (`smerovost`), the section code `mkn` (e.g. NN7781) | the road class of each street in a city-wide car network; `mkn` may be the key of TSK's per-section volumes (not checked) |
| Vyhrazené stání pro zásobování (`DOP_CUR_DOP_ZPS_ZAS_P`) | 1,145 loading-bay polygons, paid zones only | where delivery vans stand at the kerb |
| Zákaz stání (`DOP_CUR_DOP_ZPS_ZM_P`) | 13,141 no-parking polygons (driveways, bins), paid zones only | the gaps in rows of parked cars |
| Parkovací automaty (`DOP_CUR_DOP_ZPS_PARKOMATY_B`) | 1,337 points with street and city district | street furniture |
| Polohy vozů PID – API (Golemio, https://api.golemio.cz/pid/docs/openapi/) | live positions and delays of PID vehicles; needs a free key; the terms say no copyright and no database right | real stop-to-stop times and delays per line, to calibrate the autopilot and AI trams; perhaps a live mode later |
| Zimní údržba TSK (`DOP_CUR_DOP_TSK_ZIMNIUDRZBA_L`), letní údržba (`DOP_CUR_DOP_TSK_LU_TERMINY_P`) | the order of winter clearing per street; street-cleaning dates per block | weather and street-life realism (backlog) |

## Little for us

- Cycling: routes, signs, the cycling plan and the bike-counter API (no cyclists in the game yet).
- PID lines and stops as map layers (`DOP_CUR_DOP_PID_LINKY_L`: 819 routes with a diversion flag). The timetable covers them.
- Fare zones, park-and-ride lots, disabled and special parking, paid-zone areas.
- The city plan's transport layers (planned tram lines; for later content).
- Towing, traffic offences 2015–2024, road closures (opravujeme.to), DPP's news and disruption feeds, Praha 11's parking list, historic paths.
- **DPP's accident statistics** ("Nehodovost", CC BY, listed as never updated): its file link (storage.golemio.cz/lkod/dpp/ee2b8b57-…-statistikanehod.xlsx) returned a 404 page on 2026-11-26.
