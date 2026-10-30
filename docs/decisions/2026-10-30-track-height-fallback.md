# Archived DTMP track heights: coverage and fallback assessment

**Date:** 2026-10-30. **Scope:** acquisition and comparison for #61, following the user's request;
no world import or generated line-data changes. Import and source selection remain #20.

## Result

The archived tram axes provide a substantial height fallback: **210.542 km of surface-track
candidates out of 222.892 km of current DI tracks lacking usable Z (94.46%)**, after excluding
tagged structures and known disagreements. This is a conservative availability screen, not a
certification of every historical height. Only **2.319 km** of those candidates also have >=10 m
of agreeing numeric DI overlap on the **same archived feature**; **208.223 km** remain unvalidated
by that test. Neither source is an independent ground-truth survey of the other.

Before exclusions, an archived numeric height matches **218.294 km (97.94%)** of missing DI height
coverage. Of that, **7.725 km** needs separate bridge/tunnel/level review and **0.026 km** belongs to
archived features with known height disagreements. **4.598 km** has no usable geometric match or
is ambiguous. Tightening the horizontal limit from 1 m to 0.5 m still leaves **217.767 km (97.70%)**
of geometric candidates, before the structure/disagreement exclusions.

## Acquired sources and dates

- Archived service: [DTMP MapServer layer 10](https://gs-pub.praha.eu/arcgis/rest/services/dtmp/dtmp/MapServer/10),
  class **55010**, “TM – MHD – osa kolejí”. Metro (55015), railway and siding classes are excluded.
  The service advertises Z. Requests explicitly use `returnZ=true`, `outSR=5514`, and all attributes.
- Acquired the complete, small city-wide tram-axis layer: **9806 features**, approximately **15.43 MB**
  in **23 files** (20 feature batches, layer metadata, complete ID inventory, provenance). Assessment
  is clipped to the **same 16 DI export polygons** used in the prior district report; **9484 archived
  features** intersect that area. Boundary-crossing records retain their full original geometry.
- Every one of those 9484 records has finite, nonzero Z at every vertex in the broad Prague sanity
  range 100–500 m. The observed range is **178.863–382.346 m**. Numeric availability does not establish
  that a vertex describes the top of rail or the correct level.
- The archive belongs to the pre-July-2024 DTMP. Retained record fields are more specific than the
  archive label: within the assessed area `DAT_VZNIK` is present on 9484 records and `DAT_ZMENA` on
  4199; the latest change is **2024-04-18**. `ROK` ranges from 1993 to 2024, with 56 records carrying
  `-99`. These fields are retained as provenance, not assumed to be observation dates.
- Raw `PUVOD` counts: DSP 7287, ADS 1974, EC 156, JDM 53, PDO 14. Raw `GTC_ID` counts: 3 on 5594,
  5 on 3390, 7 on 500. `STAV_ZMENA`: I 7817, U 1667. The report preserves these codes without
  inventing an interpretation of their height accuracy.
- Current comparator: the **2026-09-30 DI JVF** packages, pinned in snapshot `2026-10-30`. Identical
  repeated DI ID/path records across district packages are deduplicated. Geometry uses the shared
  city frame in `tools/geo.py`; source Z is preserved, following the project's Bpv convention.
- Licence: **CC BY 4.0**, “datový podklad © IPR Praha”, using IPR's
  [download-service terms I.8](https://geoportalpraha.cz/backend/getdokument/1), retained in the DI
  source group. Raw acquisition is pinned in **snapshot `2026-10-30b`**. No upstream request is made
  by the offline analysis.

## Matching and the meaning of the percentages

The tool assesses **333.252 km** of distinct current DI ID/path geometry inside the polygon union.
Of that, **110.360 km** has numeric Z and **222.892 km** lacks it. This length denominator differs
from the earlier feature-count denominator: segmented features vary greatly in length.

Each original DI segment is clipped, then sampled in equal midpoint bins **no longer than 5 m**.
Every observation is weighted by its exact bin length. Per-district assignment uses the bin midpoint,
so individual district totals are estimates near district boundaries. The overall union total uses
the clipped lengths. These are source-track lengths; overlaps with different IDs are not silently
declared to be one physical track.

An archived segment must be within **1 m** and within **15 degrees** of the current track tangent,
allowing either travel direction. Height is linearly interpolated between the two source vertices;
zero/nonfinite/out-of-range endpoint heights are never bridged. A perpendicular crossing cannot
supply a height, and a farther track with numeric Z does not replace a nearer track missing Z.
Nearly equally close candidates (within 0.25 m of the closest fit) disagreeing in height by >0.3 m
are ambiguous and excluded. These rules estimate height coverage, not switch topology or connectivity.

The structure mask uses the pinned local OSM extract: **294 tram ways** carrying a bridge, tunnel,
covered or nonzero-layer tag, buffered **5 m** to allow for registration and nearby track geometry.
Those matches require separate review. This intentionally holds out some correct heights too;
absence of an OSM tag still does not prove that a site is ordinary surface track.

An archived feature is provisionally corroborated when >=10 m of its overlap with numeric DI has
a length-weighted p90 absolute height difference <=0.3 m. Features failing that test are marked as
disagreements; candidates elsewhere on them are held out. The test is deliberately local to the
feature and is not an accuracy guarantee for another record, a neighbouring track or a whole district.

## Height agreement where both sources have numeric Z

Signed differences below are **archive minus current DI**, length-weighted. Current DI is a
comparator, not assumed truth: almost all DI features carry the incomplete-data flag.

| Compared geometry | Matched km | Median difference | p90 absolute | p99 absolute | Within 0.30 m |
|---|---:|---:|---:|---:|---:|
| All | 107.199 | approximately 0.000 m | 0.160 m | 9.082 m | 94.84% |
| Outside structure mask | 100.068 | approximately 0.000 m | 0.137 m | 0.729 m | 96.76% |
| Inside structure mask | 7.131 | approximately 0.000 m | 10.131 m | 13.739 m | 67.94% |

Across all matches, **85.39%** is within 0.10 m, but **2.605 km** differs by more than 1 m.
Of that, **2.184 km** lies on tagged structures and **0.422 km** does not. The near-zero median and
millimetre-scale typical plan fit suggest shared source history for many records; they do not
independently validate the heights. The large tail rules out applying the archive everywhere.

### A reproducible structure failure

On Trojský most, current DI record **1000413716080** and archived OBJECTID **5168282** match within
**0.137 m** at city-frame `[1422.058, 2620.908]`. DI interpolates to **194.398 m**; the archive to
**180.412 m**, a **−13.987 m** difference. Nearby vertices in the existing compiled ZPS deck are
**194.43–194.55 m**, supporting the current deck level in this case. Those compiled vertices are a
diagnostic cross-check, not a new independent survey. The JSON report retains both source IDs,
positions, heights and deck evidence for the largest discrepancies.

There are also large disagreements away from tagged structures (one reaches approximately 24.93 m).
Do not assume that either source is correct solely because its Z is numeric or its record is newer.
Resolve such cases against a surveyed surface, structure model, observation date and physical level.

## Same-area district coverage

“Candidate” below means the archived height passes the plan/direction checks and is outside the
structure mask and known-disagreement records. Percentages use **DI length lacking Z** as denominator.
Zero missing length means no height fallback is needed there; it does not certify the existing Z.

| District | DI missing Z, km | Surface candidates, km | Missing coverage supplied |
|---|---:|---:|---:|
| Praha 1 | 17.210 | 15.319 | 89.01% |
| Praha 2 | 23.237 | 22.549 | 97.04% |
| Praha 3 | 19.479 | 19.392 | 99.55% |
| Praha 4 | 28.435 | 26.609 | 93.58% |
| Praha 5 | 25.654 | 25.073 | 97.73% |
| Praha 6 | 45.652 | 44.306 | 97.05% |
| Praha 7 | 16.728 | 16.272 | 97.28% |
| Praha 8 | 18.460 | 16.137 | 87.42% |
| Praha 9 | 11.643 | 11.200 | 96.20% |
| Praha 10 | 3.608 | 3.205 | 88.84% |
| Praha 12 | 9.104 | 6.796 | 74.65% |
| Praha 13 | 0 | 0 | — |
| Praha 14 | 3.338 | 3.338 | 100.00% |
| Praha 17 | 0.345 | 0.344 | 99.66% |
| Praha-Libuš | 0 | 0 | — |
| Praha-Troja | 0 | 0 | — |
| **Union** | **222.892** | **210.542** | **94.46%** |

## Coverage on the five lines

Both `path` and `pathBack` are sampled. Route-to-DI matching allows **2 m** and the same 15-degree
tangent check; archive-to-DI matching retains the **1 m** limit. The denominator includes route
positions with no usable DI match. Lengths are **direction/run kilometres**, including repeated
traversals in the 9 → 10 run, and shared tracks occur in several rows; do not add these to obtain
network length.

| Line | Missing route heights, km | Geometric archive candidates, km | Surface candidates, km | Missing coverage supplied |
|---|---:|---:|---:|---:|
| 9 | 40.433 | 40.178 | 39.359 | 97.34% |
| 17 | 25.000 | 24.924 | 21.226 | 84.91% |
| 22 | 21.480 | 21.313 | 21.273 | 99.04% |
| 23 | 12.637 | 12.637 | 12.576 | 99.52% |
| 37 | 10.188 | 10.171 | 10.171 | 99.83% |

Line 17's lower conservative coverage largely reflects **3.692 direction-km of structure matches**
held out for review. Those heights remain available in the archive; they have not been discarded.

## Use in the future importer

Use archived Z as a **provenance-bearing candidate for a matching surface track**, preserving the
current geometry when it is preferable. Keep source IDs, dates, matching distance, tangent agreement,
height evidence and confidence separately for geometry and height. Do not add an old alignment merely
because it has Z. Structures, ambiguous matches, known disagreements, changed alignments and transitions
between sources need explicit review. The measurements support a large fallback opportunity while
leaving those decisions to #20; no archive heights were applied to the game in this work.
The measured structure hazard and importer regression case are tracked in
[#106](https://github.com/jnd-cz/prague-transport-sim/issues/106).

## Reproduce

```powershell
python -I tools/snapshot.py fetch
python -I tools/snapshot.py data-fetch
python -P -E tools/test_dtmp_tracks.py
python -P -E tools/dtmp_tracks.py
```

The report is `reports/dtmp-tracks.json`. Upstream acquisition is explicit:
`python -P -E tools/dtmp_tracks.py --fetch --acquire-only`. The ID inventory and every explicit-ID
batch are checked for completeness, duplicate IDs, transfer-limit truncation, Z, CRS and hashes.
Eight focused tests cover interpolation, crossings and neighbouring tracks, overlapping levels,
missing Z, length weighting, denominator separation, known disagreements and structures.
