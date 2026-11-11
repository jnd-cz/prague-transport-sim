// Feedback from a shift (#138, #350): ✉ (or F9) pauses the game and opens a note; Send posts the note, the
// moment's state (place, tram, run, camera, version), the errors met so far and, if ticked, a screenshot to
// feedback.php (tools/feedback.php on the host, tools/serve.py locally), which stores it under an id of its own.
// tools/deploy.py --pull moves the notes into the machine's feedback folder (tools/feedback.py) and tools/feedback.py lists them: a note
// is read, and becomes an issue only when someone decides so. The form tells the player what goes with a note.
// The errors are kept from the page's start (script errors, rejected promises, a lost WebGL context), so a
// note says what went wrong before it; a page that cannot start offers to send them alone (failNote).
import { toLatLon } from './geo.js';
import { t, getLang, onLangChange } from './i18n.js';

const KINDS = ['driving', 'stops', 'signals', 'track', 'city', 'traffic', 'controls', 'speed', 'other'];
const SHOT_W = 1280; // px: the screenshot's largest width
const MAX_ERRORS = 20, MAX_NOTE = 5000; // (MAX_NOTE: feedback.php's cap)

// ------------------------------------------------------------------ errors met on this page
export const errors = [];
export function noteError(kind, msg, where) {
  if (errors.length >= MAX_ERRORS) errors.shift();
  errors.push({ t: Math.round(performance.now() / 100) / 10, kind, msg: String(msg).slice(0, 300), ...(where ? { where } : {}) });
}
addEventListener('error', (e) => {
  // (no e.error: the browser's own notices, like a ResizeObserver loop; a resource that failed has no message)
  if (e.error || e.message) noteError('error', e.message || e.error, e.filename ? `${e.filename.split('/').pop()}:${e.lineno}` : undefined);
});
addEventListener('unhandledrejection', (e) => noteError('rejection', e.reason?.message || e.reason));

// the deployed version (tools/deploy.py's version.json; none locally). Fetched here as well as in main.js: on a
// phone main's answer came back empty in the first reports
let version = null;
fetch('version.json', { cache: 'no-store' }).then((r) => (r.ok ? r.json() : null)).then((v) => { version = v; }, () => {});

// what the game adds to every note once it runs (src/main.js: the machine, the load times, the frame-time log)
let extra = () => ({});
export function addFacts(f) { extra = f; }

// what any note carries about the page, whatever its state
function pageFacts() {
  let more = {};
  try { more = extra() || {}; } catch { /* (a fact that fails leaves the others) */ }
  return { lang: getLang(), url: location.href, viewport: `${innerWidth}x${innerHeight}@${devicePixelRatio}`, ua: navigator.userAgent,
    version: version || window.deployVersion || null, errors: errors.slice(), ...more };
}

// a note of any kind with the page's facts: its id, or null
export function sendNote(rec) { return postFeedback({ note: '', ...rec, ...pageFacts(), t: Date.now() }); }

// a note to feedback.php: its id, or null when nothing took it
export async function postFeedback(rec) {
  try {
    const r = await fetch('feedback.php', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Feedback': '1' }, body: JSON.stringify(rec) });
    if (!r.ok || !(r.headers.get('content-type') || '').includes('json')) return null;
    return (await r.json()).id || null;
  } catch { return null; } // (offline)
}

// the errors alone, from a page that stopped (the loading screen, a lost context): one click sends them
export function failNote(where, el) {
  const b = document.createElement('button');
  b.className = 'fbSendError';
  b.textContent = t('fb.sendError');
  b.onclick = async () => {
    b.disabled = true;
    const id = await sendNote({ kind: 'error', where, line: new URLSearchParams(location.search).get('line') });
    b.textContent = id ? t('fb.errorSent') : t('fb.errorFailed');
  };
  el.append(b);
  return b;
}

export class Reporter {
  // state(): the moment's facts; shot(): a data URL of the frame as drawn now; pause(on) / paused()
  constructor({ state, shot, pause }) {
    Object.assign(this, { state, shot, pause });
    const css = document.createElement('style');
    css.textContent = `
#rpBtn { position: fixed; left: 8px; bottom: 8px; z-index: 70; font: 600 15px system-ui, sans-serif; color: #fff; background: rgba(40,80,130,.85);
  border: 1px solid #8ab; border-radius: 8px; padding: 6px 10px; cursor: pointer; display: none }
body.shift #rpBtn { display: block }
#rpBox { position: fixed; inset: 0; z-index: 80; display: none; align-items: center; justify-content: center; background: rgba(0,0,0,.45) }
#rpBox.show { display: flex }
#rpBox .p { width: min(460px, calc(100vw - 24px)); max-height: calc(100vh - 24px); overflow: auto; background: #1b1e24; color: #eee; border-radius: 10px;
  padding: 12px; font: 14px/1.4 system-ui, sans-serif; box-sizing: border-box }
#rpBox textarea, #rpBox select { width: 100%; box-sizing: border-box; font: inherit; color: #eee; background: #111318; border: 1px solid #444; border-radius: 6px; padding: 6px 8px; margin: 4px 0 }
#rpBox img { width: 100%; max-height: 28vh; object-fit: contain; background: #000; border-radius: 6px; margin: 4px 0 }
#rpBox .row { display: flex; gap: 8px; justify-content: flex-end; margin-top: 6px; flex-wrap: wrap }
#rpBox button { font: inherit; color: #eee; background: #2c313a; border: 1px solid #555; border-radius: 6px; padding: 8px 14px; cursor: pointer }
#rpBox button.go { background: #3d5a80; border-color: #6a8fc0 }
#rpBox .dim { opacity: .7; font-size: 12px; word-break: break-word }`;
    document.head.appendChild(css);
    const b = (this.btn = document.createElement('button'));
    b.id = 'rpBtn';
    b.onclick = () => this.open();
    const box = (this.box = document.createElement('div'));
    box.id = 'rpBox';
    box.innerHTML = `<div class="p"><b id="rpTitle"></b>
<select id="rpKind">${KINDS.map((k) => `<option value="${k}"></option>`).join('')}</select>
<textarea id="rpNote" rows="4" maxlength="${MAX_NOTE}"></textarea>
<label><input type="checkbox" id="rpShot" checked> <span id="rpShotL"></span></label><img id="rpImg" alt="">
<div class="dim" id="rpWhat"></div>
<div class="dim" id="rpWhere"></div>
<div class="row"><button id="rpCancel"></button><button class="go" id="rpSend"></button></div>
<div class="dim" id="rpMsg"></div></div>`;
    document.body.append(b, box);
    const $ = (id) => box.querySelector(`#${id}`);
    this.$ = $;
    this.texts();
    onLangChange(() => this.texts());
    $('rpCancel').onclick = () => this.close();
    $('rpSend').onclick = () => this.send();
    $('rpShot').onchange = () => { $('rpImg').style.display = $('rpShot').checked ? '' : 'none'; };
    box.addEventListener('keydown', (e) => { e.stopPropagation(); if (e.key === 'Escape') this.close(); });
  }

  // the labels in the language chosen now
  texts() {
    const $ = this.$;
    this.btn.textContent = t('fb.button');
    this.btn.title = t('fb.buttonTitle');
    $('rpTitle').textContent = t('fb.title');
    for (const o of $('rpKind').options) o.textContent = t(`fb.k.${o.value}`);
    $('rpNote').placeholder = t('fb.note');
    $('rpShotL').textContent = t('fb.shot');
    $('rpWhat').textContent = t('fb.what');
    $('rpCancel').textContent = t('fb.cancel');
    $('rpSend').textContent = t('fb.send');
  }

  get isOpen() { return this.box.classList.contains('show'); }

  open() {
    if (this.isOpen) return;
    // (the picture and the facts first: what is on the screen when the player decided to write)
    this.img = (() => { try { return this.shot(); } catch { return null; } })();
    this.facts = this.state();
    this.wasPaused = this.pause();
    const $ = this.$, f = this.facts;
    this.texts();
    $('rpImg').src = this.img || '';
    $('rpImg').style.display = this.img && $('rpShot').checked ? '' : 'none';
    $('rpShot').parentElement.style.display = this.img ? '' : 'none';
    $('rpWhere').textContent = [`${f.line}`, f.tram && `${f.tram.kmh} km/h`, f.nextStop && `→ ${f.nextStop}`, f.clock].filter(Boolean).join(' · ');
    $('rpMsg').textContent = '';
    $('rpSend').disabled = false;
    this.box.classList.add('show');
    $('rpNote').focus();
  }

  close() {
    this.box.classList.remove('show');
    this.pause(this.wasPaused);
  }

  async send() {
    const $ = this.$, note = $('rpNote').value.trim();
    if (!note) { $('rpMsg').textContent = t('fb.empty'); return; }
    const rec = { kind: $('rpKind').value, note, ...this.facts, ...pageFacts(), shot: $('rpShot').checked ? this.img : null, t: Date.now() };
    $('rpSend').disabled = true;
    $('rpMsg').textContent = t('fb.sending');
    const id = await postFeedback(rec);
    if (id) {
      $('rpMsg').textContent = t('fb.sent', { id });
      setTimeout(() => { if (this.isOpen && $('rpMsg').textContent.includes(id)) this.close(); }, 4000);
      $('rpNote').value = '';
    } else {
      // (no server took it: the note as a file, so nothing is lost)
      const file = `feedback-${Date.now()}.json`, a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([JSON.stringify(rec)], { type: 'application/json' }));
      a.download = file;
      a.click();
      $('rpMsg').textContent = t('fb.failed', { file });
      $('rpSend').disabled = false;
    }
  }
}

// a downscaled JPEG of the canvas, drawn just now (WebGL keeps the frame only until the next one)
export function canvasShot(canvas, render) {
  render();
  const k = Math.min(1, SHOT_W / canvas.width), c = document.createElement('canvas');
  c.width = Math.round(canvas.width * k);
  c.height = Math.round(canvas.height * k);
  c.getContext('2d').drawImage(canvas, 0, 0, c.width, c.height);
  return c.toDataURL('image/jpeg', 0.75);
}

// lat/lon in the record, for a map without the game
export function place(x, y, origin) {
  const [lat, lon] = toLatLon(x, y, origin);
  return { lat: +lat.toFixed(6), lon: +lon.toFixed(6) };
}
