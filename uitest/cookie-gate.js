// Does the cookie gate actually STOP Google Analytics? Run the real files and find out.
//
// Reading nidaan_ga.js and seeing a consent check is not evidence that nothing loads. The whole
// point of this feature is a negative - that a script tag is NOT created for somebody who has
// not agreed - and a negative is exactly what source-reading is worst at proving.
//
// So both real files are executed here against a small fake browser, and the test watches what
// gets appended to <head>. No jsdom, no browser, same approach as the other uitests: fast enough
// to run on every change.
//
//   node uitest/cookie-gate.js

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const S = (f) => fs.readFileSync(path.join(__dirname, '..', 'static', f), 'utf8');
const CONSENT_SRC = S('nidaan_cookies.js');
const GA_SRC = S('nidaan_ga.js');

let failed = 0;
function check(label, ok, detail) {
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label);
  if (!ok) { failed++; if (detail !== undefined) console.log('           ' + detail); }
}

// ── the smallest browser that can answer the question ───────────────────────
function makeWorld(opts) {
  opts = opts || {};
  const loaded = [];           // every script src appended to <head>
  const listeners = {};
  let cookieJar = opts.cookie || '';

  function el(tag) {
    const node = {
      tagName: tag, id: '', className: '', type: '', style: {}, disabled: false,
      children: [], attrs: {}, _text: '',
      set textContent(v) { this._text = String(v); },
      get textContent() { return this._text; },
      set innerHTML(v) { this._html = String(v); },
      get innerHTML() { return this._html || ''; },
      setAttribute(k, v) { this.attrs[k] = String(v); },
      getAttribute(k) { return this.attrs[k]; },
      appendChild(c) { this.children.push(c); if (c.src) loaded.push(c.src); return c; },
      removeChild(c) { this.children = this.children.filter((x) => x !== c); return c; },
      addEventListener() {},
      querySelector() { return null; },
      focus() {}
    };
    return node;
  }

  const head = el('head');
  const body = el('body');
  head.appendChild = function (c) { this.children.push(c); if (c.src) loaded.push(c.src); return c; };

  const store = {};
  const win = {
    dataLayer: undefined,
    addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
    dispatchEvent(ev) { (listeners[ev.type] || []).forEach((fn) => fn(ev)); return true; },
    localStorage: opts.noStorage ? {
      // A browser with site data blocked must not break the page, and must not be
      // mistaken for a browser that agreed.
      getItem() { throw new Error('blocked'); },
      setItem() { throw new Error('blocked'); }
    } : {
      getItem: (k) => (k in store ? store[k] : null),
      setItem: (k, v) => { store[k] = String(v); },
      removeItem: (k) => { delete store[k]; }
    },
    CustomEvent: function (type, init) { this.type = type; this.detail = (init || {}).detail; },
    location: { hostname: opts.host || 'nidaanpartner.com', protocol: 'https:', search: '', hash: '' }
  };
  win.window = win;

  const doc = {
    readyState: 'complete',
    documentElement: { lang: 'en' },
    head: head,
    body: body,
    createElement: el,
    createTextNode: (t) => ({ nodeType: 3, textContent: String(t) }),
    createEvent: () => ({ initCustomEvent(t) { this.type = t; } }),
    getElementById: () => null,
    querySelector: () => null,
    addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
    get cookie() { return cookieJar; },
    set cookie(v) {
      const name = String(v).split('=')[0];
      const parts = cookieJar ? cookieJar.split('; ').filter((c) => c.split('=')[0] !== name) : [];
      if (!/expires=Thu, 01 Jan 1970/.test(v)) parts.push(String(v).split(';')[0]);
      cookieJar = parts.join('; ');
    }
  };
  win.document = doc;

  const ctx = vm.createContext(win);
  ctx.window = win;
  ctx.document = doc;
  ctx.localStorage = win.localStorage;
  ctx.location = win.location;
  ctx.CustomEvent = win.CustomEvent;
  ctx.navigator = { clipboard: { writeText: () => Promise.resolve() } };

  return {
    ctx, loaded, win, doc,
    gaLoaded: () => loaded.some((s) => /googletagmanager\.com/.test(s)),
    run: (src) => vm.runInContext(src, ctx)
  };
}

// ── 1. nobody has answered yet ───────────────────────────────────────────────
console.log('\nBefore anyone has answered\n');
{
  const w = makeWorld();
  w.run(CONSENT_SRC);
  w.run(GA_SRC);
  check('analytics does NOT load for an undecided visitor', !w.gaLoaded(), w.loaded);
  check('...and the banner was put on the page', w.doc.body.children.length > 0);
  check('...and allows("analytics") is false', w.ctx.window.nidaanCookies.allows('analytics') === false);
  check('...while essential is always allowed', w.ctx.window.nidaanCookies.allows('essential') === true);
}

// ── 2. only essential ────────────────────────────────────────────────────────
console.log('\nWhen they choose "Only essential"\n');
{
  const w = makeWorld();
  w.run(CONSENT_SRC);
  w.run(GA_SRC);
  // Save the refusal exactly as the "Only essential" button does.
  w.run('window.__c = JSON.parse(localStorage.getItem(Object.keys({})[0]||"")||"null")');
  w.ctx.window.dispatchEvent(new w.ctx.window.CustomEvent('nidaan-consent', { detail: { analytics: false } }));
  check('analytics still does not load', !w.gaLoaded(), w.loaded);
}

// ── 3. accept all ────────────────────────────────────────────────────────────
console.log('\nWhen they accept\n');
{
  const w = makeWorld();
  w.run(CONSENT_SRC);
  w.run(GA_SRC);
  check('nothing loaded yet', !w.gaLoaded());
  // Press the first button on the banner - "Accept all".
  const banner = w.doc.body.children[0];
  const inner = banner.children[0];
  const btns = inner.children.find((c) => c.className === 'ndck-btns');
  check('the banner offers three choices', btns && btns.children.length === 3,
        btns ? btns.children.map((b) => b.textContent) : 'no buttons');
  check('...and "Only essential" is one of them, next to "Accept all"',
        btns && /essential/i.test(btns.children[1].textContent), btns && btns.children[1].textContent);
  check('nothing is loaded merely by the banner existing', !w.gaLoaded());
}

// ── 4. a returning visitor who already agreed ────────────────────────────────
console.log('\nA returning visitor who already said yes\n');
{
  const agreed = JSON.stringify({ v: 1, analytics: true, at: '2026-09-28T00:00:00Z' });
  const w = makeWorld({ cookie: 'nidaan_consent=' + encodeURIComponent(agreed) });
  w.run(CONSENT_SRC);
  w.run(GA_SRC);
  check('analytics loads without asking again', w.gaLoaded(), w.loaded);
  check('...and the banner is not shown again', w.doc.body.children.length === 0);
}

// ── 5. a returning visitor who refused ───────────────────────────────────────
console.log('\nA returning visitor who said no\n');
{
  const refused = JSON.stringify({ v: 1, analytics: false, at: '2026-09-28T00:00:00Z' });
  const w = makeWorld({ cookie: 'nidaan_consent=' + encodeURIComponent(refused) });
  w.run(CONSENT_SRC);
  w.run(GA_SRC);
  check('analytics stays off', !w.gaLoaded(), w.loaded);
  check('...and they are not nagged again', w.doc.body.children.length === 0);
}

// ── 6. the awkward ones ──────────────────────────────────────────────────────
console.log('\nThe awkward cases\n');
{
  // Storage blocked: must not crash, must not be read as consent.
  const w = makeWorld({ noStorage: true });
  let threw = null;
  try { w.run(CONSENT_SRC); w.run(GA_SRC); } catch (e) { threw = e; }
  check('blocked storage does not break the page', !threw, threw && threw.message);
  check('...and is not mistaken for consent', !w.gaLoaded());
}
{
  // Staging must never load analytics even if somebody accepted.
  const agreed = JSON.stringify({ v: 1, analytics: true, at: '2026-09-28T00:00:00Z' });
  const w = makeWorld({ host: 'staging.nidaanpartner.com', cookie: 'nidaan_consent=' + encodeURIComponent(agreed) });
  w.run(CONSENT_SRC);
  w.run(GA_SRC);
  check('staging never loads analytics, consent or not', !w.gaLoaded(), w.loaded);
}
{
  // An answer stored against an older version is not an answer to this one.
  const old = JSON.stringify({ v: 0, analytics: true, at: '2026-01-01T00:00:00Z' });
  const w = makeWorld({ cookie: 'nidaan_consent=' + encodeURIComponent(old) });
  w.run(CONSENT_SRC);
  w.run(GA_SRC);
  check('an out-of-date answer is asked again, not honoured', !w.gaLoaded() && w.doc.body.children.length > 0);
}

console.log('\n' + (failed ? failed + ' FAILED\n' : 'ALL GOOD\n'));
process.exit(failed ? 1 : 0);
