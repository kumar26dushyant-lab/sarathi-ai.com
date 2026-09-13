/* ─────────────────────────────────────────────────────────────────────────────
 * The ops screens, driven in a real browser.
 *
 * WHY THIS EXISTS. Three bugs reached the founder in one week, and all three were
 * invisible to the Python tests because all three lived ABOVE the engine, in the screen:
 *
 *   · a dialog with no close button — nobody had ever checked for one
 *   · Send reading state from a part of the page that had already been replaced
 *   · a fix that passed every unit test and still failed on the real claim, because
 *     the test built its rows differently from the way the endpoint does
 *
 * The engine tests pass on all three. Only a browser catches them. So this opens the
 * actual page, clicks the actual buttons, and fails when a button does nothing.
 *
 * SAFETY. Read-only against production by default. It stops at every point where a real
 * message or a real change would go out — it opens the read-back screen and does NOT press
 * send; it opens the handover dialog and does NOT hand over. Anything that writes is behind
 * --allow-writes, which is off unless you ask for it.
 *
 * Usage:  node flow.mjs                      (against https://nidaanpartner.com)
 *         node flow.mjs --base=http://…      (against a throwaway instance)
 *         node flow.mjs --headed             (watch it work)
 * ───────────────────────────────────────────────────────────────────────────── */
import { chromium } from 'playwright';
import { execFileSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';

const arg = (n, d) => {
  const hit = process.argv.find(a => a.startsWith(`--${n}=`));
  return hit ? hit.split('=').slice(1).join('=') : d;
};
const has = n => process.argv.includes(`--${n}`);

const BASE = arg('base', 'https://nidaanpartner.com');
const HEADED = has('headed');
const SHOTS = 'screenshots';

const pass = [], fail = [];
function chk(cond, msg, detail) {
  (cond ? pass : fail).push(msg + (detail && !cond ? ` — ${detail}` : ''));
  console.log(`  ${cond ? 'PASS ' : 'FAIL '} ${msg}${detail && !cond ? ` — ${detail}` : ''}`);
}

/* A real signed-in session. The token is minted on the server the same way the app does it,
 * so this is a genuine staff session and not a test back door.
 *
 * The script travels base64-encoded: it passes through a Windows shell, ssh, and a remote shell
 * before Python sees it, and every one of those has its own opinion about quotes and newlines. */
function tokenFor(role) {
  const py = `
import sys, sqlite3, json
sys.path.insert(0, '/opt/sarathi')
import biz_nidaan as n
c = sqlite3.connect('/opt/sarathi/sarathi_biz.db')
r = c.execute("SELECT staff_id, name, role FROM nidaan_staff WHERE role=? AND status='active' "
              "AND deleted_at IS NULL LIMIT 1", (${JSON.stringify(role)},)).fetchone()
c.close()
print(json.dumps({"t": n.create_staff_token(r[0], r[2], r[1]), "name": r[1], "role": r[2]})
      if r else "null")`;
  const b64 = Buffer.from(py, 'utf8').toString('base64');
  const out = execFileSync('ssh', ['root@84.247.172.252',
    `cd /opt/sarathi && set -a && . ./biz.env 2>/dev/null; set +a; ` +
    `echo ${b64} | base64 -d | /opt/sarathi/venv/bin/python -`],
    { encoding: 'utf8', timeout: 60000 });
  const line = out.trim().split('\n').filter(Boolean).pop();
  return JSON.parse(line);
}

async function openOps(browser, who) {
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  // Seed the session exactly as a real login does, before any script runs.
  await ctx.addInitScript(tok => {
    try { localStorage.setItem('nidaan_ops_token', tok); } catch (e) {}
  }, who.t);
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e.message || e)));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  await page.goto(`${BASE}/nidaan/ops`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForSelector('#sidebarNav a, .nav-item, [onclick*="showPanel"]', { timeout: 30000 })
    .catch(() => {});
  return { ctx, page, errors };
}

const shot = (page, name) =>
  page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: false }).catch(() => {});

/* Open a panel and wait until it has actually finished loading, rather than for a fixed guess.
 * Several panels fetch before they draw, and a fixed wait either flakes or wastes minutes. */
async function openPanel(page, key, ms = 12000) {
  await page.evaluate(k => window.showPanel && window.showPanel(k), key);
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    const t = await page.evaluate(k => {
      const el = document.getElementById('panel-' + k);
      return el ? (el.innerText || '').trim() : null;
    }, key);
    if (t === null) return { missing: true };
    if (t.length > 20 && !/^(loading|…|⏳)/i.test(t) && !/^loading/i.test(t)) {
      return { text: t, waited: Date.now() - t0 };
    }
    await page.waitForTimeout(300);
  }
  const t = await page.evaluate(k =>
    ((document.getElementById('panel-' + k) || {}).innerText || '').trim(), key);
  return { text: t, timedOut: true, waited: ms };
}

/* Every dialog must offer a way out. This is the check that would have caught the handover
 * popup the founder could not close on his phone. */
async function assertEscapable(page, label) {
  const info = await page.evaluate(() => {
    const bg = document.querySelector('.modal-bg.open');
    if (!bg) return null;
    const x = bg.querySelector('.modal-x');
    const btns = Array.from(bg.querySelectorAll('.modal-footer button')).map(b => b.textContent.trim());
    const exit = btns.some(t => /^(cancel|close|not now|go back|keep it|done|later|dismiss)/i.test(t));
    return { hasX: !!x && x.offsetParent !== null, btns, exit };
  });
  if (!info) { chk(false, `${label}: a dialog should be open and is not`); return false; }
  chk(info.hasX, `${label}: has an ✕ in the corner`);
  chk(info.exit, `${label}: has a button that leaves`, `buttons were: ${info.btns.join(' / ')}`);
  // And Escape genuinely closes it.
  await page.keyboard.press('Escape');
  await page.waitForTimeout(250);
  const stillOpen = await page.evaluate(() => !!document.querySelector('.modal-bg.open'));
  chk(!stillOpen, `${label}: Escape closes it`);
  return true;
}

async function run() {
  mkdirSync(SHOTS, { recursive: true });
  console.log(`\nDriving ${BASE} in a real browser${HEADED ? ' (headed)' : ''}\n`);

  const sa = tokenFor('super_admin');
  const ss = tokenFor('sub_super_admin');
  console.log(`  signed in as: ${sa.name} (${sa.role}) and ${ss.name} (${ss.role})\n`);

  const browser = await chromium.launch({ headless: !HEADED });

  /* ── 1. every panel opens, and none of them throws ───────────────────────── */
  console.log('── every screen opens ──');
  let { ctx, page, errors } = await openOps(browser, sa);
  const panels = ['desk', 'l2', 'board', 'bdesign', 'whatsapp', 'cp', 'claims',
                  'l2claims', 'onbehalf', 'leave', 'payfollow', 'support', 'radar'];
  for (const p of panels) {
    errors.length = 0;
    const state = await openPanel(page, p);
    if (state.missing) { chk(false, `${p}: panel exists`); continue; }
    chk(!state.timedOut && state.text.length > 20, `${p} finishes loading`,
        state.timedOut ? `still showing "${state.text.slice(0, 40)}" after ${state.waited}ms`
                       : (state.text.slice(0, 60) || '(empty)'));
    chk(!/super admin only|failed to load|could not load|something went wrong/i.test(state.text),
        `${p} is not an error page`, state.text.slice(0, 70));
    chk(errors.length === 0, `${p} throws no script error`, errors[0]);
  }
  await shot(page, 'panels');

  /* ── 2. the Bucket Designer opens a bucket and its dialogs escape ────────── */
  console.log('\n── bucket designer ──');
  errors.length = 0;
  await page.evaluate(() => window.showPanel && window.showPanel('bdesign'));
  await page.waitForTimeout(1400);
  const nBuckets = await page.evaluate(() => document.querySelectorAll('.bdcard').length);
  chk(nBuckets >= 5, `the designer lists the buckets (${nBuckets})`);
  const firstKey = await page.evaluate(() => {
    const b = document.querySelector('.bdcard button[onclick^="bdToggle"]');
    return b ? b.getAttribute('onclick').match(/'([^']+)'/)[1] : '';
  });
  if (firstKey) {
    await page.evaluate(k => window.bdToggle(k), firstKey);
    await page.waitForTimeout(500);
    const opened = await page.evaluate(() => !!document.querySelector('.bdedit'));
    chk(opened, 'a bucket opens for editing');
    const canAdd = await page.evaluate(() =>
      !!document.querySelector('.bdedit button[onclick*="bdFieldEdit"]'));
    chk(canAdd, 'and offers to add a field');
    if (canAdd) {
      await page.evaluate(() =>
        document.querySelector('.bdedit button[onclick*="bdFieldEdit"]').click());
      await page.waitForTimeout(500);
      await assertEscapable(page, 'new-field dialog');
    }
  }
  chk(errors.length === 0, 'the designer throws no script error', errors[0]);

  /* ── 3. the pending-document window, up to but not through Send ─────────── */
  console.log('\n── pending documents ──');
  errors.length = 0;
  const claimId = await page.evaluate(async () => {
    const r = await API('/l2/pending-handover');
    if (!r.ok) return 0;
    const d = await r.json();
    return (d.claims && d.claims[0] && d.claims[0].claim_id) || 0;
  });
  chk(claimId > 0, `found a claim to work with (NP-${claimId})`);
  if (claimId) {
    await page.evaluate(id => window.dwOpen(id), claimId);
    await page.waitForTimeout(1800);
    const win = await page.evaluate(() => ({
      open: !!document.querySelector('.modal-bg.open'),
      docs: document.querySelectorAll('.dwd').length,
      people: document.querySelectorAll('.dwp').length,
      wa: !!document.getElementById('dwWa'),
      em: !!document.getElementById('dwEm'),
      msg: ((document.getElementById('dwMsg') || {}).value || '').length,
    }));
    chk(win.open, 'the document window opens');
    chk(win.docs > 0, `with documents listed (${win.docs})`);
    chk(win.people > 0, `and the people it goes to (${win.people})`);
    chk(win.wa && win.em, 'with both channel tick-boxes');
    chk(win.msg > 40, `and a drafted message (${win.msg} chars)`);
    await shot(page, 'docwindow');

    // Adding a person must produce a card with its own Remove — the founder saw two broken
    // half-rows and no remove at all.
    await page.evaluate(() => window.dwExtraAdd());
    await page.waitForTimeout(400);
    const ex = await page.evaluate(() => {
      const c = document.querySelectorAll('.dwex');
      return { cards: c.length,
               inputs: c[0] ? c[0].querySelectorAll('input').length : 0,
               remove: c[0] ? !!c[0].querySelector('button[onclick*="dwExtraDel"]') : false };
    });
    chk(ex.cards === 1, 'adding a person makes one card');
    chk(ex.inputs === 3, 'with name, mobile and email', `saw ${ex.inputs} inputs`);
    chk(ex.remove, 'and its own Remove button');
    await page.evaluate(() => window.dwExtraDel(0));
    await page.waitForTimeout(300);
    chk(await page.evaluate(() => document.querySelectorAll('.dwex').length) === 0,
        'and Remove actually removes it');

    // THE BUG: open the read-back, and the channels must survive the screen being replaced.
    await page.evaluate(() => window.dwCheck());
    await page.waitForTimeout(2200);
    const rb = await page.evaluate(() => {
      const t = (document.getElementById('modalTitle') || {}).textContent || '';
      const body = (document.getElementById('modalBody') || {}).innerText || '';
      return { title: t, body,
               snapChannels: (typeof _dwSnap !== 'undefined' && _dwSnap && _dwSnap.channels) || [],
               snapDocs: ((typeof _dwSnap !== 'undefined' && _dwSnap && _dwSnap.doc_keys) || []).length };
    });
    chk(/read it back/i.test(rb.title), 'the read-back screen opens', rb.title);
    chk(rb.snapChannels.length === 2,
        'and the channels survived the screen being replaced',
        `snapshot had: [${rb.snapChannels}]`);
    chk(rb.snapDocs > 0, `with the document list intact (${rb.snapDocs})`);
    chk(!/pick at least one way/i.test(rb.body),
        'and it does NOT say "pick at least one way to send it"');
    // Every document being asked for must be named in the words the customer reads.
    chk(!/does not mention/i.test(rb.body),
        'the message names every document it asks for');
    await shot(page, 'readback');
    await assertEscapable(page, 'read-back screen');
  }
  chk(errors.length === 0, 'the document window throws no script error', errors[0]);

  /* ── 4. the handover dialog — opens, and never traps ─────────────────────── */
  console.log('\n── handover ──');
  errors.length = 0;
  if (claimId) {
    await page.evaluate(id => window.hoOpen && window.hoOpen(id), claimId);
    await page.waitForTimeout(1800);
    const ho = await page.evaluate(() => {
      const body = (document.getElementById('modalBody') || {}).innerText || '';
      return { open: !!document.querySelector('.modal-bg.open'), body,
               note: !!document.getElementById('hoNote') };
    });
    chk(ho.open, 'the handover dialog opens');
    chk(ho.note, 'with a note box');
    chk(!/fee has not been paid/i.test(ho.body),
        'and does not claim the fee is unpaid on a covered claim');
    await shot(page, 'handover');
    await assertEscapable(page, 'handover dialog');
  }
  chk(errors.length === 0, 'the handover throws no script error', errors[0]);

  /* ── 5. the same screens as a sub-super-admin ────────────────────────────── */
  console.log('\n── as a sub-super-admin ──');
  await ctx.close();
  ({ ctx, page, errors } = await openOps(browser, ss));
  for (const p of ['whatsapp', 'l2', 'desk', 'cp']) {
    errors.length = 0;
    const st = await openPanel(page, p);
    const txt = st.text || '';
    chk(!/super admin only/i.test(txt), `${ss.name} is not refused from ${p}`,
        txt.slice(0, 80));
    chk(!st.timedOut && txt.length > 20, `${p} finishes loading for them`,
        st.timedOut ? `stuck on "${txt.slice(0, 40)}"` : '');
    chk(errors.length === 0, `${p} throws no script error for them`, errors[0]);
  }
  const waBits = await page.evaluate(() => {
    const el = document.getElementById('panel-whatsapp');
    const t = (el && el.innerText) || '';
    // Check for the CONTROLS, not the words: "bulk campaigns" also appears in the screen's own
    // one-line description, and a mention is not a button.
    return { inbox: /inbox/i.test(t),
             settings: !!document.getElementById('waEnabled'),
             campaign: !!document.getElementById('wcName'),
             launch: !!document.querySelector('[onclick*="waLaunchCampaign"]') };
  });
  chk(waBits.inbox, 'a sub-super-admin sees the WhatsApp inbox');
  chk(!waBits.settings, 'but not the automation defaults');
  chk(!waBits.campaign && !waBits.launch, 'and no campaign controls at all');
  await shot(page, 'wa-subadmin');

  await ctx.close();
  await browser.close();

  console.log(`\n  ${pass.length} passed, ${fail.length} failed`);
  fail.forEach(f => console.log('   x ' + f));
  if (fail.length) process.exitCode = 1;
}

run().catch(e => { console.error('\nHARNESS ERROR:', e); process.exitCode = 2; });
