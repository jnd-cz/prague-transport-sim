// SPDX-License-Identifier: AGPL-3.0-or-later
// The project's own passenger lab, street-life-boarding v14 (2026-10-27), dist/traffic/boarding-state.js, as it was (sha256 9f980a96b335581d);
// accepted by the maintainer as good enough for now (2026-10-27). #249 step 1: brought in unchanged; step 2 fits it to the game.
// #249: changed: exitPace passed to the exit flow (its PACE by default).
// #249 step 2: changed, for the game (src/passengers/consist.js), each an option or a function the lab's scenarios do not call, so its
// times hold: prepareStops (false: the exits prepared while the clock runs), keepEvents and onEvent (the events to a callback, not kept),
// a.aboard (on the floor: from the top of the entry steps in to the bottom out), enqueue's extra (merged into each boarder: stands, the
// wish to stand though seats are free, and the game's tag), overflow (a boarder with no place left boards as counted: up the steps and
// into the count), alight's nearest (the nearest to a door by walking first, the maintainer's rule) and counted (that many counted passengers
// out first through the doors in turn), seatAboard (passengers on board at the start), reseat (a free seat to the nearest standing
// passenger who does not wish to stand, round the others: cabin-navigation.js), abandon (boarders not yet on the steps leave the
// queues), a walk's own speed, a boarder on the steps finishing the climb when the doors close, and an idle step that only counts time.
// #249 step 4: changed, likewise: ready (before a stop, those to alight there go to their doors' doorway places) and alight's ids (the
// ones chosen then alight, one still on the way from where they get to).
// #249 (2026-11-26): outside (the boarders abandon would take, left where they are: those the doors close on wait at them).
// #249 (2026-11-26, Dveře I): redirect (boarders and alighters not yet through their door sent to the one door open).
import {createPassengerCore,doorIsOpen} from './passenger-core.js';
import {createExitFlow} from './exit-flow.js';
import {planExitDoors} from './exit-routing.js';
import {transformFootprint} from './packing-geometry.js';
import {excludedFromPassengers} from './cabin-space.js';
import {createCabinNavigator} from './cabin-navigation.js';
const lerp=(a,b,t)=>a+(b-a)*t,smooth=t=>t*t*(3-2*t),tau=Math.PI*2;
const angle=(a,b,t)=>a+(((b-a+Math.PI)%tau+tau)%tau-Math.PI)*t;
// Authored door channels and routes. This is deliberately not a crowd/navmesh solver.
export function createBoardingController(layout,{vehicleId='T3-DEMO-01',exitPolicy='balanced',avoidWaiting=false,exitPace=undefined,prepareStops=true,keepEvents=true,onEvent=null,overflow=null,navigator:sharedNavigator=null}={}){
 const core=createPassengerCore({vehicleId,seats:layout.seats,doors:layout.doors??[layout.door],standing:layout.standing.places??[],capacity:layout.capacity}),{ledger,standingLedger,actors}=core,events=[];const record=(type,a)=>{if(keepEvents)events.push({type,time,passengerId:a.id,doorId:a.doorId,channel:a.channel});onEvent?.(type,a);};
 for(const p of layout.standing.places??[]){const e=p.footprintHalfExtents??{x:.32,z:.22},points=p.footprintPolygon?transformFootprint(p.footprintPolygon,p.x,p.z,p.heading):[[-e.x,-e.z],[e.x,-e.z],[e.x,e.z],[-e.x,e.z]].map(([x,z])=>[p.x+x,p.z+z]);for(const [x,z]of points)if(excludedFromPassengers(layout,x,z))throw new Error(`Standing place in excluded cab: ${p.id}`);}
 const doors=layout.doors??[layout.door],channels=doors.flatMap(door=>[-.34,.34].map((offset,lane)=>({id:`${door.id}:${lane}`,door,lane,x:door.x+offset,queue:[],entry:null,next:0,alighted:0})));
 const queueOrder=[...channels].sort((a,b)=>a.lane-b.lane||doors.indexOf(a.door)-doors.indexOf(b.door));
 const bySeat=new Map(layout.seats.map(s=>[s.id,s])),byStand=new Map((layout.standing.places??[]).map(s=>[s.id,s]));
 const entryGap=.72,entryActors=c=>[...actors.values()].filter(a=>a.channel===c.id&&!a.exiting&&a.actions&&a.z>.1&&Math.abs(a.x-c.x)<.20);
 const leaderOf=(a,c)=>entryActors(c).filter(b=>b.id!==a.id&&b.z<a.z-1e-6).sort((a,b)=>b.z-a.z)[0];
 const innerX=c=>c.door.id==='Front'?Math.min(c.x,5.10):c.x;
 let exitPlan=null,waitForEntries=false;let time=0,exited=0,boarded=0,lastBoardDoorAt=null,lastExitDoorAt=null,lastExitRouteAt=null,message='Queue passengers at all three doors.',cursor=0;
 const occupied=a=>a.stage==='seated'||a.stage==='standing';
 const place=a=>a.seatId?bySeat.get(a.seatId):byStand.get(a.standingId);
 const seatRoot=s=>({x:s.anchor.x-s.forward.x*layout.fitProfile.backwardOffsetMetres,y:s.anchor.y-layout.fitProfile.localSeatHeight,z:s.anchor.z-s.forward.z*layout.fitProfile.backwardOffsetMetres});
 function settle(a){const p=place(a);Object.assign(a,a.seatId?seatRoot(p):{x:p.x,y:p.y,z:p.z},{heading:p.heading,motion:a.seatId?'Sit':'Idle',speedMps:0,legPose:null,poseBlend:null,stage:a.seatId?'seated':'standing',actions:null,aboard:true});}
 const exitFlow=createExitFlow(layout,channels,{pace:exitPace,avoidWaiting,allActors:()=>[...actors.values()],
  onRelease:a=>core.releasePlace(a),
  onNeedYield:(ids,requester,nav)=>{
   const blockers=ids.map(id=>actors.get(id)).filter(b=>b?.stage==='standing'&&b.standingId&&!b.yielding);
   for(const b of blockers){const others=[...actors.values()].filter(x=>x!==b&&['seated','standing','exit queue','yield queue'].includes(x.stage)&&!x.exiting),free=standingLedger.seats.filter(p=>p.status==='free').map(p=>byStand.get(p.id)).filter(p=>p.phase!=='doorway'&&Math.hypot(p.x-b.x,p.z-b.z)>.4&&Math.hypot(p.x-b.x,p.z-b.z)<2.5).sort((a,c)=>Number(a.phase!=='window')-Number(c.phase!=='window')||Math.hypot(a.x-b.x,a.z-b.z)-Math.hypot(c.x-b.x,c.z-b.z));for(const target of free){const route=nav.route({x:b.x,z:b.z},{x:target.x,z:target.z},others);if(route.path&&standingLedger.reserveMove(b.id,target.id)){b.yieldSourceStandingId=b.standingId;return {actor:b,target,path:route.path};}}}return null;
  },
  onYieldAdmission:(a,target)=>{standingLedger.releasePlace(a.yieldSourceStandingId,a.id);a.standingId=target.id;record('yield-admitted',a);},
  onYieldComplete:(a,target)=>{standingLedger.occupy(target.id,a.id);a.yielding=false;Object.assign(a,{stage:'standing',motion:'Idle',speedMps:0,heading:target.heading,x:target.x,z:target.z,doorBufferId:target.doorBufferId??null});record('yield-complete',a);},
  onAdmission:a=>record('exit-approach-admitted',a),
  onOutside:a=>{channels.find(c=>c.id===a.channel).alighted++;lastExitDoorAt=time;a.aboard=false;record('exit-door-clear',a);},
  onEgress:a=>record('exit-channel-clear',a),
  onDepart:a=>{record('departed',a);actors.delete(a.id);exited++;lastExitRouteAt=time;message=`${exited} passengers alighted.`;}
 });
 function chooseChannel(seatId,doorId){if(seatId&&!doorId)doorId=sectorOf(bySeat.get(seatId).anchor.x).id;const candidates=channels.filter(c=>!doorId||c.door.id===doorId);return [...candidates].sort((a,b)=>{
  const stream=c=>c.queue.length+entryActors(c).length,door=c=>channels.filter(ch=>ch.door.id===c.door.id).reduce((n,ch)=>n+stream(ch),0);
  const local=c=>{const freeSeats=ledger.seats.filter(p=>p.status==='free');if(freeSeats.length)return freeSeats.some(p=>sectorOf(bySeat.get(p.id).anchor.x).id===c.door.id);const freeStanding=standingLedger.seats.filter(p=>p.status==='free').map(p=>byStand.get(p.id));const ordinary=freeStanding.filter(p=>p.phase!=='doorway');return (ordinary.length?ordinary:freeStanding).some(p=>p.doorId===c.door.id);};
  const penalty=c=>!doorId&&!seatId&&!local(c)?1:0;
  return (door(a)+penalty(a))-(door(b)+penalty(b))||stream(a)-stream(b)||((queueOrder.indexOf(a)-cursor+6)%6)-((queueOrder.indexOf(b)-cursor+6)%6);
 })[0];}
 const sectorOf=x=>doors.reduce((a,b)=>Math.abs(a.x-x)<Math.abs(b.x-x)?a:b);
 function reservePlace(a,c){
  const phase=p=>p.phase==='doorway'?2:p.phase==='circulation'?1:0;
  const seats=[...layout.seats].sort((a,b)=>Number(sectorOf(a.anchor.x).id!==c.door.id)-Number(sectorOf(b.anchor.x).id!==c.door.id)||Math.abs(b.anchor.x-c.door.x)-Math.abs(a.anchor.x-c.door.x));
  const stand=()=>{a.standingId=standingLedger.reserve(a.id,[...byStand.values()].sort((a,b)=>Number(a.phase==='doorway')-Number(b.phase==='doorway')||Number(a.doorId!==c.door.id)-Number(b.doorId!==c.door.id)||phase(a)-phase(b)||(a.priority??0)-(b.priority??0)).map(p=>p.id));};
  // (#249: one who wishes to stand takes a standing place first, a seat only with none left)
  if(a.stands&&!a.requestedSeat){stand();if(!a.standingId)a.seatId=core.reserveSeat(a.id,seats.map(p=>p.id));}
  else{a.seatId=core.reserveSeat(a.id,a.requestedSeat?[a.requestedSeat]:seats.map(p=>p.id));
  if(!a.seatId&&!a.requestedSeat)stand();}
  a.doorBufferId=a.standingId?byStand.get(a.standingId).doorBufferId??null:null;
  return !!(a.seatId||a.standingId);
 }
 function enqueue(count=1,seatId=null,doorId=null,{waitForPlace=false,extra=null}={}){if(seatId&&!bySeat.has(seatId))throw new Error('Unknown seat');if(doorId&&!doors.some(d=>d.id===doorId))throw new Error('Unknown door');let added=0;
  for(let i=0;i<count;i++){
   const c=chooseChannel(seatId,doorId),{id,index}=core.nextIdentity();
   const a={id,seatId:null,standingId:null,requestedSeat:seatId,channel:c.id,doorId:c.door.id,boardedDoorId:c.door.id,index,x:c.x,y:c.door.platformY,z:2.45+c.queue.length*.8,heading:Math.PI/2,distanceMetres:0,speedMps:0,motion:'Idle',animationPhase:0,legPose:null,poseBlend:null,stage:'queue',...(typeof extra==='function'?extra(i):extra)};
   if(!waitForPlace&&!reservePlace(a,c))break;
   actors.set(id,a);c.queue.push(a);cursor=(queueOrder.indexOf(c)+1)%channels.length;added++;
  }message=added?`${added} passengers queued; seats first, then available standing destinations.`:seatId?'Selected seat is unavailable.':'All destinations in this arrangement are assigned. Queue a timed exchange to wait for places to be released.';return added;
 }
 function preload(count,standCount=0){core.reset();channels.forEach(c=>{c.queue.length=0;c.entry=null;c.next=0;c.alighted=0;});exitFlow.reset();waitForEntries=false;cursor=0;exited=0;boarded=0;time=0;events.length=0;exitPlan=null;lastBoardDoorAt=null;lastExitDoorAt=null;lastExitRouteAt=null;
  const standGroups=doors.map(d=>[...byStand.values()].filter(p=>p.doorId===d.id)),standOrder=[];while(standGroups.some(g=>g.length))for(const g of standGroups)if(g.length)standOrder.push(g.shift());
  for(const [records,l,isSeat]of [[layout.seats.slice(0,count),ledger,true],[standOrder.slice(0,standCount),standingLedger,false]])for(const p of records){const {id,index}=core.nextIdentity(),c=chooseChannel(isSeat?p.id:null,isSeat?sectorOf(p.anchor.x).id:p.doorId);const a={id,seatId:isSeat?p.id:null,standingId:isSeat?null:p.id,doorBufferId:isSeat?null:p.doorBufferId??null,channel:c.id,doorId:c.door.id,boardedDoorId:c.door.id,index,distanceMetres:0,animationPhase:0};l.reserve(id,[p.id]);l.occupy(p.id,id);settle(a);actors.set(id,a);}
  message=`Loaded ${ledger.snapshot().seated} seated / ${standingLedger.snapshot().seated} standing (study positions).`;
 }
 // (#249: the walking distance from a passenger's place to the nearest door's head of the steps, along the aisle and across)
 const doorDistance=a=>{const s=a.seatId?bySeat.get(a.seatId):null,x=s?s.anchor.x+s.forward.x*.23:a.x,z=s?Math.sign(s.anchor.z)*.43:a.z;return Math.min(...doors.map(d=>Math.abs(x-innerX({x:d.x,door:d}))+Math.abs(z-.37)));};
 // (#249 step 4: ids, the passengers chosen when the stop was near (ready): those alight, whatever the count; one still on the way
 // to the door's place alights when there, and one who has not set off yet stays where they are)
 function alight(count=1,{balanced=false,nearest=false,counted=0,ids=null}={}){let late=0;for(const a of actors.values()){a.toAlight=false;if(ids?.has(a.id)){a.readyAt=null;if(a.readyPlace){a.alightOnArrive=true;late++;}}}
  let selected=[...actors.values()].filter(a=>occupied(a)&&!a.counted&&(!ids||ids.has(a.id))).sort(nearest?(a,b)=>doorDistance(a)-doorDistance(b)||a.index-b.index:(a,b)=>Number(!a.doorBufferId)-Number(!b.doorBufferId)||Number(!!a.seatId)-Number(!!b.seatId)||a.index-b.index);
  if(balanced){const groups=doors.map(d=>selected.filter(a=>a.doorId===d.id).sort((a,b)=>Number(!a.doorBufferId)-Number(!b.doorBufferId)||Number(!!a.seatId)-Number(!!b.seatId)||a.index-b.index));selected=[];while(groups.some(g=>g.length))for(const g of groups)if(g.length)selected.push(g.shift());}
  // (#249: the counted passengers stand in the doorways, one door after another, and leave first)
  const out=[];for(let i=0;i<counted;i++){const d=doors[i%doors.length],{id,index}=core.nextIdentity(),a={id,index,seatId:null,standingId:null,doorBufferId:d.id,counted:true,aboard:true,channel:`${d.id}:0`,doorId:d.id,boardedDoorId:d.id,x:innerX({x:d.x,door:d}),y:layout.floorY,z:.6,heading:-Math.PI/2,distanceMetres:0,speedMps:0,motion:'Idle',animationPhase:0,legPose:null,poseBlend:null,stage:'standing',actions:null};actors.set(id,a);out.push(a);}
  selected=out.concat(ids?selected:selected.slice(0,count));if(!selected.length)return late;const plan=planExitDoors(selected,doors,{policy:exitPolicy,active:[...actors.values()].filter(a=>a.exiting),service:exitPace?.service??{},walk:exitPace?.walk??.95});exitPlan=plan.summary;let n=0;for(const a of selected){
   const d=doors.find(d=>d.id===plan.assignment.get(a.id));a.doorId=d.id;core.requestAlighting(a,'exit queue');a.motion=a.seatId?'Sit':'Idle';n++;
  }if(exitFlow.pending.length===0)waitForEntries=[...actors.values()].some(a=>a.actions&&!a.exiting);exitFlow.schedule(selected);message=`${n} passengers requested to alight; two-stream route reservations, door clearance places first.`;return n+late;}
 const walk=(x,y,z)=>({type:'walk',x,y,z});
 function planBoard(a,c){
  // (#249: a counted passenger climbs the steps like the others and joins the count at their head)
  if(a.counted){a.actions=[walk(c.x,c.door.platformY,2.45),walk(c.x,c.door.platformY,1.58),{type:'door'},{type:'stairs',down:false},walk(innerX(c),layout.floorY,.37),{type:'clear-entry'},{type:'counted'}];a.actionIndex=0;a.actionTime=0;a.actionStart=null;core.startBoarding(a,'approach');record('board-admitted',a);return;}
  const p=place(a),approach=a.seatId?{x:p.anchor.x+p.forward.x*.23,z:Math.sign(p.anchor.z)*.45}:{x:p.x,z:p.z};
  a.actions=[walk(c.x,c.door.platformY,2.45),walk(c.x,c.door.platformY,1.58),{type:'door'},{type:'stairs',down:false},walk(innerX(c),layout.floorY,.37),walk(innerX(c),layout.floorY,.04),{type:'clear-entry'},walk(approach.x,layout.floorY,.04),walk(approach.x,layout.floorY,approach.z),{type:'turn',heading:p.heading},a.seatId?{type:'sit',seat:p}:{type:'stand'}];a.actionIndex=0;a.actionTime=0;a.actionStart=null;core.startBoarding(a,'approach');record('board-admitted',a);
 }
 function advance(a){a.actionIndex++;a.actionTime=0;a.actionStart=null;}
 function entrySample(c,t){
  const levels=c.door.entryLevels,up=[{z:1.58,y:c.door.platformY},...levels.map((b,i)=>({z:i===2?.60:(b.zMin+b.zMax)/2+.08,y:b.y})),{z:.37,y:layout.floorY}],points=up,segments=points.length-1,duration=.64,index=Math.min(segments-1,Math.floor(t/duration)),u=Math.min(1,(t-index*duration)/duration),moving=index%2,feet=[{...points[0]},{...points[0]}];
  for(let k=0;k<index;k++)feet[k%2]={...points[k+1]};const start=feet[moving],end=points[index+1],v=smooth(u),lift=.04*Math.sin(Math.PI*u);
  feet[moving]={z:lerp(start.z,end.z,v),y:lerp(start.y,end.y,Math.min(1,u*2))+lift};
  return {feet,index,u,z:(feet[0].z+feet[1].z)/2,y:(feet[0].y+feet[1].y)/2,done:t>=duration*segments,endY:points.at(-1).y};
 }
 function stepPose(a,c,t){
  const p=entrySample(c,t);a.x=c.x;a.z=p.z;a.y=p.y;a.heading=Math.PI/2;a.motion='TramStepUp';a.animationPhase=(p.index+p.u)/2;
  const sign=1,targets=p.feet.map(f=>({x:sign*(a.z-f.z)/layout.fitProfile.scale.x,y:f.y-a.y+.107})),hipsHeight=Math.min(.94,...targets.map(f=>f.y+.015+Math.sqrt(Math.max(.02,.83*.83-f.x*f.x))));a.legPose={hipsHeight,feet:targets};
  if(p.done){a.legPose=null;a.y=p.endY;a.enteredAt=time;lastBoardDoorAt=time;a.aboard=true;record('board-door-clear',a);advance(a);}
 }
 // Only hold doorway destinations for active movement near their clearance area.
 // This is a local centre/path heuristic, not full-body collision avoidance.
 function doorwayMovementNearby(a){
  const target=byStand.get(a.standingId);if(!target)return false;
  return [...actors.values()].some(b=>{
   if(b===a||!b.actions||b.exiting||b.stage==='queue'||Math.hypot(b.x-target.x,b.z-target.z)>.55)return false;
   const action=b.actions[b.actionIndex];if(!action)return false;
   if(action.type!=='walk')return true;
   const dx=action.x-b.x,dz=action.z-b.z,len=dx*dx+dz*dz,t=len?Math.max(0,Math.min(1,((target.x-b.x)*dx+(target.z-b.z)*dz)/len)):0;
   return Math.hypot(b.x+t*dx-target.x,b.z+t*dz-target.z)<.45;
  });
 }
 function tick(dt,doorsOpen){
  if(exitFlow.preparing){exitFlow.prepare(2);if(prepareStops)return;}time+=dt;const currentEntries=[...actors.values()].some(a=>a.actions&&!a.exiting);if(!currentEntries)waitForEntries=false;exitFlow.update(waitForEntries?0:dt,doorsOpen);
  startReady();
  const outbound=d=>[...actors.values()].some(a=>a.doorId===d&&(a.stage==='exit queue'||a.toAlight||a.alightOnArrive||a.exiting&&a.egressClearAt==null));
  for(const c of channels){const back=entryActors(c).sort((a,b)=>b.z-a.z)[0];if(!outbound(c.door.id)&&c.queue.length&&time>=c.next&&(!back||back.z<=2.45-entryGap)){
   const a=c.queue[0];if(!a.seatId&&!a.standingId&&!a.counted)reservePlace(a,c);
   if(!a.seatId&&!a.standingId&&!a.counted&&overflow?.(a))a.counted=true;
   const doorway=a.doorBufferId&&doorwayMovementNearby(a);if((a.seatId||a.standingId||a.counted)&&!doorway){c.queue.shift();c.next=time+.9;planBoard(a,c);}
  }}
  for(const c of channels)c.queue.forEach((a,i)=>{const activeBack=entryActors(c).sort((a,b)=>b.z-a.z)[0],preceding=i?c.queue[i-1]:activeBack,targetZ=Math.max(2.45+i*.8,preceding?preceding.z+.8:0),targetX=c.x,dx=targetX-a.x,dz=targetZ-a.z,d=Math.hypot(dx,dz),move=Math.min(d,dt*.85);if(d>.001){a.x+=dx/d*move;a.z+=dz/d*move;a.heading=angle(a.heading,Math.atan2(-dz,dx),Math.min(1,dt*8));}a.distanceMetres+=move;a.speedMps=dt?move/dt:0;a.motion=move>.00001?'Walk':'Idle';});
  const moving=[...actors.values()].sort((a,b)=>Number(!!b.exiting)-Number(!!a.exiting)||(a.exiting?Math.abs(a.x-(channels.find(c=>c.id===a.channel)?.x??0))-Math.abs(b.x-(channels.find(c=>c.id===b.channel)?.x??0)):a.index-b.index));
  for(const a of moving){
   const action=a.actions?.[a.actionIndex];if(!action)continue;const c=channels.find(c=>c.id===a.channel),open=doorIsOpen(doorsOpen,c.door.id);
   if(!a.actionStart)a.actionStart={x:a.x,y:a.y,z:a.z,heading:a.heading};a.poseBlend=null;
   if(action.type==='stairs'&&!open&&!a.actionTime){a.speedMps=0;a.stage='waiting for open door';continue;}
   const oldTime=a.actionTime,oldZ=a.z;a.actionTime+=dt;if(action.type!=='stairs')a.legPose=null;
   if(action.type==='walk'){
    a.stage='walking';const dx=action.x-a.x,dz=action.z-a.z,d=Math.hypot(dx,dz);let move=Math.min(d,dt*(action.speed??.95));const leader=!action.free&&dz<0&&Math.abs(a.x-c.x)<.20?leaderOf(a,c):null;if(leader)move=Math.min(move,Math.max(0,(a.z-leader.z-entryGap)*d/-dz));a.speedMps=dt?move/dt:0;a.motion=move>0?'Walk':'Idle';if(d>.001){a.heading=angle(a.heading,Math.atan2(-dz,dx),Math.min(1,dt*8));a.x+=dx/d*move;a.z+=dz/d*move;a.distanceMetres+=move;}a.y=action.y;if(d<=move+.002)advance(a);
   }else if(action.type==='door'){a.stage='waiting for open door';a.motion='Idle';a.speedMps=0;if(open)advance(a);
   }else if(action.type==='stairs'){a.stage='climbing measured entry steps';const leader=leaderOf(a,c);const blocked=t=>{const z=entrySample(c,t).z;return leader&&z<leader.z+entryGap;};if(blocked(a.actionTime)){let lo=oldTime,hi=a.actionTime;for(let i=0;i<16;i++){const mid=(lo+hi)/2;if(!blocked(mid))lo=mid;else hi=mid;}a.actionTime=lo;}stepPose(a,c,a.actionTime);a.speedMps=dt?Math.abs(a.z-oldZ)/dt:0;
   }else if(action.type==='clear-entry'){if(c.entry===a.id)c.entry=null;advance(a);
   }else if(action.type==='counted'){a.actions=null;actors.delete(a.id);boarded++;record('counted',a);
   }else if(action.type==='turn'){a.stage='aligning with place';a.motion='Idle';a.speedMps=0;a.heading=angle(a.actionStart.heading,action.heading,smooth(Math.min(1,a.actionTime/.4)));if(a.actionTime>=.4)advance(a);
   }else if(action.type==='sit'){
    a.stage='sitting down';a.motion='Sit';a.speedMps=0;const t=smooth(Math.min(1,a.actionTime/.8)),s=action.seat,p=seatRoot(s);a.poseBlend={from:'Idle',to:'Sit',weight:t};a.x=lerp(a.actionStart.x,p.x,t);a.z=lerp(a.actionStart.z,p.z,t);a.y=lerp(a.actionStart.y,p.y,t);a.heading=s.heading;if(a.actionTime>=.8){settle(a);core.occupySeat(a.id,s.id);if(a.reseatFrom){standingLedger.releasePlace(a.reseatFrom,a.id);a.reseatFrom=null;a.standingId=null;a.doorBufferId=null;record('reseated',a);}else boarded++;}
   }else if(action.type==='rise'){a.stage='standing up';a.motion='Idle';a.speedMps=0;const t=smooth(Math.min(1,a.actionTime/.7));a.poseBlend={from:'Sit',to:'Idle',weight:t};a.y=lerp(a.actionStart.y,layout.floorY,t);if(a.actionTime>=.7)advance(a);
   }else if(action.type==='ready')readyAt(a,action.place);
   else if(action.type==='stand'){settle(a);standingLedger.occupy(a.standingId,a.id);boarded++;
   }
  }
 }
 // (#249: n passengers on board at the start, each in a free place: one who wishes to stand (stands()) on a standing place, the
 // others on a seat; standing places by the boarders' order of kinds, by the window first and the doorways last, one of a kind at
 // random (rand: the game's seeded stream). The number placed: the cabin may have fewer places left)
 function seatAboard(n,{rand,stands=()=>false}){const phase=p=>p.phase==='doorway'?2:p.phase==='circulation'?1:0,pick=list=>list[Math.floor(rand()*list.length)];let k=0;
  for(;k<n;k++){const wish=stands(),seats=ledger.seats.filter(s=>s.status==='free'),free=standingLedger.seats.filter(s=>s.status==='free').map(s=>byStand.get(s.id)),best=free.length?Math.min(...free.map(phase)):0,standing=free.filter(p=>phase(p)===best);
   const seat=()=>seats.length?bySeat.get(pick(seats).id):null,stand=()=>standing.length?pick(standing):null,p=wish?stand()??seat():seat()??stand();if(!p)break;
   const isSeat=!!p.anchor,door=isSeat?sectorOf(p.anchor.x):doors.find(d=>d.id===p.doorId)??sectorOf(p.x),{id,index}=core.nextIdentity(),l=isSeat?ledger:standingLedger;
   const a={id,index,seatId:isSeat?p.id:null,standingId:isSeat?null:p.id,doorBufferId:isSeat?null:p.doorBufferId??null,channel:`${door.id}:0`,doorId:door.id,boardedDoorId:door.id,distanceMetres:0,animationPhase:0,stands:wish};
   l.reserve(id,[p.id]);l.occupy(p.id,id);settle(a);actors.set(id,a);}
  return k;
 }
 // (#249: a door's exchange is over: nobody waits or climbs there, nobody is to leave or leaving through it)
 const quietDoor=d=>!channels.some(c=>c.door.id===d.id&&(c.queue.length||entryActors(c).length))&&![...actors.values()].some(a=>a.doorId===d.id&&(a.stage==='exit queue'||a.alightOnArrive||a.exiting||a.actions&&!a.aboard));
 let navigator=sharedNavigator; // (#249: one for the set's cars, built before the run: about 20 ms)
 // (#249, the maintainer's rule 3: a free seat by a door whose exchange is over goes to the nearest standing passenger who does not wish to
 // stand (of the three nearest, the first with a way round the others), walking at speed m/s; the seat reserved first, the standing
 // place freed on arrival. The seats with the nearest such passenger first; at most limit moves begun and tries ways looked for a
 // call; the number begun)
 function reseat({speed=.8,limit=1,tries=3}={}){
  if(!layout.navigation)return 0;let n=0,left=tries;const standing=[...actors.values()].filter(a=>a.stage==='standing'&&a.standingId&&!a.stands&&!a.counted&&!a.toAlight&&!a.actions&&!a.exiting&&!a.yielding);if(!standing.length)return 0;
  const goalOf=s=>({x:s.anchor.x+s.forward.x*.23,z:Math.sign(s.anchor.z)*.45}),reach=s=>{const g=goalOf(s);return Math.min(...standing.map(a=>Math.hypot(a.x-g.x,a.z-g.z)));};
  const free=ledger.seats.filter(s=>s.status==='free').map(s=>bySeat.get(s.id)).filter(s=>quietDoor(sectorOf(s.anchor.x))).sort((a,b)=>reach(a)-reach(b));if(!free.length)return 0;navigator??=createCabinNavigator(layout);
  for(const s of free){if(n>=limit||left<=0)break;const goal=goalOf(s),near=standing.filter(a=>!a.actions).sort((a,b)=>Math.hypot(a.x-goal.x,a.z-goal.z)-Math.hypot(b.x-goal.x,b.z-goal.z)).slice(0,3);
   for(const a of near){if(left--<=0)break;const others=[...actors.values()].filter(b=>b!==a&&(b.stage==='seated'||b.stage==='standing')),route=navigator.route({x:a.x,z:a.z},goal,others);if(!route.path||!core.reserveSeat(a.id,[s.id]))continue;
    a.seatId=s.id;a.reseatFrom=a.standingId;a.actions=[...route.path.slice(1).map(p=>({type:'walk',x:p.x,y:layout.floorY,z:p.z,speed,free:true})),{type:'turn',heading:s.heading},{type:'sit',seat:s}];a.actionIndex=0;a.actionTime=0;a.actionStart=null;a.stage='walking';record('reseat-admitted',a);n++;break;}}
  return n;
 }
 // (#249 step 4: those getting off at the stop made ready to go once the doors open.
 // The stop near, the passengers chosen to alight there (ids) go to the free doorway places of the doors they will leave by
 // (planExitDoors, as alight assigns them), the nearest to the door first, one a door every gap s: from a seat they stand up first,
 // then walk at speed m/s round the others to the free place nearest the door that has a way (of the three nearest). A doorway
 // place is a door's (doorBufferId): alight sends them through it, and first. Those already in one, or with none free or no way,
 // stay where they are. The chosen ones keep out of reseat. The number set off or to set off)
 function ready(ids,{speed=.8,gap=.8}={}){
  for(const a of actors.values())a.toAlight=false;const chosen=[...actors.values()].filter(a=>ids.has(a.id)&&occupied(a)&&!a.counted);for(const a of chosen)a.toAlight=true;
  if(!layout.navigation||!chosen.length)return 0;readySpeed=speed;
  const plan=planExitDoors(chosen,doors,{policy:exitPolicy,active:[],service:exitPace?.service??{},walk:exitPace?.walk??.95}),byDoor=new Map();
  for(const a of chosen){const d=plan.assignment.get(a.id);if(a.doorBufferId===d)continue;if(!byDoor.has(d))byDoor.set(d,[]);byDoor.get(d).push(a);}
  let n=0;for(const [id,list]of byDoor){const d=doors.find(d=>d.id===id),to=a=>{const p=a.seatId?bySeat.get(a.seatId).anchor:a;return Math.abs(p.x-innerX({x:d.x,door:d}))+Math.abs(p.z-.37);};
   list.sort((a,b)=>to(a)-to(b)||a.index-b.index).forEach((a,k)=>{a.readyDoorId=id;a.readyAt=time+k*gap;n++;});}
  return n;
 }
 let readySpeed=.8;
 function startReady(){for(const a of actors.values()){if(a.readyAt==null||a.readyAt>time)continue;a.readyAt=null;if(!occupied(a)||a.actions)continue;
  const d=doors.find(d=>d.id===a.readyDoorId),seat=a.seatId?bySeat.get(a.seatId):null,from=seat?{x:seat.anchor.x+seat.forward.x*.23,z:Math.sign(seat.anchor.z)*.43}:{x:a.x,z:a.z},landing={x:innerX({x:d.x,door:d}),z:.37};
  const free=standingLedger.seats.filter(p=>p.status==='free').map(p=>byStand.get(p.id)).filter(p=>p.doorBufferId===d.id).sort((p,q)=>Math.hypot(p.x-landing.x,p.z-landing.z)-Math.hypot(q.x-landing.x,q.z-landing.z));
  navigator??=createCabinNavigator(layout);const others=[...actors.values()].filter(b=>b!==a&&(b.stage==='seated'||b.stage==='standing'));
  for(const p of free.slice(0,3)){const route=navigator.route(from,{x:p.x,z:p.z},others);if(!route.path)continue;if(!(seat?standingLedger.reserve(a.id,[p.id]):standingLedger.reserveMove(a.id,p.id)))continue;
   const walk=q=>({type:'walk',x:q.x,y:layout.floorY,z:q.z,speed:readySpeed,free:true});
   a.readyFrom=seat?{seat:seat.id}:{place:a.standingId};a.readyPlace=p.id;a.doorId=d.id;
   a.actions=[...(seat?[{type:'rise'},walk(from)]:[]),...route.path.slice(1).map(walk),{type:'turn',heading:p.heading},{type:'ready',place:p}];a.actionIndex=0;a.actionTime=0;a.actionStart=null;a.stage='walking';record('ready-admitted',a);break;}
 }}
 // (at the doorway place: the old place given back, the new one held; one whose stop came on the way sets off out from here)
 function readyAt(a,p){
  if(a.readyFrom.seat){ledger.releasePlace(a.readyFrom.seat,a.id);a.seatId=null;}else standingLedger.releasePlace(a.readyFrom.place,a.id);
  a.standingId=p.id;a.doorBufferId=p.doorBufferId;a.readyFrom=null;a.readyPlace=null;settle(a);standingLedger.occupy(p.id,a.id);record('ready',a);
  if(a.alightOnArrive){a.alightOnArrive=false;core.requestAlighting(a,'exit queue');exitFlow.schedule([a]);}
 }
 // (#249: the boarders not yet on the entry steps for whom test(a) holds leave the queues and the controller, their places given back:
 // the doors closed on them, or the car is full. They are returned)
 function outside(test=()=>true){return [...actors.values()].filter(a=>!a.aboard&&!a.exiting&&(a.stage==='queue'||a.actions&&(a.actionIndex<3||a.actionIndex===3&&!a.actionTime))&&test(a));}
 function abandon(test=()=>true){const gone=outside(test);
  for(const a of gone){core.releasePlace(a);for(const c of channels){const i=c.queue.indexOf(a);if(i>=0)c.queue.splice(i,1);}actors.delete(a.id);}return gone;}
 // (#249, Dveře I: the front door alone) those of test(a) bound for another door than doorId and not yet through theirs go to it:
 // boarders not yet on the entry steps join its queue, their places kept (they walk there as a queue moves up); alighters not yet
 // set off are planned out through it (exit-flow.js drop; one still on the way to a doorway place is when they get there). The number
 function redirect(test,doorId){if(!doors.some(d=>d.id===doorId))throw new Error('Unknown door');const away=a=>a.doorId!==doorId&&test(a);let n=0;
  for(const a of outside(away)){for(const c of channels){const i=c.queue.indexOf(a);if(i>=0)c.queue.splice(i,1);}
   if(a.actions)Object.assign(a,{actions:null,actionIndex:0,actionTime:0,actionStart:null,stage:'queue',legPose:null,poseBlend:null});
   const c=chooseChannel(null,doorId);Object.assign(a,{channel:c.id,doorId,boardedDoorId:doorId});c.queue.push(a);n++;}
  const out=exitFlow.drop(away);for(const a of out)Object.assign(a,{doorId,channel:`${doorId}:0`});if(out.length)exitFlow.schedule(out);
  return n+out.length;}
 // (#249: nothing moving, queued or planned: a step only counts the time)
 const idle=()=>!exitFlow.preparing&&channels.every(c=>!c.queue.length)&&![...actors.values()].some(a=>a.actions||a.exiting||a.yielding||a.stage==='exit queue'||a.readyAt!=null);
 return {setExitPolicy(value){if(!['balanced','boarding'].includes(value))throw new Error('Unknown exit policy');exitPolicy=value;},layout,ledger,standingLedger,actors,channels,events,enqueue,preload,alight,seatAboard,reseat,ready,abandon,outside,redirect,doorDistance,quietDoor,get time(){return time;},get active(){return [...actors.values()].find(a=>a.actions||a.exiting||a.yielding)||null;},get message(){return message;},
 update(dt,{doorsOpen=true}={}){if(!Number.isFinite(dt)||dt<0)throw new Error('Non-negative finite dt required');if(dt===0){tick(0,doorsOpen);return;}if(!prepareStops&&idle()){time+=dt;return;}for(let left=dt;left>1e-8;left-=.025)tick(Math.min(left,.025),doorsOpen);},
 snapshot(){const active=[...actors.values()].filter(a=>a.actions||a.exiting||a.yielding),st=standingLedger.snapshot();return {waitingAvoidance:exitFlow.diagnostics,planningExits:exitFlow.preparing,scheduledExits:exitFlow.pending.length,exitPolicy,exitPlan,vehicleId,simulationTime:time,boarded,lastBoardDoorAt,lastExitDoorAt,lastExitRouteAt,...ledger.snapshot(),standing:st.seated,standingReserved:st.reserved,studyStandingPlaces:st.mappedSeats,queued:channels.reduce((n,c)=>n+c.queue.length,0),waitingForPlace:[...actors.values()].filter(a=>a.stage==='queue'&&!a.seatId&&!a.standingId).length,exited,active:active[0]?{id:active[0].id,stage:active[0].stage,seatId:active[0].seatId}:null,moving:active.length,doorStreams:channels.map(c=>({id:c.id,queued:c.queue.length,alighted:c.alighted,entry:c.entry??entryActors(c)[0]?.id??null,climbing:entryActors(c).filter(a=>a.legPose).length,descending:[...actors.values()].filter(a=>a.channel===c.id&&a.exiting&&a.legPose).length,direction:[...actors.values()].some(a=>a.doorId===c.door.id&&(a.stage==='exit queue'||a.exiting&&a.egressClearAt==null))?'out':'in'})),message};}};
}
