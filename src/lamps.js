// The lamps' common parts (#436), for every tram model: the indicators' rhythm and the high beams' glow.
// What is lit when (the user, 2026-11-10, #436): the dipped headlights and the tail lamps whenever a tram is
// in service ("off only when the car is turned off"), the brake lamps while it brakes, the indicators before a
// turn at a junction and at a stop where passengers cross a car lane (the right ones, from braking into it until
// it pulls away), the high beams flashed as a warning or on at night on dark stretches.
import * as THREE from 'three';

// the indicators blink 1.5 times a second, lit half of it (UN ECE R48: 90 +- 30 flashes a minute)
export const BLINK_HZ = 1.5;
// the sides lit at time t (s) for an indicator state: 'left', 'right', 'hazard' or none
export function signalsAt(indicate, t) {
  const on = !!indicate && ((t * BLINK_HZ) % 1 + 1) % 1 < 0.5;
  return { left: on && indicate !== 'right', right: on && indicate !== 'left' };
}

// The high beams by day: a soft glow over each headlight (an additive radial gradient, so it brightens what is
// behind it and has no edge), drawn only while they are on. `points`: the headlights' centres in the car's frame,
// facing +z.
let glow = null;
function glowTexture() {
  if (glow) return glow;
  const cv = document.createElement('canvas');
  cv.width = cv.height = 64;
  const g = cv.getContext('2d'), r = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  r.addColorStop(0, 'rgba(255,255,255,1)'); r.addColorStop(0.25, 'rgba(255,250,235,0.85)');
  r.addColorStop(0.6, 'rgba(255,240,210,0.25)'); r.addColorStop(1, 'rgba(255,240,210,0)');
  g.fillStyle = r; g.fillRect(0, 0, 64, 64);
  glow = new THREE.CanvasTexture(cv);
  glow.colorSpace = THREE.SRGBColorSpace;
  glow.userData.shared = true;
  return glow;
}
export function beamsMesh(points, size = 0.75) {
  const g = new THREE.BufferGeometry(), pos = [], uv = [], idx = [];
  for (const [x, y, z] of points) {
    const i = pos.length / 3, h = size / 2;
    pos.push(x - h, y - h, z, x + h, y - h, z, x + h, y + h, z, x - h, y + h, z);
    uv.push(0, 0, 1, 0, 1, 1, 0, 1);
    idx.push(i, i + 1, i + 2, i, i + 2, i + 3);
  }
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.setIndex(idx);
  const m = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ map: glowTexture(), transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }));
  m.name = 'beams';
  m.visible = false;
  return m;
}
