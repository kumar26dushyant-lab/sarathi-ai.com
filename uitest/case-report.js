// #6 - the case report, built by the page's own function and read back.
const fs = require('fs');
const path = require('path');
const src = fs.readFileSync((process.argv[2] || path.join(__dirname, '..', 'static', 'nidaan_ops.html')), 'utf8');

function block(from, to) {
  const a = src.indexOf(from);
  const b = src.indexOf(to, a);
  if (a < 0 || b < 0) { console.error('anchor missing: ' + from); process.exit(1); }
  return src.slice(a, b);
}

let printed = null;
const esc = (x) => String(x == null ? '' : x).replace(/&/g, '&amp;').replace(/</g, '&lt;');

const code = block('function _csrDate(v){', 'function _csrPrint(') +
  '\nfunction _csrPrint(t, b){ printed = {title: t, body: b}; }\n' +
  block('async function csrSheet(claimId){', 'window.csrGist = csrGist;');

const api = new Function('esc', 'ndUI', '_csrRichHTML', 'setPrinted', 'getCsr', `
  let printed = null;
  let _csr = getCsr();
  async function _csrLoad(){ _csr = getCsr(); return _csr; }
  ${code}
  return {sheet: csrSheet, report: csrReport, printed: () => printed};
`.replace(/printed = \{title: t, body: b\};/, 'printed = {title: t, body: b}; setPrinted(printed);'))(
  esc, { toast: () => {} }, (v) => String(v || ''), (v) => { printed = v; },
  () => ({
    claim_id: 44, handler: 'Ashwin Kaushal', insured_name: 'Kraparam Panwar',
    complainant_name: 'Kraparam Panwar', insurer_name: 'Star Health', claim_kind: 'health',
    policy_no: 'P/9', policy_inception_date: '2024-04-01', disputed_amount: 197000,
    created_at: '2026-09-01', remarks: [], manager: '', channel_partner: '',
    fields: { hospital_name: 'Apollo', admission_date: '2026-08-08',
              discharge_date: '2026-08-10', diagnosis: 'Dengue', patient_complaint: 'Fever',
              insurer_claim_no: 'CIR/1', rejection_date: '2026-09-01',
              rejection_reason: 'Pre-existing', gist_comments: 'strong case' },
  }));

let failed = 0;
const check = (label, ok) => { console.log((ok ? '  PASS  ' : '  FAIL  ') + label); if (!ok) failed++; };

(async () => {
  await api.report(44);
  const body = printed.body;

  console.log('\nThe case details run 1 to 15, in his order\n');
  const want = ['Company Name', 'Policy type', 'Policy No.', 'Policy inception Date',
    'Disputed Amount', 'Name Of Hospital', 'Date of Admission', 'Date Of Discharge',
    'Diagnosis', 'Patient Complaint', 'Claim No.', 'Rejection Date', 'Rejection Reason',
    'Comment', 'Assign To'];
  const at = want.map((w) => body.indexOf('<b>' + w + ' :'));
  check('every one of the fifteen is on the report', at.every((i) => i >= 0));
  check('and they are in that order',
        at.every((v, i) => i === 0 || v > at[i - 1]));

  console.log('\nWhat it says\n');
  check('the company', body.includes('Star Health'));
  check('the policy type, in words', /Policy type :<\/b> health/.test(body));
  check('the amount', body.includes('197000'));
  check('dates the way a person writes them', body.includes('08-08-2026'));
  check('who will prepare the draft', /Assign To :<\/b> Ashwin Kaushal/.test(body));

  console.log('\nNothing is said twice\n');
  check('the company appears once', (body.match(/Star Health/g) || []).length === 1);
  check('the claim number appears once', (body.match(/CIR\/1/g) || []).length === 1);
  check('the rejection reason appears once',
        (body.match(/Pre-existing/g) || []).length === 1);

  console.log('\nFields that are no longer collected are not printed blank\n');
  check('no "Medical Officer" line', !body.includes('Medical Officer'));
  check('no "Approved On" line', !body.includes('Approved On'));
  check('no old "Claim Type" line', !/<b>Claim Type :/.test(body));

  console.log('\nThe money is its own section\n');
  check('there is a Money heading', body.includes('>Money<'));
  check('and a Case details heading', body.includes('>Case details<'));
  check('processing fees are still there', body.includes('Processing Fees'));

  console.log('\nThe assessment sheet drops what it can no longer fill\n');
  await api.sheet(44);
  const sheet = printed.body;
  check('no empty RELATIONSHIP line', !sheet.includes('RELATIONSHIP'));
  check('the policy type takes its place', sheet.includes('TYPE OF POLICY'));
  check('and the rest of the sheet is untouched', sheet.includes('NAME OF PATIENT'));

  console.log('\n' + (failed ? failed + ' failed' : 'all passed'));
  process.exit(failed ? 1 : 0);
})();
