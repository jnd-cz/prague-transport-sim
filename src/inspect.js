// Dev tool: inspect mode (?inspect, or the I key during a shift). The autopilot drives while the
// simulation runs faster or slower than real time (several game steps per frame); pause it any time
// and look around with the mouse. Two cameras:
//   orbit - around the tram: drag to turn, wheel to zoom
//   fly   - free: drag to look, W/A/S/D to move, R/F up and down, Shift faster, wheel = flying speed
// Keys (only while inspecting): Space pause, + / - speed, C orbit/fly, T back to the tram,
// PageDown / PageUp (or . / ,) camera to the next / previous stop, I leave.
import * as THREE from 'three';

const SPEEDS = [0.25, 0.5, 1, 2, 4, 8, 16, 32];
const STEP = 1 / 30; // longest game step (s): faster speeds take more steps per frame, not longer ones

export class Inspect {
  constructor({ camera, canvas, getGame, getTramModel, onToggle }) {
    this.camera = camera;
    this.canvas = canvas;
    this.getGame = getGame;
    this.getTramModel = getTramModel;
    this.onToggle = onToggle;
    this.active = false;
    this.paused = false;
    this.speed = 4; // index into SPEEDS: 4x
    this.mode = 'orbit';
    this.yaw = 0; this.pitch = -0.35; this.dist = 45; // orbit around the tram
    this.flyYaw = 0; this.flyPitch = -0.2; this.flySpeed = 20; // fly
    this.held = new Set();
    this.drag = null;
    this.panel = document.createElement('div');
    this.panel.id = 'inspectPanel';
    Object.assign(this.panel.style, {
      position: 'fixed', left: '12px', top: '12px', zIndex: 50, display: 'none', font: '12px/1.45 system-ui, sans-serif',
      color: '#fff', background: 'rgba(20,24,28,0.72)', padding: '8px 10px', borderRadius: '6px', pointerEvents: 'none', whiteSpace: 'pre',
    });
    document.body.appendChild(this.panel);
    const css = document.createElement('style');
    css.textContent = 'body.inspect #cab, body.inspect #mirror, body.inspect #dash, body.inspect #help, body.inspect #action, body.inspect #pausePanel, body.inspect #assist { display: none !important }';
    document.head.appendChild(css);

    canvas.addEventListener('pointerdown', (e) => {
      if (!this.active) return;
      this.drag = { x: e.clientX, y: e.clientY };
      canvas.setPointerCapture(e.pointerId);
    });
    canvas.addEventListener('pointermove', (e) => {
      if (!this.active || !this.drag) return;
      const dx = e.clientX - this.drag.x, dy = e.clientY - this.drag.y;
      this.drag = { x: e.clientX, y: e.clientY };
      if (this.mode === 'orbit') {
        this.yaw -= dx * 0.006;
        this.pitch = Math.max(-1.45, Math.min(0.3, this.pitch - dy * 0.006));
      } else {
        this.flyYaw -= dx * 0.004;
        this.flyPitch = Math.max(-1.5, Math.min(1.5, this.flyPitch - dy * 0.004));
      }
    });
    canvas.addEventListener('pointerup', () => { this.drag = null; });
    canvas.addEventListener('wheel', (e) => {
      if (!this.active) return;
      e.preventDefault();
      const k = Math.exp(e.deltaY * 0.001);
      if (this.mode === 'orbit') this.dist = Math.max(6, Math.min(600, this.dist * k));
      else this.flySpeed = Math.max(2, Math.min(300, this.flySpeed / k));
    }, { passive: false });
    window.addEventListener('keyup', (e) => this.held.delete(e.key.toLowerCase()));
    window.addEventListener('blur', () => this.held.clear());
  }

  toggle(on = !this.active) {
    const g = this.getGame();
    if (!g) return;
    this.active = on;
    window.freeCam = on; // main.js: no cab camera, no mirror
    document.body.classList.toggle('inspect', on);
    this.panel.style.display = on ? 'block' : 'none';
    this.held.clear();
    if (on) {
      // start the orbit behind the tram
      const lead = this.getTramModel().userData.cars[0];
      this.yaw = lead.rotation.y + Math.PI;
      this.paused = false;
    }
    this.onToggle(on);
  }

  // a key while inspecting: true when it was ours (the game does not see it)
  key(e) {
    const k = e.key.toLowerCase();
    if (k === 'i') { this.toggle(false); return true; }
    if (k === ' ') { this.paused = !this.paused; e.preventDefault(); return true; }
    if (k === '+' || k === '=') { this.speed = Math.min(SPEEDS.length - 1, this.speed + 1); return true; }
    if (k === '-' || k === '_') { this.speed = Math.max(0, this.speed - 1); return true; }
    if (k === 'c') { this._setMode(this.mode === 'orbit' ? 'fly' : 'orbit'); return true; }
    if (k === 't') { this._setMode('orbit'); return true; }
    if (k === 'pagedown' || k === '.') { this._toStop(1); e.preventDefault(); return true; }
    if (k === 'pageup' || k === ',') { this._toStop(-1); e.preventDefault(); return true; }
    if (['w', 'a', 's', 'd', 'r', 'f', 'shift'].includes(k)) { this.held.add(k); return true; }
    return ['o', 'p', 'escape', 'v', 'z', 'm'].includes(k) ? false : true; // the rest of the cab controls stay off
  }

  _setMode(m) {
    if (m === 'fly' && this.mode === 'orbit') {
      // fly on from where the orbit camera is, looking the same way
      const dir = new THREE.Vector3();
      this.camera.getWorldDirection(dir);
      this.flyYaw = Math.atan2(-dir.x, -dir.z);
      this.flyPitch = Math.asin(Math.max(-1, Math.min(1, dir.y)));
    }
    this.mode = m;
  }

  // camera to the next (dir 1) or previous stop ahead of / behind the camera, looking at its platform
  _toStop(dir) {
    const g = this.getGame();
    const route = g.route, cam = this.camera.position;
    const here = route.nearest(cam.x, -cam.z)?.s ?? g.tram.s;
    const list = g.stops.map((st) => st.target);
    const s = dir > 0 ? list.find((t) => t > here + 20) : [...list].reverse().find((t) => t < here - 20);
    if (s === undefined) return;
    const p = route.offset(s - 45, -14), q = route.at(s - 15), z = route.ground.profile.height(s - 15);
    this.camera.position.set(p.x, z + 9, -p.y);
    this.camera.lookAt(q.x, z + 1, -q.y);
    this._setMode('fly');
    const d = new THREE.Vector3();
    this.camera.getWorldDirection(d);
    this.flyYaw = Math.atan2(-d.x, -d.z);
    this.flyPitch = Math.asin(d.y);
  }

  // the game steps to run this frame: [] while paused
  steps(dt) {
    if (this.paused) return [];
    const total = dt * SPEEDS[this.speed], n = Math.max(1, Math.ceil(total / STEP));
    return new Array(n).fill(total / n);
  }

  // camera and panel, every frame after the game moved
  update(dt) {
    const g = this.getGame(), cam = this.camera;
    if (this.mode === 'orbit') {
      const lead = this.getTramModel().userData.cars[0], c = lead.position;
      const h = Math.cos(this.pitch) * this.dist;
      cam.position.set(c.x + Math.sin(this.yaw) * h, c.y + 2 - Math.sin(this.pitch) * this.dist, c.z + Math.cos(this.yaw) * h);
      cam.lookAt(c.x, c.y + 2, c.z);
    } else {
      const fast = this.held.has('shift') ? 4 : 1, v = this.flySpeed * fast * dt;
      const fx = -Math.sin(this.flyYaw) * Math.cos(this.flyPitch), fz = -Math.cos(this.flyYaw) * Math.cos(this.flyPitch), fy = Math.sin(this.flyPitch);
      const rx = Math.cos(this.flyYaw), rz = -Math.sin(this.flyYaw);
      if (this.held.has('w')) cam.position.add(new THREE.Vector3(fx * v, fy * v, fz * v));
      if (this.held.has('s')) cam.position.add(new THREE.Vector3(-fx * v, -fy * v, -fz * v));
      if (this.held.has('d')) cam.position.add(new THREE.Vector3(rx * v, 0, rz * v));
      if (this.held.has('a')) cam.position.add(new THREE.Vector3(-rx * v, 0, -rz * v));
      if (this.held.has('r')) cam.position.y += v;
      if (this.held.has('f')) cam.position.y -= v;
      cam.rotation.order = 'YXZ';
      cam.rotation.set(this.flyPitch, this.flyYaw, 0);
    }
    // panel: speed, where the tram and the camera are, the keys
    const st = g.stops[g.nextStop], n = g.route.nearest(cam.position.x, -cam.position.z);
    const sp = SPEEDS[this.speed];
    this.panel.textContent = [
      `INSPECT  ${this.paused ? 'PAUSED' : `${sp < 1 ? `1/${1 / sp}` : sp}× time`}  ·  camera: ${this.mode}`,
      `tram s ${Math.round(g.tram.s)} m · ${(g.tram.v * 3.6).toFixed(0)} km/h · next: ${st ? st.name : '—'}`,
      `camera at s ${n ? Math.round(n.s) : '?'} m, ${n ? Math.round(n.d) : '?'} m from the track`,
      'Space pause · + − speed · C orbit/fly · T tram · PgDn/PgUp next/prev stop · I leave',
      this.mode === 'orbit' ? 'drag: turn around the tram · wheel: zoom' : 'drag: look · WASD move · R/F up/down · Shift fast · wheel: flying speed',
    ].join('\n');
  }
}
