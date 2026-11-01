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
  const list = document.createElement('div');
  Object.assign(list.style, { maxHeight: '25vh', overflow: 'auto' });
  panel.append(list);
  const description = document.createElement('pre');
  Object.assign(description.style, { whiteSpace: 'pre-wrap', maxHeight: '25vh', overflow: 'auto' });
  const details = document.createElement('details'), label = document.createElement('summary');
  label.textContent = 'All sources and scope'; details.append(label);
  const info = document.createElement('pre');
  Object.assign(info.style, { whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: '30vh', overflow: 'auto' });
  details.append(info);
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
      const range = (h) => h?.n ? `${h.min}–${h.max} m` : 'none';
      description.textContent = [
        `Proposed: ${span.proposal?.rule}\n${span.proposal?.reason || ''}`,
        `DI near ends: ${(span.di_ends || []).map((p) => p ? `${p.z.toFixed(3)} m (${p.distance_m} m away)` : 'none').join(' / ')}`,
        `Archive: ${(span.archive_candidates || []).map((c) => `${c.id}: ${range(c.height)} (${c.record_date || 'date missing'})`).join('; ') || 'none'}`,
        `Survey: ${(span.survey_candidates || []).map((c) => `${c.class}, level ${c.level}: raw ${range(c.survey_height)}, rail candidate ${range(c.height)} (${c.source?.date || 'date missing'})${c.excluded ? `, ${c.excluded}` : ''}`).join('; ') || 'none'}`,
        `IPR bare earth: ${range(span.terrain)} (comparison only)`,
        `Flags: ${span.review_flags.join(', ')}`,
      ].join('\n\n');
      description.scrollTop = 0;
      info.textContent = JSON.stringify({ id: span.id, osm_ways: span.structure.osm_ways, flags: span.review_flags,
        proposal: span.proposal, di_ends: span.di_ends, archive: span.archive_candidates,
        survey: span.survey_candidates, terrain: span.terrain }, null, 2);
    };
    list.append(button);
  }
  panel.append(description, details);
  document.body.append(panel);
  group.userData.dispose = () => { panel.remove(); for (const r of resources) r.dispose(); };
  return group;
}
