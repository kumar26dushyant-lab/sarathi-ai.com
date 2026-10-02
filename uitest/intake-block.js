// The one claim intake block (founder, 2 Oct 2026), in a real browser at phone width:
//   - the amount comes back in words, Indian style (lakh / crore), English and Hindi;
//   - the complainant's name, mobile and email are required, the patient's mobile is not;
//   - nothing goes without the rejection letter - or, where the door allows it, a reason;
//   - "please check" shows the mobile and the amount back before anything is sent;
//   - at 375 px nothing scrolls sideways and every input is 16 px (no iPhone zoom), in both themes;
//   - every Nidaan claim form loads the block, and none keeps its own claim-type list.
//
//   node uitest/intake-block.js

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.join(__dirname, '..');
const rd = (f) => fs.readFileSync(path.join(ROOT, f), 'utf8');
let failed = 0;
const check = (label, ok, detail) => {
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label);
  if (!ok) { failed++; if (detail !== undefined) console.log('           ' + String(detail).slice(0, 300)); }
};

// ── the pages: each claim form loads the block and keeps no type list of its own ──────────
const FORMS = ['static/nidaan_ops.html', 'static/nidaan_branch.html', 'static/nidaan_dashboard.html', 'static/nidaan_start.html'];
for (const f of FORMS) {
  const h = rd(f);
  check(f + ' loads the shared intake block', h.includes('/static/nidaan_intake.js'));
  check(f + ' keeps no claim-type list of its own',
    !/<option value="(health|motor|general)"/.test(h) && !/value=\\?"general\\?"/.test(h));
}

const THEME = (dark) => `:root{--nd-bg-surface:${dark ? '#0f172a' : '#ffffff'};--nd-bg-surface-2:${dark ? '#1e293b' : '#f8fafc'};
  --nd-text-primary:${dark ? '#f1f5f9' : '#0f172a'};--nd-text-secondary:${dark ? '#cbd5e1' : '#334155'};--nd-border:${dark ? '#334155' : '#e2e8f0'};
  --nd-border-strong:${dark ? '#475569' : '#94a3b8'};--nd-danger-text:${dark ? '#fca5a5' : '#b91c1c'};}
  body{margin:0;padding:16px;background:var(--nd-bg-surface);color:var(--nd-text-primary);font-family:sans-serif}`;

const TYPES = { types: [{ code: 'health', en: 'Health / Mediclaim', hi: 'स्वास्थ्य / मेडिक्लेम' },
                        { code: 'motor', en: 'Motor', hi: 'मोटर' }] };

(async () => {
  const browser = await chromium.launch();
  for (const dark of [false, true]) {
    const ctx = await browser.newContext({ viewport: { width: 375, height: 800 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
    const page = await ctx.newPage();
    await page.route('**/nidaan/api/intake/types', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(TYPES) }));
    await page.route('**/letter', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ token: 'tok123', name: 'letter.pdf' }) }));
    const html = (`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
      <style>${THEME(dark)}</style><body><div id="box"></div>
      <script>${rd('static/nidaan_insurers.js')}</script><script>${rd('static/nidaan_intake.js')}</script></body>`);
    await page.route('https://nidaanpartner.com/test', (r) => r.fulfill({ status: 200, contentType: 'text/html; charset=utf-8', body: html }));
    await page.goto('https://nidaanpartner.com/test');
    const tag = dark ? ' (dark)' : ' (light)';

    // words
    const w = await page.evaluate(() => [NidaanIntake.words(150000, 'en'), NidaanIntake.words(150000, 'hi'),
      NidaanIntake.words(12345678, 'en'), NidaanIntake.inr(12345678), NidaanIntake.words(1000000000, 'hi')]);
    check('₹1,50,000 reads "One lakh fifty thousand rupees"' + tag, w[0] === 'One lakh fifty thousand rupees', w[0]);
    check('...and in Hindi "एक लाख पचास हज़ार रुपये"' + tag, w[1] === 'एक लाख पचास हज़ार रुपये', w[1]);
    check('crore, lakh, thousand, hundred all named' + tag, w[2] === 'One crore twenty-three lakh forty-five thousand six hundred seventy-eight rupees', w[2]);
    check('the figure is grouped the Indian way' + tag, w[3] === '₹1,23,45,678', w[3]);
    check('₹100 crore in Hindi' + tag, w[4] === 'एक सौ करोड़ रुपये', w[4]);

    await page.evaluate(() => NidaanIntake.mount('box', { lang: 'en', letterUrl: '/x/letter', headers: () => ({}), allowNoLetter: true }));
    await page.waitForSelector('#box_claim_type option[value="health"]', { state: 'attached' });

    let r = await page.evaluate(() => NidaanIntake.collect('box'));
    check('an empty form is refused at the patient name' + tag, !r.ok && r.field === 'insured_name', JSON.stringify(r));
    await page.fill('#box_insured_name', 'Kamla Devi');
    await page.fill('#box_complainant_name', 'Ramesh Kumar');
    await page.fill('#box_complainant_phone', '+91 98765 43210');
    r = await page.evaluate(() => NidaanIntake.collect('box'));
    check('the complainant email is required' + tag, !r.ok && r.field === 'complainant_email', JSON.stringify(r));
    await page.fill('#box_complainant_email', 'r@example.com');
    await page.selectOption('#box_claim_type', 'health');
    await page.selectOption('#box_ins_pick', { index: 1 });
    await page.fill('#box_disputed_amount', '150000');
    const words = await page.textContent('#box_words');
    check('the amount is shown back in words as it is typed' + tag, words.includes('One lakh fifty thousand'), words);
    r = await page.evaluate(() => NidaanIntake.collect('box'));
    check('nothing goes without the rejection letter' + tag, !r.ok && r.field === 'rejection_letter', JSON.stringify(r));

    await page.click('[data-act="noletter"]');
    await page.fill('#box_reason', 'na');
    r = await page.evaluate(() => NidaanIntake.collect('box'));
    check('"no letter" needs a real reason' + tag, !r.ok && r.field === 'no_letter_reason', JSON.stringify(r));
    await page.click('[data-act="haveit"]').catch(() => {});
    await page.setInputFiles('#box_file', { name: 'letter.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\n%%EOF') });
    await page.waitForSelector('#box_letter.ok');
    r = await page.evaluate(() => NidaanIntake.collect('box'));
    check('with the letter uploaded, the claim is complete and carries its token' + tag,
      r.ok && r.data.letter_token === 'tok123' && r.data.complainant_phone === '9876543210' && r.data.disputed_amount === 150000
      && r.data.insured_phone === '', JSON.stringify(r));
    check('...the values typed before the upload survived it' + tag, r.ok && r.data.insured_name === 'Kamla Devi');

    const p = page.evaluate(() => NidaanIntake.confirm('box'));
    await page.waitForSelector('.ndik-dlg');
    const dlg = await page.textContent('.ndik-dlg');
    check('"please check" shows the mobile, the email and the amount in words' + tag,
      dlg.includes('+91 98765 43210') && dlg.includes('r@example.com') && dlg.includes('One lakh fifty thousand'), dlg);
    await page.click('.ndik-dlg button:not(.go)');
    check('"go back and fix" sends nothing' + tag, (await p) === false);

    const lay = await page.evaluate(() => ({
      over: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      small: Array.from(document.querySelectorAll('#box input:not([type=checkbox]):not([type=file]),#box select,#box textarea'))
        .filter((e) => parseFloat(getComputedStyle(e).fontSize) < 16).map((e) => e.id),
      short: Array.from(document.querySelectorAll('#box input:not([type=checkbox]):not([type=file]),#box select,#box button'))
        .filter((e) => e.offsetParent && e.getBoundingClientRect().height < 43.5).map((e) => e.id || e.textContent)
    }));
    check('at 375 px nothing scrolls sideways' + tag, lay.over <= 0, lay.over);
    check('every input is 16 px (no zoom on iPhone)' + tag, lay.small.length === 0, lay.small);
    check('every control is at least 44 px tall (a thumb, not a stylus)' + tag, lay.short.length === 0, lay.short);

    await page.evaluate(() => NidaanIntake.mount('box', { lang: 'hi', letterUrl: '/x/letter', headers: () => ({}), allowNoLetter: true }));
    const hiText = await page.textContent('#box');
    check('the whole block switches to Hindi, keeping what was typed' + tag,
      hiText.includes('शिकायतकर्ता') && hiText.includes('विवादित राशि')
      && (await page.inputValue('#box_complainant_email')) === 'r@example.com', hiText.slice(0, 120));
    await ctx.close();
  }
  await browser.close();
  console.log(failed ? '\n' + failed + ' failed' : '\nall passed');
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
