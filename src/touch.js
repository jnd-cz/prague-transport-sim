// On-screen controls for a phone or tablet (#79): the essentials as buttons over the view, sending the same
// key events as the keyboard (src/main.js keeps one control path). Shown on a touch screen by default;
// the 🎮 button in the menu switches them, remembered per device. ⋯ opens the rarer ones, ⚑ the report.
import { t } from './i18n.js';

const KEY = 'tram-touch';
// [key, label, hold] — a held button sends keyup on release (sand, look, the emergency brake)
const MAIN = [['Shift', 'tb.deadman', true, 'dm'], ['s', '▼', false, 'brake'], ['n', '0', false, 'neutral'], ['w', '▲', false, 'drive'], [' ', 'tb.stop', true, 'emerg']];
const SIDE = [['d', 'tb.doors'], ['b', 'tb.bell'], ['a', 'tb.sand', true], ['q', '◀', true], ['e', '▶', true], ['v', 'tb.view'], ['z', 'tb.mirror'], ['p', 'II']];
const MORE = [['y', 'tb.switch', true], ['x', 'tb.iron'], ['c', 'tb.cutout', true], ['h', 'tb.saloon'], ['k', 'tb.cab'], ['f', 'tb.flap'], ['o', 'tb.auto'], ['m', 'tb.mute'], ['F9', '⚑']];

export class TouchControls {
  constructor({ deadman }) {
    this.deadman = deadman; // () => the dead-man option is on: a held button for Shift
    let on;
    try { on = localStorage.getItem(KEY); } catch { /* (no storage) */ }
    this.set(on === null || on === undefined ? matchMedia('(pointer: coarse)').matches : on === '1', false);
    const css = document.createElement('style');
    css.textContent = `
#touch { display: none; position: fixed; inset: 0; pointer-events: none; z-index: 6; user-select: none; -webkit-user-select: none }
body.touch.shift #touch { display: block }
#touch button { pointer-events: auto; touch-action: none; font: 700 15px/1 system-ui, sans-serif; color: #eee; background: rgba(30,36,32,.78);
  border: 1px solid rgba(255,255,255,.25); border-radius: 10px; min-width: 46px; min-height: 46px; padding: 4px 8px; -webkit-tap-highlight-color: transparent }
#touch button.down { background: rgba(120,140,125,.9) }
#touch .main { position: absolute; left: 0; right: 0; bottom: calc(var(--dashH) + 6px); display: flex; gap: 8px; justify-content: center; padding: 0 8px }
#touch .main button { flex: 1; max-width: 110px; min-height: 58px; font-size: 22px }
#touch .main .emerg { background: rgba(160,32,24,.85); font-size: 15px }
#touch .main .drive { background: rgba(44,107,55,.85) }
#touch .main .brake { background: rgba(138,90,28,.85) }
#touch .side { position: absolute; left: 6px; top: calc(var(--topH) + 6px); display: flex; flex-direction: column; gap: 6px; max-height: calc(100% - var(--topH) - var(--dashH) - 80px); flex-wrap: wrap }
#touch .more { position: absolute; left: 62px; top: calc(var(--topH) + 6px); display: none; flex-wrap: wrap; gap: 6px; max-width: 60vw }
#touch.open .more { display: flex }
#touch .main .dm { display: none; background: rgba(40,70,120,.85); font-size: 13px }
#touch.deadman .main .dm { display: block }
body.touch #rpBtn { display: none !important }
.tbToggle { position: fixed; top: 8px; left: 8px; z-index: 11; font-size: 18px; padding: 6px 9px }
body.shift .tbToggle { display: none }`;
    document.head.appendChild(css);
    const box = (this.box = document.createElement('div'));
    box.id = 'touch';
    const btn = ([k, label, hold, cls]) => `<button data-k="${k === ' ' ? 'space' : k}"${hold ? ' data-hold="1"' : ''}${cls ? ` class="${cls}"` : ''} data-l="${label}"></button>`;
    box.innerHTML = `<div class="main">${MAIN.map(btn).join('')}</div>
<div class="side">${SIDE.map(btn).join('')}<button data-more="1">⋯</button></div>
<div class="more">${MORE.map(btn).join('')}</div>`;
    document.body.appendChild(box);
    this.labels();
    // a pressed button: keydown, and keyup when the finger lifts (or slides off a held one)
    const down = new Map();
    const send = (type, k) => window.dispatchEvent(new KeyboardEvent(type, { key: k === 'space' ? ' ' : k, bubbles: true }));
    box.addEventListener('pointerdown', (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      e.preventDefault();
      if (b.dataset.more) { box.classList.toggle('open'); return; }
      b.classList.add('down');
      down.set(e.pointerId, b);
      try { b.setPointerCapture(e.pointerId); } catch { /* (gone) */ }
      send('keydown', b.dataset.k);
      if (!b.dataset.hold) send('keyup', b.dataset.k);
    });
    const up = (e) => {
      const b = down.get(e.pointerId);
      if (!b) return;
      down.delete(e.pointerId);
      b.classList.remove('down');
      if (b.dataset.hold) send('keyup', b.dataset.k);
      if (MORE.some(([k]) => (k === ' ' ? 'space' : k) === b.dataset.k) && !b.dataset.hold) box.classList.remove('open');
    };
    box.addEventListener('pointerup', up);
    box.addEventListener('pointercancel', up);
    box.addEventListener('contextmenu', (e) => e.preventDefault());
    // the switch, in the menu and in a shift
    const tg = (this.toggle = document.createElement('button'));
    tg.className = 'tbToggle';
    tg.textContent = '🎮';
    tg.onclick = () => this.set(!this.on);
    document.body.appendChild(tg);
    this.sync();
  }

  set(on, keep = true) {
    this.on = on;
    document.body.classList.toggle('touch', on);
    if (keep) try { localStorage.setItem(KEY, on ? '1' : '0'); } catch { /* (no storage) */ }
    if (this.toggle) this.toggle.title = t(on ? 'tb.off' : 'tb.on');
  }

  labels() {
    for (const b of this.box.querySelectorAll('button[data-l]')) b.textContent = b.dataset.l.startsWith('tb.') ? t(b.dataset.l) : b.dataset.l;
  }

  // at the start of a shift (main.js): the dead-man button with its option
  sync() { this.box.classList.toggle('deadman', !!this.deadman()); }
}
