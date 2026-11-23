// SPDX-License-Identifier: AGPL-3.0-or-later
// The overlays over the cab view (the top bar, the assist chips, the messages, the info screen's text) and the minimap;
// the driver's panel under them (src/panel.js).
import { fmtTime, fmtDev, demandAt } from './game.js';
import { t } from './i18n.js';
import { Panel } from './panel.js';
import { rectOf } from './boxes.js';

const $ = (id) => document.getElementById(id);

// A write into the page only when the value changed (#706): the HUD updates 30 times a second and most of its texts
// stand for seconds; an innerHTML or a textContent set to what it holds already still replaces the nodes, and the
// page lays them out again. The last value written, by node and property (nothing else writes these nodes).
const written = new WeakMap();
const STYLE = new Set(['width', 'background', 'display']);
function put(node, prop, v) {
  let w = written.get(node);
  if (!w) written.set(node, w = {});
  if (w[prop] === v) return;
  w[prop] = v;
  if (STYLE.has(prop)) node.style[prop] = v; else node[prop] = v;
}

// The minimap: 440 px for 700 m from the centre to an edge. The line's tracks and our route are drawn to a canvas of
// their own, twice the minimap's side, round where the tram was; an update copies its part. It is drawn again once
// the tram has gone LAYER_REACH from its centre (line 17: 356 tracks of 23,213 points were stroked 30 times a second).
const MAP_W = 440, MAP_R = 700, LAYER_W = 2 * MAP_W, LAYER_REACH = 0.9 * MAP_R;

export class Hud {
  constructor() {
    this.panel = new Panel();
    this.mini = $('minimap').getContext('2d');
    this.lastMsgKey = '';
    const ns = $('nextstop'), clock = $('clock'), score = $('score'), pax = $('pax');
    this.el = {
      nsName: ns.querySelector('.name'), nsSub: ns.querySelector('.sub'), clockText: clock.firstChild, dev: clock.querySelector('.dev'),
      scoreText: score.firstChild, scoreSub: score.querySelector('.sub'), pax, paxN: pax.querySelector('.n'), paxBar: pax.querySelector('.bar i'),
      paxSub: pax.querySelector('.sub'), info: $('info'), assist: $('assist'), msgs: $('msgs'), action: $('action'),
    };
    this.layer = null; // the minimap's tracks: { canvas, data, route, cx, cy }
    this.boxes = new WeakMap(); // a line's tracks -> their boxes (x0, y0, x1, y1 each)
    this.places = new WeakMap(); // a signal, a switch or a stop -> where it stands, { x, y }
  }

  show(on) {
    for (const id of ['dash', 'top', 'minimap', 'help']) $(id).classList.toggle('hidden', !on);
    if (!on) this.panel.openSheet(false);
  }

  update(game, opts) {
    const tram = game.tram, e = this.el;
    this.panel.update(game, opts);
    const st = game.stops[game.nextStop];
    const sw = game.nextSwitch();
    const ready = st && st.served && st.waiting === 0 && st.alight === 0 && game.clock >= st.sched - 5;

    // top bar
    if (st) {
      const d = Math.max(0, st.target - tram.s);
      put(e.nsName, 'textContent', st.name + (st.request ? ' ✋' : ''));
      const at = game.atPlatform && Math.abs(tram.v) < 0.1;
      let sub = at ? t('hud.atPlatform') : `${d > 999 ? (d / 1000).toFixed(2) + ' km' : Math.round(d) + ' m'}`;
      sub += ` · ${t('hud.dep')} ${fmtTime(st.sched).slice(0, 5)}`;
      if (st.served) sub += ` · ${st.waiting + st.alight > 0 ? t('hud.boarding', { up: st.waiting, down: st.alight }) : t('hud.boarded')}`;
      put(e.nsSub, 'textContent', sub);
    }
    put(e.clockText, 'textContent', fmtTime(game.clock));
    const last = [...game.log].reverse().find((l) => l.dev !== undefined);
    if (st && st.arrived && !st.departClock) {
      const left = st.sched - game.clock;
      put(e.dev, 'textContent', left > 0 ? t('hud.departIn', { t: fmtDev(left).slice(1) }) : t('hud.late', { t: fmtDev(-left) }));
      put(e.dev, 'className', `dev ${left > 0 ? '' : left > -60 ? 'ontime' : 'late'}`);
    } else if (last) {
      put(e.dev, 'textContent', t('hud.lastDep', { t: fmtDev(last.dev) }));
      put(e.dev, 'className', `dev ${last.dev < -5 ? 'early' : last.dev <= 60 ? 'ontime' : 'late'}`);
    } else put(e.dev, 'textContent', ' ');
    put(e.scoreText, 'textContent', String(Math.round(game.score)));
    put(e.scoreSub, 'textContent', t('hud.points'));
    // passengers on board: bar to crush load, tick at the normal capacity
    const pax = tram.passengers;
    put(e.paxN, 'textContent', `${pax} / ${tram.capacity}`);
    put(e.paxBar, 'width', `${Math.min(100, (pax / tram.crushCapacity) * 100)}%`);
    put(e.paxBar, 'background', pax > tram.capacity ? 'var(--red)' : pax > tram.capacity * 0.75 ? 'var(--amber)' : 'var(--green)');
    put(e.pax, 'className', pax > tram.capacity ? 'full' : pax > tram.capacity * 0.75 ? 'busy' : '');
    const peak = demandAt(game.clock) >= 1.7;
    put(e.paxSub, 'textContent', pax > tram.capacity ? t('hud.crowded') : t('hud.pax') + (peak ? ` · ${t('hud.peak')}` : ''));

    // info screen
    const lim = game.currentLimit;
    const nl = game.nextLimitChange();
    const K = (k) => `<span class="k">${t(k)}</span>`;
    put(e.info, 'innerHTML', [
      `${K('info.line')} <span class="big">${game.line}</span> <span class="k">→</span> ${game.stops[game.stops.length - 1].name}`,
      `${K('info.pax')} <span class="big">${tram.passengers}</span>/${tram.capacity}`,
      `${K('info.climate')} ${t('info.temps', { o: Math.round(game.climate.tout), i: Math.round(game.climate.tin), c: Math.round(game.climate.tcab) })}`,
      `${K('info.heating')} ${t('info.heatState', { s: game.climate.saloon, c: game.climate.cab, f: t(game.climate.flap ? 'flap.open' : 'flap.closed') })}`,
      `${K('info.doors')} ${t(`doors.${game.doorState}`)}`,
      `${K('info.speed')} max ${lim} km/h${nl ? ` · ${t('info.limitAhead', { v: nl.v, d: Math.round(nl.d) })}` : ''}`,
      `${K('info.power')} ${Math.round(tram.voltage)} V${tram.supply.ref ? ` (${tram.supply.ref} ${tram.supply.km.toFixed(1)} km)` : ''} · ${tram.eq.aux.U.toFixed(1)} V · ${Math.round(tram.eq.mg.rpm)} ${t('info.rpm')}`,
      `${K('info.accel')} ${tram.a.toFixed(2)} · ${t('info.lateral')} ${(game.latAcc || 0).toFixed(1)} m/s²`,
      `${K('info.grade')} ${(tram.grade * 1000 >= 0 ? '+' : '') + Math.round(tram.grade * 1000)} ‰ · ${Math.round(game.profile.height(tram.s))} ${t('info.altitude')}`,
      `${K('info.adhesion')} ${t(`adh.${game.weather}`)} μ ${tram.mu.toFixed(2)} · ${K('info.sand')} ${Math.round(tram.sand * 100)} %`,
      `${K('info.switch')} ${sw && sw.s - tram.s < 300 ? `${Math.round(sw.s - tram.s)} m · ${t(`dirShort.${sw.pos === 'straight' ? 'straight' : sw.divSide}`)}` : '—'}`,
    ].join('<br>'));

    // assist chips
    const chips = [];
    if (game.autopilot) chips.push(`<div class="chip ok">${t('chip.autopilot')}</div>`);
    if (opts.assist) {
      if (sw && sw.s - tram.s < 260) {
        const need = sw.required === 'straight' ? 'straight' : sw.divSide;
        const cur = sw.pos === 'straight' ? 'straight' : sw.divSide;
        const ok = need === cur;
        const auto = sw.auto ? t(game.opts.autoIrc ? 'chip.ircAuto' : 'chip.ircKeys') : '';
        const fix = sw.auto || !sw.passedContact ? '' : t('chip.crowbar');
        chips.push(`<div class="chip ${ok ? 'ok' : 'bad'}">${t('chip.switch', { d: Math.round(sw.s - tram.s), need: t(`dir.${need}`), cur: t(`dir.${cur}`) })}${auto}${ok ? '' : fix}</div>`);
      }
      const ct = game.nextContact();
      if (ct && ct.contact - tram.panto < 120) {
        const how = t(ct.required !== 'straight' ? 'chip.power' : game.heatingDraws() ? 'chip.coastCut' : 'chip.coast');
        const ok = game.contactCurrent() === (ct.required !== 'straight');
        chips.push(`<div class="chip ${ok ? 'ok' : 'bad'}">${t('chip.contactNext', { d: Math.max(0, Math.round(ct.contact - tram.panto)), how })}</div>`);
      }
      const sig = game.signals.find((g) => g.s > tram.s - 1);
      if (sig && sig.s - tram.s < 220) {
        const d = Math.round(sig.s - tram.s);
        const text = sig.gauntlet
          ? t('chip.gauntlet', { d, state: t(sig.state === 'go' ? 'gaunt.go' : 'gaunt.wait') })
          : t('chip.signal', { d, state: t(`sig.${sig.state}`) });
        chips.push(`<div class="chip ${sig.state === 'go' ? 'ok' : 'bad'}">${text}</div>`);
      }
      if (nl && nl.d < 150) chips.push(`<div class="chip">${t('chip.limit', { v: nl.v, d: Math.round(nl.d) })}</div>`);
      const gap = game.tramAheadGap();
      if (gap !== null && gap < 150) chips.push(`<div class="chip ${gap < 25 ? 'bad' : ''}">${t('chip.tramAhead', { d: Math.max(0, Math.round(gap)) })}</div>`);
      if (st && st.request && st.target - tram.s < 300 && st.target - tram.s > 0) {
        const need = st.waiting > 0 || st.alightFrac > 0;
        chips.push(`<div class="chip ${need ? 'bad' : 'ok'}">${t(need ? 'chip.requestNeed' : 'chip.requestNone')}</div>`);
      }
      if (ready && game.doorState === 'open') chips.push(`<div class="chip ok">${t('chip.allAboard')}</div>`);
      if (st && !st.served && game.atPlatform && Math.abs(tram.v) < 0.1 && game.doorState === 'closed') chips.push(`<div class="chip ok">${t('chip.atPlatform')}</div>`);
      if (Math.abs(tram.grade) > 0.035) chips.push(`<div class="chip">${t(tram.grade > 0 ? 'chip.uphill' : 'chip.downhill', { g: Math.abs(Math.round(tram.grade * 1000)) })}</div>`);
    }
    put(e.assist, 'innerHTML', chips.join(''));

    // messages
    const key = game.messages.map((m) => m.text).join('|');
    if (key !== this.lastMsgKey) {
      this.lastMsgKey = key;
      e.msgs.innerHTML = game.messages.map((m) => `<div class="${m.kind}">${m.text}</div>`).join('');
    }
    if (game.action) {
      put(e.action, 'display', 'block');
      put(e.action, 'textContent', `${game.action.label} ${Math.ceil(game.action.t)} s`);
    } else if (game.paused) {
      put(e.action, 'display', 'block');
      put(e.action, 'textContent', t('hud.paused'));
    } else put(e.action, 'display', 'none');

    this.drawMinimap(game);
  }

  // the line's tracks and our route round (cx, cy), for the minimap to copy from
  tracksLayer(game, cx, cy) {
    const L = this.layer ??= { canvas: Object.assign(document.createElement('canvas'), { width: LAYER_W, height: LAYER_W }) };
    Object.assign(L, { data: game.data, route: game.route, cx, cy });
    const g = L.canvas.getContext('2d'), k = MAP_W / 2 / MAP_R, reach = LAYER_W / 2 / k;
    const tx = (x) => LAYER_W / 2 + (x - cx) * k, ty = (y) => LAYER_W / 2 - (y - cy) * k;
    let boxes = this.boxes.get(game.data.tracks);
    if (!boxes) {
      boxes = new Float32Array(4 * game.data.tracks.length);
      game.data.tracks.forEach((tr, i) => {
        let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
        for (const p of tr.p) { if (p[0] < x0) x0 = p[0]; if (p[0] > x1) x1 = p[0]; if (p[1] < y0) y0 = p[1]; if (p[1] > y1) y1 = p[1]; }
        boxes.set([x0, y0, x1, y1], 4 * i);
      });
      this.boxes.set(game.data.tracks, boxes);
    }
    g.clearRect(0, 0, LAYER_W, LAYER_W);
    g.lineCap = g.lineJoin = 'round';
    g.strokeStyle = '#46524a';
    g.lineWidth = 3;
    game.data.tracks.forEach((tr, i) => {
      if (boxes[4 * i] > cx + reach || boxes[4 * i + 2] < cx - reach || boxes[4 * i + 1] > cy + reach || boxes[4 * i + 3] < cy - reach) return;
      g.beginPath();
      tr.p.forEach((p, j) => (j ? g.lineTo(tx(p[0]), ty(p[1])) : g.moveTo(tx(p[0]), ty(p[1]))));
      g.stroke();
    });
    g.strokeStyle = '#a3241d';
    g.lineWidth = 6;
    g.beginPath();
    game.route.coarse.forEach((p, i) => (i ? g.lineTo(tx(p[0]), ty(p[1])) : g.moveTo(tx(p[0]), ty(p[1]))));
    g.stroke();
    return L;
  }

  // where a signal, a switch or a stop stands (it does not move: found once)
  place(route, o, s) {
    let p = this.places.get(o);
    if (!p) { const q = route.at(s); this.places.set(o, p = { x: q.x, y: q.y }); }
    return p;
  }

  drawMinimap(game) {
    if (!rectOf(this.mini.canvas).width) return; // (not shown: a small touch screen's layout has none, index.html)
    const g = this.mini, W = MAP_W, R = MAP_R; // metres shown from centre to edge
    const tram = game.tram, route = game.route;
    const c = route.at(tram.s);
    const k = W / 2 / R;
    const tx = (x) => W / 2 + (x - c.x) * k, ty = (y) => W / 2 - (y - c.y) * k;
    const seen = (x, y, m) => x > -m && x < W + m && y > -m && y < W + m;
    let L = this.layer;
    if (!L || L.data !== game.data || L.route !== route || Math.abs(c.x - L.cx) > LAYER_REACH || Math.abs(c.y - L.cy) > LAYER_REACH) L = this.tracksLayer(game, c.x, c.y);
    g.clearRect(0, 0, W, W);
    // (whole pixels: a copy between pixels would blur the tracks)
    g.drawImage(L.canvas, Math.round(LAYER_W / 2 + (c.x - L.cx) * k - W / 2), Math.round(LAYER_W / 2 - (c.y - L.cy) * k - W / 2), W, W, 0, 0, W, W);
    g.lineCap = g.lineJoin = 'round';
    for (const sig of game.signals) {
      const p = this.place(route, sig, sig.s), x = tx(p.x), y = ty(p.y);
      if (!seen(x, y, 5)) continue;
      g.fillStyle = sig.state === 'go' ? '#6fe07a' : sig.state === 'warn' ? '#ffb43a' : '#ff4b3e';
      g.fillRect(x - 5, y - 5, 10, 10);
    }
    for (const sw of game.switches) {
      const p = this.place(route, sw, sw.s), x = tx(p.x), y = ty(p.y);
      if (!seen(x, y, 10)) continue;
      g.strokeStyle = sw.pos === sw.required ? '#6fe07a' : '#ffb43a';
      g.lineWidth = 3;
      g.beginPath();
      g.arc(x, y, 7, 0, Math.PI * 2);
      g.stroke();
    }
    g.font = '600 20px system-ui';
    for (const st of game.stops) {
      const p = this.place(route, st, st.target);
      const x = tx(p.x), y = ty(p.y);
      if (x < -50 || x > W + 50 || y < -50 || y > W + 50) continue;
      g.fillStyle = st.i === game.nextStop ? '#ffd24a' : '#fff';
      g.beginPath();
      g.arc(x, y, 7, 0, Math.PI * 2);
      g.fill();
      g.fillStyle = 'rgba(255,255,255,.85)';
      g.fillText(st.name, x + 10, y - 8);
    }
    // tram
    const h = route.heading(tram.s);
    g.save();
    g.translate(W / 2, W / 2);
    g.rotate(Math.atan2(h.hx, h.hy));
    g.fillStyle = '#5fb4ff';
    g.beginPath();
    g.moveTo(0, -14); g.lineTo(9, 10); g.lineTo(-9, 10); g.closePath();
    g.fill();
    g.restore();
  }
}
