// SPDX-License-Identifier: AGPL-3.0-or-later
// The project's own passenger lab, street-life-boarding v14 (2026-10-27), tools/standing-priority.mjs (sha256 9838298cea068874), run in a page
// (tools/cabin.py) instead of Node: imports from src/passengers. Otherwise as it was (#249 step 1).
import {transformFootprint,convexOverlap,bounds} from '../../src/passengers/packing-geometry.js';
export function finishStandingLayouts(layout,floor,regions,configurations){
 const zones=layout.doors.map(d=>({id:d.id,xMin:d.x-d.openingWidth/2-.15,xMax:d.x+d.openingWidth/2+.15,zMin:-.55,zMax:1.1}));
 const rectangle=[[-.1785,-.279],[.1785,-.279],[.1785,.279],[-.1785,.279]];
 for(const config of configurations){for(const p of config.places){p.footprintPolygon??=rectangle;p.footprintWorld=transformFootprint(p.footprintPolygon,p.x,p.z,p.heading);const b=bounds(p.footprintWorld),region=regions.find(r=>p.x>=r.xMin&&p.x<r.xMax);p.doorId=region.id;p.distanceFromDoor=Math.hypot(p.x-layout.doors.find(d=>d.id===region.id).x,p.z-.6);
   const buffer=zones.find(z=>convexOverlap(p.footprintWorld,[[z.xMin,z.zMin],[z.xMax,z.zMin],[z.xMax,z.zMax],[z.xMin,z.zMax]]));p.doorBufferId=buffer?.id??null;
   // Priority is based on the fitted body's root area, not whether a toe merely
   // crosses the circulation paint. Fit/exclusion checks still use the full hull.
   const circulation=Math.abs(p.z)<=.30||layout.doors.some(d=>Math.abs(p.x-d.x)<=d.openingWidth/2&&p.z>=-.30&&p.z<=.85);
   p.phase=buffer?'doorway':circulation?'circulation':'window';p.phaseRank=buffer?2:circulation?1:0;
  }
  config.places.sort((a,b)=>a.phaseRank-b.phaseRank||b.distanceFromDoor-a.distanceFromDoor||a.x-b.x);config.places.forEach((p,i)=>p.priority=i);
  Object.assign(config.placement,{windowPlaces:config.places.filter(p=>p.phase==='window').length,circulationPlaces:config.places.filter(p=>p.phase==='circulation').length,doorwayPlaces:config.places.filter(p=>p.phase==='doorway').length,sectorCounts:Object.fromEntries(regions.map(r=>[r.id,config.places.filter(p=>p.doorId===r.id).length]))});
 }
 return zones;
}
