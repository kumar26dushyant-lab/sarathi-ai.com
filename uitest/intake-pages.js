// The real pages, in a real browser at phone width: the one claim form actually appears where a
// claim is raised (founder, 2 Oct). The block's own test proves the block; this proves each page
// wires it in - a missing script tag or a mount that never runs shows here as a missing form.
// Every request is answered locally; nothing reaches a server.
//
//   node uitest/intake-pages.js

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.join(__dirname, '..');
let failed = 0;
const check = (label, ok, detail) => {
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label);
  if (!ok) { failed++; if (detail !== undefined) console.log('           ' + String(detail).slice(0, 300)); }
};
const TYPES = { types: [{ code: 'health', en: 'Health / Mediclaim', hi: 'स्वास्थ्य / मेडिक्लेम' }] };

async function serve(page, pagePath, file) {
  await page.route('**/*', async (r) => {
    const u = new URL(r.request().url());
    if (u.pathname === pagePath) return r.fulfill({ status: 200, contentType: 'text/html; charset=utf-8', body: fs.readFileSync(path.join(ROOT, 'static', file), 'utf8') });
    if (u.pathname.startsWith('/static/')) {
      const f = path.join(ROOT, 'static', u.pathname.slice(8));
      if (fs.existsSync(f)) {
        const ct = f.endsWith('.js') ? 'application/javascript' : f.endsWith('.css') ? 'text/css' : 'application/octet-stream';
        return r.fulfill({ status: 200, contentType: ct, body: fs.readFileSync(f) });
      }
      return r.fulfill({ status: 404, body: '' });
    }
    if (u.pathname === '/nidaan/api/intake/types') return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(TYPES) });
    if (u.hostname !== 'nidaanpartner.com') return r.fulfill({ status: 204, body: '' });   // fonts, CDNs: nothing leaves
    return r.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 375, height: 800 }, isMobile: true, hasTouch: true });
  await ctx.addInitScript(() => {
    try {
      localStorage.setItem('nidaan_token', 'x.y.z'); localStorage.setItem('nidaan_branch_token', 'x.y.z');
      localStorage.setItem('nidaan_lang', 'hi'); localStorage.setItem('nidaan_branch_form_lang', 'hi');
    } catch (e) { /* storage blocked */ }
  });
  const errors = [];

  // ── the AP portal ──
  let page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push('branch: ' + e.message));
  await serve(page, '/nidaan/branch', 'nidaan_branch.html');
  await page.goto('https://nidaanpartner.com/nidaan/branch');
  await page.waitForSelector('#bcCore_claim_type option[value="health"]', { state: 'attached', timeout: 15000 }).catch(() => {});
  check('AP portal: the claim form is the shared block', !!(await page.$('#bcCore_complainant_email')));
  check('AP portal: the one-tap guard is on', await page.evaluate(() => window.__ndOneTap === true));
  check('AP portal: Hindi by default for partners', ((await page.textContent('#bcTitle')) || '').includes('क्लेम'));
  await page.click('#bcLangBtn');
  check('AP portal: one tap switches the form to English', ((await page.textContent('#bcCore')) || '').includes('Complainant'));
  check('AP portal: an AP may raise without the letter (with a reason)', !!(await page.$('#bcCore [data-act="noletter"]')));
  await page.close();

  // ── the subscriber dashboard ──
  page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push('dashboard: ' + e.message));
  await serve(page, '/nidaan/dashboard', 'nidaan_dashboard.html');
  await page.goto('https://nidaanpartner.com/nidaan/dashboard');
  await page.evaluate(() => { try { openModal(); } catch (e) { window.__err = String(e); } });
  await page.waitForSelector('#claimCore_claim_type option[value="health"]', { state: 'attached', timeout: 15000 }).catch(() => {});
  check('Dashboard: "Raise a claim" opens the shared block', !!(await page.$('#claimCore_complainant_email')),
    await page.evaluate(() => window.__err || ''));
  check('Dashboard: the one-tap guard is on', await page.evaluate(() => window.__ndOneTap === true));
  check('Dashboard: a subscriber cannot skip the letter', !(await page.$('#claimCore [data-act="noletter"]')));
  await page.fill('#claimCore_disputed_amount', '150000');
  check('Dashboard: the amount shows in words, in Hindi',
    ((await page.textContent('#claimCore_words')) || '').includes('एक लाख पचास हज़ार'));
  await page.close();

  // ── Get started ──
  page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push('start: ' + e.message));
  await serve(page, '/nidaan/start', 'nidaan_start.html');
  await page.goto('https://nidaanpartner.com/nidaan/start');
  await page.evaluate(() => { try { enterClaimForm(); } catch (e) { window.__err = String(e); } });
  await page.waitForSelector('#rvCore_claim_type option[value="health"]', { state: 'attached', timeout: 15000 }).catch(() => {});
  check('Get started: the first claim uses the shared block', !!(await page.$('#rvCore_complainant_email')),
    await page.evaluate(() => window.__err || ''));
  check('Get started: the one-tap guard is on', await page.evaluate(() => window.__ndOneTap === true));
  check('Get started: the old optional-letter slot is gone', !(await page.$('#rev-doc-slots')));
  await page.close();

  check('no page threw a script error', errors.length === 0, errors.join(' | '));
  await browser.close();
  console.log(failed ? '\n' + failed + ' failed' : '\nall passed');
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
