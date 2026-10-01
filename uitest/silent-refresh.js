// Ops screens refresh silently (founder, 1 Oct: "why our app flicker? ... make it stable refresh
// and run smoothly").
//
// ndPaint is the one painter: no DOM work at all when the markup did not change, and when it did,
// the reader's place survives. The WhatsApp inbox used to blank the open conversation to
// "Opening…" every 25 seconds, rebuild everything, jump to the bottom and - on a phone - pull a
// person who had pressed Back into the conversation again. Checked here against the real source.
//
//   node uitest/silent-refresh.js

const fs = require('fs');
const path = require('path');
const h = fs.readFileSync(path.join(__dirname, '..', 'static', 'nidaan_ops.html'), 'utf8');

let failed = 0;
function check(label, ok, detail) {
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label);
  if (!ok) { failed++; if (detail !== undefined) console.log('           ' + String(detail).slice(0, 200)); }
}

const s = h.indexOf('function ndPaint(');
const e = h.indexOf('async function waiLoadList(');
if (s < 0 || e < 0) { console.error('ndPaint not found'); process.exit(1); }

global.document = { activeElement: null, querySelector: () => null, getElementById: () => null };
// eslint-disable-next-line no-eval
eval(h.slice(s, e) + '; global.ndPaint = ndPaint;');

function fakeEl() {
  return {
    writes: 0, _html: '', scrollTop: 0, scrollHeight: 0, clientHeight: 0,
    set innerHTML(v) { this.writes++; this._html = v; },
    get innerHTML() { return this._html; },
    querySelectorAll: () => [], querySelector: () => null, contains: () => false, getAttribute: () => null,
  };
}

const el = fakeEl();
check('first paint writes the markup', ndPaint(el, '<b>a</b>') === true && el.writes === 1, el.writes);
check('the same markup again does NOTHING (no flicker)', ndPaint(el, '<b>a</b>') === false && el.writes === 1, el.writes);
check('changed markup is painted once', ndPaint(el, '<b>b</b>') === true && el.writes === 2, el.writes);
el.scrollTop = 120;
ndPaint(el, '<b>c</b>');
check('the reader keeps their scroll position', el.scrollTop === 120, el.scrollTop);

// The WhatsApp inbox uses it, quietly
const open = h.slice(h.indexOf('async function waiOpen('), h.indexOf('function _waiContext('));
check('waiOpen shows "Opening…" only for a DIFFERENT conversation',
  /if \(!same\)\{ el\.innerHTML = '<div[^']*Opening/.test(open));
check('a quiet refresh never switches the phone view to the conversation',
  open.includes("if (grid && !quiet) grid.dataset.view = 'thread'"));
check('the conversation pane is painted through ndPaint', open.includes('ndPaint(el,'));
check('a typed reply survives a refresh', open.includes('if (tb && typed && !tb.value) tb.value = typed'));
const poll = h.slice(h.indexOf('function waiStartPoll('), h.indexOf('window.waiLoadList=waiLoadList'));
check('the 25-second poll refreshes quietly', poll.includes('waiOpen(_waiSel, true)'));
check('...and leaves alone a box someone is typing in', poll.includes('document.activeElement === box'));
const list = h.slice(h.indexOf('async function waiLoadList('), h.indexOf('async function waiOpen('));
check('the conversation list repaints only when it changed', list.includes('ndPaint(el, list.map('));
check('opening the panel no longer opens the conversation twice',
  h.includes("if (_waiSel && !document.getElementById('waiMsgs')) waiOpen(_waiSel);"));

console.log(failed ? '\n' + failed + ' failed' : '\nall passed');
process.exit(failed ? 1 : 0);
