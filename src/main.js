import * as THREE from 'three';
import { Route, extendAlongTracks } from './route.js';
import { Terrain, Profile, makeGround, carveCorridor, bridgeDecks, DtmSurface } from './terrain.js';
import { buildWorld, widenTramStreets } from './world.js';
import { Tram } from './tram.js';
import { Game, fmtTime, fmtDev } from './game.js';
import { Hud } from './hud.js';
import { TramAudio } from './audio.js';
import { makeT3, placeConsist, setConsistLine, loadDetailedT3 } from './models.js';
import { Traffic } from './traffic.js';
import { Autopilot } from './autopilot.js';
import { runStreetBot, showBotPanel } from './streetbot.js';
import { t, getLang, setLang, applyStatic, onLangChange, setLine } from './i18n.js';

const $ = (id) => document.getElementById(id);

// line selection: ?line=N, else the last one played
let lines = [];
try { lines = await (await fetch('data/lines.json')).json(); } catch { /* single-line build */ }
const params = new URLSearchParams(location.search);
let lineId = params.get('line');
try { lineId = lineId || localStorage.getItem('tram.line'); } catch { /* storage unavailable */ }
if (!lineId || (lines.length && !lines.some((l) => l.line === lineId))) lineId = lines[0]?.line || '22';
const data = await (await fetch(`data/line${lineId}.json`)).json();
data.line = String(data.line);
setLine(data.line);
// optional Geoportál Praha import (tools/geoportal.py): LOD2 buildings, retaining walls, trees
try {
  const geoRes = await fetch(`data/line${lineId}.geo.json`);
  if (geoRes.ok) {
    data.geo = await geoRes.json();
    const bin = await fetch(`data/${data.geo.buildings.file}`);
    if (bin.ok) data.geo.buildings.arr = new Int16Array(await bin.arrayBuffer());
    data.attribution += ' ' + data.geo.attribution;
  }
} catch (e) { console.warn('no Geoportál data', e); }
widenTramStreets(data); // street widths include the tram tracks running down the middle
// optional surveyed streets (Prague DTM, tools/dtm.py) for the districts imported so far
try {
  const r = await fetch(`data/line${lineId}.dtm.json`);
  if (r.ok) { data.dtm = await r.json(); data.attribution += ' ' + data.dtm.attribution; }
} catch { /* not imported for this line */ }
// the track beyond both termini, so a two-car set standing at the first stop is on rails
const route = new Route(data.path, extendAlongTracks(data.tracks, data.path, 60));
route.speedInfo = data.speed || null; // posted speeds and dedicated track (tools/osm_speeds.py)
// banked curves on dedicated track; level at platforms (stop zone from the stop sign back 30 m
// where the data has no platform)
route.prepareCant(data.stops.map((st) => ({ p0: st.p0 ?? st.s - 30, p1: st.p1 ?? st.s })));
const terrain = new Terrain(data.terrain);
const dtm = data.dtm ? new DtmSurface(data.dtm, terrain, THREE) : null;
// real bridge decks under the track (Geoportál Mosty 3D) set the track height there
const profile = new Profile(route, terrain, data.bridges, data.tunnels || [], bridgeDecks(data.geo, route, terrain), dtm);
const ground = makeGround(route, terrain, profile, dtm);
ground.walls = carveCorridor(terrain, route, profile, dtm); // flatten the track bench, retaining walls
route.ground = ground;

// ------------------------------------------------------------------ renderer & scene
const canvas = $('gl');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, logarithmicDepthBuffer: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
const scene = new THREE.Scene();
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
};
let world = null, worldWeather = null;
const rain = makeRain();
scene.add(rain);

function applyWeather(w) {
  const cfg = WEATHER[w];
  sky.set(cfg.sky);
  scene.fog.color.set(cfg.sky);
  [scene.fog.near, scene.fog.far] = cfg.fog;
  sun.intensity = cfg.sun;
  hemi.intensity = cfg.hemi;
  rain.visible = w === 'rain';
  if (worldWeather !== w) {
    if (world) {
      scene.remove(world);
      world.traverse((o) => { if (o.geometry) o.geometry.dispose(); });
    }
    world = buildWorld(scene, data, route, ground, w);
    window.world = world; // read by the lints (tools/lint.js)
    worldWeather = w;
  }
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

applyWeather('dry');
// detailed T3 model (Sketchfab, CC BY-NC 4.0); the built-in low-poly one is the fallback
let detailedOk = false;
try { await loadDetailedT3(); detailedOk = true; data.attribution += ' Tatra T3 3D model: "Tatra T3" by Jakub Vaja (conflig), sketchfab.com, CC BY-NC 4.0 (simplified).'; }
catch (e) { console.warn('detailed T3 model not loaded', e); }
const useDetailed = () => detailedOk && $('optModel').value === 'detailed';
// the T3 ran in two-car sets on most lines; line 23 is the single-car heritage line
const lineCars = data.line === '23' ? 1 : 2;
let tramModel = makeT3({ line: data.line, cars: lineCars, detailed: detailedOk });
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
    tramModel = makeT3({ line: data.line, cars, detailed: useDetailed() });
    scene.add(tramModel);
  }
  if (game) scene.remove(game.objects);
  const weather = $('optWeather').value;
  if (weather !== worldWeather) {
    $('loading').classList.remove('hidden');
  }
  applyWeather(weather);
  $('loading').classList.add('hidden');
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
    seed: Math.floor(Math.random() * 1e9),
  });
  // the line number shown on the tram, the top bar and in messages follows the run
  const showLine = (l) => { $('line').textContent = l; setLine(l); setConsistLine(tramModel, l); };
  showLine(game.line);
  game.onLineChange = showLine;
  if (traffic) traffic.dispose();
  traffic = new Traffic(scene, data, route, ground, game, Math.random);
  pilot = $('optAuto').checked ? new Autopilot() : null;
  game.autopilot = !!pilot;
  window.game = game; // handy for debugging from the console
  window.camera = camera;
  window.traffic = traffic;
  window.tramModel = tramModel;
  $('menu').classList.add('hidden');
  $('results').classList.add('hidden');
  hud.show(true);
  $('mirror').classList.remove('hidden');
  game.msg(t('msg.shiftStart', { stop: game.stops[game.nextStop].name, time: fmtTime(game.stops[game.nextStop].sched).slice(0, 5) }), 'info', 7);
  if (params.has('bot')) streetBot();
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
  camera.position.set(eye.x + lx, profile.height(s - 1.4) + 2.65 + bob, -(eye.y + ly));
  camera.rotation.set(0, 0, 0);
  camera.rotation.order = 'YXZ';
  camera.rotation.y = -yaw + look;
  camera.rotation.x = pitch;
  // sway, and the lean into a canted curve
  camera.rotation.z = Math.sin(t * 1.3) * 0.002 * Math.min(1, tram.v / 8) + route.rollAt(s - 3);
}

let last = performance.now(), hudTimer = 0;
function frame(now) {
  requestAnimationFrame(frame); // first, so an exception in one frame can't stop the loop
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  // window.headless: a dev tool steps the game itself (tools/traffic_lint.js); only draw
  if (game && !window.headless) {
    if (pilot && !game.paused && !game.finished) pilot.step(game, dt);
    game.update(dt, pilot ? pilot.input : input);
    game.updateVisuals();
    updateCamera(dt, now / 1000);
    updateRain(dt);
    if (!game.paused && !game.finished) traffic.update(dt, camera);
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
  renderer.render(scene, camera);
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
  mirrorCam.position.set(p.x, z + 2.35, -p.y);
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

$('loading').classList.add('hidden');
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
