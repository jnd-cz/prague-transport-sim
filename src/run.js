// SPDX-License-Identifier: AGPL-3.0-or-later
// A run of the simulation from a plain options object (#226): our tram, the game, the traffic and the autopilot, and
// one step for all of them. src/main.js start() builds it from the menu's options (menuOpts) and steps it each frame;
// the benches start it with their own options (window.startRun) and step it in their loops (tools/bench/u3.js,
// redruns.js, walkers.js). Before, the benches set the menu, clicked Start and each copied the stepping loop.
// Nothing here reads the page: what the page draws of a run (our tram's model, the sound, the HUD) stays in main.js.
import { Tram } from './tram.js';
import { Game } from './game.js';
import { Traffic } from './traffic.js';
import { Autopilot } from './autopilot.js';
import { rng } from './random.js';

// world: what the page loaded for its line { scene, data, route, ground, audio }; o: the run's options:
//   seed (the run's seeded stream, src/random.js), cars, controls ('arcade' / 'advanced'), autopilot (it drives),
//   trip, startStop, weather, obstacles, assist, deadman, autoSwitch, toutAt (the outdoor temperature by the clock),
//   vehicle, dealer (the fleet's, its own stream from the seed), facts (the user's facts the game reads: substations,
//   speedFacts, signFacts), extra (Game options over these: the performance test's lead)
export function createRun({ scene, data, route, ground, audio }, o) {
  const tram = new Tram(o.cars);
  tram.eq.mode = o.controls;
  // one seeded stream for the whole run (rules and traffic), apart from Math.random
  const random = rng(o.seed);
  const game = new Game(scene, data, route, tram, audio, {
    weather: o.weather,
    tripIndex: o.trip,
    startStop: o.startStop,
    assist: o.assist,
    deadman: o.deadman,
    // onboard computer sets every switch by radio (no overhead contacts to work)
    autoSwitch: o.autoSwitch,
    autoIrc: o.autoSwitch,
    obstacles: o.obstacles,
    toutAt: o.toutAt,
    vehicle: o.vehicle,
    dealer: o.dealer,
    seed: Math.floor(random() * 1e9),
    ...o.facts,
    ...o.extra,
  });
  game.runSeed = o.seed; // (replay: ?seed=N)
  const traffic = new Traffic(scene, data, route, ground, game, random);
  const pilot = o.autopilot ? new Autopilot() : null;
  game.autopilot = !!pilot;
  const run = {
    game, traffic, pilot, tram,
    // the game's half of a step: the autopilot (`driver`: the page's, which a key turns on and off; else the run's),
    // the tram and the rules. The traffic's focus is taken first, where the step begins (src/traffic.js update).
    // go: whether the traffic steps with it (not while paused, nor once the shift ended before this step)
    stepGame(h, input, driver = run.pilot) {
      const focus = traffic.focus(), ended = game.finished;
      if (driver && !game.paused && !game.finished) driver.step(game, h);
      game.update(h, driver ? driver.input : input);
      return { h, focus, go: !game.paused && !ended };
    },
    // the traffic's half: `view` the camera (for what only drawing reads), draw: pose for drawing
    stepTraffic(s, view = null, draw = true) {
      if (s.go) traffic.update(s.h, view, draw, s.focus);
    },
    step(h, input = null, view = null, draw = true) {
      const s = run.stepGame(h, input);
      run.stepTraffic(s, view, draw);
      return s;
    },
  };
  return run;
}
