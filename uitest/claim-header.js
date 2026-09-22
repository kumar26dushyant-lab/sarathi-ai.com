// The real _l2KvHtml, lifted out of the page and rendered.
//
// What has to be true: a pencil beside each fact a person may correct, a lock and NO pencil
// beside one that is finished work, the phone left alone, and the claim's own wording for
// "Patient" kept.
const fs = require('fs');
const path = require('path');
const src = fs.readFileSync((process.argv[2] || path.join(__dirname, '..', 'static', 'nidaan_ops.html')), 'utf8');

function slice(from, to) {
  const a = src.indexOf(from);
  const b = src.indexOf(to, a);
  if (a < 0 || b < 0) { console.error('anchor not found: ' + from); process.exit(1); }
  return src.slice(a, b);
}
const code = slice('const L2_KV = [', 'function _l2KvPaint()');

let CASE = null;
const ctx = {
  esc: (s) => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;'),
  _insuredLabel: (t) => (t === 'motor' ? 'Vehicle owner' : 'Patient'),
  get _l2Case() { return CASE; },
};
const make = new Function('esc', '_insuredLabel', 'getCase',
  'const _l2Case = getCase();' + code + '; return {html:_l2KvHtml, show:_l2KvShow};');
const build = (c) => { CASE = c; return make(ctx.esc, ctx._insuredLabel, () => CASE).html(); };

let failed = 0;
const check = (label, ok) => { console.log((ok ? '  PASS  ' : '  FAIL  ') + label); if (!ok) failed++; };

const open = {
  claim_id: 65,
  claim: { complainant_name: 'KRAPARAM PANWAR', insured_name: 'KRAPARAM PANWAR',
           insurer_name: 'STAR HEALTH', disputed_amount: 197000, policy_no: '',
           complainant_phone: '9926680421', claim_type: 'health' },
  st: { moved_by: 'ASHWIN KAUSHAL', locked: {} },
};

console.log('\nA claim still being worked on\n');
let h = build(open);
check('a pencil on the complainant', /Change Complainant/.test(h));
check('a pencil on the patient', /Change Patient/.test(h));
check('a pencil on the insurance company', /Change Insurance Co\./.test(h));
check('a pencil on the disputed amount', /Change Disputed/.test(h));
check('a pencil on the policy number', /Change Policy No\./.test(h));
check('five pencils, no more', (h.match(/class="pen"/g) || []).length === 5);
check('the amount reads as money', /₹1,97,000/.test(h));
check('an empty policy number shows a dash, not "null" or "undefined"',
      h.includes('Policy No.</div><div class="vrow"><div class="v">—')
      && !/null|undefined/.test(h));
check('the phone is shown', /9926680421/.test(h));
check('and the phone has NO pencil - it is the number our messages go to',
      !/Change Phone/.test(h));
check('last moved by is shown and not editable',
      /ASHWIN KAUSHAL/.test(h) && !/Change Last moved by/.test(h));

console.log('\nThe same claim once the drafts are finished\n');
const locked = JSON.parse(JSON.stringify(open));
locked.st.locked = { complainant_name: 'Pending Draft', insured_name: 'Pending Draft',
                     insurer_name: 'Pending Draft', disputed_amount: 'Pending Draft',
                     policy_no: 'Pending Draft' };
h = build(locked);
check('no pencils at all', !/class="pen"/.test(h));
check('a lock is shown instead', (h.match(/class="lk"/g) || []).length === 5);
check('and the facts are still readable', /STAR HEALTH/.test(h));

console.log('\nA motor claim calls the insured something else\n');
const motor = JSON.parse(JSON.stringify(open));
motor.claim.claim_type = 'motor';
motor.st.locked = {};
h = build(motor);
check('it says Vehicle owner, not Patient', /Vehicle owner/.test(h) && !/>Patient</.test(h));

console.log('\n' + (failed ? failed + ' failed' : 'all passed'));
process.exit(failed ? 1 : 0);
