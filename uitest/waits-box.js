// "Why is this claim waiting?" - the Documents pending box, in a real browser at phone width.
//
// Founder, 3 Oct: "the most important reason we have not mentioned - document pending - and a box
// what all documents pending automatic populate in that box and editable by staff."
//
// The REAL box code is lifted out of nidaan_ops.html and run against a stand-in server, then
// used the way staff use it: look, save unchanged, edit the list, untick, tick with nothing.
//
//   node uitest/waits-box.js
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const html = fs.readFileSync(path.join(__dirname, '..', 'static', 'nidaan_ops.html'), 'utf8').replace(/\r\n/g, '\n');
const A = html.indexOf('// WHY IS THIS CLAIM WAITING (founder, 2 Oct)');
const END = 'window.waitLoad = waitLoad; window.waitSave = waitSave; window.waitDocsRefill = waitDocsRefill;';
const B = html.indexOf(END, A);
if (A < 0 || B < 0) { console.error('the box code was not found in nidaan_ops.html'); process.exit(1); }
const code = html.slice(A, B + END.length);

let failed = 0;
const check = (label, ok, detail) => {
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label);
  if (!ok) { failed++; if (detail !== undefined) console.log('           ' + JSON.stringify(detail).slice(0, 300)); }
};

const CHOICES = [{key: 'docs_pending', label: 'Documents pending'}, {key: 'query_complainant', label: 'Query - complainant'},
  {key: 'insurer_reply', label: 'Reply - insurer'}, {key: 'our_team', label: 'Our team'}, {key: 'other', label: 'Other'}];
const SHORT = {ok: true, choices: CHOICES, ticked: [], note_limits: {other: 300, docs_pending: 1000},
  auto: [{key: 'docs', label: 'Documents pending 1 of 4', auto: true}, {key: 'fee', label: 'L2 fee unpaid', auto: true}],
  docs_missing: ['Final bill', 'Discharge summary', 'Claim form']};
const COMPLETE = {ok: true, choices: CHOICES, ticked: [], note_limits: {other: 300, docs_pending: 1000}, auto: [], docs_missing: []};

const page_html = `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{font-family:sans-serif;margin:0;padding:12px} textarea{box-sizing:border-box}</style>
<div class="waitbox" id="waitBox_61"></div>
<script>
window.posts = [];
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
function _l2Err(d, f){ return (d && d.detail) || f; }
async function API(u, o){ return fetch('/api' + u, o); }
</script>
<script>${code}</script>`;

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 375, height: 800 } });
  let state = SHORT;
  await page.route('**/api/claims/61/waiting', async (r) => {
    if (r.request().method() === 'POST') {
      await page.evaluate((b) => window.posts.push(b), JSON.parse(r.request().postData() || '{}'));
      return r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true,"added":[],"cleared":[]}' });
    }
    return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(state) });
  });
  await page.route('**/box', (r) => r.fulfill({ status: 200, contentType: 'text/html', body: page_html }));
  await page.goto('http://x/box');
  const load = async () => { await page.evaluate(() => waitLoad(61)); await page.waitForTimeout(150); };
  const docsBox = () => page.$eval('#waitDocs_61', (t) => t.value);
  const lastPost = () => page.evaluate(() => window.posts[window.posts.length - 1] || null);
  const msg = () => page.$eval('#waitMsg_61', (m) => m.textContent);

  console.log('\nThe checklist is short of three papers\n');
  await load();
  check('"Documents pending" is ticked by itself', await page.$eval('.wticks input[value=docs_pending]', (x) => x.checked));
  check('...and its box lists the missing papers, one per line',
        (await docsBox()) === 'Final bill\nDischarge summary\nClaim form', await docsBox());
  check('...the box is open, not hidden', await page.$eval('#waitDocsWrap_61', (e) => getComputedStyle(e).display !== 'none'));
  check('...it says it is automatic, and the checklist count', /automatic/.test(await page.$eval('#waitBox_61', (e) => e.textContent))
        && /1 of 4/.test(await page.$eval('#waitBox_61', (e) => e.textContent)));
  const txt = await page.$eval('#waitBox_61', (e) => e.textContent);
  check('...the other automatic reasons still show (L2 fee unpaid)', /L2 fee unpaid/.test(txt));
  check('...and the documents are not listed twice', (txt.match(/Final bill/g) || []).length === 0 || !/missing:/.test(txt));

  console.log('\nSaved without changing the list\n');
  await page.click('button.btn-primary');
  await page.waitForTimeout(250);
  let p = await lastPost();
  check('nothing is stored for documents - it keeps following the checklist', p && p.keys.indexOf('docs_pending') < 0, p);
  check('...and it says Saved', /Saved/.test(await msg()), await msg());

  console.log('\nStaff rewrite the list\n');
  await load();
  await page.fill('#waitDocs_61', 'Final bill\nHospital ICP (all pages)');
  await page.click('button.btn-primary');
  await page.waitForTimeout(250);
  p = await lastPost();
  check('their list is sent as Documents pending', p && p.keys.indexOf('docs_pending') >= 0, p);
  check('...with their words, line by line', p && p.notes && p.notes.docs_pending === 'Final bill\nHospital ICP (all pages)', p && p.notes);

  console.log('\nRefilled from the checklist\n');
  await load();
  await page.fill('#waitDocs_61', 'something else');
  await page.click('text=Fill from the checklist');
  check('"Fill from the checklist" puts the missing papers back', (await docsBox()) === 'Final bill\nDischarge summary\nClaim form');

  console.log('\nUnticked while papers are still missing\n');
  await load();
  await page.uncheck('.wticks input[value=docs_pending]');
  await page.click('button.btn-primary');
  await page.waitForTimeout(250);
  check('it says why it comes back, and where to fix it', /stays while the checklist/.test(await msg()), await msg());

  console.log('\nThe checklist is complete, and staff know of a paper it does not name\n');
  state = COMPLETE;
  await load();
  check('"Documents pending" is not ticked', !(await page.$eval('.wticks input[value=docs_pending]', (x) => x.checked)));
  await page.check('.wticks input[value=docs_pending]');
  const before = await page.evaluate(() => window.posts.length);
  await page.click('button.btn-primary');
  await page.waitForTimeout(250);
  check('ticked with an empty list is refused on the page', /List the documents/.test(await msg()), await msg());
  check('...and nothing is sent', (await page.evaluate(() => window.posts.length)) === before);
  await page.fill('#waitDocs_61', 'Hospital ICP');
  await page.click('button.btn-primary');
  await page.waitForTimeout(250);
  p = await lastPost();
  check('with a list, it is saved', p && p.keys.indexOf('docs_pending') >= 0 && p.notes.docs_pending === 'Hospital ICP', p);

  console.log('\nThe "Waiting on" filter\n');
  const sel = await page.evaluate(() => _waitFilterHtml(
    [{waits: [{key: 'docs', auto: true}]}, {waits: [{key: 'docs_pending'}]}, {waits: []}], '', 'f(this.value)'));
  check('"Documents pending" counts the automatic reason and a list staff wrote', /Documents pending \(2\)/.test(sel), sel);
  check('"Nothing recorded" counts the claim nobody has said anything about', /Nothing recorded \(1\)/.test(sel), sel);

  console.log('\nThe website\'s Hindi does not leak into ops (4 Oct)\n');
  // The website and the staff SOP keep their own Hindi switch in 'nidaan_lang'. A phone that had
  // read the SOP in Hindi showed ops' waiting filter in Hindi beside English everything else.
  const leak = await page.evaluate(() => {
    localStorage.setItem('nidaan_lang', 'hi');
    const out = _waitFilterHtml([{waits: []}], '', 'f(this.value)')
      + _waitChips([{key: 'fee', label: 'L2 fee unpaid', label_hi: 'L2 फ़ीस बाकी', auto: true}]);
    localStorage.removeItem('nidaan_lang');
    return out;
  });
  check('with the website set to Hindi, the ops filter still reads in English',
        /Waiting on: anything/.test(leak) && !/किसका इंतज़ार/.test(leak), leak.slice(0, 120));
  check('...and so do the chips', /L2 fee unpaid/.test(leak) && !/फ़ीस बाकी/.test(leak));

  console.log('\nAt phone width\n');
  state = SHORT;
  await load();
  check('nothing runs off the side of a 375 px screen',
        (await page.evaluate(() => document.documentElement.scrollWidth)) <= 375,
        await page.evaluate(() => document.documentElement.scrollWidth));

  await browser.close();
  console.log('\n' + (failed ? failed + ' failed' : 'all passed'));
  process.exit(failed ? 1 : 0);
})();
