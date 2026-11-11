// The rigged loader (#467, the first step of #456's vehicle interface): any glTF vehicle whose manifest names a rig
// (loader 'gltf-rigged', docs/vehicles.md "The rig"), driven by its parts' names alone. The hybrid T3 (assets/t3h/)
// was its first, with code of its own (src/t3h.js until #467); what that code knew of the one asset is its rig's now.
// Loaded once per vehicle into a car template:
// - the parts that never move merged by kind into vertex-coloured meshes: outside the shell, the saloon (left out on
//   the lighter level) and the glass;
// - the moving parts kept as the asset's nodes: door leaves, bogies and wheels, the collector, the lamps (the asset's
//   clips scrub the doors and the collector); the track-brake shoes and the couplers get their own pivots;
// - the textured parts (lamps, collector, mirror, the cards) as they are.
// Each set owns its materials (traffic fades AI trams one by one) and its cards. The asset's axes: +Y up, forward as
// its manifest says (`forward`, the hybrid's +X), origin on the rail plane midway between the bogies; the game's cars
// face +Z. What the game asks of every vehicle of a type (the bogies at its pivots, the shoes at its gap over the
// rail, the couplers from its pin to the coupling plane) is done here for any rig that names those parts.
import * as THREE from 'three';
import { CAR_PITCH } from './tram.js';
import { beamsMesh } from './lamps.js';

const PLANE = CAR_PITCH / 2;    // the plane two coupled heads meet in, from the car centre
const GLASS_FAR = 0.85;         // the glass's opacity on the lighter level (no saloon behind it)
// the turn about Y from the asset's forward onto the game's +Z
const TURN = { '+Z': 0, '+X': -Math.PI / 2, '-Z': Math.PI, '-X': Math.PI / 2 };

const protos = new Map();       // vehicle id -> its template
export const riggedReady = (id) => protos.has(id);
export const riggedIds = () => [...protos.keys()];
export const riggedProto = (id) => protos.get(id);

const box = (g, m) => { const b = new THREE.Box3().setFromBufferAttribute(g.attributes.position); return m ? b.applyMatrix4(m) : b; };

// one geometry of position, normal and colour (the material's colour, linear) for merging
function painted(src, m, color) {
  const g = new THREE.BufferGeometry();
  const P = src.attributes.position;
  g.setAttribute('position', P.clone());
  if (src.attributes.normal) g.setAttribute('normal', src.attributes.normal.clone());
  const c = new Float32Array(P.count * 3), C = src.attributes.color;
  for (let i = 0; i < P.count; i++) {
    const k = C ? [C.getX(i), C.getY(i), C.getZ(i)] : [1, 1, 1];
    c[i * 3] = color.r * k[0]; c[i * 3 + 1] = color.g * k[1]; c[i * 3 + 2] = color.b * k[2];
  }
  g.setAttribute('color', new THREE.BufferAttribute(c, 3));
  if (src.index) g.setIndex(src.index.clone());
  else g.setIndex([...Array(P.count).keys()]);
  g.applyMatrix4(m);
  if (!g.attributes.normal) g.computeVertexNormals();
  return g;
}

// The rig's names a vehicle's moving parts need, by what it moves (its manifest's `moves`): the missing ones, as
// "what: name" (an empty list: the rig is complete for its claims)
export function rigProblems(rig, moves, has, clips) {
  const out = [], need = (what, name) => { if (!name || !has(name)) out.push(`${what}: ${name ?? '(none named)'}`); };
  const clip = (what, name) => { if (!name || !clips.includes(name)) out.push(`${what} clip: ${name ?? '(none named)'}`); };
  if (moves.includes('bogies')) { if ((rig.bogies?.length ?? 0) < 2) out.push('bogies: fewer than two'); for (const b of rig.bogies || []) need('bogie', b.name); }
  if (moves.includes('wheels')) { if (!rig.wheels?.length) out.push('wheels: none'); for (const w of rig.wheels || []) need('wheel', w.name); }
  if (moves.includes('couplers')) for (const e of ['front', 'rear']) { if (!rig.couplers?.[e]?.length) out.push(`coupler ${e}: none`); for (const n of rig.couplers?.[e] || []) need(`coupler ${e}`, n); }
  if (moves.includes('collector')) {
    const p = rig.pantograph || {};
    need('pantograph', p.root); need('pantograph head', p.head); clip('pantograph', p.clip);
    if (!(p.maxContactHeight > p.minContactHeight)) out.push('pantograph: no contact range');
  }
  if (moves.includes('lamps')) for (const s of ['left', 'right']) { if (!rig.signals?.[s]?.length) out.push(`indicators ${s}: none`); for (const n of rig.signals?.[s] || []) need(`indicator ${s}`, n); }
  if (moves.includes('doors')) for (const d of rig.doors || []) { clip(`door ${d.name}`, d.clip); for (const l of d.leaves) { need(`door ${d.name}`, l.outer); need(`door ${d.name}`, l.inner); } }
  if (moves.includes('trackBrakes')) {
    if (!Object.keys(rig.shoes || {}).length) out.push('shoes: none');
    for (const [b, names] of Object.entries(rig.shoes || {})) { need('shoe bogie', b); for (const n of names) need(`shoe under ${b}`, n); }
  }
  return out;
}

// The vehicle `v` (its manifest) from its model's and rig's bodies (the loading screen's); type: its vehicle type
// (src/tram.js: pivots, track-brake gap, coupler pin); contact: the contact wire over the rail (the lighter level's
// collector). Throws with the rig's missing names when it lacks what its `moves` claim.
export async function loadRigged(v, glbR, rigR, type, contact) {
  if (!glbR?.ok || !rigR?.ok) throw new Error(`vehicle ${v.id}: model or rig missing`);
  const [{ GLTFLoader }, { mergeGeometries }] = await Promise.all([
    import('three/addons/loaders/GLTFLoader.js'), import('three/addons/utils/BufferGeometryUtils.js')]);
  const rig = await rigR.json();
  const gl = await new GLTFLoader().parseAsync(await glbR.arrayBuffer(), '');
  const src = gl.scene;
  src.updateMatrixWorld(true);
  const clipNames = gl.animations.map((a) => a.name);
  const bad = rigProblems(rig, v.moves || [], (n) => !!src.getObjectByName(n), clipNames);
  if (bad.length) throw new Error(`vehicle ${v.id}: its rig lacks ${bad.join('; ')}`);
  // the asset's forward axis: X (0) or Z (2), and its sign
  const fwd = v.forward ?? rig.forward ?? '+Z', ax = fwd.endsWith('X') ? 0 : 2, sg = fwd[0] === '-' ? -1 : 1;
  const along = (p) => sg * (ax === 0 ? p.x : p.z);
  const p = rig.pantograph || {}, routeStyles = rig.routeStyles || {}, info = rig.infoPlates || {};
  const glowNames = [...(rig.signals?.left || []), ...(rig.signals?.right || []), ...(rig.brakes || [])];
  const movers = new Set([
    ...(rig.doors || []).flatMap((d) => d.leaves.flatMap((l) => [l.outer, l.inner])),
    ...(rig.bogies || []).map((b) => b.name), ...(rig.wheels || []).map((w) => w.name),
    ...(p.root ? [p.root, p.head, ...(p.linkages || []).flatMap((l) => [l.lower, l.upper])] : []), ...glowNames]);
  const numberPlates = rig.numberPlates || [];
  const cards = new Set([...numberPlates, ...Object.keys(routeStyles), info.frontDestination, info.runNumber, ...(info.sideBoards || [])].filter(Boolean));
  const shoeOf = new Map(Object.entries(rig.shoes || {}).flatMap(([b, ns]) => ns.map((n) => [n, b])));
  const couplerEnd = new Map(['front', 'rear'].flatMap((e) => (rig.couplers?.[e] || []).map((n) => [n, e])));
  const saloonMats = new Set(rig.saloon?.materials || []);
  const within = rig.saloon?.within ? new THREE.Box3(new THREE.Vector3(...rig.saloon.within[0]), new THREE.Vector3(...rig.saloon.within[1])) : null;

  // the template: every node that is not a plain mesh (keeping the asset's hierarchy and transforms, so
  // its clips drive the copies by name), the moving meshes as they are
  const top = src.getObjectByName(rig.root) || src;
  const copy = new Map();
  const template = new THREE.Group();
  copy.set(top, template);
  template.name = top.name;
  top.traverse((o) => {
    if (o === top) return;
    const mover = movers.has(o.name);
    if (o.isMesh && !mover && !o.children.length) return;
    const c = o.isMesh && mover ? new THREE.Mesh(o.geometry, o.material) : new THREE.Group();
    c.name = o.name;
    // (the node's own transform, not its matrix decomposed: the hybrid's lamp glows are stored off at scale 0,
    // whose matrix decomposes to a NaN rotation, and they never drew)
    c.position.copy(o.position); c.quaternion.copy(o.quaternion); c.scale.copy(o.scale);
    copy.get(o.parent).add(c);
    copy.set(o, c);
  });
  // the frame a plain mesh moves with: its nearest moving ancestor, or the car
  const frameOf = (o) => { for (let q = o.parent; q && q !== top; q = q.parent) if (movers.has(q.name)) return q; return top; };
  const inv = new Map();
  const rel = (o, f) => {
    if (!inv.has(f)) inv.set(f, f === top ? new THREE.Matrix4().copy(top.matrixWorld).invert() : f.matrixWorld.clone().invert());
    return new THREE.Matrix4().multiplyMatrices(inv.get(f), o.matrixWorld);
  };
  const paint = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.75, metalness: 0, side: THREE.DoubleSide });
  // (one pass for both faces: three draws a double-sided transparent material twice, back then front, and
  // the 13 glass meshes of a hybrid car cost 0.9 ms a frame in tools/frametime.py's scene; dark glass at 18 %
  // shows no sorting between its faces)
  const glass = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.2, metalness: 0, side: THREE.DoubleSide, transparent: true, opacity: 0.18, depthWrite: false, forceSinglePass: true });
  glass.userData = { opacity: 0.18, glass: true }; // (traffic's fade multiplies it)
  const buckets = new Map(); // frame -> { out, in, glass, dest, run: [geometries] }
  const put = (f, kind, g) => {
    if (!buckets.has(f)) buckets.set(f, { out: [], in: [], glass: [], dest: [], run: [] });
    buckets.get(f)[kind].push(g);
  };
  const kept = new Map(); // the textured parts by frame and material (a plate keeps its name)
  const stats = { kept: 0, merged: 0, dropped: 0, shoes: 0, couplers: 0 };
  const shoes = [], couplers = [];
  const cardOf = (name) => info.frontDestination && name.startsWith(info.frontDestination) ? 'dest' : info.runNumber && name.startsWith(info.runNumber) ? 'run' : null;
  top.traverse((o) => {
    if (!o.isMesh || movers.has(o.name)) return;
    const m = o.material, f = frameOf(o), M = rel(o, f);
    if (m.opacity === 0) { stats.dropped++; return; } // (an invisible helper)
    const textured = m.map || m.normalMap || m.emissiveMap || (m.emissive && m.emissive.getHex() !== 0);
    if (textured || cards.has(o.name)) {
      const key = `${f.uuid}|${m.uuid}`;
      if (!kept.has(key)) kept.set(key, { f, m, geos: [], name: o.name });
      const g = o.geometry.clone().applyMatrix4(M);
      if (rig.fleetDigits && numberPlates.includes(o.name)) fleetSize(g, rig.fleetDigits);
      kept.get(key).geos.push(g);
      stats.kept++;
      return;
    }
    // (the destination and run cards' backs and clips: hidden with the card when the car shows none)
    const card = cardOf(o.name);
    if (card) { put(f, card, painted(o.geometry, M, m.color)); stats.merged++; return; }
    const b = box(o.geometry, M);
    if (shoeOf.has(o.name)) { shoes.push({ f, g: painted(o.geometry, M, m.color), b }); stats.shoes++; return; }
    if (couplerEnd.has(o.name)) { couplers.push({ e: couplerEnd.get(o.name) === 'front' ? 1 : -1, g: painted(o.geometry, M, m.color), b }); stats.couplers++; return; }
    const saloon = f === top && (saloonMats.has(m.name) || (within && within.containsBox(b)));
    put(f, m.transparent ? 'glass' : saloon ? 'in' : 'out', painted(o.geometry, M, m.color));
    stats.merged++;
  });
  for (const [f, k] of buckets) {
    for (const [kind, mat] of [['out', paint], ['in', paint], ['glass', glass], ['dest', paint], ['run', paint]]) {
      if (!k[kind].length) continue;
      const mesh = new THREE.Mesh(mergeGeometries(k[kind]), mat);
      mesh.name = `R_${kind}`;
      copy.get(f).add(mesh);
    }
  }
  for (const { f, m, geos, name } of kept.values()) {
    const merged = geos.length > 1 ? mergeGeometries(geos) : geos[0];
    for (const g of merged ? [merged] : geos) { // (parts whose attributes differ stay apart)
      const mesh = new THREE.Mesh(g, m);
      mesh.name = name;
      copy.get(f).add(mesh);
    }
  }
  // the track-brake shoes hang at the type's gap over the rail (the hybrid's are 67 mm up in the asset): each on its
  // own pivot under its bogie, which drops it onto the rail when its magnets are on
  for (const s of shoes) {
    const piv = new THREE.Group();
    piv.name = 'R_shoe';
    const bogieY = s.f.matrixWorld.elements[13];
    s.g.translate(0, type.trackBrakeGap - (s.b.min.y + bogieY), 0);
    piv.add(new THREE.Mesh(s.g, paint));
    piv.userData.drop = type.trackBrakeGap;
    copy.get(s.f).add(piv);
  }
  // the couplers: each bar turns about the yoke's pin under the body end (the type's couplerPivot), refitted to run
  // from just behind the pin to the coupling plane (the heads' 80 mm beyond it are not drawn: two bars would overlap)
  const get = (P, i) => (ax === 0 ? P.getX(i) : P.getZ(i)) * sg, set = (P, i, x) => (ax === 0 ? P.setX(i, x * sg) : P.setZ(i, x * sg));
  for (const c of couplers) {
    const e = c.e, lo = sg * (ax === 0 ? c.b.min.x : c.b.min.z), hi = sg * (ax === 0 ? c.b.max.x : c.b.max.z);
    const x0 = Math.min(e * lo, e * hi), x1 = Math.max(e * lo, e * hi); // (the bar's ends from the car's centre outwards)
    const pin = type.couplerPivot, a = pin - 0.1, P = c.g.attributes.position, y = (c.b.min.y + c.b.max.y) / 2;
    for (let i = 0; i < P.count; i++) {
      const x = get(P, i) * e;
      set(P, i, e * (a + (x - x0) * (PLANE - a) / (x1 - x0)) - e * pin);
      P.setY(i, P.getY(i) - y);
    }
    P.needsUpdate = true;
    c.g.computeBoundingBox(); c.g.computeBoundingSphere();
    const piv = new THREE.Group();
    piv.name = e > 0 ? 'R_coupler_front' : 'R_coupler_rear';
    piv.position.set(0, y, 0).setComponent(ax, sg * e * pin);
    piv.add(new THREE.Mesh(c.g, paint));
    template.add(piv);
  }
  template.traverse((o) => {
    if (!o.isMesh) return;
    // (no environment map in the game: metals would draw black)
    if (o.material.isMeshStandardMaterial) { o.material.metalness = 0; o.material.roughness = Math.max(o.material.roughness, 0.5); }
    o.geometry.computeBoundingSphere();
    o.geometry.userData.shared = true;
    for (const t of Object.values(o.material)) if (t?.isTexture) t.userData.shared = true;
  });
  // the bogies at the type's pivots (the hybrid's asset has them 6.485 m apart, the T3 6.4 m), their shoes with them
  const bogies = (rig.bogies || []).map((b) => {
    const n = template.getObjectByName(b.name), at = new THREE.Vector3(...(b.pivot || [0, 0, 0]));
    const front = along(n ? n.position : at) > 0;
    if (n) n.position.setComponent(ax, sg * (front ? 1 : -1) * type.bogies / 2);
    return { name: b.name, front };
  });
  // half the wheelbase of a bogie: its wheels' spread along the car (the hybrid's 0.91 m)
  const wheelAt = [];
  for (const b of rig.bogies || []) {
    const n = src.getObjectByName(b.name), xs = [];
    n?.traverse((o) => { if ((rig.wheels || []).some((w) => w.name === o.name)) { const q = new THREE.Vector3(); o.getWorldPosition(q); xs.push(along(q.applyMatrix4(inv.get(top) ?? new THREE.Matrix4().copy(top.matrixWorld).invert()))); } });
    if (xs.length > 1) wheelAt.push((Math.max(...xs) - Math.min(...xs)) / 2);
  }
  const axle = wheelAt.length ? wheelAt.reduce((s, x) => s + x, 0) / wheelAt.length : 0.9;
  // the lamps' glow: off, bright when on
  for (const n of glowNames) {
    const g = template.getObjectByName(n);
    if (!g) continue;
    g.scale.setScalar(1); g.visible = false;
    if (g.material) { g.material.emissiveIntensity = 4; g.material.toneMapped = false; }
  }
  // the lighter level (AI trams farther than FULL_OUT): the car posed with its doors shut and the collector
  // at the wire, all but the saloon and the lamps' glow merged in the car's frame by material; the cards
  // and their backs stay apart (their textures and visibility change), the glass is darker (no saloon)
  const glassFar = glass.clone();
  glassFar.opacity = GLASS_FAR; glassFar.userData = { opacity: GLASS_FAR, glass: true };
  const mixer = new THREE.AnimationMixer(template);
  const pose = [...(rig.doors || []).map((d) => [d.clip, 0]), [p.clip, p.clip ? collectorU(rig, contact) : 0]];
  for (const [name, u] of pose) {
    const clip = name && THREE.AnimationClip.findByName(gl.animations, name);
    if (!clip) continue;
    const a = mixer.clipAction(clip); a.play(); a.paused = true; a.time = u * clip.duration;
  }
  mixer.update(0);
  template.updateMatrixWorld(true);
  const glows = new Set(glowNames);
  const apart = (name) => cards.has(name) || name === 'R_dest' || name === 'R_run';
  const light = new THREE.Group(), flat = new Map();
  light.name = 'R_light';
  template.traverse((o) => {
    if (!o.isMesh || o.name === 'R_in' || glows.has(o.name)) return;
    const g = o.geometry.clone().applyMatrix4(o.matrixWorld); // (the template has no parent)
    g.userData.shared = true;
    if (apart(o.name)) { const k = new THREE.Mesh(g, o.material); k.name = o.name; light.add(k); return; }
    const m = o.material === glass ? glassFar : o.material;
    if (!flat.has(m)) flat.set(m, []);
    flat.get(m).push(g);
  });
  for (const [m, geos] of flat) {
    const merged = geos.length > 1 ? mergeGeometries(geos) : geos[0];
    for (const g of merged ? [merged] : geos) {
      g.computeBoundingSphere(); g.userData.shared = true;
      light.add(new THREE.Mesh(g, m));
    }
  }
  mixer.stopAllAction(); mixer.uncacheRoot(template);
  // the rig's places in the asset's frame onto the car's: the high beams' glow over the headlights, the tail lamps
  // added where the asset has none (the hybrid's: the user, 2026-11-10, #436, on the rear panel 0.47 m either side)
  const turn = new THREE.Matrix4().makeRotationY(TURN[fwd] ?? 0);
  const toCar = (q) => new THREE.Vector3(...q).applyMatrix4(turn);
  const heads = (rig.beams || []).map((q) => toCar(q).toArray());
  let tails = null;
  if (rig.tailLamps?.at?.length) {
    const [sx, sy, sz] = rig.tailLamps.size;
    tails = mergeGeometries(rig.tailLamps.at.map((q) => new THREE.BoxGeometry(sx, sy, sz).applyMatrix4(turn).translate(...toCar(q).toArray())));
    tails.userData.shared = true;
  }
  const proto = { template, light, rig, clips: gl.animations, bogie: type.bogies / 2, axle, bogies, ax, sg, turn: TURN[fwd] ?? 0, stats, heads, tails };
  protos.set(v.id, proto);
  return proto;
}

// the collector clip's position (0..1) for a contact height over the rail
function collectorU(rig, h) {
  const p = rig.pantograph, c = THREE.MathUtils.clamp(h, p.minContactHeight, p.maxContactHeight);
  return (p.maxContactHeight - c) / (p.maxContactHeight - p.minContactHeight);
}

// ------------------------------------------------------------------------------------------- cards
// The plates and cards as the user described them (src/models.js, "The T3's number plates and cards"),
// drawn over the asset's own plates (the hybrid's have cream on navy and no frame).
function canvas(w, h, bg) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const x = c.getContext('2d');
  if (bg) { x.fillStyle = bg; x.fillRect(0, 0, w, h); }
  x.textAlign = 'center'; x.textBaseline = 'middle';
  return [c, x];
}
function texture(c, shared) {
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace; t.flipY = false; t.anisotropy = 4;
  if (shared) t.userData.shared = true;
  return t;
}
const cache = new Map();
const cached = (key, make) => { if (!cache.has(key)) cache.set(key, texture(make(), true)); return cache.get(key); };
const up = (s) => String(s ?? '').normalize('NFC').trim().toLocaleUpperCase('cs-CZ');
const BLUE = '#1f57a8', WHITE = '#f4f4f0', IVORY = '#f5f1e5'; // (DPP blue as src/models.js; the side boards' ivory)

// the route number plates: on the roof (navy on cream), the inverted one in the rear window, the mirror's
function routeTexture(line, style) {
  return cached(`route:${style}:${line}`, () => {
    const mirror = style === 'mirror', inv = style === 'inverted', [c, x] = canvas(mirror ? 384 : 512, mirror ? 512 : 384, inv ? WHITE : BLUE);
    const w = c.width, h = c.height, t = String(line);
    x.fillStyle = inv ? '#1d3f86' : '#ffffff';
    x.font = `bold ${Math.min(h * 0.78, (w * 1.27) / t.length)}px Arial, sans-serif`;
    x.fillText(t, w / 2, h * 0.53, w * 0.94);
    return c;
  });
}
// the destination card behind the windscreen: blue capitals in a blue frame, two balanced lines when long
function destinationTexture(dest) {
  return cached(`dest:${dest ?? ''}`, () => {
    const [c, x] = canvas(1024, 384, WHITE);
    x.strokeStyle = BLUE; x.lineWidth = 18; x.strokeRect(15, 15, 994, 354);
    let lines = up(dest).split('\n');
    if (lines.length === 1 && lines[0].length > 13 && lines[0].includes(' ')) {
      const w = lines[0].split(/\s+/);
      let best = Infinity, at = 1;
      for (let i = 1; i < w.length; i++) {
        const d = Math.abs(w.slice(0, i).join(' ').length - w.slice(i).join(' ').length);
        if (d < best) { best = d; at = i; }
      }
      lines = [w.slice(0, at).join(' '), w.slice(at).join(' ')];
    }
    x.fillStyle = BLUE;
    lines.slice(0, 2).forEach((l, i, a) => { x.font = `bold ${a.length === 1 ? 200 : 140}px Arial, sans-serif`; x.fillText(l, 512, 30 + ((i + 0.5) * 324) / a.length, 920); });
    return c;
  });
}
// the side board in the second window: the route number and the destination
function sideTexture(line, dest) {
  return cached(`side:${line}:${dest ?? ''}`, () => {
    const [c, x] = canvas(1024, 600, IVORY);
    x.fillStyle = BLUE;
    x.font = 'bold 520px Arial, sans-serif'; x.fillText(String(line), 153, 318, 254);
    const lines = dest ? [up(dest)] : [''];
    lines.forEach((l, i) => { x.font = `bold ${Math.min(64, (510 / lines.length) * 0.77)}px Arial, sans-serif`; x.fillText(l, 656, 45 + ((i + 0.5) * 510) / lines.length, 672); });
    return c;
  });
}
function runTexture(run) {
  const [c, x] = canvas(384, 448, '#101418');
  x.fillStyle = '#fffdf4'; x.font = 'bold 390px Arial, sans-serif'; x.fillText(String(run ?? ''), 192, 234, 344);
  return texture(c);
}
// The fleet numbers' digits `h` m tall on every side (the rig's `fleetDigits`; the hybrid's 0.14 m: the user,
// 2026-11-10, "fix the hybrid's fleet number size"; src/t3simple.js FLEET has the photos' measurements). The texture's
// digits fill FLEET_FILL of its height whatever the font, and each quad is scaled about its centre to h / FLEET_FILL
// (the hybrid's quads were 0.19 m tall on the ends and 0.23 m on the sides, its digits 0.106 and 0.13 m).
const FLEET_FILL = 132 / 192;
function fleetSize(g, h) {
  g.computeBoundingBox();
  const b = g.boundingBox, c = b.getCenter(new THREE.Vector3()), k = h / FLEET_FILL / (b.max.y - b.min.y);
  g.translate(-c.x, -c.y, -c.z).scale(k, k, k).translate(c.x, c.y, c.z);
}
function fleetTexture(n) {
  const [c, x] = canvas(512, 192);
  const t = String(n);
  x.fillStyle = '#e3b625'; x.font = 'bold 100px Arial, sans-serif';
  const m = x.measureText(t), L = m.actualBoundingBoxLeft, R = m.actualBoundingBoxRight, A = m.actualBoundingBoxAscent, D = m.actualBoundingBoxDescent;
  const k = (FLEET_FILL * 192) / (A + D), kx = Math.min(k, 480 / (L + R));
  x.setTransform(kx, 0, 0, k, 256 - (kx * (R - L)) / 2, 96 - (k * (D - A)) / 2);
  x.fillText(t, 0, 0);
  return texture(c);
}
const setMap = (m, tex) => { if (!m || m.map === tex) return; if (m.map && !m.map.userData.shared && m.userData.own) m.map.dispose(); m.map = tex; m.userData.own = !tex.userData.shared; m.needsUpdate = true; };

// ---------------------------------------------------------------------------------------------- sets
// A set of `cars` cars of vehicle `id` on `root`, `fleet` their numbers (src/vehicles.js fleetNumbers: the manifest's
// range picked by the run number, a placeholder as the run number is until the data has them).
export function makeRiggedSet(id, root, line, cars, dest, run, collector, fleet = Array(cars).fill(null)) {
  const proto = protos.get(id), { template, rig, clips } = proto;
  const own = new Map();
  const mat = (m) => { let c = own.get(m); if (!c) { c = m.clone(); own.set(m, c); } return c; };
  Object.assign(root.userData, { rigged: true, proto, cars: [], bogie: proto.bogie, mats: { body: true }, line, dest, run, level: 'full' });
  const info = rig.infoPlates || {}, styles = rig.routeStyles || {};
  for (let k = 0; k < cars; k++) {
    const car = new THREE.Group();
    car.rotation.order = 'YXZ';
    // both levels, sharing the set's materials (the car's own for its fleet number)
    const r = template.clone(true), l = proto.light.clone(true);
    const fleetMat = new Map();
    for (const x of [r, l]) {
      x.rotation.y = proto.turn; // (the asset's forward onto the game's +Z)
      x.traverse((o) => {
        if (!o.material) return;
        if ((rig.numberPlates || []).includes(o.name)) {
          if (!fleetMat.has(o.material)) { const c = o.material.clone(); c.map = fleetTexture(fleet[k] ?? ''); c.userData.own = true; fleetMat.set(o.material, c); }
          o.material = fleetMat.get(o.material);
        } else o.material = mat(o.material);
      });
      car.add(x);
    }
    l.visible = false;
    const n = (name) => (name ? r.getObjectByName(name) : undefined);
    const both = (name) => [r.getObjectByName(name), l.getObjectByName(name)].filter(Boolean);
    const mixer = new THREE.AnimationMixer(r), act = {}, doorClips = [];
    for (const name of [...(rig.doors || []).map((d) => d.clip), rig.pantograph?.clip]) {
      const clip = name && THREE.AnimationClip.findByName(clips, name);
      if (!clip) continue;
      const a = mixer.clipAction(clip); a.play(); a.paused = true; act[name] = a;
    }
    for (const d of rig.doors || []) if (act[d.clip]) doorClips.push(act[d.clip]);
    car.userData.rig = {
      mixer, act, doorClips, collectorClip: act[rig.pantograph?.clip], doors: -1, collector: -1, braking: null, track: -1,
      bogies: proto.bogies.map((b) => ({ node: n(b.name), front: b.front, shoes: [] })),
      wheels: (rig.wheels || []).map((w) => ({ node: n(w.name), r: w.radius })),
      couplers: [n('R_coupler_front'), n('R_coupler_rear')],
      brakes: (rig.brakes || []).map(n).filter(Boolean),
      signals: { left: (rig.signals?.left || []).map(n).filter(Boolean), right: (rig.signals?.right || []).map(n).filter(Boolean) }, lit: { left: false, right: false },
      full: r, light: l, plates: {},
    };
    const cr = car.userData.rig;
    for (const b of cr.bogies) b.node?.traverse((o) => { if (o.name === 'R_shoe') b.shoes.push(o); });
    car.userData.gear = gear(cr, proto);
    // the high beams' glow over the leading car's headlights (src/lamps.js); the tail lamps on every car ("in
    // between cars only the rear red lights light up"; at twice their colour, as the built-in car's)
    if (k === 0 && proto.heads.length) { car.userData.beams = beamsMesh(proto.heads); car.add(car.userData.beams); }
    if (proto.tails) {
      const tail = new THREE.Mesh(proto.tails, new THREE.MeshBasicMaterial({ color: new THREE.Color('#d8261a').multiplyScalar(2), toneMapped: false }));
      tail.name = 'R_tail';
      car.add(tail);
    }
    // the cards: the route plates on every car (the front one shows on the leading car, the rear one on the
    // last), the destination and run number in the leading car only
    cr.plates = {
      route: Object.entries(styles).map(([name, style]) => [n(name), style]),
      dest: n(info.frontDestination), run: n(info.runNumber), side: (info.sideBoards || []).map(n),
      destAll: [info.frontDestination, 'R_dest'].filter(Boolean).flatMap(both), runAll: [info.runNumber, 'R_run'].filter(Boolean).flatMap(both),
    };
    root.add(car);
    root.userData.cars.push(car);
  }
  setRiggedLine(root, line, dest, run, true);
  poseRigged(root, { doors: 0, collector });
  return root;
}

export function setRiggedLine(model, line, dest = model.userData.dest, run = model.userData.run, force = false) {
  const u = model.userData;
  model.userData.cars.forEach((car, k) => {
    const p = car.userData.rig.plates;
    if (force || u.line !== line) for (const [node, style] of p.route) setMap(node?.material, routeTexture(line, style));
    if (force || u.line !== line || u.dest !== dest) for (const s of p.side) setMap(s?.material, sideTexture(line, dest));
    if (force || u.dest !== dest) setMap(p.dest?.material, destinationTexture(dest));
    if (force || u.run !== run) if (k === 0) setMap(p.run?.material, runTexture(run));
    // (no destination card on a tram whose destination we do not know; the cards only in the leading car)
    for (const o of p.destAll) o.visible = k === 0 && !!dest;
    for (const o of p.runAll) o.visible = k === 0;
  });
  Object.assign(u, { line, dest, run });
}

// The mechanisms from the game's state, each only when it changes: doors (0 closed .. 1 open), the
// collector's contact height over the rail, the brake lamps, the track-brake magnets (0 off, 1 the rear
// bogies', 2 all), the indicators' sides lit now (`signals`: { left, right }), the high beams.
export function poseRigged(model, { doors, collector, braking, track, signals, highBeam } = {}) {
  const { rig } = model.userData.proto;
  model.userData.cars.forEach((car) => {
    const r = car.userData.rig;
    let scrub = false;
    if (doors !== undefined && Math.abs(doors - r.doors) > 1e-3) {
      r.doors = doors;
      for (const a of r.doorClips) a.time = THREE.MathUtils.clamp(doors, 0, 1) * a.getClip().duration;
      scrub = true;
    }
    if (collector !== undefined && Math.abs(collector - r.collector) > 1e-3 && r.collectorClip) {
      r.collector = collector;
      r.collectorClip.time = collectorU(rig, collector) * r.collectorClip.getClip().duration;
      scrub = true;
    }
    if (scrub) r.mixer.update(0);
    if (braking !== undefined && braking !== r.braking) { r.braking = braking; for (const b of r.brakes) b.visible = braking; }
    if (signals !== undefined) for (const s of ['left', 'right']) if (!!signals[s] !== r.lit[s]) { r.lit[s] = !!signals[s]; for (const g of r.signals[s]) g.visible = r.lit[s]; }
    if (highBeam !== undefined && car.userData.beams) car.userData.beams.visible = !!highBeam;
    if (track !== undefined && track !== r.track) {
      r.track = track;
      // (the rear bogie's magnets first, ČKD [ckd24] p. 16; src/tr37.js trackAngles)
      for (const b of r.bogies) for (const s of b.shoes) s.position.y = (track >= 2 || (track === 1 && !b.front)) ? -s.userData.drop : 0;
    }
  });
}

// The level a set is drawn at: 'full', or 'light' (no saloon, doors shut, everything merged; for AI trams
// beyond FULL_OUT). A set at its lighter level is posed as at its full one, which shows again at once.
export function setRiggedLevel(model, level) {
  const u = model.userData;
  if (!u.rigged || u.level === level) return;
  u.level = level;
  for (const car of u.cars) { car.userData.rig.full.visible = level === 'full'; car.userData.rig.light.visible = level !== 'full'; }
}
export const FULL_IN = 50, FULL_OUT = 60; // m from the camera: AI trams' full level (the saloon through the windows)

// ------------------------------------------------------------------------------------------ running
// A car's running gear for src/consist.js (hangConsist places the cars): its bogies' and wheels' nodes, the coupler
// bars' pivots, all in the asset's frame (proto.turn about Y from the car's).
function gear(r, proto) {
  const back = new THREE.Matrix4().makeRotationY(-proto.turn), d = new THREE.Vector3(), rest = new THREE.Vector3();
  // the wheels roll about their axle: across the car, the asset's Z for a vehicle facing X and its X for one facing Z
  const spin = proto.ax === 0 ? (w, a) => { w.rotation.z = -proto.sg * a; } : (w, a) => { w.rotation.x = proto.sg * a; };
  return {
    axle: proto.axle, pinY: r.couplers[1]?.position.y ?? 0,
    live: () => r.full.visible, // (the lighter level has them merged)
    turn(i, yaw) { for (const b of r.bogies) if (b.node && b.front === (i === 0)) b.node.rotation.y = yaw; },
    roll(s) { for (const w of r.wheels) if (w.node) spin(w.node, s / w.r); },
    swing(i, q) {
      const bar = r.couplers[i];
      if (!bar) return;
      if (!q) { bar.quaternion.identity(); return; }
      // the bar from its rest along the car's axis to the link's direction, up and down too (held along its car,
      // each head rode on that car's pitch and the two stepped against each other by cm where the track changes
      // its grade between the cars, #356)
      rest.set(0, 0, 0).setComponent(proto.ax, proto.sg * (i === 0 ? 1 : -1));
      bar.quaternion.setFromUnitVectors(rest, d.copy(q).applyMatrix4(back).normalize());
    },
  };
}
