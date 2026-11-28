# The feature layer: one record per placed object (#14)

Status: **proposed** (PR for #14, step 1). The questions at the end are the maintainer's.

## Why

Placed objects reached the game by five separate ways, none with all of a place, a heading, a source and an identity
(the state on main at 888ad36):

- The archive survey's points (`lineN.dtmpoints.json`) were `{k, x, y}`: the source's object number dropped, no
  heading. Of the 19 kinds on line 17 the page drew 5 (covers, caps, grates, hydrants); lamps, poles, signals and
  sign carriers, 5,117 points, were in the file and drawn by nothing.
- The page worked out at each start what the data could have said: one cover per shaft recorded twice, a grate's turn
  from the nearest street.
- The surveyed shelter footprints (`lineN.dtm.json` `shelters`, #523: 63 on the five lines) were read by nothing.
- Stop posts, tram signals and signs, catenary poles and wall rosettes stand by the game's rules, with no record.
- The prepared shelters, benches and street furniture (#252) have no placement to read (#889 waits for this layer).

## The record

`tools/features.py` writes `data/lineN.features.json`; `src/features.js` reads it.

| field | what |
|---|---|
| `id` | the source's own identity, the same on every line that sees the object: `dtmp:<object number>` for the archive survey's points; where a source has none, the kind, the source and the place to 2 m in S-JTSK (`shelter:zps:-743932,-1047366`) |
| `kind` | what it is: the vocabulary is the build's (`features.DTMP`'s kinds, `shelter`); the page draws a kind (`src/streets.js`) or has a placeholder for it (`src/features.js` `PLACEHOLDER`), which `test_features.py` holds |
| `x`, `y` | the city frame, m |
| `heading`, `headingFrom` | compass degrees, clockwise from north: the way the object's front faces, which is its model's +Z (the vehicles' and the furniture pack's convention). `headingFrom` says what decided it: `street` (the nearest carriageway segment), `footprint` (a shelter: across its long side, towards the nearer track). Absent where nothing says: a round cover needs none |
| `mount` | `ground` or `wall` (the survey's "on a building" codes). `pole` and `span` come with the signals and signs |
| `source` | a level of `tools/sources.py`'s `furniture` chain: `dtmpoints`, `zps`, `osm`, `rule:placement` |
| `z` | a height (m Bpv) only where the source has one (a shelter's footprint). The page stands the rest on its ground |
| `length`, `width`, `stop` | what a kind's source knows beside: a shelter's footprint and its stop's PID id |
| `variant` | the model where it is not the kind's own (a shelter type): none yet |

The file holds the records in groups, one per kind, source and mount, column by column (`id`, `xy`, and a column per
field any record of the group has): a line has 10,893-28,336 records, and the file is 70-72 % of the points file it
replaces (line 17: 605 kB for 841 kB). `features.records()` and `Features.of(kind)` give the records back.
`python -P -E tools/features.py --line N --geojson OUT` writes them for a review, in S-JTSK as `built.geojson` is.

One file a line for now, like every other built file. The ids are the sources', so the same file cut by tile, or one
for the city, holds the same records: of the 76,142 objects on the five lines, 11,775 are seen by more than one line
under the same id.

## What moved from the page to the build

- **One cover per shaft:** of a ground cover's kind, the first record per 0.3 m each way (304-658 dropped a line,
  the file's `merged`).
- **A grate's turn:** the bearing of the nearest carriageway segment, looked up by 20 m cells. 317-652 grates a line
  have no carriageway in reach and lie as the page laid them, unturned.

The page draws the same: the records of the five drawn kinds are the page's own lists on every line, the grates' turn
within 0.05° (the heading is kept to 0.1°), and pictures of main against the branch at five places are the same pixel
for pixel.

`lineN.dtmpoints.json` is gone: `tools/dtm_points.py` fetches the raw answers, and `tools/registration.py` and
`tools/bench/heads.js` read the layer.

## What the page does with a kind

A kind with a model is drawn (the five in `src/streets.js`, as before). A kind without one has a placeholder, a post
or a box of its usual size, which the dev overlay (F8) shows: 5,125 on line 17, the lamps yellow, poles grey, signals
red, sign carriers blue, stop signs green, the shelters as boxes of their footprints turned by their heading.

## Next, in this order

1. **The covers at their usual sizes** (#18, into #14): the valve cap is drawn 0.12 m and the hydrant cap 0.2 m
   across, smaller than first drawn (maintainer, 2026-10-24). A grate is drawn with its long side across the street:
   the model's long side should lie along its front.
2. **`data/truth.json` over the layer:** a record moved, turned, dropped or given a variant by its id, with its
   reader named, as #889 needs for Palackého náměstí and Spojovací.
3. **OSM for the kinds the survey lacks** (the study's pick, #15): benches, waste baskets, bicycle stands, bollards;
   `direction` where tagged, else the nearest street or footway with `headingFrom` saying so.
4. **What stands by a rule as records:** stop posts, tram signals and signs with `mount` `pole` and `span`
   (`GameView._mount`), catenary poles and rosettes: `rule:placement` in the chain, until #277's data replaces it.
5. Then #889 (the prepared shelters and furniture on these records) and #277 (the second archive layer, the wall
   brackets, section insulators).

## Questions

1. Placeholders in the dev overlay only, not in play? Proposed: yes. Grey posts for 3,326 lamps and 538 poles on
   line 17 would change how every street looks before any of them has a model, and the poles would stand beside the
   catenary's rule-placed ones.
2. The covers' usual sizes (step 1): the sizes first drawn are not in the repository's history. Proposed: the
   sizes of the castings Prague's networks use, looked up and checked against the maintainer's photos before they
   go in.
