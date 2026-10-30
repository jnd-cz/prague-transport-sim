# What each height means

**Date:** 2026-10-29
**Status:** proposed (issue #9). The four per-style offsets were approved for the guarded height
staging tool on 2026-10-30; their values and provenance are in `data/truth.json` `trackHeights.railAboveDeck`.

## Measured (line 17, city frame, every 5 m of route off bridges)

- **The track profile follows the surveyed surface at the track centre.** The profile minus the raw ZPS
  surface is +0.003 m (median) on street sections and +0.005 m on tram-track areas. The 10–90 % range is
  ±0.11–0.16 m, which is the profile's smoothing. Where there's no survey, the profile is +0.05 m over the
  terrain.
- **Everything at the track is then drawn above that:**
  - the street next to the track pressed to profile **+0.14 m** (`flushDtm`);
  - the track bed at **+0.20 m**;
  - the rail heads at **+0.26 m** (`RAIL_TOP`);
  - the tram's wheels at the rail heads, so the tram rides +0.26 m too.

  On a street with embedded rails, the whole track zone stands 14–26 cm proud of the real road (the
  user's "track ribbon lifted above the survey").
- **Street beside the track, track centre and terrain agree.** The surveyed street 5 m beside the axis is
  level with the axis (median 0.00 m, 10–90 % within ±0.03 m). The archived technical map's tram-axis
  heights are 0.036 m (median) over IPR's 1 m terrain at Výtoň, and 0.046 m at the Hostivař loop
  (2026-10-27 track-source study).
- **Vertical datum.** DMR 5G, the ZPS, the archived DTMP and Mosty 3D are all Bpv. IPR's 1 m raster
  states no datum. Surveyed points minus the raster are +0.014 m (median) at Výtoň, while a Bpv / EVRS
  mix-up would show about a decimetre. So the raster is very likely Bpv too, and IPR is asked to confirm
  (#62).

## Proposal

1. **One datum: Bpv metres (EPSG:8357)** for every height in the build and the game. A source in another
   datum is converted in the build, or not used.
2. **Each height has one meaning:**

   | Height | Meaning | Source, in order |
   |---|---|---|
   | terrain | bare earth | IPR 1 m raster → DMR 5G (#10) |
   | street | top of the pavement, kerb, sidewalk | ZPS surfaces → archived DTMP → terrain + OSM |
   | deck | top surface of a bridge deck (road or track bed on it) | ZPS deck areas → Mosty 3D top → OSM span |
   | **track** | **top of rail (TOR)** at the track axis, mean of both rails; cant tilts the rails about it | DTM track axis Z (#20) → surveyed surface at the axis + the style's offset (below) → terrain + offset |

3. **The profile is the top of rail.** The tram's wheels sit on it with no lift (`RAIL_TOP` = 0). The rails
   are modelled downward from it: the head at TOR, then the rail body, and the bed below by style. The
   catenary height is measured from TOR, as in reality (the contact wire height is defined over top of rail).
4. **Track styles set how TOR relates to the surface around the track:**

   | Style | Where (data) | TOR over the surrounding surface | Drawn |
   |---|---|---|---|
   | **embedded** in a street (asphalt, setts) | survey class road / paved / parking at the axis; OSM road `embedded_rails=tram` | truth fact `rail-above-deck-embedded`: flush | street surface up to the rails, flush; a strip between the rails in the street's material; no separate bed |
   | **panels** (large concrete panels), also in a street apart from the car lanes | survey tram-track area (default for it), or road class as at Karlovo náměstí – I. P. Pavlova | truth fact `rail-above-deck-panels`: flush (measured there: the lanes 4.5 m off are level with the axis, +0.008 m) | panel surface flush with the rail heads |
   | **grass** track | marked per section (`truth.json` `trackStyles`, later the orthophoto) | truth fact `rail-above-deck-grass`: high grass variant | grass below the rail heads |
   | **ballast** (open track) | marked per section | truth fact `rail-above-deck-ballast`: rail and plate above sleeper tops | ballast below the rails, sleepers visible |

   Embedded and panel track need nothing new: the survey already gives TOR. Grass and ballast need the
   style per section; until a section is marked, it is drawn as panels. Track bed styles as content
   are #52; this record only fixes where TOR is.

   **Where the offsets come from.** No open dataset measures them yet. The street survey records the
   grass or ballast surface, not the rails. The current DTM track axes mostly carry no height (Praha 8:
   278 of 339 all-zero Z). The archived map server does expose track axes with Z in layer 10;
   the [2026-10-30 assessment](2026-10-30-track-height-fallback.md) measures their fallback coverage
   and the cases needing review. Until source heights and track styles are matched, these remain design
   values: grass from ČVUT's green-track study (two variants:
   [Zelená trať](https://projects.fd.cvut.cz/k612x1rk/soubory/Zelena_trat.pdf)); ballast from standard
   track build-up (no Prague source found). They are recorded as truth facts, so a measurement replaces
   them: the DTM track axes where they have heights (#61), or the user's photos of the example stretches.
   The staging importer reads the adopted values from the truth facts; grass and ballast remain design
   values rather than new survey measurements.

   **Example stretches** (the user, line 22, in `data/truth.json` `trackStyles` by stops, so they survive
   frame changes): ballast Malý Břevnov – Obora Hvězda; grass Pohořelec – Brusnice – Pražský hrad;
   embedded Újezd – Národní divadlo – Národní třída; panels Karlovo náměstí – Štěpánská – I. P. Pavlova.
   Marking whole lines or the network needs the orthophoto and an editor (#28), and styles change as
   streets are rebuilt, so every mark carries its source and date.
5. **Streets meet the track flush at TOR.** The +0.14 m street lift and the +0.20 / +0.26 m track lifts go.
   What z-fighting needs stays tiny (≤ 0.01 m, as `DTM_LIFT` does for streets).
6. **Fallbacks keep the meaning.** Without a survey, TOR = terrain + the style's offset (embedded by default
   in a street, OSM road over it). On a structure, TOR = deck + style offset. Never "terrain + some lift
   that looks right".

## What changes in the game (implementation issue)

- `RAIL_TOP` 0.26 → 0, bed and rail ribbons drawn down from the profile, `flushDtm`'s +0.14 → 0;
  `trackHeights` for the other lines' tracks without the 0.14 embedding offset.
- The tram, AI trams, platform heights (from the survey, relative to TOR),
  the catenary (`CONTACT_WIRE` over TOR) and the lints that use `+0.26` (`railSupport`, `tramEnvelope`,
  `deckClip` ray start) follow.
- Check: lints (railSupport, deckClip, terrainOverSurvey), the walkers and cars at crossings, screenshots of
  an embedded street (Karlovo náměstí), a separate body (Modřany), a bridge (Štefánikův most).

## Open

- Which grass variant the Hradčany stretch is (high, 4 cm, or low, ≈ 16 cm): a photo settles it.
- The ballast offset, from a track-axis height or a photo with a known reference.
