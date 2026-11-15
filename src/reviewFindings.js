// SPDX-License-Identifier: AGPL-3.0-or-later
// A review set's findings and their identity, shared by review mode (src/review.js) and the review
// directory (reviews.html, src/reviewIndex.js, #288), so both count the same findings and answers.
// No three.js here: the directory loads only this and src/verdicts.js.

// (a finding's place and kind: the same after a rebuild that leaves it where it was; the answers are
// stored under it, src/verdicts.js)
export const fid = (f) => f.kind === 'trackheight' ? `${f.src}|trackheight|${f.id}` : `${f.src}|${f.kind}|${f.x.toFixed(1)},${f.y.toFixed(1)}`;

// a finding's answer: the page's, or the one data/truth.json records for it (`recorded`, what the import
// reads: a track-height decision renamed by a rebuilt queue keeps its answer, #379), the newer of the two
export const answerOf = (f, page) => f.recorded?.v && (!page?.v || (f.recorded.t || 0) > (page.t || 0)) ? f.recorded : page;

// every object with numeric x and y in a findings file; its kind from the keys above it
export function fileFindings(json, label) {
  const out = [], skip = new Set(['places', 'checks', 'result', 'review', 'findings', 'bad']);
  const opts = Array.isArray(json?.options) ? json.options.map(String) : undefined;
  const walk = (o, kind) => {
    if (Array.isArray(o)) { for (const v of o) walk(v, kind); return; }
    if (!o || typeof o !== 'object') return;
    if (typeof o.x === 'number' && typeof o.y === 'number') {
      if (o.kind === 'trackheight' && Array.isArray(o.spans)) {
        out.push({ ...o, src: 'file', mag: typeof o.mag === 'number' ? o.mag : 1 });
        return;
      }
      const k = [kind, o.kind].filter(Boolean).join(': ') || label;
      // (marks: other points to show with it, {x, y, label, color}; pick: the answer may be a point placed
      // on the map, #258)
      const marks = Array.isArray(o.marks) ? o.marks.filter((m) => typeof m?.x === 'number' && typeof m?.y === 'number') : undefined;
      out.push({ src: 'file', kind: k, x: o.x, y: o.y, mag: typeof o.mag === 'number' ? o.mag : 1, info: o.info || o.msg || '',
        options: Array.isArray(o.options) ? o.options.map(String) : opts, ...(typeof o.place_option === 'string' ? { placeOption: o.place_option } : {}),
        ...(marks?.length ? { marks } : {}), ...(o.pick ? { pick: true } : {}), ...(o.id ? { id: String(o.id) } : {}),
        ...(o.recorded?.v ? { recorded: o.recorded } : {}) });
      return;
    }
    for (const [k, v] of Object.entries(o)) walk(v, skip.has(k) ? kind : k);
  };
  walk(json, '');
  return out;
}

// A track-height findings file references the shared queue instead of repeating all profiles.
export async function loadFindings(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const json = await response.json();
  if (json.span_file) {
    const r = await fetch(json.span_file);
    if (!r.ok) throw new Error(`span queue: HTTP ${r.status}`);
    const bytes = await r.arrayBuffer();
    if (globalThis.crypto?.subtle) {
      const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map((n) => n.toString(16).padStart(2, '0')).join('');
      if (hash !== json.span_sha256) throw new Error('span queue differs from the findings file');
    }
    const queue = JSON.parse(new TextDecoder().decode(bytes));
    if (queue.snapshot !== json.snapshot) throw new Error('span queue snapshot differs from the findings file');
    const spans = new Map(queue.spans.map((s) => [s.id, s]));
    for (const f of json.findings) {
      f.spans = f.decision.span_ids.map((id) => {
        if (!spans.has(id)) throw new Error(`span queue missing ${id}`);
        return spans.get(id);
      });
      f.span_sha256 = json.span_sha256;
    }
  }
  return fileFindings(json, url.split('/').pop());
}
