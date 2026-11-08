# Structure height decisions

Snapshot `2026-11-06r`. Proposed rules are not approvals.

Open `?line=17&review=reports/review/track-heights.json` to inspect and answer the decisions.

Each decision may cover several lines and directions. A dated reviewed rule can include all its
`approval_profile` entries in one `span_reviews` record. The placeholder rule deliberately fails
validation until a height rule is explicitly chosen. Numeric DI always keeps priority.

## osm-22756845 · tunnel

OSM ways: [22756845](https://www.openstreetmap.org/way/22756845), [477083010](https://www.openstreetmap.org/way/477083010).

| Line / direction | Nearest stops at ends | Length (m) | Proposed rule |
|---|---|---:|---|
| 9 / path | Hlavní nádraží → Hlavní nádraží | 1.5 | linear_di_portals |
| 9 / path | Hlavní nádraží → Hlavní nádraží | 0.7 | linear_di_portals |
| 9 / path | Hlavní nádraží → Hlavní nádraží | 0.7 | linear_di_portals |
| 9 / path | Hlavní nádraží → Hlavní nádraží | 1.5 | linear_di_portals |
| 9 / path | Hlavní nádraží → Hlavní nádraží | 1.4 | linear_di_portals |
| 9 / path | Hlavní nádraží → Hlavní nádraží | 1.4 | linear_di_portals |
| 9 / path | Hlavní nádraží → Hlavní nádraží | 1.4 | linear_di_portals |
| 9 / path | Hlavní nádraží → Hlavní nádraží | 2.1 | linear_di_portals |
| 9 / path | Hlavní nádraží → Hlavní nádraží | 3.9 | linear_di_portals |
| 9 / path | Hlavní nádraží → Hlavní nádraží | 1.3 | linear_di_portals |
| 9 / path | Hlavní nádraží → Hlavní nádraží | 3.8 | linear_di_portals |
| 9 / path | Hlavní nádraží → Hlavní nádraží | 1.3 | linear_di_portals |
| 9 / path | Hlavní nádraží → Hlavní nádraží | 2.5 | linear_di_portals |
| 9 / path | Hlavní nádraží → Hlavní nádraží | 6.5 | linear_di_portals |
| 9 / path | Hlavní nádraží → Hlavní nádraží | 2.7 | linear_di_portals |
| 9 / path | Hlavní nádraží → Hlavní nádraží | 1.3 | linear_di_portals |
| 9 / path | Hlavní nádraží → Hlavní nádraží | 4.0 | linear_di_portals |
| 9 / pathBack | Hlavní nádraží → Hlavní nádraží | 1.3 | linear_di_portals |
| 9 / pathBack | Hlavní nádraží → Hlavní nádraží | 1.3 | linear_di_portals |
| 9 / pathBack | Hlavní nádraží → Hlavní nádraží | 2.6 | linear_di_portals |
| 9 / pathBack | Hlavní nádraží → Hlavní nádraží | 1.3 | linear_di_portals |
| 9 / pathBack | Hlavní nádraží → Hlavní nádraží | 3.7 | linear_di_portals |
| 9 / pathBack | Hlavní nádraží → Hlavní nádraží | 3.6 | linear_di_portals |
| 9 / pathBack | Hlavní nádraží → Hlavní nádraží | 1.2 | linear_di_portals |
| 9 / pathBack | Hlavní nádraží → Hlavní nádraží | 7.3 | linear_di_portals |
| 9 / pathBack | Hlavní nádraží → Hlavní nádraží | 1.4 | linear_di_portals |

Archive candidates: `4276196` (2008-03-10; range 199.287–199.287 m); `3886879` (2012-08-30; range 198.215–205.038 m); `3375444` (2012-08-30; range 197.846–198.915 m).

DI at span ends: 199.095 m / 1000428539595 / 0.4 m away / export 2026-10-31T00:00; 199.030 m / 1000428539595 / 0.4 m away / export 2026-10-31T00:00; 198.865 m / 1000428539595 / 0.4 m away / export 2026-10-31T00:00; 198.805 m / 1000428539595 / 0.4 m away / export 2026-10-31T00:00; 198.770 m / 1000428539595 / 0.4 m away / export 2026-10-31T00:00; 198.700 m / 1000428539595 / 0.4 m away / export 2026-10-31T00:00; 198.700 m / 1000428539595 / 0.4 m away / export 2026-10-31T00:00; 198.590 m / 1000428539595 / 0.4 m away / export 2026-10-31T00:00; 198.550 m / 1000428539595 / 0.4 m away / export 2026-10-31T00:00; 198.420 m / 1000428539595 / 0.7 m away / export 2026-10-31T00:00; 198.350 m / 1000428539595 / 0.7 m away / export 2026-10-31T00:00; 198.210 m / 1000428539595 / 0.7 m away / export 2026-10-31T00:00; 198.140 m / 1000428539595 / 0.7 m away / export 2026-10-31T00:00; 198.020 m / 1000428539595 / 0.7 m away / export 2026-10-31T00:00; 197.910 m / 1000428539595 / 0.7 m away / export 2026-10-31T00:00; 197.780 m / 1000428539595 / 0.7 m away / export 2026-10-31T00:00; 197.650 m / 1000428539595 / 0.3 m away / export 2026-10-31T00:00; 197.520 m / 1000428539595 / 0.6 m away / export 2026-10-31T00:00; 197.520 m / 1000428539595 / 0.6 m away / export 2026-10-31T00:00; 197.460 m / 1000428539595 / 0.6 m away / export 2026-10-31T00:00; 197.460 m / 1000428539595 / 0.6 m away / export 2026-10-31T00:00; 197.400 m / 1000428539595 / 0.6 m away / export 2026-10-31T00:00; 197.400 m / 1000428539595 / 0.6 m away / export 2026-10-31T00:00; 197.390 m / 1000428539595 / 0.6 m away / export 2026-10-31T00:00; 197.390 m / 1000428539595 / 0.6 m away / export 2026-10-31T00:00; 197.400 m / 1000428539595 / 0.6 m away / export 2026-10-31T00:00; 197.400 m / 1000428539595 / 0.6 m away / export 2026-10-31T00:00; 197.460 m / 1000428539595 / 0.7 m away / export 2026-10-31T00:00; 197.460 m / 1000428539595 / 0.7 m away / export 2026-10-31T00:00; 197.530 m / 1000428539595 / 0.7 m away / export 2026-10-31T00:00; 197.530 m / 1000428539595 / 0.7 m away / export 2026-10-31T00:00; 197.580 m / 1000428539595 / 0.7 m away / export 2026-10-31T00:00; 197.580 m / 1000428539595 / 0.7 m away / export 2026-10-31T00:00; 197.730 m / 1000428539595 / 0.7 m away / export 2026-10-31T00:00; 197.919 m / 1000428539073 / 0.8 m away / export 2026-10-31T00:00; 197.870 m / 1000428539172 / 0.6 m away / export 2026-10-31T00:00; 197.790 m / 1000428539172 / 0.6 m away / export 2026-10-31T00:00; 197.730 m / 1000428539172 / 0.6 m away / export 2026-10-31T00:00; 197.660 m / 1000428539172 / 0.6 m away / export 2026-10-31T00:00; 197.540 m / 1000428539172 / 0.6 m away / export 2026-10-31T00:00; 197.540 m / 1000428539172 / 0.6 m away / export 2026-10-31T00:00; 197.450 m / 1000428539172 / 0.6 m away / export 2026-10-31T00:00; 197.450 m / 1000428539172 / 0.6 m away / export 2026-10-31T00:00; 197.380 m / 1000428539172 / 0.6 m away / export 2026-10-31T00:00; 197.390 m / 1000428539172 / 0.6 m away / export 2026-10-31T00:00; 197.430 m / 1000428539172 / 0.6 m away / export 2026-10-31T00:00; 197.430 m / 1000428539172 / 0.6 m away / export 2026-10-31T00:00; 197.450 m / 1000428539172 / 0.6 m away / export 2026-10-31T00:00; 197.450 m / 1000428539172 / 0.6 m away / export 2026-10-31T00:00; 197.542 m / 1000428539172 / 0.6 m away / export 2026-10-31T00:00; 198.490 m / 1000428539172 / 0.3 m away / export 2026-10-31T00:00; 198.605 m / 1000428539172 / 0.4 m away / export 2026-10-31T00:00.

Flags: `known_archive_disagreement`, `structure_hint`, `structure_unverified`, `tunnel_unverified`.

## osm-8102914 · Seifertova

OSM ways: [477078032](https://www.openstreetmap.org/way/477078032), [8102914](https://www.openstreetmap.org/way/8102914).

| Line / direction | Nearest stops at ends | Length (m) | Proposed rule |
|---|---|---:|---|
| 9 / path | Hlavní nádraží → Hlavní nádraží | 1.4 | linear_di_portals |
| 9 / path | Hlavní nádraží → Hlavní nádraží | 0.7 | linear_di_portals |
| 9 / path | Hlavní nádraží → Hlavní nádraží | 0.8 | linear_di_portals |
| 9 / path | Hlavní nádraží → Hlavní nádraží | 1.6 | linear_di_portals |
| 9 / path | Hlavní nádraží → Hlavní nádraží | 2.8 | linear_di_portals |
| 9 / path | Hlavní nádraží → Hlavní nádraží | 4.4 | linear_di_portals |
| 9 / pathBack | Hlavní nádraží → Hlavní nádraží | 2.1 | linear_di_portals |
| 9 / pathBack | Hlavní nádraží → Hlavní nádraží | 3.8 | linear_di_portals |
| 9 / pathBack | Hlavní nádraží → Hlavní nádraží | 18.0 | linear_di_portals |
| 9 / pathBack | Hlavní nádraží → Hlavní nádraží | 6.0 | linear_di_portals |
| 9 / pathBack | Hlavní nádraží → Hlavní nádraží | 1.1 | linear_di_portals |
| 9 / pathBack | Hlavní nádraží → Hlavní nádraží | 1.6 | linear_di_portals |

Archive candidates: `1970818` (2008-03-10; range 202.096–202.251 m); `4289060` (2012-08-30; range 202.551–203.872 m); `4073735` (2012-08-30; range 202.567–209.183 m); `1936074` (2008-03-10; range 202.165–202.269 m).

DI at span ends: 202.109 m / 1000428539279 / 0.3 m away / export 2026-10-31T00:00; 202.240 m / 1000428539564 / 0.4 m away / export 2026-10-31T00:00; 202.380 m / 1000428539564 / 0.4 m away / export 2026-10-31T00:00; 202.460 m / 1000428539564 / 0.6 m away / export 2026-10-31T00:00; 202.640 m / 1000428539564 / 0.4 m away / export 2026-10-31T00:00; 202.680 m / 1000428539564 / 0.4 m away / export 2026-10-31T00:00; 202.780 m / 1000428539564 / 0.8 m away / export 2026-10-31T00:00; 202.860 m / 1000428539564 / 1.2 m away / export 2026-10-31T00:00; 203.489 m / 1000428539160 / 1.9 m away / export 2026-10-31T00:00; 203.705 m / 1000428539273 / 1.4 m away / export 2026-10-31T00:00; 203.705 m / 1000428539273 / 1.4 m away / export 2026-10-31T00:00; 204.010 m / 1000428539257 / 1.0 m away / export 2026-10-31T00:00; 204.380 m / 1000428539566 / 1.0 m away / export 2026-10-31T00:00; 204.150 m / 1000428539566 / 1.0 m away / export 2026-10-31T00:00; 204.040 m / 1000428539566 / 1.0 m away / export 2026-10-31T00:00; 203.760 m / 1000428539115 / 1.4 m away / export 2026-10-31T00:00; 203.760 m / 1000428539115 / 1.4 m away / export 2026-10-31T00:00; 203.160 m / 1000428539009 / 2.5 m away / export 2026-10-31T00:00; 202.830 m / 1000428539015 / 1.1 m away / export 2026-10-31T00:00; 202.700 m / 1000428539015 / 0.5 m away / export 2026-10-31T00:00; 202.490 m / 1000428539015 / 0.3 m away / export 2026-10-31T00:00; 202.415 m / 1000428539135 / 0.3 m away / export 2026-10-31T00:00; 202.385 m / 1000428539135 / 0.3 m away / export 2026-10-31T00:00; 202.285 m / 1000428539135 / 0.3 m away / export 2026-10-31T00:00.

Flags: `ambiguous_archive_match`, `known_archive_disagreement`, `structure_hint`, `structure_unverified`, `tunnel_unverified`.

## osm-476017592 · bridge

OSM ways: [476017592](https://www.openstreetmap.org/way/476017592), [476017594](https://www.openstreetmap.org/way/476017594), [476017595](https://www.openstreetmap.org/way/476017595), [476073795](https://www.openstreetmap.org/way/476073795), [938201414](https://www.openstreetmap.org/way/938201414), [938201415](https://www.openstreetmap.org/way/938201415), [938201416](https://www.openstreetmap.org/way/938201416), [938201417](https://www.openstreetmap.org/way/938201417), [996102484](https://www.openstreetmap.org/way/996102484), [996102485](https://www.openstreetmap.org/way/996102485), [996102490](https://www.openstreetmap.org/way/996102490).

Mosty 3D features: 398 (the track meets the model's deck at an end).

| Line / direction | Nearest stops at ends | Length (m) | Proposed rule |
|---|---|---:|---|
| 9 / path | Palackého náměstí → Palackého náměstí | 0.3 | archive_agrees_with_survey |
| 9 / path | Palackého náměstí → Palackého náměstí | 1.2 | linear_di_portals |
| 9 / path | Palackého náměstí → Palackého náměstí | 1.2 | linear_di_portals |
| 9 / pathBack | Palackého náměstí → Palackého náměstí | 0.7 | linear_di_portals |

Archive candidates: `4028389` (2008-09-23; range 192.022–197.905 m); `2797335` (2008-09-23; range 187.892–187.912 m); `2425267` (2008-09-23; range 197.733–197.733 m).

DI at span ends: 197.750 m / 1000428539573 / 0.1 m away / export 2026-10-31T00:00; 197.755 m / 1000428539573 / 0.1 m away / export 2026-10-31T00:00; 197.755 m / 1000428539573 / 0.1 m away / export 2026-10-31T00:00; 197.770 m / 1000428539573 / 0.3 m away / export 2026-10-31T00:00; 197.790 m / 1000428539573 / 0.3 m away / export 2026-10-31T00:00; 197.810 m / 1000428539573 / 0.4 m away / export 2026-10-31T00:00; 197.730 m / 1000428539413 / 0.2 m away / export 2026-10-31T00:00; 197.727 m / 1000428539084 / 0.4 m away / export 2026-10-31T00:00.

Flags: `archive_surface_height_disagreement`, `known_archive_disagreement`, `paved_surface_height_disagreement`, `structure_hint`, `structure_unverified`, `track_style_defaulted_panels`, `track_zps_level_unverified`.

## osm-4722514 · bridge

OSM ways: [1176355489](https://www.openstreetmap.org/way/1176355489), [1176355495](https://www.openstreetmap.org/way/1176355495), [338644891](https://www.openstreetmap.org/way/338644891), [338644915](https://www.openstreetmap.org/way/338644915), [4722514](https://www.openstreetmap.org/way/4722514), [4722515](https://www.openstreetmap.org/way/4722515), [495700333](https://www.openstreetmap.org/way/495700333), [495700334](https://www.openstreetmap.org/way/495700334).

Mosty 3D features: 64, 69 (the track meets the model's deck at an end).

| Line / direction | Nearest stops at ends | Length (m) | Proposed rule |
|---|---|---:|---|
| 17 / path | Čechova čtvrť → Nádraží Modřany | 398.3 | review_archive_profile |
| 17 / pathBack | Nádraží Modřany → Čechova čtvrť | 401.0 | review_archive_profile |

Archive candidates: `2820098` (2012-03-08; range 200.969–205.257 m); `2855932` (2012-03-08; range 198.08–202.71 m); `1929698` (2012-07-18; range 197.472–197.93 m); `3406756` (2012-07-18; range 196.64–197.321 m); `1937198` (2012-07-18; range 196.128–196.632 m); `2864566` (2012-07-18; range 195.405–195.946 m); `4267369` (2008-03-10; range 195.279–195.279 m); `2341230` (2012-07-18; range 195.36–195.36 m); `1932977` (2012-07-18; range 192.819–195.252 m); `3831232` (2012-07-18; range 191.052–192.598 m); `2220598` (2012-07-18; range 191.04–197.524 m); `3907577` (2012-03-08; range 198.145–202.791 m); `4076997` (2012-03-08; range 200.979–205.33 m).

DI at span ends: no numeric DI within 50 m.

Flags: `ambiguous_survey_heights`, `archive_surface_height_disagreement`, `structure_hint`, `structure_unverified`, `survey_construction_unverified`, `survey_surface_height_unavailable`, `track_style_defaulted_panels`, `track_zps_level_unverified`.

## osm-4722520 · bridge

OSM ways: [338644883](https://www.openstreetmap.org/way/338644883), [4722520](https://www.openstreetmap.org/way/4722520), [495705767](https://www.openstreetmap.org/way/495705767), [495705768](https://www.openstreetmap.org/way/495705768), [495705769](https://www.openstreetmap.org/way/495705769), [495705770](https://www.openstreetmap.org/way/495705770).

Mosty 3D features: 74, 86 (the track meets the model's deck at an end).

| Line / direction | Nearest stops at ends | Length (m) | Proposed rule |
|---|---|---:|---|
| 17 / path | Nádraží Modřany → Belárie | 630.3 | review_archive_profile |
| 17 / pathBack | Belárie → Nádraží Modřany | 627.0 | review_archive_profile |

Archive candidates: `1926769` (2008-03-10; range 195.534–195.645 m); `1833321` (2008-03-10; range 195.668–195.85 m); `4497469` (2008-03-10; range 195.874–195.972 m); `4268986` (2008-03-10; range 195.996–196.088 m); `1930821` (2008-03-10; range 196.107–196.369 m); `4043381` (2008-03-10; range 196.395–196.417 m); `1930819` (2008-03-10; range 196.418–196.881 m); `3781041` (2008-03-10; range 196.884–197.062 m); `1930086` (2008-03-10; range 197.082–197.288 m); `3403333` (2008-03-10; range 197.318–197.591 m); `4370452` (2008-03-10; range 197.612–197.79 m); `4293593` (2008-03-10; range 197.792–198.187 m); `3941068` (2008-03-10; range 198.268–199.741 m); `1930087` (2008-03-10; range 199.745–200.087 m); `1925912` (2008-03-10; range 200.164–200.43 m); `1935877` (2008-03-10; range 200.493–200.69 m); `1930091` (2008-03-10; range 200.757–201.019 m); `4371401` (2008-03-10; range 195.79–201.192 m); `1837553` (2008-03-10; range 194.69–195.066 m); `1930088` (2008-03-10; range 196.438–201.604 m); `3885059` (2008-03-10; range 201.159–201.426 m); `3860603` (2008-03-10; range 200.681–201.067 m); `1930089` (2008-03-10; range 200.285–200.679 m); `1937199` (2008-03-10; range 199.701–200.124 m); `1921892` (2008-03-10; range 199.122–199.559 m); `3860919` (2008-03-10; range 198.443–198.989 m); `1841676` (2008-03-10; range 197.681–198.304 m); `4068612` (2008-03-10; range 196.84–197.513 m); `1928827` (2008-03-10; range 196.935–197.568 m); `2423689` (2008-03-10; range 197.57–198.358 m); `4274505` (2008-03-10; range 198.36–199.042 m); `3902793` (2008-03-10; range 199.042–199.617 m); `1922078` (2008-03-10; range 199.761–200.185 m); `2861682` (2008-03-10; range 200.335–200.616 m); `1937200` (2008-03-10; range 200.727–201.007 m); `4170262` (2008-03-10; range 197.622–201.613 m); `2798588` (2008-03-10; range 194.522–195.724 m); `1930090` (2008-03-10; range 195.462–201.172 m); `2537307` (2008-03-10; range 200.784–201.051 m); `1918810` (2008-03-10; range 200.453–200.716 m); `4196268` (2008-03-10; range 200.177–200.45 m); `2679208` (2008-03-10; range 199.767–200.104 m); `1934580` (2008-03-10; range 198.356–199.699 m); `2262442` (2008-03-10; range 197.846–198.353 m); `1927260` (2008-03-10; range 197.546–197.813 m); `3904340` (2008-03-10; range 197.241–197.516 m); `1941357` (2008-03-10; range 197.024–197.213 m); `1825896` (2008-03-10; range 196.824–197.003 m); `2832107` (2008-03-10; range 196.33–196.797 m); `1929874` (2008-03-10; range 196.306–196.312 m); `3414690` (2008-03-10; range 196.138–196.299 m); `4082421` (2008-03-10; range 196.029–196.121 m); `4103469` (2008-03-10; range 195.904–196.004 m); `2473806` (2008-03-10; range 195.705–195.881 m); `1927305` (2008-03-10; range 195.61–195.705 m).

DI at span ends: no numeric DI within 50 m.

Flags: `archive_surface_height_disagreement`, `structure_hint`, `structure_unverified`, `survey_construction_unverified`, `track_style_defaulted_panels`, `track_zps_level_unverified`.

## osm-98560954 · bridge

OSM ways: [338644894](https://www.openstreetmap.org/way/338644894), [98560954](https://www.openstreetmap.org/way/98560954).

Mosty 3D features: 99 (the track meets the model's deck at an end).

| Line / direction | Nearest stops at ends | Length (m) | Proposed rule |
|---|---|---:|---|
| 17 / path | Hodkovičky → Hodkovičky | 37.7 | review_archive_profile |
| 17 / pathBack | Hodkovičky → Hodkovičky | 38.0 | review_archive_profile |

Archive candidates: `2342048` (2008-03-10; range 200.827–200.827 m); `1939301` (2008-03-10; range 194.34–199.663 m); `1928411` (2008-03-10; range 194.656–197.846 m); `4123333` (2008-03-10; range 194.213–197.096 m); `1926766` (2008-03-10; range 194.014–198.921 m); `4217290` (2008-03-10; range 200.874–200.874 m).

DI at span ends: no numeric DI within 50 m.

Flags: `archive_surface_height_disagreement`, `structure_hint`, `structure_unverified`, `survey_construction_unverified`, `track_style_defaulted_panels`, `track_zps_level_unverified`.

## osm-150611269 · bridge

OSM ways: [1176355492](https://www.openstreetmap.org/way/1176355492), [1176355503](https://www.openstreetmap.org/way/1176355503), [150611269](https://www.openstreetmap.org/way/150611269), [338644907](https://www.openstreetmap.org/way/338644907), [495705765](https://www.openstreetmap.org/way/495705765), [495705766](https://www.openstreetmap.org/way/495705766).

Mosty 3D features: 112 (the track meets the model's deck at an end).

| Line / direction | Nearest stops at ends | Length (m) | Proposed rule |
|---|---|---:|---|
| 17 / path | Černý kůň → Černý kůň | 150.9 | review_archive_profile |
| 17 / pathBack | Černý kůň → Černý kůň | 154.4 | review_archive_profile |

Archive candidates: `4315636` (2008-03-10; range 197.117–198.017 m); `1927639` (2008-03-10; range 193.29–198.584 m); `2794356` (2008-03-10; range 192.617–198.584 m); `4316210` (2008-03-10; range 197.054–197.854 m).

DI at span ends: no numeric DI within 50 m.

Flags: `archive_surface_height_disagreement`, `structure_hint`, `structure_unverified`, `survey_construction_unverified`, `track_style_defaulted_panels`, `track_zps_level_unverified`.

## osm-150611136 · bridge

OSM ways: [150611136](https://www.openstreetmap.org/way/150611136), [317188281](https://www.openstreetmap.org/way/317188281), [495705763](https://www.openstreetmap.org/way/495705763), [495705764](https://www.openstreetmap.org/way/495705764).

Mosty 3D features: 129 (the track meets the model's deck at an end).

| Line / direction | Nearest stops at ends | Length (m) | Proposed rule |
|---|---|---:|---|
| 17 / path | Nádraží Braník → Nádraží Braník | 379.7 | review_archive_profile |
| 17 / pathBack | Nádraží Braník → Nádraží Braník | 382.0 | review_archive_profile |

Archive candidates: `1930346` (2023-07-20; range 195.259–195.419 m); `2224493` (2023-07-20; range 195.42–195.657 m); `1928729` (2023-07-20; range 195.678–196.036 m); `2816051` (2023-07-20; range 196.057–196.252 m); `2213722` (2023-07-20; range 196.269–196.523 m); `1928843` (2023-07-20; range 196.548–196.702 m); `1941397` (2023-07-20; range 196.736–198.006 m); `4303050` (2023-07-20; range 198.122–201.01 m); `3904699` (2023-07-20; range 198.329–201.032 m); `2454421` (2023-07-20; range 196.281–198.196 m); `3398206` (2023-07-20; range 196.04–196.268 m); `1833778` (2023-07-20; range 195.627–196.04 m); `2798658` (2023-07-20; range 195.414–195.603 m); `1924345` (2023-07-20; range 195.241–195.389 m).

DI at span ends: no numeric DI within 50 m.

Flags: `structure_hint`, `structure_unverified`, `survey_construction_unverified`, `survey_surface_height_unavailable`, `track_style_defaulted_panels`, `track_zps_level_unverified`.

## unmapped-212a2fa901a0 · unmapped

OSM ways: not tagged.

| Line / direction | Nearest stops at ends | Length (m) | Proposed rule |
|---|---|---:|---|
| 17 / path | Palackého náměstí → Palackého náměstí | 0.8 | linear_di_portals |

Archive candidates: `1916265` (2008-09-23; range 197.557–197.557 m).

DI at span ends: 197.632 m / 1000428539805 / 5.7 m away / export 2026-10-31T00:00; 197.589 m / 1000428539805 / 1.6 m away / export 2026-10-31T00:00.

Flags: `track_style_defaulted_panels`, `track_zps_level_unverified`.

## osm-30619203 · Smetanovo nábřeží

OSM ways: [30619203](https://www.openstreetmap.org/way/30619203), [476507490](https://www.openstreetmap.org/way/476507490), [476507492](https://www.openstreetmap.org/way/476507492), [476507495](https://www.openstreetmap.org/way/476507495).

| Line / direction | Nearest stops at ends | Length (m) | Proposed rule |
|---|---|---:|---|
| 17 / path | Karlovy lázně → Karlovy lázně | 19.7 | retain_numeric_di |
| 17 / pathBack | Karlovy lázně → Karlovy lázně | 19.6 | retain_numeric_di |

Archive candidates: `2183734` (2008-03-10; range 191.257–191.263 m); `1930617` (2008-03-10; range 191.356–191.464 m); `1939280` (2008-03-10; range 191.47–191.557 m); `3920592` (2008-03-10; range 191.579–191.579 m); `2261790` (2008-03-10; range 191.596–191.623 m); `3961674` (2012-01-19; range 191.256–191.71 m).

DI at span ends: 191.160 m / 1000420073071 / 1.0 m away / export 2026-10-31T00:00; 191.635 m / 1000420073056 / 0.6 m away / export 2026-10-31T00:00; 191.713 m / 1000420072954 / 2.5 m away / export 2026-10-31T00:00; 191.172 m / 1000420072954 / 2.4 m away / export 2026-10-31T00:00.

Flags: `structure_hint`, `structure_unverified`, `track_style_defaulted_panels`, `track_zps_level_unverified`, `tunnel_unverified`.

## unmapped-7652c51cda3a · unmapped

OSM ways: not tagged.

| Line / direction | Nearest stops at ends | Length (m) | Proposed rule |
|---|---|---:|---|
| 17 / path | Staroměstská → Staroměstská | 3.8 | linear_di_portals |
| 17 / path | Staroměstská → Staroměstská | 4.8 | linear_di_portals |
| 17 / pathBack | Staroměstská → Staroměstská | 5.8 | linear_di_portals |
| 17 / pathBack | Staroměstská → Staroměstská | 4.9 | linear_di_portals |

Archive candidates: `3943492` (2012-01-19; range 191.177–191.177 m); `4184461` (2008-03-10; range 191.317–191.317 m); `2935831` (2012-06-25; range 191.259–191.384 m).

DI at span ends: 191.159 m / 1000420072865 / 6.1 m away / export 2026-10-31T00:00; 191.491 m / 1000428539847 / 41.2 m away / export 2026-10-31T00:00; 191.159 m / 1000420072865 / 29.7 m away / export 2026-10-31T00:00; 191.491 m / 1000428539847 / 16.6 m away / export 2026-10-31T00:00; 191.522 m / 1000428539004 / 21.4 m away / export 2026-10-31T00:00; 191.139 m / 1000420072959 / 31.5 m away / export 2026-10-31T00:00; 191.522 m / 1000428539004 / 40.7 m away / export 2026-10-31T00:00; 191.139 m / 1000420072959 / 13.1 m away / export 2026-10-31T00:00.

Flags: `track_style_defaulted_panels`, `track_zps_level_unverified`.

## osm-127867974 · Čechův most

OSM ways: [127867974](https://www.openstreetmap.org/way/127867974), [1328077842](https://www.openstreetmap.org/way/1328077842), [136122214](https://www.openstreetmap.org/way/136122214), [475364602](https://www.openstreetmap.org/way/475364602), [475364605](https://www.openstreetmap.org/way/475364605), [475364616](https://www.openstreetmap.org/way/475364616), [475364617](https://www.openstreetmap.org/way/475364617), [476507512](https://www.openstreetmap.org/way/476507512), [476507514](https://www.openstreetmap.org/way/476507514).

Mosty 3D features: 506 (the track meets the model's deck at an end).

| Line / direction | Nearest stops at ends | Length (m) | Proposed rule |
|---|---|---:|---|
| 17 / path | Čechův most → Čechův most | 4.7 | review_archive_profile |
| 17 / pathBack | Čechův most → Čechův most | 4.0 | review_archive_profile |
| 17 / pathBack | Právnická fakulta → Právnická fakulta | 9.6 | linear_di_portals |
| 17 / pathBack | Právnická fakulta → Právnická fakulta | 4.9 | linear_di_portals |

Archive candidates: `4348952` (2008-03-10; range 196.706–196.71 m); `1939286` (2008-03-10; range 196.795–196.827 m); `3886784` (2008-03-10; range 194.056–194.142 m); `2795568` (2008-03-10; range 193.08–193.08 m).

DI at span ends: 196.000 m / 1000428539949 / 44.6 m away / export 2026-10-31T00:00; 194.246 m / 1000428539949 / 2.4 m away / export 2026-10-31T00:00; 193.970 m / 1000428539949 / 2.4 m away / export 2026-10-31T00:00; 193.288 m / 1000428539949 / 7.3 m away / export 2026-10-31T00:00; 192.969 m / 1000428539949 / 2.4 m away / export 2026-10-31T00:00.

Flags: `ambiguous_survey_heights`, `structure_hint`, `structure_unverified`, `track_style_defaulted_panels`, `track_zps_level_unverified`.

## unmapped-35a361303197 · unmapped

OSM ways: not tagged.

| Line / direction | Nearest stops at ends | Length (m) | Proposed rule |
|---|---|---:|---|
| 22 / path | Vypich → Vypich | 12.6 | independent_height_required |
| 22 / pathBack | Vypich → Vypich | 12.5 | independent_height_required |

Archive candidates: `4133575` (2018-02-20; range 358.993–359.307 m); `1796047` (2018-02-20; range 358.934–359.294 m).

DI at span ends: no numeric DI within 50 m.

Flags: `track_style_defaulted_panels`, `track_zps_level_unverified`.

## unmapped-68c098542e8a · unmapped

OSM ways: not tagged.

| Line / direction | Nearest stops at ends | Length (m) | Proposed rule |
|---|---|---:|---|
| 22 / path | Malovanka → Malovanka | 42.1 | independent_height_required |
| 22 / pathBack | Malovanka → Malovanka | 38.3 | independent_height_required |
| 23 / pathBack | Malovanka → Malovanka | 38.3 | independent_height_required |

Archive candidates: `1923213` (2008-03-10; range 297.354–297.448 m); `3875638` (2008-03-10; range 297.339–297.389 m).

DI at span ends: no numeric DI within 50 m.

Flags: `track_style_defaulted_panels`, `track_zps_level_unverified`.

## unmapped-220b321f95bf · unmapped

OSM ways: not tagged.

| Line / direction | Nearest stops at ends | Length (m) | Proposed rule |
|---|---|---:|---|
| 22 / path | Brusnice → Brusnice | 96.0 | independent_height_required |
| 22 / path | Brusnice → Brusnice | 4.7 | independent_height_required |
| 22 / pathBack | Brusnice → Brusnice | 130.9 | independent_height_required |
| 23 / path | Brusnice → Brusnice | 96.0 | independent_height_required |
| 23 / path | Brusnice → Brusnice | 4.7 | independent_height_required |
| 23 / pathBack | Brusnice → Brusnice | 130.9 | independent_height_required |

Archive candidates: `2424348` (2008-03-10; range 268.461–268.772 m); `2214139` (2024-01-18; range 266.205–268.308 m); `2796658` (2008-03-10; range 266.0–266.076 m); `1917671` (2008-03-10; range 265.757–266.91 m); `3870242` (2012-06-08; range 266.872–266.9 m); `4078960` (2012-06-08; range 266.801–266.801 m); `2791631` (2008-03-10; range 265.673–265.673 m); `1925802` (2008-03-10; range 264.853–265.54 m); `1840908` (2008-03-10; range 265.55–267.08 m); `2893402` (2008-03-10; range 265.55–265.603 m); `3903622` (2008-03-10; range 266.9–267.053 m); `2262446` (2008-03-10; range 267.058–267.08 m); `2465749` (2024-01-18; range 267.087–268.708 m).

DI at span ends: no numeric DI within 50 m.

Flags: `archive_terrain_height_disagreement`, `track_zps_level_unverified`.

## unmapped-8880185638fb · unmapped

OSM ways: not tagged.

| Line / direction | Nearest stops at ends | Length (m) | Proposed rule |
|---|---|---:|---|
| 22 / path | Královský letohrádek → Královský letohrádek | 5.0 | independent_height_required |
| 22 / path | Královský letohrádek → Královský letohrádek | 5.0 | independent_height_required |
| 22 / pathBack | Královský letohrádek → Královský letohrádek | 3.2 | linear_di_portals |
| 22 / pathBack | Královský letohrádek → Královský letohrádek | 8.9 | independent_height_required |
| 22 / pathBack | Královský letohrádek → Královský letohrádek | 5.0 | independent_height_required |
| 23 / path | Královský letohrádek → Královský letohrádek | 5.0 | independent_height_required |
| 23 / path | Královský letohrádek → Královský letohrádek | 5.0 | independent_height_required |
| 23 / pathBack | Královský letohrádek → Královský letohrádek | 3.2 | linear_di_portals |
| 23 / pathBack | Královský letohrádek → Královský letohrádek | 8.9 | independent_height_required |
| 23 / pathBack | Královský letohrádek → Královský letohrádek | 5.0 | independent_height_required |

Archive candidates: `1903811` (2008-03-10; range 231.948–233.307 m); `3402066` (2008-03-10; range 216.712–216.712 m); `2799474` (2008-03-10; range 232.079–232.259 m); `1932867` (2008-03-10; range 233.125–233.125 m).

DI at span ends: 216.567 m / 1000428539752 / 1.6 m away / export 2026-10-31T00:00; 216.887 m / 1000428539752 / 1.6 m away / export 2026-10-31T00:00; 216.567 m / 1000428539752 / 1.6 m away / export 2026-10-31T00:00; 216.887 m / 1000428539752 / 1.6 m away / export 2026-10-31T00:00.

Flags: `track_style_defaulted_panels`, `track_zps_level_unverified`.

## survey-d124ac56827f · survey_level

OSM ways: not tagged.

| Line / direction | Nearest stops at ends | Length (m) | Proposed rule |
|---|---|---:|---|
| 22 / path | Královský letohrádek → Královský letohrádek | 4.2 | linear_di_portals |
| 22 / pathBack | Královský letohrádek → Královský letohrádek | 4.5 | linear_di_portals |
| 23 / path | Královský letohrádek → Královský letohrádek | 4.2 | linear_di_portals |
| 23 / pathBack | Královský letohrádek → Královský letohrádek | 4.5 | linear_di_portals |

Archive candidates: `1929790` (2008-03-10; range 225.492–225.637 m); `4074097` (2008-03-10; range 225.51–225.67 m).

DI at span ends: 225.685 m / 1000428539621 / 0.6 m away / export 2026-10-31T00:00; 225.335 m / 1000428539826 / 1.9 m away / export 2026-10-31T00:00; 225.460 m / 1000428539669 / 0.4 m away / export 2026-10-31T00:00; 225.760 m / 1000428538965 / 1.6 m away / export 2026-10-31T00:00; 225.685 m / 1000428539621 / 0.6 m away / export 2026-10-31T00:00; 225.335 m / 1000428539826 / 1.9 m away / export 2026-10-31T00:00; 225.460 m / 1000428539669 / 0.4 m away / export 2026-10-31T00:00; 225.760 m / 1000428538965 / 1.6 m away / export 2026-10-31T00:00.

Flags: `archive_surface_height_disagreement`, `paved_surface_height_disagreement`, `track_style_defaulted_panels`.

## unmapped-ba62bb8b8cb9 · unmapped

OSM ways: not tagged.

| Line / direction | Nearest stops at ends | Length (m) | Proposed rule |
|---|---|---:|---|
| 22 / path | Malostranská → Malostranská | 0.6 | linear_di_portals |
| 22 / path | Malostranská → Malostranská | 4.7 | linear_di_portals |
| 22 / pathBack | Malostranská → Malostranská | 1.2 | linear_di_portals |
| 22 / pathBack | Malostranská → Malostranská | 1.2 | linear_di_portals |
| 22 / pathBack | Malostranská → Malostranská | 24.2 | linear_di_portals |
| 22 / pathBack | Malostranská → Malostranská | 1.0 | linear_di_portals |
| 22 / pathBack | Malostranská → Malostranská | 0.8 | linear_di_portals |
| 23 / path | Malostranská → Malostranská | 0.6 | linear_di_portals |
| 23 / path | Malostranská → Malostranská | 4.7 | linear_di_portals |
| 23 / pathBack | Malostranská → Malostranská | 1.2 | linear_di_portals |
| 23 / pathBack | Malostranská → Malostranská | 1.2 | linear_di_portals |
| 23 / pathBack | Malostranská → Malostranská | 24.2 | linear_di_portals |
| 23 / pathBack | Malostranská → Malostranská | 1.0 | linear_di_portals |
| 23 / pathBack | Malostranská → Malostranská | 0.8 | linear_di_portals |

Archive candidates: `1792945` (2008-03-10; range 200.684–200.684 m); `2233273` (2008-03-10; range 189.667–189.667 m); `1931645` (2008-09-29; range 188.469–188.477 m); `2866102` (2008-03-10; range 188.495–188.501 m); `3906263` (2008-03-10; range 189.055–189.424 m); `2678186` (2008-03-10; range 200.733–200.878 m).

DI at span ends: 200.719 m / 1000428539399 / 0.4 m away / export 2026-10-31T00:00; 200.600 m / 1000428539682 / 0.3 m away / export 2026-10-31T00:00; 189.820 m / 1000428538930 / 2.4 m away / export 2026-10-31T00:00; 189.654 m / 1000428538930 / 2.4 m away / export 2026-10-31T00:00; 188.425 m / 1000428539769 / 0.6 m away / export 2026-10-31T00:00; 188.440 m / 1000428539769 / 0.2 m away / export 2026-10-31T00:00; 188.450 m / 1000428539769 / 0.2 m away / export 2026-10-31T00:00; 188.465 m / 1000428539769 / 0.2 m away / export 2026-10-31T00:00; 188.821 m / 1000428539297 / 12.2 m away / export 2026-10-31T00:00; 190.131 m / 1000428539799 / 28.0 m away / export 2026-10-31T00:00; 200.550 m / 1000428539738 / 0.5 m away / export 2026-10-31T00:00; 200.715 m / 1000428539738 / 0.5 m away / export 2026-10-31T00:00; 200.798 m / 1000428539363 / 0.6 m away / export 2026-10-31T00:00; 200.970 m / 1000428539363 / 1.8 m away / export 2026-10-31T00:00; 200.719 m / 1000428539399 / 0.4 m away / export 2026-10-31T00:00; 200.600 m / 1000428539682 / 0.3 m away / export 2026-10-31T00:00; 189.820 m / 1000428538930 / 2.4 m away / export 2026-10-31T00:00; 189.654 m / 1000428538930 / 2.4 m away / export 2026-10-31T00:00; 188.425 m / 1000428539769 / 0.6 m away / export 2026-10-31T00:00; 188.440 m / 1000428539769 / 0.2 m away / export 2026-10-31T00:00; 188.450 m / 1000428539769 / 0.2 m away / export 2026-10-31T00:00; 188.465 m / 1000428539769 / 0.2 m away / export 2026-10-31T00:00; 188.821 m / 1000428539297 / 12.2 m away / export 2026-10-31T00:00; 190.131 m / 1000428539799 / 28.0 m away / export 2026-10-31T00:00; 200.550 m / 1000428539738 / 0.5 m away / export 2026-10-31T00:00; 200.715 m / 1000428539738 / 0.5 m away / export 2026-10-31T00:00; 200.798 m / 1000428539363 / 0.6 m away / export 2026-10-31T00:00; 200.970 m / 1000428539363 / 1.8 m away / export 2026-10-31T00:00.

Flags: `track_style_defaulted_panels`, `track_zps_level_unverified`.

## osm-476172743 · tunnel

OSM ways: [476172743](https://www.openstreetmap.org/way/476172743), [476172746](https://www.openstreetmap.org/way/476172746).

| Line / direction | Nearest stops at ends | Length (m) | Proposed rule |
|---|---|---:|---|
| 22 / path | Malostranské náměstí → Malostranské náměstí | 22.9 | linear_di_portals |
| 22 / pathBack | Malostranské náměstí → Malostranské náměstí | 22.2 | linear_di_portals |
| 23 / path | Malostranské náměstí → Malostranské náměstí | 22.9 | linear_di_portals |
| 23 / pathBack | Malostranské náměstí → Malostranské náměstí | 22.2 | linear_di_portals |

Archive candidates: `3918129` (2008-03-10; range 191.623–191.623 m); `1842449` (2008-03-10; range 191.624–191.624 m); `1928295` (2008-03-10; range 191.727–191.986 m).

DI at span ends: 191.645 m / 1000428539178 / 0.2 m away / export 2026-10-31T00:00; 191.520 m / 1000428539011 / 1.5 m away / export 2026-10-31T00:00; 191.415 m / 1000428539223 / 1.7 m away / export 2026-10-31T00:00; 190.019 m / 1000428539742 / 4.3 m away / export 2026-10-31T00:00; 191.645 m / 1000428539178 / 0.2 m away / export 2026-10-31T00:00; 191.520 m / 1000428539011 / 1.5 m away / export 2026-10-31T00:00; 191.415 m / 1000428539223 / 1.7 m away / export 2026-10-31T00:00; 190.019 m / 1000428539742 / 4.3 m away / export 2026-10-31T00:00.

Flags: `di_archive_height_disagreement`, `known_archive_disagreement`, `no_unambiguous_current_geometry`, `structure_hint`, `structure_unverified`, `track_style_defaulted_panels`, `track_zps_level_unverified`, `tunnel_unverified`.

## unmapped-2acf2f78d20a · unmapped

OSM ways: not tagged.

| Line / direction | Nearest stops at ends | Length (m) | Proposed rule |
|---|---|---:|---|
| 23 / path | Královka → Malovanka | 31.5 | independent_height_required |

Archive candidates: `4075925` (2008-03-10; range 297.482–297.727 m); `2423824` (2008-03-10; range 297.461–297.48 m).

DI at span ends: no numeric DI within 50 m.

Flags: `track_style_defaulted_panels`, `track_zps_level_unverified`.

## Ordinary no-data proposals

181.650 direction-metres use the documented IPR-terrain-plus-style proposal for #20.
These are flagged approximations. No structure receives an earth-height fallback.
