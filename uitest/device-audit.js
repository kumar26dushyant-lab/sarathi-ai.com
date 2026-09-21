// What does the ops workspace actually do on a phone, a tablet and a laptop?
//
// This renders the REAL bucket screen - the page's own l2RenderBucket(), with its own stylesheet
// - at the sizes people hold, and measures the things that make a screen unusable rather than
// merely ugly:
//
//   - the page scrolling sideways, which is the single worst thing a work screen can do on a
//     phone, because every row has to be dragged into view before it can be read;
//   - tap targets smaller than 44px, the size Apple and Google both publish, below which people
//     miss and tap again - and tapping again is exactly what the founder asked us to stop;
//   - text under 12px, which on a 360px screen in an office is not read, it is guessed at.
//
// It prints numbers, not opinions, so the same run can be made before and after a change.
//
//   node device-audit.js [path/to/nidaan_ops.html]

const fs = require('fs');
const path = require('path');
const { chromium, devices } = require('playwright');

const PAGE = process.argv[2] || path.join(__dirname, '..', 'static', 'nidaan_ops.html');
const src = fs.readFileSync(PAGE, 'utf8');

function cut(from, to, label) {
  const a = src.indexOf(from);
  if (a < 0) { console.error('could not find ' + label); process.exit(1); }
  const b = src.indexOf(to, a);
  if (b < 0) { console.error('could not find the end of ' + label); process.exit(1); }
  return src.slice(a, b);
}

// The page's own stylesheet, and the bucket screen's own styles.
const headCss = (src.match(/<style>([\s\S]*?)<\/style>/) || [])[1] || '';
// The product's real palette and type. Without it the screenshots come out in Times New Roman
// with no borders, which is a picture of something nobody uses.
const designCss = fs.readFileSync(path.join(__dirname, '..', 'static', 'nidaan_design.css'), 'utf8');
const l2Css = cut("  .l2wrap{display:flex", "`;\n  document.head.appendChild(st);", 'the L2 stylesheet');

// The real renderer and everything between it and the badges it calls. Taken as one contiguous
// slice rather than hand-picked pieces: a list of function names to extract is a list that goes
// stale, and a body that is never called costs nothing but has to PARSE, which is itself a check.
const code = cut('function l2RenderBucket(){', 'function l2RequestChange(', 'the L2 renderer');

const FIXTURE_ROWS = 6;

const SIZES = [
  { name: 'Android phone, small', w: 360, h: 740, touch: true },
  { name: 'iPhone 14',            w: 390, h: 844, touch: true },
  { name: 'iPhone 14 landscape',  w: 844, h: 390, touch: true },
  { name: 'iPad portrait',        w: 768, h: 1024, touch: true },
  { name: 'iPad landscape',       w: 1024, h: 768, touch: true },
  { name: 'Laptop',               w: 1440, h: 900, touch: false },
];

const harness = `<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<style>${designCss}</style>
<style>${headCss}</style>
<style>${l2Css}</style>
<style>
  /* What the product itself puts on the page. Dark is the default in nidaan_design.css. */
  html,body{margin:0;background:var(--nd-bg-base);color:var(--nd-text-primary);
    font-family:Inter,system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}
  .panel{padding:.8rem}
</style>
</head><body>
<div class="panel" id="panel"><div id="l2Main"></div></div>
<script>
// Only the names that live HIGHER UP nidaan_ops.html than the slice, so the slice does not
// declare them. Anything the slice does declare is assigned after it, never re-declared.
var _l2Sel = 'live_cases', _l2Sub = '', _l2Q = '', _l2Rows = [], _l2Rows2 = {};
var _role = 'super_admin', _staffId = 7, _l2Cfg = {waiting:0}, _l2View = 'table';
function esc(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function fmt(n){ return Number(n||0).toLocaleString('en-IN'); }
function _insuredLabel(){ return 'Patient'; }
function _l2Bucket(){ return {bucket_key:'live_cases', name_en:'Live Cases', icon:'\u{1f4cb}',
  red_days:6,
  guide_what:'A paid, winnable claim that somebody has started.',
  guide_do:'Fill the case gist and let the document checklist generate.',
  substates:[{sub_key:'a',name_en:'Step one'},{sub_key:'b',name_en:'Step two'}],
  moves:[{kind:'forward',to_key:'pending_draft',name_en:'Pending Draft'},
         {kind:'back',to_key:'intake',name_en:'Intake'}]}; }
function docsOpen(){} function l2Move(){} function l2MoveMenu(){} function l2Open(){}
function l2QueryRaise(){} function l2QueryResolve(){} function l2Sub(){} function l2Search(){}
function l2SetType(){} function l2SetOwner(){} function l2Export(){} function l2SetDuty(){}
function l2Pick(){} function loadL2(){} function _l2Rule(){ return {}; }

${code}

// A bucket as it actually looks on a working day: some claims late, one with a query, one
// pulled back, one inside the Lokpal window, and the long company name that is the real thing
// a narrow screen has to cope with.
_l2Handlers = [{staff_id:7,name:'Ashwin Kaushal'},{staff_id:9,name:'Annapurna Kasera'}];
_l2Rows = Array.from({length:${FIXTURE_ROWS}}, function(_,i){ return {
  claim_id: 100+i, who:'Kraparam Panwar', insured:'Kraparam Panwar',
  insurer_claim_no:'CIR/2026/201112/128284'+i, claim_type:'health',
  insurer:'Star Health and Allied Insurance Co. Ltd.', amount:197000+i,
  files:10, days:i*3, age_state:(i>3?'red':(i>1?'amber':'ok')),
  sub_name:'Step one', assigned_to:7, lokpal_days_left:(i===2?40:null),
  query:(i===1?{state:'open',by:'Ashwin',days:3}:{}),
  back:(i===4?{at:'x',by:'Boss',from:'Pending Draft',super:true}:{}),
  why:'Cannot move on until Rejection reason and Rejection date are recorded.',
  note:'Please chase the hospital for the signed discharge summary before Friday.',
  note_by:'Annapurna Kasera'
}; });
// late counts red AND amber, so it can never be smaller than red. The first version of
// this fixture said late:1 red:2, which made the summary render "-1 need looking at" -
// a fault in the test data that looked exactly like a fault in the page.
_l2Rows2 = {matching:${FIXTURE_ROWS}, red:2, late:4, sub_counts:{a:4,b:2},
  ours:3, short_docs:2, missing:1};

l2RenderBucket();
</script></body></html>`;

const THEME = process.env.THEME === 'light' ? 'light' : 'dark';

// How far apart two colours are, by the WCAG formula. Used for one question only: can this text
// be read on what is behind it?
const CONTRAST_FN = `(function(){
  function lum(c){
    var p = c.map(function(v){ v/=255; return v<=0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055,2.4); });
    return 0.2126*p[0] + 0.7152*p[1] + 0.0722*p[2];
  }
  function rgb(s){
    var m = String(s).match(/rgba?\\(([^)]+)\\)/); if(!m) return null;
    var a = m[1].split(',').map(function(x){ return parseFloat(x); });
    return {c:[a[0],a[1],a[2]], a: a.length>3 ? a[3] : 1};
  }
  // The colour actually BEHIND an element: walk up until something is not transparent.
  function behind(el){
    var e = el;
    while (e && e !== document.documentElement){
      var b = rgb(getComputedStyle(e).backgroundColor);
      if (b && b.a > 0.35) return b.c;
      e = e.parentElement;
    }
    var root = rgb(getComputedStyle(document.body).backgroundColor);
    return root ? root.c : [255,255,255];
  }
  window.__contrast = function(){
    var out = [];
    Array.from(document.querySelectorAll('#l2Main *')).forEach(function(el){
      var own = Array.from(el.childNodes).filter(function(n){ return n.nodeType===3; })
        .map(function(n){ return n.textContent; }).join('').trim();
      if (!own) return;
      var st = getComputedStyle(el);
      if (st.visibility === 'hidden' || st.display === 'none' || parseFloat(st.opacity) < 0.3) return;
      var fg = rgb(st.color); if (!fg) return;
      var bg = behind(el);
      var l1 = lum(fg.c), l2 = lum(bg);
      var ratio = (Math.max(l1,l2) + 0.05) / (Math.min(l1,l2) + 0.05);
      out.push({ t: own.slice(0,26), r: +ratio.toFixed(2),
                 sel: el.tagName.toLowerCase() + (el.className ? '.' + String(el.className).split(' ')[0] : '') });
    });
    return out;
  };
})()`;

(async () => {
  const browser = await chromium.launch();
  let worst = 0;
  const report = [];

  for (const s of SIZES) {
    const ctx = await browser.newContext({
      viewport: { width: s.w, height: s.h },
      hasTouch: s.touch,
      isMobile: s.touch,
      deviceScaleFactor: s.touch ? 3 : 1,
    });
    const page = await ctx.newPage();
    page.on('pageerror', (err) => console.log('  [browser error] ' + err.message.split('\n')[0]));
    await page.route('**/audit', (r) =>
      r.fulfill({ status: 200, contentType: 'text/html', body: harness }));
    await page.goto('http://x/audit');
    if (THEME === 'light') await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'light'));
    await page.waitForTimeout(120);

    const m = await page.evaluate((MIN) => {
      const de = document.documentElement;
      const sideways = Math.max(0, de.scrollWidth - de.clientWidth);
      // Anything a finger is meant to hit.
      const hits = Array.from(document.querySelectorAll(
        'button, a[href], select, input, [onclick], .l2mv, .l2tab, .l2b'));
      const small = [];
      hits.forEach((el) => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return;          // not on screen
        if (r.height < MIN || r.width < MIN) {
          small.push({ t: (el.textContent || el.tagName).trim().slice(0, 28),
                       w: Math.round(r.width), h: Math.round(r.height) });
        }
      });
      // Text too small to read on a phone held at arm's length.
      const tiny = [];
      Array.from(document.querySelectorAll('#l2Main *')).forEach((el) => {
        if (!el.childNodes.length) return;
        // Only elements holding their OWN text, or a parent is blamed for its child.
        const own = Array.from(el.childNodes)
          .filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim();
        if (!own) return;
        const px = parseFloat(getComputedStyle(el).fontSize);
        if (px && px < 12) {
          tiny.push({ t: own.slice(0, 26), px: +px.toFixed(1),
                      sel: el.tagName.toLowerCase() + (el.className ? '.' + String(el.className).split(' ')[0] : '') });
        }
      });
      // Does a claim row read as one thing, or is it a strip you drag sideways?
      const tbl = document.querySelector('.table-wrap');
      const overflows = tbl ? Math.max(0, tbl.scrollWidth - tbl.clientWidth) : 0;
      // PROVE SOMETHING RENDERED. A measurement of an empty screen passes every check, which is
      // the most dangerous kind of green there is.
      const rows = document.querySelectorAll('#l2Main tbody tr, #l2Main .l2card').length;
      const text = (document.getElementById('l2Main') || {}).textContent || '';
      return { sideways, small, tiny, overflows, rows,
               head: text.trim().slice(0, 60),
               cols: document.querySelectorAll('thead th').length };
    // 44px is the FINGERTIP standard (Apple HIG, Material). A mouse is precise, and its
    // published minimum is 24px (WCAG 2.5.8). Measuring a laptop against 44 is measuring it
    // against the wrong thing, and a check that asks the wrong question gets ignored.
    }, s.touch ? 44 : 24);

    if (process.env.SHOTS) {
      const f = require('path').join(__dirname, 'screenshots',
        'bucket-' + s.w + 'x' + s.h + (s.touch ? '-touch' : '') + '-' + THEME + '.png');
      await page.screenshot({ path: f, fullPage: false });
    }
    // Colour is the same at every width, so it is asked once - on the phone, where the least
    // light and the worst screens are.
    if (s.w === 390) {
      await page.evaluate(CONTRAST_FN);
      const cs = await page.evaluate(() => window.__contrast());
      m.unreadable = cs.filter((x) => x.r < 3);
      m.dim = cs.filter((x) => x.r >= 3 && x.r < 4.5);
      m.checked = cs.length;
    }
    const bad = (m.sideways > 0 ? 1 : 0) + (m.overflows > 0 ? 1 : 0)
              + (m.small.length ? 1 : 0) + (m.tiny.length ? 1 : 0);
    worst += bad;
    report.push({ s, m });
    await ctx.close();
  }

  for (const { s, m } of report) {
    console.log('\n' + s.name + '  ' + s.w + '×' + s.h + (s.touch ? '  (touch)' : ''));
    if (!m.rows) {
      console.log('  ✗ NOTHING RENDERED - the numbers below would be a measurement of an '
                + 'empty screen.\n    screen says: "' + m.head + '"');
      continue;
    }
    console.log('  claims on screen             : ' + m.rows);
    console.log('  page scrolls sideways        : '
      + (m.sideways ? '✗ by ' + m.sideways + 'px' : '✓ no'));
    console.log('  the claim list drags sideways: '
      + (m.overflows ? '✗ by ' + m.overflows + 'px (' + m.cols + ' columns)' : '✓ no'));
    console.log('  tap targets under ' + (s.touch ? '44px (touch)' : '24px (mouse) ') + ': '
      + (m.small.length ? '✗ ' + m.small.length : '✓ none'));
    if (m.small.length) {
      const seen = new Set();
      m.small.slice(0, 40).forEach((x) => {
        const k = x.t + x.w + x.h;
        if (seen.has(k)) return; seen.add(k);
        console.log('        ' + (x.w + '×' + x.h).padEnd(9) + x.t);
      });
    }
    console.log('  text under 12px              : '
      + (m.tiny.length ? '✗ ' + m.tiny.length + ' (smallest '
          + Math.min(...m.tiny.map((x) => x.px)) + 'px)' : '✓ none'));
    if (m.tiny.length) {
      const seen = new Set();
      m.tiny.forEach((x) => {
        if (seen.has(x.sel + x.px)) return; seen.add(x.sel + x.px);
        console.log('        ' + (x.px + 'px').padEnd(9) + x.sel.padEnd(14) + x.t);
      });
    }
  }

  const col = report.find((r) => r.m.checked);
  if (col) {
    console.log('\nColour, in the ' + THEME + ' theme  (' + col.m.checked + ' pieces of text)');
    console.log('  unreadable, under 3:1        : '
      + (col.m.unreadable.length ? '\u2717 ' + col.m.unreadable.length : '\u2713 none'));
    col.m.unreadable.forEach((x) =>
      console.log('        ' + (x.r + ':1').padEnd(9) + x.sel.padEnd(16) + x.t));
    console.log('  faint, under 4.5:1           : '
      + (col.m.dim.length ? '\u26a0 ' + col.m.dim.length : '\u2713 none'));
    const seen = new Set();
    col.m.dim.forEach((x) => {
      if (seen.has(x.sel)) return; seen.add(x.sel);
      console.log('        ' + (x.r + ':1').padEnd(9) + x.sel.padEnd(16) + x.t);
    });
    worst += col.m.unreadable.length ? 1 : 0;
  }

  await browser.close();
  console.log('\n' + worst + ' problem area(s) across ' + SIZES.length + ' devices ('
    + THEME + ' theme)');
})();
