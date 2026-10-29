# OSM from a local extract, not the Overpass API

**Date:** 2026-10-23 (Overpass removed entirely 2026-10-29)
**Status:** in force.

## Decision

All OSM data comes from the snapshot's local extract: Geofabrik's Czech Republic file cut to Prague
+ ~3 km (`raw/osm/praha.osm.pbf`, complete ways and relations) with pyosmium (`tools/osm_local.py`). No
tool calls the public Overpass API.

## Why

- The public Overpass servers were saturated for whole evenings (502 / 504), one mirror returned empty
  answers silently, another served data months old; line 9's fetch took hours. The user asked to spare
  them.
- A local file covers the whole city at once (the shared-world rebuild needs that), reads in ~14 s, and
  is pinned by hash in the snapshot, so every computer builds the same world.

## How

- `osm_local.emulate(name, query)` answers build_line.py's named queries in the Overpass shapes;
  `ways`, `relations`, `nodes` for new tools. Cached answers carry the extract's id (`base_id()`) and are
  recomputed when the extract changes.
- Refresh: download the newest `czech-republic-latest.osm.pbf`, `osm_local.py cut`, publish a snapshot.
