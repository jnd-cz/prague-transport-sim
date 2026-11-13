// SPDX-License-Identifier: AGPL-3.0-or-later
import * as THREE from 'three';
import { Route, checkBuiltRoute } from './route.js';
import { Terrain, Profile, makeGround, carveCorridor, bridgeModel, DtmSurface, chainTunnels } from './terrain.js';
import { buildWorld, widenTramStreets, WORLD_PARTS, buildStreetDetail } from './world.js';
import { Tram, T3, CAR_PITCH } from './tram.js';
import { Game, fmtTime, fmtDev } from './game.js';
import { Hud } from './hud.js';
import { TramAudio } from './audio.js';
import { makeT3, placeConsist, poseT3, setConsistLine, loadVehicle, pickVehicle, disposeModel, CONTACT_WIRE, RAIL_TOP } from './models.js';
import { loadRegistry, fileUrl, vehicleName, FleetDealer, preferredSet, fleetChoices, liveries, liveriesFor } from './vehicles.js';
import { Traffic } from './traffic.js';
import { Autopilot } from './autopilot.js';
import { junctionTurns, indicating } from './indicators.js';
import { signalsAt } from './lamps.js';
import { Inspect } from './inspect.js';
import { Review, parseAt } from './review.js';
import { Reporter, canvasShot, place, noteError, failNote, addFacts, sendNote } from './report.js';
import { PerfLog, machine, gpuTimer } from './perf.js';
import { TouchControls } from './touch.js';
import { runStreetBot, showBotPanel } from './streetbot.js';
import { t, getLang, setLang, applyStatic, onLangChange, setLine } from './i18n.js';
import { Loader } from './loading.js';
import { createDebugOverlay, builtGeoJSON } from './debugOverlay.js';
import { rng, runSeed } from './random.js';
import { trackStyles, loadHeightFacts } from './heights.js';
import { speedFacts } from './speedRules.js';
import { loadFigureFont, signFacts } from './speedSigns.js';
// the signs' fallback face (D-DIN) loads while the world does; the game waits for it before it draws them (#364)
const figureFont = loadFigureFont();
import { credits, logProvenance, fallbacks } from './provenance.js';
import { initHelp } from './help.js';
import { Mirror } from './mirror.js';
import { People, PEOPLE_FILES, loadPeople } from './people.js';

const $ = (id) => document.getElementById(id);

const load = new Loader();
applyStatic();
// line selection: ?line=N, else the last one played
let lines = [];
try { lines = await (await load.get('data/lines.json')).json(); } catch { /* single-line build */ }
const params = new URLSearchParams(location.search);
let lineId = params.get('line');
try { lineId = lineId || localStorage.getItem('tram.line'); } catch { /* storage unavailable */ }
if (!lineId || (lines.length && !lines.some((l) => l.line === lineId))) lineId = lines[0]?.line || '22';
// every file of the line at once (the optional ones may be missing); the T3 model alongside
for (const f of ['json', 'geo.json', 'bld.bin', 'dtm.json', 'signals.json', 'dtmpoints.json']) load.prefetch(`data/line${lineId}.${f}`);
if (!params.has('nofine')) load.prefetch(`data/line${lineId}.fine.json`).prefetch(`data/line${lineId}.fine.bin`);
// the tram models (assets/vehicles.json, #455): the ones loaded at start downloaded with the line
const vehicles = await loadRegistry((u) => load.get(u));
for (const v of vehicles) if (v.preload) for (const f of v.files) load.prefetch(fileUrl(v, f.path), f.bytes);
// the pedestrians' figures (#251); ?boxpeople keeps the box figures
const figures = !params.has('boxpeople');
if (figures) for (const f of PEOPLE_FILES) load.prefetch(f);
// (weights: the steps' usual milliseconds on line 17; the bar shares them with the downloads by time)
load.plan([['terrain', 2000], ['profile', 500], ['world', WORLD_PARTS.reduce((a, p) => a + p[1], 0)], ['gpu', 1500], ['tram', 300]]);
const data = await (await load.get(`data/line${lineId}.json`)).json();
data.line = String(data.line);
checkBuiltRoute(data); // (the track as the build draws it: its curves, the run past the termini, radius and cant: #477, #478)
const built = { [`line${lineId}.json`]: data }; // every built file, for the credits and the provenance log
// ?profile=<name>: a trial height profile over the line's own, to drive and compare (reports/review/profiles/, #358)
if (params.has('profile')) {
  const name = params.get('profile'), res = await fetch(`reports/review/profiles/line${lineId}-${encodeURIComponent(name)}.json`);
  if (res.ok) {
    const p = await res.json();
    data.heights = p.heights;
    data.heightSource = p.heightSource;
    data.tracks.forEach((t, i) => { if (p.zs[i]) t.zs = p.zs[i]; else delete t.zs; });
    const tag = document.createElement('div');
    tag.textContent = `height profile: ${name}`;
    tag.style.cssText = 'position:fixed;left:50%;top:2px;transform:translateX(-50%);z-index:50;padding:1px 8px;font:12px monospace;color:#fff;background:#0009;pointer-events:none';
    document.body.appendChild(tag);
  } else console.warn(`no height profile ${name} for line ${lineId}: ${res.status}`);
}
setLine(data.line);
// optional Geoportál Praha import (tools/geoportal.py): LOD2 buildings, retaining walls, trees
try {
  const geoRes = await load.get(`data/line${lineId}.geo.json`);
  if (geoRes.ok) {
    data.geo = await geoRes.json();
    const bin = await load.get(`data/${data.geo.buildings.file}`);
    if (bin.ok) data.geo.buildings.arr = new Int16Array(await bin.arrayBuffer());
    built[`line${lineId}.geo.json`] = data.geo;
  }
} catch (e) { console.warn('no Geoportál data', e); }
widenTramStreets(data); // street widths include the tram tracks running down the middle
// optional surveyed streets (Prague DTM, tools/dtm.py) for the districts imported so far
try {
  const r = await load.get(`data/line${lineId}.dtm.json`);
  if (r.ok) { data.dtm = await r.json(); built[`line${lineId}.dtm.json`] = data.dtm; }
} catch { /* not imported for this line */ }
// optional OSM traffic signals (stop lines, signalled crossings; .claude/tools/osm_signals.py for now)
try {
  const r = await load.get(`data/line${lineId}.signals.json`);
  if (r.ok) { data.osmSignals = await r.json(); built[`line${lineId}.signals.json`] = data.osmSignals; }
} catch { /* none for this line */ }
// optional street furniture of Prague's technical map (manholes, inlets, hydrants, …; .claude/tools/dtm_points.py)
try {
  const r = await load.get(`data/line${lineId}.dtmpoints.json`);
  if (r.ok) { const j = await r.json(); data.dtmPoints = j.points; built[`line${lineId}.dtmpoints.json`] = j.provenance ? j : { attribution: 'Street furniture: DTM Praha (archive), data base © IPR Praha (CC BY 4.0).' }; }
} catch { /* none for this line */ }
// wait for the rest before the build steps, which block the page
// the user's facts (data/truth.json): track styles set how high top of rail stands over the surface
const truth = await loadHeightFacts();
const fineRes = params.has('nofine') ? [] : await Promise.all([load.get(`data/line${lineId}.fine.json`), load.get(`data/line${lineId}.fine.bin`)]);
await Promise.all(vehicles.filter((v) => v.preload).flatMap((v) => v.files.map((f) => load.get(fileUrl(v, f.path)))));
await load.begin('terrain');
// (dev switch for comparing lint runs: ?notunnels)
if (params.has('notunnels')) data.roads = data.roads.filter((r) => !r.t);
chainTunnels(data.roads); // road tunnels and bridges: heights between their real portals / abutments
// the track beyond both termini as the build walked it, so a two-car set standing at the first stop is on rails
const route = new Route(data.path, data.pathExt);
route.speedInfo = data.speed || null; // posted speeds and dedicated track (tools/osm_speeds.py)
// the curves' radius and the banked curves as the build worked them out (tools/cant.py, #478)
route.useBuilt(data.curvature.path, data.curvature.unit, data.cant, data.crossLevel && { ...data.crossLevel, c: data.crossLevel.path });
const terrain = new Terrain(data.terrain);
// the fine terrain near the tracks (2 m, tools/fine_terrain.py), where it was made for this line
// (dev switch ?nofine: the coarse grid only, for comparing lint runs)
if (!params.has('nofine')) try {
  const [mr, br] = fineRes;
  if (mr.ok && br.ok) {
    const meta = await mr.json();
    terrain.addFine(meta, new Int16Array(await br.arrayBuffer()));
    built[`line${lineId}.fine.json`] = meta;
  }
} catch { /* not made for this line */ }
data.attribution = credits(built);
logProvenance(built);
const dtm = data.dtm ? new DtmSurface(data.dtm, terrain, THREE) : null;
await load.begin('profile');
const styles = trackStyles(truth, data); // (the build's sections and lift, tools/track_styles.py, #479, #480)
const profile = new Profile(route, data, styles.lift, dtm, terrain); // (the built top of rail and structures, #197, #480)
const ground = makeGround(route, terrain, profile, dtm);
ground.styles = styles;
ground.model = bridgeModel(data.geo); // the Mosty 3D decks anywhere (bridge ways off the route)
ground.walls = carveCorridor(terrain, route, profile, dtm); // flatten the track bench, retaining walls
route.ground = ground;

// ------------------------------------------------------------------ renderer & scene
const canvas = $('gl');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, logarithmicDepthBuffer: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
window.renderer = renderer; // (from the start, also in the menu: performance checks, tools/test_idle.py)
// Out of GPU memory (or the GPU reset), the browser drops the WebGL context. The world's geometry is no
// longer kept in JS after upload (uploadWorld), so it cannot be rebuilt here: say so and offer a reload
// instead of a frozen black screen.
// Leaving the page (another line from the menu, a reload, a link): the graphics memory goes back at once instead of
// whenever the browser collects the old page, and a page the browser kept for Back (its back/forward cache) loads
// afresh rather than resuming without it (#350). Not on a hidden tab: that is visibilitychange, and the world stays.
let leaving = false;
addEventListener('pagehide', () => {
  leaving = true;
  try { renderer.dispose(); renderer.forceContextLoss(); } catch { /* (already lost) */ }
});
addEventListener('pageshow', (e) => { if (e.persisted) location.reload(); });
canvas.addEventListener('webglcontextlost', (e) => {
  e.preventDefault();
  if (leaving) return; // (our own release above, not the browser's)
  // (window.game, not game: the context can be lost while the world uploads, before `let game` below
  // is reached, and reading it then threw instead of showing this card)
  if (window.game) window.game.paused = true;
  const card = $('resultsCard');
  card.innerHTML = `<h1>${t('gl.lost')}</h1><p>${t('gl.lostWhy')}</p><button class="primary" id="glReload">${t('gl.reload')}</button>`;
  $('results').classList.remove('hidden');
  $('glReload').onclick = () => location.reload();
  noteError('contextlost', 'WebGL context lost');
  failNote('contextlost', card);
});
const scene = new THREE.Scene();
const debugOverlay = createDebugOverlay(scene);
const sky = new THREE.Color('#b9cfe0');
scene.background = sky;
scene.fog = new THREE.Fog(sky, 180, 950);
// The cab view's field of view, and the held zoom key's (G, #382): 3x is what brings a sign at SIGN_SCALE 2 to readable
// figures (8 px at 1080p) 75 m ahead, as an eye reads the real ones (docs/decisions/2026-11-07-speed-limits-and-signs.md,
// the size experiment).
const CAB_FOV = 62, ZOOM = 3;
const zoomFov = (z) => (2 * Math.atan(Math.tan((CAB_FOV / 2) * Math.PI / 180) / z) * 180) / Math.PI;
const camera = new THREE.PerspectiveCamera(CAB_FOV, 1, 0.3, 1600);
const hemi = new THREE.HemisphereLight(0xdfe9f5, 0x6b6a5c, 1.6);
scene.add(hemi);
const sun = new THREE.DirectionalLight(0xfff1dc, 1.6);
sun.position.set(-300, 500, 200);
scene.add(sun);

function resize() {
  const w = window.innerWidth, h = window.innerHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
window.addEventListener('resize', resize);
resize();

// ------------------------------------------------------------------ weather
const WEATHER = {
  dry: { sky: '#b9cfe0', fog: [180, 950], sun: 1.6, hemi: 1.6 },
  rain: { sky: '#8e99a3', fog: [90, 520], sun: 0.55, hemi: 1.25 },
  leaves: { sky: '#a9b2b5', fog: [120, 700], sun: 0.9, hemi: 1.35 },
  snow: { sky: '#c3c9cf', fog: [70, 480], sun: 0.6, hemi: 1.45 },
};
let world = null;
const rain = makeRain(), snow = makeSnow();
scene.add(rain, snow);

// The whole world to the GPU in the loading step 'gpu' (one frame drawing everything, culling off:
// buffers and shaders), not piecemeal as it comes into view (the first frame after the loading screen
// took seconds). Its geometry is static: once a buffer is on the GPU the JS copy is dropped (line 17:
// ~660 MB of the heap). Kept with ?bot (the street bot reads the meshes) and ?keepgeo (dev tools
// reading window.world's geometry, tools/lint.js: pass it there). The cost: a lost WebGL context
// cannot be restored without reloading the page.
const keepGeometry = params.has('bot') || params.has('keepgeo');
function uploadWorld() {
  const culled = [];
  world.traverse((o) => {
    const g = o.geometry;
    if (!g) return;
    if (!keepGeometry && !g.userData.release) {
      g.userData.release = true;
      if (!g.boundingSphere) g.computeBoundingSphere(); // (culling reads it; it cannot be computed later)
      const free = function () { this.array = null; };
      for (const a of Object.values(g.attributes)) a.onUpload(free);
      g.index?.onUpload(free);
    }
    if (o.frustumCulled) { culled.push(o); o.frustumCulled = false; }
  });
  renderer.render(scene, camera);
  for (const o of culled) o.frustumCulled = true;
}

// The world is built once (in the loading step 'world'); the weather only sets the sky, the light, the
// precipitation and the materials' state (src/weather.js): instant, so it could change during a shift.
async function buildCity() {
  await load.parts(WORLD_PARTS);
  world = await buildWorld(scene, data, route, ground, (part) => load.partDone(part));
  if (data.dtmPoints) world.add(buildStreetDetail(data, ground));
  ground.dtm?.seal(); // (the survey's heights are final now: faster lookups for the simulation, #245)
  window.world = world; // read by the lints (tools/lint.js)
}

function applyWeather(w) {
  const cfg = WEATHER[w];
  sky.set(cfg.sky);
  scene.fog.color.set(cfg.sky);
  [scene.fog.near, scene.fog.far] = cfg.fog;
  sun.intensity = cfg.sun;
  hemi.intensity = cfg.hemi;
  rain.visible = w === 'rain';
  snow.visible = w === 'snow';
  world.userData.setWeather(w);
}

// snowflakes: points drifting down (~1 m/s) and sideways around the camera
function makeSnow() {
  const n = 4000, pos = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) pos.set([(Math.random() - 0.5) * 60, Math.random() * 25, (Math.random() - 0.5) * 60], i * 3);
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const m = new THREE.Points(g, new THREE.PointsMaterial({ color: 0xf4f6f8, size: 0.07, transparent: true, opacity: 0.9 }));
  m.frustumCulled = false;
  m.visible = false;
  return m;
}

function updateSnow(dt, t) {
  if (!snow.visible) return;
  const pos = snow.geometry.attributes.position.array;
  for (let i = 0; i < pos.length; i += 3) {
    pos[i + 1] -= (0.8 + (i % 7) * 0.08) * dt;
    pos[i] += Math.sin(t * 0.7 + i) * 0.3 * dt;
    if (pos[i + 1] < -3) pos[i + 1] += 25;
  }
  snow.geometry.attributes.position.needsUpdate = true;
  snow.position.set(camera.position.x, camera.position.y - 10, camera.position.z);
}

function makeRain() {
  const n = 2500;
  const pos = new Float32Array(n * 6);
  for (let i = 0; i < n; i++) {
    const x = (Math.random() - 0.5) * 70, y = Math.random() * 30, z = (Math.random() - 0.5) * 70;
    pos.set([x, y, z, x + 0.05, y + 0.6, z], i * 6);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const m = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: 0xc8d2dc, transparent: true, opacity: 0.45 }));
  m.frustumCulled = false;
  m.visible = false;
  return m;
}

function updateRain(dt) {
  if (!rain.visible) return;
  const pos = rain.geometry.attributes.position.array;
  for (let i = 0; i < pos.length; i += 6) {
    pos[i + 1] -= 14 * dt;
    pos[i + 4] -= 14 * dt;
    if (pos[i + 1] < -3) { pos[i + 1] += 30; pos[i + 4] += 30; }
  }
  rain.geometry.attributes.position.needsUpdate = true;
  rain.position.set(camera.position.x, camera.position.y - 12, camera.position.z);
}

await load.begin('world');
await buildCity();
applyWeather('dry');
await load.begin('gpu');
uploadWorld();
await load.begin('tram');
// a vehicle loaded (its files, its template) and credited once; one that fails stays out and makeT3 builds the
// first loaded one before it in the index (the built-in car loads always)
const credited = new Set();
async function useVehicle(id) {
  const v = vehicles.find((x) => x.id === id);
  if (!v) return;
  try { await loadVehicle(v, (u) => load.get(u)); }
  catch (e) { console.warn(`vehicle ${id} not loaded`, e); return; }
  if (v.licence.credit && !credited.has(id)) { credited.add(id); data.attribution += ` ${v.licence.credit}`; $('attrib').textContent = data.attribution; }
}
for (const v of vehicles) if (v.preload) await useVehicle(v.id);
let people = null;
if (figures) {
  try { people = new People(scene, await loadPeople(await Promise.all(PEOPLE_FILES.map((f) => load.get(f))))); }
  catch (e) { console.warn('pedestrian figures not loaded: the box figures stay', e); }
}
window.people = people;
// the menu's tram models, in the index's order with their names in the menu's language; the first is the default.
// One not loaded at start downloads when the player picks it (the user, 2026-11-04, of the classic model: "make it
// available for user's choice to load").
function modelMenu() {
  const sel = $('optModel'), was = sel.value;
  sel.replaceChildren(...vehicles.map((v) => new Option(vehicleName(v, getLang()), v.id)));
  sel.value = was || vehicles[0]?.id;
}
modelMenu();
// The player's preferred set (#527; the user, 2026-11-11: "I would add optinal preferred set for the player"): the
// vehicle's listed sets, then its numbers by type (a lone number: the second car dealt of its type); remembered per
// vehicle. Our tram runs as it and no AI tram is dealt it; "any" deals ours like the others.
const FLEET_KEY = 'tram.fleet';
let fleetPicks = {};
try { fleetPicks = JSON.parse(localStorage.getItem(FLEET_KEY) || '{}'); } catch { /* storage unavailable */ }
function fleetMenu() {
  const v = vehicles.find((x) => x.id === $('optModel').value), c = fleetChoices(v), sel = $('optFleet');
  $('fleetRow').hidden = !c;
  if (!c) { sel.replaceChildren(); return; }
  const group = (label, opts) => { const g = document.createElement('optgroup'); g.label = label; g.append(...opts); return g; };
  sel.replaceChildren(new Option(t('fleet.dealt'), ''),
    ...(c.sets.length ? [group(t('fleet.sets'), c.sets.map((s) => new Option(`${s.value.replace('+', ' + ')} (${s.type})`, s.value)))] : []),
    ...c.types.map((x) => group(x.type, x.numbers.map((n) => new Option(String(n), String(n))))));
  sel.value = preferredSet(v, fleetPicks[v.id]) ? fleetPicks[v.id] : '';
}
fleetMenu();
// Our tram's livery (#529): the vehicle's own, one of its liveries, or one dealt as an AI tram's is; remembered per
// vehicle.
const LIVERY_KEY = 'tram.livery';
let liveryPicks = {};
try { liveryPicks = JSON.parse(localStorage.getItem(LIVERY_KEY) || '{}'); } catch { /* storage unavailable */ }
function liveryMenu() {
  const v = vehicles.find((x) => x.id === $('optModel').value), list = liveriesFor(v), sel = $('optLivery');
  $('liveryRow').hidden = !list.length;
  sel.replaceChildren(new Option(t('livery.own'), ''), ...(list.length ? [new Option(t('livery.dealt'), '*')] : []),
    ...list.map((l) => new Option(vehicleName(l, getLang()) + (l.types ? ` (${l.types.join(', ')})` : ''), l.id)));
  const pick = liveryPicks[v?.id];
  sel.value = pick === '*' || list.some((l) => l.id === pick) ? pick : '';
}
liveryMenu();
$('optModel').addEventListener('change', () => { fleetMenu(); liveryMenu(); useVehicle($('optModel').value); });
$('optFleet').addEventListener('change', () => {
  fleetPicks[$('optModel').value] = $('optFleet').value;
  try { localStorage.setItem(FLEET_KEY, JSON.stringify(fleetPicks)); } catch { /* storage unavailable */ }
});
$('optLivery').addEventListener('change', () => {
  liveryPicks[$('optModel').value] = $('optLivery').value;
  try { localStorage.setItem(LIVERY_KEY, JSON.stringify(liveryPicks)); } catch { /* storage unavailable */ }
});
// the run's fleet: its own stream from the run's seed (src/random.js), so dealing draws nothing from the traffic's
// and a replay deals the same
const fleetDealer = (vehicle, seed) => new FleetDealer(pickVehicle(vehicle), rng((seed ^ 0x6a09e667) >>> 0));
// (a livery limited to some types: our set dealt of one of them, unless the preferred set is of another; then the
// vehicle's own)
function ourSet(dealer, vehicle, cars) {
  const v = pickVehicle(vehicle), pick = $('optLivery').value, l = liveries.get(pick);
  const s = dealer.ours(cars, preferredSet(v, $('optFleet').value), l?.types && !l.types.includes('T3SUCS') ? l.types[0] : 'T3SUCS');
  if (pick !== '*') s.livery = l && (!l.types || l.types.includes(s.type)) ? l.id : null;
  return s;
}
// the T3 ran in two-car sets on most lines; line 23 is the single-car heritage line
const lineCars = data.line === '23' ? 1 : 2;
// The run number card behind the windscreen (user, 2026-10-23): the depot's digit and the run's two
// digits (801 = depot 8, run 01); a tram keeps its run number for its whole time out in service;
// night and late-evening runs (single cars) are numbered from 51. Prepared for data the line files
// do not have yet: `data.runs[trip] = { depot, run }` (which run serves each timetable trip, from the
// PID GTFS or the run lists published by enthusiasts, e.g. pražské tramvaje / forums; a build tool to
// come). Until then a placeholder: depot 8, a day run (01-49) from the trip's place in the timetable.
function runNumber(trip) {
  const r = data.runs?.[trip];
  if (r) return `${r.depot}${String(r.run).padStart(2, '0')}`;
  return `8${String((trip % 49) + 1).padStart(2, '0')}`;
}
// (the destination card: the last stop until a shift says otherwise)
const lastStop = data.stops[data.stops.length - 1].name;
// (a T3SUCS, the tram the simulation drives with its TR 37 equipment, or the player's preferred set; AI trams are
// dealt the types and numbers of their vehicle's fleet: assets/*/vehicle.json `fleet`, src/vehicles.js FleetDealer)
let tramModel = makeT3({ line: data.line, cars: lineCars, vehicle: $('optModel').value, dest: lastStop, run: runNumber(0),
  dealt: ourSet(fleetDealer($('optModel').value, 0), $('optModel').value, lineCars) });
scene.add(tramModel);

const hud = new Hud();
const audio = new TramAudio();
let tram = new Tram();
let game = null;
let traffic = null;
let pilot = null; // autopilot driving the tram (watch the ride), or null
// our tram's lamps (#436): the indicators ('left', 'right', 'hazard' or none: the driver's switch, the autopilot's
// own while it drives), the high beams (latched on, or held for a flash); the line's junction turns and the
// stops where passengers cross a car lane, where the autopilot indicates (src/indicators.js)
const lamps = { indicate: null, high: false, held: false, lit: false, turns: [], kerb: [] };
let chase = false;

// ------------------------------------------------------------------ menu
const selStop = $('selStop'), selTrip = $('selTrip');
function menuTexts() {
  $('routeName').textContent = t('menu.routeName', {
    from: data.stops[0].name, to: data.stops[data.stops.length - 1].name,
    km: (route.length / 1000).toFixed(1), stops: data.stops.length, trips: data.timetable.length,
  });
  $('help').innerHTML = t('help');
}
$('attrib').textContent = data.attribution;
// a deployed copy says which commit and data it is (tools/deploy.py writes version.json; not asked for
// on a local server, where it would only be a 404 in the console)
if (!['localhost', '127.0.0.1'].includes(location.hostname)) fetch('version.json').then((r) => (r.ok ? r.json() : null)).then((v) => {
  if (v) $('attrib').textContent += ` · Version ${v.commit.slice(0, 7)} (${v.deployed.slice(0, 10)}), data ${v.data?.snapshot ?? '?'}.`;
  window.deployVersion = v; // (in each report, src/report.js)
}).catch(() => { /* not deployed */ });
$('line').textContent = data.line;
$('menuLine').textContent = data.line;
const selLine = $('selLine');
for (const l of lines.length ? lines : [{ line: data.line, from: data.stops[0].name, to: data.stops[data.stops.length - 1].name }]) {
  // a run that changes its number on the way: "9 → 10: Sídliště Řepy → Sídliště Řepy (via …)"
  const label = l.then ? `${l.line} → ${l.then}: ${l.from} → ${l.to} (${l.via})` : `${l.line}: ${l.from} → ${l.to}`;
  selLine.add(new Option(label, l.line));
}
selLine.value = data.line;
selLine.addEventListener('change', () => {
  try { localStorage.setItem('tram.line', selLine.value); } catch { /* storage unavailable */ }
  location.search = `?line=${selLine.value}`; // a different line loads a different world
});
applyStatic();
menuTexts();
$('optLang').value = getLang();
$('optLang').addEventListener('change', () => setLang($('optLang').value));
initHelp();
onLangChange(() => { menuTexts(); modelMenu(); fleetMenu(); liveryMenu(); const v = selTrip.value; fillTrips(); selTrip.value = v; touch.labels(); });
// on-screen controls on a phone or tablet (src/touch.js): buttons that send the keys
const touch = new TouchControls({ deadman: () => game?.opts.deadman });
data.stops.slice(0, -1).forEach((s, i) => selStop.add(new Option(`${i + 1}. ${s.name}`, i)));

function fillTrips() {
  const si = +selStop.value;
  selTrip.innerHTML = '';
  const now = new Date();
  const nowSec = now.getHours() * 3600 + now.getMinutes() * 60;
  let best = 0, bestD = Infinity;
  data.timetable.forEach((trip, i) => {
    selTrip.add(new Option(t('menu.tripOption', { dep: fmtTime(trip[si]).slice(0, 5), first: data.stops[0].name, t0: fmtTime(trip[0]).slice(0, 5) }), i));
    const d = trip[si] - nowSec;
    if (d >= 0 && d < bestD) { bestD = d; best = i; }
  });
  selTrip.value = best;
  previewAt(data.stops[si].s + 6);
}
selStop.addEventListener('change', fillTrips);
fillTrips();

$('btnStart').addEventListener('click', () => start());

// extra: Game options over the menu's (the performance test's lead to the departure)
async function start(extra = {}) {
  await useVehicle($('optModel').value);
  audio.start();
  await figureFont;   // after audio.start: the click's activation unlocks the audio
  const cars = $('optCars').value === 'auto' ? lineCars : +$('optCars').value;
  tram = new Tram(cars);
  zoom = zoomTarget = 1;
  tram.eq.mode = controlMode();
  const vehicle = $('optModel').value;
  // one seeded stream for the whole run (rules and traffic), apart from Math.random
  const seed = runSeed(), random = rng(seed);
  const dealer = fleetDealer(vehicle, seed), ours = ourSet(dealer, vehicle, cars);
  if (tramModel.userData.cars.length !== cars || tramModel.userData.vehicle !== pickVehicle(vehicle)?.id
    || String(tramModel.userData.fleet) !== String(ours.numbers) || tramModel.userData.livery !== (ours.livery ?? null)) {
    scene.remove(tramModel);
    disposeModel(tramModel);
    tramModel = makeT3({ line: data.line, cars, vehicle, dest: lastStop, run: runNumber(0), dealt: ours });
    scene.add(tramModel);
  }
  if (game) { scene.remove(game.objects); disposeModel(game.objects); }
  const weather = $('optWeather').value;
  applyWeather(weather);
  game = new Game(scene, data, route, tram, audio, {
    weather,
    tripIndex: +selTrip.value,
    startStop: +selStop.value,
    assist: $('optAssist').checked,
    deadman: $('optDeadman').checked,
    // onboard computer sets every switch by radio (no overhead contacts to work)
    autoSwitch: $('optAutoSwitch').checked,
    autoIrc: $('optAutoSwitch').checked,
    obstacles: $('optObst').value,
    toutAt: outdoorTemperature($('optTemp').value),
    vehicle: $('optModel').value,
    dealer,
    seed: Math.floor(random() * 1e9),
    substations: truth.substations?.list,
    speedFacts: speedFacts(truth),
    signFacts: signFacts(truth),
    ...extra,
  });
  game.runSeed = seed; // (replay: ?seed=N)
  perfLog.reset({ line: data.line, model: tramModel.userData.vehicle, cars, weather, controls: tram.eq.mode, autopilot: $('optAuto').checked });
  // the line number shown on the tram, the top bar and in messages follows the run
  const showLine = (l) => { $('line').textContent = l; setLine(l); setConsistLine(tramModel, l, game.destination, runNumber(game.opts.tripIndex)); };
  showLine(game.line);
  game.onLineChange = showLine;
  if (traffic) traffic.dispose();
  traffic = new Traffic(scene, data, route, ground, game, random);
  debugOverlay.reset();
  Object.assign(lamps, { indicate: null, high: false, held: false, turns: junctionTurns(route, data.switches), kerb: game.stops.filter((st) => st.vienna).map((st) => st.target) });
  game.lamps = lamps; // (the console and tests: the junction turns and kerb stops found, the lamps' state)
  pilot = $('optAuto').checked ? new Autopilot() : null;
  game.autopilot = !!pilot;
  pedalKey = null;
  window.game = game; // handy for debugging from the console
  game.provenance = { files: built, fallbacks: () => fallbacks(built) }; // where each list came from (#10)
  game.mirror = mirror.stats;
  window.camera = camera;
  window.renderer = renderer; // performance checks from the console (renderer.info, the scene)
  window.scene = scene;
  window.traffic = traffic;
  // the compiled world as GeoJSON (docs/architecture.md §10.4), for the annotation editor
  window.exportBuiltGeoJSON = (save = true) => {
    const fc = builtGeoJSON(game, traffic);
    if (save) { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify(fc)], { type: 'application/geo+json' })); a.download = `data-line${game.data.line}.built.geojson`; a.click(); }
    return fc;
  };
  window.tramModel = tramModel;
  $('menu').classList.add('hidden');
  touch.sync();
  $('results').classList.add('hidden');
  hud.show(true);
  $('mirror').classList.remove('hidden');
  game.msg(t('msg.shiftStart', { stop: game.stops[game.nextStop].name, time: fmtTime(game.stops[game.nextStop].sched).slice(0, 5) }), 'info', 7);
  if (params.has('bot')) streetBot();
  if (params.has('inspect')) inspect.toggle(true);
  if (params.has('debug')) debugOverlay.toggle(game, traffic);
}

// debugging (?bot): drive and walk every street in the surveyed DTM areas, list what looks wrong
async function streetBot() {
  game.paused = true;
  window.freeCam = true;
  hud.show(false);
  const css = document.createElement('style');
  css.textContent = '#pausePanel, #mirror, #action, #cab { display: none !important }';
  document.head.appendChild(css);
  const result = await runStreetBot({ world, traffic, ground, route, progress: (m) => game.msg(`street bot: ${m}`, 'info', 3) });
  window.streetBot = result;
  console.log('street bot', result.stats);
  const label = (P) => {
    const n = route.nearest(P.x, P.y);
    const st = n ? data.stops.reduce((a, b) => (Math.abs(b.s - n.s) < Math.abs(a.s - n.s) ? b : a)) : null;
    return `${st ? st.name : '?'} · ${n ? Math.round(n.d) : '?'} m from track · (${P.x.toFixed(0)}, ${P.y.toFixed(0)})`;
  };
  window.botPanel = showBotPanel(result, { scene, camera, label });
}

function showResults() {
  hud.show(false);
  $('mirror').classList.add('hidden');
  const served = game.log.filter((l) => l.dev !== undefined);
  const avg = served.length ? served.reduce((a, l) => a + Math.abs(l.dev), 0) / served.length : 0;
  const pen = Object.entries(game.penalties).filter(([, v]) => v >= 0.5)
    .map(([k, v]) => `<tr><td>${t(`pen.${k}`)}</td><td>−${Math.round(v)}</td></tr>`).join('');
  const rows = game.log.map((l) => `<tr><td>${l.name}</td><td>${l.dev !== undefined ? fmtDev(l.dev) : l.skipped ? t('res.requestPassed') : t('res.missed')}</td></tr>`).join('');
  $('resultsCard').innerHTML = `
    <h1><span>${data.line}</span>${t(game.failed ? 'res.derailed' : 'res.end')}</h1>
    <div class="sub">${game.stops[game.stops.length - 1].name} · ${fmtTime(game.clock)}</div>
    <div style="font-size:34px;font-weight:800;margin:6px 0">${t('res.points', { n: Math.round(game.score) })}</div>
    <div>${t('res.avgDev')} <b>${fmtDev(avg).slice(1)}</b></div>
    ${pen ? `<h3>${t('res.penalties')}</h3><table class="res">${pen}</table>` : ''}
    <h3>${t('res.stops')}</h3><table class="res">${rows}</table>
    <div id="perfAsk" class="sub" style="margin:10px 0"></div>
    <button class="primary" id="again">${t('res.again')}</button>`;
  $('results').classList.remove('hidden');
  $('again').onclick = () => { $('results').classList.add('hidden'); $('menu').classList.remove('hidden'); };
  offerPerf($('perfAsk'));
}

// ------------------------------------------------------------------ how it ran (#350)
// Every drawn frame of a shift goes into the frame-time log (src/perf.js); a note carries its summary, the
// machine and the load times, and a shift's end offers to send the summary: once, always (kept in this
// browser) or not now. Nothing is sent without a click or that "always".
const perfLog = new PerfLog();
window.perfLog = perfLog;
addFacts(() => ({ machine: machine(renderer), load: window.loadTimes || null, perf: perfLog.summary() }));
const PERF_KEY = 'tram.perfSend';
function offerPerf(el) {
  const sum = perfLog.summary();
  if (!sum || sum.seconds < 30) return;
  let always = false;
  try { always = localStorage.getItem(PERF_KEY) === 'always'; } catch { /* (no storage) */ }
  const send = async () => { el.textContent = (await sendNote({ kind: 'perf', line: data.line })) ? t('res.perfSent') : t('fb.errorFailed'); };
  if (always) { send(); return; }
  el.innerHTML = `<div>${t('res.perfAsk')}</div><button id="perfSend">${t('res.perfSend')}</button> <button id="perfAlways">${t('res.perfAlways')}</button>`;
  $('perfSend').onclick = send;
  $('perfAlways').onclick = () => { try { localStorage.setItem(PERF_KEY, 'always'); } catch { /* (no storage) */ } send(); };
}

// The performance test (the menu): a minute of the autopilot on a fixed stretch, so runs on different machines
// compare: the line's middle stop, the trip nearest 8:00 there (rush hour), dry weather, seed 1, measured after
// 5 s to settle and from the departure on. It starts 10 s before the departure, not a shift's 40 s, so the wait is
// short and the minute all driving (the user, 2026-11-11: "autopilot waits half a minute standing for the timetable
// departure"). The GPU's own time per
// frame where the browser has a timer. Two buttons: the line loaded now, and the reference run: line 17 from
// Palackého náměstí with the detailed model, the heaviest line with surveyed streets, the one result every machine
// has in common. Its stop is named, not the middle one, so it stays when the route changes (the user, 2026-11-11:
// "I would keep it fixed there even if later line 17 runs start from another stop like Libuš"). From another line
// the reference opens line 17 (?reftest=<the line left>), runs there, and its "Back to the menu" goes back.
// (window.perfTestMs: a shorter run for tools/test_perf.py)
const PT_WARM = 5000, PT_LEN = window.perfTestMs || 60000;
const REF_LINE = '17', REF_STOP = 'Palackého náměstí', PT_LEAD = 10;
let perfTest = null;
async function startPerfTest(reference = false) {
  const keep = { auto: $('optAuto').checked, weather: $('optWeather').value, model: $('optModel').value, cars: $('optCars').value };
  if (reference) { $('optModel').value = 'detailed'; $('optCars').value = 'auto'; }
  const named = reference ? data.stops.slice(0, -1).findIndex((st) => st.name === REF_STOP) : -1;
  const si = named >= 0 ? named : Math.floor((data.stops.length - 1) / 2), at8 = (trip) => Math.abs(trip[si] - 8 * 3600);
  selStop.value = si;
  fillTrips();
  selTrip.value = data.timetable.reduce((b, trip, i) => (at8(trip) < at8(data.timetable[b]) ? i : b), 0);
  $('optAuto').checked = true;
  $('optWeather').value = 'dry';
  window.runSeed = 1;
  try { await start({ lead: PT_LEAD }); } finally {
    delete window.runSeed;
    $('optAuto').checked = keep.auto;
    $('optWeather').value = keep.weather;
    $('optModel').value = keep.model;
    $('optCars').value = keep.cars;
  }
  perfTest = { t0: performance.now(), phase: 'warm', timer: gpuTimer(renderer.getContext()),
    meta: { ...perfLog.meta, test: true, reference, stop: data.stops[si].name } };
  game.msg(t('pt.running'), 'info', 8);
}
$('btnPerfTest').addEventListener('click', () => startPerfTest(false));
$('btnPerfRef').addEventListener('click', () => {
  if (String(data.line) === REF_LINE) startPerfTest(true);
  else location.search = `?line=${REF_LINE}&reftest=${encodeURIComponent(data.line)}`;
});
function perfTestStep(now) {
  if (!perfTest || !game || game.finished) { perfTest = null; return; }
  const el = now - perfTest.t0;
  // (the minute is measured from the departure: boarding and the doors take ~14 s after the start, 2026-11-11 trace)
  const off = el > PT_WARM && (tram.v > 0.5 || el > PT_WARM + 60000);
  if (perfTest.phase === 'warm' && off) { perfTest.phase = 'run'; perfTest.t1 = now; perfTest.s0 = tram.s; perfLog.reset(perfTest.meta); }
  else if (perfTest.phase === 'run' && now - perfTest.t1 > PT_LEN) finishPerfTest();
  perfTest?.timer?.poll();
}
function finishPerfTest() {
  const pt = perfTest;
  perfTest = null;
  game.paused = true;
  hud.show(false);
  const sum = { ...perfLog.summary(), gpuMs: pt.timer?.median() ?? null, driven: Math.round(tram.s - pt.s0) }, m = machine(renderer);
  // (frames over 20 ms: below a 60 Hz display's rate; a steady 30 fps has nearly all of them there and few over 50:
  // playable, not smooth. The first remote run, Intel HD Graphics 400 in Firefox: 34 fps, 74 % over 20 ms, 0.6 % over 33)
  const verdict = sum.over[20] < 5 ? 'good' : sum.over[50] < 5 ? 'ok' : 'slow';
  const row = (k, v) => `<tr><td>${t(k)}</td><td>${v}</td></tr>`;
  $('resultsCard').innerHTML = `
    <h1>${t(pt.meta.reference ? 'pt.titleRef' : 'pt.title')}</h1>
    <div class="sub">${data.line} · ${pt.meta.stop} · ${sum.seconds} s</div>
    <div style="font-size:22px;font-weight:700;margin:8px 0">${t(`pt.${verdict}`)}</div>
    <table class="res">
      ${row('pt.fps', sum.fps)}${row('pt.slow20', `${sum.over[20]} %`)}${row('pt.slow33', `${sum.over[33]} %`)}${row('pt.p90', `${sum.ms.p90} ms`)}
      ${sum.gpuMs !== null ? row('pt.gpu', `${sum.gpuMs} ms`) : ''}${row('pt.draws', sum.calls.mean)}
      ${row('pt.tris', `${(sum.triangles.mean / 1e6).toFixed(2)} M`)}${row('pt.gpuName', m.gpu || '?')}${row('pt.screen', `${m.viewport} @${m.dpr}`)}
    </table>
    <div class="sub">${t('pt.note')}</div>
    <button class="primary" id="ptSend">${t('pt.send')}</button> <button id="ptMenu">${t('pt.menu')}</button>`;
  $('results').classList.remove('hidden');
  $('ptSend').onclick = async () => {
    $('ptSend').disabled = true;
    $('ptSend').textContent = (await sendNote({ kind: 'perftest', line: data.line, perftest: sum })) ? t('pt.sent') : t('fb.errorFailed');
  };
  $('ptMenu').onclick = () => {
    // (a reference run started from another line goes back to it)
    if (params.get('reftest')) { location.search = `?line=${encodeURIComponent(params.get('reftest'))}`; return; }
    $('results').classList.add('hidden');
    $('menu').classList.remove('hidden');
  };
  window.perfTestResult = sum; // (tools/test_perf.py)
}

// ------------------------------------------------------------------ outdoor temperature
// Real hourly temperature in Prague for today (Open-Meteo, no key, sampled once per hour and
// interpolated by the timetable clock), or a fixed season. Fetched once in the background.
let pragueHourly = null;
fetch('https://api.open-meteo.com/v1/forecast?latitude=50.08&longitude=14.42&hourly=temperature_2m&forecast_days=2&timezone=Europe%2FPrague')
  .then((r) => r.json()).then((j) => { pragueHourly = j.hourly?.temperature_2m || null; }).catch(() => { /* offline: seasonal fallback */ });
function outdoorTemperature(mode) {
  const fixed = { winter: -6, autumn: 8, summer: 29 }[mode];
  if (fixed !== undefined) return (clock) => fixed + 2 * Math.sin(((clock / 3600 - 9) / 24) * 2 * Math.PI);
  return (clock) => {
    const h = clock / 3600;
    if (pragueHourly) {
      const i = Math.max(0, Math.min(pragueHourly.length - 2, Math.floor(h)));
      return pragueHourly[i] + (pragueHourly[i + 1] - pragueHourly[i]) * Math.min(1, Math.max(0, h - i));
    }
    // no network: a plausible day for the season, coolest at 5 h, warmest at 15 h
    const month = new Date().getMonth(), mean = [0, 1, 5, 10, 15, 18, 20, 20, 15, 10, 5, 1][month];
    return mean + 4 * Math.sin(((h - 9) / 24) * 2 * Math.PI);
  };
}

// ------------------------------------------------------------------ pause panel
// The pause screen offers to continue or to leave the shift for the menu (pick another line,
// trip, weather...). The abandoned shift stays paused behind the menu until a new one starts.
$('btnResume').addEventListener('click', () => { if (game) game.paused = false; });
$('btnToMenu').addEventListener('click', () => {
  if (!game) return;
  game.paused = true;
  pilot = null;
  hud.show(false);
  $('mirror').classList.add('hidden');
  $('menu').classList.remove('hidden');
});

// ------------------------------------------------------------------ input
const input = { deadman: false, sand: false, cutout: false, switchBtn: false };
let look = 0, lookTarget = 0, mirrorOn = true, camAcc = 0; // head turned left (+) / right (-), right mirror shown
let zoom = 1, zoomTarget = 1; // the cab view's magnification, eased towards the target (G held: ZOOM)
window.addEventListener('keydown', (e) => {
  if (!game || game.finished || !$('menu').classList.contains('hidden') || reporter.isOpen) return;
  const k = e.key.toLowerCase();
  if (k === 'f9' && !e.repeat) { e.preventDefault(); reporter.open(); return; }
  // dev overlay of signals, stop lines, conflicts and platforms (src/debugOverlay.js; ?debug shows it at the start)
  if (k === 'f8' && !e.repeat) { e.preventDefault(); debugOverlay.toggle(game, traffic); return; }
  // dev inspect mode (src/inspect.js): its keys first
  if (inspect.active ? inspect.key(e) : k === 'i' && !e.repeat && (inspect.toggle(true), true)) return;
  if (k === 'o' && !e.repeat) {
    pilot = pilot ? null : new Autopilot();
    game.autopilot = !!pilot;
    if (!pilot) takeOver();
    game.msg(t(pilot ? 'msg.autoOn' : 'msg.autoOff'), 'info', 4);
    return;
  }
  // touching the controller or the doors takes over from the autopilot
  if (pilot && (['w', 's', 'arrowup', 'arrowdown', ' ', 'n', 'd', 'r'].includes(k) || /^Digit[0-5]$/.test(e.code))) {
    pilot = null;
    game.autopilot = false;
    takeOver();
    game.msg(t('msg.autoOff'), 'info', 4);
  }
  if (e.key === 'Shift') input.deadman = true;
  if (k === 'a') input.sand = true;
  if (k === 'c') input.cutout = true;     // heating cut-out button (pass a contact coasting in winter)
  if (k === 'y') input.switchBtn = true;  // "Výhybka" button: current through the contact
  if (['arrowup', 'arrowdown', ' '].includes(k)) e.preventDefault();
  if (k === 'p' || k === 'escape') { game.paused = !game.paused; return; }
  if (k === 'g') { zoomTarget = ZOOM; return; }   // held: look closer (also while paused, to read a sign)
  if (k === 'l' && !e.repeat) { // the high beams: held a flash, with Shift on and off
    if (e.shiftKey) { lamps.high = !lamps.high; game.msg(t(lamps.high ? 'msg.highOn' : 'msg.highOff'), 'info', 2); } else lamps.held = true;
  }
  if (game.paused) return;
  if (e.repeat && k !== 'w' && k !== 's' && k !== 'arrowup' && k !== 'arrowdown') return;
  const prev = command();
  // number keys: a drive step, with Shift a brake step, 0 both pedals released
  const digit = /^Digit[0-5]$/.test(e.code) ? +e.code.slice(5) : null;
  if (digit !== null && !e.repeat) setStep(e.shiftKey ? -digit : digit);
  switch (k) {
    case 'w': case 'arrowup': control(+1, e.repeat); break;
    case 's': case 'arrowdown': control(-1, e.repeat); break;
    case ' ': setStep(-6); break;
    case 'n': setStep(0); break;
    case 'r': if (!arcade()) tram.eq.park(); break; // the brake pedal's ratchet (arcade parks by itself)
    case 'd': game.toggleDoors(); break;
    case 'b': game.ringBell(); break;
    case 'x': game.crowbar(); break;
    case 'q': case 'arrowleft': lookTarget = 1.3; break;   // look out of the left window
    case 'e': case 'arrowright': lookTarget = -1.3; break; // look right, at the doors
    case 'z': mirrorOn = !mirrorOn; document.body.classList.toggle('nomirror', !mirrorOn); break;
    case 'h': game.setHeating('saloon'); break;
    case 'k': game.setHeating('cab'); break;
    case 'f': game.setHeating('flap'); break;
    case 'v': chase = !chase; document.body.classList.toggle('chase', chase); break;
    case 'm': audio.setMuted(!audio.muted); break;
  }
  // the indicators' switch (by the keys' places, the same on Czech and English keyboards; the touch buttons' by their
  // names): on until switched off
  const side = { Comma: 'left', Period: 'right', Slash: 'hazard' }[e.code] ?? (e.code ? null : { ',': 'left', '.': 'right', '/': 'hazard' }[e.key]);
  if (side) { lamps.indicate = lamps.indicate === side ? null : side; game.msg(t(`msg.ind.${lamps.indicate ?? 'off'}`), 'info', 2); }
  if (command() > 0 && prev <= 0 && game.doorState !== 'closed') {
    if (arcade()) tram.eq.lever = 0;
    audio.warning(); game.msg(t('msg.closeDoors'), 'warn');
  }
  if (command() !== prev) audio.click(0.12, 1600);
});
// a held key whose keyup never comes (the window lost focus) lets the view go back
window.addEventListener('blur', () => { zoomTarget = 1; });
window.addEventListener('keyup', (e) => {
  if (e.key === 'Shift') input.deadman = false;
  const ku = e.key.toLowerCase();
  if (ku === 'a') input.sand = false;
  if (ku === 'c') input.cutout = false;
  if (ku === 'y') input.switchBtn = false;
  if (['q', 'e', 'arrowleft', 'arrowright'].includes(ku)) lookTarget = 0;
  if (ku === 'g') zoomTarget = 1;
  if (ku === 'l') lamps.held = false;
  if (e.key === ' ' && command() === -6) setStep(-5); // (the emergency stop let go: brake step 5)
  if ((ku === 'w' || ku === 'arrowup' || ku === 's' || ku === 'arrowdown') && pedalKey) pedalKey = null;
});

// The controls (#221): 'arcade' moves a lever in steps and a helper works the pedals; 'advanced' moves the
// pedals (a tap to the next step's angle, held on at 20°/s) and the ratchet (R) is the driver's
function controlMode() { return $('optControls').value === 'advanced' ? 'advanced' : 'arcade'; }
function arcade() { return tram.eq.mode === 'arcade'; }
// what the driver has set: the lever (arcade, the helper moves the pedals on the next step) or the pedals' step
function command() { return arcade() ? tram.eq.lever : tram.notch; }
function takeOver() {
  tram.eq.mode = controlMode();
  tram.eq.lever = Math.max(-5, Math.min(5, tram.notch));
}
let pedalKey = null; // advanced: a held W / S moves the pedal on after 0.35 s
function control(dir, repeat) {
  const eq = tram.eq;
  if (arcade()) { if (eq.lever === -6) eq.lever = -5; else eq.lever = Math.max(-5, Math.min(5, eq.lever + dir)); return; }
  if (!repeat) { eq.tap(dir); pedalKey = { dir, t: 0 }; }
}
function setStep(n) {
  if (arcade()) tram.eq.lever = n;
  else tram.eq.setStep(n);
}
window.addEventListener('blur', () => {
  if (game && !game.finished && !pilot) { game.paused = true; audio.setActive(false); }
}); // keep riding on autopilot

// ------------------------------------------------------------------ camera & loop
const camPos = new THREE.Vector3(), camLook = new THREE.Vector3();
let yaw = null;
// the outside view (V) orbits the tram: drag turns and tilts, the wheel or two fingers zoom, a double
// click or tap brings it back behind the tram (#79). Any button turns: tied to the tram, it has nowhere to move (#342).
// It turns about the lead car's centre, 2 m over the rail, as inspect's orbit does (#541): by default 16 m behind the
// set's rear and 17 degrees up (pitch is added to that)
const orbit = { yaw: 0, pitch: 0, k: 1, drag: 0 }, ORBIT_EL = 0.3;
{
  const ptr = new Map();
  let pinch = null;
  const on = () => chase && game && !inspect.active && !window.freeCam;
  canvas.addEventListener('pointerdown', (e) => { if (!on()) return; ptr.set(e.pointerId, { x: e.clientX, y: e.clientY }); pinch = null; });
  canvas.addEventListener('pointermove', (e) => {
    const p = ptr.get(e.pointerId);
    if (!p || !on()) return;
    if (ptr.size >= 2) {
      const [a, b] = [...ptr.values()], d0 = Math.hypot(b.x - a.x, b.y - a.y);
      p.x = e.clientX; p.y = e.clientY;
      const d1 = Math.hypot(b.x - a.x, b.y - a.y);
      if (pinch !== null && d1 > 0) orbit.k = Math.max(0.3, Math.min(4, orbit.k * (d0 / d1)));
      pinch = d1;
    } else {
      orbit.yaw -= (e.clientX - p.x) * 0.006;
      orbit.pitch = Math.max(0.03 - ORBIT_EL, Math.min(1.45 - ORBIT_EL, orbit.pitch + (e.clientY - p.y) * 0.004));
      p.x = e.clientX; p.y = e.clientY;
    }
    orbit.drag = 0.3;
  });
  const up = (e) => { ptr.delete(e.pointerId); pinch = null; };
  canvas.addEventListener('pointerup', up);
  canvas.addEventListener('pointercancel', up);
  canvas.addEventListener('wheel', (e) => { if (!on()) return; e.preventDefault(); orbit.k = Math.max(0.3, Math.min(4, orbit.k * Math.exp(e.deltaY * 0.001))); orbit.drag = 0.3; }, { passive: false });
  canvas.addEventListener('dblclick', () => { if (on()) Object.assign(orbit, { yaw: 0, pitch: 0, k: 1 }); });
  canvas.addEventListener('contextmenu', (e) => { if (on()) e.preventDefault(); });
}

function previewAt(s) {
  const p = route.at(s - 40);
  const h = route.heading(s);
  camera.position.set(p.x - h.hy * 6, profile.height(s - 40) + 12, -(p.y + h.hx * 6));
  const q = route.at(s + 20);
  camera.lookAt(q.x, profile.height(s + 20), -q.y);
  placeTram(s);
}

function placeTram(s) {
  // each car rests on its two bogies, so it follows curves and pitches with the gradient
  placeConsist(tramModel, s, (q) => { const p = route.at(q); return [p.x, p.y, profile.height(q), route.rollAt(q)]; });
  if (!game) return;
  // the doors, the brake lamps and the track-brake shoes from the game; the collector on the wire (one height over
  // the rail everywhere in the data, src/world.js); the indicators and the high beams
  const braking = tram.brake > 500, clock = game.clock;
  if (pilot) lamps.indicate = indicating(lamps.turns, lamps.kerb, tram.s, tram.v, braking);
  poseT3(tramModel, { doors: game.doorOpenness, braking, track: tram.trackMagnets, collector: CONTACT_WIRE - RAIL_TOP,
    indicate: lamps.indicate, clock, highBeam: lamps.high || lamps.held });
  // the indicators' relay ticks in the cab as they go on and off
  const sig = signalsAt(lamps.indicate, clock), lit = sig.left || sig.right;
  if (lamps.indicate && lit !== lamps.lit) audio.click(0.05, lit ? 1250 : 950);
  lamps.lit = lit;
}

function updateCamera(dt, t) {
  const s = tram.s;
  placeTram(s);
  if (window.freeCam) { tramModel.visible = true; return; } // debugging: camera set from the console
  tramModel.visible = chase;
  // the zoom is the cab view's: eased over about 0.2 s, and none outside
  zoom += ((chase ? 1 : zoomTarget) - zoom) * Math.min(1, dt * 12);
  if (Math.abs(zoom - 1) < 1e-3 && zoomTarget === 1) zoom = 1;
  const fov = zoomFov(zoom);
  if (Math.abs(camera.fov - fov) > 1e-3) { camera.fov = fov; camera.updateProjectionMatrix(); }
  if (chase) {
    // around the lead car's centre (#541; it turned about a point 10 m ahead of the front before)
    const lead = tramModel.userData.cars[0], c = lead.position;
    camLook.set(c.x, c.y + 2, c.z);
    const back = T3.length / 2 + (tramModel.userData.cars.length - 1) * CAR_PITCH + 16, el = ORBIT_EL + orbit.pitch;
    const a = lead.rotation.y + orbit.yaw, R = back / Math.cos(ORBIT_EL) * orbit.k;
    camPos.set(camLook.x - Math.sin(a) * Math.cos(el) * R, camLook.y + Math.sin(el) * R, camLook.z - Math.cos(a) * Math.cos(el) * R);
    // (while the reviewer turns it, the camera follows at once; else it trails the tram smoothly)
    orbit.drag -= dt;
    camera.position.lerp(camPos, orbit.drag > 0 ? 1 : Math.min(1, dt * 4));
    camera.lookAt(camLook);
    return;
  }
  const eye = route.at(s - 1.4);
  const h = route.heading(s + 4, 8);
  const target = Math.atan2(h.hx, h.hy);
  if (yaw === null) yaw = target;
  let d = target - yaw;
  while (d > Math.PI) d -= 2 * Math.PI;
  while (d < -Math.PI) d += 2 * Math.PI;
  yaw += d * Math.min(1, dt * 5);
  const bob = Math.sin(t * 9) * 0.012 * Math.min(1, Math.abs(tram.v) / 8);
  look += (lookTarget - look) * Math.min(1, dt * 6);
  // the cab pitches with the track (bogie-to-bogie slope) plus a little load transfer
  const slope = Math.atan2(profile.height(s - 3.2) - profile.height(s - 10.8), 7.6);
  // load transfer follows the acceleration smoothly (it drops to 0 in one frame when the tram
  // comes to a dead stop, which made the view jump)
  camAcc += (tram.a - camAcc) * Math.min(1, dt * 3);
  const pitch = -0.035 - camAcc * 0.006 + slope;
  // turning the head also leans towards that side window
  const lean = look * 0.25, lx = -Math.cos(yaw) * lean, ly = Math.sin(yaw) * lean;
  camera.position.set(eye.x + lx, profile.height(s - 1.4) + 2.39 + bob, -(eye.y + ly)); // (2.39 over top of rail)
  camera.rotation.set(0, 0, 0);
  camera.rotation.order = 'YXZ';
  camera.rotation.y = -yaw + look;
  camera.rotation.x = pitch;
  // sway, and the lean into a canted curve
  camera.rotation.z = Math.sin(t * 1.3) * 0.002 * Math.min(1, tram.v / 8) + route.rollAt(s - 3);
}

// ✉ Feedback (F9, #138, #350): a note with the moment's state and a screenshot, to feedback.php
const reporter = new Reporter({
  shot: () => canvasShot(canvas, () => renderer.render(scene, camera)),
  pause: (on) => { if (on !== undefined) { game.paused = on; return on; } const was = game.paused; game.paused = true; return was; },
  state: () => {
    const g = game, p = route.at(tram.s), d = new THREE.Vector3(), c = camera.position, r = (v, k = 1) => Math.round(v * k) / k;
    camera.getWorldDirection(d);
    const yaw = Math.atan2(d.x, -d.z), deg = (v) => Math.round((v * 180) / Math.PI);
    const cam = { x: r(c.x, 10), y: r(-c.z, 10), z: r(c.y, 10), yaw: deg(yaw), pitch: deg(Math.asin(d.y)) };
    // (the place in review mode: the camera's target on the ground, seen from above at its heading)
    const tx = c.x + d.x * 20, ty = -c.z - d.z * 20;
    return {
      line: g.line, dataLine: data.line, trip: g.opts.tripIndex, startStop: g.opts.startStop, nextStop: g.stops[g.nextStop]?.name,
      clock: fmtTime(g.clock), weather: g.opts.weather, seed: g.runSeed, obstacles: g.opts.obstacles,
      mode: inspect.active ? 'inspect' : pilot ? 'autopilot' : 'driving',
      tram: { s: r(tram.s, 10), kmh: r(tram.v * 3.6, 10), notch: tram.notch, a: r(tram.a, 100), passengers: tram.passengers,
              x: r(p.x, 10), y: r(p.y, 10), z: r(profile.height(tram.s), 100) },
      camera: cam, ...place(cam.x, cam.y, data.frame.origin),
      review: `?line=${data.line}&review&at=${tx.toFixed(1)},${ty.toFixed(1)},${cam.yaw},45,60`,
      url: location.href, viewport: `${innerWidth}x${innerHeight}@${devicePixelRatio}`, ua: navigator.userAgent,
    };
  },
});

// dev inspect mode: the autopilot drives, time faster or slower, a mouse camera (src/inspect.js)
const inspect = new Inspect({
  camera, canvas, getGame: () => game, getTramModel: () => tramModel,
  onToggle: (on) => {
    if (on && !pilot) { pilot = new Autopilot(); game.autopilot = true; }
    if (on) game.paused = false;
    hud.show(!on);
  },
});
window.inspect = inspect; // (the console and tools/test_free_camera.py, as window.game)

let last = performance.now(), hudTimer = 0, lastDraw = 0;
// An idle page draws 4 frames a second (#149): the menu, a pause, the results, and review mode with its
// camera at rest. Driving, inspect mode and a moving review camera draw every frame; a hidden tab draws
// nothing (requestAnimationFrame stops). The GPU was busy on an idle tab at full frame rate.
const IDLE_MS = 250;
function idle() {
  if (review) return review.resting();
  if (!$('menu').classList.contains('hidden')) return true;
  return !!game && !inspect.active && (game.paused || game.finished);
}
window.drawCount = 0; // (draws so far: tools/test_idle.py)

function frame(now) {
  requestAnimationFrame(frame); // first, so an exception in one frame can't stop the loop
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  // window.headless: a dev tool steps the game itself (tools/traffic_lint.js); only draw
  if (game && !window.headless) {
    const inMenu = !$('menu').classList.contains('hidden');
    const sounding = !inMenu && !game.paused && !game.finished && !(inspect.active && inspect.paused);
    audio.setActive(sounding, !inMenu && !game.paused && game.finished && !(inspect.active && inspect.paused));
    // (inspecting: several game steps per frame, or none while paused)
    const steps = inspect.active ? inspect.steps(dt) : [dt];
    steps.forEach((h, i) => {
      if (pedalKey && !pilot && !game.paused && (pedalKey.t += h) > 0.35) tram.eq.hold(pedalKey.dir, h);
      if (pilot && !game.paused && !game.finished) pilot.step(game, h);
      game.update(h, pilot ? pilot.input : input);
      // (the traffic is posed for drawing on the frame's last step only)
      if (inspect.active && !game.paused && !game.finished) traffic.update(h, camera, i === steps.length - 1);
    });
    game.updateVisuals();
    updateCamera(dt, now / 1000);
    if (inspect.active) inspect.update(dt);
    updateRain(dt);
    updateSnow(dt, now / 1000);
    if (!inspect.active && !game.paused && !game.finished) traffic.update(dt, camera);
    // The shift may have finished during game.update().
    if (game.finished) audio.setActive(false, !inMenu && !game.paused && !(inspect.active && inspect.paused));
    audio.update(tram, game.currentLimit, dt);
    hudTimer -= dt;
    if (hudTimer <= 0 && !inMenu) { hudTimer = 1 / 30; hud.update(game, game.opts); }
    $('action').style.visibility = inMenu ? 'hidden' : '';
    document.body.classList.toggle('shift', !inMenu && !game.finished);
    $('pausePanel').classList.toggle('show', game.paused && !game.finished && !inMenu);
    if (game.finished && !game.resultsShown) {
      game.resultsShown = true;
      const ended = game;
      setTimeout(() => { if (game === ended) showResults(); }, 1500); // not if a new shift started meanwhile
    }
  }
  if (review) review.update(dt);
  // (headless, once a second: every frame, the city drawn in software WebGL took most of a check's CPU,
  // about 9 cores for one page; nothing the checks read depends on drawing, #104)
  const lazy = idle();
  const draw = window.headless ? now - lastDraw > 1000 : !lazy || now - lastDraw > IDLE_MS;
  if (draw) {
    if (people && game) people.sync(camera, traffic, game);
    // (window.headlessDraw false: what a draw does for the checks, the world matrices the lints read, without its
    // pixels; the software draw took 5-12 cores of a page once a second, #411)
    if (window.headless && window.headlessDraw === false) { scene.updateMatrixWorld(); camera.updateMatrixWorld(); }
    else {
      const timing = perfTest?.phase === 'run' && perfTest.timer;
      if (timing) timing.begin();
      renderer.render(scene, camera);
      if (timing) timing.end();
    }
    lastDraw = now; window.drawCount++;
    // (driving only: the menu, a pause and the results draw 4 frames a second, #149)
    if (game && !lazy && !window.headless && !game.paused && !game.finished && !inspect.active) perfLog.frame(now, tram.s, renderer.info.render);
  }
  if (perfTest) perfTestStep(now);
  if (perfOn) updatePerf(now);
  // Present the cached picture even on idle redraws; only active driving refreshes its texture.
  if (draw && game && !chase && mirrorOn && !window.freeCam && !window.headless) {
    mirror.draw(now, !lazy, poseMirror, tramModel);
  }
}

// Right-hand rear-view mirror (by the front door): a small camera outside the cab looking back
// along the side of the set, rendered to a texture and shown mirrored in the frame at the right.
const mirrorHidden = [];
world.traverse(o => {
  // (the overhead wires stay: near the tram they show in a real T3 mirror, and lines are cheap)
  if (o.userData.mirrorDetail) mirrorHidden.push(o);
});
const mirror = new Mirror(renderer, scene, $('mirror'), mirrorHidden);
window.mirror = mirror; // cadence, target and excluded geometry are inspectable without changing the simulation
// It is fixed to the lead car's body (#541): in a curve the body is the chord between its bogies, its front over
// the outside of the track, and it leans in a canted one, so a camera posed from the track turned against it.
const mirrorTurn = new THREE.Quaternion().setFromEuler(new THREE.Euler(-0.04, 0.1, 0, 'YXZ'));
function poseMirror(mirrorCam) {
  const u = tramModel.userData, lead = u.cars[0];
  // 1.55 m right of the centre line, 2.09 m over the rail, at the body's front: 0.6 m behind the coupler's face
  // (the car's frame: x left, y up, z forward from its centre between the bogies, src/consist.js)
  const front = u.kind === 'classic' || u.kind === 'gltf' ? u.bodyFront : T3.length / 2 - 0.6;
  lead.updateWorldMatrix(true, false);
  mirrorCam.position.set(-1.55, 2.09, front).applyMatrix4(lead.matrixWorld);
  // looking back (a camera looks down its -z, the car's rear), turned a little outwards so the side of the tram
  // fills the inner edge, and a little down
  lead.getWorldQuaternion(mirrorCam.quaternion).multiply(mirrorTurn);
}

load.finish();
// review mode (?review, src/review.js): the checks' findings on the map, no shift
let review = null;
if (params.has('review')) {
  review = new Review({ scene, camera, canvas, data, route, ground, world, url: params.get('review'), at: parseAt(params.get('at')) });
  window.review = review;
} else if (params.has('seed') && params.has('at')) replayTo(+params.get('seed'), +params.get('at'));
else {
  $('menu').classList.remove('hidden');
  if (params.has('reftest') && String(data.line) === REF_LINE) startPerfTest(true); // (the reference run, opened from another line)
}
requestAnimationFrame(frame);

// ?seed=N&at=S: the traffic check's run with that seed (tools/traffic_lint.js: the same settings and
// seeded stream, the autopilot driving), stepped without drawing until our tram reaches s, then handed
// over paused with the inspector on: a stuck scene or a reported moment of such a run, as it was (#157)
async function replayTo(seed, at) {
  const { trafficRun } = await import('../tools/traffic_lint.js');
  const t0 = performance.now();
  await trafficRun({ seed, stopAt: at, progress: (msg) => { document.title = msg; } });
  document.title = `Replay: seed ${seed}, s ${Math.round(window.game.tram.s)}`;
  inspect.toggle(true); // (it starts the game running: paused after it)
  inspect.paused = true;
  window.game.paused = true;
  window.game.msg(`Replay of the traffic check, seed ${seed}: s ${Math.round(window.game.tram.s)} after ${((performance.now() - t0) / 1000).toFixed(0)} s`, 'info', 10);
}

// ------------------------------------------------------------------ performance overlay
// Menu option: frames per second, frame time (average and worst over the last second), what the
// renderer drew and the JS heap where the browser reports it (Chromium: performance.memory).
let perfOn = false, perfFrames = 0, perfSince = performance.now(), perfLast = performance.now(), perfWorst = 0;
$('optPerf').addEventListener('change', () => { perfOn = $('optPerf').checked; $('perf').classList.toggle('hidden', !perfOn); });
function updatePerf(now) {
  perfFrames++;
  perfWorst = Math.max(perfWorst, now - perfLast);
  perfLast = now;
  if (now - perfSince < 1000) return;
  const fps = (perfFrames * 1000) / (now - perfSince), info = renderer.info.render, mem = performance.memory;
  $('perf').textContent = `${fps.toFixed(0)} FPS   ${(1000 / fps).toFixed(1)} ms avg   ${perfWorst.toFixed(0)} ms worst\n`
    + `${info.calls} draw calls   ${(info.triangles / 1e6).toFixed(2)} M triangles`
    + (mem ? `\nJS heap ${(mem.usedJSHeapSize / 1e6).toFixed(0)} / ${(mem.jsHeapSizeLimit / 1e6).toFixed(0)} MB` : '');
  perfFrames = 0; perfSince = now; perfWorst = 0;
}
