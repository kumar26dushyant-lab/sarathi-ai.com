// Typing a date must not save what you have not finished typing.
//
// An <input type="date"> fires `change` as each SEGMENT is completed. Typing 28 into the day of
// 2026-05-25 fires change with 2026-05-02 first - which is a real date, in the past, and which
// the app then saved and validated. That is how a correct discharge date reported itself as
// being before the admission, and how an escalation was recorded in the year 2.
//
// This drives the real _l2DateEdit / _l2DateCommit out of nidaan_ops.html with a real keyboard.
//
//   node date-typing.js [path/to/nidaan_ops.html]

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const PAGE = process.argv[2] || path.join(__dirname, '..', 'static', 'nidaan_ops.html');
const src = fs.readFileSync(PAGE, 'utf8');
const a = src.indexOf('let _l2DateTimer = null, _l2DatePending = null;');
const b = src.indexOf('window._l2DateEdit = _l2DateEdit; window._l2DateCommit = _l2DateCommit;');
if (a < 0 || b < 0) { console.error('the date guard is not in the page'); process.exit(1); }
const guard = src.slice(a, b);

const harness = `<!doctype html><meta charset="utf-8"><body>
<input type="date" id="lf_discharge_date" value="2026-05-25"
       onchange="_l2DateEdit(this,'discharge_date','field')" onblur="_l2DateCommit()">
<input type="text" id="elsewhere">
<script>
window.saved = [];
function l2Field(key, v){ window.saved.push(key + '=' + v); }
function l2Core(key, v){ window.saved.push('core:' + key + '=' + v); }
${guard}
</script></body>`;

let failed = 0;
const check = (label, ok) => { console.log((ok ? '  PASS  ' : '  FAIL  ') + label); if (!ok) failed++; };

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.route('**/dates', (r) =>
    r.fulfill({ status: 200, contentType: 'text/html', body: harness }));
  await page.goto('http://x/dates');

  console.log('\nWhat the browser actually does while you type\n');
  const raw = await page.evaluate(() => {
    const el = document.createElement('input');
    el.type = 'date'; el.value = '2026-05-25';
    document.body.appendChild(el);
    window.__raw = [];
    el.addEventListener('change', function () { window.__raw.push(this.value); });
    el.id = 'probe';
    return true;
  });
  await page.focus('#probe');
  for (const k of ['2', '8']) { await page.keyboard.press(k); await page.waitForTimeout(60); }
  const fired = await page.evaluate(() => window.__raw);
  check('change fires twice for one typed day: ' + JSON.stringify(fired), fired.length === 2);
  check('and the first one is a date nobody meant to enter', fired[0] === '2026-05-02');

  console.log('\nThe app must save only the finished one\n');
  await page.focus('#lf_discharge_date');
  for (const k of ['2', '8']) { await page.keyboard.press(k); await page.waitForTimeout(60); }
  check('nothing saved while still typing',
        (await page.evaluate(() => window.saved)).length === 0);
  await page.click('#elsewhere');                       // leaving the field
  await page.waitForTimeout(120);
  let saved = await page.evaluate(() => window.saved);
  check('one save, on leaving the field', saved.length === 1);
  check('and it is the date they meant: ' + saved[0], saved[0] === 'discharge_date=2026-05-28');

  console.log('\nA year being typed never reaches the server\n');
  await page.evaluate(() => { window.saved = []; });
  await page.evaluate(() => {
    // 0002-09-22 is what the year segment reports after the first keystroke of 2026.
    const el = document.getElementById('lf_discharge_date');
    el.value = '0002-09-22';
    el.dispatchEvent(new Event('change'));
  });
  await page.waitForTimeout(1100);
  check('the year 2 is refused before it leaves the page',
        (await page.evaluate(() => window.saved)).length === 0);

  console.log('\nBut a person who stops typing does not have to click away\n');
  await page.evaluate(() => {
    const el = document.getElementById('lf_discharge_date');
    el.value = '2026-06-11';
    el.dispatchEvent(new Event('change'));
  });
  await page.waitForTimeout(1100);
  saved = await page.evaluate(() => window.saved);
  check('it saves once they have stopped', saved.length === 1 && saved[0] === 'discharge_date=2026-06-11');

  console.log('\nAnd clearing a date is still a real answer\n');
  await page.evaluate(() => { window.saved = []; });
  await page.evaluate(() => {
    const el = document.getElementById('lf_discharge_date');
    el.value = '';
    el.dispatchEvent(new Event('change'));
  });
  await page.waitForTimeout(1100);
  saved = await page.evaluate(() => window.saved);
  check('an empty date is sent, not swallowed', saved.length === 1 && saved[0] === 'discharge_date=');

  await browser.close();
  console.log('\n' + (failed ? failed + ' failed' : 'all passed'));
  process.exit(failed ? 1 : 0);
})();
