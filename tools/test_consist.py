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
- the doors closed during the exchange: who is on the steps finishes the way, the queue stays behind, those still to
  alight get off when the doors open again; the counts right throughout.
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
    return (c["capacity"] == {"seats": 1, "standing": 2, "shown": 3} and c["standing"]["selected"] == "b"
            and "footprintWorld" not in c["standing"]["places"][0] and c["standing"]["places"][0]["x"] == 1.2346
            and "configurations" not in c["standing"] and "mesh" not in c["seats"][0] and c["navigation"]["runs"] == [3, 1])


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
    c, h, s, w, k, d = r["cabin"], r["half"], r["stand"], r["reseat"], r["crush"], r["closed"]
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
        f"the doors closed: {d['steps0']} on the steps finish ({d['steps1']} left), {d['gone']} stay behind, nobody waits": d["steps0"] > 0 and d["steps1"] == 0 and d["waiting"] == 0 and not d["check"],
        f"the doors open again: the {d['toAlight']} left to alight get off ({d['toAlightAfter']} left), the counts right": d["toAlight"] > 0 and d["toAlightAfter"] == 0 and d["outsAfter"] == d["n"] and not d["check2"] and d["aboard"] == 60 - d["n"] + d["insAfter"],
        "tools/cabin.py game_cabin: one packing and what is read": game_cabin_keeps(),
    }
    fails += [k for k, ok in want.items() if not ok]
    for k, ok in want.items():
        print(("ok   " if ok else "FAIL ") + k)
    if fails:
        sys.exit("; ".join(fails))
    print("a set's passengers: the user's rules, the counts and places right: pass")


if __name__ == "__main__":
    main()
