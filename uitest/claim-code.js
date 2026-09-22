// The code screen the founder photographed: KAPIL, both buttons live, and a red line saying he
// had already asked for too many codes in an hour.
//
// He had. `sendCode()` disabled nothing, so five impatient taps spent the whole hour's allowance
// in five seconds and locked him out of his own claim page. This proves the taps after the first
// one now reach nobody, and that the screen says what is happening instead of scolding.
//
// Run in BOTH languages. Hindi is the default on this screen - the audience is Tier 2/3 - so an
// English-only run tests the language almost nobody here reads.
//
//   node claim-code.js [path/to/nidaan_claim_portal.html]

const fs = require('fs');
const http = require('http');
const path = require('path');
const { chromium } = require('playwright');

const PAGE = process.argv[2] || path.join(__dirname, '..', 'static', 'nidaan_claim_portal.html');
const STATIC = path.join(__dirname, '..', 'static');

let failed = 0;
const check = (label, ok) => { console.log((ok ? '  PASS  ' : '  FAIL  ') + label); if (!ok) failed++; };

// What the server will answer next, and every /verify/start it actually received.
let MODE = 'ok';
const starts = [];

const WORDS = {
  en: { wait: 'Please wait', again: 'Send it again', left: 'left',
        onWay: 'take a minute or two', help: 'Not received it?',
        rate: '5 codes have already been sent' },
  hi: { wait: 'कृपया रुकिए', again: 'दोबारा भेजें', left: 'बचे',
        onWay: 'एक-दो मिनट', help: 'कोड नहीं मिला?',
        rate: '5 कोड भेजे' },
};

function api(url, method, body) {
  const p = url.split('?')[0];
  if (p === '/nidaan/claim/api/verify/where') {
    return { ok: 200, body: { claim_id: 61, name: 'KAPIL', channels: [
      { kind: 'whatsapp', masked: '•••• 1797', ready: true },
      { kind: 'email', masked: '9********@gmail.com', ready: true },
    ] } };
  }
  if (p === '/nidaan/claim/api/verify/start') {
    starts.push(JSON.parse(body || '{}'));
    if (MODE === 'rate') {
      return { ok: 400, body: { detail: {
        error: WORDS.en.rate.replace('5 codes', '5 codes') + ' for this claim in the last hour. '
             + 'Please try again in about 22 minute(s) — or call us and we will open it with you.',
        reason: 'rate_limited', retry_after_sec: 1320, left: 0 } } };
    }
    if (MODE === 'rate_hi') {
      return { ok: 400, body: { detail: {
        error: 'पिछले एक घंटे में इस क्लेम पर 5 कोड भेजे जा चुके हैं। कृपया 22 मिनट बाद दोबारा कोशिश कीजिए।',
        reason: 'rate_limited', retry_after_sec: 1320, left: 0 } } };
    }
    if (MODE === 'fail') {
      return { ok: 400, body: { detail: {
        error: 'We could not send the code just now. Try the other way, or call us.',
        reason: 'send_failed', retry_after_sec: 0, left: 4 } } };
    }
    return { ok: 200, body: { ok: true, kind: JSON.parse(body || '{}').channel,
                              masked: '•••• 1797', ttl_min: 10, cooldown_sec: 3, left: 3 } };
  }
  return null;
}

function serve() {
  return http.createServer((req, res) => {
    let body = '';
    req.on('data', (c) => { body += c; });
    req.on('end', () => {
      const url = req.url.split('?')[0];
      if (url.startsWith('/nidaan/claim/api')) {
        const r = api(req.url, req.method, body);
        res.writeHead(r ? r.ok : 404, { 'Content-Type': 'application/json' });
        return res.end(JSON.stringify(r ? r.body : {}));
      }
      if (url === '/portal') {
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        return res.end(fs.readFileSync(PAGE, 'utf8'));
      }
      if (url.startsWith('/static/')) {
        const f = path.join(STATIC, url.slice('/static/'.length));
        if (f.startsWith(STATIC) && fs.existsSync(f)) {
          res.writeHead(200, { 'Content-Type': f.endsWith('.css') ? 'text/css' : 'text/javascript' });
          return res.end(fs.readFileSync(f));
        }
      }
      res.writeHead(204).end();
    });
  });
}

async function run(browser, base, lang) {
  const W = WORDS[lang];
  console.log('\n── ' + (lang === 'hi' ? 'Hindi (the default here)' : 'English') + ' ──\n');
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message.split('\n')[0]));
  await page.addInitScript((l) => { try { localStorage.setItem('claim_lang', l); } catch (e) {} }, lang);

  MODE = 'ok'; starts.length = 0;
  await page.goto(base + '/portal?token=test');
  await page.waitForTimeout(500);

  check('the page loaded without throwing', errors.length === 0);
  check('it asks who you are', !!(await page.$('#vPick button[data-vch="whatsapp"]')));

  // ── the whole point: five impatient taps ─────────────────────────────────
  console.log('\n  Five impatient taps, the way the founder described\n');
  const wa = await page.$('#vPick button[data-vch="whatsapp"]');
  const em = await page.$('#vPick button[data-vch="email"]');
  await wa.click();
  // force:true, because a disabled button is exactly what we are testing - Playwright would
  // otherwise wait for it to become clickable and hide the result.
  for (let i = 0; i < 4; i++) { await wa.click({ force: true }).catch(() => {}); }
  await em.click({ force: true }).catch(() => {});
  await page.waitForTimeout(600);

  check('exactly ONE code was asked for, not six — got ' + starts.length, starts.length === 1);
  check('and it was the way they pressed', starts[0] && starts[0].channel === 'whatsapp');

  // ── what the screen says while they wait ─────────────────────────────────
  const codeTxt = await page.innerText('#vCode');
  check('the code box is open', await page.isVisible('#vCode'));
  check('it says the code is on its way', (await page.innerText('#content')).includes(W.onWay));
  check('"send it again" is frozen', await page.isDisabled('#vAgainBtn'));
  check('and shows the wait counting down', /\d/.test(codeTxt) && codeTxt.includes(W.wait));
  check('the help is NOT shown while it is still coming',
        !(await page.isVisible('#vHelp')));

  console.log('\n  Once the wait is over\n');
  await page.waitForTimeout(3200);   // the fixture asks for a 3-second cooldown
  check('"send it again" comes back', !(await page.isDisabled('#vAgainBtn')));
  const againTxt = await page.innerText('#vAgainBtn');
  check('and says how many codes are left — ' + JSON.stringify(againTxt.trim()),
        againTxt.includes('3') && againTxt.includes(W.left));
  check('the help is shown now', await page.isVisible('#vHelp'));
  check('it names a number to call', (await page.innerText('#vHelp')).includes('98260 11116'));

  // ── out of codes ─────────────────────────────────────────────────────────
  console.log('\n  When they really are out of codes\n');
  MODE = (lang === 'hi') ? 'rate_hi' : 'rate';
  starts.length = 0;
  await page.click('#vAgainBtn');
  await page.waitForTimeout(500);
  const msg = await page.innerText('#vMsg');
  check('the message says how long the wait is, not "a little" — ' + JSON.stringify(msg.trim().slice(0, 60)),
        /22/.test(msg));
  check('and the button stays shut', await page.isDisabled('#vAgainBtn'));
  await page.click('#vAgainBtn', { force: true }).catch(() => {});
  await page.waitForTimeout(300);
  check('tapping it again reaches nobody', starts.length === 1);

  check('nothing was thrown on the way', errors.length === 0);
  if (errors.length) errors.forEach((e) => console.log('    [browser] ' + e));
  await ctx.close();
}

// A send that FAILED must not cost them a wait - the server deletes that row, so it cost them
// nothing, and making them sit out a minute for our outage is a punishment for our own fault.
async function runFailUnfreezes(browser, base) {
  console.log('\n── A send that fails must not cost them the wait ──\n');
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await ctx.newPage();
  await page.addInitScript(() => { try { localStorage.setItem('claim_lang', 'en'); } catch (e) {} });
  MODE = 'fail'; starts.length = 0;
  await page.goto(base + '/portal?token=test');
  await page.waitForTimeout(400);
  await page.click('#vPick button[data-vch="whatsapp"]');
  await page.waitForTimeout(600);
  check('the refusal is shown', (await page.innerText('#vMsg')).includes('could not send'));
  check('and the buttons are live again straight away',
        !(await page.isDisabled('#vPick button[data-vch="whatsapp"]')));
  check('so the other way can be tried at once',
        !(await page.isDisabled('#vPick button[data-vch="email"]')));
  await ctx.close();
}

(async () => {
  const server = serve();
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const base = 'http://127.0.0.1:' + server.address().port;
  const browser = await chromium.launch();
  await run(browser, base, 'hi');
  await run(browser, base, 'en');
  await runFailUnfreezes(browser, base);
  await browser.close();
  server.close();
  console.log('\n' + (failed ? failed + ' failed' : 'all passed'));
  process.exit(failed ? 1 : 0);
})();
