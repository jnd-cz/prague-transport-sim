// SPDX-License-Identifier: AGPL-3.0-or-later
// A gamepad (#592): the standard layout (Xbox and PlayStation pads), read every frame and sent as the keyboard's
// key events, as the touch buttons are (src/touch.js), so src/main.js keeps one control path. The triggers set the
// steps by how far they are pressed (the right one drive, the left one brake, the left over the right); a trigger
// sends a step only when its step changes, so the keyboard works beside a pad at rest. While a pad is connected the
// dead-man pedal counts as held (src/main.js: a button held all shift tires the hand). Its mapping is in README.md.

// standard-layout button index → [key, code]; every one is held: keydown on press, keyup on release
const BUTTONS = {
  0: ['d', 'KeyD'],          // A / ✕: doors
  1: ['b', 'KeyB'],          // B / ○: bell
  2: ['a', 'KeyA'],          // X / □: sand
  3: [' ', 'Space'],         // Y / △: emergency brake
  4: ['r', 'KeyR'],          // LB / L1: the parking brake on and off (advanced controls)
  5: ['g', 'KeyG'],          // RB / R1: look closer
  8: ['v', 'KeyV'],          // Back / Share: cab or outside view
  9: ['p', 'KeyP'],          // Start / Options: pause
  10: ['z', 'KeyZ'],         // L3: mirror
  12: ['w', 'KeyW'],         // D-pad up: a step towards drive
  13: ['s', 'KeyS'],         // D-pad down: a step towards brake
  14: [',', 'Comma'],        // D-pad left: indicators left
  15: ['.', 'Period'],       // D-pad right: indicators right
};
// held W / S repeat as a held key does: after 0.4 s, every 0.15 s
const REPEAT = new Set([12, 13]), DELAY = 0.4, EVERY = 0.15;
const LT = 6, RT = 7, STEPS = 5;
// a trigger's step: step n from (n - 1) / 5 + 0.06 of its travel, back below n - 1 only under (n - 1) / 5 + 0.01, so a
// trigger held at a step's edge doesn't flicker between two
export function trigStep(v, cur) {
  let n = cur;
  while (n < STEPS && v >= n / STEPS + 0.06) n++;
  while (n > 0 && v < (n - 1) / STEPS + 0.01) n--;
  return n;
}

export class Gamepad {
  constructor({ onConnect } = {}) {
    this.pads = new Map(); // index → { down: Map(button → { h: held s, next: next repeat }), drive, brake, cmd, look }
    this.onConnect = onConnect;
    this.last = null;
    window.addEventListener('gamepadconnected', (e) => { this.onConnect?.(e.gamepad.id); });
    window.addEventListener('gamepaddisconnected', (e) => this.release(e.gamepad.index));
    if (navigator.getGamepads) requestAnimationFrame((t) => this.frame(t));
  }

  get active() { return this.pads.size > 0; }

  send(type, key, code, extra = {}) {
    window.dispatchEvent(new KeyboardEvent(type, { key, code, bubbles: true, ...extra }));
  }

  // a pad gone: whatever it held is let go
  release(i) {
    const p = this.pads.get(i);
    if (!p) return;
    for (const b of p.down.keys()) this.send('keyup', ...BUTTONS[b]);
    if (p.look) this.send('keyup', p.look, p.look === 'q' ? 'KeyQ' : 'KeyE');
    this.pads.delete(i);
  }

  frame(now) {
    requestAnimationFrame((t) => this.frame(t));
    const dt = this.last === null ? 0 : Math.min(0.1, (now - this.last) / 1000);
    this.last = now;
    let list;
    try { list = navigator.getGamepads(); } catch { return; }
    for (const g of list) {
      if (!g || !g.connected || g.mapping !== 'standard') continue;
      let p = this.pads.get(g.index);
      if (!p) this.pads.set(g.index, (p = { down: new Map(), drive: 0, brake: 0, cmd: 0, look: null }));
      this.poll(g, p, dt);
    }
  }

  poll(g, p, dt) {
    const B = g.buttons;
    for (const [i, [key, code]] of Object.entries(BUTTONS)) {
      const b = +i, on = !!B[b]?.pressed, held = p.down.get(b);
      if (on && held === undefined) { p.down.set(b, { h: 0, next: DELAY }); this.send('keydown', key, code); }
      else if (on) {
        held.h += dt;
        if (REPEAT.has(b) && held.h >= held.next) { held.next += EVERY; this.send('keydown', key, code, { repeat: true }); }
      } else if (held !== undefined) { p.down.delete(b); this.send('keyup', key, code); }
    }
    // the triggers: a drive or brake step, sent as the number keys (with Shift a brake step, 0 both pedals released)
    p.drive = trigStep(B[RT]?.value ?? 0, p.drive);
    p.brake = trigStep(B[LT]?.value ?? 0, p.brake);
    const cmd = p.brake ? -p.brake : p.drive;
    if (cmd !== p.cmd) {
      p.cmd = cmd;
      const n = Math.abs(cmd), ev = { shiftKey: cmd < 0 };
      this.send('keydown', String(n), `Digit${n}`, ev);
      this.send('keyup', String(n), `Digit${n}`, ev);
    }
    // the right stick across: look out of the left or right window, let go under 0.4
    const x = g.axes[2] ?? 0;
    const look = x < -0.6 ? 'q' : x > 0.6 ? 'e' : Math.abs(x) < 0.4 ? null : p.look;
    if (look !== p.look) {
      if (p.look) this.send('keyup', p.look, p.look === 'q' ? 'KeyQ' : 'KeyE');
      if (look) this.send('keydown', look, look === 'q' ? 'KeyQ' : 'KeyE');
      p.look = look;
    }
  }
}
