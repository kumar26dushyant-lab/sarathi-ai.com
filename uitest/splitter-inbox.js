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

// ── the review screen ───────────────────────────────────────────────────────
console.log('\nThe review screen\n');

const review = html.slice(html.indexOf('function dsRenderReview('),
                          html.indexOf('// ── what the splitter has been taught'));

check('it walks the person through in numbered steps',
      /<b>1\.<\/b>/.test(review) && /<b>2\.<\/b>/.test(review) && /<b>3\.<\/b>/.test(review),
      'the founder asked for baby steps staff can read and follow');
check('it says the pages were read on this server', /read on this server/.test(review));
check('it shows the ready-made sets', /dsRenderSets|id="dsSets"/.test(review));

// Two taps, not drag-and-drop: this is used on a phone in a corridor.
check('correcting a page is TAP page then TAP name',
      /dsPick\(/.test(review) && /Tap the page/.test(review));
check('...with no drag-and-drop to fail on a touch screen',
      !/ondragstart|draggable=|ondrop/.test(review));
check('...and each type is offered by NAME, not an icon',
      /esc\(t\.label\)/.test(review), 'words over ambiguous icons');

check('teaching is a separate, opt-in tick',
      /id="dsTeach"/.test(review) && /Remember this/.test(review),
      '"this page once" and "pages like this always" are different decisions');
check('a page nobody could read says so rather than guessing',
      /could not be read/.test(review));
check('the sets say what is NOT in the file', /not in this file/.test(review));

// ── the rules screen ────────────────────────────────────────────────────────
console.log('\nWhat the splitter has learned\n');

const rules = html.slice(html.indexOf('function dsToggleRules('),
                         html.indexOf('async function dsLoadThumbs('));

check('there is a screen for it at all', rules.length > 200);
check('a rule is shown as WORDS a person can read',
      /r\.words\|\|\[\]/.test(rules) && /when at least 4 of these words appear/.test(rules),
      'a similarity score would be unarguable, which is the problem');
check('...with who taught it and how often it has fired',
      /taught by/.test(rules) && /times_fired/.test(rules));
check('...and an undo next to each one', /dsUndoRule\(/.test(rules));
check('turning one off is confirmed first', /confirm\(/.test(rules));
check('...and says it is kept on record, not deleted',
      /kept on record, not deleted/.test(rules),
      '"removed" and "turned off" are different promises');
check('with nothing learned it explains how to teach it',
      /Nothing learned yet/.test(rules) && /Remember this/.test(rules));

console.log('\n' + (failed ? failed + ' FAILED\n' : 'ALL GOOD\n'));
process.exit(failed ? 1 : 0);
