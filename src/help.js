// Help in the menu (#330): the player's guide from README.md (Czech) or README.en.md (English), one source for
// the repository and the game. Shown is what stands between the two markers; the renderer knows only the
// Markdown those files use: headings, paragraphs, lists with one nested level, tables, bold, italics, code, links.
import { t, getLang, onLangChange } from './i18n.js';

const FILES = { cs: 'README.md', en: 'README.en.md' };
const OPEN = '<!-- help -->', CLOSE = '<!-- /help -->';

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

export function helpPart(md) {
  const a = md.indexOf(OPEN), b = md.indexOf(CLOSE);
  return a < 0 || b < a ? '' : md.slice(a + OPEN.length, b).trim();
}

function inline(s) {
  // code first: nothing inside it is read as Markdown (\u0000 keeps its place through the rest)
  const code = [];
  let h = esc(s).replace(/`([^`]+)`/g, (_, c) => { code.push(c); return `\u0000${code.length - 1}\u0000`; });
  h = h.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/(^|[\s(])\*([^*\s][^*]*)\*/g, '$1<i>$2</i>')
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1'); // (a link within the repository leads nowhere on the site)
  return h.replace(/\u0000(\d+)\u0000/g, (_, i) => `<kbd>${code[+i]}</kbd>`);
}

const cells = (l) => l.trim().replace(/^\||\|$/g, '').split('|').map((c) => inline(c.trim()));

export function renderMarkdown(md) {
  const lines = md.split(/\r?\n/), out = [];
  let i = 0;
  while (i < lines.length) {
    const l = lines[i];
    let m;
    if (!l.trim()) { i++; continue; }
    if ((m = l.match(/^(#{2,4}) (.+)/))) { out.push(`<h${m[1].length}>${inline(m[2])}</h${m[1].length}>`); i++; continue; }
    if (l.startsWith('|')) {
      const head = cells(l);
      i += 2; // (the row of dashes)
      const rows = [];
      while (i < lines.length && lines[i].startsWith('|')) rows.push(cells(lines[i++]));
      out.push(`<table><thead><tr>${head.map((c) => `<th>${c}</th>`).join('')}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table>`);
      continue;
    }
    if (/^- /.test(l)) {
      const items = [];
      while (i < lines.length && (/^- /.test(lines[i]) || /^\s+\S/.test(lines[i]))) {
        if (/^- /.test(lines[i])) items.push(lines[i].slice(2));
        else items[items.length - 1] += ' ' + lines[i].trim();
        i++;
      }
      out.push(`<ul>${items.map((x) => `<li>${inline(x)}</li>`).join('')}</ul>`);
      continue;
    }
    const para = [];
    while (i < lines.length && lines[i].trim() && !/^(#{2,4} |\||- )/.test(lines[i])) para.push(lines[i++].trim());
    out.push(`<p>${inline(para.join(' '))}</p>`);
  }
  return out.join('\n');
}

const seen = {}; // language -> its page, fetched once

async function page(lang) {
  if (!seen[lang]) {
    seen[lang] = fetch(FILES[lang]).then((r) => { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then((md) => renderMarkdown(helpPart(md)));
    seen[lang].catch(() => { delete seen[lang]; }); // (a failed load may be tried again)
  }
  return seen[lang];
}

export function initHelp() {
  const panel = document.getElementById('helpPanel'), body = document.getElementById('helpBody');
  const show = async () => {
    const lang = getLang();
    try {
      const html = await page(lang);
      if (lang === getLang()) body.innerHTML = html;
    } catch { body.textContent = t('help.failed'); }
  };
  const close = () => panel.classList.add('hidden');
  document.getElementById('btnHelp').addEventListener('click', () => {
    panel.classList.remove('hidden');
    panel.firstElementChild.scrollTop = 0;
    show();
  });
  document.getElementById('btnHelpClose').addEventListener('click', close);
  panel.addEventListener('click', (e) => { if (e.target === panel) close(); });
  window.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !panel.classList.contains('hidden')) close(); });
  onLangChange(() => { if (!panel.classList.contains('hidden')) show(); });
}
