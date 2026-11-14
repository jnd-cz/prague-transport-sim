import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { makePhotoT3, posePhotoT3, photoT3Stats } from '../../src/t3photo.js';

const scene = new THREE.Scene(); scene.background = new THREE.Color('#e9e8e3');
const camera = new THREE.PerspectiveCamera(37, innerWidth / innerHeight, .05, 120);
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); renderer.setSize(innerWidth, innerHeight);
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.0;
document.querySelector('#stage').append(renderer.domElement);
const env = new THREE.PMREMGenerator(renderer), room = new RoomEnvironment();
scene.environment = env.fromScene(room, .04).texture; room.dispose(); env.dispose();
scene.add(new THREE.HemisphereLight('#ffffff', '#79827b', 1.1));
const sun = new THREE.DirectionalLight('#fff1da', 2.5); sun.position.set(-5, 12, 9); sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048); Object.assign(sun.shadow.camera, { left: -12, right: 12, top: 12, bottom: -12, near: .5, far: 40 });
sun.shadow.bias = -.0003; sun.shadow.normalBias = .025; scene.add(sun);
const fill = new THREE.DirectionalLight('#d1e1ef', 1); fill.position.set(7, 7, -8); scene.add(fill);
const ground = new THREE.Mesh(new THREE.PlaneGeometry(200, 200), new THREE.MeshStandardMaterial({ color: '#dedfd8', roughness: .95 }));
ground.rotation.x = -Math.PI / 2; ground.position.y = -.035; ground.receiveShadow = true; scene.add(ground);
// Two thin rails make the scale and wheel contact readable without a city-data dependency.
for (const x of [-.7175, .7175]) {
  const rail = new THREE.Mesh(new THREE.BoxGeometry(.058, .04, 20), new THREE.MeshStandardMaterial({ color: '#979f9b', metalness: .75, roughness: .36 }));
  rail.position.set(x, -.02, 0); rail.receiveShadow = true; scene.add(rail);
}
const controls = new OrbitControls(camera, renderer.domElement); controls.target.set(0, 1.5, 0);
controls.enableDamping = true; controls.maxPolarAngle = Math.PI / 2; controls.minDistance = 2; controls.maxDistance = 40;
const model = makePhotoT3(); scene.add(model);
const stats = photoT3Stats(model);
document.querySelector('#stats').textContent = `${stats.triangles.toLocaleString()} triangles · ${stats.meshes} meshes`;
const $ = id => document.getElementById(id), value = id => +$(id).value;
const state = () => ({ doors: [value('door1'), value('door2'), value('door3')], pantograph: value('pantograph'),
  bogies: [value('bogies'), -value('bogies')], wipers: value('wipers'), wheelAngle });
let wheelAngle = 0;
function pose() { posePhotoT3(model, state()); }
for (const id of ['door1', 'door2', 'door3', 'pantograph', 'bogies', 'wipers']) $(id).addEventListener('input', pose);
$('wireframe').addEventListener('change', () => model.traverse(o => { if (o.isMesh) o.material.wireframe = $('wireframe').checked; }));
function reset() {
  for (const id of ['door1', 'door2', 'door3', 'bogies', 'wipers']) $(id).value = 0;
  $('pantograph').value = .68; $('wheels').checked = false; wheelAngle = 0; pose();
}
$('reset').addEventListener('click', reset);
function view(name) {
  const views = { hero: [-15, 7.0, 19], front: [0, 3.2, 18], side: [-23, 3.4, 0], rear: [9, 5.5, -19], left: [20, 5, 13] };
  camera.position.set(...(views[name] || views.hero)); controls.target.set(0, 1.55, 0);
  if (innerWidth <= 700) camera.position.sub(controls.target).multiplyScalar(2.8).add(controls.target);
  controls.update(); renderer.render(scene, camera);
}
document.querySelectorAll('[data-view]').forEach(b => b.addEventListener('click', () => view(b.dataset.view)));
async function exportGLB() {
  return new GLTFExporter().parseAsync(model, { binary: true, onlyVisible: true });
}
$('export').addEventListener('click', async () => {
  $('export').disabled = true;
  try {
    const data = await exportGLB(), url = URL.createObjectURL(new Blob([data], { type: 'model/gltf-binary' }));
    const a = document.createElement('a'); a.href = url; a.download = 'tatra-t3-6892.glb'; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) { $('error').textContent = `Export failed: ${e.message}`; }
  finally { $('export').disabled = false; }
});
function resize() {
  const oldAspect = camera.aspect;
  camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); renderer.setSize(innerWidth, innerHeight);
  // Leave room beside the tram for controls without changing its geometry.
  if (innerWidth > 700) camera.setViewOffset(innerWidth, innerHeight, innerWidth * .08, 0, innerWidth, innerHeight);
  else camera.setViewOffset(innerWidth, innerHeight, 0, innerHeight * .16, innerWidth, innerHeight);
  if (oldAspect > .8 && camera.aspect < .8) camera.position.sub(controls.target).multiplyScalar(2.8).add(controls.target);
  if (oldAspect < .8 && camera.aspect > .8) camera.position.sub(controls.target).multiplyScalar(1 / 2.8).add(controls.target);
}
addEventListener('resize', resize); resize(); view('hero');
let last = performance.now();
renderer.setAnimationLoop(now => {
  if ($('wheels').checked) { wheelAngle += Math.min(.05, (now - last) / 1000) * 2; pose(); }
  last = now; controls.update(); renderer.render(scene, camera);
});
window.t3studio = { model, scene, camera, renderer, controls, stats, pose: posePhotoT3, reset, view, exportGLB };
