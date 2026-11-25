// SPDX-License-Identifier: AGPL-3.0-or-later
// The project's own passenger lab, street-life-boarding v14 (2026-10-27), tools/adaptive-packing.mjs (sha256 bd89520d320d4976), run in a page
// (tools/cabin.py) instead of Node: imports from tools/cabin and src/passengers. Otherwise as it was (#249 step 1).
import {inflate} from './body-footprint.js';
import {transformFootprint,convexOverlap,bounds,boundsOverlap} from '../../src/passengers/packing-geometry.js';
export function adaptivePacking(layout,floor,body,{id='adaptive',padding=.008,trials=24}={}){
 const {cell,nx,nz,xMin,zMin,cat}=floor,polygon=inflate(body.polygon,padding),angles=[0,Math.PI/2,Math.PI,-Math.PI/2,Math.PI/4,-Math.PI/4,3*Math.PI/4,-3*Math.PI/4];
 const forms=angles.map(heading=>{const points=transformFootprint(polygon,0,0,heading),b=bounds(points),mask=[];for(let iz=Math.floor(b.zMin/cell-.5);iz<=Math.ceil(b.zMax/cell+.5);iz++)for(let ix=Math.floor(b.xMin/cell-.5);ix<=Math.ceil(b.xMax/cell+.5);ix++){const a=ix*cell-cell/2,z=iz*cell-cell/2,square=[[a,z],[a+cell,z],[a+cell,z+cell],[a,z+cell]];if(convexOverlap(points,square,-1e-10))mask.push([ix,iz]);}return {heading,points,b,mask};});
 const candidates=[];let n=0;for(let iz=0;iz<nz;iz+=2)for(let ix=0;ix<nx;ix+=2){const x=xMin+(ix+.5)*cell,z=zMin+(iz+.5)*cell;
  for(let f=0;f<forms.length;f++){const form=forms[f];if(!form.mask.every(([dx,dz])=>{const xx=ix+dx,zz=iz+dz;return xx>=0&&xx<nx&&zz>=0&&zz<nz&&cat[zz*nx+xx]>=5;}))continue;
   const points=form.points.map(([a,b])=>[a+x,b+z]),b=bounds(points);candidates.push({x,z,heading:form.heading,polygon:points,bounds:b,n:n++,f});
  }
 }
 const hash=(n,seed)=>{let x=(n+1)^Math.imul(seed+1,0x9e3779b1);x=Math.imul(x^(x>>>16),0x85ebca6b);x=Math.imul(x^(x>>>13),0xc2b2ae35);return ((x^(x>>>16))>>>0)/4294967296;};
 function pack(order,initial=[]){const selected=[...initial],grid=new Map();const keys=b=>{const out=[];for(let z=Math.floor(b.zMin/.6);z<=Math.floor(b.zMax/.6);z++)for(let x=Math.floor(b.xMin/.6);x<=Math.floor(b.xMax/.6);x++)out.push(`${x}:${z}`);return out;};const add=p=>{for(let k of keys(p.bounds)){if(!grid.has(k))grid.set(k,[]);grid.get(k).push(p);}};selected.forEach(add);
  for(const p of order){const nearby=new Set(keys(p.bounds).flatMap(k=>grid.get(k)??[]));if([...nearby].some(q=>boundsOverlap(p.bounds,q.bounds)&&convexOverlap(p.polygon,q.polygon)))continue;selected.push(p);add(p);}return selected;
 }
 let best=[];for(let seed=0;seed<trials;seed++){
  // Vary local phase and scan direction; no fixed rows or forced side-facing.
  const order=[...candidates].sort((a,b)=>{const score=p=>seed<8?(seed%2?p.x:-p.x)*1.7+(seed%4<2?p.z:-p.z)*.8+hash(p.n,seed)*.20:(hash(p.n,seed)*1.4+Math.abs(p.z)*-.12);return score(a)-score(b);});
  const packed=pack(order);if(packed.length>best.length)best=packed;
 }
 // Local remove-and-refill search allows the lattice phases around a pocket to change.
 for(let seed=0;seed<40;seed++){const pivot=best[Math.floor(hash(seed,77)*best.length)],radius=.65+hash(seed,91)*.65,kept=best.filter(p=>Math.hypot(p.x-pivot.x,p.z-pivot.z)>radius),order=[...candidates].sort((a,b)=>hash(a.n,seed+50)-hash(b.n,seed+50)),next=pack(order,kept);if(next.length>best.length)best=next;}
 const places=best.map((p,i)=>({id:`stand-${id}-${String(i+1).padStart(3,'0')}`,x:+p.x.toFixed(4),z:+p.z.toFixed(4),y:layout.floorY,heading:p.heading,footprintPolygon:polygon,footprintWorld:p.polygon,footprintHalfExtents:{x:Math.max(Math.abs(p.bounds.xMin-p.x),Math.abs(p.bounds.xMax-p.x)),z:Math.max(Math.abs(p.bounds.zMin-p.z),Math.abs(p.bounds.zMax-p.z))}}));
 return {id,label:padding>.02?'Adaptive · extra clearance':'Adaptive · fitted outlines',places,bodyFootprint:body,paddingMetres:padding,search:{candidates:candidates.length,trials,localRefills:40,gridMetres:.04},placement:{kind:padding>.02?'Adaptive · extra clearance':'Adaptive · fitted outlines',count:places.length,totalWithSeats:places.length+24,referenceAvatarWidth:body.width,referenceAvatarDepth:body.depth,overlappingBoundingEnvelopePairs:0,overlapMetric:'Rotated inflated convex body outlines; zero intersection pairs',limits:'Complete Idle-phase body projection plus padding, conservatively fitted to 2 cm net-floor cells. Static pose packing, not moving-body clearance or an optimal packing proof.'}};
}
