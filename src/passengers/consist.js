// SPDX-License-Identifier: AGPL-3.0-or-later
// A tram set's passengers (#249 step 2): the passenger lab's boarding controller (boarding-state.js) for each car, on the game's T3
// cabin (assets/passengers/t3-cabin.json, tools/cabin.py --game: 24 seats and 81 standing places, the user's 105 shown a car), behind the
// game's counts (src/game.js). Everything here is in the cars' own frames, never the world's; nothing is drawn (step 3 draws it).
//
// The user's rules (2026-11-25, #249):
// - about one boarder in five wishes to stand though seats are free (STAND_SHARE, a trait drawn from the game's seeded stream);
// - who alights: the passengers nearest a door by walking (boarding-state.js alight's nearest), the counted ones first;
// - a seat come free by a door whose exchange is over goes to the nearest standing passenger who does not wish to stand, walking at
//   RESEAT_SPEED round the others, also while the tram drives;
// - above the places shown, up to the car's declared capacity (the crush load), passengers are counted only: they climb the steps
//   like the others and join the count at their head, and leave first, from the doorways, through the doors in turn.
// A passenger is aboard from the head of the entry steps in to their foot out (a.aboard): the counts change there, which is where
// the game's crossings are (update's list) and what the autopilot waits for.
import { createBoardingController } from './boarding-state.js';
import { GAME_PACE } from './exit-flow.js';
import { createCabinNavigator } from './cabin-navigation.js';

export const STAND_SHARE = 0.2; // (the user: "some people boarding can stand even with free seats"; revisited with journeys, #40)
export const RESEAT_SPEED = 0.8; // m/s: a slow walk to a seat inside
const RESEAT_EVERY = 1; // s between the looks for free seats
const RESEAT_TRIES = 3; // ways looked for a look and a car (cabin-navigation.js: about a millisecond each)

// layout: the cabin; cars; crush: a car's declared capacity (src/tram.js T3.crushCapacity); rand: the game's seeded stream for the
// passengers (src/random.js)
export function createConsist(layout, { cars, crush, rand }) {
  const shown = layout.seats.length + layout.standing.places.length, extra = Math.max(0, crush - shown);
  const set = [], platform = [], crossings = [];
  const tally = { start: 0, in: 0, out: 0 };
  let reseatT = 0;
  const actorsOf = (car) => car.c.actors.values();
  // (aboard: on the floor, the counted ones with them; incoming: boarders not yet up the steps; outgoing: aboard and to alight)
  const aboard = (car) => { let n = car.counted; for (const a of actorsOf(car)) if (a.aboard) n++; return n; };
  const incoming = (car) => { let n = 0; for (const a of actorsOf(car)) if (!a.aboard && !a.exiting) n++; return n; };
  const outgoing = (car) => { let n = 0; for (const a of actorsOf(car)) if (a.aboard && (a.exiting || a.stage === 'exit queue')) n++; return n; };
  const room = (car) => crush - aboard(car) - incoming(car) + outgoing(car);
  // (the ways round the others to a freed seat, one grid for the cars: its ids are the cars' own)
  const navigator = layout.navigation ? createCabinNavigator(layout) : null;
  for (let k = 0; k < cars; k++) {
    const car = { k, counted: 0, flight: 0 };
    car.c = createBoardingController(layout, {
      vehicleId: `car${k + 1}`, exitPace: GAME_PACE, prepareStops: false, keepEvents: false, navigator,
      // (a boarder with no place left: counted, if nobody is still to leave the car and its count has room)
      overflow: () => { if (outgoing(car) > 0 || car.counted + car.flight >= extra) return false; car.flight++; return true; },
      onEvent: (type, a) => {
        if (type === 'board-door-clear') { tally.in++; crossings.push({ dir: 'in', tag: a.tag, car: k, lane: a.channel }); }
        else if (type === 'exit-door-clear') { tally.out++; crossings.push({ dir: 'out', car: k, lane: a.channel }); }
        else if (type === 'counted') { car.flight--; car.counted++; }
      },
    });
    set.push(car);
  }
  const stands = () => rand() < STAND_SHARE;

  // the boarders not yet given a car go to the one with the most room (the fewest coming, then the front first); a runner to the
  // rear car's rear door (src/game.js _spawnRunners)
  function assign() {
    for (let i = 0; i < platform.length;) {
      const b = platform[i];
      const car = b.car != null ? (room(set[b.car]) > 0 ? set[b.car] : null)
        : set.filter((c) => room(c) > 0).sort((x, y) => room(y) - room(x) || incoming(x) - incoming(y) || x.k - y.k)[0];
      if (!car) { i++; continue; }
      car.c.enqueue(1, null, b.door, { waitForPlace: true, extra: { tag: b.tag, stands: b.stands } });
      platform.splice(i, 1);
    }
  }

  return {
    cars: set, shown, extra,
    // n passengers on board at the start, spread over the cars; the number now on board
    load(n) {
      for (let k = 0; k < cars; k++) {
        const car = set[k], m = Math.floor(n / cars) + (k < n % cars ? 1 : 0), placed = car.c.seatAboard(m, { rand, stands });
        car.counted += Math.min(extra, m - placed);
      }
      tally.start = this.aboard;
      return tally.start;
    },
    get aboard() { return set.reduce((n, car) => n + aboard(car), 0); },
    // passengers still to alight (scheduled, not yet down the steps), and boarders of a stop's tag not yet up them
    get toAlight() { return set.reduce((n, car) => n + outgoing(car), 0); },
    waiting(tag) {
      let n = platform.filter((b) => b.tag === tag).length;
      for (const car of set) for (const a of actorsOf(car)) if (!a.aboard && !a.exiting && a.tag === tag) n++;
      return n;
    },
    // n boarders of a stop (tag) on the platform; car and door for a runner's
    board(n, tag, { car = null, door = null } = {}) { for (let i = 0; i < n; i++) platform.push({ tag, car, door, stands: stands() }); },
    // n of those aboard and not yet leaving alight: the nearest to a door in the whole set by walking, the counted ones first
    // (in the doorways), one car after another; the number scheduled
    alight(n) {
      const pick = [];
      for (const car of set) {
        for (let i = 0; i < car.counted; i++) pick.push({ car, d: -1, i });
        for (const a of actorsOf(car)) if ((a.stage === 'seated' || a.stage === 'standing') && !a.counted) pick.push({ car, d: car.c.doorDistance(a), i: a.index });
      }
      pick.sort((x, y) => x.d - y.d || x.i - y.i || x.car.k - y.car.k);
      let total = 0;
      for (const car of set) {
        const mine = pick.slice(0, n).filter((p) => p.car === car), counted = mine.filter((p) => p.d < 0).length;
        car.counted -= counted;
        total += car.c.alight(mine.length - counted, { nearest: true, counted });
      }
      return total;
    },
    // the boarders of a stop not yet on the steps go home (the doors closed on them, or the set is full); the number
    abandon(tag) {
      let n = 0;
      for (let i = platform.length - 1; i >= 0; i--) if (platform[i].tag === tag) { platform.splice(i, 1); n++; }
      for (const car of set) for (const a of car.c.abandon((a) => a.tag === tag)) { n++; if (a.counted) car.flight--; }
      return n;
    },
    // boarders waiting on the platform with no room in any car and nobody left to alight
    get full() { return platform.length > 0 && set.every((c) => room(c) <= 0 && outgoing(c) === 0); },
    // those of a stop still on the platform stay there (the set is full); the number
    leaveFull(tag) {
      let n = 0;
      for (let i = platform.length - 1; i >= 0; i--) if (platform[i].tag === tag) { platform.splice(i, 1); n++; }
      return n;
    },
    // a step of dt s; open: the doors are open with the tram standing at the stop (new crossings only then). The crossings in it:
    // [{ dir: 'in' | 'out', tag, car, lane (the door's stream, as 'Front:1') }]
    update(dt, open) {
      crossings.length = 0;
      assign();
      for (const car of set) car.c.update(dt, { doorsOpen: open });
      if ((reseatT += dt) >= RESEAT_EVERY) {
        reseatT = 0;
        for (const car of set) car.c.reseat({ speed: RESEAT_SPEED, tries: RESEAT_TRIES });
      }
      return crossings;
    },
    // what is wrong with the counts and places (nothing: []): the count from the start and the crossings against the passengers on
    // board, every place's holder there and holding it, every settled passenger's place theirs, the counted ones within the car's room
    check() {
      const bad = [], total = this.aboard;
      if (tally.start + tally.in - tally.out !== total) bad.push(`count ${tally.start} + ${tally.in} in - ${tally.out} out != ${total} aboard`);
      for (const car of set) {
        const { actors, ledger, standingLedger } = car.c;
        for (const [l, key] of [[ledger, 'seatId'], [standingLedger, 'standingId']]) {
          for (const p of l.seats) {
            if (p.status === 'free') continue;
            const a = actors.get(p.passengerId);
            if (!a) bad.push(`car ${car.k + 1}: ${p.id} held by ${p.passengerId}, who is not there`);
            else if (a[key] !== p.id && a.reseatFrom !== p.id) bad.push(`car ${car.k + 1}: ${p.id} held by ${a.id}, whose place is ${a[key]}`);
          }
        }
        for (const a of actors.values()) {
          if (a.counted || (a.stage !== 'seated' && a.stage !== 'standing')) continue;
          const p = (a.seatId ? ledger : standingLedger).seats.find((s) => s.id === (a.seatId ?? a.standingId));
          if (!p || p.passengerId !== a.id || p.status !== 'occupied') bad.push(`car ${car.k + 1}: ${a.id} ${a.stage} at ${a.seatId ?? a.standingId}, not theirs`);
        }
        if (car.counted < 0 || car.flight < 0 || car.counted + car.flight > extra) bad.push(`car ${car.k + 1}: counted ${car.counted}, coming ${car.flight}`);
        if (aboard(car) > crush) bad.push(`car ${car.k + 1}: ${aboard(car)} aboard, over ${crush}`);
      }
      return bad;
    },
  };
}
