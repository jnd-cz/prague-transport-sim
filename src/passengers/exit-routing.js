// SPDX-License-Identifier: AGPL-3.0-or-later
// The project's own passenger lab, street-life-boarding v14 (2026-10-27), dist/traffic/exit-routing.js, as it was (sha256 6caa0fada4afea2b);
// accepted by the maintainer as good enough for now (2026-10-27). #249 step 1: brought in unchanged; step 2 fits it to the game.
// #249: changed: each door's service time and the walk speed options (the lab's 2 s and 0.95 m/s by default).
// Bounded stationary-cabin routing policy, independent of presentation.
// Contiguous X groups avoid sending opposing streams through one another.
// (#249: service, s a person through each door by its id, 2 for any door by default, the lab's; walk m/s for the reach)
export function planExitDoors(passengers, doors, {policy='balanced', active=[], service={}, walk=.95}={}) {
 const ordered=[...doors].sort((a,b)=>a.x-b.x),people=[...passengers].sort((a,b)=>a.x-b.x||a.index-b.index),assignment=new Map();
 if(policy==='boarding'){
  for(const a of people)assignment.set(a.id,a.doorBufferId??a.boardedDoorId??a.doorId);
 }else{
  const costs=ordered.map(d=>{
   const backlog=active.filter(a=>a.doorId===d.id&&a.egressClearAt==null).length;
   const prefix=[0];const per=service[d.id]??2;for(const a of people)prefix.push(prefix.at(-1)+(Math.abs(a.x-d.x)+Math.abs(a.z-.04))/walk);
   return (lo,hi)=>{if(lo===hi)return {eta:backlog*per,travel:0};const travel=prefix[hi]-prefix[lo],reach=Math.max(...people.slice(lo,hi).map(a=>(Math.abs(a.x-d.x)+Math.abs(a.z-.04))/walk));return {eta:(hi-lo+backlog)*per+reach,travel};};
  });
  let best=null;for(let i=0;i<=people.length;i++)for(let j=i;j<=people.length;j++){
   const ranges=[[0,i],[i,j],[j,people.length]];if(ranges.some(([lo,hi],k)=>people.slice(lo,hi).some(a=>a.doorBufferId&&a.doorBufferId!==ordered[k].id)))continue;const c=ranges.map(([lo,hi],k)=>costs[k](lo,hi)),score=Math.max(...c.map(c=>c.eta))+.015*c.reduce((n,c)=>n+c.travel,0);
   if(!best||score<best.score-1e-8)best={score,ranges};
  }
  best.ranges.forEach(([lo,hi],i)=>people.slice(lo,hi).forEach(a=>assignment.set(a.id,ordered[i].id)));
 }
 return {assignment,summary:{policy,model:'Contiguous longitudinal groups; estimated 2 s/person service + walking/backlog; heuristic, not an exact fastest-path solver',counts:Object.fromEntries(ordered.map(d=>[d.id,people.filter(a=>assignment.get(a.id)===d.id).length])),changedBoardingDoor:people.filter(a=>assignment.get(a.id)!==(a.boardedDoorId??a.doorId)).length}};
}
