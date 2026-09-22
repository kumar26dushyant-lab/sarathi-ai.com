// Pages 7 and 8, rendered from the page's own functions.
const fs = require('fs');
const path = require('path');
const src = fs.readFileSync((process.argv[2] || path.join(__dirname, '..', 'static', 'nidaan_ops.html')), 'utf8');

function block(from, to) {
  const a = src.indexOf(from);
  const b = src.indexOf(to, a);
  if (a < 0 || b < 0) { console.error('anchor missing: ' + from); process.exit(1); }
  return src.slice(a, b);
}

const esc = (x) => String(x == null ? '' : x).replace(/&/g, '&amp;').replace(/</g, '&lt;');
let failed = 0;
const check = (label, ok) => { console.log((ok ? '  PASS  ' : '  FAIL  ') + label); if (!ok) failed++; };

// ── the green line on the board ──────────────────────────────────────────────
const badge = new Function('esc', block('function _escBadge(i){', 'function _qBadge(q){')
  + '; return _escBadge;')(esc);

console.log('\nThe Escalation board says what was DONE\n');
const four = new Date(Date.now() - 4 * 86400000).toISOString().slice(0, 10);
let h = badge({ bucket: 'escalation', sub: 'escalated', escalation_date: four });
check('it says the claim is escalated', h.includes('Escalated on ' + four));
check('and how long ago, in days a person can check', /4 days ago/.test(h));
check('in green, because this is a step completed', h.includes('--nd-success-text'));

check('one day reads as "1 day", not "1 days"',
      /1 day ago/.test(badge({ bucket: 'escalation', sub: 'escalated',
        escalation_date: new Date(Date.now() - 86400000).toISOString().slice(0, 10) })));
check('a claim not yet escalated shows nothing',
      badge({ bucket: 'escalation', sub: 'pending', escalation_date: '' }) === '');
check('an escalated claim with no date shows nothing rather than "Invalid Date"',
      badge({ bucket: 'escalation', sub: 'escalated', escalation_date: '' }) === '');
check('rubbish in the date shows nothing',
      badge({ bucket: 'escalation', sub: 'escalated', escalation_date: 'not a date' }) === '');
check('and no other bucket gets this line',
      badge({ bucket: 'pending_draft', sub: 'drafting', escalation_date: four }) === '');

// ── the credentials ──────────────────────────────────────────────────────────
let CASE = null;
const credCode = block('function _escCreds(st){', 'async function escQuery(');
const makeCreds = () => new Function('esc', 'window', 'API', 'ndUI', '_l2Err', 'document', 'getCase',
  'const _l2Case = getCase();' + credCode + '; return {creds:_escCreds, line:_escCredLine};')(
  esc, {}, () => {}, { toast: () => {} }, () => '', { getElementById: () => null }, () => CASE);

CASE = { claim_id: 44, st: { values: {}, may_see_secrets: true } };
let api = makeCreds();

console.log('\nWhen nothing has been captured yet\n');
h = api.creds(CASE.st);
check('it says so plainly', h.includes('No case email'));
check('and offers a way to add it', h.includes('escCredEdit'));

console.log('\nOnce the email and password are on the claim\n');
CASE.st.values = { case_email: 'np44@gmail.com', case_email_password: 'S3cret!' };
api = makeCreds();
h = api.creds(CASE.st);
check('the email is shown', h.includes('np44@gmail.com'));
check('the password is shown to someone who may see it', h.includes('S3cret!'));
check('each line has its own pencil', (h.match(/escCredEdit/g) || []).length === 2);
check('and the dead "Correct" jump is gone', !h.includes('csrFocus'));

console.log('\nSomeone who may NOT see the password\n');
CASE.st.may_see_secrets = false;
CASE.st.values = { case_email: 'np44@gmail.com', case_email_password: '••••••••' };
api = makeCreds();
h = api.creds(CASE.st);
check('the email is still theirs to correct', h.includes("escCredEdit(&#39;case_email&#39;)"));
check('but the password is not', !h.includes("escCredEdit(&#39;case_email_password&#39;)"));
check('and it says who can', h.includes('super admins'));

console.log('\n' + (failed ? failed + ' failed' : 'all passed'));
process.exit(failed ? 1 : 0);
