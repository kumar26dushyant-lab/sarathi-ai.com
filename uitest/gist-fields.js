// The real gist, lifted out of the page and rendered.
//
// What has to be true: fifteen lines, in the founder's order, with his words; a closed list for
// the company and the policy type; the people who prepare drafts on Assign To; and nothing
// asking for the things he took off the list.
const fs = require('fs');
const path = require('path');
const src = fs.readFileSync((process.argv[2] || path.join(__dirname, '..', 'static', 'nidaan_ops.html')), 'utf8');

function block(from, to) {
  const a = src.indexOf(from);
  const b = src.indexOf(to, a);
  if (a < 0 || b < 0) { console.error('anchor missing: ' + from); process.exit(1); }
  return src.slice(a, b);
}

const code =
  block('const CSR_GIST = [', 'const CSR_DRAFT_FACTS') +
  block('const CSR_CHOICES = {', 'function _csrStyles()') +
  block('function _csrVal(kind, key){', 'function _csrAllLocked(') +
  block('let _csrEditing = null;', 'function _csrPaint()') +
  block('function _csrInput(f){', '// Admission and discharge police each other');

let CSR = null;
const esc = (x) => String(x == null ? '' : x).replace(/&/g, '&amp;').replace(/</g, '&lt;');
const make = () => new Function(
  'esc', '_csrLocked', '_csrClaim', 'L2_TYPES', '_l2Handlers', 'window', 'getCsr',
  'const _csr = getCsr();' + code +
  '; return {body:_csrGistBody, line:_csrLine, input:_csrInput, gist:CSR_GIST};'
)(esc, (k) => !!(CSR && (CSR.locked || {})[k]), 65,
  ['health', 'motor', 'life', 'travel', 'property', 'marine', 'other'],
  [{ staff_id: 7, name: 'Ashwin Kaushal' }, { staff_id: 9, name: 'Annapurna Kasera' }],
  { NidaanInsurers: { list: ['Star Health and Allied Insurance Co. Ltd.', 'HDFC ERGO General Insurance Co. Ltd.'] } },
  () => CSR);

let failed = 0;
const check = (label, ok) => { console.log((ok ? '  PASS  ' : '  FAIL  ') + label); if (!ok) failed++; };

CSR = {
  insurer_name: 'STAR HEALTH', claim_kind: 'health', policy_no: 'P/123',
  policy_inception_date: '2024-04-01', disputed_amount: 197000, assigned_to: 7,
  handler: 'Ashwin Kaushal', locked: {},
  fields: { hospital_name: 'Apollo', admission_date: '2026-08-08', discharge_date: '2026-08-10',
            diagnosis: 'Dengue', patient_complaint: 'Fever', insurer_claim_no: 'CIR/2026/1',
            rejection_date: '2026-09-01', rejection_reason: 'Pre-existing', gist_comments: 'ok' },
};
let api = make();

console.log('\nThe fifteen, in his order and his words\n');
const want = ['Company Name', 'Policy type', 'Policy No.', 'Policy inception Date',
  'Disputed Amount', 'Name Of Hospital', 'Date of Admission', 'Date Of Discharge', 'Diagnosis',
  'Patient Complaint', 'Claim No.', 'Rejection Date', 'Rejection Reason', 'Comment', 'Assign To'];
check('exactly fifteen', api.gist.length === 15);
const got = api.gist.map((f) => f[0]);
check('in the right order: ' + (JSON.stringify(got) === JSON.stringify(want) ? 'yes' : JSON.stringify(got)),
      JSON.stringify(got) === JSON.stringify(want));

console.log('\nWhat he took off the list is not asked for\n');
const keys = api.gist.map((f) => f[2]);
check('no "On behalf of"', !keys.includes('relationship'));
check('no old ClaimShield "Claim Type"', !keys.includes('rejection_type'));
check('no case email', !keys.includes('case_email'));
check('no case email password', !keys.includes('case_email_password'));
check('no Patient / Complainant - those are at the top of the claim',
      !keys.includes('insured_name') && !keys.includes('complainant_name'));

console.log('\nAt rest, it reads as a page\n');
const body = api.body();
check('the company is shown', body.includes('STAR HEALTH'));
check('the amount reads as money', body.includes('₹1,97,000'));
check('the policy type is shown in words', /Policy type[\s\S]{0,120}health/.test(body));
check('Assign To shows the person, not a number', body.includes('Ashwin Kaushal'));
check('every line offers a change', (body.match(/Change/g) || []).length >= 15);

console.log('\nThe company uses the ONE shared picker, not a second copy of it\n');
let h = api.input(api.gist[0]);
check('it is a mount point for the shared component',
      h.includes('csr_core_insurer_name_box'));
check('and not a hand-rolled dropdown', !/<select/.test(h));

console.log('\nPolicy type and Assign To are closed lists too\n');
h = api.input(api.gist[1]);
check('policy type is a dropdown', /<select/.test(h));
check('health is selected', /value="health" selected/.test(h));
check('and nothing outside the list is offered', !/value="cargo"/.test(h));
h = api.input(api.gist[14]);
check('Assign To is a dropdown', /<select/.test(h));
check('it offers the people who prepare drafts', h.includes('Annapurna Kasera'));
check('and "nobody yet" for an unassigned claim', h.includes('nobody yet'));

console.log('\nFinished work shows a lock, not a pencil\n');
CSR.locked = { hospital_name: 'Pending Draft' };
api = make();
const b2 = api.body();
check('the hospital line is locked', /Name Of Hospital[\s\S]{0,200}Locked/.test(b2));
check('and the others are still editable', (b2.match(/Change/g) || []).length >= 14);

console.log('\n' + (failed ? failed + ' failed' : 'all passed'));
process.exit(failed ? 1 : 0);
