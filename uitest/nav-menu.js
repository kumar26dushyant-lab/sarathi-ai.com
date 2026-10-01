// The ops menu as an office (founder, 1 Oct): foldable groups, the buckets inside Consolidation.
//
// What a menu rebuild can silently break, pinned here:
//   - a screen that disappears from the menu (its id no longer listed)
//   - a screen listed twice
//   - a screen that became visible to a lower role than before (minRank lowered)
//   - a menu entry with no panel behind it
//   - Consolidation not holding the buckets, or the fold state not remembered
//
//   node uitest/nav-menu.js

const fs = require('fs');
const path = require('path');
const OPS = fs.readFileSync(path.join(__dirname, '..', 'static', 'nidaan_ops.html'), 'utf8');

let failed = 0;
const t = (label, ok, detail) => {
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label);
  if (!ok) { failed++; if (detail) console.log('           ' + detail); }
};

const start = OPS.indexOf('const zones = [', OPS.indexOf('function buildSidebar()'));
const end = OPS.indexOf('];', start);
const zones = eval(OPS.slice(start + 'const zones = '.length, end + 1));
const items = zones.flatMap((z) => z.items.map((i) => Object.assign({ zone: z.k }, i)));
const ids = items.map((i) => i.id);

// Every screen the menu had before the rebuild, with who could see it (0 team, 1 admin, 2 super).
const BEFORE = { l2: 0, tasks: 0, crm: 0, overview: 0, claims: 1, l2claims: 1, docdesk: 0, archived: 1,
  accounts: 1, mybiz: 0, onbehalf: 0, payfollow: 1, docsplit: 0, branches: 1, cp: 0, staff: 2,
  leave: 0, leavehistory: 2, whatsapp: 1, telegram: 0, radar: 1, support: 0, analytics: 2,
  revenue: 2, settings: 2, bdesign: 2, plans: 2, content: 2, guide: 0, health: 2 };

console.log('\nThe ops menu\n');
const lost = Object.keys(BEFORE).filter((id) => !ids.includes(id));
t('no screen lost from the menu', lost.length === 0, lost.join(', '));
const dup = ids.filter((id, i) => ids.indexOf(id) !== i);
t('no screen listed twice', dup.length === 0, dup.join(', '));
const lowered = items.filter((i) => BEFORE[i.id] != null && i.minRank < BEFORE[i.id]);
t('no screen became visible to a lower role', lowered.length === 0, lowered.map((i) => i.id).join(', '));
t('revenue stays owner-only', items.find((i) => i.id === 'revenue').ownerOnly === true);
const noPanel = [...new Set(ids)].filter((id) => !OPS.includes('id="panel-' + id + '"') && !OPS.includes("'panel-" + id + "'"));
t('every menu entry has a panel behind it', noPanel.length === 0, noPanel.join(', '));
const line = zones.find((z) => z.k === 'line');
t('Consolidation is a group that holds the buckets', line && line.buckets === true);
t('...starting with the L2 waiting queue and all open claims',
  line && line.items[0].id === 'l2claims' && line.items[1].id === 'l2' && line.items[1].bucket === 'all');
t('the buckets come from the same counts the workspace uses',
  OPS.includes("API('/buckets/counts')") && /_navLoadBuckets[\s\S]{0,600}\/buckets\/counts/.test(OPS));
t('a fold is remembered per person (local only)', OPS.includes("localStorage.getItem('nd_nav_folded'"));
t('the group holding the open screen never starts folded', OPS.includes('folded[zone.k] === true && !holdsActive'));
t('screen opens are counted, without blocking anything', OPS.includes("/nidaan/ops/api/ui/opened") && OPS.includes('keepalive:true'));
t('My work comes first', zones[0].k === 'work');

console.log('\n' + (failed ? failed + ' failed' : 'all passed'));
process.exit(failed ? 1 : 0);
