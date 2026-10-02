// Every form that has an insurance-company box must actually put the picker in it. The AP form's box
// sat empty from 13 Sep to 2 Oct, so partners never saw the field (17 AP claims arrived without one).
//
//   node uitest/ap-insurer-picker.js

const fs = require('fs');
const path = require('path');

let failed = 0;
function check(label, ok) { console.log((ok ? '  PASS  ' : '  FAIL  ') + label); if (!ok) failed++; }

const dir = path.join(__dirname, '..', 'static');
for (const f of fs.readdirSync(dir).filter((x) => x.endsWith('.html'))) {
  const h = fs.readFileSync(path.join(dir, f), 'utf8');
  const read = [...h.matchAll(/NidaanInsurers\.value\(\s*'([A-Za-z0-9_]+)'[ ]*[)]/g)].map((m) => m[1]);
  for (const id of new Set(read)) {
    check(f + ': the insurer box "' + id + '" is mounted, not just read',
      h.includes("NidaanInsurers.mount('" + id + "'"));
  }
}
console.log(failed ? '\n' + failed + ' failed' : '\nall passed');
process.exit(failed ? 1 : 0);
