# SPDX-License-Identifier: AGPL-3.0-or-later
"""A tram set's passengers (#249 step 2): python -P -E tools/test_consist.py (its own server on a free port).

The game's cabin (assets/passengers/t3-cabin.json, tools/cabin.py --game) is the hybrid T3's (its assetSha256 the model's):
24 seats and 81 standing places, 105 shown, no two standing outlines overlapping, none in the cab. In a page, the set's
passengers (src/passengers/consist.js) on two cars, by the user's rules (2026-11-25, #249):
- a half-empty set's exchange (50 aboard, 15 off, 20 on): everyone across, the counts and places right (check()), the
  alighters the nearest to a door in the set, and the same crossings twice for one seed;
- about one boarder in five wishes to stand: into an empty set they stand though seats are free, the others sit;
- the seats freed at a stop go to standing passengers who do not wish to stand, while the tram drives on; those who wish
  to stand stay standing;
- above the 105 shown, counted passengers up to the crush load (160 a car): a full set takes what it has room for and the
  rest stay on the platform; the counted ones alight first;
- the front door beside the cab takes both its streams, in and out, two people on its steps at once;
- the doors closed during the exchange: who is on the steps finishes the way, the queue stays behind, those still to
  alight get off when the doors open again; the counts right throughout;
- (step 4, the user, 2026-11-26: "those getting off at the stop needs to be prepared often, to be ready to go once door
  opens") the stop near, those to alight there go to their doors' doorway places while the tram drives, nobody else moving;
  the same ones alight, sooner after the doors open than from their places, the boarders after them; one whose stop comes
  while they are on the way alights from where they get to.
- (Dveře I, the user, 2026-11-26: "only the 1st door in car where driver sits") with the first car's front door alone open,
  the boarders queued at both cars' shut doors all get on through it, the second car's handed to the first where they stand;
  the first car's alighters leave through it, the second car's stay aboard until all the doors open; the counts right.
And tools/cabin.py's game_cabin keeps one packing and what the passenger modules read.
"""
import faulthandler
import functools
import hashlib
import http.server
import os
import re
import sys
import threading

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves tools/ out)
import cabin  # noqa: E402
import gpu  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PAGE = """async () => {
  const { createConsist, STAND_SHARE } = await import('/src/passengers/consist.js');
  const { createBoardingController } = await import('/src/passengers/boarding-state.js');
  const { transformFootprint, convexOverlap } = await import('/src/passengers/packing-geometry.js');
  const { rng } = await import('/src/random.js');
  const L = await (await fetch('/assets/passengers/t3-cabin.json')).json();
  const H = 1 / 30, out = {};
  const world = L.standing.places.map((p) => transformFootprint(p.footprintPolygon, p.x, p.z, p.heading));
  let pairs = 0;
  for (let i = 0; i < world.length; i++) for (let j = i + 1; j < world.length; j++) if (convexOverlap(world[i], world[j])) pairs++;
  let cab = null;
  try { createBoardingController(L); } catch (e) { cab = String(e); }
  out.cabin = { sha: L.assetSha256, seats: L.seats.length, standing: L.standing.places.length, shown: L.capacity.shown, pairs, cab };
  const set = (load, seed = 1, cars = 2) => { const p = createConsist(L, { cars, crush: 160, rand: rng(seed) }); p.load(load); return p; };
  // (steps until everyone of tag 7 is across and nobody is to alight; the crossings' times)
  // (and 2 s more: the last ones in walk on from the head of the steps)
  const run = (p, open = true, most = 120) => {
    const times = [];
    let t = 0, ins = 0, outs = 0, left = 0;
    for (; t < most; t += H) {
      for (const x of p.update(H, open)) { times.push(`${x.dir}${Math.round(t * 1000)}`); if (x.dir === 'in') ins++; else outs++; }
      if (p.full) left += p.leaveFull(7);
      if (p.waiting(7) === 0 && p.toAlight === 0) break;
    }
    for (let i = 0; i < 2 / H; i++) p.update(H, open);
    return { t: +t.toFixed(2), ins, outs, left, times };
  };
  const occupied = (p) => p.cars.flatMap((car) => [...car.c.actors.values()].filter((a) => (a.stage === 'seated' || a.stage === 'standing') && !a.counted).map((a) => ({ a, car })));

  // the half-empty exchange
  {
    const p = set(50);
    const before = occupied(p);
    p.board(20, 7);
    const n = p.alight(15);
    const leaving = before.filter(({ a }) => a.stage === 'exit queue'), staying = before.filter(({ a }) => a.stage !== 'exit queue');
    const far = Math.max(...leaving.map(({ a, car }) => car.c.doorDistance(a))), near = Math.min(...staying.map(({ a, car }) => car.c.doorDistance(a)));
    const r = run(p), again = set(50);
    again.board(20, 7);
    again.alight(15);
    const r2 = run(again);
    out.half = { n, far, near, ...r, times: undefined, same: JSON.stringify(r.times) === JSON.stringify(r2.times), aboard: p.aboard, check: p.check() };
  }
  // the wish to stand: into an empty set, 20 a car
  {
    let standers = 0, boarders = 0, wrong = 0;
    for (let seed = 1; seed <= 10; seed++) {
      const p = set(0, seed);
      p.board(40, 7);
      run(p);
      for (const car of p.cars) for (const a of car.c.actors.values()) {
        boarders++;
        if (a.stands) standers++;
        if (a.stands !== !!a.standingId || a.stands === !!a.seatId) wrong++;
      }
    }
    out.stand = { standers, boarders, wrong, share: STAND_SHARE };
  }
  // the freed seats: seats full and some standing, 30 off, then 20 s of driving
  {
    const p = set(80, 3);
    const standers = () => p.cars.map((car) => [...car.c.actors.values()].filter((a) => a.stage === 'standing' && a.stands).length);
    const sitters = () => p.cars.map((car) => [...car.c.actors.values()].filter((a) => a.stage === 'standing' && !a.stands).length);
    const free = () => p.cars.map((car) => car.c.ledger.seats.filter((s) => s.status === 'free').length);
    p.alight(30);
    run(p);
    const f1 = free(), w1 = sitters(), s1 = standers();
    for (let i = 0; i < 20 / H; i++) p.update(H, false);
    out.reseat = { standersBefore: s1, standersAfter: standers(), sittersAtDoors: w1, freeAtDoors: f1, sittersAfter: sitters(), freeAfter: free(), check: p.check() };
  }
  // above the shown places: the crush load
  {
    const p = set(300);
    const counted0 = p.cars.map((c) => c.counted);
    p.board(40, 7);
    const r = run(p);
    const counted1 = p.cars.map((c) => c.counted);
    p.alight(10);
    run(p);
    out.crush = { counted0, counted1, ins: r.ins, aboard: p.aboard, left: r.left, counted2: p.cars.map((c) => c.counted), check: p.check() };
  }
  // the front door, beside the cab: both its streams, in and out, two people on its steps at once (the user, 2026-11-25: "I hope
  // the front door still fits two passengers going out or in at the same time"); one car, 80 aboard, 30 off, 30 on
  {
    const p = set(80, 2, 1), lanes = {}, most = { in: 0, out: 0 };
    p.board(30, 7);
    p.alight(30);
    for (let t = 0; t < 120; t += H) {
      for (const x of p.update(H, true)) { const k = `${x.lane} ${x.dir}`; lanes[k] = (lanes[k] || 0) + 1; }
      const steps = [...p.cars[0].c.actors.values()].filter((a) => a.legPose && a.doorId === 'Front');
      most.in = Math.max(most.in, steps.filter((a) => !a.exiting).length);
      most.out = Math.max(most.out, steps.filter((a) => a.exiting).length);
      if (p.waiting(7) === 0 && p.toAlight === 0) break;
    }
    out.front = { lanes, most };
  }
  // (#249 step 4) ready at the doors: the stop near, those to alight there go to their doors' doorway places with the doors closed
  // (12 s of driving), then alight when the doors open; against the same set alighting from where they sat. And one whose stop
  // comes 0.5 s after: those on the way alight from where they get to
  {
    const first = (r, d) => Math.min(...r.times.filter((s) => s.startsWith(d)).map((s) => +s.slice(d.length)));
    const last = (r, d) => Math.max(...r.times.filter((s) => s.startsWith(d)).map((s) => +s.slice(d.length)));
    // (as the game: alight, then the stop's boarders on the platform, when the tram stands at the stop)
    const p = set(50, 4), q = set(50, 4), late = set(50, 4);
    const before = new Map(occupied(p).map(({ a, car }) => [`${car.k}${a.id}`, { x: a.x, z: a.z, seat: a.seatId, place: a.standingId }]));
    const moving = p.ready(15), chosen = new Set(), bad = [];
    for (const car of p.cars) for (const a of car.c.actors.values()) if (a.toAlight) chosen.add(`${car.k}${a.id}`);
    for (let t = 0; t < 12; t += H) { p.update(H, false); if (Math.round(t / H) % 15 === 0) bad.push(...p.check()); }
    let atDoors = 0, stayed = 0, others = 0;
    for (const { a, car } of occupied(p)) {
      const k = `${car.k}${a.id}`, b = before.get(k);
      if (chosen.has(k)) { if (a.doorBufferId && a.standingId) atDoors++; else if (a.x === b.x && a.z === b.z) stayed++; }
      else if (a.x !== b.x || a.z !== b.z || a.seatId !== b.seat || a.standingId !== b.place) others++;
    }
    const n = p.alight(15), leaving = new Set();
    p.board(20, 7);
    for (const car of p.cars) for (const a of car.c.actors.values()) if (a.stage === 'exit queue') leaving.add(`${car.k}${a.id}`);
    const r = run(p);
    q.alight(15);
    q.board(20, 7);
    const qLeaving = new Set();
    for (const car of q.cars) for (const a of car.c.actors.values()) if (a.stage === 'exit queue') qLeaving.add(`${car.k}${a.id}`);
    const rq = run(q);
    late.ready(15);
    for (let t = 0; t < 0.5; t += H) late.update(H, false);
    const nLate = late.alight(15);
    late.board(20, 7);
    const rl = run(late);
    out.ready = {
      moving, chosen: chosen.size, atDoors, stayed, others, bad, n, outs: r.outs, ins: r.ins, check: p.check(),
      same: [...chosen].every((k) => leaving.has(k) && qLeaving.has(k)) && leaving.size === chosen.size && qLeaving.size === chosen.size,
      firstOut: first(r, 'out'), lastOut: last(r, 'out'), firstIn: first(r, 'in'),
      qFirstOut: first(rq, 'out'), qLastOut: last(rq, 'out'), qFirstIn: first(rq, 'in'),
      late: { n: nLate, outs: rl.outs, ins: rl.ins, aboard: late.aboard, check: late.check() },
    };
  }
  // the doors closed during the exchange, then opened again
  {
    const p = set(60, 5);
    p.board(30, 7);
    const n = p.alight(20);
    let ins = 0, outs = 0;
    const count = (xs) => { for (const x of xs) if (x.dir === 'in') ins++; else outs++; };
    for (let t = 0; t < 3.5; t += H) count(p.update(H, true));
    const onSteps = () => p.cars.reduce((k, car) => k + [...car.c.actors.values()].filter((a) => a.legPose).length, 0);
    const steps0 = onSteps(), gone = p.abandon(7);
    for (let t = 0; t < 10; t += H) count(p.update(H, false));
    const closed = { steps0, gone, steps1: onSteps(), waiting: p.waiting(7), toAlight: p.toAlight, ins, outs, check: p.check() };
    for (let t = 0; t < 60 && p.toAlight; t += H) count(p.update(H, true));
    out.closed = { n, ...closed, toAlightAfter: p.toAlight, insAfter: ins, outsAfter: outs, aboard: p.aboard, check2: p.check() };
  }
  // (#249, Dveře I, the user, 2026-11-26: "only the 1st door in car where driver sits"; those waiting walk to it, those to alight
  // leave through it) 60 aboard, 20 to alight and 24 queued at the shut doors of both cars; the first car's front door alone opens:
  // everyone boards through it, the second car's boarders handed to the first car where they stand (in its frame), the first car's
  // alighters out through it, the second car's stay aboard; then all the doors: they get off. The counts right throughout
  {
    const p = set(60, 6), spacing = 15.04, lanes = {}, bad = [];
    p.board(24, 7);
    const n = p.alight(20);
    const ofCar = p.cars.map((car) => [...car.c.actors.values()].filter((a) => a.stage === 'exit queue').length);
    for (let t = 0; t < 2; t += H) p.update(H, false);
    const queued = p.cars.map((car) => [...car.c.actors.values()].filter((a) => !a.aboard).length);
    const was = new Map([...p.cars[1].c.actors.values()].filter((a) => !a.aboard).map((a) => [a.id, { x: a.x - spacing, z: a.z }]));
    p.onlyDoor('Front', spacing);
    let t = 0, handed = 0, moved = 0;
    const count = (xs) => { for (const x of xs) { const k = `${x.car} ${x.lane.split(':')[0]} ${x.dir}`; lanes[k] = (lanes[k] || 0) + 1; } };
    count(p.update(H, [{ Front: true }]));
    for (const a of p.cars[0].c.actors.values()) {
      const w = a.from && was.get(a.from);
      if (w) { handed++; moved = Math.max(moved, Math.hypot(a.x - w.x, a.z - w.z)); }
    }
    for (; t < 150; t += H) {
      count(p.update(H, [{ Front: true }]));
      if (Math.round(t / H) % 30 === 0) bad.push(...p.check());
      if (p.waiting(7) === 0 && p.toAlight === ofCar[1]) break;
    }
    for (let i = 0; i < 2 / H; i++) count(p.update(H, [{ Front: true }]));
    const stuck = p.toAlight, aboard1 = p.aboard;
    p.onlyDoor(null);
    for (let i = 0; i < 60 / H && p.toAlight; i++) count(p.update(H, true));
    out.only = { n, ofCar, queued, was: was.size, handed, moved: +moved.toFixed(3), lanes, t: +t.toFixed(1), stuck, aboard1, after: p.toAlight, aboard: p.aboard, bad, check: p.check() };
  }
  return out;
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def importmap():
    html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    return re.search(r'<script type="importmap">.*?</script>', html, re.S).group(0)


def game_cabin_keeps():
    """tools/cabin.py's game_cabin on a small layout: one packing, the fields read, the floats rounded"""
    place = {"id": "p1", "x": 1.23456789, "y": .89, "z": -.3, "heading": .5, "footprintPolygon": [[-.1, 0], [0, -.1], [.1, 0]],
             "footprintWorld": [[0, 0]], "footprintHalfExtents": {"x": .1, "z": .1}, "doorId": "Rear", "doorBufferId": None,
             "phase": "window", "priority": 0, "distanceFromDoor": 3}
    layout = {"schemaVersion": "0.6.0", "assetId": "m", "assetSha256": "ab", "axes": {}, "units": "metres", "floorY": .89,
              "seats": [{"id": "s1", "anchor": {"x": 0, "y": 1, "z": .5}, "heading": 0, "forward": {"x": 1, "z": 0}, "width": .5, "mesh": "x"}],
              "exclusions": [{"id": "cab", "polygon": [[0, 0]], "sourceMeshes": []}], "doors": [{"id": "Rear", "x": -5}],
              "fitProfile": {"scale": {"x": 1}, "localSeatHeight": .4, "backwardOffsetMetres": .04, "status": "x"},
              "standing": {"bodyFootprint": {"sha256": "c", "polygon": [[0, 0]], "source": "x"},
                           "configurations": [{"id": "a", "places": [place]}, {"id": "b", "places": [place, place], "placement": {"count": 2}}]}}
    nav = {"schemaVersion": "0.1.0", "assetSha256": "ab", "cell": .02, "nx": 1, "nz": 1, "xMin": 0, "zMin": 0, "categories": [], "runs": [3, 1],
           "seatedFootprint": {"polygon": [[0, 0]]}, "method": "x"}
    c = cabin.game_cabin(layout, nav, "b")
    # (off_floor: a 4 x 2 grid of 0.1 m cells, circulation but one fixture cell at x 0.2-0.3, z 0-0.1)
    grid = {"cell": .1, "nx": 4, "nz": 2, "xMin": 0, "zMin": 0, "categories": ["outside", "cab", "fixtures", "legroom", "edge margin",
            "circulation", "standing pockets"], "runs": [5, 2, 2, 1, 5, 5]}
    on = {"id": "on", "footprintWorld": [[.02, .02], [.18, .02], [.18, .18], [.02, .18]]}
    off = {"id": "off", "footprintWorld": [[.12, .02], [.28, .02], [.28, .08], [.12, .08]]}
    return (c["capacity"] == {"seats": 1, "standing": 2, "shown": 3} and c["standing"]["selected"] == "b"
            and "footprintWorld" not in c["standing"]["places"][0] and c["standing"]["places"][0]["x"] == 1.2346
            and "configurations" not in c["standing"] and "mesh" not in c["seats"][0] and c["navigation"]["runs"] == [3, 1]
            and cabin.off_floor(grid, [on, off]) == [("off", ["fixtures"])])


def main():
    faulthandler.dump_traceback_later(600, exit=True)  # (page.evaluate has no time limit of its own)
    sha = hashlib.sha256(open(os.path.join(ROOT, "assets", "t3h", "tatra-t3-hybrid-nc.glb"), "rb").read()).hexdigest()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    fails = []
    try:
        with sync_playwright() as p:
            browser = gpu.launch(p)[0]
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route(base + "/__consist.html", lambda r: r.fulfill(
                content_type="text/html", body=f"<!doctype html><html><head>{importmap()}</head><body></body></html>"))
            page.goto(base + "/__consist.html")
            page.set_default_timeout(500000)
            r = page.evaluate(PAGE)
            browser.close()
            if errors:
                fails.append(f"page errors: {errors[:3]}")
    finally:
        server.shutdown()
        faulthandler.cancel_dump_traceback_later()
    c, h, s, w, k, d, f, y = r["cabin"], r["half"], r["stand"], r["reseat"], r["crush"], r["closed"], r["front"], r["ready"]
    yl = y["late"]
    fl = f["lanes"]
    o = r["only"]
    ol = o["lanes"]
    share = s["standers"] / s["boarders"]
    want = {
        "the cabin: the model's, 24 seats + 81 standing = 105, no outline overlapping another, none in the cab":
            c["sha"] == sha and (c["seats"], c["standing"], c["shown"], c["pairs"], c["cab"]) == (24, 81, 105, 0, None),
        f"half empty: 15 off and 20 on in {h['t']} s, 55 aboard, the counts right ({h['check'][:1]})":
            h["n"] == 15 and h["outs"] == 15 and h["ins"] == 20 and h["aboard"] == 55 and not h["check"] and h["t"] < 60,
        f"half empty: the alighters the nearest to a door ({h['far']:.2f} m at most, the others {h['near']:.2f} m at least)": h["far"] <= h["near"] + 1e-9,
        "half empty: one seed, the same crossings": h["same"],
        f"the wish to stand: {s['standers']} of {s['boarders']} ({share:.2f}, about {s['share']})": abs(share - s["share"]) < 0.08,
        f"into an empty set the standers stand and the others sit ({s['wrong']} not)": s["wrong"] == 0,
        f"the freed seats taken while driving: free {w['freeAtDoors']} -> {w['freeAfter']}, standing who would sit {w['sittersAtDoors']} -> {w['sittersAfter']}":
            all(f == 0 or n == 0 for f, n in zip(w["freeAfter"], w["sittersAfter"])) and sum(w["sittersAfter"]) < sum(w["sittersAtDoors"]) and not w["check"],
        f"those who wish to stand stay standing ({w['standersBefore']} -> {w['standersAfter']})": w["standersAfter"] == w["standersBefore"],
        f"the crush: counted {k['counted0']} -> {k['counted1']}, {k['ins']} of 40 aboard, {k['left']} left on the platform": k["counted0"] == [45, 45] and k["counted1"] == [55, 55] and k["ins"] == 20 and k["left"] == 20,
        f"the crush: the counted alight first ({k['counted1']} -> {k['counted2']}), the counts right": k["counted2"] == [50, 50] and k["aboard"] == 310 and not k["check"],
        f"the front door: both streams in and out ({ {k: v for k, v in sorted(fl.items()) if k.startswith('Front')} }), "
        f"on its steps at once {f['most']['in']} in, {f['most']['out']} out":
            all(fl.get(f"Front:{n} {d}", 0) > 0 for n in (0, 1) for d in ("in", "out")) and f["most"]["in"] >= 2 and f["most"]["out"] >= 2,
        f"ready: the stop near, the {y['chosen']} to alight go to their doors' doorway places ({y['atDoors']} there, {y['stayed']} "
        f"where they were), nobody else moves ({y['others']}), the counts and places right on the way ({y['bad'][:1]})":
            y["chosen"] == 15 and y["atDoors"] + y["stayed"] == 15 and y["atDoors"] >= 12 and y["others"] == 0 and not y["bad"],
        f"ready: the same {y['n']} alight as from their places, the counts right": y["same"] and y["n"] == 15 and y["outs"] == 15 and not y["check"],
        f"ready: out first {y['firstOut'] / 1000} s and last {y['lastOut'] / 1000} s after the doors open (from their places "
        f"{y['qFirstOut'] / 1000}, {y['qLastOut'] / 1000} s), the first boarder in at {y['firstIn'] / 1000} s ({y['qFirstIn'] / 1000} s)":
            y["firstOut"] <= 2500 and y["firstOut"] < y["qFirstOut"] and y["lastOut"] < y["qLastOut"] and y["firstIn"] < y["qFirstIn"],
        f"ready, the stop 0.5 s after: those on the way alight from where they get to ({yl['outs']} of {yl['n']} out, the counts right)":
            yl["n"] == 15 and yl["outs"] == 15 and yl["ins"] == 20 and yl["aboard"] == 55 and not yl["check"],
        f"the doors closed: {d['steps0']} on the steps finish ({d['steps1']} left), {d['gone']} stay behind, nobody waits": d["steps0"] > 0 and d["steps1"] == 0 and d["waiting"] == 0 and not d["check"],
        f"the doors open again: the {d['toAlight']} left to alight get off ({d['toAlightAfter']} left), the counts right": d["toAlight"] > 0 and d["toAlightAfter"] == 0 and d["outsAfter"] == d["n"] and not d["check2"] and d["aboard"] == 60 - d["n"] + d["insAfter"],
        f"Doors I: {o['queued']} queued at the shut doors, the second car's {o['was']} handed to the first car where they stood "
        f"({o['handed']}, {o['moved']} m on), all {ol.get('0 Front in', 0)} on through its front door in {o['t']} s ({ol})":
            o["queued"][1] > 0 and o["handed"] == o["was"] and o["moved"] < 0.1 and ol.get("0 Front in", 0) == 24
            and all(k.startswith("0 Front") for k in ol if k.endswith(" in")),
        f"Doors I: the first car's {o['ofCar'][0]} alighters out through it, the second car's {o['ofCar'][1]} stay aboard ({o['stuck']}); "
        f"then all the doors: they get off ({o['after']} left), the counts right ({(o['bad'] + o['check'])[:1]})":
            min(o["ofCar"]) > 0 and o["ofCar"][0] + o["ofCar"][1] == o["n"] == 20 and ol.get("0 Front out", 0) == o["ofCar"][0]
            and o["stuck"] == o["ofCar"][1] and o["after"] == 0 and o["aboard"] == 64 and not o["bad"] and not o["check"],
        "tools/cabin.py game_cabin: one packing and what is read; off_floor finds a place over a fixture": game_cabin_keeps(),
    }
    fails += [k for k, ok in want.items() if not ok]
    for k, ok in want.items():
        print(("ok   " if ok else "FAIL ") + k)
    if fails:
        sys.exit("; ".join(fails))
    print("a set's passengers: the user's rules, the counts and places right: pass")


if __name__ == "__main__":
    main()
