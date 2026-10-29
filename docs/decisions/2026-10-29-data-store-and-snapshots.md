# Source snapshots and built data in a private store, code on GitHub

**Date:** 2026-10-29
**Status:** in force. Details and commands: [DATA.md](../../DATA.md).

## Decision

- Git (GitHub `jnd-cz/prague-transport-sim`) holds code, tools, docs and small hand-made data
  (`data/truth.json`).
- Raw sources are pinned **snapshots** (`snapshots/<id>.json`, `snapshots/CURRENT`: per file path, size,
  SHA-256, source, licence, date); built game data is listed in `data/MANIFEST.json`. The files
  themselves are stored by hash in an SFTP-only store on the user's server (`tools/snapshot.py`).
- Builds are reproducible from a snapshot; the built data per commit is published so playing and tuning
  need no build.

## Why

- Most sources keep no history (PID GTFS, Geoportál, ČÚZK services, district DTM packages): without a
  pinned copy two computers build different worlds.
- The sources are ~2 GB and the built data ~85 MB per state: too large for git history.
- The store's address and access stay private when the repository becomes public (issue: going public).
