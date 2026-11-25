// SPDX-License-Identifier: AGPL-3.0-or-later
// The project's own passenger lab, street-life-boarding v14 (2026-10-27), tools/standing-layouts.mjs (sha256 05f9427daa823977), run in a page
// (tools/cabin.py) instead of Node: no change but the name. Otherwise as it was (#249 step 1).
// Offline rectangular footprint experiments on the classified source floor.
export function prepareStandingLayouts(layout, floor, regions) {
 const width=.558,depth=.357,cell=floor.cell,{nx,nz,xMin,zMin,cat}=floor;
 const sums=[5,6].map(kind=>{const s=new Uint32Array((nx+1)*(nz+1));for(let z=0;z<nz;z++)for(let x=0;x<nx;x++)s[(z+1)*(nx+1)+x+1]=Number(cat[z*nx+x]===kind)+s[z*(nx+1)+x+1]+s[(z+1)*(nx+1)+x]-s[z*(nx+1)+x];return s;});
 function area(x,z,w=width,d=depth){const a=Math.floor((x-w/2-xMin)/cell),b=Math.ceil((x+w/2-xMin)/cell),c=Math.floor((z-d/2-zMin)/cell),e=Math.ceil((z+d/2-zMin)/cell);if(a<0||b>nx||c<0||e>nz)return null;const n=s=>s[e*(nx+1)+b]-s[c*(nx+1)+b]-s[e*(nx+1)+a]+s[c*(nx+1)+a],circulation=n(sums[0]),pockets=n(sums[1]);return circulation+pockets===(b-a)*(e-c)?{circulation,pockets}:null;}
 const configurations=[{id:'aligned',label:'Aligned rows',pitchX:.58,pitchZ:.38,stagger:false},{id:'staggered',label:'Staggered rows',pitchX:.58,pitchZ:.38,stagger:true},{id:'dense',label:'Dense rows · nominal 110 stress',pitchX:.58,pitchZ:.22,stagger:false,target:86}];
 const layouts=configurations.map(config=>{
  let best=[];
  // A common row lattice makes the result legible; sweep its phase offline.
  for(let oz=0;oz<config.pitchZ-.001;oz+=cell)for(let ox=0;ox<config.pitchX-.001;ox+=cell){const points=[];let row=0;
   for(let z=zMin+oz;z<1.4;z+=config.pitchZ,row++)for(let x=xMin+ox+(config.stagger&&row%2?config.pitchX/2:0);x<7.2;x+=config.pitchX){const a=area(x,z);if(!a)continue;const r=regions.find(r=>x>=r.xMin&&x<r.xMax),door=layout.doors.find(d=>d.id===r.id);points.push({x:+x.toFixed(4),z:+z.toFixed(4),doorId:r.id,row,phase:a.circulation?'circulation':'window',circulationFraction:a.circulation/(a.pockets+a.circulation),distanceFromDoor:Math.hypot(x-door.x,z-.6)});}
   if(points.length>best.length)best=points;
  }
  // Fill peripheral rows before circulation; within a row fill away from its door first.
  best.sort((a,b)=>Number(a.phase==='circulation')-Number(b.phase==='circulation')||Math.abs(b.z)-Math.abs(a.z)||b.distanceFromDoor-a.distanceFromDoor||a.x-b.x);
  if(config.target&&best.length<config.target)throw new Error(`Dense rows have only ${best.length} valid destinations`);
  const points=(config.target?best.slice(0,config.target):best).map((p,i)=>({...p,id:`stand-${config.id}-${String(i+1).padStart(3,'0')}`,y:layout.floorY,heading:p.z<0?Math.PI/2:-Math.PI/2,priority:i,footprintHalfExtents:{x:width/2,z:depth/2}}));
  let overlap=0,min=Infinity;for(let i=0;i<points.length;i++)for(let j=i+1;j<points.length;j++){const a=points[i],b=points[j],dx=Math.abs(a.x-b.x),dz=Math.abs(a.z-b.z);if(dx<width-1e-6&&dz<depth-1e-6)overlap++;min=Math.min(min,Math.hypot(dx/width,dz/depth));}
  return {...config,places:points,placement:{kind:config.label,count:points.length,totalWithSeats:points.length+layout.seats.length,referenceAvatarWidth:width,referenceAvatarDepth:depth,shoulderPitchMetres:config.pitchX,depthPitchMetres:config.pitchZ,minimumNormalizedPairDistance:min,overlappingBoundingEnvelopePairs:overlap,windowPlaces:points.filter(p=>p.phase==='window').length,sectorCounts:Object.fromEntries(regions.map(r=>[r.id,points.filter(p=>p.doorId===r.id).length])),limits:'All raster cells under each full rectangle lie on net floor. This is a sampled floor/envelope study, not exact upper-body or seat-contact validation. '+(config.id==='dense'?'Dense rows deliberately overlap current body depth envelopes.':'Standing rectangles are separated; turn sweeps and seated-body clearance remain unvalidated.')}};
 });
 return layouts;
}
