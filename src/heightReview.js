// Optional staged-height spans in F8. Their height follows the current world; no proposal changes it.
import * as THREE from 'three';

export function buildHeightReview(game) {
  const spans = game.heightReview?.spans.filter((s) => String(s.line) === String(game.data.line)) || [];
  if (!spans.length) return null;
  const group = new THREE.Group(), resources = [];
  const panel = document.createElement('div');
  panel.id = 'heightReviewPanel';
  Object.assign(panel.style, { position: 'fixed', right: '12px', top: '12px', zIndex: 55, width: '390px', maxWidth: '42vw',
    maxHeight: '70vh', overflow: 'auto', padding: '10px', color: '#fff', background: '#14181ced', font: '12px/1.4 system-ui' });
  const heading = document.createElement('b');
  heading.textContent = 'HEIGHT REVIEW · orange: held · red: conflict · blue: numeric DI · green: approved';
  panel.append(heading);
  const info = document.createElement('pre');
  Object.assign(info.style, { whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' });
  for (const span of spans) {
    const conflict = span.review_flags.some((f) => /disagreement|ambiguous/.test(f));
    const color = span.status === 'approved' ? 0x44dd88 : span.status === 'di_numeric' ? 0x66ccff : conflict ? 0xff5555 : 0xffbb44;
    const points = span.profile.map((p) => {
      const [x, y] = p.xy, near = game.route.nearest(x, y);
      return new THREE.Vector3(x, (near ? game.profile.height(near.s) : 0) + 0.8, -y);
    });
    if (points.length === 1) points.push(points[0].clone().add(new THREE.Vector3(0.1, 0, 0)));
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const material = new THREE.LineBasicMaterial({ color, depthTest: false });
    const line = new THREE.Line(geometry, material);
    line.renderOrder = 1000;
    line.userData.heightReviewId = span.id;
    group.add(line);
    resources.push(geometry, material);
    const button = document.createElement('button');
    button.textContent = `${span.structure.names.join(' / ') || span.structure.kind} · ${span.from_stop} → ${span.to_stop} · ${span.direction} · ${Math.round(span.length_m)} m`;
    Object.assign(button.style, { display: 'block', width: '100%', textAlign: 'left', marginTop: '6px', color: `#${color.toString(16)}`, background: '#30353c', border: '1px solid #657080', padding: '5px' });
    button.onclick = () => {
      game.inspectHeightSpan?.(span);
      info.textContent = JSON.stringify({ id: span.id, osm_ways: span.structure.osm_ways, flags: span.review_flags,
        proposal: span.proposal, di_ends: span.di_ends, archive: span.archive_candidates,
        survey: span.survey_candidates, terrain: span.terrain }, null, 2);
    };
    panel.append(button);
  }
  panel.append(info);
  document.body.append(panel);
  group.userData.dispose = () => { panel.remove(); for (const r of resources) r.dispose(); };
  return group;
}
