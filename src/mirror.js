// The rear view has a separate texture cadence. Its cached picture must still be composited after
// every main draw, or the main scene wipes it on the frames between updates (#79).
import * as THREE from 'three';

const PERIOD = 1000 / 30;

export class Mirror {
  constructor(renderer, scene, element, hidden = []) {
    Object.assign(this, { renderer, scene, element, hidden });
    this.camera = new THREE.PerspectiveCamera(30, 150 / 190, 0.3, 300);
    this.target = new THREE.WebGLRenderTarget(240, 304);
    this.scene = new THREE.Scene();
    this.view = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    const g = new THREE.PlaneGeometry(2, 2), uv = g.attributes.uv;
    for (let i = 0; i < uv.count; i++) uv.setX(i, 1 - uv.getX(i));
    this.scene.add(new THREE.Mesh(g, new THREE.MeshBasicMaterial({ map: this.target.texture })));
    this.source = scene;
    this.last = null;
    this.stats = { updates: 0, presents: 0, far: 300, maxHz: 30, excluded: hidden.length };
  }

  draw(now, active, pose, model) {
    const R = this.renderer, box = this.element.getBoundingClientRect();
    if (box.width <= 12 || box.height <= 12) return;
    const th = Math.round(Math.max(120, Math.min(640, (box.height - 12) * R.getPixelRatio())));
    const resized = th !== this.target.height;
    if (resized) this.target.setSize(Math.round(th * 150 / 190), th);
    const due = this.last === null || now - this.last >= PERIOD - .01;
    if (resized || this.last === null || active && due) {
      pose(this.camera);
      const visibility = this.hidden.map(o => o.visible), vis = model.visible;
      const target = R.getRenderTarget();
      try {
        for (const o of this.hidden) o.visible = false;
        model.visible = true;
        R.setRenderTarget(this.target);
        R.render(this.source, this.camera);
      } finally {
        R.setRenderTarget(target);
        model.visible = vis;
        this.hidden.forEach((o, i) => { o.visible = visibility[i]; });
      }
      // Keep the cadence's phase across 60/120/144 Hz and slow frames; never catch up with a burst.
      this.last = this.last === null || resized ? now :
        this.last + Math.max(1, Math.floor((now - this.last + .01) / PERIOD)) * PERIOD;
      this.stats.updates++;
    }
    const viewport = R.getViewport(new THREE.Vector4()), scissor = R.getScissor(new THREE.Vector4());
    const clipping = R.getScissorTest(), clear = R.autoClear;
    try {
      R.setViewport(box.left + 6, innerHeight - box.bottom + 6, box.width - 12, box.height - 12);
      R.setScissor(box.left + 6, innerHeight - box.bottom + 6, box.width - 12, box.height - 12);
      R.setScissorTest(true);
      R.autoClear = false;
      R.render(this.scene, this.view);
      this.stats.presents++;
    } finally {
      R.autoClear = clear;
      R.setScissorTest(clipping);
      R.setScissor(scissor);
      R.setViewport(viewport);
    }
  }
}
