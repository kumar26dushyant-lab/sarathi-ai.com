// Page 1: ticking "All documents received" must ask first, and saying no must leave the screen
// telling the truth.
const fs = require('fs');
const path = require('path');
const src = fs.readFileSync((process.argv[2] || path.join(__dirname, '..', 'static', 'nidaan_ops.html')), 'utf8');

function block(from, to) {
  const a = src.indexOf(from);
  const b = src.indexOf(to, a);
  if (a < 0 || b < 0) { console.error('anchor missing: ' + from); process.exit(1); }
  return src.slice(a, b);
}

let asked = null;      // {title, body, yesLabel, onYes}
let saved = null;      // what actually reached the server
const ndConfirm = (title, body, onYes, yesLabel) => { asked = { title, body, yesLabel, onYes }; };

const code =
  block('function _docsTickAsk(', 'async function _l2DocsTickDo(') +
  '\nasync function _l2DocsTickDo(claimId, on){ saved = {claimId, on}; }\n';

const api = new Function('ndConfirm', 'setSaved', `
  let saved = null;
  ${code}
  return {ask:_docsTickAsk, tick:l2DocsTick, read:() => saved};
`.replace('let saved = null;', 'let saved = null;')
 .replace('saved = {claimId, on};', 'saved = {claimId, on}; setSaved(saved);'))(
  ndConfirm, (v) => { saved = v; });

let failed = 0;
const check = (label, ok) => { console.log((ok ? '  PASS  ' : '  FAIL  ') + label); if (!ok) failed++; };

console.log('\nTicking it asks first\n');
let box = { checked: true };
saved = null; asked = null;
api.tick(174, true, box);
check('a question was asked', !!asked);
check('it names the claim', asked.body.includes('NP-174'));
check('it says the tick speaks in your name', /in your name/.test(asked.body));
check('it says what the tick unlocks', /move to Level-2/.test(asked.body));
check('the yes button says what yes means', /all in/i.test(asked.yesLabel));
check('and NOTHING was saved before the answer', saved === null);

console.log('\nSaying no leaves the box as it was\n');
check('the tick was put back', box.checked === false);
check('and still nothing was saved', saved === null);

console.log('\nSaying yes does it\n');
asked.onYes();
check('it reached the server', saved && saved.claimId === 174 && saved.on === true);

console.log('\nUnticking asks too - it reverses somebody’s word\n');
box = { checked: false };
saved = null; asked = null;
api.tick(174, false, box);
check('a question was asked', !!asked);
check('it warns the claim stays put', /stays in L2 Claims/.test(asked.body));
check('the box was put back to ticked', box.checked === true);
check('nothing saved yet', saved === null);
asked.onYes();
check('and saying yes takes it back', saved && saved.on === false);

console.log('\nNo checkbox element (called from somewhere else) must not throw\n');
try {
  api.tick(174, true, null);
  check('it still asks', !!asked);
} catch (e) {
  check('it still asks (threw: ' + e.message + ')', false);
}

console.log('\n' + (failed ? failed + ' failed' : 'all passed'));
process.exit(failed ? 1 : 0);
