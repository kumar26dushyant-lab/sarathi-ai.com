// The bucket screen's furniture: tabs that are empty, chips that repeat the rows, and 136
// claims that are not Level-2 work sitting above the 21 that are.
//
// Founder, 24 Sep, three questions in one: "why we are showing them? ... what purpose they are
// solving? ... how better we can manage these statuses/filters without overbuilding but keep
// things simple?"
//
// Answered with live numbers, then built. What is pinned here is the behaviour that makes each
// one safe rather than merely tidier:
//
//   - a sub-state tab appears when something is behind it, AND the tab you are standing on
//     always stays — otherwise moving the last claim out of a tab makes that tab vanish while
//     you are looking at it.
//   - the summary chips appear when the pile is too big to read, but a DEADLINE (a closing
//     Lokpal window, a claim past its limit) shows at any size. A deadline you only notice on a
//     busy day is not a deadline.
//   - "N in this bucket" is gone: it repeated the sidebar button that had just been clicked.
//
// The helpers are lifted out of the page and run directly.
//
//   node uitest/bucket-chrome.js

const fs = require('fs');
const path = require('path');

const OPS = fs.readFileSync(path.join(__dirname, '..', 'static', 'nidaan_ops.html'), 'utf8');

let failed = 0;
const t = (label, ok, detail) => {
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label);
  if (!ok) { failed++; if (detail) console.log('           ' + detail); }
};

// ── the sub-state tab rule, as written in the page ──────────────────────────
function liveSubs(subs, sc, current) {
  return subs.filter((s) => (sc[s.sub_key] || 0) > 0 || current === s.sub_key);
}

console.log('\nThe bucket screen\n');

const drafting = [
  { sub_key: 'drafting', name_en: 'Drafting' },
  { sub_key: 'with_mo', name_en: 'With Medical Officer' },
  { sub_key: 'draft_query', name_en: 'Draft Query' },
  { sub_key: 'approved', name_en: 'Approved' },
];

// Pending Draft on the live data he was looking at: 3 claims, all drafting.
let shown = liveSubs(drafting, { drafting: 3 }, '');
t('four tabs for three claims in one state becomes one tab',
  shown.length === 1 && shown[0].sub_key === 'drafting',
  shown.map((s) => s.sub_key).join(', '));

// Live Cases: twelve claims, none carrying a sub-state.
shown = liveSubs([{ sub_key: 'a', name_en: 'A' }, { sub_key: 'b', name_en: 'B' }], {}, '');
t('a bucket whose claims use no sub-state shows no tabs at all', shown.length === 0);

// Escalation: genuinely used, so nothing changes.
const esc = [
  { sub_key: 'pending', name_en: 'Escalation Pending' },
  { sub_key: 'esc_query', name_en: 'Escalation Query' },
  { sub_key: 'escalated', name_en: 'Escalated' },
];
shown = liveSubs(esc, { pending: 5, escalated: 1 }, '');
t('a bucket that DOES use its states keeps them',
  shown.length === 2 && shown.map((s) => s.sub_key).join() === 'pending,escalated',
  shown.map((s) => s.sub_key).join(', '));
t('...and the empty one in the middle is dropped', !shown.some((s) => s.sub_key === 'esc_query'));

// THE TRAP: standing on a tab whose last claim just moved away.
shown = liveSubs(esc, { pending: 5 }, 'escalated');
t('the tab you are STANDING ON survives going empty',
  shown.some((s) => s.sub_key === 'escalated'),
  shown.map((s) => s.sub_key).join(', '));

// ── the chip rule ───────────────────────────────────────────────────────────
// `let ban =` sits BEFORE this block in the file, so slicing to it gave an empty string
// and five checks passed on nothing. Slice forward to the next landmark instead.
const _chipA = OPS.indexOf('const _qOpen =');
const chipSrc = OPS.slice(_chipA, OPS.indexOf('const guide =', _chipA));
if (_chipA < 0 || !chipSrc.trim()) { console.error('could not find the chip block'); process.exit(1); }
// The emitted MARKUP, not the phrase — the comment explaining the removal contains the words.
t('"in this bucket" is gone', !chipSrc.includes('in this bucket</span>'));
t('a deadline shows at any size — closing window is outside the size gate',
  /_urgent\s*=\s*pill\(d\.closing_window/.test(chipSrc), chipSrc.slice(0, 120));
t('...and so is past-the-limit', /_urgent[\s\S]{0,120}past the limit/.test(chipSrc));
t('the descriptive chips are gated on the pile being big',
  /_rest\s*=\s*!_big\s*\?\s*''/.test(chipSrc));
t('...and the gate is a screenful, not a guess', /_big\s*=.*>=\s*10/.test(chipSrc));
t('no chips at all when there is nothing to say',
  /\(_urgent \|\| _rest\)/.test(chipSrc));

// ── Before Level-2 ──────────────────────────────────────────────────────────
const railSrc = OPS.slice(OPS.indexOf("'<div class=\"l2rh\">The buckets</div>'") - 1200,
                          OPS.indexOf("'<div class=\"l2main\"") + 40);
const posBuckets = railSrc.indexOf('The buckets');
const posPre = railSrc.indexOf('Before Level-2');
t('the buckets now come BEFORE the pre-Level-2 rail',
  posBuckets > -1 && posPre > -1 && posBuckets < posPre,
  `buckets@${posBuckets} pre@${posPre}`);
t('...folded, not deleted — the buttons are still built',
  OPS.includes('const preRail = pre.map('));
t('...and the folded line carries the total', OPS.includes('const preTotal ='));
t('...closed by default', /<details class="l2pre">/.test(OPS) && !/<details class="l2pre" open/.test(OPS));
t('...and the fold is styled in both themes (variables only, no literals)',
  /\.l2pre>summary\{[^}]*var\(--nd-text-muted\)/.test(OPS));

// ── the step picker ─────────────────────────────────────────────────────────
// Founder, 25 Sep: "where I can see or find the option to move in internal bucket status?"
// The tabs were only ever FILTERS. The mover is this picker on the claim — and it was hidden for
// Pending Draft, whose four configured steps left two ('with_mo', 'approved') that nothing in
// the codebase could set. Configured and unreachable.
const pickSrc = OPS.slice(OPS.indexOf('// The step picker is gone only where'),
                          OPS.indexOf('_escPanel(st, id)'));
t('the step picker is shown for Pending Draft again',
  pickSrc.length > 0 && !/st\.bucket !== 'pending_draft'/.test(pickSrc), pickSrc.slice(0, 200));
t('...and still hidden for Escalation, where the work decides the step',
  /st\.bucket !== 'escalation'/.test(pickSrc));
t('...and says it changes the step only, not the bucket',
  /the claim stays where it is/.test(pickSrc));

// The automatic state must not be offered by hand, but must still show when a claim is in it —
// otherwise the dropdown silently disagrees with the row it is sitting on.
const autoSrc = OPS.slice(OPS.indexOf('const _autoSub ='), OPS.indexOf('// Rich-text fields'));
t('the query flow keeps ownership of draft_query',
  /_autoSub\s*=\s*\{pending_draft:\s*\['draft_query'\]\}/.test(autoSrc), autoSrc.slice(0, 160));
t('...but it still appears when the claim is already in it',
  /_autoFor\.indexOf\(s\.sub_key\) < 0 \|\| st\.sub === s\.sub_key/.test(autoSrc));

console.log('\n' + (failed ? `${failed} failed`
  : 'tabs appear when used, chips when needed, buckets first, steps settable'));
process.exit(failed ? 1 : 0);
