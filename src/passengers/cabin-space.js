// SPDX-License-Identifier: AGPL-3.0-or-later
// The project's own passenger lab, street-life-boarding v14 (2026-10-27), dist/traffic/cabin-space.js, as it was (sha256 1b390fba29cbcfb5);
// accepted by the user as "good enough for now" (2026-10-27). #249 step 1: brought in unchanged; step 2 fits it to the game.
// Pure geometry policy shared by offline preparation and local simulation.
export function pointInPolygon(x,z,polygon){let inside=false;for(let i=0,j=polygon.length-1;i<polygon.length;j=i++){
 const [xi,zi]=polygon[i],[xj,zj]=polygon[j];if((zi>z)!==(zj>z)&&x<(xj-xi)*(z-zi)/(zj-zi)+xi)inside=!inside;
 }return inside;
}
export function excludedFromPassengers(layout,x,z){return (layout.exclusions??[]).some(p=>pointInPolygon(x,z,p.polygon));}
export const sideFacing=z=>z<0?Math.PI/2:-Math.PI/2;

export function selectCabinPacking(source,id=source.standing.selected??'aligned'){
 const configuration=source.standing.configurations?.find(c=>c.id===id);if(!configuration)throw new Error(`Unknown standing configuration: ${id}`);
 return {...source,standing:{...source.standing,selected:id,places:configuration.places,placement:configuration.placement,studyPlaceLimit:configuration.places.length}};
}
