// SPDX-License-Identifier: AGPL-3.0-or-later
// The project's own passenger lab, street-life-boarding v14 (2026-10-27), dist/traffic/packing-geometry.js, as it was (sha256 3fc8675a1161ac32);
// accepted by the user as "good enough for now" (2026-10-27). #249 step 1: brought in unchanged; step 2 fits it to the game.
// Convex XZ footprints shared by offline preparation, maps and checks.
export function transformFootprint(polygon,x,z,heading){const c=Math.cos(heading),s=Math.sin(heading);return polygon.map(([u,v])=>[x+c*u+s*v,z-s*u+c*v]);}
export function convexOverlap(a,b,epsilon=1e-8){for(const p of [a,b])for(let i=0;i<p.length;i++){const v=p[i],q=p[(i+1)%p.length],nx=q[1]-v[1],nz=v[0]-q[0];let loA=Infinity,hiA=-Infinity,loB=Infinity,hiB=-Infinity;for(const x of a){const d=x[0]*nx+x[1]*nz;loA=Math.min(loA,d);hiA=Math.max(hiA,d);}for(const x of b){const d=x[0]*nx+x[1]*nz;loB=Math.min(loB,d);hiB=Math.max(hiB,d);}if(hiA<=loB+epsilon||hiB<=loA+epsilon)return false;}return true;}
export function bounds(polygon){return {xMin:Math.min(...polygon.map(v=>v[0])),xMax:Math.max(...polygon.map(v=>v[0])),zMin:Math.min(...polygon.map(v=>v[1])),zMax:Math.max(...polygon.map(v=>v[1]))};}
export function boundsOverlap(a,b){return a.xMin<b.xMax&&a.xMax>b.xMin&&a.zMin<b.zMax&&a.zMax>b.zMin;}
