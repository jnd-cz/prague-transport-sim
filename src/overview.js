// SPDX-License-Identifier: AGPL-3.0-or-later
// The project's overview (overview.html, #826): overview.json from tools/overview.py (the board, the agents'
// sessions, what waits for the maintainer, the heavy queue with its estimated times), and the review sets' unanswered
// findings counted live as reviews.html counts them (src/reviewIndex.js). Every text from the data goes in as text.
import { answers, count } from './reviewIndex.js';

const OLD = 15 * 60; // (s: a snapshot older than this means the build PC is off or its loop stopped)
const ACTIVE = 5 * 60; // (s: a session whose log changed within this works now)
let snap = null, repo = 'jnd-cz/prague-transport-sim';

// an element with its properties and children; a string child is a text node
function h(tag, props, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v; else e.setAttribute(k, v);
  }
  for (const k of kids.flat(Infinity)) if (k != null && k !== false) e.append(k instanceof Node ? k : String(k));
  return e;
}
const now = () => Date.now() / 1000;
const ago = (t) => {
  if (!t) return '-';
  const s = Math.max(0, now() - t);
  return s < 90 ? `${Math.round(s)} s` : s < 5400 ? `${Math.round(s / 60)} min` : s < 172800 ? `${(s / 3600).toFixed(s < 36000 ? 1 : 0)} h` : `${Math.round(s / 86400)} d`;
};
const mins = (s) => (s < 5400 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);
const clock = (t) => (t ? new Date(t * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '?');
const gh = (kind, n) => h('a', { href: `https://github.com/${repo}/${kind}/${Number(n)}`, target: '_blank', rel: 'noopener' }, `${kind === 'pull' ? 'PR ' : ''}#${n}`);
const chip = (text, cls) => h('span', { class: `chip ${cls || ''}` }, text);
const plain = (t) => String(t).replace(/\*\*|`/g, ''); // (a PR's question items are Markdown)
const none = (text) => h('div', { class: 'none' }, text);
const fill = (id, ...kids) => document.getElementById(id).replaceChildren(...kids.flat(Infinity).filter(Boolean));
const prState = (pr) => (pr.state === 'OPEN' ? (pr.draft ? 'draft' : 'ready') : String(pr.state || '').toLowerCase());

function status() {
  const el = document.getElementById('status');
  if (!snap) return;
  const age = now() - snap.time;
  el.className = age > OLD ? 'old' : 'dim';
  el.replaceChildren(`updated ${ago(snap.time)} ago (${clock(snap.time)})`, age > OLD ? ': the build PC is off or its loop stopped' : '',
    ' · main ', h('a', { href: `https://github.com/${repo}/commit/${encodeURIComponent(snap.main.commit)}`, target: '_blank', rel: 'noopener' }, snap.main.commit.slice(0, 7)),
    ` ${snap.main.subject}`, snap.github ? '' : h('span', { class: 'bad' }, ' · GitHub did not answer: rows from git only'));
}

async function reviewSets() {
  // (the deployed index and the live answers, as reviews.html counts them; a stale set (issue closed) is left out)
  try {
    const r = await fetch('reports/review/index.json', { cache: 'no-store' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const index = await r.json();
    const { items } = await answers(index.lines);
    const sets = await Promise.all(index.sets.map(async (s) => {
      try { return { ...s, c: await count(s, items) }; } catch { return null; }
    }));
    return sets.filter((s) => s && s.c.waiting > 0 && s.waitsForInfo?.state !== 'CLOSED');
  } catch (e) {
    return { error: e.message };
  }
}

function waiting(sets) {
  const w = snap.waiting;
  const q = w.questions.map((p) => h('div', { class: 'card' },
    h('div', { class: 'top' }, gh('pull', p.pr), h('b', {}, p.title)),
    p.sections.map((s) => [h('div', { class: 'dim' }, s.title), h('ul', {}, s.items.map((i) => h('li', {}, plain(i))))])));
  const total = Array.isArray(sets) ? sets.reduce((a, s) => a + s.c.waiting, 0) : 0;
  const setList = Array.isArray(sets)
    ? (sets.length ? h('div', { class: 'card' }, h('div', { class: 'top' }, h('b', {}, `${total} findings in ${sets.length} sets`), h('a', { href: 'reviews.html' }, 'open the review sets')),
      h('ul', {}, sets.map((s) => h('li', {}, s.title || s.file.split('/').pop(), ' ',
        h('span', { class: 'wait' }, `${s.c.waiting} waiting`), s.waitsFor ? [' · ', gh('issues', s.waitsFor)] : '',
        s.lines.map((l) => [' · ', h('a', { href: `index.html?line=${encodeURIComponent(l)}&review${s.ids ? '' : `=${encodeURIComponent(s.file)}`}&todo` }, `line ${l}`)])))))
      : none('no findings wait'))
    : none(sets ? `the review index did not load (${sets.error})` : 'counting…');
  const n = w.questions.length + w.needsUser.length + w.readyPrs.length + total;
  fill('ov-waiting', h('h2', {}, `Waiting for you${n ? ` (${n})` : ''}`),
    h('h3', {}, 'PRs ready to merge'), w.readyPrs.length ? h('ul', {}, w.readyPrs.map((p) => h('li', {}, gh('pull', p.pr), ' ', p.title))) : none('none'),
    h('h3', {}, 'Questions in PRs'), q.length ? q : none('none'),
    h('h3', {}, 'Issues labelled needs-user'), w.needsUser.length ? h('ul', {}, w.needsUser.map((i) => h('li', {}, gh('issues', i.number), ' ', i.title))) : none('none'),
    h('h3', {}, 'Review findings'), setList);
}

function heavy() {
  const q = snap.heavy;
  const jobs = q.jobs.map((j) => {
    const run = j.state === 'running';
    const exp = j.expect ? `${mins(j.expect)}${j.expectFrom === 'history' ? ' (history)' : ''}` : 'not known';
    return h('div', { class: 'card' },
      h('div', { class: 'top' }, h('b', {}, j.what), chip(j.state, run ? 'done' : 'wait'), chip(j.share ? `shared ${Math.round(j.share.gb)} GB, ${j.share.cores} cores` : 'alone'),
        j.late ? chip('past its expected time', 'bad') : ''),
      h('div', { class: 'facts' }, h('span', {}, 'in ', h('b', {}, j.root)),
        h('span', {}, `${run ? 'running' : 'waiting'} `, h('b', {}, ago(j.since))),
        j.gb != null ? h('span', {}, 'holds ', h('b', {}, `${j.gb.toFixed(1)} GB`)) : '',
        h('span', {}, 'expected ', h('b', {}, exp)),
        run ? '' : h('span', {}, 'starts ', h('b', {}, j.start ? `~${clock(j.start)}` : 'not known')),
        h('span', {}, 'ends ', h('b', {}, j.late ? 'any moment' : j.finish ? `~${clock(j.finish)}` : 'not known'))),
      j.warn ? h('div', { class: 'bad' }, j.warn) : '');
  });
  const last = q.jobs.reduce((a, j) => (j.finish && j.finish > a ? j.finish : a), 0);
  const unknown = q.jobs.some((j) => !j.finish && !j.late);
  fill('ov-heavy', h('h2', {}, `Heavy jobs (${q.jobs.length})`),
    h('div', { class: 'dim' }, q.freeGb != null ? `${q.freeGb.toFixed(0)} GB free, ` : '', `${q.cores} cores; shared jobs keep ${q.keepGb} GB free`,
      q.jobs.length ? ` · the queue empties ${unknown ? 'at a time not known' : `~${clock(last)}`}` : ''),
    jobs.length ? jobs : none('the queue is empty'),
    q.ended.length ? [h('h3', {}, 'Ended by their watch (24 h)'), h('ul', {}, q.ended.map((e) => h('li', {}, `${e.what} in ${e.root}, ${ago(e.end)} ago after ${mins(e.wall || 0)}: ${e.ended}`)))] : '');
}

function sessions() {
  const ss = snap.sessions;
  const one = (s) => h('div', { class: 'card' },
    h('div', { class: 'top' }, h('b', {}, s.agent), now() - s.last < ACTIVE ? chip('active', 'done') : chip(`idle ${ago(s.last)}`),
      s.issue ? [gh('issues', s.issue), s.issueTitle || ''] : h('span', { class: 'dim' }, s.main ? 'in the main checkout' : s.branch || '')),
    h('div', { class: 'facts' }, h('span', {}, 'in ', h('b', {}, s.folder)), s.branch ? h('span', {}, 'branch ', h('b', {}, s.branch)) : '',
      s.pr ? h('span', {}, gh('pull', s.pr.number), ` ${prState(s.pr)}`) : ''));
  const recent = ss.filter((s) => now() - s.last < 6 * 3600), older = ss.filter((s) => now() - s.last >= 6 * 3600);
  fill('ov-sessions', h('h2', {}, `Sessions (${recent.length} in 6 h, ${ss.length} in 48 h)`),
    recent.length ? recent.map(one) : none('none in the last 6 h'),
    older.length ? h('details', {}, h('summary', {}, `${older.length} older`), older.map(one)) : '');
}

// the clashes over shared files listed; the pairs that only both rebuild data (every rebuilding branch with every
// other) folded into one line
function clashList(cs) {
  const li = (c) => h('li', {}, chip(c.kind, c.kind === 'code' ? 'bad' : ''), `${c.a} × ${c.b}`, c.why ? `: ${c.why}` : '',
    c.files.length ? h('span', { class: 'dim' }, ` [${c.files.join(', ')}${c.more ? ` +${c.more}` : ''}]`) : '');
  const data = cs.filter((c) => c.kind === 'data' && !c.files.length), other = cs.filter((c) => !data.includes(c));
  const who = [...new Set(data.flatMap((c) => [c.a, c.b]))];
  return [other.length ? h('ul', {}, other.map(li)) : '',
    data.length ? h('details', {}, h('summary', {}, `${data.length} pairs only both rebuild data (${who.join(', ')}): one publishes, the others rebase on it`),
      h('ul', {}, data.map(li))) : ''];
}

function board() {
  const b = snap.board;
  const flagCls = { conflict: 'bad', recheck: 'wait', asks: 'info', ready: 'done', stale: '', gone: '', rebuilds: 'wait' };
  const row = (r) => h('div', { class: 'card' },
    h('div', { class: 'top' }, r.issue ? gh('issues', r.issue) : h('b', {}, r.name), h('b', {}, r.issueTitle || r.branch || 'detached'),
      r.pr ? [gh('pull', r.pr.number), chip(prState(r.pr))] : ''),
    h('div', { class: 'facts' }, h('span', {}, 'lane ', h('b', {}, r.lane || '-')), r.agents.length ? h('span', {}, h('b', {}, r.agents.join(', '))) : '',
      h('span', {}, h('b', {}, r.worktree ? r.worktree + (r.main ? ' (main)' : '') : 'remote only')),
      h('span', {}, 'touched ', h('b', {}, ago(r.touched))), h('span', {}, `+${r.ahead}/−${r.behind}`), r.files ? h('span', {}, r.files) : '',
      r.dirty ? h('span', {}, `${r.dirty} dirty`) : ''),
    r.flags.length ? h('div', {}, r.flags.map((f) => chip(f + (f === 'rebuilds' && r.label ? ' (holds the label)' : ''), flagCls[f]))) : '');
  const live = b.rows.filter((r) => !r.flags.some((f) => ['gone', 'missing', 'stale'].includes(f)));
  const rest = b.rows.filter((r) => !live.includes(r));
  const lanes = h('div', { class: 'facts' }, b.lanes.map((l) => h('span', { class: l.over ? 'bad' : '' }, `${l.lane} `,
    h('b', {}, `${l.live.length}/${l.limit}`), l.paused ? ' paused' : '', l.over ? ` over: ${l.live.join(', ')}` : '')));
  const ready = Object.entries(b.ready).map(([lane, v]) => h('details', {}, h('summary', {}, `${lane}: ${v.count} ready`),
    h('ul', {}, v.issues.map((i) => h('li', {}, gh('issues', i.number), ` ${i.milestone} · ${i.title}`)), v.count > v.issues.length ? h('li', { class: 'dim' }, `… and ${v.count - v.issues.length} more`) : '')));
  fill('ov-board', h('h2', {}, 'The board'),
    h('div', { class: 'dim' }, 'Rebuild label: ', b.rebuildLabel.length ? b.rebuildLabel.map((n) => [gh('issues', n), ' ']) : 'nobody'),
    h('h3', {}, 'Lanes (live / limit)'), lanes,
    h('h3', {}, `Branches in flight (${live.length})`), live.map(row),
    rest.length ? h('details', {}, h('summary', {}, `${rest.length} finished, stale or missing`), rest.map(row)) : '',
    h('h3', {}, `Clashes (${b.clashes.length})`),
    b.clashes.length ? clashList(b.clashes) : none('none'),
    h('h3', {}, 'Ready to start'), ready.length ? ready : none('none'),
    b.claimed.length ? h('div', { class: 'dim' }, 'An agent\'s label but no branch: ', b.claimed.map((n) => [gh('issues', n), ' '])) : '');
}

async function load() {
  try {
    const r = await fetch('overview.json', { cache: 'no-store' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    snap = await r.json();
  } catch (e) {
    document.getElementById('status').replaceChildren(h('span', { class: 'bad' }, `No overview (${e.message}): tools/overview.py writes and uploads it.`));
    return;
  }
  repo = snap.repo || repo;
  status();
  heavy();
  sessions();
  board();
  if (!document.querySelector('#ov-waiting h2')) waiting(null);
  waiting(await reviewSets());
  window.overview = snap; // (for the page test)
}

load();
setInterval(load, 60_000);
setInterval(status, 15_000);
