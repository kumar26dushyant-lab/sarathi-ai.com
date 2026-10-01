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
global.esc = (x) => String(x == null ? '' : x).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
// eslint-disable-next-line no-eval
eval(h.slice(s2, e2) + h.slice(s, e) + '; global._istParts=_istParts; global._waiTicks=_waiTicks; global._waiBubbles=_waiBubbles;');

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

console.log(failed ? '\n' + failed + ' failed' : '\nall passed');
process.exit(failed ? 1 : 0);
