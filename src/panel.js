// SPDX-License-Identifier: AGPL-3.0-or-later
// The driver's panel (#246): car 6921's cab as on the car, in its order and with its plates (the sources control by
// control: docs/research/prazsketramvaje/t3-cab.md), and the game's own layer on it in dark glass (the pedal bar, the
// helper lamps, the info screen, key hints).
// - Desktop: one band round the driver, 240 px high at a 900 px high window and scaled with it: the left wall, the
//   console (the info screen where 6921 has its onboard computer, the speedometer on its pedestal), the panel (the upper
//   tier, the well with the lamp strip and the buttons, the right block) and the right wing with the run's timetable.
//   The head's turn (Q / E) slides it; the game's block (the pedals, the helper lamps) stays put. Tab folds it to the
//   compact strip (remembered).
// - Phone: a compact strip (the dial, the ammeter, the lamp strip, the helper lamps, the pedals) no taller than the
//   dashboard was, and a sheet with the panel drawn at a size a thumb can hit, a tab per part of the cab.
// A control works by sending the game's key, as src/touch.js does (one control path in src/main.js); the controls the
// game doesn't simulate yet are drawn and inert (#640).
import { t, getLang, onLangChange } from './i18n.js';
import { TR37_SPEC } from './tr37.js';
import { fmtTime } from './game.js';

const $ = (id) => document.getElementById(id);
const px = (n) => `${n}px`;
const store = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch { /* (no storage) */ } return null; };
const FOLD_KEY = 'tram-panel-fold';

// The controls: the plate in each language, works in the game (true), drawn only (false, #640) or the game's own ('aid'),
// the source, and what it does in each language
const C = {
  myci: { cs: 'Mycí stroj', en: 'Washing plant', sim: false, src: 'ČKD ckd03 p. 14',
    en_: 'Washing-plant passage: the contactors close with no line voltage, and the drive pedal releases the shoe brakes.',
    cs_: 'Průjezd mycím strojem: stykače sepnou bez napětí v troleji, jízdní pedál uvolní čelisťové brzdy.' },
  // (named as the drivers call it: the user, 2026-11-18, "rename the 'Bezpečnostní spínač' to 'Záchranná brzda'")
  bezp: { cs: 'Záchranná<br>brzda', en: 'Emergency<br>brake', sim: true, src: 'ckd24 § 5.3; DPP',
    en_: 'Emergency brake: drops the safety relay; all track brakes and full shoe brakes, the bell rings.',
    cs_: 'Záchranná brzda: odpadne bezpečnostní relé, všechny kolejnicové a plné čelisťové brzdy, zvoní zvonek.' },
  havar: { cs: 'Havarijní<br>pojezd', en: 'Emergency<br>drive', sim: false, src: 'DPP textbook p. 8',
    en_: "Emergency drive: cuts this car's 600 V equipment so the coupled car can move it.",
    cs_: 'Havarijní pojezd: odpojí výzbroj 600 V tohoto vozu, aby jej mohl odsunout spřažený vůz.' },
  couv: { cs: 'Přepínač<br>couvání', en: 'Reversing<br>switch', sim: false, src: 'DPP textbook p. 8',
    en_: 'Hands the driving to the rear auxiliary station.', cs_: 'Předá řízení na zadní pomocné stanoviště.' },
  napeti: { cs: 'Napětí<br>v troleji', en: 'Line<br>voltage', sim: true, src: 'ckd03 p. 9',
    en_: 'Glow lamp: lit while the overhead wire has voltage. The T3 has no line voltmeter.',
    cs_: 'Doutnavka: svítí, když je v troleji napětí. T3 nemá voltmetr trakčního napětí.' },
  nevyst: { cs: 'Nevystu-<br>povat', en: 'Do not<br>alight', sim: true, src: 'ckd03 p. 10',
    en_: 'Buzzers at all doors while held; closing all doors needs it first. In the game D does both.',
    cs_: 'Bzučáky u všech dveří, dokud je stisknuto; zavření všech dveří jej vyžaduje. Ve hře obojí udělá D.' },
  dvere1: { cs: 'Dveře I', en: 'Doors I', sim: false, src: 'ckd24 § 7.1', en_: 'The front door alone.', cs_: 'Jen přední dveře.' },
  dvere2: { cs: 'Dveře II', en: 'Doors II', sim: true, src: 'ckd24 § 7.1',
    en_: 'All doors: open, or close after the warning.', cs_: 'Všechny dveře: otevřít, nebo zavřít po výstraze.' },
  houk: { cs: 'Světelná<br>houkačka', en: 'Light<br>horn', sim: true, src: 'schema TSH',
    en_: 'Light horn: the headlights flash while held.', cs_: 'Světelná houkačka: světlomety blikají, dokud je stisknuto.' },
  zvonek: { cs: 'Zvonek', en: 'Bell', sim: true, src: 'ckd24 § 7.3', en_: 'The warning bell.', cs_: 'Výstražný zvonek.' },
  svetl: { cs: 'Světlomety', en: 'Headlights', sim: true, src: 'ckd02 item 66',
    en_: 'Headlights: dipped / high beam.', cs_: 'Světlomety: tlumená / dálková.' },
  smer: { cs: 'Směr', en: 'Indicators', sim: true, src: 'ckd02 item 65',
    en_: 'Indicators left / right: press its side.', cs_: 'Směrová světla vlevo / vpravo: stiskněte stranu.' },
  vypinac: { cs: 'Vypínač<br>řízení', en: 'Control<br>switch', sim: false, src: 'ckd03 B3',
    en_: 'Control switch 0–1–2: 2 starts the motor-generator and springs back to 1.',
    cs_: 'Vypínač řízení 0–1–2: poloha 2 spustí motorgenerátor a vrátí se do 1.' },
  funkce: { cs: 'Funkce ČB', en: 'Shoe brake<br>release', sim: false, src: 'DPP textbook p. 19',
    en_: 'Releases the shoe brakes with no line voltage (a DPP fitting).', cs_: 'Uvolní čelisťové brzdy bez napětí v troleji (úprava DPP).' },
  bzucak: { cs: 'Bzučák', en: 'Buzzer', sim: false, src: 'ckd24 § 7.4',
    en_: 'The buzzer between coupled cars; it also sounds by itself with no line voltage.',
    cs_: 'Bzučák mezi spřaženými vozy; sám zazní i bez napětí v troleji.' },
  sterace: { cs: 'Stěrače', en: 'Wipers', sim: false, src: 'schema VS', en_: 'Wipers.', cs_: 'Stěrače.' },
  osvetl: { cs: 'Osvětlení', en: 'Lights', sim: false, src: 'DPP textbook p. 7',
    en_: 'Outside lights, day / night.', cs_: 'Vnější osvětlení, den / noc.' },
  vyhybka: { cs: 'Výhybka', en: 'Switch', sim: true, src: 'ckd24 § 8.2',
    en_: 'Switch button: current through the overhead contact with the accelerator at 30 or under.',
    cs_: 'Tlačítko výhybky: proud přes trolejový kontakt při zrychlovači do 30.' },
  vystr: { cs: 'Světelná<br>výstraha', en: 'Hazard<br>lights', sim: true, src: 'a later fitting',
    en_: 'Hazard lights.', cs_: 'Výstražná světla.' },
  nouz: { cs: 'Nouzové<br>osvětlení', en: 'Emergency<br>lighting', sim: false, src: 'ckd03 item 6',
    en_: 'Emergency lighting over the doors.', cs_: 'Nouzové osvětlení nad dveřmi.' },
  topzrc: { cs: 'Topení<br>zrcátka', en: 'Mirror<br>heating', sim: false, src: 'ckd02 item 99', en_: 'Mirror heating.', cs_: 'Topení zrcátek.' },
  zarivky: { cs: 'Zářivkové<br>osvětlení', en: 'Saloon<br>lighting', sim: false, src: 'ckd24 § 6.4',
    en_: 'Saloon fluorescent lighting, half the tubes switchable.', cs_: 'Zářivkové osvětlení salonu, polovina trubic vypínatelná.' },
  prepos: { cs: 'Přepínač<br>osvětlení', en: 'Lighting<br>polarity', sim: false, src: 'ckd24 § 6.4; DPP p. 7',
    en_: 'Polarity of the fluorescent tubes: turned at every terminus.', cs_: 'Polarita zářivek: přepíná se na každé konečné.' },
  revers: { cs: 'Směrový přepínač', en: 'Reverser', sim: false, src: 'DPP textbook p. 4',
    en_: 'Reverser, set with the universal crank: forward / 0 / reverse. The game drives forward only.',
    cs_: 'Směrový přepínač, ovládaný univerzální klikou: vpřed / 0 / vzad. Hra jezdí jen vpřed.' },
  kalor: { cs: 'Kalorifer', en: 'Cab heater', sim: true, src: 'ckd03 item 13; DPP p. 8',
    en_: 'Cab heater: 0 off, 1 fan, 2 half, 3 full (also the windscreen).', cs_: 'Kalorifer: 0 vypnuto, 1 ventilátor, 2 poloviční, 3 plný (i čelní sklo).' },
  salon: { cs: 'Topení', en: 'Saloon<br>heating', sim: true, src: 'ckd24 § 6.2', q: true,
    en_: 'Saloon heating 0 – ½ – 1. Its place in the cab is a guess.', cs_: 'Topení salonu 0 – ½ – 1. Jeho místo v kabině je odhad.' },
  vyptop: { cs: 'Vypínač<br>topení', en: 'Heating<br>cut-out', sim: true, src: 'DPP textbook p. 6',
    en_: "Heating cut-out: held while passing a contact, so the heaters' current does not set the switch.",
    cs_: 'Vypínač topení: držet při průjezdu kontaktem, aby proud topení nepřestavil výhybku.' },
  pisek: { cs: 'Pískování', en: 'Sand', sim: true, src: 'DPP textbook p. 6', q: true,
    en_: 'Sanding lever. Its place in the cab is a guess.', cs_: 'Páka pískování. Její místo v kabině je odhad.' },
  speedo: { cs: 'Rychloměr', en: 'Speedometer', sim: true, src: 'photo of 6921',
    en_: 'Speedometer 0–80 km/h with the odometer. The red mark is the limit (assist).',
    cs_: 'Rychloměr 0–80 km/h s počítadlem. Červená značka je omezení rychlosti (asistence).' },
  amp: { cs: 'Ampérmetr', en: 'Ammeter', sim: true, src: 'ckd02 items 47–48',
    en_: 'Ammeter 0–600 A, drive and brake alike.', cs_: 'Ampérmetr 0–600 A, pro jízdu i brzdu.' },
  volt: { cs: 'Voltmetr', en: 'Voltmeter', sim: true, src: 'ckd02 item 49',
    en_: 'Battery voltmeter 0–40 V: about 26 V standing, 28 V charging.', cs_: 'Voltmetr baterie 0–40 V: asi 26 V v klidu, 28 V při nabíjení.' },
  lstrip: { cs: 'Kontrolky', en: 'Lamps', sim: true, src: 'ckd24 § 7.2–7.7',
    en_: 'Indicators (green), EXIT (green) lit by a passenger\'s stop request until the doors open, DOORS green when all are closed, BRAKES I / II / TRAIN red while the shoe brakes are on, ACCELERATOR orange while its resistors are in, mirror heating.',
    cs_: 'Směrovky (zelené), VÝSTUP (zelená) svítí po znamení řidiči od cestujícího do otevření dveří, DVEŘE zelená při všech zavřených, BRZDY I / II / VLAK červené při zabrzděných čelisťových brzdách, ZRYCHLOVAČ oranžová při zařazených odporech, topení zrcátek.' },
  pedals: { cs: 'Pedály', en: 'Pedals', sim: 'aid', src: '#221',
    en_: 'The pedals on the floor: drive above, brake below, P parked; beside them the accelerator 1–99.',
    cs_: 'Pedály na podlaze: jízda nahoře, brzda dole, P zajištěno; vedle zrychlovač 1–99.' },
  alamps: { cs: 'Pomůcky', en: 'Helpers', sim: 'aid', src: '#246',
    en_: 'Helper lamps, shown with the assist option.', cs_: 'Pomocné kontrolky, s asistencí.' },
  term: { cs: 'Palubní počítač', en: 'Onboard computer', sim: 'aid', src: 'photo of 6921',
    en_: "The game's info screen, where 6921 has its onboard computer.", cs_: 'Informační obrazovka hry, kde má 6921 palubní počítač.' },
  tt: { cs: 'Jízdní řád', en: 'Timetable', sim: 'aid', src: 'photo of 6921',
    en_: "The run's timetable, the next stop marked.", cs_: 'Jízdní řád pořadí, příští zastávka vyznačena.' },
};
// the game's key for a control (shown on it with the assist option); held: the key is held while the control is
const KEYS = { bezp: ['Space', ' ', true], nevyst: ['D', 'd'], dvere2: ['D', 'd'], houk: ['L', 'l', true], zvonek: ['B', 'b'],
  svetl: ['⇧L', 'L'], smer: [', .'], vyhybka: ['Y', 'y', true], vystr: ['/', '/'], kalor: ['K', 'k'], salon: ['H', 'h'],
  vyptop: ['C', 'c', true], pisek: ['A', 'a', true] };
// the lamp strip, left to right (6921's "ED – OPRAVNY" plate): [lamp, cs, en, the LED's shape]. V is the stop request,
// labelled as some cars have it, the first brake lamp too (the user, 2026-11-17: "the V led sign is for Výstup, some
// trams have this labeled and we can have it too", "The first red brzda I would label 'Brzda I'")
const STRIP = [['L', 'Směr vlevo', 'Left', 'arrowL'], ['V', 'Výstup', 'Exit', 'V'], ['D', 'Dveře', 'Doors', 'doors'], ['B1', 'Brzda I', 'Brake I', 'brake'],
  ['B2', 'Brzdy II', 'Brakes II', 'brake'], ['BV', 'Vlak', 'Train', 'brake'], ['Z', 'Zrychlovač', 'Accelerator', 'dice5'],
  ['T', 'Topení zrcátka', 'Mirror heat', 'T'], ['R', 'Směr vpravo', 'Right', 'arrowR']];
// the helper lamps (the game's): [key, colour]
const ALAMPS = [['speed', 'red'], ['doors', 'red'], ['current', 'green'], ['ready', 'green'], ['slip', 'red'], ['track', 'amber'],
  ['sand', 'blue'], ['deadman', 'red']];

// ------------------------------------------------------------------ drawing the parts (HTML / SVG strings)
const lab = (id) => C[id][getLang() === 'cs' ? 'cs' : 'en'];
// a control: btn | rot | tog | cam | glow, on a plate (ch chrome, r red letters, y the yellow sticker, yr red on yellow)
function ctl(id, x, y, kind, o = {}) {
  const c = C[id], k = KEYS[id];
  let inner = '';
  if (kind === 'btn') inner = `<span class="bezel"><i class="cap ${o.color || 'black'}"></i></span>`;
  if (kind === 'rot') inner = `<span class="bezel">${POS[id] ? marks(id) : ''}<i class="knob ${o.color || ''}" data-k="${id}"></i></span>`;
  if (kind === 'tog') inner = `<span class="tog"><i class="lever" data-k="${id}"></i></span>`;
  if (kind === 'glow') inner = '<span class="glow"><i></i></span>';
  if (kind === 'cam') inner = `<span class="cam"><span class="marks">${o.marks === false ? '' : camMarks()}</span><i class="handle" data-k="${id}"></i></span>`;
  const cls = ['ctl', kind, c.sim === true ? '' : 'inert'].join(' ');
  return `<div class="${cls}" data-c="${id}" style="left:${px(x)};top:${px(y)}${o.fs ? `;font-size:${o.fs}px` : ''}">` +
    `<span class="plate ${o.plate || ''}" data-lab="${id}">${lab(id)}</span>${inner}${k && c.sim === true ? `<i class="kb">${k[0]}</i>` : ''}${c.q ? '<i class="q">?</i>' : ''}</div>`;
}
// 6921's edgewise meters, flat as from straight above (the user's photo, 2026-11-17: "draw them as rectangles rather
// than curved surface from perspective ... the needle comes from the right side"): a black frame, the scale plate under
// the strip with the calibration stamp, the figures left of the ticks (on a narrow plate in their place), the pointer's
// blade coming in from the right.
// The scales are the photo's: a tick every 20 A, a long one every 100 A, figures every 200 A; a tick every 2 V, figures
// every 10 V. Compact strips leave out the short ticks and the strip.
const SCALE = { amp: [600, 20, 100, 200, 'A', '- - -11- 2002'], volt: [40, 2, 10, 10, 'V', '- - -12- 2002'] };
function meter(id, x, y, w, h, fig = 9, dense = true) {
  const [max, minor, long, step, unit, stamp] = SCALE[id], f = (n) => +n.toFixed(2);
  const b = Math.max(3, Math.round(w * 0.07)), wx = b + 2.5, wy = b + 2.5, ww = w - 2 * wx, wh = h - 2 * wy;
  const xr = wx + ww * (dense ? 0.66 : 0.74), xl = xr - ww * 0.27;
  // a figure stands left of its mark where the plate has room for the widest, else over its mark, in its place (the phone's
  // strips: their ammeter's 600 ran onto the frame, the user, 2026-11-18, "perhaps put it on top of the mark when running
  // short on space", #691; above its mark it touched the next one). Its width at 0.6 em a digit: --f-label's Barlow
  // Condensed is not loaded, so a phone draws Roboto, 0.56 em.
  const fw = String(max).length * fig * 0.6, over = fw > xl - wx - 0.5, fx = over ? Math.min(xr - ww * 0.105, wx + ww - fw / 2 - 0.5) : xl;
  const sh = dense ? wh * 0.1 : 0, y0 = wy + wh - fig * 0.6 - 1.5, y1 = wy + sh + fig * 0.5 + 1.5, at = (v) => y0 - (v / max) * (y0 - y1);
  let s = `<svg viewBox="0 0 ${w} ${h}"><rect class="fr" width="${w}" height="${h}" rx="3"/>` +
    `<rect class="rim" x="${b}" y="${b}" width="${f(w - 2 * b)}" height="${f(h - 2 * b)}" rx="1.5"/>` +
    `<rect class="pl" x="${wx}" y="${wy}" width="${f(ww)}" height="${f(wh)}"/><rect class="gap" x="${f(wx + ww * 0.93)}" y="${wy}" width="${f(ww * 0.07)}" height="${f(wh)}"/>`;
  if (dense) s += `<rect class="strip" x="${wx}" y="${wy}" width="${f(ww)}" height="${f(sh)}"/><rect class="edge" x="${wx}" y="${f(wy + sh)}" width="${f(ww)}" height=".7"/>` +
    `<text class="stamp" x="${f(wx + ww * 0.45)}" y="${f(wy + sh * 0.68)}" font-size="${f(sh * 0.5)}">${stamp}</text>`;
  for (let v = 0; v <= max + 1e-6; v += dense ? minor : long) {
    const big = Math.abs(v / long - Math.round(v / long)) < 1e-6, ty = f(at(v));
    // (the compact ones leave out the 0: their unit letter stands there)
    const num = Math.abs(v / step - Math.round(v / step)) < 1e-6 && (dense || v);
    if (num && over) { s += `<text class="fig over" x="${f(fx)}" y="${ty}" font-size="${fig}">${v}</text>`; continue; }
    s += big ? `<rect class="tk" x="${f(xr - ww * 0.24)}" y="${f(ty - 0.6)}" width="${f(ww * 0.27)}" height="1.2"/>`
      : `<rect class="tk" x="${f(xr - ww * 0.1)}" y="${f(ty - 0.35)}" width="${f(ww * 0.1)}" height=".7"/>`;
    if (num) s += `<text class="fig" x="${f(xl)}" y="${ty}" font-size="${fig}">${v}</text>`;
  }
  s += `<text class="unit" x="${f(wx + ww * 0.06)}" y="${f(y0)}" font-size="${f(fig * 1.45)}">${unit}</text>`;
  // the pointer at 0, moved up by update() (data-r: the scale's length)
  s += `<g class="ptr" data-m="${id}" data-r="${f(y0 - y1)}"><rect x="${f(xr - ww * 0.13)}" y="${f(y0 - 0.45)}" width="${f(ww * 0.19)}" height=".9"/>` +
    `<rect x="${f(xr + ww * 0.05)}" y="${f(y0 - 1)}" width="${f(wx + ww - xr - ww * 0.05)}" height="2" rx=".4"/></g></svg>`;
  return `<div class="meter" data-c="${id}" style="left:${px(x)};top:${px(y)};width:${px(w)};height:${px(h)}">${s}</div>`;
}
// (the arrows green and shorter, the brake lamp's bars beside its ring as on 6921: the user, 2026-11-17, "The arrows for
// left and right should be green leds I think, can be a bit shorter", "the led symbol parts of |O| can be alongside each
// other"). V is the open door, two strokes apart, green (the user, 2026-11-18, after a photo of a T3P's panel: "the V (or
// open door symbol, the two lines are not touching) ... It's green").
const LED = {
  arrowL: (l) => `<svg viewBox="0 0 24 14"><path class="off" data-l="${l}" d="M1 7 L9 1 L9 4.5 L23 4.5 L23 9.5 L9 9.5 L9 13 Z"/></svg>`,
  arrowR: (l) => `<svg viewBox="0 0 24 14"><path class="off" data-l="${l}" d="M23 7 L15 1 L15 4.5 L1 4.5 L1 9.5 L15 9.5 L15 13 Z"/></svg>`,
  V: (l) => `<svg viewBox="0 0 16 14"><path class="off" data-l="${l}" d="M1 1 H4.4 L7.2 13 H3.8 Z M15 1 H11.6 L8.8 13 H12.2 Z"/></svg>`,
  doors: (l) => `<svg viewBox="0 0 16 14"><rect class="off" data-l="${l}" x="2" y="1" width="4.5" height="12"/><rect class="off" data-l="${l}" x="9.5" y="1" width="4.5" height="12"/></svg>`,
  brake: (l) => `<svg viewBox="0 0 20 14"><rect class="off" data-l="${l}" x="1" y="2" width="3.4" height="10" rx=".8"/><circle class="off" data-l="${l}" cx="10" cy="7" r="4.6"/><rect class="off" data-l="${l}" x="15.6" y="2" width="3.4" height="10" rx=".8"/></svg>`,
  // the accelerator lamp: five LEDs as a die's five (the user, 2026-11-17)
  dice5: (l) => `<svg viewBox="0 0 14 14">${[[2.6, 2.6], [11.4, 2.6], [7, 7], [2.6, 11.4], [11.4, 11.4]].map(([x, y]) => `<circle class="off" data-l="${l}" cx="${x}" cy="${y}" r="2.1"/>`).join('')}</svg>`,
  T: (l) => `<svg viewBox="0 0 14 14"><path class="off" data-l="${l}" d="M1 1 H13 V4 H8.6 V13 H5.4 V4 H1 Z"/></svg>`,
};
function lampStrip(x, y, w, fs, labels = true) {
  const cs = getLang() === 'cs';
  return `<div class="lstrip${labels ? '' : ' nolab'}" data-c="lstrip" style="left:${px(x)};top:${px(y)};width:${px(w)};font-size:${fs}px">` +
    STRIP.map(([l, c, e, shape]) => `<div class="it"><span class="lab" data-strip="${l}">${cs ? c : e}</span><span class="led">${LED[shape](l)}</span></div>`).join('') +
    '<span class="ed">ED – OPRAVNY</span></div>';
}
// 6921's speedometer: a black face, white figures 0-80, the odometer, the limit's red mark (assist)
function speedo(d) {
  let s = `<svg viewBox="-100 -100 200 200" width="${d}" height="${d}">`;
  s += '<circle r="98" fill="#0b0c0c" stroke="#2a2d2c" stroke-width="3"/><circle r="91" fill="#121414"/>';
  const ang = (v) => (-225 + (v / 80) * 270) * Math.PI / 180;
  for (let v = 0; v <= 80; v += 2.5) {
    const big = v % 10 === 0, mid = v % 5 === 0, a = ang(v), r0 = big ? 72 : mid ? 78 : 82;
    s += `<line x1="${(Math.cos(a) * r0).toFixed(1)}" y1="${(Math.sin(a) * r0).toFixed(1)}" x2="${(Math.cos(a) * 88).toFixed(1)}" y2="${(Math.sin(a) * 88).toFixed(1)}" stroke="#f2f2ea" stroke-width="${big ? 3.2 : 1.4}"/>`;
    if (big) s += `<text x="${(Math.cos(a) * 57).toFixed(1)}" y="${(Math.sin(a) * 57 + 6).toFixed(1)}" class="fig">${v}</text>`;
  }
  s += '<text x="0" y="32" class="kmh">km/h</text>';
  s += '<rect x="-29" y="42" width="58" height="16" rx="2" fill="#050505" stroke="#3a3d3c"/><text class="odo" x="0" y="54.5">000000</text>';
  s += '<path class="lim" d="M0,-99 L-7,-86 L7,-86 Z" fill="#ff3b30" stroke="#fff" stroke-width=".8" visibility="hidden"/>';
  return `${s}<path class="ndl" d="M-3.5,8 L0,-80 L3.5,8 Z" fill="#f6f4ea"/><circle r="9" fill="#2a2d2c" stroke="#555"/></svg>`;
}
const crank = (w) => `<svg viewBox="0 0 120 110" width="${w}" height="${(w * 110) / 120}"><rect x="8" y="8" width="104" height="94" rx="6" fill="#d8dbd9" stroke="#555"/>` +
  '<text x="60" y="22" class="fig2">VPŘED</text><text x="22" y="62" class="fig2">0</text><text x="60" y="99" class="fig2">VZAD</text>' +
  '<circle cx="60" cy="58" r="15" fill="#2a2d2c"/><rect x="56" y="32" width="8" height="28" rx="3" fill="#1a1c1b"/><circle cx="60" cy="33" r="5.5" fill="#3a3e3c"/></svg>';
// A rotary switch's positions: the label and the knob's angle there (degrees from 3 o'clock, clockwise as CSS turns it),
// the labels round the knob where its pointer stops (the user, 2026-11-17: "the heater rotary switches (and other rotary
// ones) should be aligned to the position labels, not turn to another angle"). Those without labels on the car stand as
// on the user's photos of 6921 (the user, 2026-11-18: "position the unlabeled knobs according to the reference photos"):
// up off and right on (OFF, ON), as its door switches show: DVEŘE II up with the doors closed, DVEŘE I turned right with
// the front door open and the doors' lamp dark. OSVĚTLENÍ, the outside lights, at DAY, 45° left (DPP textbook, the T3R.P
// pages: "zapnuté vnější osvětlení na „den“ - to je vlevo"; the photos, taken in the evening, have it 45° right; the game
// has no night yet); the saloon's fluorescent lighting at the left, "předvolba" (ibid.). The cams: VYPÍNAČ ŘÍZENÍ's marks
// 0 up, 1 at 45°, 2 right, its handle at 1; PŘEPÍNAČ OSVĚTLENÍ's marks don't show on the photo, its handle stands
// diagonal as there.
const POS = { kalor: [['0', 135], ['1', 105], ['2', 75], ['3', 45]], salon: [['0', 135], ['½', 90], ['1', 45]] };
const OFF = -90, ON = 0, CAM = [-90, -45, 0], DAY = -135, PRESEL = 180;
// a cam's marks round its handle, 42 % of the plate from its middle (clear of the handle's tip)
const camMarks = () => CAM.map((a, i) => {
  const r = a * Math.PI / 180;
  return `<b style="left:${(50 + 42 * Math.cos(r)).toFixed(1)}%;top:${(50 + 42 * Math.sin(r)).toFixed(1)}%">${i}</b>`;
}).join('');
// the labels round a knob, 2.3 em from its middle (in its bezel)
const marks = (id) => POS[id].map(([m, a]) => {
  const at = (f) => `calc(50% + ${(2.3 * f(a * Math.PI / 180)).toFixed(2)}em)`;
  return `<b class="pos" style="left:${at(Math.cos)};top:${at(Math.sin)}">${m}</b>`;
}).join('');

// The band's sections, x from the screen's middle at the head straight ahead (design px; the band is 240 high)
const H = 240, W0 = 1640, PER_RAD = 850; // the design height and width; the band's slide per radian of the head's turn
const SEC = { wall: [-2600, 1740], console: [-840, 478], panel: [-362, 980], wing: [630, 1740] };
// the sides' last things, band x: the wall's plate of the sanding lever (wallSec, to 1700), the wing's timetable (wingSec,
// to 1300); with the head turned all the way they end before the game's block (slide())
const SIDE_END = { left: SEC.wall[0] + 1700, right: SEC.wing[0] + 1300 };
// the sheet's tabs: a part of a section ([section, x from, x to] in its own x)
const TABS = [['left', 'wall', 880, 1720], ['panel', 'panel', 0, 544], ['right', 'panel', 540, 980], ['wing', 'wing', 560, 1320], ['game']];

function wallSec() {
  return `<div class="wallsurf"></div>
    <div class="sideplate" style="left:900px;top:36px;width:640px;height:178px"></div>
    <div class="crank" data-c="revers" style="left:930px;top:56px">${crank(150)}</div>
    ${ctl('kalor', 1110, 64, 'rot', { plate: 'y', fs: 15 })}
    ${ctl('salon', 1230, 64, 'rot', { fs: 15 })}
    ${ctl('vyptop', 1350, 64, 'btn', { color: 'black', plate: 'y', fs: 15 })}
    <div class="sideplate dark" style="left:1570px;top:26px;width:130px;height:196px"></div>
    ${ctl('pisek', 1592, 44, 'tog', { plate: 'y', fs: 17 })}`;
}
function consoleSec() {
  return `<div class="surface con"></div><div class="sill"></div>
    <div class="terminal" data-c="term" style="left:14px;top:14px;width:250px;height:212px"><div class="bezelT"></div><div class="scr" id="info"></div></div>
    <div class="pedestal" style="left:268px;top:20px;width:202px;height:202px"></div>
    <div class="speedo" data-c="speedo" style="left:276px;top:28px">${speedo(186)}</div>`;
}
const ROW = ['funkce:btn:black:y', 'bzucak:btn:black:yr', 'sterace:rot::', 'osvetl:rot::yr', 'vyhybka:btn:red:', 'vystr:rot:ruby:y', 'nouz:rot::', 'topzrc:rot::y'];
function panelSec() {
  const f = 11;
  return `<div class="surface"></div><div class="sill"></div>
    ${[[8, 100], [970, 24], [536, 40], [760, 30], [960, 128], [700, 96]].map(([x, y]) => `<i class="screw" style="left:${x}px;top:${y}px"></i>`).join('')}
    ${ctl('myci', 10, 10, 'btn', { color: 'black', plate: 'y', fs: f })}
    ${ctl('bezp', 70, 10, 'btn', { color: 'red', plate: 'r', fs: f })}
    ${meter('amp', 128, 6, 72, 108)}
    <div class="slot" style="left:208px;top:16px;width:58px;height:64px"></div>
    ${meter('volt', 274, 6, 72, 108)}
    ${ctl('havar', 354, 10, 'rot', { color: 'red', fs: f })}
    ${ctl('couv', 414, 10, 'rot', { color: 'green', plate: 'r', fs: f })}
    ${ctl('napeti', 474, 10, 'glow', { plate: 'y', fs: f })}
    <div class="well" style="left:8px;top:122px;width:528px;height:118px"></div>
    ${lampStrip(16, 127, 512, 12)}
    ${ctl('svetl', 52, 174, 'tog', { plate: 'y', fs: f })}
    ${['nevyst:btn:red', 'dvere1:rot:', 'dvere2:rot:', 'houk:btn:blue', 'zvonek:btn:green'].map((s, i) => {
      const [id, kind, color] = s.split(':');
      return ctl(id, 116 + i * 64, 168, kind, { color, fs: f });
    }).join('')}
    ${ctl('smer', 436, 174, 'tog', { plate: 'y', fs: f })}
    <div class="rail" style="left:2px;top:229px;width:540px"></div>
    ${ctl('vypinac', 896, 8, 'cam', { plate: 'y', fs: f })}
    ${ROW.map((s, i) => { const [id, kind, color, plate] = s.split(':'); return ctl(id, 552 + i * 53, 160, kind, { color, plate, fs: 10.4 }); }).join('')}`;
}
function wingSec() {
  return `<div class="surface wing"></div><div class="sill"></div>
    ${ctl('zarivky', 600, 40, 'rot', { fs: 14 })}
    ${ctl('prepos', 700, 24, 'cam', { plate: 'y', fs: 13, marks: false })}
    <div class="warnplate" style="left:690px;top:148px;width:130px" data-warn="1"></div>
    <div class="paper" data-c="tt" style="left:880px;top:12px;width:420px;height:212px"><h4><span class="ttLine"></span><span class="ttEnd"></span></h4><table class="tt"></table></div>`;
}
const SECS = { wall: wallSec, console: consoleSec, panel: panelSec, wing: wingSec };
// the game's block: the pedal bar and the helper lamps
// (and the speed while the head is turned: the dial turns away with the band)
const gameBlock = (cls, cw, ch) => `<div class="gm ${cls}" data-c="alamps"><canvas class="pedalcv" width="${cw}" height="${ch}" data-c="pedals"></canvas><div class="spd"><b>0</b> km/h</div>` +
  `<div class="alamps">${ALAMPS.map(([k, c]) => `<div class="alamp ${c}" data-a="${k}"></div>`).join('')}</div></div>`;
// the compact strips: a phone in landscape (and the folded desktop), a phone in portrait
function compactL() {
  return `<div class="surface"></div><div class="sill thin"></div>
    <div class="pedestal" style="left:4px;top:4px;width:80px;height:80px"></div>
    <div class="speedo" data-c="speedo" style="left:7px;top:7px">${speedo(74)}</div>
    ${meter('amp', 90, 5, 36, 78, 8, false)}
    ${lampStrip(132, 5, 270, 8, false)}
    <div class="alamps cmpl" style="left:132px;top:34px;width:270px;height:49px">${ALAMPS.map(([k, c]) => `<div class="alamp ${c}" data-a="${k}"></div>`).join('')}</div>
    <canvas class="pedalcv" width="32" height="78" style="left:408px;top:5px" data-c="pedals"></canvas>
    <div class="handle"><b>▲</b><span class="hl"></span></div>`;
}
function compactP() {
  return `<div class="surface"></div><div class="sill thin"></div>
    <div class="pedestal" style="left:2px;top:6px;width:102px;height:102px"></div>
    <div class="speedo" data-c="speedo" style="left:6px;top:10px">${speedo(94)}</div>
    ${meter('amp', 108, 6, 32, 100, 8, false)}
    ${lampStrip(144, 6, 196, 6.8, false)}
    <div class="alamps cmpl" style="left:144px;top:32px;width:196px;height:74px">${ALAMPS.map(([k, c]) => `<div class="alamp ${c}" data-a="${k}"></div>`).join('')}</div>
    <canvas class="pedalcv" width="34" height="100" style="left:344px;top:6px" data-c="pedals"></canvas>`;
}

// The pedal bar (#221): one axis from the brake pedal's stop (bottom) to the drive pedal's (top), each pedal's steps as
// coloured zones, a marker where the pedal is, P when parked; beside it the accelerator's position (1–99: resistors to
// 75, field stages from 80)
function drawPedals(cv, eq, S) {
  const c = cv.getContext('2d'), W = cv.width, Hh = cv.height, mid = Hh / 2, k = (mid - 4) / S.pedalMax;
  const aw = Math.max(7, Math.round(W * 0.2)), bw = W - aw - 4;
  const y = (a) => mid - a * k; // drive +, brake −
  c.clearRect(0, 0, W, Hh);
  c.fillStyle = '#1e2420'; c.fillRect(0, 0, bw, Hh);
  const band = (a0, a1, col) => { c.fillStyle = col; c.fillRect(2, Math.min(y(a0), y(a1)), bw - 4, Math.abs(y(a1) - y(a0)) - 1); };
  const d = S.driveAngles, b = S.brakeAngles;
  for (let i = 0; i < 5; i++) band(d[i], d[i + 1] ?? S.pedalMax, ['#24502c', '#2c6b37', '#358343', '#3f9b4f', '#4ab35b'][i]);
  for (let i = 0; i < 5; i++) band(-b[i], -(b[i + 1] ?? S.parkAngle), ['#5a4a22', '#6f5420', '#8a5a1c', '#a35a1a', '#bb5418'][i]);
  band(-S.parkAngle, -S.trackAngles[0], '#7a1d18');
  band(-S.trackAngles[0], -S.pedalMax, '#6a2a8a');
  if (Hh > 100) {
    c.font = `600 ${Hh > 160 ? 11 : 9}px ui-monospace, monospace`; c.textAlign = 'center'; c.fillStyle = '#d9e6da';
    for (let i = 0; i < 5; i++) {
      c.fillText(String(i + 1), bw / 2, y((d[i] + (d[i + 1] ?? S.pedalMax)) / 2) + 4);
      c.fillText(String(i + 1), bw / 2, y(-(b[i] + (b[i + 1] ?? S.parkAngle)) / 2) + 4);
    }
    c.fillText(eq.parked ? 'P' : 'p', bw / 2, y(-(S.parkAngle + S.trackAngles[0]) / 2) + 4);
  }
  c.fillStyle = '#59645b'; c.fillRect(2, mid - 0.5, bw - 4, 1);
  // the pedal: drive above, brake below (the parked ratchet holds the brake at its station)
  const a = eq.pedal.drive > 0 ? eq.pedal.drive : -eq.brakeAngle;
  c.fillStyle = eq.parked ? '#ffb0a0' : '#ffffff';
  c.fillRect(0, y(a) - 2, bw, 4);
  // the accelerator
  const ax = W - aw, top = 4, h = Hh - 8;
  c.fillStyle = '#151a17'; c.fillRect(ax, top, aw, h);
  c.fillStyle = eq.p < 75 ? '#d0a030' : '#e0d070';
  const hp = (h * (eq.p - 1)) / 98;
  c.fillRect(ax, top + h - hp, aw, hp);
  c.fillStyle = '#0b0e0c';
  for (const q of [75, 80, 85, 90, 95]) c.fillRect(ax, top + h - (h * (q - 1)) / 98, aw, 1);
}

// The stop request (V): a passenger presses "znamení řidiči" in the saloon some way after the last stop, and the lamp
// stays lit until the doors open (the user, 2026-11-17: "It should be connected to request stop button (znamení
// řidiči)"). At a request stop where somebody gets off (src/game.js: alightFrac, which also makes the stop needed); the
// press 20 m to 60 % of the way from the last stop, the same for a stop on every run (no draw from the game's random).
function requested(game, st, s) {
  if (!st || !st.request || !(st.alightFrac > 0) || st.served) return false;
  const prev = game.stops[st.i - 1], from = prev ? prev.target : 0, k = ((st.i + 1) * 2654435761 >>> 0) / 2 ** 32;
  return s >= from + Math.min(0.6 * (st.target - from), 20 + k * 140);
}

// ------------------------------------------------------------------ the panel
export class Panel {
  constructor() {
    this.dash = $('dash');
    this.look = 0;
    this.fold = store(FOLD_KEY) === '1';
    this.held = {}; // keys held (the momentary controls drawn pressed)
    this.bellT = 0;
    this.speedShown = 0;
    this.build();
    onLangChange(() => { this.relabel(); this.layout(); });
    // the controls drawn pressed while their key is (from the keyboard, the touch buttons or the panel itself)
    window.addEventListener('keydown', (e) => {
      // (Tab in a form, the feedback note's, moves between its fields)
      if (e.key === 'Tab' && document.body.classList.contains('shift') && !e.target.closest?.('input, textarea, select')) {
        e.preventDefault(); this.setFold(!this.fold); return;
      }
      const k = e.key === ' ' ? ' ' : e.key.toLowerCase();
      this.held[k] = true;
      if (k === 'b') this.bellT = performance.now();
    });
    window.addEventListener('keyup', (e) => { this.held[e.key === ' ' ? ' ' : e.key.toLowerCase()] = false; });
    window.addEventListener('blur', () => { this.held = {}; });
    window.addEventListener('resize', () => this.layout());
  }

  build() {
    const sec = (k, html) => `<section class="sec ${k}" style="left:${px(SEC[k][0])};width:${px(SEC[k][1])}">${html}</section>`;
    this.dash.innerHTML = `<div class="pz full"><div class="band">${Object.keys(SEC).map((k) => sec(k, SECS[k]())).join('')}</div>${gameBlock('desk', 62, 208)}</div>
      <div class="cmp cl">${compactL()}</div><div class="cmp cp">${compactP()}</div>`;
    // the sheet: the panel's parts again, at a thumb's size
    const sheet = (this.sheet = document.createElement('div'));
    sheet.id = 'pSheet';
    sheet.innerHTML = `<div class="tabs">${TABS.map(([k]) => `<button data-tab="${k}"></button>`).join('')}<button class="x" data-tab="close">✕</button></div>
      <div class="body">${TABS.map(([k, s, x0, x1]) => (s
        ? `<div class="pane" data-pane="${k}"><div class="slice" style="width:${px(x1 - x0)};height:${px(H)}"><section class="sec ${s}" style="left:${px(-x0)};width:${px(SEC[s][1])}">${SECS[s]()}</section></div></div>`
        : `<div class="pane gamepane" data-pane="${k}">${[['o', 'tb.auto'], ['r', 'tb.park'], ['x', 'tb.iron'], ['f', 'tb.flap'], ['z', 'tb.mirror'], ['m', 'tb.mute'], ['F9', '✉']].map(([key, l]) => `<button data-key="${key}" data-l="${l}"></button>`).join('')}</div>`)).join('')}</div>`;
    document.body.appendChild(sheet);
    // (the sheet's own info screen would be a second #info: the sheet has no console)
    this.tip = document.createElement('div');
    this.tip.id = 'pTip';
    document.body.appendChild(this.tip);
    this.tab = 'panel';
    // the parts updated each time, both copies of each
    const all = (sel) => [...this.dash.querySelectorAll(sel), ...sheet.querySelectorAll(sel)];
    this.el = {
      ndl: all('.ndl'), lim: all('.lim'), odo: all('.odo'), amp: all('[data-m="amp"]'), volt: all('[data-m="volt"]'),
      led: {}, ctl: {}, knob: {}, alamps: all('[data-a]'), pedals: all('.pedalcv'), band: this.dash.querySelector('.band'),
      pz: this.dash.querySelector('.pz'), gm: this.dash.querySelector('.gm.desk'), spd: this.dash.querySelector('.gm.desk .spd b'), tt: all('.tt'), ttLine: all('.ttLine'), ttEnd: all('.ttEnd'), warn: all('[data-warn]'),
    };
    for (const [l] of STRIP) this.el.led[l] = all(`[data-l="${l}"]`);
    for (const id of Object.keys(C)) { this.el.ctl[id] = all(`[data-c="${id}"]`); this.el.knob[id] = all(`[data-k="${id}"]`); }
    this.state = {};
    this.ttKey = '';
    this.wire(this.dash);
    this.wire(sheet);
    sheet.querySelector('.tabs').addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      if (b.dataset.tab === 'close') this.openSheet(false); else this.showTab(b.dataset.tab);
    });
    this.dash.querySelectorAll('.cmp').forEach((c) => c.addEventListener('click', () => {
      if (this.compactBy === 'fold') this.setFold(false); else this.openSheet(!this.sheet.classList.contains('open'));
    }));
    this.relabel();
    this.layout();
  }

  // presses: a control sends its key (held ones until let go); the side a toggle is pressed on picks its way
  wire(root) {
    const send = (type, key) => window.dispatchEvent(new KeyboardEvent(type, { key, shiftKey: key === 'L', bubbles: true }));
    const down = new Map();
    root.addEventListener('pointerdown', (e) => {
      const g = e.target.closest('.gamepane button');
      if (g) { e.preventDefault(); send('keydown', g.dataset.key); send('keyup', g.dataset.key); return; }
      const el = e.target.closest('.ctl, .meter, .lstrip, .speedo, .crank, .terminal, .paper, .gm');
      if (!el || el.closest('.cmp')) return;
      const id = el.dataset.c;
      if (id === 'smer') {
        const r = el.getBoundingClientRect(), k = e.clientX < r.left + r.width / 2 ? ',' : '.';
        e.preventDefault(); send('keydown', k); send('keyup', k); return;
      }
      const k = KEYS[id];
      if (!k || !k[1] || C[id].sim !== true) return;
      if (id === 'nevyst' && document.body.dataset.doors === 'closed') return; // (it only warns: the doors are shut)
      e.preventDefault();
      send('keydown', k[1]);
      if (!k[2]) { send('keyup', k[1]); return; }
      down.set(e.pointerId, k[1]);
      try { el.setPointerCapture(e.pointerId); } catch { /* (gone) */ }
    });
    const up = (e) => { const k = down.get(e.pointerId); if (k === undefined) return; down.delete(e.pointerId); send('keyup', k); };
    root.addEventListener('pointerup', up);
    root.addEventListener('pointercancel', up);
    root.addEventListener('contextmenu', (e) => e.preventDefault());
    // what a control is: on hovering it with a mouse
    root.addEventListener('pointerover', (e) => {
      if (e.pointerType !== 'mouse' || !matchMedia('(hover: hover)').matches) return;
      const el = e.target.closest('[data-c]');
      if (!el) { this.tip.style.display = 'none'; return; }
      this.showTip(el.dataset.c, e);
    });
    root.addEventListener('pointermove', (e) => { if (this.tip.style.display === 'block') this.moveTip(e); });
    root.addEventListener('pointerleave', () => { this.tip.style.display = 'none'; });
  }

  showTip(id, e) {
    const c = C[id];
    if (!c) return;
    const cs = getLang() === 'cs', k = KEYS[id];
    const pill = c.sim === 'aid' ? ['aid', 'panel.aid'] : c.sim ? ['sim', 'panel.sim'] : ['no', 'panel.inert'];
    this.tip.innerHTML = `<div class="nm">${(cs ? c.cs : c.en).replace(/<br>/g, ' ').replace('- ', '')}</div><div class="what">${cs ? c.cs_ : c.en_}</div>` +
      `<div class="meta"><span class="pill ${pill[0]}">${t(pill[1])}</span>${k && c.sim === true ? `<b>${k[0]}</b>` : ''}</div><div class="src">${c.src}</div>`;
    this.tip.style.display = 'block';
    this.moveTip(e);
  }

  moveTip(e) {
    const w = this.tip.offsetWidth, h = this.tip.offsetHeight;
    this.tip.style.left = px(Math.max(8, Math.min(innerWidth - w - 8, e.clientX + 14)));
    this.tip.style.top = px(Math.max(8, e.clientY - h - 12));
  }

  relabel() {
    const cs = getLang() === 'cs';
    const all = (sel) => [...this.dash.querySelectorAll(sel), ...this.sheet.querySelectorAll(sel)];
    for (const p of all('[data-lab]')) p.innerHTML = lab(p.dataset.lab);
    for (const s of all('[data-strip]')) { const it = STRIP.find(([l]) => l === s.dataset.strip); s.textContent = cs ? it[1] : it[2]; }
    for (const a of all('[data-a]')) a.innerText = t(`lamp.${a.dataset.a}`);
    for (const w of this.el.warn) w.textContent = t('panel.terminus');
    for (const b of this.sheet.querySelectorAll('.tabs [data-tab]')) if (b.dataset.tab !== 'close') b.textContent = t(`panel.tab.${b.dataset.tab}`);
    for (const b of this.sheet.querySelectorAll('.gamepane [data-l]')) b.textContent = b.dataset.l.startsWith('tb.') ? t(b.dataset.l) : b.dataset.l;
    this.ttKey = '';
    this.fitted = false;
  }

  // shrinks a plate's letters where its words don't fit its width (the fonts differ by system)
  fit() {
    for (const p of [...this.dash.querySelectorAll('.plate, .lstrip .lab'), ...this.sheet.querySelectorAll('.pane.on .plate')]) {
      if (!p.offsetParent) continue;
      p.style.fontSize = '';
      let f = 1;
      while (p.scrollWidth > p.clientWidth + 0.5 && f > 0.62) { f -= 0.04; p.style.fontSize = `${f.toFixed(2)}em`; }
    }
    this.fitted = true;
  }

  setFold(on) {
    this.fold = on;
    store(FOLD_KEY, on ? '1' : '0');
    this.layout();
  }

  // the scale and the mode: the whole panel, or the compact strip (a phone, Tab, a small window)
  layout() {
    const b = document.body, W = innerWidth, Hh = innerHeight;
    const s = Math.min(Hh / 900, W / W0);
    const small = matchMedia('(max-width: 760px), (max-height: 520px)').matches, touchSmall = b.classList.contains('touch') && small;
    this.compactBy = touchSmall ? 'touch' : this.fold ? 'fold' : s < 0.55 ? 'small' : null;
    const compact = !!this.compactBy, portrait = touchSmall && Hh > W;
    b.classList.toggle('pcompact', compact);
    b.classList.toggle('pportrait', portrait);
    b.classList.toggle('pfold', this.compactBy === 'fold');
    if (touchSmall) b.style.removeProperty('--dashH');
    else b.style.setProperty('--dashH', px(Math.round((compact ? 88 * Math.max(0.8, s) : H * s))));
    this.s = s;
    for (const h of this.dash.querySelectorAll('.hl')) h.textContent = t(this.compactBy === 'fold' ? 'panel.unfold' : 'panel.open');
    this.layoutKey = this.modeKey();
    requestAnimationFrame(() => this.place());
  }

  // what the layout depends on: the window, the on-screen controls (src/touch.js), Tab's fold
  modeKey() { return `${innerWidth}x${innerHeight}:${document.body.classList.contains('touch')}:${this.fold}`; }

  place() {
    const dw = this.dash.offsetWidth, dh = this.dash.offsetHeight;
    this.placed = `${dw}x${dh}`;
    if (!dw || !dh) return;
    if (!document.body.classList.contains('pcompact')) {
      const s = dh / H, pz = this.el.pz;
      pz.style.transform = `scale(${s})`;
      pz.style.width = px(dw / s);
      this.el.band.style.left = px(dw / s / 2);
      this.bandScale = s;
      // (slide(): where the band's middle and the game's block stand, design px; 12 px kept clear before the block)
      const gm = this.el.gm;
      this.clear = gm.offsetWidth ? { band: dw / s / 2, gm: gm.offsetLeft - 12 } : null;
    } else {
      this.clear = null;
      for (const c of this.dash.querySelectorAll('.cmp')) {
        const w = c.classList.contains('cp') ? 380 : 600, h = c.classList.contains('cp') ? 112 : 88;
        const k = Math.min(dw / w, dh / h);
        c.style.transform = `translateX(-50%) scale(${k})`;
      }
    }
    this.fitted = false;
    if (this.sheet.classList.contains('open')) this.showTab(this.tab);
  }

  openSheet(on) {
    this.sheet.classList.toggle('open', on);
    if (on) this.showTab(this.tab);
  }

  toggleSheet() { this.openSheet(!this.sheet.classList.contains('open')); }

  showTab(k) {
    this.tab = k;
    for (const b of this.sheet.querySelectorAll('.tabs [data-tab]')) b.setAttribute('aria-pressed', String(b.dataset.tab === k));
    for (const p of this.sheet.querySelectorAll('.pane')) p.classList.toggle('on', p.dataset.pane === k);
    const pane = this.sheet.querySelector(`.pane[data-pane="${k}"]`), sl = pane?.querySelector('.slice');
    if (sl) {
      const tab = TABS.find(([x]) => x === k), w = tab[3] - tab[2], aw = pane.clientWidth, ah = pane.clientHeight;
      let s = Math.min(aw / w, ah / H);
      if (s < 0.62) s = Math.min(0.62, ah / H); // (narrower: the part scrolls sideways)
      sl.style.transform = `scale(${s})`;
      sl.style.marginRight = px(w * s - w);
      sl.style.marginBottom = px(H * s - H);
    }
    this.fitted = false;
  }

  // the state shown: called with the HUD (30 times a second)
  update(game, opts) {
    const b = document.body;
    if (this.layoutKey !== this.modeKey()) this.layout();
    else if (this.placed !== `${this.dash.offsetWidth}x${this.dash.offsetHeight}`) this.place();
    if (!this.fitted) this.fit();
    const tram = game.tram, eq = tram.eq, lamps = game.lamps || {}, e = this.el, now = performance.now();
    const set = (k, v, f) => { if (this.state[k] !== v) { this.state[k] = v; f(v); } };
    b.dataset.doors = game.doorState;
    b.classList.toggle('passist', !!opts.assist);
    b.classList.toggle('pdeadman', !!opts.deadman);
    // the dial, the meters
    this.speedShown += (Math.min(82, tram.kmh) - this.speedShown) * 0.35;
    const ang = (v) => -225 + (v / 80) * 270 + 90;
    set('ndl', Math.round(this.speedShown * 10), () => { for (const n of e.ndl) n.setAttribute('transform', `rotate(${ang(this.speedShown).toFixed(1)})`); });
    set('spd', Math.round(tram.kmh), (v) => { e.spd.textContent = v; });
    const lim = opts.assist ? game.currentLimit : null;
    set('lim', lim, (v) => { for (const n of e.lim) { n.setAttribute('visibility', v === null ? 'hidden' : 'visible'); if (v !== null) n.setAttribute('transform', `rotate(${ang(v)})`); } });
    // (6921's reading on the user's photo, and the shift's kilometres on it)
    if (this.shift !== game) { this.shift = game; this.s0 = tram.s; this.ttKey = ''; }
    set('odo', Math.floor(405143 + Math.max(0, tram.s - this.s0) / 1000), (v) => { for (const n of e.odo) n.textContent = String(v).padStart(6, '0'); });
    const amp = Math.round(Math.min(1.03, Math.abs(tram.current) / 600) * 400), volt = Math.round(Math.min(1.03, eq.aux ? eq.aux.U / 40 : 0) * 400);
    set('amp', amp, (v) => { for (const p of e.amp) p.style.transform = `translateY(${-(v / 400) * p.dataset.r}px)`; });
    set('volt', volt, (v) => { for (const p of e.volt) p.style.transform = `translateY(${-(v / 400) * p.dataset.r}px)`; });
    // the lamp strip (ckd24 § 7.2-7.7)
    const st = game.stops[game.nextStop], blink = !!lamps.lit, ind = lamps.indicate, shoe = !!eq.lamps?.shoe;
    const led = (l, on, cls) => set(`led${l}`, on ? cls : '', (v) => { for (const n of e.led[l]) n.setAttribute('class', v ? `on ${v}` : 'off'); });
    led('L', (ind === 'left' || ind === 'hazard') && blink, 'g');
    led('R', (ind === 'right' || ind === 'hazard') && blink, 'g');
    led('V', requested(game, st, tram.s), 'g');
    led('D', game.doorState === 'closed', 'g');
    led('B1', shoe, 'r'); led('B2', shoe, 'r'); led('BV', shoe && tram.cars > 1, 'r');
    led('Z', !!eq.lamps?.acc, 'o');
    led('T', false, 'a');
    // the controls
    const cl = (id, cls, on) => set(`${id}.${cls}`, !!on, (v) => { for (const n of e.ctl[id]) n.classList.toggle(cls, v); });
    const knob = (id, a) => set(`${id}.k`, a, (v) => { for (const n of e.knob[id]) n.style.setProperty('--a', `${v}deg`); });
    const h = this.held;
    cl('bezp', 'down', h[' ']); cl('houk', 'down', lamps.held); cl('vyhybka', 'down', h.y); cl('vyptop', 'down', h.c);
    cl('zvonek', 'down', now - this.bellT < 300); cl('nevyst', 'down', game.doorState === 'closing'); cl('nevyst', 'lit', game.doorState === 'closing');
    cl('napeti', 'lit', tram.voltage > 200); cl('vystr', 'lit', ind === 'hazard' && blink);
    knob('dvere2', game.doorState === 'closed' || game.doorState === 'closing' ? OFF : ON); knob('dvere1', OFF);
    knob('kalor', POS.kalor[game.climate.cab][1]); knob('salon', POS.salon[game.climate.saloon][1]);
    knob('svetl', lamps.high ? -26 : 26); knob('smer', ind === 'left' ? -28 : ind === 'right' ? 28 : 0);
    knob('pisek', h.a || tram.sanding ? -30 : 20); knob('vystr', ind === 'hazard' ? ON : OFF);
    knob('vypinac', CAM[1]); knob('prepos', CAM[1]); knob('osvetl', DAY); knob('sterace', OFF); knob('nouz', OFF); knob('topzrc', OFF);
    knob('havar', OFF); knob('couv', OFF); knob('zarivky', PRESEL);
    // the helper lamps (the game's)
    const ready = st && st.served && st.waiting === 0 && st.alight === 0 && game.clock >= st.sched - 5;
    const help = { speed: game.overspeed, doors: game.doorState !== 'closed', current: tram.drawing, ready,
      slip: (tram.slip || tram.slide) && Math.floor(now / 150) % 2, track: tram.trackBrake, sand: tram.sanding,
      deadman: game.deadmanWarn && Math.floor(now / 250) % 2 };
    set('alamps', Object.values(help).map((v) => (v ? 1 : 0)).join(''), () => { for (const a of e.alamps) a.classList.toggle('on', !!help[a.dataset.a]); });
    if (eq.kind === 'pedals') for (const cv of e.pedals) if (cv.offsetParent) drawPedals(cv, eq, TR37_SPEC);
    // the timetable on the right wing
    const key = `${game.nextStop}:${getLang()}`;
    if (key !== this.ttKey) {
      this.ttKey = key;
      const from = Math.max(0, game.nextStop - 3), rows = game.stops.slice(from, from + 11);
      const html = rows.map((s) => `<tr class="${s.i < game.nextStop ? 'done' : s.i === game.nextStop ? 'next' : ''}"><td>${s.name}</td><td>${fmtTime(s.sched).slice(0, 5)}</td></tr>`).join('');
      for (const tb of e.tt) tb.innerHTML = html;
      for (const l of e.ttLine) l.textContent = t('panel.line', { l: game.line });
      for (const l of e.ttEnd) l.textContent = `→ ${game.stops[game.stops.length - 1].name}`;
    }
    this.slide();
  }

  // the band follows the head (each frame, src/main.js); lim: the head's turn at its most each way (src/cabframe.js
  // lookLimits). With the head turned all the way, the side's last control ends before the game's block (the user,
  // 2026-11-17: "in the side views, the info overlay hides the panel features"): the band slides that much further
  // left, in step with the turn.
  setLook(look, lim) { this.look = look; this.lim = lim; this.slide(); }
  slide() {
    let x = this.look * PER_RAD;
    const L = this.lim && (this.look > 0 ? this.lim.left : this.lim.right), c = this.clear;
    if (L > 0 && c) {
      const over = c.band + Math.sign(this.look) * L * PER_RAD + (this.look > 0 ? SIDE_END.left : SIDE_END.right) - c.gm;
      if (over > 0) x -= over * Math.min(1, Math.abs(this.look) / L);
    }
    x = Math.round(x * 2) / 2;
    if (x !== this.slid) { this.slid = x; this.el.band.style.transform = `translateX(${x}px)`; this.el.gm.classList.toggle('aside', Math.abs(this.look) > 0.3); }
  }
}
