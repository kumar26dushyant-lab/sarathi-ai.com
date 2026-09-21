// One tap, one action - tested in a real browser, with the real guard.
//
// The guard is lifted out of nidaan_ops.html and dropped into a small page with buttons that
// behave like the ops screen's: some send a request, some only change the screen. Then it is
// clicked the way an impatient person clicks.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const src = fs.readFileSync(process.argv[2] || path.join(__dirname, '..', 'static', 'nidaan_ops.html'), 'utf8');
const a = src.indexOf('(function(){\n  if (window.__ndOneTap) return;');
const b = src.indexOf('})();', a) + '})();'.length;
if (a < 0 || b < 5) { console.error('guard not found in the page'); process.exit(1); }
const guard = src.slice(a, b);

const page_html = `<!doctype html><meta charset="utf-8"><body>
<button id="slow" onclick="go('slow')">Move</button>
<button id="ui" onclick="ui()">Pencil</button>
<button id="rapid" data-nd-rapid="1" onclick="go('rapid')">Rapid</button>
<button id="hang" onclick="hang()">Hangs</button>
<button id="other" onclick="go('other')">Other</button>
<button id="opens" onclick="openDlg()">Opens a dialog</button>
<div id="dlg"></div>
<table><tr id="row" onclick="go('row')"><td>NP-1</td></tr></table>
<div id="out"></div>
<script>
window.calls = {slow:0, rapid:0, other:0, ui:0, hang:0, row:0};
window.sent = 0;
// A request that takes 600ms, like a move on a slow phone.
function go(k){ window.calls[k]++; window.sent++;
  fetch('/slow?k=' + k).then(function(){}, function(){}); }
function ui(){ window.calls.ui++; document.getElementById('out').textContent = 'opened'; }
function hang(){ window.calls.hang++; fetch('/hang').then(function(){}, function(){}); }
// The same shape as openModal: the dialog's buttons appear instantly and are armed a moment
// later, so a finger still coming down cannot press one.
window.confirmed = 0;
function openDlg(){
  const d = document.getElementById('dlg');
  d.innerHTML = '<button id="yes" onclick="window.confirmed++">Yes, move it</button>';
  const b = d.querySelector('button');
  b.dataset.ndArming = '1';
  setTimeout(function(){ delete b.dataset.ndArming; }, 280);
}
// A background poll, started on a timer and NOT by any tap. The guard must ignore it.
setInterval(function(){ fetch('/poll').then(function(){}, function(){}); }, 100);
</script>
<script>${guard}</script>
</body>`;

let failed = 0;
const check = (label, ok) => { console.log((ok ? '  PASS  ' : '  FAIL  ') + label); if (!ok) failed++; };

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext();
  const page = await ctx.newPage();

  await page.route('**/slow*', async (r) => {
    await new Promise((res) => setTimeout(res, 600));
    await r.fulfill({ status: 200, body: '{}' });
  });
  await page.route('**/poll*', (r) => r.fulfill({ status: 200, body: '{}' }));
  // Never answers, to prove the ceiling releases the button.
  await page.route('**/hang*', () => {});
  await page.route('**/onetap', (r) => r.fulfill({ status: 200, contentType: 'text/html', body: page_html }));
  await page.goto('http://x/onetap');

  console.log('\nAn impatient person taps Move five times\n');
  for (let i = 0; i < 5; i++) { await page.click('#slow', { force: true }); await page.waitForTimeout(40); }
  check('it ran once, not five times', (await page.evaluate(() => window.calls.slow)) === 1);
  check('and one request was sent', (await page.evaluate(() => window.sent)) === 1);
  check('the button shows it is working',
        await page.evaluate(() => document.getElementById('slow').classList.contains('nd-working')));
  check('and says so to a screen reader',
        (await page.getAttribute('#slow', 'aria-busy')) === 'true');

  console.log('\nOnce the request finishes, the button works again\n');
  await page.waitForTimeout(900);
  check('it is no longer marked working',
        !(await page.evaluate(() => document.getElementById('slow').classList.contains('nd-working'))));
  await page.click('#slow');
  check('a real second move is allowed', (await page.evaluate(() => window.calls.slow)) === 2);

  console.log('\nA button that only changes the screen is not held up\n');
  await page.waitForTimeout(700);
  await page.click('#ui');
  await page.waitForTimeout(260);
  await page.click('#ui');
  check('two deliberate taps both worked', (await page.evaluate(() => window.calls.ui)) === 2);

  console.log('\nA background poll does not freeze the screen\n');
  // The poll fires every 100ms throughout. If the guard watched "any request in flight",
  // every button on the page would sit dead behind it.
  await page.waitForTimeout(400);
  const before = await page.evaluate(() => window.calls.other);
  await page.click('#other');
  await page.waitForTimeout(900);
  await page.click('#other');
  check('both taps landed', (await page.evaluate(() => window.calls.other)) === before + 2);

  console.log('\nA request that never answers still gives the button back\n');
  await page.click('#hang');
  check('the first tap ran', (await page.evaluate(() => window.calls.hang)) === 1);
  await page.click('#hang', { force: true });
  check('and a second tap during it is swallowed',
        (await page.evaluate(() => window.calls.hang)) === 1);
  await page.waitForTimeout(10500);
  check('after the ceiling, the button is usable again',
        !(await page.evaluate(() => document.getElementById('hang').classList.contains('nd-working'))));
  await page.click('#hang');
  check('and it works', (await page.evaluate(() => window.calls.hang)) === 2);

  console.log('\nA claim row is a tap target too\n');
  for (let i = 0; i < 4; i++) { await page.click('#row', { force: true }); await page.waitForTimeout(40); }
  check('opening a claim four times opens it once',
        (await page.evaluate(() => window.calls.row)) === 1);
  await page.waitForTimeout(900);
  await page.click('#row');
  check('and it can be opened again afterwards',
        (await page.evaluate(() => window.calls.row)) === 2);

  console.log('\nA dialog does not act on the tap that opened it\n');
  await page.click('#opens');
  await page.waitForTimeout(60);              // a finger still coming down
  await page.click('#yes', { force: true });
  check('the tap-through did NOT confirm', (await page.evaluate(() => window.confirmed)) === 0);
  await page.waitForTimeout(320);
  await page.click('#yes');
  check('but a real click a moment later does',
        (await page.evaluate(() => window.confirmed)) === 1);

  console.log('\nSomething that asks to stay rapid, stays rapid\n');
  for (let i = 0; i < 3; i++) { await page.click('#rapid'); await page.waitForTimeout(30); }
  check('all three taps ran', (await page.evaluate(() => window.calls.rapid)) === 3);

  await browser.close();
  console.log('\n' + (failed ? failed + ' failed' : 'all passed'));
  process.exit(failed ? 1 : 0);
})();
