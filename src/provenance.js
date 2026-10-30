// What the built files say they were made from (tools/sources.py, #10): each file's `provenance` names,
// per list, the layer, its sources in fallback order and how many features came from each. The credits
// line is made from the sources actually used, and the fallbacks are logged for review
// (window.game.provenance in the console).

// files: { 'line17.json': parsed, ... }. Once per holder, as tools/sources.py's attribution():
// "Terrain, Trees: datový podklad © IPR Praha (CC BY 4.0)." A file built before provenance existed
// brings its own line.
export function credits(files) {
  const by = new Map(), own = [];
  for (const f of Object.values(files)) {
    if (!f?.provenance) { if (f?.attribution && !own.includes(f.attribution)) own.push(f.attribution); continue; }
    for (const s of Object.values(f.provenance.sources || {})) {
      const i = (s.attribution || '').indexOf(': ');
      if (i < 0) continue;
      const what = s.attribution.slice(0, i), holder = s.attribution.slice(i + 2);
      if (!by.has(holder)) by.set(holder, []);
      if (!by.get(holder).includes(what)) by.get(holder).push(what);
    }
  }
  return [...[...by].map(([h, w]) => `${w.join(', ')}: ${h}.`), ...own].join(' ');
}

// One row per list: which level its features came from (0 = the layer's preferred source)
export function fallbacks(files) {
  const rows = [];
  for (const [file, f] of Object.entries(files)) {
    for (const [list, e] of Object.entries(f?.provenance?.lists || {})) {
      const n = e.count.reduce((a, b) => a + b, 0);
      if (!n) continue;
      rows.push({ file, list, layer: e.layer, unit: e.unit,
        levels: e.levels.map((s, i) => `${s} ${e.count[i]}`).join(' / '),
        fallback: e.count.slice(1).some((c) => c > 0) });
    }
  }
  return rows;
}

export function logProvenance(files) {
  const rows = fallbacks(files);
  if (!rows.length) return;
  const fb = rows.filter((r) => r.fallback);
  console.log(`sources: ${rows.length} lists, ${fb.length} from a fallback level: ` +
    fb.map((r) => `${r.layer} (${r.file} ${r.list}: ${r.levels})`).join('; '));
}
