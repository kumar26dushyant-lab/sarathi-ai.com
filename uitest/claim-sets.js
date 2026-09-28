// The three sets, on the claim, beside the checklist staff already use.
//
// Founder: the folders should be buildable "at claim level itself", and it must fit the existing
// claim conversation "without conflict or discrepancies". So this lives in the Documents panel
// next to "Attached" and "The checklist" - the same screen where somebody attaches a file, ticks
// it off, and asks the complainant for what is missing.
//
// Read from the page source, the same as the other uitests: what matters is that the box is
// wired to the claim's own endpoints and that the dangerous shortcuts are absent.
//
//   node uitest/claim-sets.js

const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, '..', 'static', 'nidaan_ops.html'), 'utf8')
  .replace(/\r\n/g, '\n');

let failed = 0;
function check(label, ok, detail) {
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label);
  if (!ok) { failed++; if (detail !== undefined) console.log('           ' + detail); }
}

// The box lives inside the Documents panel, not in a separate tool.
console.log('\nWhere it lives\n');

const panel = html.slice(html.indexOf('async function docsRender('),
                         html.indexOf('// ── The three sets, built from what is already'));

check('the sets box is part of the Documents panel', /id="dcSets"/.test(panel),
      'a separate tool is one staff have to remember exists');
check('...beside the checklist and the complainant messaging',
      panel.indexOf('id="dcSets"') > panel.indexOf('dwAsk('),
      'this is the screen where that conversation already happens');
check('...and loads AFTER the panel is on screen',
      /schList\(_dcClaim\);[\s\S]{0,200}dcSetsLoad\(\)/.test(panel),
      'reading a scanned claim takes seconds; attaching a file must not wait on it');

// ── the behaviour the founder specified ─────────────────────────────────────
console.log('\nWhat the box does\n');

const box = html.slice(html.indexOf('// ── The three sets, built from what is already'),
                       html.indexOf('// Remove a document that should not be on the claim.'));

check('it reads the claim\'s own sets endpoint', /\/doc-sets/.test(box));
// By DOCUMENT NAME, not page number. On a real claim the page-number version read
// "please arrange pages 1,2,3 ... 106" - a wall nobody can act on.
check('a doubtful document is named, not numbered',
      /esc\(u\.name\)/.test(box),
      'staff talk about "the bill", never about page 47');
check('...with a reason beside each one', /esc\(u\.why\)/.test(box));
check('...and the whole claim is held until it is settled',
      /arr\.ready[\s\S]{0,400}Please check these/.test(box),
      'a set that is nearly right is the dangerous kind - nobody checks it');
check('...and a 40-page bill is listed once, not forty times',
      /arr\.unsure\.length/.test(box) && !/arr\.unsure\.join\(/.test(box));
check('each set can be downloaded', /dcSetGet\(/.test(box));
check('...and says what is NOT on the claim', /not on this claim/.test(box));
check('it shows what the CHECKLIST still wants', /still_needed/.test(box),
      'the thing a loose pile of files cannot know');

console.log('\nThe switch\n');

check('the switch is on the claim', /doc-auto/.test(box));
check('...described as off unless you turn it on', /Off unless you turn it on/.test(box));
check('...and says a person can still change a page by hand',
      /change a page by hand/.test(box),
      'the audit case: automation was sure and still wrong');

console.log('\nCorrecting a page\n');

check('a page is changed by two taps, not dragging',
      /dcPagePick\(/.test(box) && !/ondragstart|draggable=/.test(box));
check('...offered by NAME, from the server\'s list',
      /_dcSets\.types/.test(box),
      'the page keeps no copy of the type names, so adding one never means editing the page');
check('...keyed by document and page INSIDE it, never the merged number',
      /doc_id[\s\S]{0,120}page_in_doc/.test(box),
      'a merged page number moves when another document arrives');
check('teaching is offered only to an admin',
      /_role === 'super_admin' \|\| _role === 'sub_super_admin'/.test(box),
      'a rule changes what the whole team sees');
check('...and a team member is told what to do instead',
      /Ask an admin to make it a rule/.test(box));

console.log('\n"Don\'t send this page"\n');

check('each page has a Don\'t send button', /Don\\'t send/.test(box) && /dcPageHold\(/.test(box));
check('...which reads Send again once held back', /Send again/.test(box));
check('...and asks first before holding a page back',
      /async function dcPageHold[\s\S]{0,200}confirm\(/.test(box),
      'a page silently missing from a legal bundle is the hard mistake to notice');
check('...keyed by document and page INSIDE it',
      /doc-exclude[\s\S]{0,160}page_in_doc/.test(box));
check('a held-back page stays in the list, struck through, with who held it back',
      /line-through/.test(box) && /excluded_by/.test(box),
      'hiding it would look as though it never arrived');
check('...and the box says how many are held back', /page\(s\) held back/.test(box));
check('the page list stays open after a change', /dcPagesWrap[\s\S]{0,40}\.open/.test(box));
check('dcPageHold is reachable from the onclick', /window\.dcPageHold=dcPageHold/.test(html));

console.log('\nNothing here deletes\n');

check('no delete call anywhere in the sets box',
      !/method:'DELETE'|discard_job_file/.test(box));

console.log('\n' + (failed ? failed + ' FAILED\n' : 'ALL GOOD\n'));
process.exit(failed ? 1 : 0);
