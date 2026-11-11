// On-screen controls for a phone or tablet (#79): the essentials as buttons over the view, sending the same
// key events as the keyboard (src/main.js keeps one control path). Shown on a touch screen by default;
// the 🎮 button in the menu switches them, remembered per device. ⋯ opens the rarer ones, ✉ the feedback note.
// Full screen (#485): asked once in the menu on a touch screen; with a yes, a shift starts in full screen turned to
// landscape (a browser goes full screen only from a tap: Start's), and ⛶ switches it any time. Leaving it (the back
// gesture) holds until the next start. Safari on an iPhone has no full screen for a page: there the question becomes how
// to add the game to the home screen, from where it opens full screen (app.webmanifest, the apple-* tags in index.html);
// opened so, it asks nothing and only the hint to turn the phone stays. In landscape on a phone the controller is a column at the right thumb and the
// other buttons two columns at the left, the dashboard between them (the CSS below).
import { t } from './i18n.js';

const KEY = 'tram-touch';
const FS_KEY = 'tram-fullscreen'; // '1' yes, '0' no, unset: not asked yet
const STARTS = ['btnStart', 'btnPerfTest', 'btnPerfRef'];
const store = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch { /* (no storage) */ } return null; };
const fsElement = () => document.fullscreenElement || document.webkitFullscreenElement || null;
const fsAble = () => !!(document.fullscreenEnabled || document.webkitFullscreenEnabled);
// (started from the home screen: full screen already, the browser's bars gone)
const standalone = () => matchMedia('(display-mode: fullscreen), (display-mode: standalone)').matches || navigator.standalone === true;
// [key, label, hold] — a held button sends keyup on release (sand, look, zoom, the emergency brake)
const MAIN = [['Shift', 'tb.deadman', true, 'dm'], ['s', '▼', false, 'brake'], ['n', '0', false, 'neutral'], ['w', '▲', false, 'drive'], [' ', 'tb.stop', true, 'emerg']];
const SIDE = [['d', 'tb.doors'], ['b', 'tb.bell'], ['a', 'tb.sand', true], ['q', '◀', true], ['e', '▶', true], ['g', '🔍', true], ['v', 'tb.view'], ['z', 'tb.mirror'], ['p', 'II']];
// (the indicators: left, right, hazard; the high beams: held a flash, 'L' on and off as Shift+L)
const MORE = [[',', '⇦'], ['.', '⇨'], ['/', '⚠'], ['l', 'tb.flash', true], ['L', 'tb.beam'], ['r', 'tb.park'], ['y', 'tb.switch', true], ['x', 'tb.iron'], ['c', 'tb.cutout', true], ['h', 'tb.saloon'], ['k', 'tb.cab'], ['f', 'tb.flap'], ['o', 'tb.auto'], ['m', 'tb.mute'], ['F9', '✉']];

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
body.shift .tbToggle { display: none }
.tbToggle.fs { left: 56px }
#fsAsk { position: fixed; top: 8px; left: 104px; right: 8px; z-index: 11; display: none; gap: 8px; align-items: center; flex-wrap: wrap;
  background: rgba(15,20,17,.94); border: 1px solid rgba(255,255,255,.2); border-radius: 8px; padding: 6px 10px; font: 14px system-ui, sans-serif; color: #eee }
/* (only over the game's menu: not in a shift, nor over ?review's map) */
#menu:not(.hidden) ~ #fsAsk.show { display: flex } body.shift #fsAsk { display: none }
#fsAsk button { font: 600 14px system-ui, sans-serif; padding: 6px 12px; border-radius: 6px }
#fsTurn { position: fixed; top: 40%; left: 50%; transform: translateX(-50%); z-index: 7; display: none; pointer-events: none;
  background: rgba(10,14,12,.86); color: #eee; padding: 8px 14px; border-radius: 8px; font: 600 15px system-ui, sans-serif }
@media (orientation: portrait) { body.fs.shift #fsTurn { display: block } }
/* a phone in landscape: the controller at the right thumb, the rest at the left, the dashboard and the top bar between */
@media (orientation: landscape) and (max-height: 520px) {
  body.touch { --padL: 132px; --padR: 104px }
  body.touch #dash { left: var(--padL); right: var(--padR); border-radius: 10px 10px 0 0 }
  body.touch #top, body.touch #assist, body.touch #msgs { left: calc(50% + (var(--padL) - var(--padR)) / 2) }
  body.touch #assist { max-width: calc(100vw - var(--padL) - var(--padR) - 16px) }
  body.touch #mirror { right: calc(var(--padR) + 8px); bottom: calc(var(--dashH) + 8px); height: clamp(80px, 34vh, 180px) }
  #touch .main { left: auto; right: 6px; top: 6px; bottom: 6px; width: 92px; flex-direction: column; gap: 6px; padding: 0 }
  #touch .main button { flex: 1; max-width: none; min-height: 0; font-size: 20px }
  #touch .main .dm { order: 0 } #touch .main .drive { order: 1 } #touch .main .neutral { order: 2 }
  #touch .main .brake { order: 3 } #touch .main .emerg { order: 4; font-size: 14px }
  #touch .side { top: 6px; max-height: none; width: 120px; flex-direction: row; align-content: flex-start }
  #touch .side button { width: 57px; min-width: 0; padding: 2px; font-size: 13px }
  /* (in pairs: doors bell, sand zoom, look left right, view mirror, pause more) */
  #touch .side [data-k="g"] { order: 1 } #touch .side [data-k="q"], #touch .side [data-k="e"] { order: 2 }
  #touch .side [data-k="v"], #touch .side [data-k="z"] { order: 3 } #touch .side [data-k="p"], #touch .side [data-more] { order: 4 }
  #touch .more { left: var(--padL); top: 6px; max-width: calc(100vw - var(--padL) - var(--padR) - 8px) }
}`;
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
    const send = (type, k) => window.dispatchEvent(new KeyboardEvent(type, { key: k === 'space' ? ' ' : k, shiftKey: k === 'L', bubbles: true }));
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
    this.fullscreen();
    this.sync();
  }

  // full screen: the question, ⛶, the starts that enter it, the landscape lock and the hint to turn the phone
  fullscreen() {
    const turn = (this.fsTurn = document.createElement('div'));
    turn.id = 'fsTurn';
    document.body.appendChild(turn);
    const coarse = matchMedia('(pointer: coarse)').matches;
    if (standalone()) { document.body.classList.add('fs'); this.fsLabels(); return; }
    if (!fsAble()) {
      // (Safari on an iPhone: the way to full screen is the home screen; said once)
      if (!coarse || store(FS_KEY) !== null) return;
      const ask = (this.fsAsk = document.createElement('div'));
      ask.id = 'fsAsk';
      ask.className = 'show home';
      ask.innerHTML = '<span></span><button data-a="0"></button>';
      ask.addEventListener('click', (e) => { if (e.target.closest('button')) { store(FS_KEY, '0'); ask.classList.remove('show'); } });
      document.body.appendChild(ask);
      this.fsLabels();
      return;
    }
    const fs = (this.fsToggle = document.createElement('button'));
    fs.className = 'tbToggle fs';
    fs.textContent = '⛶';
    fs.onclick = () => {
      if (fsElement()) { store(FS_KEY, '0'); (document.exitFullscreen || document.webkitExitFullscreen)?.call(document); } else { store(FS_KEY, '1'); this.enter(); }
      ask.classList.remove('show');
    };
    document.body.appendChild(fs);
    const ask = (this.fsAsk = document.createElement('div'));
    ask.id = 'fsAsk';
    ask.innerHTML = '<span></span><button data-a="1"></button><button data-a="0"></button>';
    ask.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      store(FS_KEY, b.dataset.a);
      ask.classList.remove('show');
      if (b.dataset.a === '1') this.enter();
    });
    document.body.appendChild(ask);
    if (store(FS_KEY) === null && coarse) ask.classList.add('show');
    // (a start's tap is the gesture the browser asks for; capture: before main.js starts the shift)
    document.addEventListener('click', (e) => {
      if (store(FS_KEY) === '1' && !fsElement() && STARTS.includes(e.target.closest('button')?.id)) this.enter();
    }, true);
    const sync = () => { document.body.classList.toggle('fs', !!fsElement() || standalone()); this.fsLabels(); };
    document.addEventListener('fullscreenchange', sync);
    document.addEventListener('webkitfullscreenchange', sync);
    this.fsLabels();
  }

  enter() {
    const el = document.documentElement;
    const req = el.requestFullscreen ? el.requestFullscreen({ navigationUI: 'hide' }) : el.webkitRequestFullscreen?.();
    // (the lock works only in full screen and only where the browser allows it: Chrome on Android; elsewhere the hint)
    Promise.resolve(req).then(() => screen.orientation?.lock?.('landscape')).catch(() => {});
  }

  fsLabels() {
    if (this.fsTurn) this.fsTurn.textContent = '↻ ' + t('fs.turn');
    if (this.fsToggle) this.fsToggle.title = t(fsElement() ? 'fs.off' : 'fs.on');
    if (!this.fsAsk) return;
    const [q, a, b] = this.fsAsk.children;
    if (this.fsAsk.classList.contains('home')) { q.textContent = t('fs.home'); a.textContent = t('fs.ok'); return; }
    q.textContent = t('fs.ask');
    a.textContent = t('fs.yes');
    b.textContent = t('fs.no');
  }

  set(on, keep = true) {
    this.on = on;
    document.body.classList.toggle('touch', on);
    if (keep) try { localStorage.setItem(KEY, on ? '1' : '0'); } catch { /* (no storage) */ }
    if (this.toggle) this.toggle.title = t(on ? 'tb.off' : 'tb.on');
  }

  labels() {
    for (const b of this.box.querySelectorAll('button[data-l]')) b.textContent = b.dataset.l.startsWith('tb.') ? t(b.dataset.l) : b.dataset.l;
    this.fsLabels();
  }

  // at the start of a shift (main.js): the dead-man button with its option
  sync() { this.box.classList.toggle('deadman', !!this.deadman()); }
}
