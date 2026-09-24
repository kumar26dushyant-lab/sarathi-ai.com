// The pager's arithmetic, exercised against the real source in nidaan_ops.html.
//
// Founder, 24 Sep: "all claims, L2 claims, buckets, accounts all section should have pages
// option because as claims are increasing the scrolling is getting increasing ... if they want
// to see 10 claims, 20 claims, or 30 claims in one page that's great if nothing is selected
// default should be 30".
//
// Paging is arithmetic, and arithmetic is where an off-by-one hides a row from somebody who
// needed it. The trap that matters is the one nobody thinks of: filtering a list down to three
// rows while sitting on page 2 must not show an empty table. That is checked here.
//
// No browser: the helpers are lifted out of the page and run directly, so this stays fast enough
// to run on every change.
//
//   node uitest/pager.js

const fs = require('fs');
const path = require('path');

const h = fs.readFileSync(path.join(__dirname, '..', 'static', 'nidaan_ops.html'), 'utf8');
const start = h.indexOf('const _PAGE_SIZES');
const end = h.indexOf('function _renderClaimResults');
if (start < 0 || end < 0 || end <= start) {
  console.error('could not find the pager helpers in nidaan_ops.html');
  process.exit(1);
}

global.window = {};
global.localStorage = {
  _d: {},
  getItem(k) { return this._d[k] === undefined ? null : this._d[k]; },
  setItem(k, v) { this._d[k] = v; },
};
// eslint-disable-next-line no-eval
eval(h.slice(start, end));

let ok = 0, bad = 0;
const t = (label, cond) => { console.log((cond ? '  PASS  ' : '  FAIL  ') + label); cond ? ok++ : bad++; };

console.log('\nPaging\n');

const list = Array.from({ length: 47 }, (_, i) => i + 1);

t('the default page size is 30, as he asked', pageSize('claims') === 30);
t('page 1 holds 30', pageSlice('claims', list).length === 30);
t('...starting at the first row', pageSlice('claims', list)[0] === 1);

gotoPage('claims', 2, 'noop');
t('page 2 holds the remaining 17', pageSlice('claims', list).length === 17);
t('...and starts where page 1 stopped', pageSlice('claims', list)[0] === 31);

gotoPage('claims', 9, 'noop');
t('a page past the end clamps to the last one', pageSlice('claims', list).length === 17);

// THE TRAP. Search or filter down to a handful while on a late page.
gotoPage('claims', 2, 'noop');
t('filtering to 3 rows while on page 2 still shows all 3',
  pageSlice('claims', [1, 2, 3]).length === 3);

setPageSize('claims', 10, 'noop');
t('choosing 10 per page gives 10', pageSlice('claims', list).length === 10);
t('...and drops back to page 1, not a page that no longer exists',
  pageSlice('claims', list)[0] === 1);
t('...and the choice is remembered', pageSize('claims') === 10);

localStorage.setItem('nd_ps_claims', '9999');
t('a junk stored size falls back to 30 rather than showing 9999 rows',
  pageSize('claims') === 30);

const bar = pagerBar('claims', 47, '_renderClaimResults');
t('the bar states the range and the total', bar.includes('1–30') && bar.includes('47'));
t('...and contains no inline function literal (verify-ops-buttons reads those as handlers)',
  !bar.includes('function('));
t('an empty list does not break the bar', typeof pagerBar('claims', 0, 'x') === 'string');

// Two lists must not share a page number.
gotoPage('claims', 3, 'noop');
gotoPage('accounts', 1, 'noop');
t('each list keeps its own page', pageOf('claims', 200) === 3 && pageOf('accounts', 200) === 1);

// ── every list, not just All Claims ─────────────────────────────────────────
// Founder, 25 Sep: "pagination is only done on all claims, why it's not done on L2 claims,
// accounts, and all buckets?"
const OPSH = fs.readFileSync(path.join(__dirname, '..', 'static', 'nidaan_ops.html'), 'utf8');

// THE ONE THAT WOULD BE SILENT DATA LOSS: an Excel export holding only the page somebody
// happened to be looking at, with nothing on screen to say so.
const exp = OPSH.slice(OPSH.indexOf('function l2Export'), OPSH.indexOf('function l2Export') + 900);
t('the Excel export still takes EVERY row, not the page', /const rows = _l2Rows\.map/.test(exp));
t('...and nothing paged leaked into it', !exp.includes('pageSlice'));

// L2 Claims has three views and two of them return early — paging only the table would have
// left Board and Cards quietly unpaged.
const oc = OPSH.slice(OPSH.indexOf('const _pkOc ='), OPSH.indexOf('const _pkOc =') + 900);
t('L2 Claims pages BEFORE the view branches',
  oc.indexOf('rows = pageSlice') < oc.indexOf("_l2View==='board'"));
t('...so the Board view is paged too', /_l2View==='board'\).*_ocBar\+_renderClaimBoard/.test(oc));
t('...and the Cards view', /_l2View==='cards'\).*_ocBar\+_renderClaimCards/.test(oc));

const bt = OPSH.slice(OPSH.indexOf('function l2Table(b){'), OPSH.indexOf('function l2Table(b){') + 400);
t('each bucket gets its own page number', /_pk = 'bucket:' \+ \(b\.bucket_key/.test(bt));

t('accounts repaint the FILTERED list, not the whole set',
  OPSH.includes('window._accShown = accounts'));
t('...through a named repaint the pager can call', OPSH.includes('window.renderAccountsPage'));

t('the pager can hand an argument back to its renderer',
  /function pagerBar\(key, total, redraw, arg\)/.test(h));
t('...quoted for a string, bare for a number', /typeof arg === 'number'/.test(h));

console.log('\n' + (bad ? bad + ' failed'
  : 'every list paged, the page outlives its rows, and the export is untouched'));
process.exit(bad ? 1 : 0);
