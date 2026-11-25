// SPDX-License-Identifier: AGPL-3.0-or-later
// The project's own passenger lab, street-life-boarding v14 (2026-10-27), dist/traffic/occupancy.js, as it was (sha256 56c16fd032bb58f7);
// accepted by the user as "good enough for now" (2026-10-27). #249 step 1: brought in unchanged; step 2 fits it to the game.
// Session/simulation data only. No Three.js or DOM references.
export function createSeatLedger(layout){
 const seats=layout.seats.map(s=>({id:s.id,status:'free',passengerId:null})),map=new Map(seats.map(s=>[s.id,s]));
 if(map.size!==seats.length)throw new Error('Seat ids must be unique');
 const already=id=>seats.some(s=>s.passengerId===id);
 return {seats,reserve(passengerId,preferredIds=seats.map(s=>s.id)){
  if(!String(passengerId).trim())throw new Error('Passenger id required');if(already(passengerId))throw new Error('Passenger already has a seat');
  const s=preferredIds.map(id=>map.get(id)).find(s=>s?.status==='free');if(!s)return null;s.status='reserved';s.passengerId=passengerId;return s.id;
 },reserveMove(passengerId,targetId){const source=seats.find(s=>s.passengerId===passengerId&&s.status==='occupied'),target=map.get(targetId);if(!source||target?.status!=='free'||seats.some(s=>s.passengerId===passengerId&&s.status==='reserved'))return null;Object.assign(target,{status:'reserved',passengerId,relocation:true});return targetId;},releasePlace(placeId,passengerId){const s=map.get(placeId);if(!s||s.passengerId!==passengerId)return false;Object.assign(s,{status:'free',passengerId:null,relocation:false});return true;},occupy(seatId,passengerId){const s=map.get(seatId);if(!s||s.status!=='reserved'||s.passengerId!==passengerId)throw new Error('Seat reservation does not belong to this passenger');s.status='occupied';s.relocation=false;},
 release(passengerId){const s=seats.find(s=>s.passengerId===passengerId);if(!s)return false;s.status='free';s.passengerId=null;s.relocation=false;return true;},
 reset(){seats.forEach(s=>{s.status='free';s.passengerId=null;s.relocation=false;});},snapshot(){return{seated:seats.filter(s=>s.status==='occupied').length,reserved:seats.filter(s=>s.status==='reserved').length,free:seats.filter(s=>s.status==='free').length,mappedSeats:seats.length,nominalTotal:layout.capacity?.nominalTotal??null,standingLimit:layout.capacity?.operationalStandingLimit??null};}};
}
