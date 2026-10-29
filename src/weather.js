// Weather as a state of the materials, not of the geometry: the world is built once in its dry
// colours, and the weather sets a few shared shader uniforms (wet, snow, autumn) and recolours the
// instanced trees. Changing it costs nothing and could happen during a shift.
//   wet:    surfaces darker (a factor per material, in linear colour), rails glossier
//   snow:   white on faces that point up, patchy (noise); streets slushy and thinner; water and
//           vertical faces bare
//   autumn: the terrain's grass and woods and the tree crowns in autumn colours; leaf litter
import * as THREE from 'three';

export const WEATHER_UNIFORMS = {
  uWet: { value: 0 },
  uSnow: { value: 0 },
  uAutumn: { value: 0 },
};

// the look of each weather (the sky and the light are main.js's)
export const WEATHER_LOOK = {
  dry: { wet: 0, snow: 0, autumn: 0 },
  rain: { wet: 1, snow: 0, autumn: 0 },
  leaves: { wet: 1, snow: 0, autumn: 1 },
  snow: { wet: 0.5, snow: 1, autumn: 0 },
};

// GLSL: value noise for the patchy snow, and the snow colour
const NOISE = /* glsl */ `
  float wHash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
  float wNoise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(wHash(i), wHash(i + vec2(1, 0)), u.x), mix(wHash(i + vec2(0, 1)), wHash(i + vec2(1, 1)), u.x), u.y);
  }`;

// Patch a Lambert / Standard material for the weather.
//   wet:   colour factor when wet (linear; 1 = unchanged)
//   snow:  how much snow lies on its upward faces at full snow: 1 ground, ~0.55 streets (driven,
//          ploughed: slush), 0 none
//   slush: snow on it looks like grey slush (carriageways)
//   veg:   the terrain: per-vertex land class (attribute landCls: 0 ground, 1 grass, 2 wood, 3 water):
//          only the bare ground gets wet, grass and woods turn in autumn, water takes no snow
export function weatherize(material, { wet = 1, snow = 0, slush = false, veg = false } = {}) {
  const key = `w${wet.toFixed(2)}s${snow}${slush ? 'l' : ''}${veg ? 'v' : ''}`;
  material.customProgramCacheKey = () => key;
  material.userData.weather = { wet, snow, slush, veg };
  material.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, WEATHER_UNIFORMS);
    if (veg) {
      sh.uniforms.uAutumnGrass = { value: new THREE.Color('#7f8a4c') };
      sh.uniforms.uAutumnWood = { value: new THREE.Color('#8a6a34') };
    }
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', `#include <common>
        varying vec3 vWPos; varying vec3 vWNor;
        ${veg ? 'attribute float landCls; varying float vCls;' : ''}`)
      .replace('#include <project_vertex>', `#include <project_vertex>
        {
          mat4 wm = modelMatrix;
          #ifdef USE_INSTANCING
            wm = modelMatrix * instanceMatrix;
          #endif
          vWPos = (wm * vec4(transformed, 1.0)).xyz;
          vWNor = normalize(mat3(wm) * objectNormal);
          ${veg ? 'vCls = landCls;' : ''}
        }`);
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', `#include <common>
        uniform float uWet; uniform float uSnow; uniform float uAutumn;
        ${veg ? 'uniform vec3 uAutumnGrass; uniform vec3 uAutumnWood; varying float vCls;' : ''}
        varying vec3 vWPos; varying vec3 vWNor;
        ${NOISE}`)
      .replace('#include <color_fragment>', `#include <color_fragment>
        {
          float wetF = ${wet.toFixed(3)}, cover = ${snow.toFixed(3)};
          ${veg ? `
          // land class: bare ground wets, grass and woods turn, water takes no snow
          if (vCls > 0.5 && vCls < 1.5) diffuseColor.rgb = mix(diffuseColor.rgb, uAutumnGrass, uAutumn);
          if (vCls > 1.5 && vCls < 2.5) diffuseColor.rgb = mix(diffuseColor.rgb, uAutumnWood, uAutumn);
          if (vCls > 0.5) wetF = 1.0;
          if (vCls > 2.5) cover = 0.0;` : ''}
          diffuseColor.rgb *= mix(1.0, wetF, uWet);
          // snow: on faces pointing up, in patches (two octaves of noise), thinner on driven streets
          float up = smoothstep(0.45, 0.8, vWNor.y);
          float n = 0.6 * wNoise(vWPos.xz * 0.23) + 0.4 * wNoise(vWPos.xz * 1.9);
          float c = uSnow * up * smoothstep(0.75 - cover, 0.95 - cover, n);
          vec3 snowCol = ${slush ? 'mix(vec3(0.38, 0.39, 0.40), vec3(0.72, 0.74, 0.77), n)' : 'vec3(0.82, 0.85, 0.89)'};
          diffuseColor.rgb = mix(diffuseColor.rgb, snowCol, c);
        }`);
  };
  material.needsUpdate = true;
  return material;
}

// Tree crowns in autumn: a mix of what lines Prague's streets and parks, each tree at its own stage
// (the species and the stage from the tree's index, so the same tree looks the same every time).
// [share, colour of the turned leaves]
// (bright: the crowns are flat-shaded, their sides come out a good deal darker than these)
const SPECIES = [
  [0.32, ['#e6bd3a', '#efcb4a', '#d9ac2e']],            // small-leaved lime (Tilia): yellow
  [0.18, ['#f0a030', '#ebb33c', '#dc5a2a', '#c8442a']], // Norway maple: yellow, orange, some red
  [0.14, ['#bf7a32', '#b0692e', '#c98a3c']],            // horse chestnut: rusty brown, early
  [0.10, ['#cfa64c', '#bd9542']],                       // plane tree: yellow-brown, late
  [0.10, ['#a37838', '#b0843f']],                       // oak, hornbeam: brown
  [0.08, ['#e58c34', '#ec9e3a']],                       // birch, cherry: orange
  [0.08, ['#3f5a2e', '#465f34']],                       // conifers: stay green
];
const GREEN = new THREE.Color('#5d7a35');
const hash = (i, k) => { const x = Math.sin(i * 127.1 + k * 311.7) * 43758.5453; return x - Math.floor(x); };

// the crown colour of tree i: `summer` its own green (kept for the dry and wet weather)
export function crownColor(i, weather, summer, out = new THREE.Color()) {
  if (weather === 'snow') {
    // bare deciduous crowns read as a dark grey-brown haze of twigs; conifers stay dark green
    // (setHSL is in linear colour: l 0.08-0.13 shows as a mid-dark grey-brown)
    const conifer = hash(i, 1) > 1 - SPECIES[6][0];
    return conifer ? out.set('#3b5230') : out.setHSL(0.07 + hash(i, 2) * 0.03, 0.15 + hash(i, 3) * 0.1, 0.08 + hash(i, 4) * 0.05);
  }
  if (weather !== 'leaves') return out.copy(summer);
  let u = hash(i, 1), sp = SPECIES[SPECIES.length - 1];
  for (const s of SPECIES) { if (u < s[0]) { sp = s; break; } u -= s[0]; }
  const turned = new THREE.Color(sp[1][Math.floor(hash(i, 2) * sp[1].length)]);
  if (sp === SPECIES[6]) return out.copy(turned);
  // how far it has turned: most trees well on, some still green, a few nearly done
  const stage = Math.min(1, 0.35 + hash(i, 3) * 0.8);
  out.copy(GREEN).lerp(turned, stage);
  const hsl = {};
  out.getHSL(hsl);
  return out.setHSL(hsl.h, hsl.s, Math.min(0.9, hsl.l * (0.92 + hash(i, 4) * 0.25)));
}

// The share of the crown left on a tree in autumn (crowns thin as leaves fall): a scale factor
export function crownThinning(i, weather) {
  if (weather === 'snow') return 0.8;
  return weather === 'leaves' ? 0.86 + hash(i, 5) * 0.14 : 1;
}

// Fallen leaves: a texture of many small leaves (alpha cut out). crushed: the dark wet mash on the
// rails and in the tram's path.
const leafTex = {};
export function leafTexture(crushed = false) {
  const key = crushed ? 'crushed' : 'fresh';
  if (leafTex[key]) return leafTex[key];
  const S = 256, cv = document.createElement('canvas');
  cv.width = cv.height = S;
  const c = cv.getContext('2d');
  let seed = crushed ? 7 : 3;
  const r = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const fresh = ['#c9a227', '#d98a1c', '#b8901f', '#c0441e', '#9a5a26', '#a8692e', '#d6b335', '#86552c'];
  const mush = ['#4a3418', '#5a3e1c', '#3e2c16', '#6b4a22', '#523a1e'];
  const pal = crushed ? mush : fresh;
  const n = crushed ? 260 : 420;
  for (let i = 0; i < n; i++) {
    // denser towards the middle, so a patch fades out at its edge
    const a = r() * Math.PI * 2, d = Math.sqrt(r()) * S * 0.46 * (0.4 + 0.6 * r());
    const x = S / 2 + Math.cos(a) * d, y = S / 2 + Math.sin(a) * d;
    const len = (crushed ? 9 : 11) + r() * 9, w = len * (0.45 + r() * 0.25);
    c.save();
    c.translate(x, y);
    c.rotate(r() * Math.PI * 2);
    c.fillStyle = pal[Math.floor(r() * pal.length)];
    c.globalAlpha = crushed ? 0.75 : 1;
    c.beginPath();
    if (crushed) c.ellipse(0, 0, len * 0.6, w * 0.6, 0, 0, Math.PI * 2); // shapeless
    else { c.moveTo(-len / 2, 0); c.quadraticCurveTo(0, -w, len / 2, 0); c.quadraticCurveTo(0, w, -len / 2, 0); } // a leaf
    c.fill();
    if (!crushed && r() < 0.6) { // the midrib
      c.strokeStyle = 'rgba(80,50,20,0.5)'; c.lineWidth = 0.8;
      c.beginPath(); c.moveTo(-len / 2, 0); c.lineTo(len / 2, 0); c.stroke();
    }
    c.restore();
  }
  const t = new THREE.CanvasTexture(cv);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  leafTex[key] = t;
  return t;
}

// sRGB colour ratio (dry → wet, as the old weather colours were written) as a linear factor
export const wetFactor = (dryHex, wetHex) => new THREE.Color(wetHex).r / new THREE.Color(dryHex).r;
