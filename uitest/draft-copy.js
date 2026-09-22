// What actually lands on the clipboard when somebody copies a draft?
//
// Founder, 22 Sep: copying the draft and pasting into Gmail gives a non-editable IMAGE instead
// of text. Gmail pastes an image when the clipboard offers one and no usable text/html - so the
// question is not "what does Gmail do", it is "what flavours does the copy put there".
//
// This renders the real editor with a real stored draft and reads the clipboard back, so the
// answer is a list of MIME types rather than a theory. Then it checks the Copy button puts
// BOTH text/html and text/plain there, which is what makes a paste editable and keeps the bold
// and the underlines.
//
//   node draft-copy.js

const fs = require('fs');
const http = require('http');
const path = require('path');
const { chromium } = require('playwright');

const OPS = fs.readFileSync(path.join(__dirname, '..', 'static', 'nidaan_ops.html'), 'utf8');
const DESIGN = fs.readFileSync(path.join(__dirname, '..', 'static', 'nidaan_design.css'), 'utf8');

// A real draft, in the shape the database actually stores them.
const DRAFT = '<p>To</p><p>Star Health Insurance Co Ltd</p>'
  + '<p>Subject:-Review request against rejection of my son\'s hospitalization Claim- SPARSH PATHAK</p>'
  + '<p><b>POLICY NUMBER: 9339112105061628</b></p>'
  + '<p>Dear Sir/Madam,</p>'
  + '<p>I am 6 years old Star Health Insurance Company\'s customer and paying continuous premium '
  + 'to company on time. <b><u>Whereas my policy is under Moratorium period and as per this IRDA '
  + 'policy clause company cannot reject any claim</u></b> of any customer who is running his '
  + 'policy since previous 5 years.</p>';

let failed = 0;
const check = (label, ok) => { console.log((ok ? '  PASS  ' : '  FAIL  ') + label); if (!ok) failed++; };

function cut(from, to, label) {
  const a = OPS.indexOf(from);
  const b = OPS.indexOf(to, a);
  if (a < 0 || b < 0) { console.error('anchor missing: ' + label); process.exit(1); }
  return OPS.slice(a, b);
}

const headCss = (OPS.match(/<style>([\s\S]*?)<\/style>/g) || [])
  .map((b) => b.replace(/<\/?style>/g, ''))
  .find((b) => b.includes('.csred{')) || '';

// The page's own copy helpers, taken as source rather than re-implemented here. From
// _draftPlainText, because l2CopyDraft calls both of the ones above it - and starting the slice
// at `function l2CopyDraft(` drops the `async` in front of it, which fails at parse time.
const copyFn = cut('function _draftPlainText(', '\nwindow.l2CopyDraft');

const PAGE = `<!doctype html><html><head><meta charset="utf-8">
<style>${DESIGN}</style><style>${headCss}</style>
<style>body{background:var(--nd-bg-base);padding:1rem}</style>
</head><body>
<div class="csrrt">
  <div class="csrbar"><button id="copyBtn" type="button">Copy</button></div>
  <div class="csred" contenteditable="true" id="lf_draft_en" data-key="draft_en"
       data-label="Draft">${DRAFT}</div>
</div>
<script>
function esc(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
var ndUI = { toast: function(m){ window.__toast = m; } };
${copyFn}
document.getElementById('copyBtn').onclick = function(){ l2CopyDraft('draft_en', this); };
</script></body></html>`;

function serve() {
  return http.createServer((req, res) => {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(PAGE);
  });
}

async function flavours(page) {
  return page.evaluate(async () => {
    try {
      const items = await navigator.clipboard.read();
      const out = [];
      for (const it of items) out.push(...it.types);
      return out;
    } catch (e) { return ['<could not read: ' + e.message + '>']; }
  });
}

(async () => {
  const server = serve();
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const base = 'http://127.0.0.1:' + server.address().port;

  const browser = await chromium.launch();
  const ctx = await browser.newContext();
  await ctx.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: base });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message.split('\n')[0]));
  await page.goto(base + '/');
  await page.waitForTimeout(200);

  // ── 1. what a plain select-all + Ctrl-C leaves behind ─────────────────────
  console.log('\nSelecting the draft by hand and copying\n');
  await page.evaluate(() => {
    const ed = document.getElementById('lf_draft_en');
    ed.focus();
    const r = document.createRange(); r.selectNodeContents(ed);
    const s = getSelection(); s.removeAllRanges(); s.addRange(r);
    document.execCommand('copy');
  });
  await page.waitForTimeout(200);
  const manual = await flavours(page);
  console.log('    flavours on the clipboard: ' + manual.join(', '));
  check('a hand copy carries text/html (formatting survives)', manual.includes('text/html'));
  check('and text/plain (a fallback that is still editable)', manual.includes('text/plain'));
  check('and NOT an image, which is what pastes as a picture',
        !manual.some((t) => t.startsWith('image/')));

  // ── 2. the Copy button ────────────────────────────────────────────────────
  console.log('\nPressing the Copy button\n');
  await page.evaluate(() => navigator.clipboard.writeText('cleared'));
  await page.click('#copyBtn');
  await page.waitForTimeout(400);
  const btn = await flavours(page);
  console.log('    flavours on the clipboard: ' + btn.join(', '));
  check('the button puts text/html there', btn.includes('text/html'));
  check('and text/plain', btn.includes('text/plain'));
  check('and no image flavour at all', !btn.some((t) => t.startsWith('image/')));

  const html = await page.evaluate(async () => {
    const items = await navigator.clipboard.read();
    for (const it of items) {
      if (it.types.includes('text/html')) return (await (await it.getType('text/html')).text());
    }
    return '';
  });
  const text = await page.evaluate(() => navigator.clipboard.readText());

  console.log('\n  the HTML flavour starts:  ' + JSON.stringify(html.slice(0, 90)));
  console.log('  the plain flavour starts: ' + JSON.stringify(text.slice(0, 90)));

  check('the bold survives', /<b>|<strong>|font-weight/i.test(html));
  check('the underline survives', /<u>|text-decoration/i.test(html));
  check('paragraphs survive, so it is not one run-on block', /<p[\s>]/i.test(html));
  check('the plain text keeps its line breaks', text.split('\n').length >= 5);
  check('the plain text is readable prose, not tags', !/[<>]/.test(text));
  check('it says it copied', !!(await page.evaluate(() => window.__toast)));
  check('nothing was thrown', errors.length === 0);
  if (errors.length) errors.forEach((e) => console.log('    [browser] ' + e));

  await browser.close();
  server.close();
  console.log('\n' + (failed ? failed + ' failed' : 'all passed'));
  process.exit(failed ? 1 : 0);
})();
