// SPDX-License-Identifier: AGPL-3.0-or-later
// The project's own passenger lab, street-life-boarding v14 (2026-10-27), dist/traffic/passenger-tests.js, as it was (sha256 ae74eedd2fed8cab);
// accepted by the maintainer as good enough for now (2026-10-27). #249 step 1: brought in unchanged; step 2 fits it to the game.
// Scenario/timing orchestration; no renderer or wall clock. All times are simulation seconds.
export function createPassengerTests(controller){
 let run=null,history=[];
 function begin(kind){controller.preload(0);run={kind,status:'running',phase:kind==='full'?'boarding':'exchange',startedAt:controller.time,phaseAt:controller.time,eventCursor:0,timings:{},perDoor:{},counts:{},assumptions:{walkingMps:.95,entryFootTransferSeconds:.64,entryCentreGapMetres:.72,doors:3,streamsPerDoor:2,doorsInitiallyOpen:true,standingPlacement:controller.layout.standing.placement.kind,packing:controller.layout.standing.selected,exitPolicy:controller.snapshot().exitPolicy,waitingBodyMode:controller.snapshot().waitingAvoidance.mode}};
  if(kind==='full'){run.target=24+controller.standingLedger.seats.length;controller.enqueue(run.target);}else if(kind==='waiting'){controller.preload(24,12);run.target=6;controller.alight(6,{balanced:true});run.outgoingIds=[...controller.actors.values()].filter(a=>a.stage==='exit queue').map(a=>a.id);run.eventCursor=0;}else{
   controller.preload(24,6);run.target=30;controller.alight(10,{balanced:true});run.outgoingIds=[...controller.actors.values()].filter(a=>a.stage==='exit queue').map(a=>a.id);run.outgoingSeated=run.outgoingIds.filter(id=>controller.actors.get(id).seatId).length;controller.enqueue(10,null,null,{waitForPlace:true});
  }
  return report();
 }
 function update(){if(!run||run.status!=='running')return;const r=controller.snapshot();
  for(const event of controller.events.slice(run.eventCursor)){
   const d=run.perDoor[event.doorId]??={out:0,in:0,firstIncomingAt:null,lastOutgoingClearAt:null,lastOutgoingDoorAt:null};
   if(event.type==='board-admitted'){d.in++;if(run.kind==='mixed'&&d.firstIncomingAt===null)d.firstIncomingAt=event.time-run.startedAt;}
   if(event.type==='exit-door-clear'){d.out++;d.lastOutgoingDoorAt=event.time-run.phaseAt;if(run.kind==='mixed')run.timings.tenOutDoorClear=event.time-run.startedAt;}
   if(event.type==='exit-channel-clear')d.lastOutgoingClearAt=event.time-run.startedAt;
  }
  run.eventCursor=controller.events.length;run.elapsed=r.simulationTime-run.startedAt;run.counts={seated:r.seated,standing:r.standing,queued:r.queued,waitingForPlace:r.waitingForPlace,exited:r.exited};
  if(run.kind==='full'&&run.phase==='boarding'&&r.seated+r.standing===run.target){run.timings.boardingDoorClear=r.lastBoardDoorAt-run.startedAt;run.timings.boardingSettled=run.elapsed;run.phase='alighting';run.phaseAt=controller.time;controller.alight(run.target);}
  if(run.kind==='full'&&run.phase==='alighting'&&r.exited===run.target){run.timings.alightingDoorClear=r.lastExitDoorAt-run.phaseAt;run.timings.alightingRouteComplete=controller.time-run.phaseAt;finish();}
  if(run.kind==='mixed'&&r.exited===10&&r.seated+r.standing===30&&r.queued===0&&r.moving===0){run.timings.exchangeComplete=run.elapsed;run.timings.lastIncomingDoorClear=r.lastBoardDoorAt-run.startedAt;run.timings.lastOutgoingRouteComplete=r.lastExitRouteAt-run.startedAt;finish();}
  run.waitingAvoidance=r.waitingAvoidance;
  if(run.kind==='waiting'&&r.exited===6&&r.moving===0&&r.planningExits===0){run.timings.waitingComplete=run.elapsed;finish();}
  if(r.waitingAvoidance.blocked.length&&r.moving===0&&r.planningExits===0&&r.scheduledExits===0){run.status='blocked';run.phase='waiting for clearance';}
  if(run.elapsed>480){run.status='stalled';run.phase='stalled';}
 }
 function finish(){run.status='complete';run.phase='complete';history.push(structuredClone(run));if(history.length>8)history.shift();}
 function report(){return run?structuredClone(run):{status:'idle',phase:'idle',timings:{},elapsed:0};}
 return {startFull:()=>begin('full'),startMixed:()=>begin('mixed'),startWaiting:()=>begin('waiting'),update,report,get history(){return structuredClone(history);},cancel(){run=null;}};
}
