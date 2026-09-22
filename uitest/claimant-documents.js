// The complainant's document flow, in a real browser, in BOTH languages.
//
// The founder watched somebody upload four files and remove two, while all four had already
// reached the office. What has to be true now: picking is not handing over, the screen says which
// state you are in, the button asks before it sends, and when it is done there is a button that
// ends the job.
//
// Run in both languages deliberately. Hindi is the DEFAULT on this screen - the audience is Tier
// 2/3 - so an English-only test would be testing the language almost nobody here reads.
//
//   node claimant-documents.js [path/to/nidaan_claim_portal.html]

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const PAGE = process.argv[2] || path.join(__dirname, '..', 'static', 'nidaan_claim_portal.html');
const src = fs.readFileSync(PAGE, 'utf8');

let failed = 0;
const check = (label, ok) => { console.log((ok ? '  PASS  ' : '  FAIL  ') + label); if (!ok) failed++; };

// One file still being chosen, one already handed over.
const DOCS = [
  { doc_id: 1, name: 'MAIN BILL.pdf', url: '/d/1', uploaded_at: 'x', submitted_at: null },
  { doc_id: 2, name: 'IPD.pdf', url: '/d/2', uploaded_at: 'x', submitted_at: '2026-09-22' },
];

// What each language must actually say on screen.
const WORDS = {
  en: { tag: 'Not sent yet', pending: 'have NOT received them yet',
        confirm: 'Send these documents', canRemove: 'remove anything that is wrong',
        comeBack: 'come back and add more later', done: 'We have your documents',
        doneBtn: 'Done', emailBack: 'link in your email', closeSelf: 'close this tab' },
  hi: { tag: 'अभी भेजा नहीं',
        pending: 'हमें अभी नहीं मिले हैं',
        confirm: 'NidaanPartner को भेजने',
        canRemove: 'गलत फ़ाइल अभी भी हटा',
        comeBack: 'बाद में लौटकर',
        done: 'आपके दस्तावेज़ मिल गए',
        doneBtn: 'हो गया',
        emailBack: 'ईमेल के लिंक',
        closeSelf: 'टैब बंद' },
};

async function run(browser, lang) {
  const W = WORDS[lang];
  console.log('\n── ' + (lang === 'hi' ? 'Hindi (the default here)' : 'English') + ' ──\n');

  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => console.log('  [browser error] ' + e.message.split('\n')[0]));

  let submitted = false;
  await page.route('**/nidaan/claim/api/me', (r) =>
    r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      claim: { claim_id: 39, claim_type: 'health', status: 'assigned', disputed_amount: 733356,
               insured_name: 'GARVIT ARJUN JAIN', insured_phone: '9584468804',
               insured_email: 'a@b.com' },
      fee: { fee_pct: 15, gst_pct: 18, terms_html: '', terms_html_hi: '', illustration: {} },
      timeline: [], consent: {},
      documents: submitted ? DOCS.map((d) => ({ ...d, submitted_at: '2026-09-22' })) : DOCS,
    }) }));
  await page.route('**/nidaan/claim/api/documents/submit', (r) => {
    submitted = true;
    return r.fulfill({ status: 200, contentType: 'application/json',
                       body: JSON.stringify({ ok: true, submitted: 1, total: 2 }) });
  });
  await page.route('**/portal*', (r) =>
    r.fulfill({ status: 200, contentType: 'text/html', body: src }));

  const dialogs = [];
  page.on('dialog', async (d) => { dialogs.push({ type: d.type(), msg: d.message() }); await d.accept(); });

  await page.addInitScript((l) => {
    try { localStorage.setItem('claim_lang', l); } catch (e) {}
  }, lang);
  // The portal asks who you are unless a session is in hand. That OTP journey is a different
  // test; #s= is the same route a staff preview link takes.
  await page.goto('http://x/portal?token=test#s=test-session');
  await page.waitForTimeout(400);

  // innerText of the RENDERED area. textContent('body') would include the <script> tags, which
  // hold BOTH dictionaries - so every phrase would match and every assertion would pass.
  const before = await page.innerText('#content');
  check('the file still being chosen is tagged', before.includes(W.tag));
  check('the page says we do NOT have them yet', before.includes(W.pending));
  check('there is a Save and submit button', !!(await page.$('#submitBtn')));
  check('and it does not yet claim we have them', !before.includes(W.done));

  await page.click('#submitBtn');
  await page.waitForTimeout(500);
  const confirm = dialogs.find((d) => d.type === 'confirm');
  check('it asks before sending', !!confirm);
  check('and says where they are going', !!confirm && confirm.msg.includes(W.confirm));
  check('that anything wrong can still be removed',
        !!confirm && confirm.msg.includes(W.canRemove));
  check('and that they can come back later', !!confirm && confirm.msg.includes(W.comeBack));

  const after = await page.innerText('#content');
  check('afterwards it confirms we have them', after.includes(W.done));
  check('nothing is tagged as unsent any more', !after.includes(W.tag));
  check('the Save and submit button is gone', !(await page.$('#submitBtn')));
  check('there is a button that ends the job', after.includes(W.doneBtn));
  check('and it says how to come back', after.includes(W.emailBack));

  dialogs.length = 0;
  const done = await page.$('.donebox button');
  if (done) {
    await done.click();
    await page.waitForTimeout(400);
    // A tab opened from a link cannot be closed by script, so it must SAY so rather than look
    // like a button that did nothing - which is the complaint this whole screen came from.
    check('pressing Done closes the page or explains why it cannot',
          page.isClosed() || dialogs.some((d) => d.msg.includes(W.closeSelf)));
  } else {
    check('the Done button is there to press', false);
  }

  if (!page.isClosed()) await ctx.close();
}

(async () => {
  const browser = await chromium.launch();
  await run(browser, 'hi');
  await run(browser, 'en');
  await browser.close();
  console.log('\n' + (failed ? failed + ' failed' : 'all passed'));
  process.exit(failed ? 1 : 0);
})();
