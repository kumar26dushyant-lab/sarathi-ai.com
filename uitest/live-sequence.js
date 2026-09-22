// The Live Cases screen asks for the founder's fifteen, in his order, down the page.
//
// Five of them are columns on the claim, not bucket fields, which is why the list used to have
// ten and the order never matched. This renders the real l2CaseRender and reads the labels back
// in the order they appear.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const PAGE = process.argv[2] || path.join(__dirname, '..', 'static', 'nidaan_ops.html');
const src = fs.readFileSync(PAGE, 'utf8');

function cut(from, to, label) {
  const a = src.indexOf(from);
  const b = src.indexOf(to, a);
  if (a < 0 || b < 0) { console.error('anchor missing: ' + label); process.exit(1); }
  return src.slice(a, b);
}

const gist = cut('const CSR_GIST = [', 'const CSR_DRAFT_FACTS', 'CSR_GIST');
const render = cut('function l2CaseRender(rem){', 'function l2MoveFromCase(', 'l2CaseRender');

const WANT = ['Company Name', 'Policy type', 'Policy No.', 'Policy inception Date',
  'Disputed Amount', 'Name Of Hospital', 'Date of Admission', 'Date Of Discharge',
  'Diagnosis', 'Patient Complaint', 'Claim No.', 'Rejection Date', 'Rejection Reason',
  'Comment', 'Assign To'];

// The bucket's own fields, as the server sends them.
const FIELDS = [
  ['hospital_name', 'Name Of Hospital', 'text'], ['admission_date', 'Date of Admission', 'date'],
  ['discharge_date', 'Date Of Discharge', 'date'], ['diagnosis', 'Diagnosis', 'textarea'],
  ['patient_complaint', 'Patient Complaint', 'textarea'],
  ['insurer_claim_no', 'Claim No.', 'text'], ['rejection_date', 'Rejection Date', 'date'],
  ['rejection_reason', 'Rejection Reason', 'textarea'], ['gist_comments', 'Comment', 'textarea'],
  ['case_email', 'Case email', 'text'], ['case_email_password', 'Case email password', 'text'],
].map(([k, l, t]) => ({ field_key: k, label_en: l, field_type: t, active: 1, required_exit: 0 }));

const harness = `<!doctype html><meta charset="utf-8"><body>
<div id="modalTitle"></div><div id="modalBody"></div>
<script>
function esc(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function _insuredLabel(){ return 'Patient'; }
function _escCreds(){ return '<div id="escCreds">the case email block</div>'; }
function _escPanel(){ return ''; }
function _escFlags(){ return ''; }
function _qBadge(){ return ''; }
function _l2BuiltSoFar(){ return ''; }
function _l2RichEditor(){ return ''; }
function _l2AssignPanel(){ return '<div id="assignPanel"></div>'; }
function _l2Err(){ return ''; }
function docView(){} function docsOpen(){} function l2SetSub(){} function l2QuerySend(){}
function l2QueryRaise(){} function l2QueryResolve(){} function l2MoveFromCase(){}
function l2MoveMenuCase(){} function l2RequestChange(){} function l2Start(){}
function l2ShowSecret(){} function l2Core(){} function l2Field(){} function l2SetType(){}
function l2SetOwner(){} function _l2DateEdit(){} function _l2DateCommit(){}
function csrGist(){} function csrDraft(){} function csrSheet(){} function csrReport(){}
var _l2Handlers = [{staff_id:7,name:'Ashwin Kaushal'}];
var L2_TYPES = ['health','motor','life','travel','property','marine','other'];
var _role='super_admin';
window.NidaanInsurers = { mount: function(id){ document.getElementById(id).innerHTML =
  '<select id="' + id + '_pick"><option>Star Health</option></select>'; }, value: function(){ return 'Star Health'; } };
${gist}
var _l2Case = {claim_id: 39, claim: {complainant_name:'Garvit Arjun Jain', insured_name:'Garvit Arjun Jain',
  insurer_name:'Care Health', claim_type:'health', policy_no:'80913811',
  policy_inception_date:'2017-03-04', disputed_amount:733356, assigned_to_staff_id:7},
  files: [], st: {in_pipeline:true, bucket:'live_cases', sub:'', substates:[], values:{},
  fields: ${JSON.stringify(FIELDS)}, guide:{}, contact:{}, query:{}, back:{}, moves:[]}};
${render}
l2CaseRender([]);
</script></body>`;

let failed = 0;
const check = (label, ok) => { console.log((ok ? '  PASS  ' : '  FAIL  ') + label); if (!ok) failed++; };

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  page.on('pageerror', (e) => console.log('  [browser error] ' + e.message.split('\n')[0]));
  await page.route('**/seq', (r) =>
    r.fulfill({ status: 200, contentType: 'text/html', body: harness }));
  await page.goto('http://x/seq');
  await page.waitForTimeout(150);

  const labels = await page.evaluate(() =>
    Array.from(document.querySelectorAll('#modalBody .l2fld > label'))
      .map((l) => l.textContent.replace('*', '').trim()));

  console.log('\nWhat the screen asks for, top to bottom\n');
  labels.forEach((l, i) => console.log('  ' + String(i + 1).padStart(2) + '. ' + l));

  console.log('');
  check('all fifteen are on the screen', WANT.every((w) => labels.includes(w)));
  const got = labels.filter((l) => WANT.includes(l));
  check('and they are in his order',
        JSON.stringify(got) === JSON.stringify(WANT));
  check('the case email is not asked for a second time',
        !labels.includes('Case email'));
  check('nor its password', !labels.includes('Case email password'));

  console.log('\nEach one keeps the control that suits it\n');
  check('the company is the shared picker', !!(await page.$('#lfins_box_pick')));
  check('the policy type is a closed list', !!(await page.$('#lf_claim_type')));
  check('Assign To offers the people who draft',
        (await page.textContent('#lf_assigned_to')).includes('Ashwin Kaushal'));
  check('the disputed amount is a number box',
        (await page.getAttribute('#lf_core_disputed_amount', 'type')) === 'number');
  check('the dates wait until you have finished typing',
        (await page.getAttribute('#lf_admission_date', 'onchange')).includes('_l2DateEdit'));

  await browser.close();
  console.log('\n' + (failed ? failed + ' failed' : 'all passed'));
  process.exit(failed ? 1 : 0);
})();
