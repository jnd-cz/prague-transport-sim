// The review directory (reviews.html, #288): every review set (reports/review/index.json, built by
// tools/review_sets.py at each deploy), the issue that waits for it, and how many of its findings are
// answered, counted live from the answer store (src/verdicts.js) with the findings read and keyed as review
// mode reads them (src/reviewFindings.js). A set's answers are stored under the line it was opened with,
// so every line's store is read. A kerb list lies in the line's survey data, read by review mode (src/review.js):
// its entry carries the findings' ids and its link opens the line's review mode, which starts on the kerbs.
import { fileFindings, fid, answerOf } from './reviewFindings.js';
import { readLineAnswers } from './verdicts.js';

const $ = (id) => document.getElementById(id);
const esc = (t) => String(t ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
// (a PR's question items are Markdown: bold and code shown plain)
const plain = (t) => esc(String(t).replace(/\*\*|`/g, ''));

// {finding id: record}, the newest record of each over every line's store
export async function answers(lines) {
  const stores = await Promise.all(lines.map((l) => readLineAnswers(`line${l}`)));
  const items = {};
  for (const s of stores) for (const [k, v] of Object.entries(s.items)) if (!items[k] || (v.t || 0) >= (items[k].t || 0)) items[k] = v;
  return { items, online: stores.every((s) => s.available) };
}

// a set's findings and how many are answered (an answer with "unsure" counts, and is shown apart)
export async function count(set, items) {
  let found = set.ids?.map((id) => ({ id }));
  if (!found) {
    const r = await fetch(set.file, { cache: 'no-store' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    found = fileFindings(await r.json(), set.file.split('/').pop()).map((f) => ({ id: fid(f), f }));
  }
  let answered = 0, unsure = 0, noted = 0;
  for (const { id, f } of found) {
    const a = f ? answerOf(f, items[id]) : items[id];
    if (a?.v) { answered++; if (a.v === 'unsure') unsure++; }
    if (a?.note) noted++;
  }
  return { total: found.length, answered, unsure, noted, waiting: found.length - answered };
}

const issueUrl = (repo, n) => `https://github.com/${repo}/issues/${n}`;
const name = (set) => set.title || set.file.split('/').pop().replace(/\.json$/, '').replace(/-/g, ' ');

function setRow(set) {
  const c = set.c;
  const links = set.lines.length
    ? set.lines.map((l) => `<a href="index.html?line=${encodeURIComponent(l)}&review${set.ids ? '' : `=${encodeURIComponent(set.file)}`}${c && c.waiting ? '&todo' : ''}">line ${esc(l)}</a>`).join('')
    : '<span class="bad">no line known: open it from its issue</span>';
  const counts = set.error ? `<span class="bad">${esc(set.error)}</span>`
    : `<span class="wait">${c.waiting} waiting</span> · <span class="done">${c.answered} answered</span>${c.unsure ? ` (<span class="unsure">${c.unsure} unsure</span>)` : ''}`;
  const bar = set.error || !c.total ? '' : `<div class="bar" title="${c.answered} of ${c.total}">`
    + `<i style="width:${(100 * (c.answered - c.unsure)) / c.total}%;background:var(--done)"></i>`
    + `<i style="width:${(100 * c.unsure) / c.total}%;background:var(--unsure)"></i></div>`;
  const notes = [set.unknown?.length ? `<span class="bad">unknown: ${set.unknown.map(esc).join(', ')}</span>` : '',
    set.waitsFor !== set.issue && set.issue ? `filed under #${set.issue}, which was closed into #${set.waitsFor}` : '',
    c?.noted ? `${c.noted} with a note` : ''].filter(Boolean).join(' · ');
  return `<div class="set"><div class="name">${esc(name(set))} <span class="dim">${esc(set.file.split('/').pop())}</span></div>
<div class="counts">${counts}</div><div class="links">${links}</div>${bar}${notes ? `<div class="note dim">${notes}</div>` : ''}</div>`;
}

function issueBlock(repo, n, info, sets) {
  const head = n ? `<a href="${issueUrl(repo, n)}" target="_blank" rel="noopener">#${n}</a> ${esc(info?.title || '')}`
    + (info?.state ? ` <span class="state ${esc(info.state)}">${esc(info.state.toLowerCase())}</span>` : '') : 'No issue known';
  const waiting = sets.reduce((a, s) => a + (s.c?.waiting || 0), 0);
  return `<div class="issue"><h3>${head}${waiting ? ` <span class="dim">${waiting} waiting</span>` : ''}</h3>${sets.map(setRow).join('')}</div>`;
}

function grouped(repo, sets) {
  const by = new Map();
  for (const s of sets) {
    const k = s.waitsFor || 0;
    if (!by.has(k)) by.set(k, { info: s.waitsForInfo, sets: [] });
    by.get(k).sets.push(s);
  }
  return [...by.entries()].sort((a, b) => (b[0] || 0) - (a[0] || 0)).map(([n, g]) => issueBlock(repo, n, g.info, g.sets)).join('');
}

function questions(index) {
  if (!index.questions?.length) return '';
  return `<h2>Questions in pull requests</h2><div class="dim">From the open PRs' descriptions${index.built ? ` at the deploy of ${esc(index.built)}` : ''}; answer them on the PR or in a session.</div>`
    + index.questions.map((q) => `<div class="issue q"><h3><a href="${esc(q.url)}" target="_blank" rel="noopener">PR #${q.pr}</a> ${esc(q.title)}${q.draft ? ' <span class="state">draft</span>' : ''}</h3>`
      + q.sections.map((s) => `<div class="dim">${esc(s.title)}</div><ul>${s.items.map((i) => `<li>${plain(i)}</li>`).join('')}</ul>`).join('') + '</div>').join('');
}

export async function main() {
  let index;
  // (the deploy's time comes from version.json, which every deploy uploads: the index carries none, so an unchanged
  // tree deploys it unchanged, #386; tools/serve.py has no version.json)
  const version = fetch('version.json', { cache: 'no-store' }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  try {
    const r = await fetch('reports/review/index.json', { cache: 'no-store' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    index = await r.json();
  } catch (e) {
    $('status').innerHTML = `No index of the review sets (${esc(e.message)}): <code>python -I tools/review_sets.py</code> builds it; <code>tools/deploy.py</code> does at each deploy.`;
    return;
  }
  const deployed = (await version)?.deployed;
  index.built = typeof deployed === 'string' ? deployed.slice(0, 16).replace('T', ' ') : null;
  const { items, online } = await answers(index.lines);
  const sets = await Promise.all(index.sets.map(async (s) => {
    try { return { ...s, c: await count(s, items) }; } catch (e) { return { ...s, error: e.message }; }
  }));
  // (a set whose issue is closed while findings wait is out of date and is deleted: the user, 2026-11-05)
  const stale = (s) => !s.error && s.c.waiting > 0 && s.waitsForInfo?.state === 'CLOSED';
  const old = sets.filter(stale);
  const waiting = sets.filter((s) => !stale(s) && (s.error || s.c.waiting > 0)), answered = sets.filter((s) => !s.error && s.c.waiting === 0);
  const total = waiting.reduce((a, s) => a + (s.c?.waiting || 0), 0);
  $('status').innerHTML = `${total} finding${total === 1 ? '' : 's'} waiting in ${waiting.length} of ${sets.length} sets · index ${index.built ? `of the deploy of ${esc(index.built)} ` : ''}(${esc(index.commit || '')})`
    + (online ? '' : ' · <span class="bad">the answer store did not answer: counts from this device only</span>');
  $('waiting').innerHTML = (waiting.length ? `<h2>Waiting for answers</h2>${grouped(index.repo, waiting)}` : '<h2>Nothing waiting</h2>')
    + (old.length ? `<h2>Out of date</h2><div class="dim">Their issue is closed while findings wait: these sets are out of date, and their files in <code>reports/review/</code> are to be deleted.</div>${grouped(index.repo, old)}` : '');
  $('questions').innerHTML = questions(index);
  $('answered').innerHTML = answered.length ? `<h2>Answered</h2><details><summary>${answered.length} sets with every finding answered</summary>${grouped(index.repo, answered)}</details>` : '';
  window.reviewIndex = { index, sets, old: old.map((s) => s.file) }; // (for the page test, tools/test_review_index.py)
}

main();
