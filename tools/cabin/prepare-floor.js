// SPDX-License-Identifier: AGPL-3.0-or-later
// The project's own passenger lab, street-life-boarding v14 (2026-10-27), tools/prepare-cabin-floor.mjs (sha256 4823b74541ccab48), run in a page
// (tools/cabin.py) instead of Node: the layout, the T3 model and its hash given, the files returned (prepareFloor; the PNG left out);
// more packings on request (opts.packings: the lab's adaptive one with other options, or tools/cabin/packing-search.js's). Otherwise as it was (#249 step 1).
// #249 step 2: opts.cabFixtures false leaves out the fixtures that stand in the driver's cab (their box's centre in its exclusion): the
// cab's control panel (Control_Panel_18, x 5.42-6.94 m) marked by its box the floor behind the cab's partition by the front door, which
// is open floor, part of the circulation area (maintainer, #249). The lab's own files keep them (the default).
/** Offline plan-area estimate from the source mesh plus explicit passenger-space policy. */
import {finishStandingLayouts} from './standing-priority.js';
import {adaptivePacking} from './adaptive-packing.js';
import {searchPacking} from './packing-search.js';
import {loadBodyFootprint} from './body-footprint.js';
import {prepareStandingLayouts} from './standing-layouts.js';
import * as T from 'three';import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {pointInPolygon,excludedFromPassengers} from '../../src/passengers/cabin-space.js';
// layout: prepareLayout's, model: the T3's GLB bytes, sha: their SHA-256; opts.packings: more packings to make
// (adaptivePacking's options), opts.navigationOnly as the Node tool's --navigation-only
export async function prepareFloor(layout,model,sha,opts={}){const files={};
if(sha!==layout.assetSha256)throw new Error('Cabin source hash mismatch');
const source=await new GLTFLoader().parseAsync(model.slice(0),'');source.scene.updateMatrixWorld(true);
const meshes=[];source.scene.traverse(o=>{if(o.isMesh)meshes.push(o);});
function triangles(o){const a=o.geometry.attributes.position,idx=o.geometry.index?.array??Array.from({length:a.count},(_,i)=>i),out=[];for(let i=0;i<idx.length;i+=3)out.push([0,1,2].map(j=>new T.Vector3().fromBufferAttribute(a,idx[i+j]).applyMatrix4(o.matrixWorld)));return out;}
const floors=meshes.filter(o=>['Ground','Ground__Wave'].includes(o.material.name)).flatMap(triangles),wall=source.scene.getObjectByName('Interior_Walls_4'),wallPoints=[];
for(const p of triangles(wall))for(let j=0;j<3;j++){const a=p[j],b=p[(j+1)%3];if((a.y<=1.4&&b.y>1.4)||(b.y<=1.4&&a.y>1.4)){const t=(1.4-a.y)/(b.y-a.y);wallPoints.push([a.x+(b.x-a.x)*t,a.z+(b.z-a.z)*t]);}}
function hull(points){const p=[...new Map(points.map(p=>[p.map(v=>v.toFixed(5)).join(','),p])).values()].sort((a,b)=>a[0]-b[0]||a[1]-b[1]),cross=(a,b,c)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]),half=[];for(const v of p){while(half.length>1&&cross(half.at(-2),half.at(-1),v)<=0)half.pop();half.push(v);}const n=half.length;for(const v of p.slice(0,-1).reverse()){while(half.length>n&&cross(half.at(-2),half.at(-1),v)<=0)half.pop();half.push(v);}half.pop();return half;}
const outline=hull(wallPoints),boxes=meshes.filter(o=>/^(Red|Blue)_Seat_\d+$/.test(o.name)||o.material.name==='Control_Panel'||/^Handles_7[2-7]$/.test(o.name)).map(o=>{const b=new T.Box3().setFromObject(o);return {mesh:o.name,xMin:b.min.x,xMax:b.max.x,zMin:b.min.z,zMax:b.max.z};}).filter(b=>opts.cabFixtures!==false||!excludedFromPassengers(layout,(b.xMin+b.xMax)/2,(b.zMin+b.zMax)/2));
const seatLegroom=layout.seats.map(s=>{const f=s.forward,r={x:-f.z,z:f.x};return {id:s.id,polygon:[[.18,-.26],[.56,-.26],[.56,.26],[.18,.26]].map(([a,b])=>[s.anchor.x+f.x*a+r.x*b,s.anchor.z+f.z*a+r.z*b])};});
const byX=[...layout.doors].sort((a,b)=>a.x-b.x),regions=byX.map((d,i)=>({id:d.id,name:`${d.id} catchment`,xMin:i?(byX[i-1].x+d.x)/2:-7.2,xMax:i<2?(d.x+byX[i+1].x)/2:7.2}));
const categoryNames=['outside','cab','fixtures','legroom','edge margin','circulation','standing pockets'],colors=['#eff4f1','#8c6174','#536573','#d9a968','#b4bfc1','#71adcf','#73bb94'];
const margin=.05,edgeDistance=(x,z)=>Math.min(...outline.map((p,i)=>{const q=outline[(i+1)%outline.length],dx=q[0]-p[0],dz=q[1]-p[1],u=T.MathUtils.clamp(((x-p[0])*dx+(z-p[1])*dz)/(dx*dx+dz*dz),0,1);return Math.hypot(x-p[0]-u*dx,z-p[1]-u*dz);}));
function survey(cell){
 const xMin=-7.2,zMin=-1.4,nx=Math.round(14.4/cell),nz=Math.round(2.8/cell),level=new Uint8Array(nx*nz),steps=new Uint8Array(nx*nz),cabFloor=new Uint8Array(nx*nz),cat=new Uint8Array(nx*nz),counts=Array(7).fill(0),perRegion=regions.map(r=>({...r,categories:Array(7).fill(0)}));
 for(const p of floors){const ys=p.map(v=>v.y),y=ys.reduce((a,b)=>a+b)/3;const isCabFloor=Math.min(...ys)>=layout.floorY-.025&&Math.max(...ys)<=layout.floorY+.12;const isFlat=Math.max(...ys)-Math.min(...ys)<=.025;const mask=!isFlat?null:Math.abs(y-layout.floorY)<.025?level:y>.3&&y<layout.floorY-.06?steps:null;if(!mask&&!isCabFloor)continue;
  const a=p[0],b=p[1],c=p[2],den=(b.z-c.z)*(a.x-c.x)+(c.x-b.x)*(a.z-c.z);if(Math.abs(den)<1e-10)continue;
  const ix0=Math.max(0,Math.floor((Math.min(...p.map(v=>v.x))-xMin)/cell)),ix1=Math.min(nx-1,Math.ceil((Math.max(...p.map(v=>v.x))-xMin)/cell)),iz0=Math.max(0,Math.floor((Math.min(...p.map(v=>v.z))-zMin)/cell)),iz1=Math.min(nz-1,Math.ceil((Math.max(...p.map(v=>v.z))-zMin)/cell));
  for(let iz=iz0;iz<=iz1;iz++)for(let ix=ix0;ix<=ix1;ix++){const x=xMin+(ix+.5)*cell,z=zMin+(iz+.5)*cell,u=((b.z-c.z)*(x-c.x)+(c.x-b.x)*(z-c.z))/den,v=((c.z-a.z)*(x-c.x)+(a.x-c.x)*(z-c.z))/den;if(u>=-1e-8&&v>=-1e-8&&u+v<=1+1e-8){if(mask)mask[iz*nx+ix]=1;if(isCabFloor)cabFloor[iz*nx+ix]=1;}}
 }
 let lowerStepCells=0;for(let iz=0;iz<nz;iz++)for(let ix=0;ix<nx;ix++){
  const i=iz*nx+ix,x=xMin+(ix+.5)*cell,z=zMin+(iz+.5)*cell;if(!pointInPolygon(x,z,outline))continue;if(steps[i]&&!level[i]&&!excludedFromPassengers(layout,x,z))lowerStepCells++;
  if(!level[i]&&!(cabFloor[i]&&excludedFromPassengers(layout,x,z)))continue;let c;
  if(excludedFromPassengers(layout,x,z))c=1;
  else if(boxes.some(b=>x>=b.xMin&&x<=b.xMax&&z>=b.zMin&&z<=b.zMax))c=2;
  else if(seatLegroom.some(p=>pointInPolygon(x,z,p.polygon)))c=3;
  else if(edgeDistance(x,z)<margin)c=4;
  else if(Math.abs(z)<=.30||layout.doors.some(d=>Math.abs(x-d.x)<=d.openingWidth/2&&z>=-.30&&z<=.85))c=5;
  else c=6;
  cat[i]=c;counts[c]++;const r=perRegion.find(r=>x>=r.xMin&&x<r.xMax);r.categories[c]++;
 }
 const areas=Object.fromEntries(categoryNames.slice(1).map((name,i)=>[name,counts[i+1]*cell*cell])),levelDeckArea=counts.slice(1).reduce((a,b)=>a+b,0)*cell*cell,freeArea=areas.circulation+areas['standing pockets'];
 const regionAreas=perRegion.map(r=>({id:r.id,xMin:r.xMin,xMax:r.xMax,levelDeck:r.categories.slice(1).reduce((a,b)=>a+b,0)*cell*cell,cab:r.categories[1]*cell*cell,fixtures:r.categories[2]*cell*cell,legroom:r.categories[3]*cell*cell,edgeMargin:r.categories[4]*cell*cell,circulation:r.categories[5]*cell*cell,pockets:r.categories[6]*cell*cell,free:(r.categories[5]+r.categories[6])*cell*cell}));
 return {cell,xMin,zMin,nx,nz,cat,areas,levelDeckArea,freeArea,lowerStepArea:lowerStepCells*cell*cell,regions:regionAreas};
}
const coarse=survey(.02),fine=survey(.01),target=layout.capacity.scenarioStandingTarget;
const runs=[];for(let i=0;i<coarse.cat.length;){let j=i+1;while(j<coarse.cat.length&&coarse.cat[j]===coarse.cat[i])j++;runs.push(coarse.cat[i],j-i);i=j;}
const navigation={schemaVersion:'0.1.0',assetSha256:layout.assetSha256,cell:coarse.cell,nx:coarse.nx,nz:coarse.nz,xMin:coarse.xMin,zMin:coarse.zMin,categories:categoryNames,runs,seatedFootprint:await loadBodyFootprint(layout,'Sit',{minY:.55}),method:'Source floor classification; root paths admit legroom/circulation/pockets and exclude fixtures, cab, margin, outside. Body-core clearance is explicit in the runtime navigator.'};
files['t3-cabin-navigation.json']=navigation;
if(opts.navigationOnly)return {files,summary:{navigationCells:coarse.cat.length,runs:runs.length/2,seatedFootprint:navigation.seatedFootprint}};
let remainder=target;for(const r of coarse.regions){r.standingTargetShare=target*r.free/coarse.freeArea;r.proportionalAllocation=Math.floor(r.standingTargetShare);remainder-=r.proportionalAllocation;}
for(const r of [...coarse.regions].sort((a,b)=>(b.standingTargetShare%1)-(a.standingTargetShare%1)).slice(0,remainder))r.proportionalAllocation++;
// Compare ordered rectangular layouts; dense remains an explicit nominal stress option.
const seedPlaces=structuredClone((layout.standing.studyPlaces??layout.standing.places).slice(0,6));
const bodyFootprint=await loadBodyFootprint(layout);const configurations=[...prepareStandingLayouts(layout,coarse,regions),adaptivePacking(layout,coarse,bodyFootprint),adaptivePacking(layout,coarse,bodyFootprint,{id:'loose',padding:.028,trials:16}),...(opts.packings??[]).map(o=>o.search?searchPacking(layout,coarse,bodyFootprint,o.search):adaptivePacking(layout,coarse,bodyFootprint,o))];const doorClearances=finishStandingLayouts(layout,coarse,regions,configurations),selected=configurations.find(c=>c.id==='adaptive'),packed=selected.places;
layout.schemaVersion='0.6.0';layout.standing.status='Prepared rotated body-outline and row candidates; static fit does not validate operational capacity';layout.standing.studyPlaces=seedPlaces;layout.standing.configurations=configurations;layout.standing.selected='adaptive';layout.standing.doorClearances=doorClearances;layout.standing.bodyFootprint=bodyFootprint;layout.standing.places=packed;layout.standing.studyPlaceLimit=packed.length;layout.standing.placement=selected.placement;
files['t3-cabin-layout.json']=layout;
const report={schemaVersion:'0.2.0',assetSha256:layout.assetSha256,units:{coordinates:'metres',area:'square metres',density:'people per square metre'},method:'2 cm centre-sampled union of source horizontal passenger-floor triangles (including sloped cab floor only inside its exclusion), clipped to convex hull of inner-wall cross-section at Y=1.4 m; checked against 1 cm sampling',assumptions:{driverCab:layout.exclusions,seatObstacles:'World XZ bounding boxes of all passenger seats, Control_Panel fixtures and six floor-mounted poles; conservative rectangular footprints',legroom:'With all 24 seats occupied: authored forward 0.18–0.56 m × ±0.26 m beside each source cushion anchor; union with fixture footprints',wallEdgeInsetMetres:margin,aisleWidthMetres:.60,doorCirculation:'Main-level door-width strips from Z=-0.30 to +0.85 m; lower steps excluded from stationary standing',regionSplit:'Nearest door by longitudinal X coordinate, not a measured passenger-demand split'},referenceCapacity:layout.capacity,stressPlacement:configurations.find(c=>c.id==='dense').placement,area:{deckFootprint:coarse.levelDeckArea,passengerDeck:coarse.levelDeckArea-coarse.areas.cab,...coarse.areas,freeIncludingCirculation:coarse.freeArea,lowerEntryTreads:coarse.lowerStepArea},resolutionCheck:{coarseMetres:.02,fineMetres:.01,freeAreaAtFineResolution:fine.freeArea,absoluteFreeAreaDifference:Math.abs(fine.freeArea-coarse.freeArea),categoryDifferences:Object.fromEntries(Object.keys(coarse.areas).map(k=>[k,Math.abs(coarse.areas[k]-fine.areas[k])]))},regions:coarse.regions,referenceLoad:{seated:layout.seats.length,standing:target,personsPerFreeSquareMetre:target/coarse.freeArea,squareMetresPerStandingPerson:coarse.freeArea/target,personsPerPocketSquareMetre:target/coarse.areas['standing pockets'],allocationMethod:'86 distributed proportionally to net point-floor area including circulation; descriptive load scenario, not fitted avatar locations'},densityScenarios:[2,4,6,8].map(density=>({density,standingByArea:Math.floor(coarse.freeArea*density),totalByArea:layout.seats.length+Math.floor(coarse.freeArea*density)})),limits:['Model-space estimate, not a surveyed floor plan or certified capacity calculation.','Floor holes, simplified furniture, convex wall outline and authored allowances affect results more than numerical sampling alone.','Free area is point-floor area, not a body-centre packing solution; disconnected slivers and seated feet/body shapes need further review.','Circulation is part of the high-load reference denominator; preserving it empty leaves only the standing pockets.','Reference capacity does not establish a comfort density or support 86 collision-free current avatars.']};
files['t3-floor-space.json']=report;
// Exact classified raster rendered as vector runs; no decorative geometry or guessed proportions.
const sx=96,ox=58,oy=90,svg=[`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1500 560" role="img" aria-labelledby="title desc"><title id="title">T3 passenger floor-space estimate</title><desc id="desc">Cab, fixture and legroom exclusions; circulation and standing pockets. Front is right. Source geometry with authored policy.</desc><rect width="1500" height="560" fill="#eff4f1"/><g font-family="Arial,sans-serif" fill="#183c40"><text x="58" y="35" font-size="24">T3 · passenger floor-space estimate</text><text x="58" y="60" font-size="16">Rear ←  metres / +X forward  → Front · source mesh + authored exclusions</text></g>`];
for(let iz=0;iz<coarse.nz;iz++){let start=0;for(let ix=1;ix<=coarse.nx;ix++)if(ix===coarse.nx||coarse.cat[iz*coarse.nx+ix]!==coarse.cat[iz*coarse.nx+start]){const c=coarse.cat[iz*coarse.nx+start];if(c)svg.push(`<rect x="${(ox+start*coarse.cell*sx).toFixed(2)}" y="${(oy+iz*coarse.cell*sx).toFixed(2)}" width="${((ix-start)*coarse.cell*sx+.03).toFixed(2)}" height="${(coarse.cell*sx+.03).toFixed(2)}" fill="${colors[c]}"/>`);start=ix;}}
const X=x=>ox+(x-coarse.xMin)*sx,Z=z=>oy+(z-coarse.zMin)*sx;
svg.push(`<polygon points="${outline.map(([x,z])=>`${X(x).toFixed(2)},${Z(z).toFixed(2)}`).join(' ')}" fill="none" stroke="#23474b" stroke-width="2"/>`);
for(const d of layout.doors)svg.push(`<g fill="#183c40" font-family="Arial,sans-serif" font-size="17"><text x="${X(d.x)}" y="397" text-anchor="middle">${d.id} door</text><text x="${X(d.x)}" y="420" text-anchor="middle">${coarse.regions.find(r=>r.id===d.id).free.toFixed(1)} m² net floor</text></g>`);
for(const r of coarse.regions.slice(1))svg.push(`<line x1="${X(r.xMin)}" x2="${X(r.xMin)}" y1="85" y2="365" stroke="#183c40" stroke-width="1" stroke-dasharray="5 5"/>`);
svg.push(`<text x="${X(6.22)}" y="${Z(-.25)}" text-anchor="middle" font-family="Arial,sans-serif" font-size="18" fill="white">DRIVER</text>`);
for(let i=1;i<7;i++){const x=58+(i-1)%3*470,y=460+Math.floor((i-1)/3)*36;svg.push(`<rect x="${x}" y="${y-15}" width="20" height="20" fill="${colors[i]}"/><text x="${x+30}" y="${y}" font-family="Arial,sans-serif" font-size="17" fill="#183c40">${categoryNames[i]} · ${coarse.areas[categoryNames[i]].toFixed(1)} m²</text>`);}
svg.push('<text x="58" y="542" font-family="Arial,sans-serif" font-size="14" fill="#456367">Approximate plan areas, not a certified layout or body-packing result. Source T3: SimonStrikesBack + conflig, CC BY-NC 4.0.</text></svg>');
files['floor-space.svg']=svg.join('\n');
const loadSvg=svg.join('\n').replace('</svg>',packed.map(p=>`<polygon points="${p.footprintWorld.map(([x,z])=>`${X(x)},${Z(z)}`).join(' ')}" fill="#20373e" fill-opacity=".15" stroke="#8a3156" stroke-width="1"/>`).join('')+'</svg>');files['capacity-layout.svg']=loadSvg;
const summary={stressPlacement:configurations.find(c=>c.id==='dense').placement,area:report.area,resolutionCheck:report.resolutionCheck,regions:report.regions,referenceLoad:report.referenceLoad};

for(const c of configurations){const map=svg.join('\n').replace('</svg>',c.places.map(p=>`<polygon points="${p.footprintWorld.map(([x,z])=>`${X(x)},${Z(z)}`).join(' ')}" fill="${p.phase==='window'?'#225b43':p.phase==='doorway'?'#813e68':'#1d4d76'}" fill-opacity=".40" stroke="#173c40" stroke-width="1"/>`).join('')+'</svg>');files[`packing-${c.id}.svg`]=map;}summary.placements=configurations.map(c=>({id:c.id,...c.placement}));return {files,summary};}
