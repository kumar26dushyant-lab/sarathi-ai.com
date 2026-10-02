// The WhatsApp inbox reads like WhatsApp (founder, 2 Oct): Indian time with am/pm, a day
// separator, ✓ / ✓✓ / blue ✓✓ ticks, the bot called NidaanMitra - checked against the real source.
//
//   node uitest/wa-like-whatsapp.js

const fs = require('fs');
const path = require('path');
const h = fs.readFileSync(path.join(__dirname, '..', 'static', 'nidaan_ops.html'), 'utf8');

let failed = 0;
function check(label, ok, detail) {
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label);
  if (!ok) { failed++; if (detail !== undefined) console.log('           ' + String(detail).slice(0, 300)); }
}

const s = h.indexOf('function _istParts(');
const e = h.indexOf('const _WAI_EMO');
const s2 = h.indexOf('const _WAI_SENDER = {');
const e2 = h.indexOf('};', s2) + 2;
if (s < 0 || e < 0 || s2 < 0) { console.error('helpers not found'); process.exit(1); }
// The helpers touch the page once at load (the Translate switch); a bare stand-in is enough here.
global.window = global.window || {};
global.document = global.document || { addEventListener() {}, querySelectorAll() { return []; },
  body: { classList: { toggle() {} } } };
global.localStorage = global.localStorage || { getItem() { return null; }, setItem() {} };
global.esc = (x) => String(x == null ? '' : x).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
// eslint-disable-next-line no-eval
eval(h.slice(s2, e2) + h.slice(s, e) + '; global._istParts=_istParts; global._waiTicks=_waiTicks; global._waiBubbles=_waiBubbles; global._waLangTick=_waLangTick;');

const p = _istParts('2026-10-02 05:00:00');
check('a UTC time is shown in Indian time with am/pm (05:00 UTC = 10:30 am)', p && p.time === '10:30 am', p && p.time);
const p2 = _istParts('2026-10-01 20:00:00');
check('...and on the Indian date (20:00 UTC on 1 Oct = 1:30 am on 2 Oct)', p2 && p2.day.indexOf('2 Oct') === 0 && p2.time === '1:30 am', p2 && (p2.day + ' ' + p2.time));

check('sent shows one tick', _waiTicks({ direction: 'out', status: 'sent' }).includes('>✓<'));
check('delivered shows two ticks', _waiTicks({ direction: 'out', status: 'delivered' }).includes('>✓✓<') && !_waiTicks({ direction: 'out', status: 'delivered' }).includes('read'));
check('read shows two BLUE ticks', _waiTicks({ direction: 'out', status: 'read' }).includes('wtk read'));
check('a failed message says so', _waiTicks({ direction: 'out', status: 'failed' }).includes('not delivered'));
check('their messages carry no ticks', _waiTicks({ direction: 'in', status: 'read' }) === '');

const html = _waiBubbles([
  { direction: 'in', body: 'hello', created_at: '2026-09-29 05:00:00' },
  { direction: 'out', sender: 'bot', body: 'Namaste', status: 'read', created_at: '2026-09-29 05:01:00' },
  { direction: 'in', body: 'next day', created_at: '2026-09-30 05:00:00' },
], 'Ramesh');
check('a separator for each day', (html.match(/class="wai-day"/g) || []).length === 2, html.slice(0, 200));
check('the bot is called NidaanMitra', html.includes('NidaanMitra'));
check('each bubble is searchable (in-chat search)', html.includes('data-t="hello"') && html.includes('data-t="namaste"'));
check('the inbox has a search across all chats and inside a chat',
  h.includes('placeholder="Search names, numbers and messages"') && h.includes('placeholder="Search in this chat"'));
check('a short row of good emojis under the reply box', h.includes("const _WAI_EMO = ['🙏'") && h.includes("_waiEmojiBar('waiBox')"));
check("the claim's own WhatsApp window, in the drawer and the case sheet",
  h.includes('id="claimWa_${c.claim_id}"') && h.includes("'<div id=\"claimWa_' + id + '\""));

// The claim's window is the inbox's window (founder, 2 Oct: "no texts messaging box").
const cw = h.slice(h.indexOf('async function claimWaLoad('), h.indexOf('async function claimWaSend('));
check("the claim's reply box is ALWAYS there (greyed with the reason when WhatsApp's rules stop a reply)",
  cw.includes("'<textarea id=\"' + boxId + '\"") && cw.includes("(canType ? '' : ' disabled')"));
check('...with take over / give back, search in the chat, the 24-hour note and the emoji row',
  cw.includes('I will take over') && cw.includes('Give back to NidaanMitra') && cw.includes('claimWaFind(')
  && cw.includes('24-hour') && cw.includes('_waiEmojiBar(boxId)'));
check('...the same bubbles as the inbox (ticks, Indian time, day separators)', cw.includes('_waiBubbles(d.messages, nm)'));
check('...and it refreshes quietly while open, never while someone types',
  cw.includes('setInterval(') && cw.includes('ndPaint(el, html)') && cw.includes('document.activeElement === b'));

// In their language, recorded in English (founder, 2 Oct).
const trHtml = _waiBubbles([
  { direction: 'in', body: 'माझा क्लेम नाकारला', body_en: 'My claim was rejected', lang: 'mr', lang_name: 'Marathi', created_at: '2026-10-02 05:00:00' },
  { direction: 'out', sender: 'human', sender_name: 'Ravi', body: 'कृपया पाठवा', body_en: 'Please send it', created_at: '2026-10-02 05:01:00' },
], 'Ramesh');
check('a Marathi message shows its English copy, labelled as a machine translation from Marathi',
  trHtml.includes('class="wai-tr"') && trHtml.includes('machine translation from Marathi') && trHtml.includes('My claim was rejected'));
check("a staff reply sent in their language shows the staff member's own English",
  trHtml.includes('as our team wrote it') && trHtml.includes('Please send it'));
check('searching a chat finds a message by its English too', trHtml.includes('my claim was rejected'));
check('"Send in their language" is offered for a Marathi speaker, not for an English one',
  _waLangTick('t', 'mr', 'Marathi').includes('Send in their language (Marathi)') && _waLangTick('t', 'en', 'English') === '');
check('the switch hides the English copy without redrawing', h.includes('body.wa-tr-off .wai-tr{display:none}'));
check('nothing machine-translated is sent unseen: the preview comes first',
  h.includes("const final = await _waTrPreview(text") && h.includes("payload = {text: final, english: text"));

console.log(failed ? '\n' + failed + ' failed' : '\nall passed');
process.exit(failed ? 1 : 0);
