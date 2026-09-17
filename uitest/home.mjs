/* The public homepage, measured at the widths people actually use.
 *
 * The founder's report (17 Sep): "on homepage top ribbon is messed up on web desktop, make it
 * properly aligned in all devices". The nav labels were breaking mid-phrase ("How It / Works")
 * because nothing stopped them wrapping, and the tablet width was still trying to fit eleven
 * items on one row.
 *
 * This checks the things that were actually wrong, at each size:
 *   - nothing spills off the side of the screen
 *   - the top bar is ONE row on a desktop, and no label is broken in two
 *   - below 1000px the bar is brand + burger, and the menu opens
 *
 * Usage:  node home.mjs                       (live)
 *         node home.mjs --local-html=../static/nidaan_index.html
 */
import { chromium } from 'playwright';
import { pathToFileURL } from 'url';
import path from 'path';

const arg = (n, d) => {
  const hit = process.argv.find(a => a.startsWith(`--${n}=`));
  return hit ? hit.split('=').slice(1).join('=') : d;
};
const BASE = arg('base', 'https://nidaanpartner.com');
const LOCAL = arg('local-html', '');
const pass = [], fail = [];
const chk = (c, m, extra) => { (c ? pass : fail).push(m); console.log((c ? '  PASS  ' : '  FAIL  ') + m + (c || !extra ? '' : ' — ' + extra)); };

const SIZES = [
  { name: 'desktop 1920', w: 1920, h: 1080, desktop: true },
  { name: 'laptop 1440',  w: 1440, h: 900,  desktop: true },
  { name: 'laptop 1280',  w: 1280, h: 800,  desktop: true },
  { name: 'laptop 1300',  w: 1300, h: 800,  desktop: true },   // just above the burger threshold
  { name: 'laptop 1240',  w: 1240, h: 800,  desktop: false },  // just below it
  { name: 'tablet 1024',  w: 1024, h: 768,  desktop: false },
  { name: 'tablet 820',   w: 820,  h: 1180, desktop: false },
  { name: 'iPhone 390',   w: 390,  h: 844,  desktop: false },
  { name: 'Android 360',  w: 360,  h: 800,  desktop: false },
];

async function run() {
  const browser = await chromium.launch();
  const url = LOCAL ? pathToFileURL(path.resolve(LOCAL)).href : `${BASE}/`;
  for (const s of SIZES) {
    const ctx = await browser.newContext({ viewport: { width: s.w, height: s.h },
                                           deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    await page.goto(url, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(700);
    // A first-time visitor meets two things before the page itself: the language popup and the
    // advisor/policyholder gate. Answer both the way a person would, so what we measure after is
    // the page they actually use.
    await page.evaluate(() => {
      try { window.chooseLang && window.chooseLang('en'); } catch (e) {}
      try { window.egChoose && window.egChoose('advisor'); } catch (e) {}
    });
    await page.waitForTimeout(300);

    const m = await page.evaluate(() => {
      const nav = document.querySelector('.nav-inner');
      const links = [...document.querySelectorAll('.nav-links a, .nav-links button')];
      // Text that wrapped occupies more than one client rect. Measuring the ELEMENT's height
      // instead counts padding as wrapping, which flagged the padded CRM button as broken when
      // it was on one line.
      const wrapped = links.filter(a => {
        if (a.offsetParent === null) return false;
        try {
          const r = document.createRange();
          r.selectNodeContents(a);
          // Several rects on the SAME line just means several child spans. Wrapping means the
          // text sits on more than one line, so count distinct tops.
          const tops = new Set([...r.getClientRects()].map(x => Math.round(x.top)));
          return tops.size > 1;
        } catch (e) { return false; }
      }).map(a => (a.textContent || '').trim().slice(0, 24));
      const burger = document.querySelector('.nav-burger');
      const chips = [...document.querySelectorAll('.path-chip')].filter(c => c.offsetParent !== null);
      return {
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        navHeight: nav ? Math.round(nav.getBoundingClientRect().height) : 0,
        wrapped,
        burgerShown: !!(burger && getComputedStyle(burger).display !== 'none'),
        linksShown: links.filter(a => a.offsetParent !== null).length,
        chipOverflow: chips.some(c => c.getBoundingClientRect().right > innerWidth + 1
                                   || c.getBoundingClientRect().left < -1),
      };
    });

    console.log(`\n── ${s.name} ──`);
    chk(m.overflow <= 2, `${s.name}: nothing spills off the side`, `${m.overflow}px wider than the screen`);
    chk(!m.chipOverflow, `${s.name}: the ribbon chips stay inside the screen`);
    if (s.desktop) {
      chk(m.wrapped.length === 0, `${s.name}: no menu label is broken in two`, m.wrapped.join(' | '));
      chk(m.navHeight <= 96, `${s.name}: the bar is one row (${m.navHeight}px)`);
      chk(!m.burgerShown, `${s.name}: the full menu is shown, no burger`);
    } else {
      chk(m.burgerShown, `${s.name}: the bar is brand + ☰`);
      // and the menu actually opens. The language popup can appear on a delay, after the first
      // dismissal - clear whatever is covering the bar before tapping, as a person would.
      await page.evaluate(() => {
        try { window.chooseLang && window.chooseLang('en'); } catch (e) {}
        try { window.egChoose && window.egChoose('advisor'); } catch (e) {}
        const ov = document.getElementById('langChooser'); if (ov) ov.remove();
      });
      await page.waitForTimeout(150);
      await page.click('.nav-burger');
      await page.waitForTimeout(350);
      const open = await page.evaluate(() => {
        const l = document.querySelector('.nav-links');
        return { shown: l && getComputedStyle(l).display !== 'none',
                 overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth };
      });
      chk(open.shown, `${s.name}: tapping ☰ opens the menu`);
      chk(open.overflow <= 2, `${s.name}: and the open menu still fits the screen`);
    }
    await ctx.close();
  }
  await browser.close();
  console.log(`\n  ${pass.length} passed, ${fail.length} failed`);
  fail.forEach(f => console.log('   x ' + f));
  if (fail.length) process.exitCode = 1;
}

run().catch(e => { console.error('\nHARNESS ERROR:', e); process.exitCode = 2; });
