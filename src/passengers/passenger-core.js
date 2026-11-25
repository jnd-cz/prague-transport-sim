// SPDX-License-Identifier: AGPL-3.0-or-later
// The project's own passenger lab, street-life-boarding v14 (2026-10-27), dist/traffic/passenger-core.js, as it was (sha256 79d84c76ffbdca0d);
// accepted by the user as "good enough for now" (2026-10-27). #249 step 1: brought in unchanged; step 2 fits it to the game.
// Renderer-independent passenger identity, place ownership and door predicates.
// Vehicle-specific routes, steps, queues and collision rules remain with adapters.
import {createSeatLedger} from './occupancy.js';
export function validateVehiclePlaces({doors,seats}){
 if(!Array.isArray(doors)||!doors.length||!Array.isArray(seats))throw new Error('Vehicle needs doors and seats');
 for(const [kind,items] of [['door',doors],['seat',seats]]){const ids=new Set();for(const item of items){if(!item.id||ids.has(item.id))throw new Error(`Missing or duplicate ${kind} id`);ids.add(item.id);const x=kind==='door'?item.x:item.anchor?.x;if(!Number.isFinite(x)||(kind==='seat'&&!Number.isFinite(item.anchor?.z)))throw new Error(`Invalid ${kind} coordinates`);}}
}
export function createPassengerCore({vehicleId,seats,doors,standing=[] ,capacity=null,idDigits=4}){
 if(!vehicleId)throw new Error('Vehicle id required');validateVehiclePlaces({doors,seats});
 const actors=new Map(),ledger=createSeatLedger({seats,capacity}),standingLedger=createSeatLedger({seats:standing});let serial=0;
 return {actors,ledger,standingLedger,
  nextIdentity(){const index=++serial;return{id:`${vehicleId}:P${String(index).padStart(idDigits,'0')}`,index};},
  startBoarding(actor,stage){if(actor.stage!=='queue')throw new Error('Passenger must be waiting to board');actor.stage=stage;},
  requestAlighting(actor,stage){if(!['seated','standing'].includes(actor.stage))throw new Error('Passenger must be aboard to alight');actor.stage=stage;},
  reserveSeat(id,preferred){return ledger.reserve(id,preferred);},
  occupySeat(id,seatId){ledger.occupy(seatId,id);},
  releasePlace(actor){return (actor.seatId?ledger:standingLedger).release(actor.id);},
  reset(){actors.clear();ledger.reset();standingLedger.reset();}
 };
}
export function doorIsOpen(doorsOpen,id){return typeof doorsOpen==='boolean'?doorsOpen:!!doorsOpen[id];}
