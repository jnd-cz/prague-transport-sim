// SPDX-License-Identifier: AGPL-3.0-or-later
// Vehicle packages a player installs (#530; docs/decisions/2026-11-10-vehicle-packages.md, sections 1, 6 and 7;
// docs/vehicles.md, Packages). A package is a folder with `package.json` at its root: a vehicle, a livery, a sound pack
// or a fleet for a vehicle. A .zip, a folder or a URL may hold several (a bundle, a complete vehicle pack:
// maintainer, 2026-11-11); each is checked, installed, switched off and removed on its own. Installed ones live in the
// browser's origin private file system (OPFS) under packages/<id>/, with packages/index.json, and answer at
// `packages/<id>/<path>` (src/localFiles.js), so the game's loaders read them as they read assets/. Nothing leaves the
// browser. What a package may hold: src/packageRules.json, shared with tools/test_vehicles.py.
import { localFiles } from './localFiles.js';
import { byId, liveries, soundPacks, installed, registerPackage, unregisterPackage, liveryProblems, soundProblems, liveryVehicle, fleetOf } from './vehicles.js';
import { loadVehicle, forgetVehicle, vehicleFit } from './models.js';
import { VEHICLE_TYPES } from './tram.js';

let rules = null;
export const packageRules = async () => rules ??= await (await fetch(new URL('./packageRules.json', import.meta.url))).json();

// ---- versions: "1.2.0" against a range of comparators, ">=1 <2" (docs/vehicles.md, Packages)
const parts = (s) => String(s).split('.').map((x) => +x || 0);
const cmp = (a, b) => { const x = parts(a), y = parts(b); for (let i = 0; i < 3; i++) if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) - (y[i] || 0); return 0; };
export function satisfies(version, range) {
  return String(range ?? '*').trim().split(/\s+/).every((c) => {
    if (c === '*' || c === '') return true;
    const m = /^(>=|<=|>|<|=)(\d+(?:\.\d+){0,2})$/.exec(c);
    if (!m) return false;
    const d = cmp(version, m[2]);
    return { '>=': d >= 0, '<=': d <= 0, '>': d > 0, '<': d < 0, '=': d === 0 }[m[1]];
  });
}

// ---- sizes, before anything is unpacked or more is read (#713): the caps of src/packageRules.json
const ext = (path) => path.split('.').pop().toLowerCase();
// (one file's cap by its type; a file of no type the game reads is not kept, and may be as big as the biggest kept one)
const fileCap = (path, r) => r.caps[r.types[ext(path)]] ?? Math.max(...Object.values(r.types).map((c) => r.caps[c]));
const mb = (n) => `${(n / 1048576).toFixed(1)} MB`;
// what a picked folder or an archive may be: so many files, so many bytes (thrown: the menu shows it as the report)
export function withinCaps(count, bytes, r, what = 'the archive') {
  if (count > r.caps.entries) throw new Error(`${what} holds ${count} files, over the cap of ${r.caps.entries}`);
  if (bytes > r.caps.archive) throw new Error(`${what} is ${mb(bytes)}, over the cap of ${mb(r.caps.archive)}`);
}
// a deflated file, to the size its archive declares and no further (a directory that understates it is a refusal,
// not memory filled: 1 MB of zeros deflates to 1 kB)
async function inflate(raw, most, name) {
  const reader = new Blob([raw]).stream().pipeThrough(new DecompressionStream('deflate-raw')).getReader(), out = new Uint8Array(most);
  let n = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    if (n + value.length > most) { reader.cancel().catch(() => {}); throw new Error(`${name}: unpacks to more than the ${most} bytes its archive declares`); }
    out.set(value, n);
    n += value.length;
  }
  if (n !== most) throw new Error(`${name}: unpacks to ${n} bytes, its archive declares ${most}`);
  return out;
}
// a response's bytes, `cap` at most (its declared length first, then what arrives)
async function readCapped(res, cap, what) {
  if (+res.headers.get('content-length') > cap) throw new Error(`${what}: ${mb(+res.headers.get('content-length'))}, over the cap of ${mb(cap)}`);
  const reader = res.body.getReader(), parts = [];
  let n = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    n += value.length;
    if (n > cap) { reader.cancel().catch(() => {}); throw new Error(`${what}: over the cap of ${mb(cap)}`); }
    parts.push(value);
  }
  const out = new Uint8Array(n);
  let o = 0;
  for (const part of parts) { out.set(part, o); o += part.length; }
  return out;
}

// ---- a .zip's files (stored or deflated: what every archiver writes; no Zip64, which the package cap never needs).
// Its directory is read and held to the caps first: the archive's bytes, its files' number, each one's declared size
// and their sum. Then each file is unpacked to its declared size at most.
export async function readZip(buf) {
  const r = await packageRules();
  const u8 = new Uint8Array(buf), dv = new DataView(u8.buffer, u8.byteOffset, u8.byteLength);
  withinCaps(0, u8.length, r);
  let e = -1;
  for (let i = u8.length - 22; i >= Math.max(0, u8.length - 65557); i--) if (dv.getUint32(i, true) === 0x06054b50) { e = i; break; }
  if (e < 0) throw new Error('not a zip archive');
  const n = dv.getUint16(e + 10, true), dec = new TextDecoder(), dir = [], out = new Map();
  let p = dv.getUint32(e + 16, true), total = 0;
  for (let k = 0; k < n; k++) {
    if (p + 46 > u8.length || dv.getUint32(p, true) !== 0x02014b50) throw new Error('a broken zip directory');
    const flags = dv.getUint16(p + 8, true), method = dv.getUint16(p + 10, true), size = dv.getUint32(p + 20, true), full = dv.getUint32(p + 24, true);
    const nl = dv.getUint16(p + 28, true), xl = dv.getUint16(p + 30, true), cl = dv.getUint16(p + 32, true), off = dv.getUint32(p + 42, true);
    const name = dec.decode(u8.subarray(p + 46, p + 46 + nl)).replace(/\\/g, '/');
    p += 46 + nl + xl + cl;
    if (name.endsWith('/')) continue;
    if (flags & 1) throw new Error(`${name}: encrypted`);
    if (method !== 0 && method !== 8) throw new Error(`${name}: compression ${method} (only stored or deflated files are read)`);
    if (full > fileCap(name, r)) throw new Error(`${name.slice(0, 80)}: ${full} bytes unpacked, over the cap of ${fileCap(name, r)} for one file of its type`);
    total += full;
    dir.push({ name, method, size, full, off });
  }
  withinCaps(dir.length, total, r, 'what the archive unpacks to');
  for (const { name, method, size, full, off } of dir) {
    if (off + 30 > u8.length) throw new Error('a broken zip directory');
    const start = off + 30 + dv.getUint16(off + 26, true) + dv.getUint16(off + 28, true), raw = u8.subarray(start, start + size);
    if (method === 8) out.set(name, await inflate(raw, full, name));
    else if (raw.length !== full) throw new Error(`${name}: ${raw.length} bytes stored, its archive declares ${full}`);
    else out.set(name, raw.slice());
  }
  return out;
}

// ---- the packages in a set of files (path -> bytes): every package.json and the files under its folder
// (a listed path: the rules' `path`, plain names in folders; it is shown on the loading screen and names a stored file)
const safe = (path, r) => typeof path === 'string' && new RegExp(r.path).test(path);
export function unpack(entries) {
  const roots = [...entries.keys()].filter((k) => k === 'package.json' || k.endsWith('/package.json')).map((k) => k.slice(0, -'package.json'.length));
  return roots.sort((a, b) => b.length - a.length).map((root, _, all) => {
    const files = new Map();
    for (const [k, v] of entries) {
      if (!k.startsWith(root) || all.some((r) => r !== root && r.length > root.length && r.startsWith(root) && k.startsWith(r))) continue;
      files.set(k.slice(root.length), v);
    }
    let manifest = null, error = null;
    try { manifest = JSON.parse(new TextDecoder().decode(files.get('package.json'))); } catch (e) { error = `package.json is not JSON: ${e.message}`; }
    return { root, manifest, files, error };
  });
}

const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
export const sha256 = async (bytes) => hex(await crypto.subtle.digest('SHA-256', bytes));

// ---- the check (the record's section 7): { problems, warnings }; a package with problems is refused, one with
// warnings is offered with them
export function manifestProblems(p, r) {
  const bad = [], warn = [];
  const need = (ok, why) => { if (!ok) bad.push(why); };
  need(p && typeof p === 'object', 'package.json is not an object');
  if (!p || typeof p !== 'object') return { problems: bad, warnings: warn };
  need(p.schema === r.schema, `schema ${p.schema} is not ${r.schema}`);
  need(r.kinds.includes(p.kind), `kind ${p.kind} is none of ${r.kinds.join(', ')}`);
  need(new RegExp(r.id).test(p.id ?? ''), `id ${p.id} is not author.package in lower case`);
  need(!r.reserved.includes(p.id), `id ${p.id} is a name the browser's store keeps for itself`);
  need(/^\d+\.\d+\.\d+$/.test(p.version ?? ''), `version ${p.version} is not major.minor.patch`);
  need(p.game && satisfies(r.interface, p.game), `game ${p.game}: wants another vehicle interface than this game's ${r.interface}`);
  need(['cs', 'en'].every((l) => typeof p.names?.[l] === 'string' && p.names[l].trim()), 'names in cs and en');
  if (!p.description?.cs || !p.description?.en) warn.push('no description in cs and en');
  const lic = p.licence || {};
  need(r.licences.includes(lic.spdx), `licence ${lic.spdx} is none of the redistributable ones (${r.licences.join(', ')})`);
  need(Array.isArray(lic.authors) && lic.authors.length, 'licence without authors');
  need(typeof lic.credit === 'string' && lic.credit.trim(), 'licence without a credit line');
  if (lic.commercial === false || /-NC-/.test(lic.spdx ?? '')) warn.push('non-commercial licence');
  const req = Object.entries(p.requires || {});
  if (p.kind === 'vehicle') need(!req.length, 'a vehicle requires nothing');
  else need(req.length === 1, `requires ${JSON.stringify(p.requires)}: wants the one vehicle it is for`);
  need(Array.isArray(p.files) && p.files.length, 'no files listed');
  for (const f of p.files || []) {
    if (!safe(f.path, r)) { bad.push(`file ${String(f.path).slice(0, 80)}: not a path inside the package (plain names in folders: letters, digits, . _ - and spaces)`); continue; }
    need(r.types[ext(f.path)], `file ${f.path}: .${ext(f.path)} is not a file type the game reads`);
    need(Number.isInteger(f.bytes) && f.bytes >= 0, `file ${f.path}: no bytes`);
    need(/^[0-9a-f]{64}$/.test(f.sha256 ?? ''), `file ${f.path}: no sha256`);
  }
  if (p.thumbnail) need(p.files?.some((f) => f.path === p.thumbnail) && r.types[ext(p.thumbnail)] === 'image', `thumbnail ${p.thumbnail} is not one of its images`);
  return { problems: bad, warnings: warn };
}

// A model's own links: every `uri` in a glTF (a .gltf, or a .glb's JSON chunk) is data inside the file or one of the
// package's listed files beside or below the model. A loader fetches what a model names, so a link to anywhere else
// would be a request from the player's browser: a package is its listed files and nothing more.
function modelLinks(path, bytes, listed) {
  const b = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes), dec = new TextDecoder();
  let doc;
  try {
    if (ext(path) === 'glb') {
      const dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
      if (b.byteLength < 20 || dv.getUint32(0, true) !== 0x46546c67 || dv.getUint32(16, true) !== 0x4e4f534a) throw new Error('no glTF header');
      const n = dv.getUint32(12, true);
      if (20 + n > b.byteLength) throw new Error('cut short');
      doc = JSON.parse(dec.decode(b.subarray(20, 20 + n)));
    } else doc = JSON.parse(dec.decode(b));
  } catch (e) { return [`file ${path}: not a glTF model the check can read (${e.message})`]; }
  const dir = path.slice(0, path.lastIndexOf('/') + 1), bad = [];
  const walk = (o) => {
    if (!o || typeof o !== 'object') return;
    for (const [k, v] of Object.entries(o)) {
      if (k === 'uri' && typeof v === 'string') {
        let rel = null;
        try { rel = decodeURIComponent(v); } catch { /* (not a path) */ }
        if (!/^data:/i.test(v) && !(rel !== null && listed.has(dir + rel))) bad.push(`file ${path}: links to ${v.slice(0, 80)}, which is neither data in the file nor one of the package's files`);
      } else walk(v);
    }
  };
  walk(doc);
  return bad;
}

// its files against the list: present, of their size and hash, within the caps; files not listed are not kept
export async function fileProblems(p, files, r) {
  const bad = [], warn = [];
  let total = 0;
  for (const f of p.files || []) {
    const b = files.get(f.path);
    if (!b) { bad.push(`file ${f.path} missing`); continue; }
    total += b.byteLength;
    if (b.byteLength !== f.bytes) bad.push(`file ${f.path}: ${b.byteLength} bytes, listed ${f.bytes}`);
    else if (await sha256(b) !== f.sha256) bad.push(`file ${f.path}: its sha256 is not the one listed`);
    const cls = r.types[ext(f.path)];
    if (cls && b.byteLength > r.caps[cls]) bad.push(`file ${f.path}: ${b.byteLength} bytes, over the ${cls} cap of ${r.caps[cls]}`);
  }
  if (total > r.caps.package) bad.push(`${total} bytes, over the package cap of ${r.caps.package}`);
  const listed = new Set((p.files || []).map((f) => f.path).concat('package.json'));
  for (const f of p.files || []) if (r.types[ext(f.path)] === 'model' && ext(f.path) !== 'bin' && files.get(f.path)) bad.push(...modelLinks(f.path, files.get(f.path), listed));
  const extra = [...files.keys()].filter((k) => !listed.has(k));
  if (extra.length) warn.push(`files not listed, left out: ${extra.join(', ')}`);
  return { problems: bad, warnings: warn };
}

// what its files hold, at an install (#713; not at every start: decoding is the loaders' work then): an image's sides
// (a livery's textures power-of-two ones, as the repository's: tools/test_vehicles.py), a sound's length
const pow2 = (x) => x > 0 && (x & (x - 1)) === 0;
async function contentProblems(p, files, r) {
  const bad = [];
  for (const f of p.files || []) {
    const b = files.get(f.path), cls = r.types[ext(f.path)];
    if (!b) continue;
    if (cls === 'image') {
      let im = null;
      try { im = await createImageBitmap(new Blob([b])); } catch { bad.push(`file ${f.path}: not an image this browser reads`); continue; }
      const w = im.width, h = im.height;
      im.close();
      if (Math.max(w, h) > r.image.maxSide) bad.push(`image ${f.path} is ${w} x ${h} px, over ${r.image.maxSide} px a side`);
      else if (p.kind === 'livery' && f.path !== p.thumbnail && !(pow2(w) && pow2(h))) bad.push(`image ${f.path} is ${w} x ${h} px: a livery's textures have power-of-two sides`);
    } else if (cls === 'sound') {
      let secs = null;
      try { secs = (await new OfflineAudioContext(1, 1, 44100).decodeAudioData(b.slice().buffer)).duration; }
      catch { if (ext(f.path) !== 'ogg') bad.push(`file ${f.path}: not a sound this browser can decode`); }   // (an Ogg: its MP3 fallback plays, #636)
      if (secs > r.sound.maxSeconds) bad.push(`sound ${f.path} plays ${secs.toFixed(1)} s, over the ${r.sound.maxSeconds} s a sound may`);
    }
  }
  if (p.kind === 'sounds') {
    const gains = [['gain', p.gain], ...Object.entries(p.loops || {}).map(([name, l]) => [`loop ${name}: gain`, l?.gain])];
    for (const [what, g] of gains) if (g != null && !(Number.isFinite(g) && g >= 0 && g <= r.sound.maxGain)) bad.push(`${what} ${g} is not between 0 and ${r.sound.maxGain}`);
  }
  return bad;
}

// a fleet package's numbers (the record's section 4; tools/test_vehicles.py fleet_problems for the repository's)
function fleetProblems(p, v) {
  const bad = [], types = p.types;
  if (!types || typeof types !== 'object' || !Object.keys(types).length) return ['fleet without types'];
  const own = fleetOf(v)?.types.map((t) => t.type), typeOf = new Map();
  for (const [name, t] of Object.entries(types)) {
    if (own && !own.includes(name)) bad.push(`type ${name}: ${v.id}'s fleet has no such type`);
    const ns = Array.isArray(t.list) ? t.list : (t.ranges || []).flatMap((x) => (Array.isArray(x) && x[0] <= x[1] ? Array.from({ length: x[1] - x[0] + 1 }, (_, i) => x[0] + i) : (bad.push(`type ${name}: range ${JSON.stringify(x)} is not [first, last]`), [])));
    if (!ns.length) bad.push(`type ${name}: no numbers`);
    for (const n of ns) { if (!Number.isInteger(n) || n <= 0) { bad.push(`type ${name}: ${n} is not a fleet number`); break; } if (typeOf.has(n)) bad.push(`number ${n} in types ${typeOf.get(n)} and ${name}`); typeOf.set(n, name); }
  }
  for (const s of p.sets || []) if (!Array.isArray(s) || s.length < 2 || s.some((n) => !typeOf.has(n))) bad.push(`set ${JSON.stringify(s)}: not two or more of its numbers`);
  return bad;
}

// what its kind needs: a vehicle's fields, its model loaded by the game's own loader and measured against its type
// and the budget; a livery's, a sound pack's or a fleet's slots, events and types among those its vehicle declares
async function kindProblems(p, r, stored) {
  const bad = [];
  if (p.kind !== 'vehicle') {
    const vid = liveryVehicle(p), v = byId.get(vid);
    if (!v) return { problems: [`its vehicle ${vid} is not installed`] };
    if (!satisfies(v.version ?? '1.0.0', p.requires[vid])) bad.push(`wants ${vid} ${p.requires[vid]}, installed ${v.version ?? '1.0.0'}`);
    if (p.kind === 'livery') bad.push(...liveryProblems(p, v, p.id));
    if (p.kind === 'sounds') bad.push(...soundProblems(p, v));
    if (p.kind === 'fleet') bad.push(...fleetProblems(p, v));
    return { problems: bad };
  }
  const T = VEHICLE_TYPES[p.type], files = new Set((p.files || []).map((f) => f.path));
  if (!T) bad.push(`type ${p.type} is none of the game's (${Object.keys(VEHICLE_TYPES).join(', ')})`);
  if (!r.loaders.includes(p.loader)) bad.push(`loader ${p.loader} is none of ${r.loaders.join(', ')}`);
  if (!files.has(p.model)) bad.push(`its model ${p.model} is not among its files`);
  if (p.loader === 'gltf-rigged' && !files.has(p.rig)) bad.push(`its rig ${p.rig} is not among its files`);
  for (const m of p.moves || []) if (!r.moves.includes(m)) bad.push(`moves: ${m} is not a movement the game knows`);
  if (p.fleet) bad.push(...fleetProblems(p.fleet, p).map((x) => `fleet: ${x}`));
  if (bad.length) return { problems: bad };
  // the model, loaded as the game loads it (the rig's names for its claimed moves: src/rigged.js rigProblems)
  let fit = stored;
  if (!fit) {
    const had = byId.get(p.id);
    byId.set(p.id, p);
    try { await loadVehicle(p); fit = vehicleFit(p); }
    catch (e) { return { problems: [String(e.message || e).replace(`vehicle ${p.id}: `, '')] }; }
    finally { if (had) byId.set(p.id, had); else byId.delete(p.id); }
  }
  const L = T.length + r.fit.lengthOver, W = T.width + r.fit.widthOver, f2 = (x) => x.toFixed(2), warn = [];
  if (fit.size[2] > r.fit.maxLength) bad.push(`one car is ${f2(fit.size[2])} m long, over the ${r.fit.maxLength} m a vehicle may be: is its forward axis right?`);
  else if (fit.size[2] > L) warn.push(`one car is ${f2(fit.size[2])} m long, over its type ${p.type}'s ${f2(L)} m: it runs on ${p.type}'s bogie pivots`);
  if (fit.size[0] > W) bad.push(`one car is ${f2(fit.size[0])} m wide, over its type's ${f2(W)} m: is its forward axis right?`);
  if (fit.low < -r.fit.railLow || fit.low > r.fit.railHigh) bad.push(`its lowest point is ${f2(fit.low)} m from the rail plane: its wheels stand on y = 0`);
  if (fit.triangles > r.budget.triangles) bad.push(`${fit.triangles} triangles a car, over the budget of ${r.budget.triangles}`);
  if (fit.drawCalls > r.budget.drawCalls) bad.push(`${fit.drawCalls} draw calls a car, over the budget of ${r.budget.drawCalls}`);
  return { problems: bad, warnings: warn, fit };
}

// the whole check of one package (its files in memory): its manifest, files, at an install what they hold (`fresh`;
// not when an installed one is read back at a start), then its kind
export async function checkPackage(pkg, stored = null, fresh = true) {
  const r = await packageRules();
  if (pkg.error) return { problems: [pkg.error], warnings: [] };
  const m = manifestProblems(pkg.manifest, r);
  if (m.problems.length) return m;
  const f = await fileProblems(pkg.manifest, pkg.files, r);
  if (fresh && !f.problems.length) f.problems.push(...await contentProblems(pkg.manifest, pkg.files, r));
  if (f.problems.length) return { problems: f.problems, warnings: [...m.warnings, ...f.warnings] };
  const p = pkg.manifest;
  if (!installed.has(p.id) && (byId.has(p.id) || liveries.has(p.id) || soundPacks.has(p.id))) return { problems: [`id ${p.id} is taken by the game's own`], warnings: [] };
  serve(p, pkg.files);
  installed.add(p.id);
  const k = await kindProblems(p, r, stored);
  if (k.problems.length) { forget(p); return { problems: k.problems, warnings: [...m.warnings, ...f.warnings] }; }
  return { problems: [], warnings: [...m.warnings, ...f.warnings, ...(k.warnings || [])], fit: k.fit };
}

// a package's files at their addresses (blob URLs), and taken away again
function serve(p, files) {
  for (const f of p.files) {
    const u = `packages/${p.id}/${f.path}`;
    if (localFiles.has(u)) URL.revokeObjectURL(localFiles.get(u));
    localFiles.set(u, URL.createObjectURL(new Blob([files.get(f.path)])));
  }
}
function forget(p) {
  for (const [u, b] of localFiles) if (u.startsWith(`packages/${p.id}/`)) { URL.revokeObjectURL(b); localFiles.delete(u); }
  installed.delete(p.id);
  if (p.kind === 'vehicle') forgetVehicle(p.id);
}

// ---- the store: OPFS packages/<id>/<path>, and packages/index.json { packages: { <id>: { enabled, source, at, fit } } }
const KIND_ORDER = { vehicle: 0, fleet: 1, livery: 2, sounds: 3 };
export const canInstall = () => !!navigator.storage?.getDirectory;
const home = async () => (await navigator.storage.getDirectory()).getDirectoryHandle('packages', { create: true });
async function readIndex() {
  try { return JSON.parse(await (await (await (await home()).getFileHandle('index.json')).getFile()).text()); }
  catch { return { schema: 1, packages: {} }; }
}
async function writeFile(dir, path, bytes) {
  const segs = path.split('/');
  for (const s of segs.slice(0, -1)) dir = await dir.getDirectoryHandle(s, { create: true });
  const w = await (await dir.getFileHandle(segs.at(-1), { create: true })).createWritable();
  await w.write(bytes);
  await w.close();
}
async function readFile(dir, path) {
  const segs = path.split('/');
  for (const s of segs.slice(0, -1)) dir = await dir.getDirectoryHandle(s);
  return new Uint8Array(await (await (await dir.getFileHandle(segs.at(-1))).getFile()).arrayBuffer());
}
let index = null;
const saveIndex = async () => writeFile(await home(), 'index.json', JSON.stringify(index));

// every installed package as the menu lists it: { id, kind, manifest, enabled, source, ok, problems, warnings }
export const state = new Map();

// the installed packages read, checked and the switched-on ones put in the registry (at startup, after the repository's)
export async function loadInstalled() {
  if (!canInstall()) return state;
  index = await readIndex();
  const dir = await home(), ids = Object.keys(index.packages);
  const read = await Promise.all(ids.map(async (id) => {
    try {
      const files = new Map([['package.json', await readFile(await dir.getDirectoryHandle(id), 'package.json')]]);
      const manifest = JSON.parse(new TextDecoder().decode(files.get('package.json')));
      for (const f of manifest.files || []) { try { files.set(f.path, await readFile(await dir.getDirectoryHandle(id), f.path)); } catch { /* listed missing by the check */ } }
      return { id, manifest, files };
    } catch (e) { return { id, error: `its files cannot be read: ${e.message}` }; }
  }));
  read.sort((a, b) => (KIND_ORDER[a.manifest?.kind] ?? 9) - (KIND_ORDER[b.manifest?.kind] ?? 9));
  for (const pkg of read) {
    const at = index.packages[pkg.id];
    if (!at.enabled) { state.set(pkg.id, { id: pkg.id, manifest: pkg.manifest, ...at, ok: true, problems: [], warnings: [] }); continue; }
    const c = await checkPackage(pkg, at.fit, false);
    state.set(pkg.id, { id: pkg.id, manifest: pkg.manifest, ...at, ok: !c.problems.length, ...c });
    if (!c.problems.length) registerPackage(pkg.manifest);
  }
  return state;
}

// install the packages in a set of files (path -> bytes); source: where they came from ('file', 'folder' or a URL).
// Returns one report per package: { id, names, ok, problems, warnings, replaced }
export async function install(entries, source) {
  if (!canInstall()) return [{ id: null, ok: false, problems: ['this browser keeps no files for a page (no OPFS)'], warnings: [] }];
  index ??= await readIndex();
  const found = unpack(entries);
  if (!found.length) return [{ id: null, ok: false, problems: ['no package.json in it'], warnings: [] }];
  found.sort((a, b) => (KIND_ORDER[a.manifest?.kind] ?? 9) - (KIND_ORDER[b.manifest?.kind] ?? 9));
  navigator.storage.persist?.().catch(() => {});
  const reports = [];
  for (const pkg of found) {
    const id = pkg.manifest?.id, old = id && state.get(id);
    if (old?.manifest?.version === pkg.manifest.version) { reports.push({ id, names: pkg.manifest.names, ok: false, problems: [`version ${old.manifest.version} is installed already`], warnings: [] }); continue; }
    if (old) { unregisterPackage(id); forget(old.manifest); }
    const c = await checkPackage(pkg);
    if (c.problems.length) {
      if (old) await restore(id);   // (the version installed stays)
      reports.push({ id, names: pkg.manifest?.names, ok: false, ...c });
      continue;
    }
    const dir = await home();
    if (old) await dir.removeEntry(id, { recursive: true });
    const d = await dir.getDirectoryHandle(id, { create: true });
    for (const f of pkg.manifest.files) await writeFile(d, f.path, pkg.files.get(f.path));
    await writeFile(d, 'package.json', pkg.files.get('package.json'));
    index.packages[id] = { enabled: true, source, at: new Date().toISOString(), fit: c.fit ?? null };
    await saveIndex();
    registerPackage(pkg.manifest);
    state.set(id, { id, manifest: pkg.manifest, ...index.packages[id], ok: true, ...c });
    reports.push({ id, names: pkg.manifest.names, ok: true, ...c, replaced: old?.manifest?.version ?? null });
  }
  return reports;
}
// the installed version back, from its files (a newer one was refused)
async function restore(id) {
  const dir = await (await home()).getDirectoryHandle(id), files = new Map([['package.json', await readFile(dir, 'package.json')]]);
  const manifest = JSON.parse(new TextDecoder().decode(files.get('package.json')));
  for (const f of manifest.files) files.set(f.path, await readFile(dir, f.path));
  const c = await checkPackage({ manifest, files }, index.packages[id].fit, false);
  if (!c.problems.length) registerPackage(manifest);
}

// the files at an address: a .zip, or a package.json and the files it lists beside it (path -> bytes). No more is
// read than the caps allow: an archive's, a manifest's, each listed file's by its type, a package's for them together
export async function fetchEntries(url) {
  const rules = await packageRules();
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  if (/\.zip($|\?)/i.test(url)) return readZip((await readCapped(res, rules.caps.archive, url)).buffer);
  const bytes = await readCapped(res, rules.caps.data, url), p = JSON.parse(new TextDecoder().decode(bytes)), entries = new Map([['package.json', bytes]]);
  const list = Array.isArray(p.files) ? p.files : [];
  withinCaps(list.length, 0, rules, 'its list');
  let total = 0;
  for (const f of list) {
    if (!safe(f.path, rules)) continue;
    const r = await fetch(new URL(f.path, new URL(url, location.href)));
    if (!r.ok) continue;
    const b = await readCapped(r, Math.min(fileCap(f.path, rules), rules.caps.package - total), f.path);
    total += b.length;
    entries.set(f.path, b);
  }
  return entries;
}
// installed from an address (only on the player's click; the hashes checked)
export const installUrl = async (url) => install(await fetchEntries(url), url);

// the packages in a set of files checked as an install checks them, and nothing kept: the game as it was after (a
// package of the same id installed here is taken out for the check and put back). For a submission (#580): one report
// per package, as install's, with the manifest
export async function dryCheck(entries) {
  const found = unpack(entries);
  if (!found.length) return [{ id: null, ok: false, problems: ['no package.json in it'], warnings: [] }];
  found.sort((a, b) => (KIND_ORDER[a.manifest?.kind] ?? 9) - (KIND_ORDER[b.manifest?.kind] ?? 9));
  const reports = [], passed = [], away = [];
  for (const pkg of found) {
    const id = pkg.manifest?.id, old = id && state.get(id);
    if (old?.enabled && old.ok) { unregisterPackage(id); forget(old.manifest); away.push(id); }
    const c = await checkPackage(pkg);
    if (!c.problems.length) { registerPackage(pkg.manifest); passed.push(pkg.manifest); }
    reports.push({ id, names: pkg.manifest?.names, manifest: pkg.manifest, ok: !c.problems.length, ...c });
  }
  // (in reverse: a fleet or livery before its vehicle)
  for (const m of passed.reverse()) { unregisterPackage(m.id); forget(m); }
  for (const id of away) await restore(id);
  return reports;
}
// a newer version at its address: the version there, or null
export async function newerAt(id) {
  const s = state.get(id);
  if (!/^https?:/.test(s?.source ?? '') || /\.zip($|\?)/i.test(s.source)) return null;
  const p = JSON.parse(new TextDecoder().decode(await readCapped(await fetch(s.source, { cache: 'no-store' }), (await packageRules()).caps.data, s.source)));
  return cmp(p.version, s.manifest.version) > 0 ? p.version : null;
}

// switched on or off: in or out of the registry now (a set on the street keeps its look until it leaves)
export async function setEnabled(id, on) {
  const s = state.get(id);
  if (!s) return;
  if (!on) { unregisterPackage(id); forget(s.manifest); s.enabled = false; s.problems = []; }
  else {
    const dir = await (await home()).getDirectoryHandle(id), files = new Map([['package.json', await readFile(dir, 'package.json')]]);
    for (const f of s.manifest.files) { try { files.set(f.path, await readFile(dir, f.path)); } catch { /* the check lists it */ } }
    const c = await checkPackage({ manifest: s.manifest, files }, index.packages[id].fit, false);
    Object.assign(s, { enabled: true, ok: !c.problems.length, ...c });
    if (!c.problems.length) registerPackage(s.manifest);
  }
  index.packages[id].enabled = on;
  await saveIndex();
  // (the packages for a vehicle switched off go with it, and come back with it)
  if (s.manifest.kind === 'vehicle') for (const [oid, o] of state) if (oid !== id && liveryVehicle(o.manifest) === id && o.enabled) {
    if (!on) { unregisterPackage(oid); forget(o.manifest); o.ok = false; o.problems = [`its vehicle ${id} is switched off`]; }
    else { await setEnabled(oid, true); }
  }
}
export async function remove(id) {
  const s = state.get(id);
  if (!s) return;
  unregisterPackage(id);
  forget(s.manifest);
  state.delete(id);
  // (the packages for a vehicle removed stay installed, out of the registry, until it is back)
  for (const o of state.values()) if (liveryVehicle(o.manifest) === id && o.ok) {
    unregisterPackage(o.id); forget(o.manifest); o.ok = false; o.problems = [`its vehicle ${id} is not installed`];
  }
  delete index.packages[id];
  await (await home()).removeEntry(id, { recursive: true }).catch(() => {});
  await saveIndex();
}

// the curated list (maintainer, 2026-11-11):
// assets/catalogue.json, packages their authors submitted and the project reviewed, installed by URL
export async function catalogue() {
  try { return (await (await fetch('assets/catalogue.json')).json()).packages || []; } catch { return []; }
}
