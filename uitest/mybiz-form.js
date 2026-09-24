// The "Raise a claim for a customer" form must not overlap itself, at any width.
//
// Founder, 24 Sep: "for mybusiness raise a claim for a customer, insurance company and disputed
// amount fields are overlapping, fix it."
//
// The cause was arithmetic, not taste: the grid gave each field a 150px track, and the insurer
// picker sat in a <span> with min-width:13rem (~208px). A grid child cannot shrink below its
// min-width, so that box spilled sideways over the Disputed-amount input beside it.
//
// Checked by MEASURING the rendered boxes rather than by reading the CSS, because the whole
// class of bug is "the CSS looks fine and the pixels disagree" — and at three widths, since an
// overlap that only appears on a phone is still an overlap. His standing rule: every change has
// to work on a phone.
//
//   node uitest/mybiz-form.js

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const OPS = fs.readFileSync(path.join(__dirname, '..', 'static', 'nidaan_ops.html'), 'utf8');
const DESIGN = fs.readFileSync(path.join(__dirname, '..', 'static', 'nidaan_design.css'), 'utf8');

// The form's own markup, lifted out of the template literal it lives in.
const start = OPS.indexOf('<input id="mbcName"');
const end = OPS.indexOf('<textarea id="mbcNotes"');
if (start < 0 || end < 0) { console.error('could not find the My Business form'); process.exit(1); }
let form = OPS.slice(OPS.lastIndexOf('<div style="display:grid', start), end);
// The template is interpolated at runtime; here the Hindi ternaries just become their English side.
form = form.replace(/\$\{hi\?'[^']*':'([^']*)'\}/g, '$1').replace(/\$\{[^}]*\}/g, '');

const page = (w) => `<!doctype html><html><head><meta charset="utf-8">
<style>${DESIGN}</style>
<style>body{margin:0;padding:8px;background:var(--nd-bg-base);font-family:system-ui,sans-serif}
 input,select,textarea{width:100%;box-sizing:border-box;padding:.5rem;border-radius:8px;
   border:1px solid var(--nd-border-strong);background:var(--nd-bg-surface-2);
   color:var(--nd-text-primary)}</style></head><body>
<div style="max-width:${w}px">${form}</div>
<script>
  // What NidaanInsurers.mount() puts in the box: a real select, full width.
  var b = document.getElementById('mbcInsurerBox');
  if (b) b.innerHTML = '<select style="width:100%"><option>Star Health and Allied Insurance Co. Ltd.</option></select>';
<\/script></body></html>`;

const IDS = ['mbcName', 'mbcPhone', 'mbcEmail', 'mbcType', 'mbcInsurerBox',
             'mbcAmount', 'mbcPolicy', 'mbcAssociate'];

let failed = 0;
const check = (label, ok, detail) => {
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label);
  if (!ok) { failed++; if (detail) console.log('           ' + detail); }
};

(async () => {
  const browser = await chromium.launch();
  const pg = await browser.newPage();
  console.log('\nRaise a claim for a customer\n');

  for (const width of [1280, 760, 360]) {
    await pg.setViewportSize({ width: Math.max(width, 360), height: 900 });
    await pg.setContent(page(width));
    await pg.waitForTimeout(80);

    const boxes = await pg.evaluate((ids) => {
      const out = {};
      ids.forEach((id) => {
        const el = document.getElementById(id);
        if (!el) return;
        const r = el.getBoundingClientRect();
        out[id] = { x: r.x, y: r.y, w: r.width, h: r.height, right: r.right, bottom: r.bottom };
      });
      out.__scroll = { doc: document.documentElement.scrollWidth,
                       client: document.documentElement.clientWidth };
      return out;
    }, IDS);

    const missing = IDS.filter((i) => !boxes[i]);
    check(`${width}px: every field is on the page`, !missing.length, missing.join(', '));
    if (missing.length) continue;

    // Any two fields that share a row must not sit on top of one another.
    const pairs = [];
    for (let i = 0; i < IDS.length; i++) {
      for (let j = i + 1; j < IDS.length; j++) {
        const a = boxes[IDS[i]], b = boxes[IDS[j]];
        const overlapX = Math.min(a.right, b.right) - Math.max(a.x, b.x);
        const overlapY = Math.min(a.bottom, b.bottom) - Math.max(a.y, b.y);
        if (overlapX > 1 && overlapY > 1) pairs.push(`${IDS[i]} ∩ ${IDS[j]}`);
      }
    }
    check(`${width}px: no two fields overlap`, !pairs.length, pairs.join(' · '));

    // The specific pair he reported.
    const ins = boxes.mbcInsurerBox, amt = boxes.mbcAmount;
    const ov = Math.min(ins.right, amt.right) - Math.max(ins.x, amt.x) > 1
            && Math.min(ins.bottom, amt.bottom) - Math.max(ins.y, amt.y) > 1;
    check(`${width}px: Insurance Company and Disputed amount are clear of each other`, !ov,
          `insurer x${Math.round(ins.x)}–${Math.round(ins.right)}, `
          + `amount x${Math.round(amt.x)}–${Math.round(amt.right)}`);

    check(`${width}px: the form does not scroll sideways`,
          boxes.__scroll.doc <= boxes.__scroll.client + 1,
          `${boxes.__scroll.doc} > ${boxes.__scroll.client}`);
  }

  await browser.close();
  console.log('\n' + (failed ? `${failed} failed` : 'the form holds at desktop, tablet and phone'));
  process.exit(failed ? 1 : 0);
})();
