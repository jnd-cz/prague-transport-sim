// SPDX-License-Identifier: AGPL-3.0-or-later
// The overlays over the cab view (the top bar, the assist chips, the messages, the info screen's text) and the minimap;
// the driver's panel under them (src/panel.js).
import { fmtTime, fmtDev, demandAt } from './game.js';
import { t } from './i18n.js';
import { Panel } from './panel.js';

const $ = (id) => document.getElementById(id);

export class Hud {
  constructor() {
    this.panel = new Panel();
    this.mini = $('minimap').getContext('2d');
    this.lastMsgKey = '';
  }

  show(on) {
    for (const id of ['dash', 'top', 'minimap', 'help']) $(id).classList.toggle('hidden', !on);
    if (!on) this.panel.openSheet(false);
  }

  update(game, opts) {
    const tram = game.tram;
    this.panel.update(game, opts);
    const st = game.stops[game.nextStop];
    const sw = game.nextSwitch();
    const ready = st && st.served && st.waiting === 0 && st.alight === 0 && game.clock >= st.sched - 5;

    // top bar
    const ns = $('nextstop');
    if (st) {
      const d = Math.max(0, st.target - tram.s);
      ns.querySelector('.name').textContent = st.name + (st.request ? ' ✋' : '');
      const at = game.atPlatform && Math.abs(tram.v) < 0.1;
      let sub = at ? t('hud.atPlatform') : `${d > 999 ? (d / 1000).toFixed(2) + ' km' : Math.round(d) + ' m'}`;
      sub += ` · ${t('hud.dep')} ${fmtTime(st.sched).slice(0, 5)}`;
      if (st.served) sub += ` · ${st.waiting + st.alight > 0 ? t('hud.boarding', { up: st.waiting, down: st.alight }) : t('hud.boarded')}`;
      ns.querySelector('.sub').textContent = sub;
    }
    const clock = $('clock');
    clock.firstChild.textContent = fmtTime(game.clock);
    const last = [...game.log].reverse().find((l) => l.dev !== undefined);
    const devEl = clock.querySelector('.dev');
    if (st && st.arrived && !st.departClock) {
      const left = st.sched - game.clock;
      devEl.textContent = left > 0 ? t('hud.departIn', { t: fmtDev(left).slice(1) }) : t('hud.late', { t: fmtDev(-left) });
      devEl.className = `dev ${left > 0 ? '' : left > -60 ? 'ontime' : 'late'}`;
    } else if (last) {
      devEl.textContent = t('hud.lastDep', { t: fmtDev(last.dev) });
      devEl.className = `dev ${last.dev < -5 ? 'early' : last.dev <= 60 ? 'ontime' : 'late'}`;
    } else devEl.innerHTML = '&nbsp;';
    $('score').firstChild.textContent = Math.round(game.score);
    $('score').querySelector('.sub').textContent = t('hud.points');
    // passengers on board: bar to crush load, tick at the normal capacity
    const pax = tram.passengers, paxEl = $('pax');
    paxEl.querySelector('.n').textContent = `${pax} / ${tram.capacity}`;
    const bar = paxEl.querySelector('.bar i');
    bar.style.width = `${Math.min(100, (pax / tram.crushCapacity) * 100)}%`;
    bar.style.background = pax > tram.capacity ? 'var(--red)' : pax > tram.capacity * 0.75 ? 'var(--amber)' : 'var(--green)';
    paxEl.className = pax > tram.capacity ? 'full' : pax > tram.capacity * 0.75 ? 'busy' : '';
    const peak = demandAt(game.clock) >= 1.7;
    paxEl.querySelector('.sub').textContent = pax > tram.capacity ? t('hud.crowded') : t('hud.pax') + (peak ? ` · ${t('hud.peak')}` : '');

    // info screen
    const lim = game.currentLimit;
    const nl = game.nextLimitChange();
    const K = (k) => `<span class="k">${t(k)}</span>`;
    $('info').innerHTML = [
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
    ].join('<br>');

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
    $('assist').innerHTML = chips.join('');

    // messages
    const key = game.messages.map((m) => m.text).join('|');
    if (key !== this.lastMsgKey) {
      this.lastMsgKey = key;
      $('msgs').innerHTML = game.messages.map((m) => `<div class="${m.kind}">${m.text}</div>`).join('');
    }
    const act = $('action');
    if (game.action) {
      act.style.display = 'block';
      act.textContent = `${game.action.label} ${Math.ceil(game.action.t)} s`;
    } else if (game.paused) {
      act.style.display = 'block';
      act.textContent = t('hud.paused');
    } else act.style.display = 'none';

    this.drawMinimap(game);
  }

  drawMinimap(game) {
    const g = this.mini, W = 440, R = 700; // metres shown from centre to edge
    const tram = game.tram, route = game.route;
    const c = route.at(tram.s);
    const k = W / 2 / R;
    const tx = (x) => W / 2 + (x - c.x) * k, ty = (y) => W / 2 - (y - c.y) * k;
    g.clearRect(0, 0, W, W);
    g.lineCap = g.lineJoin = 'round';
    g.strokeStyle = '#46524a';
    g.lineWidth = 3;
    for (const t of game.data.tracks) {
      g.beginPath();
      t.p.forEach((p, i) => (i ? g.lineTo(tx(p[0]), ty(p[1])) : g.moveTo(tx(p[0]), ty(p[1]))));
      g.stroke();
    }
    g.strokeStyle = '#a3241d';
    g.lineWidth = 6;
    g.beginPath();
    route.coarse.forEach((p, i) => (i ? g.lineTo(tx(p[0]), ty(p[1])) : g.moveTo(tx(p[0]), ty(p[1]))));
    g.stroke();
    for (const sig of game.signals) {
      const p = route.at(sig.s);
      g.fillStyle = sig.state === 'go' ? '#6fe07a' : sig.state === 'warn' ? '#ffb43a' : '#ff4b3e';
      g.fillRect(tx(p.x) - 5, ty(p.y) - 5, 10, 10);
    }
    for (const sw of game.switches) {
      const p = route.at(sw.s);
      g.strokeStyle = sw.pos === sw.required ? '#6fe07a' : '#ffb43a';
      g.lineWidth = 3;
      g.beginPath();
      g.arc(tx(p.x), ty(p.y), 7, 0, Math.PI * 2);
      g.stroke();
    }
    g.font = '600 20px system-ui';
    for (const st of game.stops) {
      const p = route.at(st.target);
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
