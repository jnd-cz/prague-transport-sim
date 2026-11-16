// SPDX-License-Identifier: AGPL-3.0-or-later
// The menu's Vehicles… page (#530): the installed packages with their version, author, licence and their check's
// problems and warnings; install from a .zip, a folder or an address; switch off, remove, update; the curated list.
// onChange: after any change, the menu's model, fleet and livery lists are made again from the registry.
// Submitting to the project (#580): a .zip or its address, checked here as an install checks it (dryCheck), then sent
// to the host's submit.php (tools/submit.php; tools/serve.py locally) with the check's report; tools/submissions.py
// reviews them.
import { t, getLang, onLangChange } from './i18n.js';
import { state, install, installUrl, readZip, setEnabled, remove, newerAt, canInstall, catalogue, dryCheck, fetchEntries } from './packages.js';
import { localUrl } from './localFiles.js';

const el = (tag, { dataset, ...props } = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); Object.assign(e.dataset, dataset); e.append(...kids.filter((k) => k != null)); return e; };
const name = (m) => m?.names?.[getLang()] || m?.names?.en || m?.id || '?';

export function initPackages({ onChange }) {
  const panel = document.getElementById('pkgPanel'), body = document.getElementById('pkgBody');
  let last = [], busy = false;
  const sub = { report: [], msg: null, busy: false, contact: '', note: '', host: false, licence: false, url: '' };
  const changed = () => { onChange(); render(); };
  const run = async (f) => {
    if (busy) return;
    busy = true; render();
    try { last = (await f()) || []; } catch (e) { last = [{ id: null, ok: false, problems: [String(e.message || e)], warnings: [] }]; }
    busy = false;
    changed();
  };

  function render() {
    const lang = getLang(), list = [...state.values()];
    const rows = list.map((s) => {
      const m = s.manifest || {}, lic = m.licence || {};
      const toggle = el('input', { type: 'checkbox', checked: !!s.enabled, title: t('pkg.enabled') });
      toggle.onchange = () => run(async () => { await setEnabled(s.id, toggle.checked); return []; });
      const del = el('button', { textContent: t('pkg.remove'), className: 'pkgBtn' });
      del.onclick = () => { if (confirm(t('pkg.removeAsk', { name: name(m) }))) run(async () => { await remove(s.id); return []; }); };
      const upd = /^https?:/.test(s.source || '') ? el('button', { textContent: t('pkg.update'), className: 'pkgBtn' }) : null;
      if (upd) upd.onclick = () => run(async () => { const v = await newerAt(s.id); return v ? installUrl(s.source) : [{ id: s.id, names: m.names, ok: true, problems: [], warnings: [t('pkg.newest')] }]; });
      const thumb = m.thumbnail && s.enabled && s.ok ? el('img', { src: localUrl(`packages/${s.id}/${m.thumbnail}`), className: 'pkgThumb', alt: '' }) : null;
      return el('div', { className: 'pkgRow' + (s.ok ? '' : ' bad'), dataset: { id: s.id } }, thumb,
        el('div', { className: 'pkgMain' },
          el('div', {}, el('b', { textContent: name(m) }), ` ${m.version || ''} · ${t('pkg.kind.' + m.kind)} · `, el('code', { textContent: s.id })),
          m.description ? el('div', { className: 'dim', textContent: m.description[lang] || m.description.en || '' }) : null,
          el('div', { className: 'dim', textContent: `${(lic.authors || []).join(', ')} · ${lic.spdx || ''}${lic.credit ? ' · ' + lic.credit : ''}` }),
          ...(s.problems || []).map((p) => el('div', { className: 'pkgProblem', textContent: '✕ ' + p })),
          ...(s.warnings || []).map((w) => el('div', { className: 'pkgWarn', textContent: '! ' + w }))),
        el('label', { className: 'pkgCtl' }, toggle, ' ', t('pkg.enabled')), upd, del);
    });
    const file = el('input', { type: 'file', accept: '.zip,application/zip', id: 'pkgZip' });
    file.onchange = () => file.files[0] && run(async () => install(await readZip(await file.files[0].arrayBuffer()), 'file'));
    const folder = el('input', { type: 'file', id: 'pkgFolder', webkitdirectory: true, multiple: true });
    folder.onchange = () => folder.files.length && run(async () => {
      // (the paths below the folder picked: its own name is the first part)
      const entries = new Map();
      for (const f of folder.files) entries.set(f.webkitRelativePath.split('/').slice(1).join('/'), new Uint8Array(await f.arrayBuffer()));
      return install(entries, 'folder');
    });
    const url = el('input', { type: 'url', id: 'pkgUrl', placeholder: 'https://…/package.json' });
    const go = el('button', { textContent: t('pkg.installUrl'), className: 'pkgBtn', id: 'pkgUrlGo' });
    go.onclick = () => url.value && run(() => installUrl(url.value.trim()));
    const report = last.map((r) => el('div', { className: r.ok ? 'pkgOk' : 'pkgProblem' },
      `${r.ok ? '✓' : '✕'} ${name({ names: r.names, id: r.id })}: ${r.ok ? t(r.replaced ? 'pkg.updated' : 'pkg.installed', { v: r.replaced }) : t('pkg.refused')}`,
      ...[...(r.problems || []), ...(r.warnings || [])].map((p) => el('div', { className: 'dim', textContent: p }))));
    body.replaceChildren(...[
      el('h2', { textContent: t('pkg.title') }),
      el('p', { className: 'dim', textContent: t('pkg.about') }),
      ...(canInstall() ? [
        el('div', { className: 'pkgInstall' }, el('label', {}, t('pkg.fromZip'), ' ', file), el('label', {}, t('pkg.fromFolder'), ' ', folder)),
        el('div', { className: 'pkgInstall' }, url, go),
      ] : [el('p', { className: 'pkgProblem', textContent: t('pkg.noStore') })]),
      busy ? el('p', { textContent: t('pkg.busy') }) : null,
      el('div', { id: 'pkgReport' }, ...report),
      el('h3', { textContent: t('pkg.installedList') }),
      rows.length ? el('div', { id: 'pkgList' }, ...rows) : el('p', { className: 'dim', textContent: t('pkg.none') }),
      el('h3', { textContent: t('pkg.catalogue') }),
      el('div', { id: 'pkgCatalogue' }, el('p', { className: 'dim', textContent: '…' })),
      submitForm()].filter(Boolean));
    catalogue().then((c) => {
      const box = document.getElementById('pkgCatalogue');
      if (!box) return;
      box.replaceChildren(...(c.length ? c.map((x) => {
        const b = el('button', { textContent: state.has(x.id) ? t('pkg.have') : t('pkg.install'), className: 'pkgBtn', disabled: state.has(x.id) || !canInstall() });
        b.onclick = () => run(() => installUrl(x.url));
        return el('div', { className: 'pkgRow' }, el('div', { className: 'pkgMain' }, el('b', { textContent: name(x) }), ` · ${x.author || ''} · ${x.licence || ''} · `,
          x.home ? el('a', { href: x.home, target: '_blank', rel: 'noopener', textContent: new URL(x.home).host }) : null), b);
      }) : [el('p', { className: 'dim', textContent: t('pkg.catalogueEmpty') })]));
    });
  }

  // the submission form; its fields keep what was typed across the page's redraws
  function submitForm() {
    const zip = el('input', { type: 'file', accept: '.zip,application/zip', id: 'subZip' });
    const url = el('input', { type: 'url', id: 'subUrl', placeholder: 'https://…/package.json', value: sub.url });
    url.oninput = () => { sub.url = url.value; };
    const contact = el('input', { type: 'text', id: 'subContact', maxLength: 200, value: sub.contact, placeholder: t('sub.contact') });
    contact.oninput = () => { sub.contact = contact.value; };
    const note = el('textarea', { id: 'subNote', maxLength: 2000, rows: 2, value: sub.note, placeholder: t('sub.note') });
    note.oninput = () => { sub.note = note.value; };
    const host = el('input', { type: 'checkbox', id: 'subHost', checked: sub.host });
    host.onchange = () => { sub.host = host.checked; };
    const lic = el('input', { type: 'checkbox', id: 'subLicence', checked: sub.licence });
    lic.onchange = () => { sub.licence = lic.checked; };
    const send = el('button', { textContent: t(sub.busy ? 'sub.checking' : 'sub.send'), className: 'pkgBtn', id: 'subSend', disabled: sub.busy });
    send.onclick = async () => {
      const file = zip.files[0], address = url.value.trim();
      if (!file && !address) { sub.msg = { ok: false, text: t('sub.needSource') }; render(); return; }
      if (!lic.checked) { sub.msg = { ok: false, text: t('sub.needLicence') }; render(); return; }
      sub.busy = true; sub.msg = null; sub.report = []; render();
      try {
        const bytes = file ? new Uint8Array(await file.arrayBuffer()) : null;
        let entries;
        try { entries = bytes ? await readZip(bytes.buffer) : await fetchEntries(address); }
        catch (e) { throw new Error(bytes ? String(e.message || e) : t('sub.unreadable', { why: String(e.message || e) })); }
        sub.report = await dryCheck(entries);
        if (sub.report.some((r) => !r.ok)) { sub.msg = { ok: false, text: t('sub.refused') }; return; }
        const meta = {
          schema: 1, url: file ? null : address, contact: sub.contact.trim() || null, note: sub.note.trim() || null,
          host: host.checked, licence: true, lang: getLang(), game: window.deployVersion?.commit || null,
          packages: sub.report.map((r) => ({ id: r.id, version: r.manifest.version, kind: r.manifest.kind, names: r.manifest.names,
            authors: r.manifest.licence?.authors || [], licence: r.manifest.licence?.spdx || null, warnings: r.warnings || [], fit: r.fit || null })),
        };
        const form = new FormData();
        form.append('meta', JSON.stringify(meta));
        if (bytes) form.append('pack', new Blob([bytes], { type: 'application/zip' }), 'pack.zip');
        const res = await fetch('submit.php', { method: 'POST', body: form, headers: { 'X-Submit': '1' } });
        const ans = await res.json().catch(() => null);
        sub.msg = res.ok && ans?.id ? { ok: true, text: t('sub.sent', { id: ans.id }), id: ans.id } : { ok: false, text: t('sub.failed', { why: ans?.error || res.status }) };
      } catch (e) {
        sub.msg = { ok: false, text: t('sub.failed', { why: String(e.message || e) }) };
      } finally { sub.busy = false; render(); }
    };
    const report = sub.report.map((r) => el('div', { className: r.ok ? 'pkgOk' : 'pkgProblem' }, `${r.ok ? '✓' : '✕'} ${name({ names: r.names, id: r.id })}`,
      ...[...(r.problems || []), ...(r.warnings || [])].map((p) => el('div', { className: 'dim', textContent: p }))));
    return el('div', { id: 'subForm' },
      el('h3', { textContent: t('sub.title') }),
      el('p', { className: 'dim', textContent: t('sub.about') }),
      el('div', { className: 'pkgInstall' }, el('label', {}, t('sub.zip'), ' ', zip), el('label', {}, t('sub.url')), url),
      el('div', { className: 'pkgInstall' }, contact),
      el('div', { className: 'pkgInstall' }, note),
      el('label', { className: 'subCheck' }, host, ' ', t('sub.host')),
      el('label', { className: 'subCheck' }, lic, ' ', t('sub.licence')),
      el('div', { className: 'pkgInstall' }, send),
      el('div', { id: 'subReport' }, ...report,
        sub.msg ? el('div', { className: sub.msg.ok ? 'pkgOk' : 'pkgProblem', textContent: sub.msg.text, dataset: sub.msg.id ? { id: sub.msg.id } : {} }) : null));
  }

  const close = () => panel.classList.add('hidden');
  document.getElementById('btnVehicles').addEventListener('click', () => { last = []; render(); panel.classList.remove('hidden'); panel.firstElementChild.scrollTop = 0; });
  document.getElementById('btnPkgClose').addEventListener('click', close);
  panel.addEventListener('click', (e) => { if (e.target === panel) close(); });
  window.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !panel.classList.contains('hidden')) close(); });
  onLangChange(() => { if (!panel.classList.contains('hidden')) render(); });
}
