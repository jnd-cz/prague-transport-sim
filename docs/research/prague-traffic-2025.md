# Prague street traffic: vehicle mix, sizes and city-wide numbers (research for #864)

Researched 2026-11-26. **M** marks a measured or registry value, with its source and its place in that source. **E** marks an estimate. The main source is TSK hl. m. Prahy, *Ročenka dopravy Praha 2025* (published 2026; data for 2025), in the store's `raw/reference/tsk/`:
- the PDF, whose charts were read by rendering its pages with pdf.js;
- the maintainer's Markdown conversion, which kept the tables.

Page numbers are the yearbook's printed ones; the PDF's page number is the same.

Its p. 87 allows sharing texts, charts and data with the source named: "Technická správa komunikací hl. m. Prahy, a. s.".

## 1. Which vehicles are in the traffic

### Traffic-stream composition (yearbook §2.3, p. 12, "Skladba dopravního proudu"; weekday, both directions, 0–24 h)

| 2025, % of vehicles | cars and vans ≤ 3.5 t | motorcycles | trucks > 3.5 t | buses outside PID |
|---|---|---|---|---|
| **M** central cordon: the wider centre (Petřín, Letná, Negrelli viaduct, Riegrovy sady, Vyšehrad) | 95.9 | 2.0 | 1.4 | 0.7 |
| **M** outer cordon: the main roads into the built-up city | 88.1 | 0.4 | 11.1 | 0.4 |

- **M** For the whole network, cars and vans up to 3.5 t were 91 % of vehicle-km: 21.288 of 23.328 million vehicle-km per weekday (§2.2, p. 9).
- **M** Cyclists are 0.1–1.0 % of vehicles (p. 12, note). Motorcycles in the centre were 1.7–3.0 % in 2020–2025.
- The counts do not separate cars from vans: both are "osobní a dodávkové do 3,5 t". A 3.5 t box truck is in that column too.
- **M** Trucks over 3.5 t at the city boundary, from toll data (31 Mar – 14 Apr 2025, §2.5, p. 19):
  - about 40,000 enter on a weekday;
  - 75 % are articulated or with trailers, 15 % medium two-axle, 5 % heavy three-axle, 5 % coaches;
  - 70 % of them are transit, mostly on the motorways.
  - Inside the centre, trucks are 1.4 %.

### Registered vehicles (yearbook §2.4, pp. 17–18; central vehicle register as of 1 Jan 2026)

| **M** | Czech Republic | Prague |
|---|---|---|
| motor vehicles | 9,279,809 | 1,362,135 |
| passenger cars (M1) | 6,815,057 | 1,088,201 |
| goods vehicles | 837,283 | 145,183 |
| of which up to 3.5 t (N1) | 646,083 | 114,347 |
| motorcycles | 1,371,017 | 110,791 |
| buses | 21,108 | 4,232 |

- N1 vans are 9.5 % of Prague's M1 + N1 (8.7 % nationally). The registry over-counts Prague: about 42 % of the country's new registrations are made there, many by companies whose cars run elsewhere (yearbook p. 17).
- **M** Median Prague passenger car: **4,541 × 1,810 × 1,495 mm** (length × width × height). Median curb mass 1,441 kg, permitted mass 1,950 kg (p. 18). The median footprint has grown slowly over 25 years. This is the calibration target for the game's car mix (§3).
- **M** Average age in Prague: 12.86 years for passenger cars and 14.55 for all vehicles (p. 18). The national average for cars was 16.68 years in December 2025 (SDA via ČT24).
- **M** Fuel of Prague's passenger cars (p. 18, chart):
  - petrol 54.56 %, diesel 40.41 %, alternative 4.77 %, not stated 0.25 %;
  - of the alternative: battery-electric 1.638 %, petrol-electric hybrids 1.447 %, LPG 0.93 %, CNG/LNG 0.47 %.

  So about 1 car in 30 is plug-in or hybrid: quiet when driving slowly.
- **M** Median footprint (length × width) by year of first registration (p. 18, chart): about 7.5 m² for cars from 2000, 8.0 m² from 2006, and 8.4–8.6 m² from 2019–2024. The fleet's median is 8.2 m² (4.541 × 1.810).
- **M** Car occupancy: 1.33 people (§2.2, p. 11).

### New-car sales, 2025 (Cebia / SDA; national)

**M** Top ten:

| rank | model | units |
|---|---|---|
| 1 | Octavia | 18,330 |
| 2 | Kamiq | 11,550 |
| 3 | Karoq | 11,454 |
| 4 | Kodiaq | 10,854 |
| 5 | Fabia | 10,117 |
| 6 | Scala | 9,536 |
| 7 | i30 | 8,031 |
| 8 | Superb | 6,620 |
| 9 | Corolla | 6,465 |
| 10 | Tucson | 5,964 |

- **M** SUVs and crossovers are 48 % of the top 30 (71.8k of 150.4k).
- **M** Light goods vehicles: 20,278 new registrations, against 248,719 cars.

## 2. Vehicle sizes by class

These are maker figures: length × body width without mirrors × height, then wheelbase, in metres. The rows marked M were checked against a source; the rest are **E** (from memory, within a few cm by generation and facelift). Spot-check a model before a type is fixed to it.

| class | models | L × W × H | WB |
|---|---|---|---|
| city car | Citigo / up!, i10, Picanto, Aygo X, Fiat 500, Spring | 3.57–3.73 × 1.63–1.74 × 1.48–1.52 | 2.3–2.4 |
| small, older fleet | Fabia I–III, Felicia, Yaris, Swift, older Polo / Fiesta / Corsa | 3.86–4.0 × 1.64–1.73 × 1.45–1.50 | 2.45–2.50 |
| small, current | Fabia IV, i20, Clio, Polo | 4.04–4.11 × 1.75–1.78 × 1.45 | 2.56 |
| compact | Golf 8, i30, Ceed, Scala, Corolla hatchback | 4.28–4.37 × 1.79–1.80 × 1.44–1.47 | 2.62–2.65 |
| Octavia class | Octavia IV liftback or Combi 4.69 × 1.83 × 1.47 (mirrors ≈ 2.00); Rapid 4.48 | — | 2.69 |
| large | Superb, saloon or Combi | 4.90 × 1.85 × 1.48 | 2.84 |
| SUV | Kamiq 4.24 × 1.79 × 1.53 · Karoq 4.38 × 1.84 × 1.60 · Duster 4.34 × 1.81 × 1.66 · Tucson 4.50 × 1.87 × 1.65 · Enyaq 4.65 × 1.88 × 1.62 · Kodiaq 4.76 × 1.86 × 1.66 | — | 2.64–2.79 |
| small van / MPV | Caddy, Berlingo / Partner / Combo | 4.40–4.85 × 1.85 × 1.80–1.88 | 2.76–2.97 |
| mid van | **M** Transit Custom 2023+ 5.05 / 5.45 × 2.00 (mirrors 2.28) × 1.97, WB 3.10 / 3.50 (Parkers); Transporter T6.1 4.90 / 5.30 × 1.90 × 1.99; Trafic 5.00 / 5.40 × 1.96 × 1.97; Vito 4.90–5.37 × 1.93 × 1.91 | — | 3.0–3.5 |
| large van | **M** Ducato / Boxer / Jumper L2H1 5.41 × 2.05 (mirrors ≈ 2.50) × 2.25–2.27, WB 3.45 (Vans Direct, CarsGuide); Sprinter 5.27 / 5.93 / 6.97 × 2.02 × 2.36–2.83; Transit, Master, Daily 5.5–6.0 × 2.0–2.07 | — | 3.3–4.3 |
| 3.5 t box truck | **M** Daily, Sprinter or Master chassis with a ≈ 4.2 m box. Dealer listings give the box inside as 4.1–4.4 × 2.1 × 2.1–2.3, on a 4.10 m wheelbase. **E** about 6.8–7.3 × 2.2–2.3 (box) × 3.1–3.4 overall | — | 3.7–4.35 |
| medium truck | MAN TGL, Atego, DAF LF, refuse truck | ≈ 7.5–9 × 2.55 × 3.4–3.7 | ≈ 4.5 |

Ordinary cars have tracks of about 1.52–1.58 m.

## 3. What this means for the game's types (#864)

- **E** The mix for the streets with trams, which lie mostly inside or near the central cordon, as % of all vehicles:

  | small | compact | sedan | estate | SUV | MPV / small van | mid van | large van | box 3.5 t | motorcycle | medium truck | coach |
  |---|---|---|---|---|---|---|---|---|---|---|---|
  | 13 | 15 | 14 | 14 | 23 | 6 | 5.5 | 3.5 | 2 | 2 | 1.4 | 0.6 |

- **E** How the mix was set:
  - The motorcycle, truck and coach shares are the central cordon's (§1).
  - Vans are about 14 % of the ≤ 3.5 t vehicles, small vans included. That is above N1's 9.5 % of the registry, because vans are used more per day than private cars.
  - The split among cars follows the sales mix with an older fleet.
  - With the SUV type spread 4.2–4.75 m by instance scale, this mix's median passenger car is about 4.53 × 1.82 m, against the registry's 4.541 × 1.810 m.
  - The median height (1.495 m) is a weak check: many hatchbacks sit at 1.47–1.50 m.
- **E** On lines that leave the centre on main roads, trucks rise toward the outer cordon's 11 %. Most of that is motorway transit, which trams do not meet.
- The game has no motorcycle and no coach type: 2.6 % of the centre's traffic.

## 4. Numbers for the city-wide simulation (yearbook, 2025)

### Trams (§3.3, p. 24)

**M** Network and service:
- 36 lines: 27 by day, 9 by night;
- 148.8 km of network;
- 285 stop names at 624 stop poles, 522 m apart on average;
- **average travel speed 19.09 km/h**;
- 429 trains in service at the peak;
- 7,002 trips a weekday (200 at night);
- 1,266,210 passengers a weekday, 368.2 million a year;
- 60.05 million car-km a year;
- service about 4:45–0:15, night service 0:15–5:00.

**M** Other details:
- The base interval is 15 (7.5) minutes; on the 2025 Advent weekends it was 12 (6).
- Low-floor service is 71 % in the timetable and 77 % in practice (p. 27).
- The new Škoda 52T entered service on 3 Nov 2025, with 20 cars by 14 Dec. A further 20 are due in 2026, with an option for 160 more (p. 29).

### Signals (§6.1, pp. 40–41; §7.1, pp. 51–53)

**M** Counts:
- 682 controllers at 717 signalled places, 149 of them crossings for pedestrians only;
- 557 controllers connected to a centre.

**M** On the tram network:
- 258 signals: 243 (94 %) with tram priority;
- **absolute priority at 64 (25 %)**: every tram passes without stopping, except trams arriving one after another;
- **conditional priority at 179 (69 %)**: fewer and shorter stops than without priority;
- no priority at 15 (6 %).

**M** Night and weak traffic:
- **67 % of signals run continuously.** The rest go dark or flashing at times.
- 139 places run "flashing yellow" with a pedestrian demand. In that mode, public transport has no priority.

**M** Other:
- Raised kerbs that keep cars off the tram track total 13,850 m.
- Bus lanes on tram track total 20,000 m, out of 74,800 m of bus lanes.
- Since 22 Oct 2025, 14 bus lines cross Vítězné náměstí on the tram track (p. 54).

### Traffic by hour, weekday and month (§2.3, pp. 12–13, charts; whole network, 2025)

**M** The share of a weekday's 24 h traffic in each hour, %. All vehicles (p. 12):

| 0–1 | 1–2 | 2–3 | 3–4 | 4–5 | 5–6 | 6–7 | 7–8 | 8–9 | 9–10 | 10–11 | 11–12 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.9 | 0.6 | 0.5 | 0.5 | 1.0 | 2.5 | 5.7 | **6.5** | 6.3 | 5.9 | 5.6 | 5.7 |

| 12–13 | 13–14 | 14–15 | 15–16 | 16–17 | 17–18 | 18–19 | 19–20 | 20–21 | 21–22 | 22–23 | 23–24 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 5.8 | 6.0 | 6.2 | 6.6 | **6.7** | 6.4 | 5.9 | 4.8 | 3.6 | 2.8 | 2.1 | 1.4 |

**M** "Slow vehicles" (trucks and buses; p. 13), which peak at 10–11 with 7.3 % and are a larger share at night:

| 0–1 | 1–2 | 2–3 | 3–4 | 4–5 | 5–6 | 6–7 | 7–8 | 8–9 | 9–10 | 10–11 | 11–12 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1.6 | 1.4 | 1.7 | 2.4 | 3.5 | 5.5 | 6.0 | 5.5 | 5.7 | 6.8 | **7.3** | 7.1 |

| 12–13 | 13–14 | 14–15 | 15–16 | 16–17 | 17–18 | 18–19 | 19–20 | 20–21 | 21–22 | 22–23 | 23–24 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 6.7 | 6.5 | 5.8 | 4.8 | 4.0 | 3.5 | 3.4 | 3.0 | 2.3 | 2.0 | 1.9 | 1.6 |

**M** By weekday, all vehicles, % of an average weekday (p. 13):

| Mon | Tue | Wed | Thu | Fri | Sat | Sun |
|---|---|---|---|---|---|---|
| 97 | 100 | 101 | 102 | 100 | 74 | 70 |

**M** By month, all vehicles, % of the year's average (p. 13):

| Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 95 | 97 | 101 | 105 | 106 | 106 | 90 | 92 | 103 | 106 | 102 | 97 |

**E** For the simulation:
- A street's traffic at hour h on day d of month m is its weekday 24 h volume × hour share × weekday factor × month factor.
- The peak hour carries about 6.5 % of the day.
- The share of trucks and buses in the traffic changes through the day. It is their daily share times slow ÷ all for that hour: about 4.8× at 3–4 h (2.4 ÷ 0.5) and 0.55× at 17–18 h (3.5 ÷ 6.4). In the centre that is about 7 % at 3 a.m. against 0.8 % in the evening peak.
- These are whole-network shapes. The yearbook gives no per-street hourly profile, and the tram streets in the centre may peak differently.

### Car traffic (§2.2, pp. 9–11)

**M** Volumes:
- 23.3 million vehicle-km a weekday on the whole network;
- the central cordon is crossed by 474,000 vehicles a weekday (both directions);
- the outer cordon is crossed by 718,000.

**M** Busiest at-grade junctions (vehicles a day):
- Černokostelecká – Průmyslová: 69,000;
- Poděbradská – Kbelská: 68,000;
- Kolbenova – Kbelská: 63,000;
- Mezibranská – Žitná: 59,000;
- Bělohorská – Kukulova: 58,000.

**M** Volumes per section of the network (vehicles in 24 h on a weekday):
- printed as labels on the city map inside the front cover (PDF p. 2): readable by eye, too dense to transcribe;
- published as a table on TSK's website (p. 11), not fetched yet. That table is the source for car volumes per street in a city-wide run (it needs a snapshot, DATA.md).

### Accidents (§8.1, pp. 55–57)

**M** 2025 totals:
- 11,038 accidents;
- 15 deaths, 168 seriously and 2,231 lightly injured;
- 508 accidents with pedestrians;
- 1.5 accidents per million vehicle-km. On ramps the rate is 4.1; on radials 0.4; on the city ring 0.5.

**M** Accidents with the driver at fault:

| cause | accidents |
|---|---|
| inattention | 2,749 |
| following too close | 1,269 |
| changing lanes without giving way | 823 |
| not yielding as signed | 572 |
| left turn without giving way | 451 |
| red light | 133 |

### City and modes (§1, pp. 6–7)

**M** City:
- 1,407,084 people on 496 km²;
- 4,104 km of road;
- 773 cars per 1,000 people.

**M** Trips by people of Prague and the Central Bohemian Region within Prague on a weekday (the 2021 survey):
- public transport 37 %;
- walking 35 %;
- car 25 %;
- combined public transport and car 2 %;
- bicycle 1 %.

**M** Paid parking zones: 177,602 spaces, by district (p. 68), e.g. Praha 1: 9,178, Praha 2: 12,210, Praha 6: 28,777.

## Sources

- TSK hl. m. Prahy, *Ročenka dopravy Praha 2025* (2026). The 2024 edition is at https://cdn.tsk-praha.cz/portal/2025/06/TSK-Rocenka-dopravy-za-rok-2024.pdf; older ones are at cdn.tsk-praha.cz/portal/2025/03/udi-rocenka-YYYY-cz.pdf.
- [Cebia, TOP 30 nejprodávanější auta Česka v roce 2025](https://www.cebia.cz/novinky/trh-s-automobily/top-30-nejprodavanejsi-auta-ceska-v-roce-2025)
- [kurzy.cz, sales 2025 (SDA)](https://zpravy.kurzy.cz/843131-prodeje-novych-osobnich-aut-v-r-2025-rostly-mezirocne-o-7-4--na-249-000-dovoz-ojetin-rostl-o-5-6/)
- [Parkers, Transit Custom](https://parkers.co.uk/vans-pickups/ford/transit-custom/2024-dimensions)
- [Vans Direct, Ducato](https://www.vansdirect.co.uk/load-sizing-guide/fiat-ducato-dimensions/)
- [vanreviewer, Daily](https://vanreviewer.co.uk/iveco/daily/dimensions/10346/)
- Box truck listings: [machineseeker](https://www.machineseeker.com/iveco-daily+35-160/i-22336137), [truckscout24](https://www.truckscout24.com/tsp/ts-209-31-287)

## Rough checks for a city-wide run

From §4, to compare against once the whole network runs (#731, #722):
- the average tram travel speed of 19.09 km/h;
- 429 trains at the peak;
- 7,002 trips a weekday.

The traffic's hourly shape above is the input for car volumes through the day.

## Not read

- TSK's table of volumes per section of the network (yearbook p. 11).
- The 2020 report on Prague's vehicle fleet (`zprava-skladba-vozparku-v-praze-2020`): its host did not resolve on 2026-11-26.
