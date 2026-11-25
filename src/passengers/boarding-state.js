// SPDX-License-Identifier: AGPL-3.0-or-later
// The project's own passenger lab, street-life-boarding v14 (2026-10-27), dist/traffic/boarding-state.js, as it was (sha256 9f980a96b335581d);
// accepted by the user as "good enough for now" (2026-10-27). #249 step 1: brought in unchanged; step 2 fits it to the game.
// #249: changed: exitPace passed to the exit flow (its PACE by default).
import {createPassengerCore,doorIsOpen} from './passenger-core.js';
import {createExitFlow} from './exit-flow.js';
import {planExitDoors} from './exit-routing.js';
import {transformFootprint} from './packing-geometry.js';
import {excludedFromPassengers} from './cabin-space.js';
const lerp=(a,b,t)=>a+(b-a)*t,smooth=t=>t*t*(3-2*t),tau=Math.PI*2;
const angle=(a,b,t)=>a+(((b-a+Math.PI)%tau+tau)%tau-Math.PI)*t;
// Authored door channels and routes. This is deliberately not a crowd/navmesh solver.
export function createBoardingController(layout,{vehicleId='T3-DEMO-01',exitPolicy='balanced',avoidWaiting=false,exitPace=undefined}={}){
 const core=createPassengerCore({vehicleId,seats:layout.seats,doors:layout.doors??[layout.door],standing:layout.standing.places??[],capacity:layout.capacity}),{ledger,standingLedger,actors}=core,events=[];const record=(type,a)=>events.push({type,time,passengerId:a.id,doorId:a.doorId,channel:a.channel});
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
 function settle(a){const p=place(a);Object.assign(a,a.seatId?seatRoot(p):{x:p.x,y:p.y,z:p.z},{heading:p.heading,motion:a.seatId?'Sit':'Idle',speedMps:0,legPose:null,poseBlend:null,stage:a.seatId?'seated':'standing',actions:null});}
 const exitFlow=createExitFlow(layout,channels,{pace:exitPace,avoidWaiting,allActors:()=>[...actors.values()],
  onRelease:a=>core.releasePlace(a),
  onNeedYield:(ids,requester,nav)=>{
   const blockers=ids.map(id=>actors.get(id)).filter(b=>b?.stage==='standing'&&b.standingId&&!b.yielding);
   for(const b of blockers){const others=[...actors.values()].filter(x=>x!==b&&['seated','standing','exit queue','yield queue'].includes(x.stage)&&!x.exiting),free=standingLedger.seats.filter(p=>p.status==='free').map(p=>byStand.get(p.id)).filter(p=>p.phase!=='doorway'&&Math.hypot(p.x-b.x,p.z-b.z)>.4&&Math.hypot(p.x-b.x,p.z-b.z)<2.5).sort((a,c)=>Number(a.phase!=='window')-Number(c.phase!=='window')||Math.hypot(a.x-b.x,a.z-b.z)-Math.hypot(c.x-b.x,c.z-b.z));for(const target of free){const route=nav.route({x:b.x,z:b.z},{x:target.x,z:target.z},others);if(route.path&&standingLedger.reserveMove(b.id,target.id)){b.yieldSourceStandingId=b.standingId;return {actor:b,target,path:route.path};}}}return null;
  },
  onYieldAdmission:(a,target)=>{standingLedger.releasePlace(a.yieldSourceStandingId,a.id);a.standingId=target.id;record('yield-admitted',a);},
  onYieldComplete:(a,target)=>{standingLedger.occupy(target.id,a.id);a.yielding=false;Object.assign(a,{stage:'standing',motion:'Idle',speedMps:0,heading:target.heading,x:target.x,z:target.z,doorBufferId:target.doorBufferId??null});record('yield-complete',a);},
  onAdmission:a=>record('exit-approach-admitted',a),
  onOutside:a=>{channels.find(c=>c.id===a.channel).alighted++;lastExitDoorAt=time;record('exit-door-clear',a);},
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
  a.seatId=core.reserveSeat(a.id,a.requestedSeat?[a.requestedSeat]:seats.map(p=>p.id));
  if(!a.seatId&&!a.requestedSeat)a.standingId=standingLedger.reserve(a.id,[...byStand.values()].sort((a,b)=>Number(a.phase==='doorway')-Number(b.phase==='doorway')||Number(a.doorId!==c.door.id)-Number(b.doorId!==c.door.id)||phase(a)-phase(b)||(a.priority??0)-(b.priority??0)).map(p=>p.id));
  a.doorBufferId=a.standingId?byStand.get(a.standingId).doorBufferId??null:null;
  return !!(a.seatId||a.standingId);
 }
 function enqueue(count=1,seatId=null,doorId=null,{waitForPlace=false}={}){if(seatId&&!bySeat.has(seatId))throw new Error('Unknown seat');if(doorId&&!doors.some(d=>d.id===doorId))throw new Error('Unknown door');let added=0;
  for(let i=0;i<count;i++){
   const c=chooseChannel(seatId,doorId),{id,index}=core.nextIdentity();
   const a={id,seatId:null,standingId:null,requestedSeat:seatId,channel:c.id,doorId:c.door.id,boardedDoorId:c.door.id,index,x:c.x,y:c.door.platformY,z:2.45+c.queue.length*.8,heading:Math.PI/2,distanceMetres:0,speedMps:0,motion:'Idle',animationPhase:0,legPose:null,poseBlend:null,stage:'queue'};
   if(!waitForPlace&&!reservePlace(a,c))break;
   actors.set(id,a);c.queue.push(a);cursor=(queueOrder.indexOf(c)+1)%channels.length;added++;
  }message=added?`${added} passengers queued; seats first, then available standing destinations.`:seatId?'Selected seat is unavailable.':'All destinations in this arrangement are assigned. Queue a timed exchange to wait for places to be released.';return added;
 }
 function preload(count,standCount=0){core.reset();channels.forEach(c=>{c.queue.length=0;c.entry=null;c.next=0;c.alighted=0;});exitFlow.reset();waitForEntries=false;cursor=0;exited=0;boarded=0;time=0;events.length=0;exitPlan=null;lastBoardDoorAt=null;lastExitDoorAt=null;lastExitRouteAt=null;
  const standGroups=doors.map(d=>[...byStand.values()].filter(p=>p.doorId===d.id)),standOrder=[];while(standGroups.some(g=>g.length))for(const g of standGroups)if(g.length)standOrder.push(g.shift());
  for(const [records,l,isSeat]of [[layout.seats.slice(0,count),ledger,true],[standOrder.slice(0,standCount),standingLedger,false]])for(const p of records){const {id,index}=core.nextIdentity(),c=chooseChannel(isSeat?p.id:null,isSeat?sectorOf(p.anchor.x).id:p.doorId);const a={id,seatId:isSeat?p.id:null,standingId:isSeat?null:p.id,doorBufferId:isSeat?null:p.doorBufferId??null,channel:c.id,doorId:c.door.id,boardedDoorId:c.door.id,index,distanceMetres:0,animationPhase:0};l.reserve(id,[p.id]);l.occupy(p.id,id);settle(a);actors.set(id,a);}
  message=`Loaded ${ledger.snapshot().seated} seated / ${standingLedger.snapshot().seated} standing (study positions).`;
 }
 function alight(count=1,{balanced=false}={}){let selected=[...actors.values()].filter(occupied).sort((a,b)=>Number(!a.doorBufferId)-Number(!b.doorBufferId)||Number(!!a.seatId)-Number(!!b.seatId)||a.index-b.index);
  if(balanced){const groups=doors.map(d=>selected.filter(a=>a.doorId===d.id).sort((a,b)=>Number(!a.doorBufferId)-Number(!b.doorBufferId)||Number(!!a.seatId)-Number(!!b.seatId)||a.index-b.index));selected=[];while(groups.some(g=>g.length))for(const g of groups)if(g.length)selected.push(g.shift());}
  selected=selected.slice(0,count);if(!selected.length)return 0;const plan=planExitDoors(selected,doors,{policy:exitPolicy,active:[...actors.values()].filter(a=>a.exiting),service:exitPace?.service??{},walk:exitPace?.walk??.95});exitPlan=plan.summary;let n=0;for(const a of selected){
   const d=doors.find(d=>d.id===plan.assignment.get(a.id));a.doorId=d.id;core.requestAlighting(a,'exit queue');a.motion=a.seatId?'Sit':'Idle';n++;
  }if(exitFlow.pending.length===0)waitForEntries=[...actors.values()].some(a=>a.actions&&!a.exiting);exitFlow.schedule(selected);message=`${n} passengers requested to alight; two-stream route reservations, door clearance places first.`;return n;}
 const walk=(x,y,z)=>({type:'walk',x,y,z});
 function planBoard(a,c){const p=place(a),approach=a.seatId?{x:p.anchor.x+p.forward.x*.23,z:Math.sign(p.anchor.z)*.45}:{x:p.x,z:p.z};
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
  if(p.done){a.legPose=null;a.y=p.endY;a.enteredAt=time;lastBoardDoorAt=time;record('board-door-clear',a);advance(a);}
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
  if(exitFlow.preparing){exitFlow.prepare(2);return;}time+=dt;const currentEntries=[...actors.values()].some(a=>a.actions&&!a.exiting);if(!currentEntries)waitForEntries=false;exitFlow.update(waitForEntries?0:dt,doorsOpen);
  const outbound=d=>[...actors.values()].some(a=>a.doorId===d&&(a.stage==='exit queue'||a.exiting&&a.egressClearAt==null));
  for(const c of channels){const back=entryActors(c).sort((a,b)=>b.z-a.z)[0];if(!outbound(c.door.id)&&c.queue.length&&time>=c.next&&(!back||back.z<=2.45-entryGap)){
   const a=c.queue[0];if(!a.seatId&&!a.standingId)reservePlace(a,c);
   const doorway=a.doorBufferId&&doorwayMovementNearby(a);if((a.seatId||a.standingId)&&!doorway){c.queue.shift();c.next=time+.9;planBoard(a,c);}
  }}
  for(const c of channels)c.queue.forEach((a,i)=>{const activeBack=entryActors(c).sort((a,b)=>b.z-a.z)[0],preceding=i?c.queue[i-1]:activeBack,targetZ=Math.max(2.45+i*.8,preceding?preceding.z+.8:0),targetX=c.x,dx=targetX-a.x,dz=targetZ-a.z,d=Math.hypot(dx,dz),move=Math.min(d,dt*.85);if(d>.001){a.x+=dx/d*move;a.z+=dz/d*move;a.heading=angle(a.heading,Math.atan2(-dz,dx),Math.min(1,dt*8));}a.distanceMetres+=move;a.speedMps=dt?move/dt:0;a.motion=move>.00001?'Walk':'Idle';});
  const moving=[...actors.values()].sort((a,b)=>Number(!!b.exiting)-Number(!!a.exiting)||(a.exiting?Math.abs(a.x-(channels.find(c=>c.id===a.channel)?.x??0))-Math.abs(b.x-(channels.find(c=>c.id===b.channel)?.x??0)):a.index-b.index));
  for(const a of moving){
   const action=a.actions?.[a.actionIndex];if(!action)continue;const c=channels.find(c=>c.id===a.channel),open=doorIsOpen(doorsOpen,c.door.id);
   if(!a.actionStart)a.actionStart={x:a.x,y:a.y,z:a.z,heading:a.heading};a.poseBlend=null;
   if(action.type==='stairs'&&!open){a.speedMps=0;a.stage='waiting for open door';continue;}
   const oldTime=a.actionTime,oldZ=a.z;a.actionTime+=dt;if(action.type!=='stairs')a.legPose=null;
   if(action.type==='walk'){
    a.stage='walking';const dx=action.x-a.x,dz=action.z-a.z,d=Math.hypot(dx,dz);let move=Math.min(d,dt*.95);const leader=dz<0&&Math.abs(a.x-c.x)<.20?leaderOf(a,c):null;if(leader)move=Math.min(move,Math.max(0,(a.z-leader.z-entryGap)*d/-dz));a.speedMps=dt?move/dt:0;a.motion=move>0?'Walk':'Idle';if(d>.001){a.heading=angle(a.heading,Math.atan2(-dz,dx),Math.min(1,dt*8));a.x+=dx/d*move;a.z+=dz/d*move;a.distanceMetres+=move;}a.y=action.y;if(d<=move+.002)advance(a);
   }else if(action.type==='door'){a.stage='waiting for open door';a.motion='Idle';a.speedMps=0;if(open)advance(a);
   }else if(action.type==='stairs'){a.stage='climbing measured entry steps';const leader=leaderOf(a,c);const blocked=t=>{const z=entrySample(c,t).z;return leader&&z<leader.z+entryGap;};if(blocked(a.actionTime)){let lo=oldTime,hi=a.actionTime;for(let i=0;i<16;i++){const mid=(lo+hi)/2;if(!blocked(mid))lo=mid;else hi=mid;}a.actionTime=lo;}stepPose(a,c,a.actionTime);a.speedMps=dt?Math.abs(a.z-oldZ)/dt:0;
   }else if(action.type==='clear-entry'){if(c.entry===a.id)c.entry=null;advance(a);
   }else if(action.type==='turn'){a.stage='aligning with place';a.motion='Idle';a.speedMps=0;a.heading=angle(a.actionStart.heading,action.heading,smooth(Math.min(1,a.actionTime/.4)));if(a.actionTime>=.4)advance(a);
   }else if(action.type==='sit'){
    a.stage='sitting down';a.motion='Sit';a.speedMps=0;const t=smooth(Math.min(1,a.actionTime/.8)),s=action.seat,p=seatRoot(s);a.poseBlend={from:'Idle',to:'Sit',weight:t};a.x=lerp(a.actionStart.x,p.x,t);a.z=lerp(a.actionStart.z,p.z,t);a.y=lerp(a.actionStart.y,p.y,t);a.heading=s.heading;if(a.actionTime>=.8){settle(a);core.occupySeat(a.id,s.id);boarded++;}
   }else if(action.type==='stand'){settle(a);standingLedger.occupy(a.standingId,a.id);boarded++;
   }
  }
 }
 return {setExitPolicy(value){if(!['balanced','boarding'].includes(value))throw new Error('Unknown exit policy');exitPolicy=value;},layout,ledger,standingLedger,actors,channels,events,enqueue,preload,alight,get time(){return time;},get active(){return [...actors.values()].find(a=>a.actions||a.exiting||a.yielding)||null;},get message(){return message;},
 update(dt,{doorsOpen=true}={}){if(!Number.isFinite(dt)||dt<0)throw new Error('Non-negative finite dt required');if(dt===0){tick(0,doorsOpen);return;}for(let left=dt;left>1e-8;left-=.025)tick(Math.min(left,.025),doorsOpen);},
 snapshot(){const active=[...actors.values()].filter(a=>a.actions||a.exiting||a.yielding),st=standingLedger.snapshot();return {waitingAvoidance:exitFlow.diagnostics,planningExits:exitFlow.preparing,scheduledExits:exitFlow.pending.length,exitPolicy,exitPlan,vehicleId,simulationTime:time,boarded,lastBoardDoorAt,lastExitDoorAt,lastExitRouteAt,...ledger.snapshot(),standing:st.seated,standingReserved:st.reserved,studyStandingPlaces:st.mappedSeats,queued:channels.reduce((n,c)=>n+c.queue.length,0),waitingForPlace:[...actors.values()].filter(a=>a.stage==='queue'&&!a.seatId&&!a.standingId).length,exited,active:active[0]?{id:active[0].id,stage:active[0].stage,seatId:active[0].seatId}:null,moving:active.length,doorStreams:channels.map(c=>({id:c.id,queued:c.queue.length,alighted:c.alighted,entry:c.entry??entryActors(c)[0]?.id??null,climbing:entryActors(c).filter(a=>a.legPose).length,descending:[...actors.values()].filter(a=>a.channel===c.id&&a.exiting&&a.legPose).length,direction:[...actors.values()].some(a=>a.doorId===c.door.id&&(a.stage==='exit queue'||a.exiting&&a.egressClearAt==null))?'out':'in'})),message};}};
}
