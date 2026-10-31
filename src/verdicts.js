// Review verdicts (#136): what the reviewer decided per finding, kept in the browser and sent to the server,
// which merges them per finding (the newer "t" wins: tools/reviews.py). On the web host that is
// review.php (tools/review.php, uploaded by tools/deploy.py); without it (tools/serve.py) POST
// /review/NAME.json, read back from reports/reviews/NAME.json. Records not sent yet stay in
// localStorage and go with the next save or retry.
const KEY = (name) => `tram-review:${name}`;

// one record file to the store (src/report.js): review.php, else tools/serve.py; true when stored
export async function postRecord(name, body) {
  const opts = { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Review': '1' }, body: JSON.stringify(body) };
  for (const url of [`review.php?f=${name}`, `review/${name}.json`]) {
    try {
      const r = await fetch(url, opts);
      if (r.ok && (r.headers.get('content-type') || '').includes('json')) return true;
    } catch { /* (offline) */ }
  }
  return false;
}

export class Verdicts {
  constructor(name, meta = {}, onStatus = () => {}) {
    Object.assign(this, { name, meta, onStatus, items: {}, pending: {}, mode: null, state: 'loading' });
    try {
      const v = JSON.parse(localStorage.getItem(KEY(name)) || '{}');
      this.items = v.items || {};
      this.pending = v.pending || {};
    } catch { /* (no storage: a private window) */ }
  }

  // the server's records merged in, then what is still to send
  async load() {
    let got = null;
    try {
      const r = await fetch(`review.php?f=${this.name}`, { cache: 'no-store' });
      if (r.ok && (r.headers.get('content-type') || '').includes('json')) { this.mode = 'php'; got = await r.json(); }
    } catch { /* (offline) */ }
    if (!this.mode) {
      this.mode = 'serve';
      try {
        const r = await fetch(`reports/reviews/${this.name}.json`, { cache: 'no-store' });
        if (r.ok) got = await r.json();
      } catch { /* (offline) */ }
    }
    for (const [k, v] of Object.entries(got?.items || {})) if (!this.items[k] || (v.t || 0) > (this.items[k].t || 0)) this.items[k] = v;
    this._keep();
    await this.send();
  }

  get(id) { return this.items[id]; }

  set(id, rec) {
    const r = { ...rec, t: Date.now() };
    this.items[id] = this.pending[id] = r;
    this._keep();
    this.send();
    return r;
  }

  async send() {
    const ids = Object.keys(this.pending);
    if (!ids.length) { this._status('saved'); return true; }
    if (this.busy) return false;
    this.busy = true;
    const items = Object.fromEntries(ids.map((k) => [k, this.pending[k]]));
    const url = this.mode === 'php' ? `review.php?f=${this.name}` : `review/${this.name}.json`;
    let ok = false;
    try {
      const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Review': '1' },
        body: JSON.stringify({ meta: { ...this.meta, saved: new Date().toISOString() }, items }) });
      ok = r.ok;
    } catch { /* (offline: kept for later) */ }
    this.busy = false;
    // (a record changed again while it was sent stays pending)
    if (ok) for (const k of ids) if (this.pending[k] === items[k]) delete this.pending[k];
    this._keep();
    this._status(ok ? (Object.keys(this.pending).length ? 'sending' : 'saved') : 'offline');
    if (ok && Object.keys(this.pending).length) return this.send();
    return ok;
  }

  _status(s) { this.state = s; this.onStatus(s, Object.keys(this.pending).length); }

  _keep() {
    try { localStorage.setItem(KEY(this.name), JSON.stringify({ items: this.items, pending: this.pending })); } catch { /* (full or off) */ }
  }
}
