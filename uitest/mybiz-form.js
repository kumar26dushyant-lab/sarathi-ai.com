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

// Since 2 Oct the form is the shared intake block (nidaan_intake.js) plus the channel-partner
// choice - so this mounts THAT, exactly as the ops page does, and measures it.
if (!OPS.includes("NidaanIntake.mount('mbcCore'") || !OPS.includes('<div id="mbcCore"></div>')) {
  console.error('the My Business form no longer mounts the shared block'); process.exit(1);
}
const INS = fs.readFileSync(path.join(__dirname, '..', 'static', 'nidaan_insurers.js'), 'utf8');
const INTAKE = fs.readFileSync(path.join(__dirname, '..', 'static', 'nidaan_intake.js'), 'utf8');

const page = (w) => `<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>${DESIGN}</style>
<style>body{margin:0;padding:8px;background:var(--nd-bg-base);font-family:system-ui,sans-serif}</style></head><body>
<div style="max-width:${w}px"><div id="mbcCore"></div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:.55rem;margin-top:.7rem">
    <select id="mbcAssociate" style="min-height:44px"><option>Channel Partner (optional)…</option></select></div></div>
<script>${INS}<\/script><script>${INTAKE}<\/script>
<script>NidaanIntake.mount('mbcCore', {lang:'en', letterUrl:'/x', headers:function(){return {};}, allowNoLetter:true});<\/script>
</body></html>`;

const IDS = ['mbcCore_insured_name', 'mbcCore_insured_phone', 'mbcCore_insured_email',
             'mbcCore_complainant_name', 'mbcCore_complainant_phone', 'mbcCore_complainant_email',
             'mbcCore_claim_type', 'mbcCore_ins', 'mbcCore_disputed_amount', 'mbcCore_policy_no', 'mbcAssociate'];

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
    await pg.route('https://nidaanpartner.com/f', (r) => r.fulfill({ status: 200, contentType: 'text/html; charset=utf-8', body: page(width) }));
    await pg.route('**/nidaan/api/intake/types', (r) => r.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ types: [{ code: 'health', en: 'Health / Mediclaim', hi: 'स्वास्थ्य' }] }) }));
    await pg.goto('https://nidaanpartner.com/f');
    await pg.waitForSelector('#mbcCore_claim_type option[value="health"]', { state: 'attached' });

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
    const ins = boxes.mbcCore_ins, amt = boxes.mbcCore_disputed_amount;
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
