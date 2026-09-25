// The notification switches, in a real browser, on a phone.
//
// Founder, 25 Sep: "per event per role and per event per specific user involved, of course claim
// level settings will take precedence ... just so I should not depend on notification thing on
// you every time to do code changes."
//
// A tickbox that renders, accepts a click and reaches nothing looks exactly like one that works.
// The Python verifier proves the wiring exists in the source; only a browser proves the row
// actually draws one, that a locked row draws none, that a refused save puts the tick back, and
// that the whole thing is usable on a phone - which is the standing rule for every change.
//
// Nothing here touches a server. The page is loaded from disk and every API call is answered by
// this file, so it is safe to run at any hour, including while the team is working.
//
//   node uitest/notify-switches.js            (add --headed to watch)

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const HEADED = process.argv.includes('--headed');
const PAGE = path.join(__dirname, '..', 'static', 'nidaan_ops.html');

let ok = 0, bad = 0;
const t = (label, cond, detail) => {
  console.log((cond ? '  PASS  ' : '  FAIL  ') + label + (!cond && detail ? '\n           ' + detail : ''));
  cond ? ok++ : bad++;
};

// Four notifications is enough to prove the shape: one ordinary, one locked, and two more so a
// group has rows either side of the locked one.
const REGISTRY = {
  lock_reason: { en: 'Money, security and system health are never switched off.' },
  events: [
    { key: 'claim.status', group: 'claims', group_label: 'Claims', label: 'Claim status changed',
      who: 'Whoever is on the claim', channels: 'Telegram, bell', locked: false },
    { key: 'claim.assigned', group: 'claims', group_label: 'Claims', label: 'Claim assigned',
      who: 'The person it went to', channels: 'Telegram, bell', locked: false },
    { key: 'payment.failed', group: 'money', group_label: 'Money', label: 'A payment failed',
      who: 'Super admins', channels: 'Telegram, email, bell', locked: true },
    { key: 'bucket.move', group: 'claims', group_label: 'Claims', label: 'Claim moved a bucket',
      who: 'Whoever is on the claim', channels: 'Telegram, bell', locked: false },
  ],
  // Somebody has already switched one off. The screen must show that, not just the default.
  prefs: [{ scope: 'role', role: 'team_member', event_key: 'bucket.move', channel: '*',
            enabled: 0, frequency: 'off' }],
};

(async () => {
  const browser = await chromium.launch({ headless: !HEADED });
  // A real phone, because the founder's rule is that every change works on one.
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true,
  });
  const page = await ctx.newPage();

  const posted = [];
  let refuseNext = false;

  // Everything the page might ask for is answered here; nothing leaves this machine.
  await ctx.route('**/nidaan/ops/api/**', async route => {
    const req = route.request();
    const url = new URL(req.url());
    if (url.pathname.endsWith('/notifications/registry')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(REGISTRY) });
    }
    if (url.pathname.endsWith('/notifications/prefs') && req.method() === 'POST') {
      posted.push(JSON.parse(req.postData() || '{}'));
      if (refuseNext) {
        refuseNext = false;
        return route.fulfill({ status: 403, contentType: 'application/json',
                               body: JSON.stringify({ detail: 'Super admins only' }) });
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) });
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
  // The page loads a couple of its own files; serve them from disk too.
  await ctx.route('**/static/**', async route => {
    const f = path.join(__dirname, '..', 'static', path.basename(new URL(route.request().url()).pathname));
    if (fs.existsSync(f)) return route.fulfill({ status: 200, path: f });
    return route.fulfill({ status: 200, body: '' });
  });

  const errors = [];
  page.on('pageerror', e => errors.push(String(e.message || e)));
  page.on('console', m => {
    if (m.type() !== 'error') return;
    const txt = m.text();
    // Two kinds of noise this harness creates itself, neither a fault in the page:
    //  - nothing outside this machine is reachable, so the page's external scripts cannot load;
    //  - the 403 is the refusal we ask for on purpose, to prove the tick goes back.
    if (/ERR_NAME_NOT_RESOLVED|ERR_INTERNET_DISCONNECTED/.test(txt)) return;
    if (/403 \(Forbidden\)/.test(txt)) return;
    errors.push('console: ' + txt);
  });

  await ctx.route(u => u.pathname === '/nidaan/ops',
    r => r.fulfill({ status: 200, contentType: 'text/html; charset=utf-8', body: fs.readFileSync(PAGE, 'utf8') }));
  await page.goto('http://nidaanpartner.test/nidaan/ops', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof window.loadNotificationRegistry === 'function', { timeout: 20000 });

  // Show the real Settings panel and draw into it, rather than signing in: this suite is about
  // these rows, and the panel it must work inside is the one already in the page.
  await page.evaluate(() => {
    document.documentElement.classList.add('ops-has-token');
    document.getElementById('appShell').style.display = '';   // the shell a real login reveals
    document.getElementById('panel-settings').style.display = 'block';
    return window.loadNotificationRegistry();
  });
  await page.waitForSelector('input[onchange^="npToggle"]', { timeout: 10000 });

  console.log('\nThe switches, on a 390px phone\n');

  const boxes = page.locator('#panel-settings input[onchange^="npToggle"]');
  t('every switchable notification draws a tickbox for all three jobs',
    await boxes.count() === 9, 'found ' + await boxes.count() + ', expected 3 rows x 3 jobs');

  const lockedRow = page.locator('#panel-settings tr', { hasText: 'payment.failed' });
  t('the money notification draws no tickbox at all',
    await lockedRow.locator('input').count() === 0);
  t('...and says why, with the lock',
    (await lockedRow.textContent() || '').includes('\u{1F512}'));

  // bucket.move is off for team_member in the stub, and on for the other two jobs.
  const moveRow = page.locator('#panel-settings tr', { hasText: 'bucket.move' });
  const moveBoxes = moveRow.locator('input');
  t('a switch somebody already set shows as unticked', await moveBoxes.nth(2).isChecked() === false);
  t('...and only for that job', await moveBoxes.nth(0).isChecked() === true
                                && await moveBoxes.nth(1).isChecked() === true);
  const statusRow = page.locator('#panel-settings tr', { hasText: 'claim.status' });
  t('a notification nobody has touched is ticked - the default is ON',
    await statusRow.locator('input').nth(0).isChecked() === true);

  // Tap it the way a person on a phone does.
  await statusRow.locator('input').nth(2).click();
  await page.waitForFunction(() => true);
  t('tapping it sends exactly one save', posted.length === 1, JSON.stringify(posted));
  t('...addressed to the job, the notification and both channels',
    posted[0] && posted[0].scope === 'role' && posted[0].role === 'team_member'
    && posted[0].event_key === 'claim.status' && posted[0].channel === '*'
    && posted[0].enabled === false && posted[0].frequency === 'off', JSON.stringify(posted[0]));

  // A refusal must not leave a tick claiming something that did not happen.
  refuseNext = true;
  await statusRow.locator('input').nth(1).click();
  await page.waitForFunction(() => !document.querySelector('#panel-settings input:disabled'), { timeout: 5000 });
  t('a refused save puts the tickbox back where it was',
    await statusRow.locator('input').nth(1).isChecked() === true);

  // The phone rule: the page itself must never scroll sideways. The table may, inside its own box.
  const sideways = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth);
  t('the page does not scroll sideways on a phone', sideways <= 1, sideways + 'px over');
  t('...because the table scrolls inside its own box instead',
    await page.evaluate(() => {
      const tb = document.querySelector('#panel-settings table');
      return !!tb && getComputedStyle(tb.parentElement).overflowX === 'auto';
    }));

  // On a phone the job columns are only reachable by scrolling sideways. If the name goes with
  // them you are ticking a box with no idea which notification it belongs to.
  const stuck = await page.evaluate(() => {
    const tb = document.querySelector('#panel-settings table');
    const box = tb.parentElement;
    box.scrollLeft = box.scrollWidth;                 // all the way to the job columns
    const cell = tb.querySelector('tbody td');
    return { cellLeft: Math.round(cell.getBoundingClientRect().left),
             boxLeft: Math.round(box.getBoundingClientRect().left),
             scrolled: box.scrollLeft > 0,
             text: cell.textContent.trim().slice(0, 30) };
  });
  t('scrolled to the far side, the notification name is still on screen',
    stuck.scrolled && stuck.cellLeft >= stuck.boxLeft - 1, JSON.stringify(stuck));

  // A tap target too small to hit is the same as no control at all.
  const box = await statusRow.locator('input').nth(0).boundingBox();
  t('the tickbox is big enough to hit with a thumb (>=16px)',
    box && box.width >= 16 && box.height >= 16, box && (box.width + 'x' + box.height));

  // Both themes, because a control nobody can see in daylight is not a control.
  for (const theme of ['light', 'dark']) {
    await page.emulateMedia({ colorScheme: theme });
    await page.evaluate(th => document.documentElement.setAttribute('data-theme', th), theme);
    const seen = await page.evaluate(() => {
      const td = [...document.querySelectorAll('#panel-settings td')]
        .find(x => x.textContent.includes('\u{1F512}'));
      const cs = td && getComputedStyle(td);
      const bg = getComputedStyle(document.body).backgroundColor;
      return { fg: cs && cs.color, bg };
    });
    t(theme + ' mode: the lock cell has a colour of its own, not the background',
      !!seen.fg && seen.fg !== seen.bg, JSON.stringify(seen));
    await page.screenshot({ path: path.join(__dirname, 'screenshots', 'notify-switches-' + theme + '.png') })
      .catch(() => {});
  }

  t('the page threw nothing while doing all that', errors.length === 0, errors.join(' | '));

  await browser.close();
  console.log('\n' + (bad ? bad + ' failed' : ok + ' checks, the switches work on a phone in both themes'));
  process.exit(bad ? 1 : 0);
})();
