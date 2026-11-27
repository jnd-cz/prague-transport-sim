// SPDX-License-Identifier: AGPL-3.0-or-later
// Landmarks past the fog (#610). The user, 2026-11-15: "hide the small things far away and on the opposite keep the
// largest building on higher ground so that they can be see as visual landmarks, like in real city".
// The camera draws to the fog's end (src/main.js applyWeather); a landmark is drawn beyond it, in a lighter haze that
// ends LANDMARK_STRETCH times farther. Its own meshes in the world (src/buildings.js buildLod2) take that haze near the
// camera, and a copy of its triangles is drawn first, in a pass of its own from just inside the far plane to the
// haze's end; the world is then drawn over it. A hill in front of a landmark past the fog's end is drawn in the sky's
// colour, as all the ground there, and covers the landmark's foot.
import * as THREE from 'three';

// which buildings (src/buildings.js buildLod2): LANDMARK_TALL m and higher (line 17: 45 buildings of 2080 over 12 m,
// 37: 15 of 1276, 9: 40 of 4784; 2026-11-15), or LANDMARK_HIGH m and higher standing LANDMARK_RISE m or more over
// the line's typical ground, the median of the ground along its route (17: +12 at Barrandov, 9: +61, Řepy's panel
// blocks at 355 m; 37: none)
export const LANDMARK_TALL = 40, LANDMARK_HIGH = 30, LANDMARK_RISE = 60;
export const LANDMARK_STRETCH = 5; // the landmarks' haze ends this many times farther than the fog
export const LANDMARK_UNIFORMS = { uLandmarkFar: { value: 950 * LANDMARK_STRETCH } };

// a material's fog made the landmarks' haze: from the fog's start to LANDMARK_UNIFORMS' end
export function landmarkHaze(material) {
  // (the key asked each time: a weatherized material's changes when the snow comes or goes, src/weather.js)
  const prev = material.onBeforeCompile, key = material.customProgramCacheKey.bind(material);
  material.onBeforeCompile = (sh, r) => {
    prev.call(material, sh, r);
    Object.assign(sh.uniforms, LANDMARK_UNIFORMS);
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', '#include <common>\nuniform float uLandmarkFar;')
      .replace('#include <fog_fragment>', `#ifdef USE_FOG
        gl_FragColor.rgb = mix(gl_FragColor.rgb, fogColor, smoothstep(fogNear, uLandmarkFar, vFogDepth));
      #endif`);
  };
  material.customProgramCacheKey = () => `${key()}|landmark`;
  return material;
}

// the mean linear colour of a canvas texture (a facade tile): the copy past the far plane has no texture
const means = new Map();
export function textureMean(tex) {
  if (!tex?.image?.getContext) return 1;
  if (means.has(tex)) return means.get(tex);
  const { width: w, height: h } = tex.image, d = tex.image.getContext('2d').getImageData(0, 0, w, h).data;
  let sum = 0;
  const lin = Array.from({ length: 256 }, (_, v) => { const c = v / 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; });
  for (let i = 0; i < d.length; i += 4) for (let k = 0; k < 3; k++) sum += lin[d[i + k]];
  const m = sum / (w * h * 3);
  means.set(tex, m);
  return m;
}

// The pass past the far plane: one mesh of every landmark's triangles (position, normal, colour), its own lights
// following the world's.
export class Landmarks {
  constructor(pos, nor, col, lights, list = []) {
    this.list = list; // [x, y, height, base] of each landmark building
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera();
    this.lights = lights.map((l) => { const c = l.clone(); this.scene.add(c); return [l, c]; });
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
    g.computeBoundingSphere();
    const mat = new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide });
    mat.customProgramCacheKey = () => 'landmark-far';
    this.mesh = new THREE.Mesh(g, landmarkHaze(mat));
    this.mesh.matrixAutoUpdate = false;
    this.scene.add(this.mesh);
    this.triangles = pos.length / 9;
  }

  // the sky and the landmarks past camera.far; the caller then draws the world without clearing the colour
  render(renderer, scene, camera) {
    for (const [l, c] of this.lights) { c.color.copy(l.color); c.intensity = l.intensity; c.position.copy(l.position); if (l.groundColor) c.groundColor.copy(l.groundColor); }
    const cam = this.camera;
    cam.fov = camera.fov; cam.aspect = camera.aspect; cam.zoom = camera.zoom;
    cam.near = camera.far * 0.97; cam.far = LANDMARK_UNIFORMS.uLandmarkFar.value;
    cam.updateProjectionMatrix();
    camera.updateMatrixWorld(); // (drawn before the world's own render updates it)
    camera.matrixWorld.decompose(cam.position, cam.quaternion, cam.scale);
    this.scene.background = scene.background;
    this.scene.fog = scene.fog;
    renderer.render(this.scene, cam);
  }
}
