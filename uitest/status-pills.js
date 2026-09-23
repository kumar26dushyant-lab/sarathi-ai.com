// Are the status pills actually readable - in dark mode AND in light mode?
//
// Founder, 22 Sep: "currently a few status not visible correctly". Two different faults hid
// behind that one sentence, and only one of them was a colour:
//
//   - `review_delivered`, the status 115 of our claims are in, had no pill rule anywhere. It
//     rendered as a bare lowercase word. That is not a colour bug, it is a missing rule.
//   - `.s-in_negotiation` carried a hardcoded `#fde047` - pale yellow text on a pale-yellow
//     ground. Fine on dark, near-invisible on light, because the background variable moves with
//     the theme and the literal does not.
//
// So this measures rather than eyeballs: every pill is rendered in both themes and its real
// contrast ratio computed against what is actually behind it. WCAG AA for small bold text is
// 4.5:1; 3:1 is the large-text floor and is where a pill starts being guessed at rather than
// read. Below 3:1 fails here.
//
//   node status-pills.js

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const OPS = fs.readFileSync(path.join(__dirname, '..', 'static', 'nidaan_ops.html'), 'utf8');
const DASH = fs.readFileSync(path.join(__dirname, '..', 'static', 'nidaan_dashboard.html'), 'utf8');
const DESIGN = fs.readFileSync(path.join(__dirname, '..', 'static', 'nidaan_design.css'), 'utf8');

// The COLOURS now live once in nidaan_design.css. What each page still owns is the pill's shape -
// ops draws a rectangle, the dashboard a rounded pill - so that is what gets pulled out here.
// Still a search rather than "the first <style>": nidaan_ops.html has five style blocks and the
// first is 55 characters long, which once gave every status an identical ratio and looked like a
// pass.
function pillCss(src, name, shapeClass) {
  const blocks = [...src.matchAll(/<style>([\s\S]*?)<\/style>/g)].map((m) => m[1]);
  const hit = blocks.find((b) => b.includes('.' + shapeClass + '{'));
  if (!hit) { console.error('no stylesheet in ' + name + ' defines .' + shapeClass); process.exit(1); }
  return hit;
}

// The pills, by how much they should ask of you. This is the founder's own reading of the list:
// a claim waiting on somebody outside is the only thing that should shout.
const LOUD = 'review_query', LIVE = 'in_review', DONE = 'review_delivered';

// Every status the app can show, offered or retired.
const STATUSES = [
  'intimated', 'assigned', 'in_review', 'review_query', 'review_query_resolved',
  'review_delivered', 'withdrawn', 'in_negotiation', 'resolved_won', 'resolved_lost', 'closed',
];

const FLOOR = 3.0;   // below this a pill is guessed at, not read

let failed = 0;
const check = (label, ok) => { console.log((ok ? '  PASS  ' : '  FAIL  ') + label); if (!ok) failed++; };

function harness(pageCss, pillClass) {
  return `<!doctype html><html><head><meta charset="utf-8">
<style>${DESIGN}</style>
<style>${pageCss}</style>
<style>body{margin:0;padding:1rem;background:var(--nd-bg-base)}
  .row{padding:.35rem 0}</style>
</head><body>
${STATUSES.map((s) => `<div class="row"><span class="${pillClass} s-${s}" id="p-${s}">${s}</span></div>`).join('\n')}
</body></html>`;
}

// The colour actually painted behind an element, walking up through anything transparent - a
// pill's own background is a 12% wash, so the page behind it is most of what you see.
const MEASURE = (ids) => {
  const parse = (c) => {
    const m = /rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/.exec(c || '');
    return m ? [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4]] : null;
  };
  const over = (fg, bg) => [0, 1, 2].map((i) => fg[i] * fg[3] + bg[i] * (1 - fg[3]));
  const lum = (c) => {
    const f = c.map((v) => {
      const x = v / 255;
      return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2];
  };
  const out = {};
  ids.forEach((id) => {
    const el = document.getElementById('p-' + id);
    if (!el) { out[id] = null; return; }
    // Solid ground first: walk up until something is opaque.
    let ground = [255, 255, 255];
    for (let n = el.parentElement; n; n = n.parentElement) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c[3] === 1) { ground = [c[0], c[1], c[2]]; break; }
    }
    const own = parse(getComputedStyle(el).backgroundColor);
    const bg = own ? over(own, ground) : ground;
    const fgc = parse(getComputedStyle(el).color) || [0, 0, 0, 1];
    const fg = over(fgc, bg);
    const a = lum(fg), b = lum(bg);
    const g = lum(ground);
    out[id] = {
      ratio: (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05),
      // How far the pill's own fill sits from the page behind it. A solid fill lands high, an
      // 18% tint in the middle, a 7% tint barely above 1. This is "weight" as a number.
      presence: (Math.max(b, g) + 0.05) / (Math.min(b, g) + 0.05),
      colour: getComputedStyle(el).color,
    };
  });
  return out;
};

async function measure(page, pageName, pageCss, pillClass) {
  await page.setContent(harness(pageCss, pillClass));
  const results = {};
  for (const theme of ['dark', 'light']) {
    await page.evaluate((t) => { document.documentElement.setAttribute('data-theme', t); }, theme);
    await page.waitForTimeout(60);
    results[theme] = await page.evaluate(MEASURE, STATUSES);
  }
  console.log('\n── ' + pageName + ' ──\n');
  console.log('  ' + 'status'.padEnd(24) + 'dark'.padEnd(10) + 'light'.padEnd(11)
              + 'weight (dark / light)');
  for (const s of STATUSES) {
    const d = results.dark[s], l = results.light[s];
    if (!d || !l) { check(s + ' — no pill rendered at all', false); continue; }
    const line = '  ' + s.padEnd(24)
      + (d.ratio.toFixed(2) + ':1').padEnd(10)
      + (l.ratio.toFixed(2) + ':1').padEnd(11)
      + d.presence.toFixed(2) + ' / ' + l.presence.toFixed(2);
    const ok = d.ratio >= FLOOR && l.ratio >= FLOOR;
    console.log(line + (ok ? '' : '   <-- too faint'));
    check(pageName + ': ' + s + ' is readable in BOTH modes', ok);
  }

  // The hierarchy itself. Readability is necessary and was never the complaint - the complaint
  // was that nothing stood out, and that is a statement about the gaps between these three.
  console.log('');
  // Compared on distance from 1, not on the ratio itself: a contrast ratio of 1.0 means the fill
  // is INDISTINGUISHABLE from the page, so 1.22 against 1.11 is twice the presence, not a tenth
  // more of it. Multiplying the ratios instead made a real two-fold gap look like a failure.
  const weight = (x) => x.presence - 1;
  for (const theme of ['dark', 'light']) {
    const r = results[theme];
    if (!r[LOUD] || !r[LIVE] || !r[DONE]) continue;
    check(pageName + ' / ' + theme + ': a blocked claim outweighs one in progress',
          weight(r[LOUD]) > weight(r[LIVE]) * 3);
    check(pageName + ' / ' + theme + ': one in progress outweighs one already settled',
          weight(r[LIVE]) > weight(r[DONE]) * 1.6);
  }
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 500, height: 900 } });
  await measure(page, 'ops workspace',
                pillCss(OPS, 'nidaan_ops.html', 'pill-status'), 'pill-status');
  await measure(page, 'subscriber dashboard',
                pillCss(DASH, 'nidaan_dashboard.html', 'status-pill'), 'status-pill');
  await browser.close();
  console.log('\n' + (failed ? failed + ' failed' : 'all readable in both modes'));
  process.exit(failed ? 1 : 0);
})();
