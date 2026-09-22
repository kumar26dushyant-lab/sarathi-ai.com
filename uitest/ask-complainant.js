// "Ask the complainant for what is missing" — the button the founder circled, in a real browser.
//
// The report was the one that preceded the move-window outage: pressed, and nothing happens.
// The cause was not this button. `window.csrFocus = csrFocus;` threw a ReferenceError while the
// page was still loading, so every `let` and `const` declared BELOW that line stayed in the
// temporal dead zone - including `_dwClaim`, which is the first thing this button touches.
//
// So this test does two jobs, and the first is the important one:
//
//   1. the page must load without throwing ANYTHING. A single top-level throw silently kills
//      every declaration after it, and the symptom is always a button that does nothing.
//   2. the documents window opens, the button opens the pending-documents window, and asking
//      the complainant takes a deliberate yes first.
//
//   node ask-complainant.js [path/to/nidaan_ops.html]

const fs = require('fs');
const http = require('http');
const path = require('path');
const { chromium } = require('playwright');

const PAGE = process.argv[2] || path.join(__dirname, '..', 'static', 'nidaan_ops.html');
const STATIC = path.join(__dirname, '..', 'static');
const CLAIM = 75;

const DOCS = [
  { doc_id: 1, original_name: 'INVESTIGATIONS.pdf', file_size: 1363148, mime_type: 'application/pdf',
    url: '/d/1', uploaded_at: '2026-09-15 11:21' },
  { doc_id: 2, original_name: 'KYC.pdf', file_size: 974848, mime_type: 'application/pdf',
    url: '/d/2', uploaded_at: '2026-09-16 07:42' },
];

// 4 of 8, exactly as the founder's screenshot has it.
const CHECKLIST = [
  { key: 'policy',    label: 'Policy Document (with T&C page) / Policy Copy', received: true, received_via: 'staff:ANNAPURNA KASERA' },
  { key: 'rejection', label: 'Rejection Letter / Bill Summary',              received: true, received_via: 'staff:ANNAPURNA KASERA' },
  { key: 'finalbill', label: 'Final Bill with Payment Receipts',             received: true, received_via: 'staff:ANNAPURNA KASERA' },
  { key: 'claimform', label: 'Claim Form',                                   received: true, received_via: 'staff:ANNAPURNA KASERA' },
  { key: 'discharge', label: 'Discharge Summary / Discharge Documents',      received: false },
  { key: 'kyc',       label: 'KYC (ID proof of the policyholder)',           received: false },
  { key: 'caseemail', label: 'Email ID created for this case (with its password)', received: false },
  { key: 'other',     label: 'Any other documents available', required: false, received: false },
];

const CLAIM_ROW = {
  claim_id: CLAIM, claim_type: 'health', status: 'assigned',
  insured_name: 'GARVIT ARJUN JAIN', complainant_name: 'GARVIT ARJUN JAIN',
  complainant_phone: '9584468804', complainant_email: 'a@b.com',
  pipeline_stage: '', docs_complete_at: null, docs_complete_by: null,
};

let failed = 0;
const check = (label, ok) => { console.log((ok ? '  PASS  ' : '  FAIL  ') + label); if (!ok) failed++; };

// Every ops call this journey makes. Anything not listed is answered 404 AND printed, so a
// missing route shows up as a missing route instead of as a silently empty screen.
function fixture(p, method) {
  if (method === 'GET' && p === `/claims/${CLAIM}/documents`) return { docs: DOCS };
  if (method === 'GET' && p === `/claims/${CLAIM}/doc-window`)
    return { docs: CHECKLIST, types: ['health', 'motor', 'life'], claim_type: 'health',
             channels: { email: true, whatsapp: true },
             contact: { email: 'a@b.com', phone: '9584468804' } };
  if (method === 'GET' && p === `/claims/${CLAIM}`) return { claim: CLAIM_ROW };
  if (method === 'GET' && p === `/claims/${CLAIM}/last-ask`) return { asked: false };
  if (method === 'GET' && p === `/claims/${CLAIM}/reminders`) return { reminders: [] };
  if (method === 'POST' && p === `/claims/${CLAIM}/doc-window/draft`)
    return { message: 'Namaste, we still need the following documents…' };
  return null;
}

// The page fetches with absolute paths, so it needs an origin. A file:// URL makes every fetch
// fail with "URL scheme file is not supported", which hides exactly the errors we are hunting.
const unmatched = [];
function serve() {
  return http.createServer((req, res) => {
    const url = req.url.split('?')[0];
    if (url.startsWith('/nidaan/ops/api')) {
      const body = fixture(url.slice('/nidaan/ops/api'.length), req.method);
      if (body === null) unmatched.push(req.method + ' ' + url);
      res.writeHead(body === null ? 404 : 200, { 'Content-Type': 'application/json' });
      return res.end(JSON.stringify(body || {}));
    }
    if (url === '/' || url === '/nidaan/ops') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      return res.end(fs.readFileSync(PAGE, 'utf8'));
    }
    if (url.startsWith('/static/')) {
      const f = path.join(STATIC, url.slice('/static/'.length));
      if (f.startsWith(STATIC) && fs.existsSync(f)) {
        const t = f.endsWith('.css') ? 'text/css' : (f.endsWith('.js') ? 'text/javascript' : 'text/plain');
        res.writeHead(200, { 'Content-Type': t + '; charset=utf-8' });
        return res.end(fs.readFileSync(f));
      }
    }
    res.writeHead(204).end();
  });
}

(async () => {
  const server = serve();
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const base = 'http://127.0.0.1:' + server.address().port;

  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();

  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message.split('\n')[0]));

  await page.goto(base + '/nidaan/ops');
  await page.waitForTimeout(800);

  // ── 1. the page must load clean ────────────────────────────────────────────
  // This is the whole lesson of the bug. One top-level throw and every let/const below it is
  // dead for the life of the page, with no message anywhere a staffer or a log would see.
  console.log('\nThe page loads without throwing\n');
  console.log('    errors on load: ' + (errors.join(' | ') || 'none'));
  check('nothing was thrown while the page was loading', errors.length === 0);

  // The names that were in the temporal dead zone, each read straight from the page.
  const dead = await page.evaluate(() => {
    const names = ['_dwClaim', '_dwData', '_dwLast', '_cbState', '_cbBusy', 'CB_BUCKETS',
                   '_waiSel', '_waiOnDuty', '_lineStatsAt', '_qrPollTimer'];
    return names.filter((n) => {
      try { new Function('return typeof ' + n)(); return false; } catch (e) { return true; }
    });
  });
  check('every declaration below the old throw is alive — ' + (dead.join(', ') || 'all alive'),
        dead.length === 0);

  // ── 2. the journey ─────────────────────────────────────────────────────────
  await page.evaluate(() => {
    window._token = 'test-token'; window._role = 'super_admin';
    window._staffId = 7; window._staffName = 'Test Staff';
  });

  console.log('\nThe documents window opens\n');
  await page.evaluate((c) => window.docsOpen(c), CLAIM);
  await page.waitForTimeout(700);
  const title1 = (await page.textContent('#modalTitle').catch(() => '')) || '';
  check('the window is open', await page.isVisible('#modalBg.open'));
  check('it is the documents window — ' + JSON.stringify(title1), /Documents/.test(title1));
  check('the checklist came through (4 of 8)', /4 of 8/i.test(await page.innerText('#modalBody')));

  const btn = await page.$('#modalBody button:has-text("Ask the complainant for what is missing")');
  check('the button the founder circled is on screen', !!btn);
  if (!btn) { await browser.close(); server.close(); process.exit(1); }

  console.log('\nPressing it asks first — nothing may leave on one tap\n');
  const before = errors.length;
  await btn.click();
  await page.waitForTimeout(400);
  const askTitle = (await page.textContent('#modalTitle').catch(() => '')) || '';
  const askBody = (await page.innerText('#modalBody').catch(() => '')) || '';
  check('a question was asked', /Ask the complainant/i.test(askTitle));
  check('it names the claim', /NP-75/.test(askBody));
  check('it says nothing has gone yet', /Nothing reaches the complainant yet/i.test(askBody));
  check('and there is a way back', !!(await page.$('#modalFooter button:has-text("Go back")')));

  console.log('\nGoing back returns to the documents window, not to nothing\n');
  await page.click('#modalFooter button:has-text("Go back")');
  await page.waitForTimeout(700);
  check('the documents window is back',
        /Documents/.test((await page.textContent('#modalTitle').catch(() => '')) || ''));

  console.log('\nSaying yes opens the request\n');
  await page.click('#modalBody button:has-text("Ask the complainant for what is missing")');
  await page.waitForTimeout(400);
  await page.click('#modalFooter button:has-text("Open the request")');
  await page.waitForTimeout(1200);

  const title2 = (await page.textContent('#modalTitle').catch(() => '')) || '';
  const bodyTxt = (await page.innerText('#modalBody').catch(() => '')) || '';
  const newErrors = errors.slice(before);
  console.log('    title after the press : ' + JSON.stringify(title2));
  console.log('    errors on the press   : ' + (newErrors.join(' | ') || 'none'));

  check('a window is still on screen', await page.isVisible('#modalBg.open'));
  check('it is the pending-documents window', /Pending documents/i.test(title2));
  check('it finished loading', !/Loading/i.test(bodyTxt));
  check('the outstanding documents are listed', /Discharge Summary/.test(bodyTxt));
  check('nothing was thrown', newErrors.length === 0);

  if (unmatched.length) {
    console.log('\n  routes this journey asked for that the fixture does not cover:');
    [...new Set(unmatched)].forEach((u) => console.log('    ' + u));
  }

  try {
    fs.mkdirSync(path.join(__dirname, 'screenshots'), { recursive: true });
    await page.screenshot({ path: path.join(__dirname, 'screenshots', 'ask-complainant.png') });
  } catch (e) {}

  await browser.close();
  server.close();
  console.log('\n' + (failed ? failed + ' failed' : 'all passed'));
  process.exit(failed ? 1 : 0);
})();
