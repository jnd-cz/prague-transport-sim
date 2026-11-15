// SPDX-License-Identifier: AGPL-3.0-or-later
// Run by tools/test_sounds.py: real TR37 transitions, recorded before the audio frame (#590).
import { TR37, TR37_SPEC } from '../../src/tr37.js';
import { TramAudio, lineContactorReleaseLevel } from '../../src/audio.js';
import { soundProblems } from '../../src/vehicles.js';

export async function contactors() {
  const failures = [], need = (ok, why) => { if (!ok) failures.push(why); }, dt = 0.01;
  const fresh = () => { const e = new TR37(); e.mode = 'advanced'; e.park(false); return e; };
  const step = (e, n, ctx = {}) => { let out; for (let i = 0; i < n; i++) out = e.update(dt, { v: 8, ...ctx }); return out; };
  const prepare = () => { const e = fresh(); step(e, 100); e.pressTo(5); step(e, 500); return e; };
  const a = new TramAudio(); a.start(); a.setMuted(true); a.setActive(true);
  const e = fresh(), tram = { eq: e, v: 8, s: 0, current: 0, force: 0, cars: 1 };
  a.watchEquipment(e); a.trace = [];
  const flush = () => a.update(tram, 100, dt);
  flush(); need(a.trace.length === 0, 'initialization played a contactor');
  step(e, 100);
  for (let i = 0; i < 3; i++) {
    e.pressTo(5); step(e, 300);
    e.pressTo(3); step(e, 100); // positive-step change must not switch LS
    e.pressTo(0); step(e, 80);
  }
  need(a.contactorEvents.length === 6, `three applications queued ${a.contactorEvents.length} edges`);
  const captured = a.contactorEvents.map(x => ({ ...x }));
  tram.current = -300; flush(); flush();
  const edges = a.trace.filter(x => x.e.startsWith('lineContactor.'));
  need(edges.map(x => x.e).join() === Array(3).fill(['lineContactor.close','lineContactor.open']).flat().join(), 'missing, duplicate or unordered edges');
  need(edges.filter(x => x.e.endsWith('.open')).every(x => x.current > 0), 'opening read post-opening/brake current');

  const release = slow => {
    const q = prepare(), log = []; q.onLineContactor = x => log.push(x);
    if (slow) { q.pressTo(1); step(q, 500); }
    q.pressTo(0); step(q, 50);
    need(log.length === 1 && !log[0].closed, 'release must open once');
    return log[0]?.current;
  };
  const abrupt = release(false), gradual = release(true);
  need(abrupt > gradual && gradual > 0, `release currents abrupt ${abrupt}, gradual ${gradual}`);
  const q = prepare(), log = []; q.onLineContactor = x => log.push(x);
  q.pressTo(0); step(q, 10); q.pressTo(5); step(q, 100);
  need(log.length === 0 && q.ls && q.relT === -1, 'cancelled release replayed a start or release');
  q.pressTo(0); step(q, 50); need(log.length === 1 && !q.ls, 'opening after cancellation');
  const protection = [];
  for (const ctx of [{doorsOpen:true}, {rescue:true}, {forcedStop:true}, {mr:true}, {brake:true}, {mg:true}]) {
    const q = prepare(), before = q.tractionCurrent, log = []; q.onLineContactor = x => log.push(x);
    if (ctx.mr) q.mr = true;
    if (ctx.brake) q.pressTo(-3);
    if (ctx.mg) q.mg.i = 0;
    step(q, 1, ctx);
    need(log.length === 1 && !log[0].closed && log[0].current === before, `interlock ${JSON.stringify(ctx)} capture`);
    protection.push(log[0]);
  }
  const over = prepare(), overLog = []; over.onLineContactor = x => overLog.push(x); over.p = 99;
  const overOut = step(over, 1, {v:0,voltage:1000});
  need(over.mr && overLog.length === 1 && overLog[0].current === overOut.current && overOut.current > TR37_SPEC.maxRelay, 'maximum-relay trip current');
  const instant = fresh(), instantLog = []; step(instant, 100); instant.p = 99;
  instant.onLineContactor = x => instantLog.push(x); instant.pressTo(5); step(instant, 1, {v:0,voltage:2000});
  need(instantLog.length === 2 && instantLog[0].closed && !instantLog[1].closed, 'same-substep close/open lost');

  const levels = [-200,0,100,240,480,900].map(i => lineContactorReleaseLevel(i));
  need(levels[0] === .25 && levels[1] === .25 && levels[4] === 1 && levels[5] === 1 && levels[2] < levels[3], 'gain bounds/order');
  need(lineContactorReleaseLevel(100,{minGain:.1,maxGain:.7,refCurrent:200}) === .4, 'configured gain curve');
  for (const curve of [{minGain:0},{maxGain:2},{minGain:.8,maxGain:.2},{refCurrent:0},{refCurrent:Infinity},false,[]])
    need(soundProblems({files:[],lineContactorRelease:curve},{}).some(x=>x.startsWith('lineContactorRelease:')), 'invalid release curve accepted');

  const played = [], builtin = [];
  a._play = (buffer, level) => played.push({buffer,level}); a.click = (gain) => builtin.push(gain);
  for (const [events, want] of [[new Map([['lineContactor',['generic']]]),['generic','generic']],
    [new Map([['lineContactor',['generic']],['lineContactor.close',['start']],['lineContactor.open',['end']]]),['start','end']],
    [new Map([['lineContactor.open',['end']]]),['end']], [new Map(),[]]]) {
    played.length = builtin.length = 0; a.pack = {events};
    a.emit('lineContactor.close'); a.emit('lineContactor.open',{current:0});
    need(played.length + builtin.length === 2 && played.map(x=>x.buffer).join() === want.join(), 'directional/generic/synthesis fallback double-play');
    if (played.at(-1)?.buffer === 'end') need(played.at(-1).level === .25, 'sample release floor');
  }
  a.pack = null;
  a.contactorEvents.push({closed:false,current:480}); a.setActive(false); flush();
  need(a.contactorEvents.length === 0, 'pause left stale events');
  const n = a.trace.length; a.emit('lineContactor.open',{current:480}); a.setActive(true); flush();
  need(a.trace.length === n, 'pause/resume fabricated a contactor');
  a.setActive(false); const silent = fresh(); a.watchEquipment(silent); step(silent,100); silent.pressTo(5); step(silent,100);
  need(a.contactorEvents.length === 0, 'inactive audio accumulated switching');
  a.setActive(true); a.emit('lineContactor.open',{current:0});
  await new Promise(r=>setTimeout(r,100));
  need(a.master.gain.value === 0, 'minimum event gain defeated mute');
  await a.ctx.close();
  return {failures, edges, captured, abrupt, gradual, protection, overCurrent:overOut.current, levels};
}
