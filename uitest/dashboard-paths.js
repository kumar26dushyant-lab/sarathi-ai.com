// Every call the subscriber dashboard makes goes to a NidaanPartner API path.
//
// 1 Oct: the Features tab called api('/features...'). The dashboard's api() helper sends the path
// exactly as given, so that reached '/features' - a Sarathi HTML page that answers 200 - and the
// tab silently showed nothing for every subscriber. A bare path can never be right here.
//
//   node uitest/dashboard-paths.js
const fs = require('fs');
const path = require('path');
const SRC = fs.readFileSync(path.join(__dirname, '..', 'static', 'nidaan_dashboard.html'), 'utf8');
let failed = 0;
const t = (label, ok, detail) => {
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label);
  if (!ok) { failed++; if (detail) console.log('           ' + detail); }
};
const calls = [...SRC.matchAll(/\bapi\(\s*(['"`])([^'"`]*)/g)].map((m) => m[2]);
console.log('\nThe subscriber dashboard\n');
t('the scan found the calls', calls.length >= 10, calls.length);
const bad = calls.filter((p) => !p.startsWith('/nidaan/'));
t('every api() call goes to a /nidaan/ path', bad.length === 0, bad.join(', '));
t('the Features tab asks /nidaan/api/features', SRC.includes("api('/nidaan/api/features?lang="));
console.log('\n' + (failed ? failed + ' failed' : 'all passed'));
process.exit(failed ? 1 : 0);
