import * as THREE from 'three';
import { Route, extendAlongTracks } from './route.js';
import { Terrain, Profile, makeGround, carveCorridor, bridgeDecks, bridgeModel, DtmSurface, chainTunnels } from './terrain.js';
import { buildWorld, widenTramStreets, WORLD_PARTS, buildStreetDetail } from './world.js';
import { Tram } from './tram.js';
import { Game, fmtTime, fmtDev } from './game.js';
import { Hud } from './hud.js';
import { TramAudio } from './audio.js';
import { makeT3, placeConsist, setConsistLine, loadDetailedT3 } from './models.js';
import { Traffic } from './traffic.js';
import { Autopilot } from './autopilot.js';
import { Inspect } from './inspect.js';
import { spreadTracks } from './trackfix.js';
import { runStreetBot, showBotPanel } from './streetbot.js';
import { t, getLang, setLang, applyStatic, onLangChange, setLine } from './i18n.js';
import { Loader } from './loading.js';
import { createDebugOverlay, builtGeoJSON } from './debugOverlay.js';
import { rng, runSeed } from './random.js';
import { trackStyles } from './heights.js';

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
const T3_FILES = ['assets/t3/t3.gltf', 'assets/t3/t3.bin', 'assets/t3/t3_color.jpg'];
for (const f of ['json', 'geo.json', 'bld.bin', 'dtm.json', 'signals.json', 'dtmpoints.json']) load.prefetch(`data/line${lineId}.${f}`);
if (!params.has('nofine')) load.prefetch(`data/line${lineId}.fine.json`).prefetch(`data/line${lineId}.fine.bin`);
for (const f of T3_FILES) load.prefetch(f);
// (weights: the steps' usual milliseconds on line 17; the bar shares them with the downloads by time)
load.plan([['terrain', 2000], ['profile', 500], ['world', WORLD_PARTS.reduce((a, p) => a + p[1], 0)], ['gpu', 1500], ['tram', 300]]);
const data = await (await load.get(`data/line${lineId}.json`)).json();
data.line = String(data.line);
setLine(data.line);
// optional Geoportál Praha import (tools/geoportal.py): LOD2 buildings, retaining walls, trees
try {
  const geoRes = await load.get(`data/line${lineId}.geo.json`);
  if (geoRes.ok) {
    data.geo = await geoRes.json();
    const bin = await load.get(`data/${data.geo.buildings.file}`);
    if (bin.ok) data.geo.buildings.arr = new Int16Array(await bin.arrayBuffer());
    data.attribution += ' ' + data.geo.attribution;
  }
} catch (e) { console.warn('no Geoportál data', e); }
widenTramStreets(data); // street widths include the tram tracks running down the middle
// optional surveyed streets (Prague DTM, tools/dtm.py) for the districts imported so far
try {
  const r = await load.get(`data/line${lineId}.dtm.json`);
  if (r.ok) { data.dtm = await r.json(); data.attribution += ' ' + data.dtm.attribution; }
} catch { /* not imported for this line */ }
// optional OSM traffic signals (stop lines, signalled crossings; .claude/tools/osm_signals.py for now)
try {
  const r = await load.get(`data/line${lineId}.signals.json`);
  if (r.ok) data.osmSignals = await r.json();
} catch { /* none for this line */ }
// optional street furniture of Prague's technical map (manholes, inlets, hydrants, …; .claude/tools/dtm_points.py)
try {
  const r = await load.get(`data/line${lineId}.dtmpoints.json`);
  if (r.ok) { const j = await r.json(); data.dtmPoints = j.points; data.attribution += ' Street furniture: DTM Praha (archive), data base © IPR Praha (CC BY 4.0).'; }
} catch { /* none for this line */ }
// wait for the rest before the build steps, which block the page
// the user's facts (data/truth.json): track styles set how high top of rail stands over the surface
const truth = await fetch('data/truth.json').then((r) => (r.ok ? r.json() : null)).catch(() => null);
const fineRes = params.has('nofine') ? [] : await Promise.all([load.get(`data/line${lineId}.fine.json`), load.get(`data/line${lineId}.fine.bin`)]);
const t3Res = await Promise.all(T3_FILES.map((f) => load.get(f)));
await load.begin('terrain');
// the two tracks of a double-track line at least 3 m apart (OSM sometimes draws them closer)
// (dev switches for comparing lint runs: ?nospread, ?notunnels)
if (!params.has('nospread')) data.trackSpread = spreadTracks(data);
if (params.has('notunnels')) data.roads = data.roads.filter((r) => !r.t);
chainTunnels(data.roads); // road tunnels and bridges: heights between their real portals / abutments
// the track beyond both termini, so a two-car set standing at the first stop is on rails
const route = new Route(data.path, extendAlongTracks(data.tracks, data.path, 60));
route.speedInfo = data.speed || null; // posted speeds and dedicated track (tools/osm_speeds.py)
// banked curves on dedicated track; level at platforms (stop zone from the stop sign back 30 m
// where the data has no platform)
route.prepareCant(data.stops.map((st) => ({ p0: st.p0 ?? st.s - 30, p1: st.p1 ?? st.s })));
const terrain = new Terrain(data.terrain);
// the fine terrain near the tracks (2 m, tools/fine_terrain.py), where it was made for this line
// (dev switch ?nofine: the coarse grid only, for comparing lint runs)
if (!params.has('nofine')) try {
  const [mr, br] = fineRes;
  if (mr.ok && br.ok) {
    const meta = await mr.json();
    terrain.addFine(meta, new Int16Array(await br.arrayBuffer()));
    data.attribution += ' ' + meta.attribution;
  }
} catch { /* not made for this line */ }
const dtm = data.dtm ? new DtmSurface(data.dtm, terrain, THREE) : null;
await load.begin('profile');
// real bridge decks under the track (Geoportál Mosty 3D) set the track height there
const styles = trackStyles(truth, data, dtm ? (s) => { const p = route.at(s); return dtm.classAt(p.x, p.y); } : null, route.length);
const profile = new Profile(route, terrain, data.bridges, data.tunnels || [], bridgeDecks(data.geo, route, terrain, data.bridges), dtm, data.clearances || [], styles.lift);
const ground = makeGround(route, terrain, profile, dtm);
ground.styles = styles;
ground.model = bridgeModel(data.geo); // the Mosty 3D decks anywhere (bridge ways off the route)
ground.walls = carveCorridor(terrain, route, profile, dtm); // flatten the track bench, retaining walls
route.ground = ground;

// ------------------------------------------------------------------ renderer & scene
const canvas = $('gl');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, logarithmicDepthBuffer: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
// Out of GPU memory (or the GPU reset), the browser drops the WebGL context. The world's geometry is no
// longer kept in JS after upload (uploadWorld), so it cannot be rebuilt here: say so and offer a reload
// instead of a frozen black screen.
canvas.addEventListener('webglcontextlost', (e) => {
  e.preventDefault();
  if (game) game.paused = true;
  const card = $('resultsCard');
  card.innerHTML = `<h1>${t('gl.lost')}</h1><p>${t('gl.lostWhy')}</p><button class="primary" id="glReload">${t('gl.reload')}</button>`;
  $('results').classList.remove('hidden');
  $('glReload').onclick = () => location.reload();
});
const scene = new THREE.Scene();
const debugOverlay = createDebugOverlay(scene);
const sky = new THREE.Color('#b9cfe0');
scene.background = sky;
scene.fog = new THREE.Fog(sky, 180, 950);
const camera = new THREE.PerspectiveCamera(62, 1, 0.3, 1600);
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
// detailed T3 model (Sketchfab, CC BY-NC 4.0); the built-in low-poly one is the fallback
let detailedOk = false;
const t3Blobs = {};
const T3_TYPES = { gltf: 'model/gltf+json', bin: 'application/octet-stream', jpg: 'image/jpeg' };
for (const r of t3Res) if (r.ok) t3Blobs[r.url] = r.blobUrl(T3_TYPES[r.url.split('.').pop()]);
try { await loadDetailedT3(T3_FILES[0], t3Blobs); detailedOk = true; data.attribution += ' Tatra T3 3D model: "Tatra T3" by Jakub Vaja (conflig), sketchfab.com, CC BY-NC 4.0 (simplified).'; }
catch (e) { console.warn('detailed T3 model not loaded', e); }
const useDetailed = () => detailedOk && $('optModel').value === 'detailed';
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
let tramModel = makeT3({ line: data.line, cars: lineCars, detailed: detailedOk, dest: lastStop, run: runNumber(0) });
scene.add(tramModel);

const hud = new Hud();
const audio = new TramAudio();
let tram = new Tram();
let game = null;
let traffic = null;
let pilot = null; // autopilot driving the tram (watch the ride), or null
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
onLangChange(() => { menuTexts(); const v = selTrip.value; fillTrips(); selTrip.value = v; });
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

$('btnStart').addEventListener('click', start);

function start() {
  audio.start();
  const cars = $('optCars').value === 'auto' ? lineCars : +$('optCars').value;
  tram = new Tram(cars);
  if (tramModel.userData.cars.length !== cars || !!tramModel.userData.mats.body !== useDetailed()) {
    scene.remove(tramModel);
    tramModel = makeT3({ line: data.line, cars, detailed: useDetailed(), dest: lastStop, run: runNumber(0) });
    scene.add(tramModel);
  }
  if (game) scene.remove(game.objects);
  // one seeded stream for the whole run (rules and traffic), apart from Math.random
  const seed = runSeed(), random = rng(seed);
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
    detailed: useDetailed(),
    seed: Math.floor(random() * 1e9),
  });
  game.runSeed = seed; // (replay: ?seed=N)
  // the line number shown on the tram, the top bar and in messages follows the run
  const showLine = (l) => { $('line').textContent = l; setLine(l); setConsistLine(tramModel, l, game.destination, runNumber(game.opts.tripIndex)); };
  showLine(game.line);
  game.onLineChange = showLine;
  if (traffic) traffic.dispose();
  traffic = new Traffic(scene, data, route, ground, game, random);
  debugOverlay.reset();
  pilot = $('optAuto').checked ? new Autopilot() : null;
  game.autopilot = !!pilot;
  window.game = game; // handy for debugging from the console
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
    <button class="primary" id="again">${t('res.again')}</button>`;
  $('results').classList.remove('hidden');
  $('again').onclick = () => { $('results').classList.add('hidden'); $('menu').classList.remove('hidden'); };
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
window.addEventListener('keydown', (e) => {
  if (!game || game.finished || !$('menu').classList.contains('hidden')) return;
  const k = e.key.toLowerCase();
  // dev overlay of signals, stop lines, conflicts and platforms (src/debugOverlay.js; ?debug shows it at the start)
  if (k === 'f8' && !e.repeat) { e.preventDefault(); debugOverlay.toggle(game, traffic); return; }
  // dev inspect mode (src/inspect.js): its keys first
  if (inspect.active ? inspect.key(e) : k === 'i' && !e.repeat && (inspect.toggle(true), true)) return;
  if (k === 'o' && !e.repeat) {
    pilot = pilot ? null : new Autopilot();
    game.autopilot = !!pilot;
    game.msg(t(pilot ? 'msg.autoOn' : 'msg.autoOff'), 'info', 4);
    return;
  }
  // touching the controller or the doors takes over from the autopilot
  if (pilot && ['w', 's', 'arrowup', 'arrowdown', ' ', 'n', 'd'].includes(k)) {
    pilot = null;
    game.autopilot = false;
    game.msg(t('msg.autoOff'), 'info', 4);
  }
  if (e.key === 'Shift') input.deadman = true;
  if (k === 'a') input.sand = true;
  if (k === 'c') input.cutout = true;     // heating cut-out button (pass a contact coasting in winter)
  if (k === 'y') input.switchBtn = true;  // "Výhybka" button: current through the contact
  if (['arrowup', 'arrowdown', ' '].includes(k)) e.preventDefault();
  if (k === 'p' || k === 'escape') { game.paused = !game.paused; return; }
  if (game.paused) return;
  if (e.repeat && k !== 'w' && k !== 's' && k !== 'arrowup' && k !== 'arrowdown') return;
  const prev = tram.notch;
  switch (k) {
    case 'w': case 'arrowup': if (tram.notch === -5) tram.notch = -4; else tram.notch = Math.min(4, tram.notch + 1); break;
    case 's': case 'arrowdown': tram.notch = Math.max(-4, tram.notch - 1); break;
    case ' ': tram.notch = -5; break;
    case 'n': tram.notch = 0; break;
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
  if (tram.notch > 0 && game.doorState !== 'closed') {
    tram.notch = prev > 0 ? prev : 0;
    if (prev <= 0) { audio.warning(); game.msg(t('msg.closeDoors'), 'warn'); }
  }
  if (tram.notch !== prev) audio.click(0.12, 1600);
});
window.addEventListener('keyup', (e) => {
  if (e.key === 'Shift') input.deadman = false;
  const ku = e.key.toLowerCase();
  if (ku === 'a') input.sand = false;
  if (ku === 'c') input.cutout = false;
  if (ku === 'y') input.switchBtn = false;
  if (['q', 'e', 'arrowleft', 'arrowright'].includes(ku)) lookTarget = 0;
  if (e.key === ' ' && tram.notch === -5) tram.notch = -4;
});
window.addEventListener('blur', () => { if (game && !game.finished && !pilot) game.paused = true; }); // keep riding on autopilot

// ------------------------------------------------------------------ camera & loop
const camPos = new THREE.Vector3(), camLook = new THREE.Vector3();
let yaw = null;

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
}

function updateCamera(dt, t) {
  const s = tram.s;
  placeTram(s);
  if (window.freeCam) { tramModel.visible = true; return; } // debugging: camera set from the console
  tramModel.visible = chase;
  if (chase) {
    // behind and above the tram body (works also at the very start of the route)
    const lead = tramModel.userData.cars[0], back = 20 + (tramModel.userData.cars.length - 1) * 8;
    const fx = Math.sin(lead.rotation.y), fz = Math.cos(lead.rotation.y);
    camPos.set(lead.position.x - fx * back - fz * 3, lead.position.y + 8.5, lead.position.z - fz * back + fx * 3);
    const q = route.at(s + 10);
    camLook.set(q.x, profile.height(s + 10) + 1.5, -q.y);
    camera.position.lerp(camPos, Math.min(1, dt * 4));
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

// dev inspect mode: the autopilot drives, time faster or slower, a mouse camera (src/inspect.js)
const inspect = new Inspect({
  camera, canvas, getGame: () => game, getTramModel: () => tramModel,
  onToggle: (on) => {
    if (on && !pilot) { pilot = new Autopilot(); game.autopilot = true; }
    if (on) game.paused = false;
    hud.show(!on);
  },
});

let last = performance.now(), hudTimer = 0, lastDraw = 0;
function frame(now) {
  requestAnimationFrame(frame); // first, so an exception in one frame can't stop the loop
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  // window.headless: a dev tool steps the game itself (tools/traffic_lint.js); only draw
  if (game && !window.headless) {
    // (inspecting: several game steps per frame, or none while paused)
    const steps = inspect.active ? inspect.steps(dt) : [dt];
    steps.forEach((h, i) => {
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
    audio.update(tram, game.currentLimit, dt);
    hudTimer -= dt;
    const inMenu = !$('menu').classList.contains('hidden');
    if (hudTimer <= 0 && !inMenu) { hudTimer = 1 / 30; hud.update(game, game.opts); }
    $('action').style.visibility = inMenu ? 'hidden' : '';
    $('pausePanel').classList.toggle('show', game.paused && !game.finished && !inMenu);
    if (game.finished && !game.resultsShown) {
      game.resultsShown = true;
      const ended = game;
      setTimeout(() => { if (game === ended) showResults(); }, 1500); // not if a new shift started meanwhile
    }
  }
  // (headless, once a second: every frame, the city drawn in software WebGL took most of a check's CPU,
  // about 9 cores for one page; nothing the checks read depends on drawing, #104)
  if (!window.headless || now - lastDraw > 1000) { renderer.render(scene, camera); lastDraw = now; }
  if (perfOn) updatePerf(now);
  if (game && !chase && mirrorOn && !window.freeCam && !window.headless) renderMirror(); // (not while a test steps the game)
}

// Right-hand rear-view mirror (by the front door): a small camera outside the cab looking back
// along the side of the set, rendered to a texture and shown mirrored in the frame at the right.
const mirrorCam = new THREE.PerspectiveCamera(30, 150 / 190, 0.3, 700);
const mirrorRT = new THREE.WebGLRenderTarget(240, 304);
const mirrorScene = new THREE.Scene(), mirrorView = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
{
  const g = new THREE.PlaneGeometry(2, 2), uv = g.attributes.uv;
  for (let i = 0; i < uv.count; i++) uv.setX(i, 1 - uv.getX(i)); // a mirror shows it the other way round
  mirrorScene.add(new THREE.Mesh(g, new THREE.MeshBasicMaterial({ map: mirrorRT.texture })));
}
function renderMirror() {
  const s = tram.s, p = route.offset(s - 0.6, -1.55), h = route.heading(s - 6, 6), z = profile.height(s);
  mirrorCam.position.set(p.x, z + 2.09, -p.y);
  // looking back, turned a little outwards so the side of the tram fills the inner edge
  mirrorCam.rotation.order = 'YXZ';
  mirrorCam.rotation.set(-0.04, Math.atan2(-h.hx, h.hy) + Math.PI + 0.1, 0);
  const vis = tramModel.visible;
  tramModel.visible = true;
  renderer.setRenderTarget(mirrorRT);
  renderer.render(scene, mirrorCam);
  renderer.setRenderTarget(null);
  tramModel.visible = vis;
  const r = $('mirror').getBoundingClientRect(), H = window.innerHeight;
  renderer.setViewport(r.left + 6, H - r.bottom + 6, r.width - 12, r.height - 12);
  renderer.setScissor(r.left + 6, H - r.bottom + 6, r.width - 12, r.height - 12);
  renderer.setScissorTest(true);
  renderer.autoClear = false;
  renderer.render(mirrorScene, mirrorView);
  renderer.autoClear = true;
  renderer.setScissorTest(false);
  renderer.setViewport(0, 0, window.innerWidth, window.innerHeight);
}

load.finish();
$('menu').classList.remove('hidden');
requestAnimationFrame(frame);

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
