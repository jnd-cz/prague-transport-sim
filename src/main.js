import * as THREE from 'three';
import { Route } from './route.js';
import { Terrain, Profile, makeGround, carveCorridor } from './terrain.js';
import { buildWorld } from './world.js';
import { Tram, T3 } from './tram.js';
import { Game, fmtTime, fmtDev } from './game.js';
import { Hud } from './hud.js';
import { TramAudio } from './audio.js';
import { makeT3 } from './models.js';
import { Traffic } from './traffic.js';
import { Autopilot } from './autopilot.js';
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
const route = new Route(data.path);
const terrain = new Terrain(data.terrain);
const profile = new Profile(route, terrain, data.bridges, data.tunnels || []);
const ground = makeGround(route, terrain, profile);
ground.walls = carveCorridor(terrain, route, profile); // flatten the track bench, retaining walls
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
const tramModel = makeT3({ line: data.line });
tramModel.rotation.order = 'YXZ';
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
  selLine.add(new Option(`${l.line}: ${l.from} → ${l.to}`, l.line));
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
  tram = new Tram();
  if (game) scene.remove(game.objects);
  const weather = $('optWeather').value;
  if (weather !== worldWeather) {
    $('loading').classList.remove('hidden');
  }
  applyWeather(weather);
  $('loading').classList.add('hidden');
  game = new Game(scene, data, route, tram, audio, {
    weather,
    autoIrc: $('optAutoIrc').checked,
    tripIndex: +selTrip.value,
    startStop: +selStop.value,
    assist: $('optAssist').checked,
    deadman: $('optDeadman').checked,
    obstacles: $('optObst').value,
    seed: Math.floor(Math.random() * 1e9),
  });
  if (traffic) traffic.dispose();
  traffic = new Traffic(scene, data, route, ground, game, Math.random);
  pilot = $('optAuto').checked ? new Autopilot() : null;
  game.autopilot = !!pilot;
  window.game = game; // handy for debugging from the console
  window.traffic = traffic;
  $('menu').classList.add('hidden');
  $('results').classList.add('hidden');
  hud.show(true);
  game.msg(t('msg.shiftStart', { stop: game.stops[game.nextStop].name, time: fmtTime(game.stops[game.nextStop].sched).slice(0, 5) }), 'info', 7);
}

function showResults() {
  hud.show(false);
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

// ------------------------------------------------------------------ input
const input = { deadman: false, sand: false };
window.addEventListener('keydown', (e) => {
  if (!game || game.finished) return;
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
    case 'q': game.irc('left'); break;
    case 'r': game.irc('straight'); break;
    case 'e': game.irc('right'); break;
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
  if (e.key.toLowerCase() === 'a') input.sand = false;
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
  // body rests on its two bogies, so it pitches with the gradient
  const a = route.at(s - 3.2), b = route.at(s - 10.8);
  const za = profile.height(s - 3.2), zb = profile.height(s - 10.8);
  tramModel.position.set((a.x + b.x) / 2, (za + zb) / 2 + 0.3, -(a.y + b.y) / 2);
  tramModel.rotation.y = Math.atan2(a.x - b.x, -(a.y - b.y));
  tramModel.rotation.x = -Math.atan2(za - zb, 7.6);
}

function updateCamera(dt, t) {
  const s = tram.s;
  placeTram(s);
  tramModel.visible = chase;
  if (chase) {
    // behind and above the tram body (works also at the very start of the route)
    const fx = Math.sin(tramModel.rotation.y), fz = Math.cos(tramModel.rotation.y);
    camPos.set(tramModel.position.x - fx * 20 - fz * 3, tramModel.position.y + 8.5, tramModel.position.z - fz * 20 + fx * 3);
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
  // the cab pitches with the track (bogie-to-bogie slope) plus a little load transfer
  const slope = Math.atan2(profile.height(s - 3.2) - profile.height(s - 10.8), 7.6);
  const pitch = -0.035 - tram.a * 0.006 + slope;
  camera.position.set(eye.x, profile.height(s - 1.4) + 2.65 + bob, -eye.y);
  camera.rotation.set(0, 0, 0);
  camera.rotation.order = 'YXZ';
  camera.rotation.y = -yaw;
  camera.rotation.x = pitch;
  camera.rotation.z = Math.sin(t * 1.3) * 0.002 * Math.min(1, tram.v / 8);
}

let last = performance.now(), hudTimer = 0;
function frame(now) {
  requestAnimationFrame(frame); // first, so an exception in one frame can't stop the loop
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  if (game) {
    if (pilot && !game.paused && !game.finished) pilot.step(game, dt);
    game.update(dt, pilot ? pilot.input : input);
    game.updateVisuals();
    updateCamera(dt, now / 1000);
    updateRain(dt);
    if (!game.paused && !game.finished) traffic.update(dt, camera);
    audio.update(tram, game.currentLimit, dt);
    hudTimer -= dt;
    if (hudTimer <= 0) { hudTimer = 1 / 30; hud.update(game, game.opts); }
    if (game.finished && !game.resultsShown) {
      game.resultsShown = true;
      const ended = game;
      setTimeout(() => { if (game === ended) showResults(); }, 1500); // not if a new shift started meanwhile
    }
  }
  renderer.render(scene, camera);
}

$('loading').classList.add('hidden');
$('menu').classList.remove('hidden');
requestAnimationFrame(frame);
