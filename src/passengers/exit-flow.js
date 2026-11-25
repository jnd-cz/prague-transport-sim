// SPDX-License-Identifier: AGPL-3.0-or-later
// The project's own passenger lab, street-life-boarding v14 (2026-10-27), dist/traffic/exit-flow.js, as it was (sha256 776c708cc81c7d75);
// accepted by the user as "good enough for now" (2026-10-27). #249 step 1: brought in unchanged; step 2 fits it to the game.
// #249: changed: the alighting pace an option (PACE, the lab's values by default: the lab's times hold).
import {createCabinNavigator,pointPolygonDistance} from './cabin-navigation.js';
// Cooperative time/space reservations for the stationary cabin's authored exit routes.
// No scene objects. Optional root-core/waiting-outline guard is a bounded experiment.
// (#249: the alighting pace as an option, PACE the lab's values: walk m/s, foot s a transfer down the steps, gap and stairGap m
// between centres, laneSteps the least planner steps between a lane's stair entries)
export const PACE={walk:.95,foot:.64,gap:.64,stairGap:.74,laneSteps:30};
// The game's alighting pace (#249; the user, 2026-11-25: "going out from tram shoul be always faster than filling it to full
// capacity"): down the steps a foot in 0.44 s (up, boarding: the lab's 0.64), a brisk 1.2 m/s, 0.52 m between the centres of
// two alighters of a door (the body outline is 0.558 m wide with the arms: side by side they brush shoulders, as a crowd
// squeezing out; boarders keep their distance only to the one ahead in their own stream), 0.64 m on one stream's steps, a
// lane's stair entries 1 s apart. On the game's T3, a full car empties before it fills on every packing: 105 (16 headings on
// 2 cm) out of the doors in 34.1 s, in through them in 39.7 s (the lab's pace: out in 53.2 s; 0.58 m between centres: 36.1 s,
// and two looser packings out as slowly as in). Measured slower or barely faster, left out: letting a door's two streams take
// unequal counts, and the inner alighters setting off before the doorway group has left its places.
export const GAME_PACE={walk:1.2,foot:.44,gap:.52,stairGap:.64,laneSteps:20};
const STEP=.05,lerp=(a,b,t)=>a+(b-a)*t,smooth=t=>t*t*(3-2*t),tau=Math.PI*2;
const turn=(a,b,t)=>a+(((b-a+Math.PI)%tau+tau)%tau-Math.PI)*t;
function stairSample(door,floorY,t,scale,startZ=.37,foot=.64){
 const up=[{z:1.58,y:door.platformY},...door.entryLevels.map((b,i)=>({z:i===2?.60:(b.zMin+b.zMax)/2+.08,y:b.y})),{z:startZ,y:floorY}],points=up.reverse().concat({z:1.85,y:door.platformY}),duration=foot,index=Math.min(points.length-2,Math.floor(t/duration)),u=Math.min(1,(t-index*duration)/duration),moving=index%2,feet=[{...points[0]},{...points[0]}];
 for(let k=0;k<index;k++)feet[k%2]={...points[k+1]};const start=feet[moving],end=points[index+1],v=smooth(u);feet[moving]={z:lerp(start.z,end.z,v),y:lerp(start.y,end.y,v)+.04*Math.sin(Math.PI*u)};
 const z=(feet[0].z+feet[1].z)/2,y=(feet[0].y+feet[1].y)/2,targets=feet.map(f=>({x:-(z-f.z)/scale,y:f.y-y+.107})),hipsHeight=Math.min(.94,...targets.map(f=>f.y+.015+Math.sqrt(Math.max(.02,.83*.83-f.x*f.x))));
 return {z,y,legPose:{hipsHeight,feet:targets},animationPhase:(index+u)/2};
}
export function traceExit(a,c,layout,route=null,pace=PACE){
 const landingZ=route?.at(-1)?.z??.37;let p={x:a.x,y:a.y,z:a.z,heading:a.heading,distance:0,speed:0,motion:a.seatId?'Sit':'Idle',legPose:null,poseBlend:null,phase:'rise',released:false,outside:false,egress:false};const frames=[{...p}];
 const append=o=>{p={...p,...o};frames.push(p);};
 function walk(x,y,z,phase='walk'){
  const from={...p},length=Math.hypot(x-p.x,z-p.z),steps=Math.max(1,Math.ceil(length/pace.walk/STEP));let previous=0,heading=p.heading;
  for(let i=1;i<=steps;i++){const u=i/steps,travel=length*u;heading=turn(heading,Math.atan2(-(z-from.z),x-from.x),Math.min(1,STEP*8));append({x:lerp(from.x,x,u),z:lerp(from.z,z,u),y:lerp(from.y,y,u),heading,distance:from.distance+travel,speed:(travel-previous)/STEP,motion:length>.001?'Walk':'Idle',poseBlend:null,legPose:null,phase});previous=travel;}
 }
 if(a.seatId){const from={...p},steps=Math.ceil(.7/STEP);for(let i=1;i<=steps;i++)append({y:lerp(from.y,layout.floorY,smooth(i/steps)),poseBlend:{from:'Sit',to:'Idle',weight:smooth(i/steps)},speed:0,motion:'Idle'});}
 if(route){if(a.seatId){const seat=layout.seats.find(s=>s.id===a.seatId);walk(seat.anchor.x+seat.forward.x*.23,layout.floorY,Math.sign(a.z)*.43);p={...p,released:true};frames[frames.length-1]=p;}for(const point of route.slice(1)){walk(point.x,layout.floorY,point.z);if(!a.doorBufferId&&p.distance>=.35){p={...p,released:true};frames[frames.length-1]=p;}}p={...p,released:true};frames[frames.length-1]=p;}
 else if(a.doorBufferId){walk(c.x,layout.floorY,.37);p={...p,released:true};frames[frames.length-1]=p;}
 else{
  const seat=a.seatId?layout.seats.find(s=>s.id===a.seatId):null,x=seat?seat.anchor.x+seat.forward.x*.23:a.x,neck=c.door.id==='Front'?5.10:c.door.x,sign=Math.sign(neck-x)||1,raw=c.door.id==='Front'?Math.min(5.10,neck-sign*.70):neck-sign*.70,fork=sign>0?Math.max(raw,x):Math.min(raw,x);
  if(seat)walk(x,layout.floorY,Math.sign(a.z)*.43);walk(x,layout.floorY,.04);p={...p,released:true};frames[frames.length-1]=p;walk(fork,layout.floorY,.04);walk(c.x,layout.floorY,.37);
 }
 const entryIndex=frames.length;let lastZ=p.z;const descent=5*pace.foot;for(let i=1;i<=Math.ceil(descent/STEP);i++){const sample=stairSample(c.door,layout.floorY,Math.min(descent,i*STEP),layout.fitProfile.scale.x,landingZ,pace.foot),distance=p.distance+Math.abs(sample.z-lastZ);append({...sample,x:c.x,heading:-Math.PI/2,distance,speed:Math.abs(sample.z-lastZ)/STEP,motion:'TramStepDown',poseBlend:null,phase:'stairs'});lastZ=sample.z;}
 p={...p,legPose:null,outside:true,y:c.door.platformY};frames[frames.length-1]=p;
 walk(c.x+(c.lane===0?-.95:.95),c.door.platformY,2.05,'egress');p={...p,egress:true};frames[frames.length-1]=p;walk(c.x+(c.lane===0?-.95:.95),c.door.platformY,5.8,'platform');
 for(const p of frames){const cx=Math.floor(p.x/.8),cz=Math.floor(p.z/.8);p.key=`${cx}:${cz}`;p.keys=[];for(let x=cx-1;x<=cx+1;x++)for(let z=cz-1;z<=cz+1;z++)p.keys.push(`${x}:${z}`);}
 return {frames,entryIndex,released:frames.findIndex(f=>f.released),outside:frames.findIndex(f=>f.outside),egress:frames.findIndex(f=>f.egress),channel:c};
}
function traceYield(a,path,target,layout,c){let p={x:a.x,y:a.y,z:a.z,heading:a.heading,distance:0,speed:0,motion:'Idle',legPose:null,poseBlend:null,phase:'yield',released:false,outside:false,egress:false};const frames=[p];for(const goal of path.slice(1)){const from=p,distance=Math.hypot(goal.x-p.x,goal.z-p.z),n=Math.max(1,Math.ceil(distance/.95/STEP));for(let i=1;i<=n;i++){const u=i/n;p={...p,x:lerp(from.x,goal.x,u),z:lerp(from.z,goal.z,u),y:layout.floorY,heading:turn(p.heading,Math.atan2(-(goal.z-from.z),goal.x-from.x),STEP*8),distance:from.distance+distance*u,speed:distance/n/STEP,motion:'Walk'};frames.push(p);}}const heading=p.heading;for(let i=1;i<=8;i++){p={...p,heading:turn(heading,target.heading,smooth(i/8)),speed:0,motion:'Idle'};frames.push(p);}for(const p of frames){const cx=Math.floor(p.x/.8),cz=Math.floor(p.z/.8);p.key=`${cx}:${cz}`;p.keys=[];for(let x=cx-1;x<=cx+1;x++)for(let z=cz-1;z<=cz+1;z++)p.keys.push(`${x}:${z}`);}return {frames,entryIndex:Infinity,released:Infinity,outside:Infinity,egress:Infinity,channel:c};}
export function createExitFlow(layout,channels,{pace=PACE,onRelease,onOutside,onEgress,onDepart,onAdmission,avoidWaiting=false,allActors=()=>[],onNeedYield,onYieldAdmission,onYieldComplete}={}){
 const groups=new Map(layout.doors.map(d=>[d.id,{time:0,table:new Map(),plans:new Map(),bufferRelease:0,assigned:[0,0],nextEntry:[0,0]}]));
 const pending=[],blockedPlans=new Map(),navigator=avoidWaiting?createCabinNavigator(layout):null;let detours=0,yields=0,wake=false;
 const stationary=a=>['seated','standing','exit queue','yield queue'].includes(a.stage)&&!a.exiting;
 function retryBlocked(){for(const [id,a]of blockedPlans){a.navigationBlocked=null;pending.push(a);}blockedPlans.clear();}
 function conflicts(group,trace,start){
  for(let i=0;i<trace.frames.length;i++){const p=trace.frames[i],table=group.table.get(start+i);if(!table)continue;for(const key of p.keys)for(const b of table.get(key)??[]){const sameEntry=b.channel===trace.channel.id&&(p.phase==='stairs'||b.phase==='stairs')&&Math.abs(p.x-b.x)<.20,gap=sameEntry?pace.stairGap:pace.gap;if((p.x-b.x)**2+(p.z-b.z)**2<gap*gap)return true;}}
  return false;
 }
 function reserve(group,trace,start){for(let i=0;i<trace.frames.length;i++){const p=trace.frames[i],t=start+i;if(!group.table.has(t))group.table.set(t,new Map());const table=group.table.get(t),key=p.key;if(!table.has(key))table.set(key,[]);table.get(key).push({x:p.x,z:p.z,phase:p.phase,channel:trace.channel.id});}}
 function schedule(passengers){
  for(const group of groups.values()){group.assigned=channels.filter(c=>groups.get(c.door.id)===group).map(c=>[...group.plans.values()].filter(p=>p.c.id===c.id&&p.kind!=='yield').length);}
  if(avoidWaiting)retryBlocked();pending.push(...passengers);pending.sort((a,b)=>Number(!a.doorBufferId)-Number(!b.doorBufferId)||Math.abs(a.x-layout.doors.find(d=>d.id===a.doorId).x)+Math.abs(a.z-.37)-Math.abs(b.x-layout.doors.find(d=>d.id===b.doorId).x)-Math.abs(b.z-.37)||a.index-b.index);
 }
 function prepare(count=2){for(let n=0;n<count&&pending.length;n++){
  const a=pending.shift(),failures=[],group=groups.get(a.doorId),minimumAssigned=Math.min(...group.assigned),options=channels.filter(c=>c.door.id===a.doorId&&(navigator||group.assigned[c.lane]===minimumAssigned)).map(c=>{
   let route=null,dependencyStart=0;
   if(navigator){const seat=a.seatId?layout.seats.find(s=>s.id===a.seatId):null,startPoint=seat?{x:seat.anchor.x+seat.forward.x*.23,z:Math.sign(a.z)*.43}:{x:a.x,z:a.z},waiting=allActors().filter(b=>b!==a&&stationary(b)),hard=waiting.filter(b=>!group.plans.has(b.id));for(const g of groups.values())for(const p of g.plans.values())if(p.kind==='yield')hard.push({...p.a,id:p.a.id+':yield-target',x:p.target.x,z:p.target.z,heading:p.target.heading,standingId:p.target.id,seatId:null});
    const result=navigator.route(startPoint,{x:c.x,z:c.door.id==='Front'&&c.lane===1?.55:.37},hard);if(!result.path){failures.push({reason:result.reason,blockerIds:result.blockerIds??[]});return null;}
    const hardShapes=navigator.blockers(hard);if(seat&&!navigator.bodySegmentClear({x:a.x,z:a.z},startPoint,hardShapes)){failures.push({reason:'Seat escape is blocked',blockerIds:hardShapes.filter(b=>!navigator.bodySegmentClear({x:a.x,z:a.z},startPoint,[b])).map(b=>b.id)});return null;}
    route=result.path;
    a.navigationDetour=result.detour;
   }
   const trace=traceExit(a,c,layout,route,pace);if(navigator){const hard=allActors().filter(b=>b!==a&&stationary(b)&&!group.plans.has(b.id)),shapes=navigator.blockers(hard),hits=shapes.filter(b=>trace.frames.some(p=>pointPolygonDistance(p.x,p.z,b.polygon)<navigator.radius+.02));if(hits.length){failures.push({reason:'Authored seat escape or stair stream crosses a waiting occupant',blockerIds:hits.map(b=>b.id)});return null;}for(const b of allActors().filter(b=>b!==a&&stationary(b)&&group.plans.has(b.id))){const shape=navigator.blockers([b])[0];if(trace.frames.some(p=>pointPolygonDistance(p.x,p.z,shape.polygon)<navigator.radius+.02))dependencyStart=Math.max(dependencyStart,group.plans.get(b.id).start+1);}}let start=Math.max(Math.ceil(group.time/STEP),dependencyStart,group.nextEntry[c.lane]-trace.entryIndex);if(!a.doorBufferId)start=Math.max(start,group.bufferRelease);
   while(conflicts(group,trace,start)){start+=4;if(start>group.time/STEP+6000)throw new Error('Exit route reservation horizon exceeded');}
   return {a,c,trace,start,cost:start+trace.outside+(navigator?Math.max(0,group.assigned[c.lane]-minimumAssigned)*2:0)};
  }).filter(Boolean).sort((a,b)=>a.cost-b.cost||a.c.lane-b.c.lane),plan=options[0];if(!plan){a.navigationBlocked={reason:[...new Set(failures.map(f=>f.reason))].join('; '),blockerIds:[...new Set(failures.flatMap(f=>f.blockerIds))]};
   if(navigator&&onNeedYield){const result=onNeedYield(a.navigationBlocked?.blockerIds??[],a,navigator);if(result){const b=result.actor,c=channels.find(c=>c.door.id===a.doorId),trace=traceYield(b,result.path,result.target,layout,c);let start=Math.ceil(group.time/STEP);while(conflicts(group,trace,start))start+=4;group.plans.set(b.id,{a:b,c,trace,start,kind:'yield',target:result.target});b.stage='yield queue';b.yieldDoorId=a.doorId;yields++;reserve(group,trace,start);}}
   blockedPlans.set(a.id,a);continue;
  }a.navigationBlocked=null;if(a.navigationDetour)detours++;
  group.plans.set(a.id,plan);group.assigned[plan.c.lane]++;group.nextEntry[plan.c.lane]=plan.start+plan.trace.entryIndex+pace.laneSteps;a.channel=plan.c.id;a.exitScheduledAt=plan.start*STEP-group.time;reserve(group,plan.trace,plan.start);if(a.doorBufferId)group.bufferRelease=Math.max(group.bufferRelease,plan.start+plan.trace.released+1);
 }}
 function update(dt,doorsOpen){for(const [id,group]of groups){const open=typeof doorsOpen==='boolean'?doorsOpen:doorsOpen[id];if(open)group.time+=dt;
   for(const [id,plan]of group.plans){const {a,trace,c}=plan,t=group.time/STEP-plan.start;if(t<0)continue;if(plan.baseDistance==null){if(plan.kind==='yield'){a.yielding=true;a.yieldAdmittedAt=group.time;onYieldAdmission?.(a,plan.target);}else{a.exiting=true;a.exitAdmittedAt=group.time;}if(avoidWaiting)wake=true;plan.baseDistance=a.distanceMetres;if(plan.kind!=='yield')onAdmission?.(a);}
    const i=Math.min(trace.frames.length-1,Math.floor(t+1e-8)),v=Math.min(1,Math.max(0,t-i)),p=trace.frames[i],q=trace.frames[Math.min(i+1,trace.frames.length-1)];
    Object.assign(a,{x:lerp(p.x,q.x,v),y:lerp(p.y,q.y,v),z:lerp(p.z,q.z,v),heading:turn(p.heading,q.heading,v),distanceMetres:plan.baseDistance+lerp(p.distance,q.distance,v),speedMps:open?lerp(p.speed,q.speed,v):0,motion:open?p.motion:p.phase==='rise'?'Sit':'Idle',legPose:p.legPose&&q.legPose?{hipsHeight:lerp(p.legPose.hipsHeight,q.legPose.hipsHeight,v),feet:p.legPose.feet.map((f,j)=>({x:lerp(f.x,q.legPose.feet[j].x,v),y:lerp(f.y,q.legPose.feet[j].y,v)}))}:p.legPose,poseBlend:p.poseBlend,animationPhase:lerp(p.animationPhase??0,q.animationPhase??0,v),stage:plan.kind==='yield'?'yielding':p.phase==='stairs'?'descending measured entry steps':p.phase==='rise'?'standing up':'alighting'});
    if(p.phase==='stairs'&&a.descentStartedAt==null)a.descentStartedAt=group.time;
    if(p.released&&!a.placeReleased){a.placeReleased=true;onRelease?.(a);}
    if(p.outside&&a.outsideAt==null){a.outsideAt=group.time;onOutside?.(a);}
    if(p.egress&&a.egressClearAt==null){a.egressClearAt=group.time;onEgress?.(a);}
    if(t>=trace.frames.length-1){group.plans.delete(id);if(avoidWaiting)wake=true;if(plan.kind==='yield')onYieldComplete?.(a,plan.target);else onDepart?.(a);}
   }
   // Past reservations cannot affect newly scheduled routes.
   const past=Math.floor(group.time/STEP)-3;for(const key of group.table.keys())if(key<past)group.table.delete(key);
  }if(wake){wake=false;retryBlocked();}}
 return {schedule,prepare,update,get preparing(){return pending.length;},get diagnostics(){return {mode:avoidWaiting?'guarded':'reference',rootRadius:navigator?.radius??null,detours,yields,blocked:[...blockedPlans.values()].map(a=>({id:a.id,...a.navigationBlocked}))};},reset(){pending.length=0;blockedPlans.clear();detours=0;yields=0;navigator?.clearCache();for(const g of groups.values()){g.time=0;g.table.clear();g.plans.clear();g.bufferRelease=0;g.assigned=[0,0];g.nextEntry=[0,0];}},get pending(){return [...groups.values()].flatMap(g=>[...g.plans.keys()]);}};
}
