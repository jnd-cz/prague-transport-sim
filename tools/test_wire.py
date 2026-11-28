# SPDX-License-Identifier: AGPL-3.0-or-later
"""Browser tests of the contact wire's height under structures (src/wire.js, #71): python -P -E tools/test_wire.py
(serves the checkout itself on a free port)."""
import functools
import http.server
import os
import sys
import threading

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves tools/ out)
import gpu  # noqa: E402  (Chromium on the GPU where it has one, #463)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=ROOT))
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    with sync_playwright() as p:
        browser = gpu.launch(p)[0]
        page = browser.new_page()
        page.goto(f'http://127.0.0.1:{server.server_port}/README.md')
        print(page.evaluate('''async () => {
          const {Ceilings, makeWire, headroomAt, COLLECTOR, WIRE_UNDER, WIRE_MIN, WIRE_GRADE, WIRE_FROM, CLEARANCE, CLEAR_MARGIN, SLAB_LEFT, LIFT_REACH} = await import('/src/wire.js');
          const check = (ok, msg) => { if (!ok) throw Error(msg); };
          const near = (a, b, e = 1e-6) => Math.abs(a - b) <= e;
          const N = 5.34;
          // a straight track along x at rail height 200, a vertex every 1.5 m
          const track = (y, z, x0 = -600, x1 = 600) => { const smooth = [], zs = []; for (let x = x0; x <= x1; x += 1.5) { smooth.push([x, y]); zs.push(z); } return {smooth, z: zs}; };
          // a slab across the track at x = 0..4, its underside `under` m over the rails
          const slab = (C, under, y0 = -5, y1 = 5, z = 200) => { for (let x = 0; x <= 4; x += 0.4) for (let y = y0; y <= y1; y += 0.4) C.add(x, y, z + under); };

          // 1. the lookup: the lowest point within the collector's reach in plan, in the height band asked for
          let C = new Ceilings();
          C.add(0, 0.9, 204.5); C.add(0, 1.2, 204.0); C.add(0, 0, 203.0); C.add(0, 0, 206.0);
          check(C.lowest(0, 0, 200 + WIRE_FROM, 200 + N + WIRE_UNDER) === 204.5, 'a point 1.2 m aside and one under the band are not over the collector');
          check(C.lowest(0, 0, 200 + WIRE_FROM, 200 + N + WIRE_UNDER, 1.3) === 204.0, 'a wider reach finds the point 1.2 m aside');
          check(C.lowest(50, 0, 0, 999) === null, 'nothing over a place 50 m on');
          C.add(0, 0.9, 204.5);
          check(C.count === 4, 'a point is kept once');

          // 2. nothing over the tracks: the normal height everywhere
          let W = makeWire([track(0, 200)], new Ceilings(), N);
          check(W.over(0, 0, 200) === N && W.low.length === 0 && W.drops.length === 0, 'no structure, the normal height');

          // 3. a bridge 4.32 m over the rails: the wire WIRE_UNDER m under it, back at 1 in 250 either way
          C = new Ceilings(); slab(C, 4.32);
          W = makeWire([track(0, 200)], C, N);
          check(near(W.over(1.5, 0, 200), 4.32 - WIRE_UNDER), 'under the bridge the wire is WIRE_UNDER m under it');
          // (the track is read every 0.5 m: its low points run from x = -0.5 to 4.5)
          check(near(W.over(104.5, 0, 200), 4.32 - WIRE_UNDER + 100 * WIRE_GRADE, 0.001) && near(W.over(-96.5, 0, 200), 4.32 - WIRE_UNDER + 96 * WIRE_GRADE, 0.001), '100 m past the bridge it has risen 0.4 m, both ways');
          check(W.over(400, 0, 200) === N, 'back at the normal height 400 m on');
          check(W.drops.length === 1 && W.drops[0].under === 4.32 && W.drops[0].wire === 4.17 && W.drops[0].reach === 293 && W.impossible.length === 0, 'the place is listed with its heights and its reach: ' + JSON.stringify(W.drops));

          // 4. the wire beside it comes down too; a track on another level does not
          W = makeWire([track(0, 200), track(3.5, 200), track(20, 208)], C, N);
          check(W.over(1.5, 3.5, 200) < 4.2, 'the opposite track under the same bridge');
          check(near(W.over(1.5, 30, 200), 4.32 - WIRE_UNDER + 26.5 * WIRE_GRADE, 0.001), 'a wire 26.5 m from the nearer track on the same level is 0.11 m higher');
          check(W.over(1.5, 20, 208) === N, 'a track 8 m higher, on the bridge, keeps the normal height');

          // 5. a structure just over the normal wire lowers nothing
          C = new Ceilings(); slab(C, 5.5);
          W = makeWire([track(0, 200)], C, N);
          check(W.over(1.5, 0, 200) === N && W.drops.length === 0, 'a bridge 5.5 m over the rails: the wire passes under it as it is');

          // 6. lower than a collector reaches: no evidence, the wire stays and the place is listed
          C = new Ceilings(); slab(C, 3.83);
          W = makeWire([track(0, 200)], C, N);
          check(W.over(1.5, 0, 200) === N && W.drops.length === 0 && W.impossible.length === 1 && W.impossible[0].under === 3.83, 'a structure 3.83 m over the rails: ' + JSON.stringify(W.impossible));
          check(WIRE_MIN + WIRE_UNDER > 3.83 && COLLECTOR === 1, 'the figures the cases stand on');

          // 7. a street that comes down to the bridge at 6 %: before the bridge the wire is no higher than under it
          const sloped = (() => { const smooth = [], zs = []; for (let x = -60; x <= 60; x += 1.5) { smooth.push([x, 0]); zs.push(200 - 0.06 * x); } return {smooth, z: zs}; })();
          C = new Ceilings(); for (let x = 0; x <= 4; x += 0.4) for (let y = -5; y <= 5; y += 0.4) C.add(x, y, 204.5);
          W = makeWire([sloped], C, N);
          const at = (x) => 200 - 0.06 * x + W.over(x, 0, 200 - 0.06 * x);
          check(at(0) <= 204.5 - WIRE_UNDER + 1e-6 && at(2) <= 204.5 - WIRE_UNDER + 1e-6, 'under the bridge, under it');
          check(at(-1.5) <= 204.5 - WIRE_UNDER + 0.01 && at(-3) <= 204.5 - WIRE_UNDER + 0.02, 'a vertex 1.5 and 3 m before the bridge, the rails 9 and 18 cm higher: the wire stays under the bridge: ' + at(-1.5).toFixed(3) + ' ' + at(-3).toFixed(3));
          check(W.over(-40, 0, 202.4) > W.over(-3, 0, 200.18), 'and rises over the rails farther up the street');

          // 8. the clearance posted near a place: the highest of the ways within reach, 0 for none
          const posted = headroomAt([{p: [[-50, 5], [50, 5]], mh: 4.3}, {p: [[-50, 40], [50, 40]], mh: 3.1}, {p: [[0, 0]], mh: 9}]);
          check(posted(0, 0) === 4.3 && posted(60, 0) === 4.3 && posted(0, 30) === 3.1 && posted(0, -20) === 0 && posted(70, 0) === 0, 'a way 5 m aside, past its end, the other way, none near');
          check(headroomAt([{p: [[-50, 5], [50, 5]], mh: 3.2}, {p: [[-50, -5], [50, -5]], mh: 4.3}, {p: [[-50, 0], [50, 0]], mh: 4.0}])(0, 0) === 4.3, 'three ways within reach: the highest');
          check(headroomAt(undefined)(0, 0) === 0 && CLEARANCE === 4.2 && CLEAR_MARGIN === 0.1 && SLAB_LEFT === 0.3, 'a line with no list: none; the figures the cases stand on');

          // 9. a model too low for the clearance: its underside lifted to the clearance and the margin, the slab kept
          // (a deck across the track at x = 0..4: its underside and its top over the rails at 200)
          const deck = (under, top) => { const D = new Ceilings(); for (let x = 0; x <= 4; x += 0.4) for (let y = -5; y <= 5; y += 0.4) { D.add(x, y, 200 + under, 200); D.add(x, y, 200 + top, 200); } return D; };
          C = deck(4.14, 4.7);
          let lifted = C.lift(posted);
          check(lifted.length > 0 && lifted.every((p) => near(p.z, 204.4) && near(p.from, 204.14) && p.mh === 4.3), 'under 4.14, top 4.7, posted 4.3: to 4.4 m, 0.3 m of slab left');
          check(near(C.lowest(1.5, 0, 203.6, 205.49), 204.4) && near(C.highest(1.5, 0, 0.45), 204.7), 'the lookup has the lifted underside; the top stays');
          W = makeWire([track(0, 200)], C, N);
          check(near(W.over(1.5, 0, 200), 4.4 - WIRE_UNDER) && W.drops.length === 1 && W.drops[0].under === 4.4, 'the wire passes under the lifted underside: ' + JSON.stringify(W.drops));
          check(W.lifts.length === 1 && W.lifts[0].from === 4.14 && W.lifts[0].to === 4.4 && W.lifts[0].mh === 4.3, 'the place is listed: ' + JSON.stringify(W.lifts));
          let at9 = W.liftAt(2, 8);
          check(at9 && near(at9.to, 204.3 + CLEAR_MARGIN + WIRE_UNDER) && at9.zr === 200 && W.liftAt(2, 5 + LIFT_REACH + 0.5) === null && W.liftAt(300, 0) === null, 'the lifted point near a corner 3 m aside of the deck; none past the reach');
          // (one clearance for the structure: a tagged way that ends 10 m before its face holds for its far side, 14 m on)
          C = deck(4.14, 4.7); lifted = C.lift(headroomAt([{p: [[-60, 0], [-10, 0]], mh: 4.3}]));
          check(lifted.length > 0 && lifted.every((p) => p.mh === 4.3 && near(p.z, 204.4)) && lifted.some((p) => p.x > 3.9), 'the way ends before the bridge: 4.3 m for all of it');
          // (two bridges 30 m apart, the sign near the first alone: the second takes the legal height)
          C = deck(4.14, 4.7); for (let x = 30; x <= 34; x += 0.4) for (let y = -5; y <= 5; y += 0.4) { C.add(x, y, 204.14, 200); C.add(x, y, 204.7, 200); }
          lifted = C.lift(headroomAt([{p: [[-60, 0], [-10, 0]], mh: 4.3}]));
          check(lifted.filter((p) => p.x < 5).every((p) => p.mh === 4.3) && lifted.filter((p) => p.x > 29).every((p) => p.mh === CLEARANCE) && lifted.some((p) => p.x > 29), 'the bridge 30 m on: the legal height');
          // (a deep model: the clearance decides, the wire WIRE_UNDER under it and CLEAR_MARGIN over the sign's height)
          C = deck(4.14, 5.2); C.lift(posted);
          W = makeWire([track(0, 200)], C, N);
          check(near(C.lowest(1.5, 0, 203.6, 205.49), 204.3 + CLEAR_MARGIN + WIRE_UNDER) && near(W.over(1.5, 0, 200), 4.3 + CLEAR_MARGIN), 'posted 4.3, top 5.2: to 4.55 m, the wire 4.4 m');
          // (nothing posted: the legal height)
          C = deck(4.14, 5.2); C.lift(headroomAt([]));
          check(near(C.lowest(1.5, 0, 203.6, 205.49), 204.45), 'nothing posted: to 4.45 m');
          // (a thin model: the slab left decides)
          C = deck(4.14, 4.5); C.lift(posted);
          check(near(C.lowest(1.5, 0, 203.6, 205.49), 204.2), 'top 4.5: to 4.2 m only');
          // (high enough: untouched, and a low sign lowers nothing)
          C = deck(4.6, 5.2);
          check(C.lift(posted).length === 0 && near(C.lowest(1.5, 0, 203.6, 205.49), 204.6), 'under 4.6: as it is');
          C = deck(4.32, 5.2);
          check(C.lift(headroomAt([{p: [[-50, 0], [50, 0]], mh: 3.1}])).length === 0, 'a sign of 3.1 m under a model 4.32 m up: as it is');
          // (a point with no rail given is left)
          C = new Ceilings(); slab(C, 4.14); slab(C, 4.7);
          check(C.lift(posted).length === 0, 'points without their rail are not lifted');

          // 10. a model lower than a collector reaches, lifted: the wire comes down under it; too thin to lift, it stays listed
          C = deck(3.65, 4.6); C.lift(headroomAt([]));
          W = makeWire([track(0, 200)], C, N);
          check(W.impossible.length === 0 && W.drops.length === 1 && near(W.over(1.5, 0, 200), 4.3 - WIRE_UNDER), 'under 3.65, top 4.6: lifted to 4.3 m, the wire 4.15 m');
          C = deck(3.65, 4.2); C.lift(headroomAt([]));
          W = makeWire([track(0, 200)], C, N);
          check(W.impossible.length === 1 && W.impossible[0].under === 3.9 && W.over(1.5, 0, 200) === N, 'top 4.2: lifted to 3.9 m, still lower than a collector reaches: ' + JSON.stringify(W.impossible));
          // (a sign lower than a collector reaches: the lowest wire and its gap are asked for)
          C = deck(3.8, 5.0); C.lift(headroomAt([{p: [[-50, 0], [50, 0]], mh: 3.1}]));
          W = makeWire([track(0, 200)], C, N);
          check(near(C.lowest(1.5, 0, 203.6, 205.49), 200 + WIRE_MIN + WIRE_UNDER) && W.impossible.length === 0 && near(W.over(1.5, 0, 200), WIRE_MIN), 'a sign of 3.1 m, the model 3.8 m up: lifted to 4.05 m, the wire at its lowest');
          return '10 wire cases pass';
        }'''))
        browser.close()
finally:
    server.shutdown()
