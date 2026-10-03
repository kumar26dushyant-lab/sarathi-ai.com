// One document limit, in a real browser (3 Oct 2026): /static/nidaan_limits.js.
//
// Several big files used to go as ONE request and be refused whole; a file that failed was often
// never mentioned. This drives the real helper the pages now share: what it refuses, how it
// splits, that it sends every batch, and that it names what did not go - in English and Hindi.
//
//   node uitest/limits.js
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const lim = fs.readFileSync(path.join(__dirname, '..', 'static', 'nidaan_limits.js'), 'utf8');
let failed = 0;
const check = (label, ok, detail) => {
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label);
  if (!ok) { failed++; if (detail !== undefined) console.log('           ' + JSON.stringify(detail).slice(0, 300)); }
};

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const posts = [];
  await page.route('**/up', async (r) => {
    const body = r.request().postDataBuffer() || Buffer.alloc(0);
    posts.push(body.length);
    // The second request fails, to prove a failure is named rather than swallowed.
    if (posts.length === 2) return r.fulfill({ status: 413, contentType: 'application/json', body: '{"detail":"That batch is too big"}' });
    return r.fulfill({ status: 200, contentType: 'application/json', body: '{"count":1}' });
  });
  await page.route('**/page', (r) => r.fulfill({ status: 200, contentType: 'text/html',
    body: '<!doctype html><meta charset="utf-8"><script>' + lim + '</script>' }));
  await page.goto('http://x/page');

  // Stand-in files: real File objects whose size we choose without allocating 100 MB of memory.
  const res = await page.evaluate(async () => {
    const MB = 1e6;
    const f = (name, mb) => { const x = new File(['x'], name); Object.defineProperty(x, 'size', { value: mb * MB }); return x; };
    const L = window.NidaanLimits;
    const files = [f('a.pdf', 40), f('b.pdf', 40), f('c.pdf', 40), f('huge.pdf', 96), f('d.pdf', 1)];
    const groups = L.batches(files).map(g => g.map(x => x.name));
    const sums = L.batches(files).map(g => g.reduce((t, x) => t + x.size, 0));
    const many = L.batches(Array.from({ length: 25 }, (_, i) => f('p' + i + '.jpg', 1))).map(g => g.length);
    const sent = await L.send('/up', files, { headers: { Authorization: 'Bearer t' } });
    return {
      limit: L.docMaxMB, big: L.oversize(files).map(x => x.name), groups, sums, many, sent,
      en: L.report(sent, false), hi: L.report(sent, true),
      tooBig: L.tooBig(f('x', 95.5)), fits: L.tooBig(f('y', 95)),
      refusalEn: L.refusal('scan.pdf', 120 * MB, false), refusalHi: L.refusal('scan.pdf', 120 * MB, true),
    };
  });

  console.log('\nWhat is refused\n');
  check('the limit is 95 MB', res.limit === 95, res.limit);
  check('a 96 MB file is picked out before anything is sent', JSON.stringify(res.big) === '["huge.pdf"]', res.big);
  check('95 MB fits; 95.5 MB does not', res.fits === false && res.tooBig === true);
  check('the refusal says the size, the limit and what to do', /120 MB/.test(res.refusalEn) && /95 MB/.test(res.refusalEn)
        && /PDF/.test(res.refusalEn) && /सीमा/.test(res.refusalHi), [res.refusalEn, res.refusalHi]);

  console.log('\nHow it splits\n');
  check('three 40 MB files go as two requests (80 + 40), never one 120 MB request',
        JSON.stringify(res.groups) === '[["a.pdf","b.pdf"],["c.pdf","d.pdf"]]', res.groups);
  check('25 small files go as 20 + 5 - the server takes 20 per request', JSON.stringify(res.many) === '[20,5]', res.many);
  check('no request carries more than 99 MB of files', res.sums.length === 2 && res.sums.every(n => n <= 99e6), res.sums);

  console.log('\nWhat it reports\n');
  check('every batch is sent', posts.length === 2, posts.length);
  check('the files that went are counted', res.sent.sent === 2, res.sent);
  check('the files in the failed batch are NAMED', JSON.stringify(res.sent.failed) === '["c.pdf","d.pdf"]', res.sent.failed);
  check('...with the server\'s reason', /too big/.test(res.en), res.en);
  check('the too-big file is named as not sent', /huge\.pdf/.test(res.en) && /95 MB/.test(res.en), res.en);
  check('...and all of it in Hindi too', /नहीं भेजी/.test(res.hi) && /अपलोड नहीं हुई/.test(res.hi), res.hi);
  check('it is not called a success', res.sent.ok === false);

  await browser.close();
  console.log('\n' + (failed ? failed + ' failed' : 'all passed'));
  process.exit(failed ? 1 : 0);
})();
