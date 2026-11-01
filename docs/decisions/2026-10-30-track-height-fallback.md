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
### Guarded height-import stage (#106)

`tools/import_track_heights.py` stages the height decisions for #20 under `reports/track-heights.json`.
Track topology and game integration remain #20. The output separates unchanged DI XY geometry and
raw source Z from the selected height, height source, confidence, evidence IDs and review flags.
Geometry records retain DI attributes and source package hashes/state dates; archive IDs retain their
attributes, acquisition dates and batch hashes. Archived-only geometry is never added by this stage.

The user's revised selection order (2026-10-30) is:

1. Use numeric DI Z as supplied. Archived Z and the optional review file cannot override it; a
   disagreement remains flagged. This selects DI's deck-level height on the Trojský most regression.
2. Where DI lacks usable Z, use its unambiguous archived track match, within the existing plan and
   heading limits. Ordinary track no longer needs a hand-reviewed point observation.
3. Where neither has usable Z, a containing survey of **confirmed paved track** may supply its surface
   height plus the applicable `data/truth.json` `trackHeights.railAboveDeck` fact. Paved means flush
   embedded rails, panels or setts, including a dedicated strip behind a kerb. Multiple physical levels
   remain unresolved. There is no extrapolation outside the surveyed polygon.

An archive-only height is held for review when there are several candidate levels, a known archive
record discrepancy over 1 m, a contradictory containing paved survey, or an obsolete/uncertain alignment.
An OSM structure hint requires independent survey support at the track's ZPS level; without it the
sample is `structure_unverified`. The OSM buffer supplies no level itself. Flags and all
candidates remain visible even when DI or a later reviewed observation selects a height. The research
availability screen remains an estimate; staged selections report their actual source and confidence.

`tools/track_decks.py` discovers every `data/line*.dtm.json` and checks all surveyed surface classes,
triangulating their vertex heights only inside their footprint. A covering tram area establishes the
track's ZPS level; otherwise a covering deck can establish it. Conflicting anchor levels are unresolved.
Covering tram areas take precedence over deck anchors, so a deck above a ground track cannot lend it
the upper level. Conflicting tram levels stay on hold even when OSM has no structure tag.
Without anchors, a containing nonzero-level surface also leaves the level unresolved; it cannot be
assumed to be ground simply because OSM has no structure tag.
DI placement codes are not used as ZPS levels: Trojský most's DI code is 0. At a structure, a ground-level
anchor cannot establish an elevated track level. Without a structure hint, absent anchors use level 0
with `ordinary_surface_default` provenance. Railway bridges (class `rail`), water, walls, roofs and buildings
are diagnostics only. A surface more than 3 m from independent numeric DI is `surface_on_other_level` and
cannot establish a track level. This test never uses the archive to validate itself. Surfaces at
another level remain in the report with `survey_level_mismatch` and cannot validate or supply rail Z.
Nearby polygons within 1.5 m remain diagnostic; only a containing surface can supply or veto a height.
The eligible paved classes are defined in `tools/track_heights.py`. Records retain the compiled file hash,
area index and available source-state
date. The four style offsets approved for staging are facts in `data/truth.json`, rather than constants
in the importer or the game. The user's reply, “Use the proposed offsets for all four styles”, is recorded
at `trackHeights.offsetApproval`; approval adopts design values, not a new survey measurement.
User `trackStyles` marks are applied to their line sections; unmarked track uses the
documented panel **drawing** default and carries a `track_style_defaulted_panels` flag. That default
does not prove paved construction for a height check.

`tools/track_context.py` classifies construction from explicit truth styles, then matching pinned OSM
`surface` / `embedded_rails`, then a covering paved survey class at the established track level. A generic ZPS tram area
does not establish its material. Open grass/ballast outlines may follow ditches or embankment toes:
they neither supply a rail height nor veto an archive height. Unknown construction also keeps the
survey diagnostic. Archive disagreement over 1 m with numeric DI still holds the whole archive record.

### Calibration and review response, 2026-11-01

Calibration uses numeric DI, never archive Z, at the DI tangent. Coincident compiled-line copies are
deduplicated per sample/class/level/height. The small report is
[`reports/review/track-height-calibration.json`](../../reports/review/track-height-calibration.json);
it separates raw DI-minus-survey from the approved drawing-offset residual.

| Construction / surveyed class | Samples | DI minus raw survey, p10 / median / p90 (m) |
|---|---:|---|
| Confirmed pavement, unmarked road level 0 | 11,111 | −0.057 / +0.044 / +0.202 |
| Explicit embedded style, road level 0 | 1,040 | −0.107 / +0.099 / +0.152 |
| Unverified construction, railway bridge level 1 | 104 | −7.428 / −6.060 / −4.953 |
| Unverified construction, green level 0 | 224 | +0.075 / +0.224 / +0.447 |

Of the green samples, **219** form one site, Koh-i-noor – Slavia – Nádraží Eden; none overlaps the
explicit Hradčany grass marks. The other **5** are ground beneath Trojský most, more than 8 m below
the rails. The 219-site length-weighted median is +0.222 m, p10 +0.075 m, p90 +0.428 m. Its survey class establishes
green ground, not whether its Z is vegetation or track bed. The user's section assessment is recorded
at `data/truth.json` `trackHeights.surveyCalibrationSites`; exact grass boundaries and individual
sample construction remain unverified. No +0.22 m
survey-to-rail fact is adopted. The approved grass drawing offset remains a separate design fact.

The 3 m level-separation test removes the overhead-deck cluster without treating ordinary open-bed
differences of a few decimetres as another storey. Ordinary road calibration has no >3 m residual.
This is a level exclusion, not a claim that every remaining surface measures rail height.

`tools/track_structure_review.py` groups held samples into contiguous direction spans and structure
decisions. The [review queue](../../reports/review/track-height-spans.json) contains OSM IDs/names,
both nearest stops, lengths per direction, dated archive records, numeric DI near the ends, same-level
survey candidates, IPR bare-earth comparisons and one proposed rule per span. Untagged elevated survey
areas retain their survey IDs instead of acquiring an invented OSM identity. A proposal does not approve
a height. Building underpasses, including the Křížovnické náměstí case identified in the review, need a
reviewed street-level rule; a covering building surface cannot establish rail height.

Open `?line=17&inspect&heightreview=reports/review/track-height-spans.json`. F8 shows held spans in orange,
conflicts in red, building passages resolved by numeric DI in blue, and approved spans in green.
Clicking a span flies the camera to it and displays its
sources and proposal; `window.game.heightReview` exposes the complete queue. The overlay follows the
current world profile and never applies a proposed height.

**Last no-data fallback for #20:** ordinary track may use IPR's 1 m bare-earth terrain plus its approved
style drawing offset, flagged `terrain_fallback_unvalidated` with raster provenance and its assumed Bpv
datum. The queue's `ordinary_terrain_fallbacks` gives those proposals. No ambiguous level, known archive
conflict, bridge, underpass or tunnel receives this fallback. Structures require reviewed evidence;
earth under a bridge is never substituted for its rail level. Profile assembly and applying these
proposals to the game remain #20.

**Tunnel decision (user, 2026-10-30):** hold archive heights for review until independent evidence is
available. Pinned OSM tunnel, covered and negative-layer tram ways retain a `tunnel_unverified` flag.
Numeric DI still wins; local reviewed tunnel evidence can resolve a fallback. Surface survey above a
tunnel cannot validate its archive height. No portal-profile heuristic is applied in this stage.

Published survey sidecars currently belong to lines 17 and 22; intersecting routes use that coverage too.
The pinned raw snapshot now includes the expanded districts from #125. New compiled sidecars are discovered
without changing the guard. Missing coverage leaves structures held for review.

The selection rule is `tools/track_heights.py`. An optional `--evidence` JSON file holds these lists:

- `evidence`: a unique `id`, the `di_id`, city-frame `xy`, `radius_m` (positive, at most 1 m),
  `reviewed: true`, `vertical_datum: "Bpv"`, `height_meaning: "top_of_rail"`, finite `z`, a reviewed
  integer `level`, context `kind` (`surface`, `deck` or `tunnel`), and `source` with `dataset`, `record`
  and `date`. This local observation can resolve a flagged fallback. It must already describe rail
  height; a raw deck-surface point is not a reviewed rail observation. Numeric DI still keeps priority.
- `alignment_reviews`: `dataset` (`di` or `archive`), feature `id`, `status` (`current`, `uncertain`
  or `obsolete`) and a `source` reference. Obsolete DI geometry is rejected, uncertain DI geometry is
  held for review, and obsolete/uncertain archived candidates cannot supply a selected height. The
  source geometry remains visible in the staging output with its review, rather than silently added.
- `span_reviews`: a unique `id`, `reviewed: true`, `vertical_datum: "Bpv"`,
  `height_meaning: "top_of_rail"`, integer physical `level`, `kind` and dated `source` (`dataset`, `record`,
  `date`). Each `profiles` entry scopes the decision to `di_ids`, a simple city-frame `xy` path, and
  `radius_m` at most 1 m. Its `rule` is `{"type":"archive"}`, `{"type":"constant","z":…}`, or
  `{"type":"linear","ends":[startZ,endZ]}`. Copy each direction span's `approval_profile` from the
  queue; a single structure decision may include several such profiles. Archive approval retains the
  archive source; a new reviewed profile records its review source. Conflicting approvals stay held.
  Numeric DI still wins. A tunnel portal profile requires this explicit approval and dated basis.

Evidence is bound to the current track ID and point, never reused for a neighbouring track or the
rest of a long archived feature. For a reviewed fallback, all applicable observations must agree on
physical level and within 0.3 m in rail height; supported candidates must fit within 0.3 m as well.
The nearest archive segment missing Z is not replaced by a farther numeric segment.

Archive records are flagged throughout their candidate coverage when any compared sample differs
by more than 1 m, including records shorter than the research's 10 m test. The research's p90 screen
remains part of its availability analysis, not an additional ordinary-track gate. Flags and both
candidates remain visible even when local evidence resolves a sample. Source transitions and profile assembly
are left to #20; staged midpoint samples are not a continuous rail profile.

## Reproduce

```powershell
python -I tools/snapshot.py fetch
python -I tools/snapshot.py data-fetch
python -P -E tools/test_dtmp_tracks.py
python -P -E tools/dtmp_tracks.py
python -P -E tools/test_track_heights.py
python -P -E tools/import_track_heights.py
python -P -E tools/calibrate_track_heights.py --input reports/track-heights.json
python -P -E tools/track_structure_review.py --input reports/track-heights.json
```

The report is `reports/dtmp-tracks.json`. Upstream acquisition is explicit:
`python -P -E tools/dtmp_tracks.py --fetch --acquire-only`. The ID inventory and every explicit-ID
batch are checked for completeness, duplicate IDs, transfer-limit truncation, Z, CRS and hashes.
Eight focused tests cover interpolation, crossings and neighbouring tracks, overlapping levels,
missing Z, length weighting, denominator separation, known disagreements and structures.

Verification on 2026-10-30: an isolated checkout with no archived files fetched all **23 new files**
directly from the SFTP store with `--no-cache`. `snapshot.py status` then reported **0 missing/changed,
0 extra inputs and 0 built-data differences**. Running the full offline assessment there produced
an **exact JSON match**, including all 16 district rows, all five route rows, height distributions
and outlier/deck evidence. The 1549 previously pinned source paths are unchanged in the new snapshot.
