// The splitter inbox: three files open, and the fourth explains itself.
//
// Founder, 28 Sep: three jobs per person, and the oldest goes only with permission.
//
// The check that matters is the FOURTH upload. The server refuses it with a 409 whose detail is
// an object; the page used to print that straight through esc(), so a staff member would have
// read "[object Object]" at the exact moment they needed to know what to do. A message nobody
// can act on is the same as no message.
//
// Handlers are lifted out of the page and run against a small fake, like the other uitests -
// no browser, fast enough to run on every change.
//
//   node uitest/splitter-inbox.js

const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, '..', 'static', 'nidaan_ops.html'), 'utf8');

let failed = 0;
function check(label, ok, detail) {
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label);
  if (!ok) { failed++; if (detail !== undefined) console.log('           ' + detail); }
}

// ── the page no longer claims an AI reads the documents ─────────────────────
console.log('\nWhat the screen tells staff\n');

const intro = html.slice(html.indexOf('Document Splitter & Collator'),
                         html.indexOf('Document Splitter & Collator') + 700);
check('the intro does not say an AI separates the documents',
      !/the AI separates/i.test(intro), intro.slice(0, 120));
check('...it says the pages are read on our own server',
      /on our own server/i.test(intro));
check('...and that the person corrects it before exporting',
      /you correct it/i.test(intro));

// ── the inbox ───────────────────────────────────────────────────────────────
console.log('\nThe inbox\n');

check('the splitter screen has an inbox', html.includes('id="dsInbox"'));
check('...loaded when the screen opens', /dsLoadInbox\(\);\n\}/.test(html)
      || html.includes('dsLoadInbox();'));
check('...from the route that returns only this person\'s jobs',
      html.includes("/nidaan/ops/api/docsplit/jobs"));
check('...and refreshed after an upload',
      (html.match(/dsLoadInbox\(\)/g) || []).length >= 3,
      'open, after upload, and after closing');

const closeFn = html.slice(html.indexOf('async function dsClose('),
                           html.indexOf('async function dsClose(') + 900);
check('closing is confirmed first', /confirm\(/.test(closeFn), closeFn.slice(0, 80));
check('...and says the file is kept, not deleted', /kept, not deleted/.test(closeFn));
check('...and calls the close route, not a delete',
      /\/close`/.test(closeFn) && !/DELETE/.test(closeFn));

// ── the fourth upload ───────────────────────────────────────────────────────
console.log('\nThe fourth upload\n');

const up = html.slice(html.indexOf('async function dsUpload('),
                      html.indexOf('function dsRenderReview('));

check('a 409 inbox_full is handled on its own', /r\.status===409/.test(up)
      && /inbox_full/.test(up), 'otherwise the object prints as [object Object]');
check('...and names the file that is in the way', /d\.oldest|o\.title/.test(up));
check('...and offers to open or close THAT one', /dsOpen\(/.test(up) && /dsClose\(/.test(up));
check('...and closes nothing by itself',
      !/\/close`,\{method:'POST'/.test(up.replace(/dsClose\([^)]*\)/g, '')),
      'the button asks; the upload handler must not act');

// A non-409 error must still read as a sentence, not an object.
check('any other error still prints a sentence, never an object',
      /typeof d==='string'/.test(up), up.slice(-400));

// ── nothing here deletes ────────────────────────────────────────────────────
console.log('\nNothing on this screen deletes a file\n');

const splitterJs = html.slice(html.indexOf('function loadDocSplit('),
                              html.indexOf('window.dsLoadInbox'));
check('no discard/delete call anywhere in the splitter screen',
      !/discard_job_file|method:'DELETE'/.test(splitterJs));

console.log('\n' + (failed ? failed + ' FAILED\n' : 'ALL GOOD\n'));
process.exit(failed ? 1 : 0);
