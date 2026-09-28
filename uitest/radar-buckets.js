// The radar screen: authorities first, and the noise out of the way.
//
// Founder, 28 Sep: "the purpose of this feature was to see all the filtered emails in first tab
// ... everyone is confused how to read it."
//
// They were confused for a reason. The first tab was "Act now", which held red AND amber - and
// 44 of the 58 emails the radar had collected were amber, every one of them our own notification
// or a Google account notice. So the first thing anybody saw was a list of our own mail, sliced
// seven ways.
//
// The bucket function is lifted out and RUN against real-shaped items, because the fault that
// nearly shipped here was an ordering one that eslint cannot see: the tile strip read two counts
// declared with `const` on the line below it, which throws the moment the screen renders.
//
//   node uitest/radar-buckets.js

const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, '..', 'static', 'nidaan_ops.html'), 'utf8')
  .replace(/\r\n/g, '\n');

let failed = 0;
function check(label, ok, detail) {
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label);
  if (!ok) { failed++; if (detail !== undefined) console.log('           ' + detail); }
}

// ── run the real bucket function ────────────────────────────────────────────
const fnSrc = html.slice(html.indexOf('function _radarInBucket('),
                         html.indexOf('function _renderRadarItems('));
const _isFwdConfirm = () => false;
const _isConfirm = () => false;
const _radarInBucket = new Function('_isFwdConfirm', '_isConfirm',
  fnSrc + '; return _radarInBucket;')(_isFwdConfirm, _isConfirm);

const AUTHORITY = { flag: 'red', status: 'new', category: 'authority' };
const UNKNOWN   = { flag: 'amber', status: 'new', category: 'insurer_or_other' };
const OURS      = { flag: 'green', status: 'new', category: 'internal' };
const GOOGLE    = { flag: 'green', status: 'new', category: 'service' };
const ANSWERED  = { flag: 'red', status: 'responded', category: 'authority' };
const CLOSED    = { flag: 'red', status: 'closed', category: 'authority' };

console.log('\nWhere each kind of email goes\n');

check('an authority letter is in the FIRST tab',
      _radarInBucket(AUTHORITY, 'authority') === true);
check('...and not in "needs a look"', _radarInBucket(AUTHORITY, 'look') === false);

check('an unrecognised sender goes to "needs a look"',
      _radarInBucket(UNKNOWN, 'look') === true);
check('...and NOT into the authorities tab',
      _radarInBucket(UNKNOWN, 'authority') === false,
      'mixing them is what made the screen unreadable');

check('our own notification is cleared away',
      _radarInBucket(OURS, 'cleared') === true && _radarInBucket(OURS, 'look') === false);
check('a Google notice is cleared away',
      _radarInBucket(GOOGLE, 'cleared') === true && _radarInBucket(GOOGLE, 'authority') === false);

check('an answered letter leaves the first tab',
      _radarInBucket(ANSWERED, 'authority') === false && _radarInBucket(ANSWERED, 'done') === true,
      'otherwise the tab never empties and stops meaning anything');
check('a closed one is done too', _radarInBucket(CLOSED, 'done') === true);

// ── the screen itself ───────────────────────────────────────────────────────
console.log('\nThe screen\n');

const render = html.slice(html.indexOf('function _renderRadarItems('),
                          html.indexOf('function _renderRadarItems(') + 3000);

check('the first tab is the authorities one', /_radarFlag\|\|'authority'/.test(html),
      'the default bucket is what everybody sees first');
check('...and it is named in plain words', /From authorities/.test(render));
check('there are five filters, not seven',
      (render.match(/\$\{fTab\(/g) || []).length === 5,
      (render.match(/fTab\('(\w+)'/g) || []).join(' '));
check('no tile claims an AI handled anything', !/AI handled/.test(render),
      'nothing is handled by a model any more');

// The ordering fault that eslint cannot see: `const` counts must be declared before the tile
// strip that reads them, or the screen throws ReferenceError on first render.
const iAuth = render.indexOf('const nAuth');
const iStrip = render.indexOf('const metricStrip');
check('the counts are declared before the strip that uses them',
      iAuth >= 0 && iStrip >= 0 && iAuth < iStrip,
      'const has a temporal dead zone - using it one line early throws at render');

console.log('\n' + (failed ? failed + ' FAILED\n' : 'ALL GOOD\n'));
process.exit(failed ? 1 : 0);
