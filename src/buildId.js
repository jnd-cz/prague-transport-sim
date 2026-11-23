// SPDX-License-Identifier: AGPL-3.0-or-later
// One build of a line (#702): data/lineN.json's CRC-32 is the line's build ID, and tools/build_id.py writes it into the
// provenance (`build`) of every other file of the line the page loads. A file of another build, or with none (written
// by hand after a rebuild: a tool stamps its provenance afresh), stops the load and names the command that rebuilds
// the line: the network points into the line file's arrays by index (its signals, platforms and roads), and a set of
// two builds loaded and bound the signals to the wrong lanes. A set in which no file carries one was built before #702
// and loads, with a note in the console.

let table = null;

// the CRC-32 of the bytes (zlib's, as tools/build_id.py computes it), 8 hex digits
export function crc32(bytes) {
  if (!table) {
    table = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      table[n] = c;
    }
  }
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) c = table[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return ((c ^ 0xffffffff) >>> 0).toString(16).padStart(8, '0');
}

// built: {file name: its JSON} of the line's files the page loaded, the line file's among them; id: the line file's
// CRC-32. 'same' when every other file carries it, 'none' when none carries one (before #702); else it throws.
export function checkBuild(lineId, id, built) {
  const lineFile = `line${lineId}.json`;
  const ids = Object.entries(built).filter(([name]) => name !== lineFile).map(([name, j]) => [name, j?.provenance?.build ?? null]);
  if (ids.every(([, b]) => b === null)) {
    console.info(`line ${lineId}: its files carry no build ID (built before #702): python -P -E tools/rebuild.py ${lineId} stamps them`);
    return 'none';
  }
  const off = ids.filter(([, b]) => b !== id);
  if (!off.length) return 'same';
  const what = off.map(([name, b]) => `data/${name} ${b ? `is of build ${b}` : 'carries no build'}`).join(', ');
  throw new Error(`line ${lineId}: ${what}, not data/${lineFile}'s ${id}: python -P -E tools/rebuild.py ${lineId}`);
}
