// Pull the REAL l2Move out of the page and run the expression that was killing it.
//
// Not a mock of the bug: the actual source, brace-matched out of the file, with only the calls
// it makes to the rest of the page stubbed. If `to` were still in there, this throws exactly as
// the browser did.
const fs = require('fs');
const path = require('path');

const src = fs.readFileSync((process.argv[2] || path.join(__dirname, '..', 'static', 'nidaan_ops.html')), 'utf8');
const at = src.indexOf('async function l2Move(claimId, toKey, presetReason, fromKey){');
if (at < 0) { console.error('could not find l2Move'); process.exit(1); }
let i = src.indexOf('{', at), depth = 0, end = i;
for (; end < src.length; end++) {
  if (src[end] === '{') depth++;
  else if (src[end] === '}') { depth--; if (depth === 0) break; }
}
const fnSrc = src.slice(at, end + 1);

let opened = null;
const ctx = {
  ndUI: { toast: (m, k) => { console.log('    toast:', k, m); } },
  _l2Sel: 'live_cases',
  _role: 'team_member',
  _l2Rule: () => ({ needs_reason: false, kind: 'forward', off_route: false }),
  // Pending Draft, as the live configuration has it: four steps. This is the case that threw.
  _l2Bucket: (k) => ({
    bucket_key: k,
    name_en: k === 'lokpal' ? 'Lokpal' : (k === 'escalation' ? 'Escalation' : 'Pending Draft'),
    icon: '📝', is_park: false,
    substates: k === 'lokpal'
      ? [{ sub_key: 'pending', name_en: 'Lokpal Pending', is_default: true },
         { sub_key: 'registered', name_en: 'Lokpal Registered' },
         { sub_key: 'ann5_pending', name_en: 'Annexure 5 Pending' },
         { sub_key: 'hearing', name_en: 'Hearing' }]
      : [{ sub_key: 'drafting', name_en: 'Drafting', is_default: true },
         { sub_key: 'with_mo', name_en: 'With Medical Officer / Advocate' },
         { sub_key: 'draft_query', name_en: 'Draft Query' },
         { sub_key: 'approved', name_en: 'Approved' }],
  }),
  esc: (s) => String(s == null ? '' : s),
  openModal: (title, body) => { opened = { title, body }; },
  _l2Send: () => {},
  document: { getElementById: () => null },
};

const fn = new Function(...Object.keys(ctx), 'return (' + fnSrc + ')')(...Object.values(ctx));

let failed = 0;
function check(label, ok) {
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label);
  if (!ok) failed++;
}

(async () => {
  console.log('\nMoving NP-1 into Pending Draft - which always arrives on Drafting\n');
  try {
    await fn(1, 'pending_draft', '', 'live_cases');
    check('the move window opens at all', !!opened);
    // Founder, 22 Sep. The other three steps are things that happen AFTER arriving; offering
    // them here invites somebody to record a step before it has happened.
    check('no step picker - it always arrives on Drafting',
          !/id="l2mSub"/.test(opened && opened.body));
    check('and the note box the move needs', /id="l2mWhy"/.test(opened.body));
  } catch (e) {
    check('the move window opens at all (threw: ' + e.message + ')', false);
  }

  console.log('\nBut a bucket with a real choice on arrival still offers one\n');
  opened = null;
  try {
    // Lokpal: which annexure has come back is a decision a person makes, not a step that
    // follows from arriving. If this ever stops offering a picker, the picker is broken.
    await fn(1, 'lokpal', '', 'escalation');
    check('the window opens', !!opened);
    check('and the steps are offered', /id="l2mSub"/.test(opened && opened.body));
  } catch (e) {
    check('the window opens (threw: ' + e.message + ')', false);
  }

  console.log('\nAnd into Escalation, where the step picker is deliberately NOT offered\n');
  opened = null;
  try {
    await fn(1, 'escalation', '', 'live_cases');
    check('the window opens', !!opened);
    check('no step picker - entering Escalation always lands on Escalation Pending',
          !/id="l2mSub"/.test(opened.body));
  } catch (e) {
    check('the window opens (threw: ' + e.message + ')', false);
  }

  console.log('\n' + (failed ? failed + ' failed' : 'all passed'));
  process.exit(failed ? 1 : 0);
})();
