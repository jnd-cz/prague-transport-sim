// Report an issue from a shift or inspect mode (#138): ⚑ (or F9) pauses the game and opens a note; Send
// stores the note, the state of the moment (place, tram, run, camera, version) and a screenshot as one
// record report-<time>-<random> through the review store (src/verdicts.js: review.php on the host,
// tools/serve.py locally), where tools/deploy.py --pull-reviews hands it to the agent as
// reports/reviews/report-….json and .jpg. The id is shown to be quoted in chat.
import { toLatLon } from './geo.js';
import { postRecord } from './verdicts.js';

const KINDS = ['track / terrain', 'streets / kerbs', 'buildings / objects', 'traffic / pedestrians', 'signals / rules', 'tram / physics', 'sound / HUD', 'other'];
const SHOT_W = 1280; // px: the screenshot's largest width

export class Reporter {
  // state(): the moment's facts; shot(): a data URL of the frame as drawn now; pause(on) / paused()
  constructor({ state, shot, pause }) {
    Object.assign(this, { state, shot, pause });
    this.version = null;
    fetch('version.json', { cache: 'no-store' }).then((r) => (r.ok ? r.json() : null)).then((v) => { this.version = v; }, () => {});
    const css = document.createElement('style');
    css.textContent = `
#rpBtn { position: fixed; left: 8px; bottom: 8px; z-index: 70; font: 600 15px system-ui, sans-serif; color: #fff; background: rgba(150,40,40,.85);
  border: 1px solid #e88; border-radius: 8px; padding: 6px 10px; cursor: pointer; display: none }
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
    b.textContent = '⚑ Report';
    b.title = 'report what you see here (F9)';
    b.onclick = () => this.open();
    const box = (this.box = document.createElement('div'));
    box.id = 'rpBox';
    box.innerHTML = `<div class="p"><b>Report an issue</b>
<select id="rpKind">${KINDS.map((k) => `<option>${k}</option>`).join('')}</select>
<textarea id="rpNote" rows="4" placeholder="what is wrong here, what should it be"></textarea>
<label><input type="checkbox" id="rpShot" checked> with the screenshot</label><img id="rpImg" alt="">
<div class="dim" id="rpWhere"></div>
<div class="row"><button id="rpCancel">Cancel</button><button class="go" id="rpSend">Send</button></div>
<div class="dim" id="rpMsg"></div></div>`;
    document.body.append(b, box);
    const $ = (id) => box.querySelector(`#${id}`);
    this.$ = $;
    $('rpCancel').onclick = () => this.close();
    $('rpSend').onclick = () => this.send();
    $('rpShot').onchange = () => { $('rpImg').style.display = $('rpShot').checked ? '' : 'none'; };
    box.addEventListener('keydown', (e) => { e.stopPropagation(); if (e.key === 'Escape') this.close(); });
  }

  get isOpen() { return this.box.classList.contains('show'); }

  open() {
    if (this.isOpen) return;
    // (the picture and the facts first: what is on the screen when the reporter decided to report)
    this.img = (() => { try { return this.shot(); } catch { return null; } })();
    this.facts = this.state();
    this.wasPaused = this.pause();
    const $ = this.$, f = this.facts;
    $('rpImg').src = this.img || '';
    $('rpImg').style.display = this.img ? '' : 'none';
    $('rpShot').parentElement.style.display = this.img ? '' : 'none';
    $('rpWhere').textContent = [`line ${f.line}`, f.tram && `s ${f.tram.s} m, ${f.tram.kmh} km/h`, f.nextStop && `next ${f.nextStop}`, f.clock, `${f.lat}, ${f.lon}`].filter(Boolean).join(' · ');
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
    const $ = this.$, d = new Date(), p = (n) => String(n).padStart(2, '0');
    const id = `report-${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}-${Math.random().toString(36).slice(2, 6)}`;
    const rec = { kind: $('rpKind').value, note: $('rpNote').value.trim(), ...this.facts, version: this.version,
      shot: $('rpShot').checked ? this.img : null, t: Date.now() };
    $('rpSend').disabled = true;
    $('rpMsg').textContent = 'sending…';
    const ok = await postRecord(id, { meta: { report: true }, items: { [id]: rec } });
    if (ok) {
      $('rpMsg').innerHTML = `Sent as <b>${id}</b>: quote it in the chat.`;
      setTimeout(() => { if (this.isOpen && $('rpMsg').textContent.includes(id)) this.close(); }, 4000);
      $('rpNote').value = '';
    } else {
      // (no server: the record as a file, so nothing is lost)
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([JSON.stringify({ items: { [id]: rec } })], { type: 'application/json' }));
      a.download = `${id}.json`;
      a.click();
      $('rpMsg').textContent = `The server did not take it: saved as ${id}.json in your downloads.`;
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
