# OSM2World: its ideas in our tools, not the tool in our build (#15)

Status: proposed (draft for the user, PR for #15).

## Why

#15 asked what of OSM2World our pipeline should take ([the study](../research/osm2world/README.md), read at
OSM2World `1d31c25`). Our world comes from measured sources per layer, with OSM as the fallback; OSM2World
builds from OSM alone and guesses widths, positions and heights from tags.

## The decision

- **OSM2World is not run as a build step.** It would add a JVM; its output carries tag guesses where we have
  survey data; it converts each tile on its own, so neighbours can disagree at junctions; its height
  constraints are declared but, at this commit, only a merge-to-mean is enforced.
- **Its methods are reimplemented in our tools** where the study found them useful (the candidates in the
  study's README, picked by the user). A tool that ends up a close translation of its code carries
  OSM2World's MIT notice in its header.
- **No new library.** The constrained triangulation #276 needs is shapely's `constrained_delaunay_triangles`
  (shapely 2.1+, GEOS 3.10+), already a build dependency: line 17's ground-level survey (9,437 areas,
  348,482 vertices) in 4.95 s, every boundary edge kept.
- **Textures from their origin.** CC0 sets the style repo uses are fetched from ambientCG itself and entered in
  `ASSETS.md`; nothing is copied from the style repo's repacked files.

## What it changes

Nothing in the pipeline today. #276 takes shapely for its triangulation; the issues made from the candidates
name their checks.
