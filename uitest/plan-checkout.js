// The plan checkout opens for a new person, and what it says afterwards can be seen (audit, 2 Oct):
//   - someone who clicked "Choose Silver" and signed up had 'silver' stored BEFORE paying, so
//     switchPlan('silver') did nothing and the checkout never opened;
//   - every message after the payment sheet closed was written into a window already hidden.
//
//   node uitest/plan-checkout.js

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.join(__dirname, '..');
let failed = 0;
const check = (label, ok, detail) => {
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label);
  if (!ok) { failed++; if (detail !== undefined) console.log('           ' + String(detail).slice(0, 300)); }
};

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 375, height: 800 }, isMobile: true });
  await ctx.addInitScript(() => { try { localStorage.setItem('nidaan_token', 'x.y.z'); localStorage.setItem('nidaan_plan', 'silver'); } catch (e) {} });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.route('**/*', async (r) => {
    const u = new URL(r.request().url());
    if (u.pathname === '/nidaan/dashboard') return r.fulfill({ status: 200, contentType: 'text/html; charset=utf-8', body: fs.readFileSync(path.join(ROOT, 'static', 'nidaan_dashboard.html'), 'utf8') });
    if (u.pathname.startsWith('/static/')) {
      const f = path.join(ROOT, 'static', u.pathname.slice(8));
      if (fs.existsSync(f)) return r.fulfill({ status: 200, contentType: f.endsWith('.js') ? 'application/javascript' : 'text/css', body: fs.readFileSync(f) });
      return r.fulfill({ status: 404, body: '' });
    }
    if (u.hostname !== 'nidaanpartner.com') return r.fulfill({ status: 204, body: '' });
    if (u.pathname === '/nidaan/api/me') return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ account_id: 1, email: 'a@example.invalid', subscription: null }) });
    return r.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
  await page.goto('https://nidaanpartner.com/nidaan/dashboard');
  await page.waitForTimeout(600);
  await page.evaluate(() => { _meCache = { subscription: null }; });
  await page.evaluate(() => switchPlan('silver'));
  check('a new person who chose Silver (stored before paying) sees the checkout',
    await page.evaluate(() => document.getElementById('subscribeModal').classList.contains('open')));
  await page.evaluate(() => { _meCache = { subscription: { plan: 'silver' } }; closeSubscribeModal(); switchPlan('silver'); });
  check('...while someone who HAS Silver is not asked to buy it again',
    !(await page.evaluate(() => document.getElementById('subscribeModal').classList.contains('open'))));
  const shown = await page.evaluate(() => {
    closeSubscribeModal();
    const msg = document.getElementById('subMsg');
    _subShow(); msg.className = 'msg info'; msg.textContent = 'The payment was not completed.';
    return { open: document.getElementById('subscribeModal').classList.contains('open'),
             visible: getComputedStyle(msg).display !== 'none' && msg.offsetHeight > 0 };
  });
  check('a message after the payment sheet closes is on screen, not in a hidden window', shown.open && shown.visible,
    JSON.stringify(shown));
  check('nothing on the page says "you were NOT charged" without knowing it',
    !(await page.content()).includes('you were NOT charged'));
  // A plan that has ended: NEW claims frozen with the reason; nothing else touched (founder, 2 Oct).
  const ENT = { can_raise: false, reason: 'sub_expired', options: ['renew'],
                message_en: 'Your plan has ended, so a new claim cannot be raised.', message_hi: 'आपका प्लान ख़त्म हो चुका है।' };
  await page.route('**/nidaan/api/me', (r) => r.fulfill({ status: 200, contentType: 'application/json',
    body: JSON.stringify({ account_id: 1, email: 'a@example.invalid', subscription: null, entitlement: ENT,
                           account_state: { type: 'retail', active: true } }) }));
  await page.evaluate(() => { try { loadDashboard(); } catch (e) {} });
  await page.waitForTimeout(800);
  const fr = await page.evaluate(() => {
    const b = document.getElementById('newClaimBtn'), box = document.getElementById('entBanner');
    try { openModal(); } catch (e) {}
    return { disabled: !!(b && b.disabled), banner: box ? box.textContent : '', shown: box ? getComputedStyle(box).display : 'none',
             modal: document.getElementById('claimModal').classList.contains('open'),
             renew: !!(box && box.querySelector('.ent-btn')) };
  });
  check('a plan that has ended: "Raise a claim" is frozen', fr.disabled, JSON.stringify(fr));
  check('...with the reason on screen and a Renew button', fr.shown !== 'none' && /plan has ended|ख़त्म/.test(fr.banner) && fr.renew,
    JSON.stringify(fr));
  check('...and the claim form will not open even if called', !fr.modal, JSON.stringify(fr));
  check('no script errors', errors.length === 0, errors.join(' | '));
  await browser.close();
  console.log(failed ? '\n' + failed + ' failed' : '\nall passed');
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
