// The vehicle registry (#455): every tram model the game offers is a folder in assets/ with a vehicle.json
// (its names, files, licence and credit, tier, variants with their fleet numbers), listed in
// assets/vehicles.json. The index's order is the menu's and the fallback's: a vehicle that is not loaded
// gives way to the first loaded one before it or after it in that order (src/models.js pickVehicle). The
// manifest's fields: docs/vehicles.md, "The manifest"; tools/test_vehicles.py checks them.
export const INDEX = 'assets/vehicles.json';
export const LOADERS = ['builtin', 'gltf', 'gltf-classic', 'gltf-rigged'];
export const vehicles = [];   // the manifests in the index's order
export const byId = new Map();

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
  return vehicles;
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

// The type of a set and its cars' fleet numbers, from the vehicle's variants ({ type, fleet: [[first, last], …] }):
// the type picked by the run number, weighted by how many numbers it has (a type the run number names stays),
// the cars' numbers spread through its ranges from the run number, so a run keeps its cars.
const hashOf = (s) => { let h = 2166136261; for (const ch of String(s)) h = Math.imul(h ^ ch.charCodeAt(0), 16777619) >>> 0; return h; };
const span = (fleet) => fleet.reduce((n, [a, b]) => n + b - a + 1, 0);
export function variantOf(v, run) {
  const vs = v?.variants || [];
  if (!vs.length) return null;
  let h = hashOf(run) % vs.reduce((s, x) => s + span(x.fleet), 0);
  for (const x of vs) { const n = span(x.fleet); if (h < n) return x.type; h -= n; }
}
export function fleetNumbers(v, type, run, cars) {
  const x = v?.variants?.find((y) => y.type === type);
  if (!x) return Array(cars).fill(null);
  const n = span(x.fleet), h = hashOf(`${run}#`);
  return Array.from({ length: cars }, (_, k) => {
    let i = (h + k * 37) % n;
    for (const [a, b] of x.fleet) { if (i <= b - a) return a + i; i -= b - a + 1; }
  });
}
