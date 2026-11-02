// Track-height decision profile (#162). Distances are measured along the longest reviewed span.
const valid = (z) => Number.isFinite(z) && z > 100 && z < 500;
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function project(p, base) {
  if (base.length === 1) return { d:Math.hypot(p[0]-base[0].xy[0],p[1]-base[0].xy[1]), s:base[0].s };
  let best = { d: Infinity, s: 0 };
  for (let i = 1; i < base.length; i++) {
    const a = base[i-1], b = base[i], dx = b.xy[0]-a.xy[0], dy = b.xy[1]-a.xy[1], l2 = dx*dx+dy*dy;
    const t = l2 ? Math.max(0,Math.min(1,((p[0]-a.xy[0])*dx+(p[1]-a.xy[1])*dy)/l2)) : 0;
    const d = Math.hypot(p[0]-a.xy[0]-t*dx,p[1]-a.xy[1]-t*dy);
    if (d < best.d) best = { d, s: a.s + (b.s-a.s)*t };
  }
  return best;
}

export function heightProfile(f, route, profile) {
  const main = [...f.spans].sort((a,b) => b.length_m-a.length_m)[0];
  if (!main || !main.profile.length) return null;
  const base = [...(main.approach || []),...main.profile].sort((a,b) => a.s-b.s), origin = main.start_s;
  const series = [];
  for (const span of [main,...f.spans.filter((s)=>s !== main)]) {
    const points = [...(span.approach || []),...span.profile].map((p) => {
      const pos = span === main ? {s:p.s,d:0} : project(p.xy,base);
      const n = route.nearest(...p.xy);
      return { ...p, x:pos.s-origin, distance:pos.d, game:n && n.d < 8 ? profile.height(n.s) : null };
    }).filter((p) => p.distance < 12).sort((a,b) => a.x-b.x);
    if (points.length) series.push({span,points});
  }
  const pts = series.flatMap((s) => s.points), x0 = Math.min(-30,...pts.map((p)=>p.x)), x1 = Math.max(main.length_m+30,...pts.map((p)=>p.x));
  const zs = pts.flatMap((p) => [p.ipr_terrain_z,p.di_z,p.game,...p.archive.map((a)=>a.z),...p.surfaces.map((a)=>a.surface_z ?? a.z)]).filter(valid);
  if (!zs.length) return null;
  const z0 = Math.floor(Math.min(...zs)-1), z1 = Math.ceil(Math.max(...zs)+1), w = 360, h = 210, left = 42, right = 350, top = 12, bottom = 180;
  const X = (x) => left+(x-x0)/(x1-x0)*(right-left), Y = (z) => bottom-(z-z0)/(z1-z0)*(bottom-top);
  const line = (points, get, color, dash = '') => {
    let path = '', drawing = false;
    for (const p of points) { const z = get(p); if (!valid(z)) { drawing = false; continue; }
      path += `${drawing?'L':'M'}${X(p.x).toFixed(1)},${Y(z).toFixed(1)}`; drawing = true; }
    return `<path d="${path}" fill="none" stroke="${color}" stroke-width="1.5" ${dash ? `stroke-dasharray="${dash}"` : ''}/>`;
  };
  const terrain = series[0].points.filter((p)=>valid(p.ipr_terrain_z));
  let svg = `<svg id="heightProfile" viewBox="0 0 ${w} ${h}" role="img" aria-label="Track height profile" style="width:100%;touch-action:none;background:#171b20">`;
  if (main.structure_extent) {
    const [a,b] = main.structure_extent.map((s)=>s-origin);
    svg += `<rect x="${X(a)}" y="${top}" width="${Math.max(0,X(b)-X(a))}" height="${bottom-top}" fill="#746339" opacity=".25"/>`;
  }
  const labelStep = Math.max(1,Math.ceil((z1-z0)*10/(bottom-top)));
  for (let z = z0; z <= z1; z++) {
    svg += `<path d="M${left},${Y(z)}H${right}" stroke="#52565c" stroke-width=".5"/>`;
    if ((z-z0)%labelStep === 0) svg += `<text x="${left-4}" y="${Y(z)+3}" fill="#ddd" font-size="8" text-anchor="end">${z}</text>`;
  }
  if (terrain.length) svg += `<path d="M${X(terrain[0].x)},${bottom} ${terrain.map((p)=>`L${X(p.x)},${Y(p.ipr_terrain_z)}`).join(' ')} L${X(terrain[terrain.length-1].x)},${bottom}Z" fill="#65583e" opacity=".45"/>`;
  const diLabels = new Set();
  for (const {span,points} of series) {
    const dash = span.direction === 'pathBack' ? '4 2' : '';
    const archiveIds = new Set(points.flatMap((p)=>p.archive.filter((a)=>valid(a.z)).map((a)=>a.id)));
    for (const id of archiveIds) svg += line(points,(p)=>p.archive.find((a)=>a.id===id)?.z,'#eeeeee',dash);
    if (span === main) svg += line(points,(p)=>p.game,'#48d5ff','3 2');
    if (span.proposal?.rule === 'linear_di_portals') {
      const [a,b] = span.proposal.ends; svg += line(points,(p)=>a+(b-a)*Math.max(0,Math.min(1,(p.s-span.start_s)/span.length_m)),'#ff9e31','2 2');
    } else if (['review_archive_profile','archive_agrees_with_survey'].includes(span.proposal?.rule))
      svg += line(points,(p)=>p.archive.find((a)=>valid(a.z) && !a.excluded)?.z,'#ff9e31','2 3');
    for (const p of points) {
      for (const s of p.surfaces) {
        const z = s.surface_z ?? s.z;
        if (valid(z)) svg += `<circle cx="${X(p.x)}" cy="${Y(z)}" r="2.1" fill="${s.rail_height_eligible && !s.excluded ? '#eabf53' : 'none'}" stroke="#eabf53"><title>${esc(s.class)} level ${esc(s.level ?? '?')}: ${z.toFixed(2)} m</title></circle>`;
      }
      if (valid(p.di_z)) {
        const x = X(p.x), y = Y(p.di_z), key = `${Math.round(x/20)},${Math.round(y/10)}`;
        svg += `<path d="M${x},${y-3}l3,3 -3,3 -3,-3Z" fill="#e87eff"><title>DI ${p.di_z.toFixed(2)} m</title></path>`;
        if (!diLabels.has(key)) { diLabels.add(key); svg += `<text x="${x+4}" y="${y-4}" fill="#e87eff" font-size="8">${p.di_z.toFixed(2)}</text>`; }
      }
    }
  }
  const reverse = series.filter((s)=>s.span.line === main.line && s.span.direction !== main.direction);
  const rail = (p) => valid(p.di_z) ? p.di_z : p.archive.find((v)=>valid(v.z))?.z;
  for (const p of series[0].points) {
    const a = rail(p);
    if (!valid(a)) continue;
    for (const other of reverse) {
      const q = other.points.reduce((a,b)=>Math.abs(b.x-p.x)<Math.abs(a.x-p.x) ? b : a);
      const b = rail(q);
      if (Math.abs(q.x-p.x)<=3 && Math.hypot(q.xy[0]-p.xy[0],q.xy[1]-p.xy[1])<=8 && valid(b) && Math.abs(a-b)>1)
        svg += `<circle cx="${X(p.x)}" cy="${Y(a)}" r="4" fill="none" stroke="#ff3333"><title>Directions differ by ${Math.abs(a-b).toFixed(2)} m</title></circle>`;
    }
  }
  svg += `<line id="heightCursor" x1="0" x2="0" y1="${top}" y2="${bottom}" stroke="#fff" visibility="hidden"/><text x="${left}" y="198" fill="#ddd" font-size="9">${Math.round(x0)} m</text><text x="${right}" y="198" fill="#ddd" font-size="9" text-anchor="end">${Math.round(x1)} m</text></svg>`;
  const exaggeration = ((bottom-top)/(right-left)*(x1-x0)/(z1-z0)).toFixed(1);
  const layers = [...new Set(Object.values(main.structure.tags || {}).map((t)=>t.layer).filter((x)=>x !== undefined))];
  const embankment = Object.values(main.structure.tags || {}).some((t)=>t.embankment && t.embankment !== 'no');
  return { html:`<div class="dim" style="font-size:11px;line-height:1.2">${esc(main.structure.kind)}${embankment ? ' · embankment' : ''}${layers.length ? ` · layer ${esc(layers.join(', '))}` : ''} · ${esc(main.direction)} · vertical exaggeration ${exaggeration}×<br>archive white · game cyan dashed · survey gold · DI purple · ground brown · proposal orange</div>${svg}`,
    points:series[0].points, x0, x1, left, right, width:w };
}
