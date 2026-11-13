// SPDX-License-Identifier: AGPL-3.0-or-later
// The vehicle registry (#455): every tram model the game offers is a folder in assets/ with a vehicle.json
// (its names, files, licence and credit, tier, its fleet's types, numbers and sets), listed in
// assets/vehicles.json. The index's order is the menu's and the fallback's: a vehicle that is not loaded
// gives way to the first loaded one before it or after it in that order (src/models.js pickVehicle). The
// manifest's fields: docs/vehicles.md, "The manifest"; tools/test_vehicles.py checks them.
import { EVENTS, LOOPS } from './audio.js';

export const INDEX = 'assets/vehicles.json';
export const LOADERS = ['builtin', 'gltf', 'gltf-classic', 'gltf-rigged'];
export const vehicles = [];   // the manifests in the index's order
export const byId = new Map();
export const liveries = new Map();   // id -> a livery's manifest (#529), only those that fit their vehicle
export const soundPacks = new Map(); // id -> a sound pack's manifest (#528), only those that fit their vehicle

const dir = (id) => `assets/${id}/`;
export const fileUrl = (v, path) => dir(v.id) + path;

// get(url) -> a fetch-like body ({ ok, json() }): the loading screen's Loader.get, or fetch. A manifest that cannot
// be read or lacks what the game needs is left out with a warning; the rest load.
export async function loadRegistry(get = (u) => fetch(u)) {
  if (vehicles.length) return vehicles;
  const index = await (await get(INDEX)).json();
  const list = await Promise.all(index.vehicles.map(async (id) => {
    try {
      const v = await (await get(`${dir(id)}vehicle.json`)).json();
      const bad = problems(v, id);
      if (bad.length) { console.warn(`vehicle ${id} left out:`, bad.join('; ')); return null; }
      return v;
    } catch (e) { console.warn(`vehicle ${id} left out:`, e); return null; }
  }));
  for (const v of list) if (v) { vehicles.push(v); byId.set(v.id, v); }
  // the liveries (#529): assets/<id>/livery.json, each for the vehicle its `requires` names
  const looks = await Promise.all((index.liveries || []).map(async (id) => {
    try {
      const l = await (await get(`${dir(id)}livery.json`)).json();
      const bad = liveryProblems(l, byId.get(liveryVehicle(l)), id);
      if (bad.length) { console.warn(`livery ${id} left out:`, bad.join('; ')); return null; }
      return l;
    } catch (e) { console.warn(`livery ${id} left out:`, e); return null; }
  }));
  for (const l of looks) if (l) liveries.set(l.id, l);
  // the sound packs (#528): assets/<id>/sounds.json, each for the vehicle its `requires` names
  const packs = await Promise.all((index.sounds || []).map(async (id) => {
    try {
      const p = await (await get(`${dir(id)}sounds.json`)).json();
      const bad = [...(p.id !== id ? [`its id ${p.id} is not its folder's ${id}`] : []), ...(p.kind !== 'sounds' ? [`kind ${p.kind} is not sounds`] : []),
        ...soundProblems(p, byId.get(liveryVehicle(p)))];
      if (bad.length) { console.warn(`sound pack ${id} left out:`, bad.join('; ')); return null; }
      return p;
    } catch (e) { console.warn(`sound pack ${id} left out:`, e); return null; }
  }));
  for (const p of packs) if (p) soundPacks.set(p.id, p);
  for (const v of vehicles) if (v.sounds) {
    const bad = soundProblems({ ...v.sounds, files: v.files }, v);
    if (bad.length) { console.warn(`vehicle ${v.id}'s sounds left out:`, bad.join('; ')); delete v.sounds; }
  }
  return vehicles;
}

// A sound pack (#528; docs/decisions/2026-11-10-vehicle-packages.md, section 5): `events`, an event's file or a list
// (one picked at random each time), and `loops`, a loop's `file` with its reference (`refSpeed` m/s for motor and
// rolling, `refRpm` for mg) and `gain`; files in WAV or MP3. A vehicle's manifest may hold one as `sounds` (its
// files among the vehicle's), or a package (kind `sounds`) adds one; the events and loops it leaves out keep the
// built-in sounds (src/audio.js).
export function soundProblems(p, v) {
  const out = [];
  if (!v) return [`its vehicle ${liveryVehicle(p)} is not loaded`];
  const files = new Set((p.files || []).map((f) => f.path)), sound = /\.(wav|mp3)$/i;
  const file = (what, f) => { if (!files.has(f)) out.push(`${what}: ${f} is not among its files`); else if (!sound.test(f)) out.push(`${what}: ${f} is not WAV or MP3`); };
  for (const [e, f] of Object.entries(p.events || {})) {
    if (!(e in EVENTS)) out.push(`event ${e}: the game raises no such event`);
    for (const x of [f].flat()) file(`event ${e}`, x);
  }
  for (const [name, l] of Object.entries(p.loops || {})) {
    if (!(name in LOOPS)) { out.push(`loop ${name}: the game has no such loop`); continue; }
    file(`loop ${name}`, l.file);
    const ref = name === 'mg' ? 'refRpm' : name === 'flange' ? null : 'refSpeed';
    if (ref && !(l[ref] > 0)) out.push(`loop ${name}: ${ref} is not a positive number`);
  }
  return out;
}
// the sound pack a set of vehicle v sounds with: the first package for it, else its manifest's own, else none (the
// built-in sounds); { id, events, loops, url(path) }
export function soundsFor(v) {
  const p = [...soundPacks.values()].find((x) => liveryVehicle(x) === v?.id);
  if (p) return { ...p, url: (f) => dir(p.id) + f };
  return v?.sounds ? { ...v.sounds, id: `${v.id}:own`, url: (f) => dir(v.id) + f } : null;
}

// A livery (#529; docs/decisions/2026-11-10-vehicle-packages.md, section 3): `textures` and `colours` by the slots
// its vehicle declares (the manifest's `slots`, a slot's glTF materials; `colours`, the colours a model painted by
// colour takes), `numbers` the fleet numbers' `font` and `colour`, `types` the fleet types it fits, `share` the part
// of AI sets of those types that wear it. Every slot it leaves out keeps the vehicle's own.
export const liveryVehicle = (l) => Object.keys(l?.requires || {})[0];
export const liveryUrl = (l, path) => dir(l.id) + path;
const HEX = /^#[0-9a-f]{6}$/i;
export function liveryProblems(l, v, id = l?.id) {
  const out = [];
  if (l?.id !== id) out.push(`its id ${l?.id} is not its folder's ${id}`);
  if (l?.kind !== 'livery') out.push(`kind ${l?.kind} is not livery`);
  if (!l?.names?.en || !l?.names?.cs) out.push('no names in both languages');
  if (!v) { out.push(`its vehicle ${liveryVehicle(l)} is not loaded`); return out; }
  const slots = v.slots || {}, paints = v.colours || [], files = new Set((l.files || []).map((f) => f.path));
  for (const [s, path] of Object.entries(l.textures || {})) {
    if (!slots[s]) out.push(`texture slot ${s}: ${v.id} has no such slot`);
    if (!files.has(path)) out.push(`texture ${path} is not among its files`);
  }
  for (const [s, c] of Object.entries(l.colours || {})) {
    if (!slots[s] && !paints.includes(s)) out.push(`colour slot ${s}: ${v.id} has no such slot`);
    if (!HEX.test(c)) out.push(`colour ${s} ${c} is not #rrggbb`);
  }
  if (l.numbers?.colour && !HEX.test(l.numbers.colour)) out.push(`numbers.colour ${l.numbers.colour} is not #rrggbb`);
  const types = fleetOf(v)?.types.map((t) => t.type) || [];
  for (const t of l.types || []) if (!types.includes(t)) out.push(`type ${t}: ${v.id}'s fleet has no such type`);
  if (l.share != null && !(l.share >= 0 && l.share <= 1)) out.push(`share ${l.share} is not between 0 and 1`);
  return out;
}
// the liveries a set of vehicle v and fleet type `type` may wear
export const liveriesFor = (v, type = null) => [...liveries.values()].filter((l) => liveryVehicle(l) === v?.id && (!type || !l.types || l.types.includes(type)));
// the livery a set wears: the one the fleet gives one of its numbers (an advertising wrap, the fleet's `liveries`),
// else one of those that fit its type, each on its `share` of the sets (r: a draw in [0, 1)), else the vehicle's own
export function liveryOf(v, type, numbers, r) {
  const wrap = v?.fleet?.liveries;
  for (const n of numbers || []) { const id = wrap?.[n]; if (id && liveryVehicle(liveries.get(id)) === v.id) return id; }
  let acc = 0;
  for (const l of liveriesFor(v, type)) { acc += l.share || 0; if (r < acc) return l.id; }
  return null;
}

// what the game cannot do without (the full check, files and licence included, is tools/test_vehicles.py)
function problems(v, id) {
  const out = [];
  if (v.id !== id) out.push(`its id ${v.id} is not its folder's ${id}`);
  if (!LOADERS.includes(v.loader)) out.push(`unknown loader ${v.loader}`);
  if (!v.names?.en || !v.names?.cs) out.push('no names in both languages');
  if (v.loader !== 'builtin' && !v.files?.some((f) => f.path === v.model)) out.push('its model is not among its files');
  if (v.files?.length && !v.licence?.credit) out.push('files without a credit line');
  return out;
}

export const vehicleName = (v, lang) => v.names[lang] || v.names.en;


// The fleet (#527; docs/decisions/2026-11-10-vehicle-packages.md, section 4): the manifest's
// `fleet: { types: { <type>: { ranges: [[first, last], …], except: […] } | { list: […] } }, sets: [[lead, second], …] }`.
// A set listed runs together and with no other car; one of its cars may run alone as a single car (the user,
// 2026-11-13: "if the player gets single car of the pair then the other number is free to be used by ai tram"),
// and the set is then not dealt whole while it is out. A set not listed is numbers of one type dealt together.
const FLEETS = new WeakMap();
export function fleetOf(v) {
  if (!v?.fleet?.types) return null;
  let f = FLEETS.get(v);
  if (f) return f;
  f = { types: [], typeOf: new Map(), setOf: new Map() };
  for (const [type, t] of Object.entries(v.fleet.types)) {
    const out = new Set(t.except || []), numbers = [];
    if (t.list) numbers.push(...t.list);
    else for (const [a, b] of t.ranges || []) for (let n = a; n <= b; n++) if (!out.has(n)) numbers.push(n);
    f.types.push({ type, numbers });
    for (const n of numbers) f.typeOf.set(n, type);
  }
  for (const set of v.fleet.sets || []) for (const n of set) f.setOf.set(n, set);
  FLEETS.set(v, f);
  return f;
}

// The player's preferred set (the user, 2026-11-11: "I would add optinal preferred set for the player"): '6892+6921'
// or one lead car's number, '7269'; null when the vehicle has no such numbers.
export function preferredSet(v, text) {
  const f = fleetOf(v), numbers = String(text ?? '').split('+').map((x) => +x.trim()).filter((n) => n > 0);
  if (!f || !numbers.length) return null;
  const type = f.typeOf.get(numbers[0]);
  if (!type || numbers.some((n) => f.typeOf.get(n) !== type)) return null;
  return { type, numbers: f.setOf.get(numbers[0]) && numbers.length === 1 ? [...f.setOf.get(numbers[0])] : numbers };
}
// what the menu offers: the listed sets, then every number by type
export function fleetChoices(v) {
  const f = fleetOf(v);
  if (!f) return null;
  return { sets: (v.fleet.sets || []).map((s) => ({ value: s.join('+'), type: f.typeOf.get(s[0]) })),
    types: f.types.map(({ type, numbers }) => ({ type, numbers: numbers.filter((n) => !f.setOf.has(n)) })) };
}

// Dealing (the record's section 4): the run's own stream shuffles every number of the vehicle into one deck, so each
// type comes up as often as it has numbers (the user, 2026-11-10: "roughly related to their range sizes"); a set is
// dealt from where the deck stands, skipping numbers on the street, and given back when it leaves; when every number
// is out it deals again from the start. The player's numbers are held for the whole run. rand: a stream of its own
// (src/random.js), so dealing draws nothing from the traffic's.
export class FleetDealer {
  constructor(v, rand) {
    this.v = v; this.rand = rand;
    this.f = fleetOf(v);
    this.out = new Map();   // number -> how many sets carry it
    this.at = 0;
    this.deck = this.f ? this.f.types.flatMap((t) => t.numbers) : [];
    for (let i = this.deck.length - 1; i > 0; i--) { const j = Math.floor(rand() * (i + 1)); [this.deck[i], this.deck[j]] = [this.deck[j], this.deck[i]]; }
  }
  // our own tram: the preferred set (a lone lead car dealt a partner of its type), else dealt from `type` where the
  // vehicle has it (the T3SUCS the simulation drives), else from any
  ours(cars, prefer = null, type = 'T3SUCS') {
    if (!this.f) return { type: null, numbers: Array(cars).fill(null) };
    if (prefer) {
      const numbers = prefer.numbers.slice(0, cars);
      for (const n of numbers) this._take(n);
      while (numbers.length < cars) numbers.push(this._next(prefer.type, numbers, true) ?? numbers[0]);
      return { type: prefer.type, numbers, livery: liveryOf(this.v, prefer.type, numbers, this.rand()) };
    }
    return this.deal(cars, this.f.types.some((t) => t.type === type) ? type : null);
  }
  deal(cars, type = null) {
    if (!this.f) return { type: null, numbers: Array(cars).fill(null) };
    const L = this.deck.length;
    for (const free of [true, false]) {
      for (let i = 0; i < L; i++) {
        const n = this.deck[(this.at + i) % L], t = this.f.typeOf.get(n), set = this.f.setOf.get(n);
        if (type && t !== type) continue;
        if (free && this.out.get(n)) continue;
        let numbers;
        if (set && cars === 1) numbers = [n];   // (a set's car runs alone on a single-car line: its partner stays free)
        else if (set) {
          if (set.length !== cars || (free && set.some((m) => this.out.get(m)))) continue;
          numbers = [...set];
        } else {
          numbers = [n];
          while (numbers.length < cars) { const m = this._next(t, numbers, free, (this.at + i + 1) % L); if (m == null) break; numbers.push(m); }
          if (numbers.length < cars) continue;
        }
        this.at = (this.at + i + 1) % L;
        for (const m of numbers) this._take(m);
        return { type: t, numbers, livery: liveryOf(this.v, t, numbers, this.rand()) };
      }
    }
    return { type: null, numbers: Array(cars).fill(null) };   // (no set of that length or type at all)
  }
  give(numbers) { for (const n of numbers || []) if (this.out.get(n)) this.out.set(n, this.out.get(n) - 1); }
  // the next number of type t in the deck after `from` that runs in no listed set and is not in `has`
  _next(t, has, free, from = this.at) {
    const L = this.deck.length;
    for (let i = 0; i < L; i++) {
      const n = this.deck[(from + i) % L];
      if (this.f.typeOf.get(n) === t && !this.f.setOf.has(n) && !has.includes(n) && !(free && this.out.get(n))) return n;
    }
    return null;
  }
  _take(n) { this.out.set(n, (this.out.get(n) || 0) + 1); }
}

// Without a dealer (a test page, a picture): the type and numbers from the run number's hash, so a run keeps its cars.
const hashOf = (s) => { let h = 2166136261; for (const ch of String(s)) h = Math.imul(h ^ ch.charCodeAt(0), 16777619) >>> 0; return h; };
export function variantOf(v, run) {
  const f = fleetOf(v), all = f?.types.reduce((s, t) => s + t.numbers.length, 0);
  if (!all) return null;
  let h = hashOf(run) % all;
  for (const t of f.types) { if (h < t.numbers.length) return t.type; h -= t.numbers.length; }
}
export function fleetNumbers(v, type, run, cars) {
  const t = fleetOf(v)?.types.find((x) => x.type === type);
  if (!t?.numbers.length) return Array(cars).fill(null);
  const h = hashOf(`${run}#`);
  return Array.from({ length: cars }, (_, k) => t.numbers[(h + k * 37) % t.numbers.length]);
}
