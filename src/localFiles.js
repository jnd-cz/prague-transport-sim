// SPDX-License-Identifier: AGPL-3.0-or-later
// Files the game holds in the browser (#530): an installed package's files (src/packages.js) answer at the address
// they would have on the host, `packages/<id>/<path>`, through a blob URL. Every loader reads through localUrl, so a
// package's vehicle, livery and sounds load as the repository's do.
export const localFiles = new Map();   // packages/<id>/<path> -> blob: URL
export const localUrl = (u) => localFiles.get(u) ?? u;
