# Headless tests in Python + Playwright; licence direction

**Date:** 2026-10-29
**Status:** agreed; implementation in M1 issues.

## Tests

The benches and lints run in the page (`tools/lint.js`, `tools/bench/`). They are driven headless from
the command line by **Python + Playwright** (Chromium), collecting JSON and comparing with thresholds.
No Node toolchain for now; Node or Deno only once the simulation core is split from Three.js (M5), where
type checking would come with it.

## Licences

- **Code:** **GPL-3.0** (the user's choice, 2026-10-29; `LICENSE`): fully open source, and versions others
  distribute stay open. MIT code (e.g. ported from OSM2World) can be included with its notice kept.
- **Own assets** (models, textures, the user's photos and recordings): their own licence, separate from
  the code (e.g. CC BY-NC-SA 4.0).
- **Third-party assets:** only with a licence that allows redistribution, each listed in an asset
  register (file, author, source, licence).
- **OSM2World:** code is MIT, ports keep its notice; its bundled models and textures are checked one by
  one.
- **Data:** OSM-derived built data is ODbL when distributed; IPR Praha, ČÚZK, DTM, PID need attribution
  (CC BY 4.0).
