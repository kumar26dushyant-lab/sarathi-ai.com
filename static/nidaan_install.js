/* ─────────────────────────────────────────────────────────────────────────────
   Nidaan — shared PWA install helper (subscriber app + ops app).

   Why this exists:
   • On Android/desktop Chrome/Edge the browser fires `beforeinstallprompt`; we
     capture it and offer a one-tap Install.
   • On iOS Safari that event NEVER fires — the only way to install is the manual
     Share → "Add to Home Screen" flow. iOS also only allows Web Push AT ALL once
     the app is installed to the home screen (iOS 16.4+). So the iOS install guide
     is what makes notifications work there.
   • Once installed (display-mode: standalone) notifications are attributed to the
     APP (its own icon), not "Chrome • site" — which removes the "Possible spam /
     Unsubscribe" browser chrome the user saw.

   Config (set BEFORE loading this script):
     window.NIDAAN_APP_ID   — 'sub' | 'ops' (dismissal is remembered per app)
     window.NIDAAN_APP_NAME — display name, e.g. 'Nidaan Partner'
   Public API:
     NidaanInstall.isStandalone()  → bool
     NidaanInstall.available()     → bool (can we offer an install right now?)
     NidaanInstall.show()          → trigger install (Android prompt or iOS guide)
   ──────────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';

  var APP_ID   = window.NIDAAN_APP_ID   || 'app';
  var APP_NAME = window.NIDAAN_APP_NAME || 'Nidaan';
  var DISMISS_KEY  = 'nidaan_install_dismissed_' + APP_ID;
  var DISMISS_DAYS = 10;          // don't nag: re-offer only after this many days
  var deferred = null;            // captured beforeinstallprompt event (Android)

  function isStandalone() {
    return (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches)
        || window.navigator.standalone === true;
  }
  function isIOS() {
    return /iphone|ipad|ipod/i.test(navigator.userAgent)
        || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1); // iPadOS 13+
  }
  function isAndroid() { return /android/i.test(navigator.userAgent); }
  function dismissedRecently() {
    try {
      var t = parseInt(localStorage.getItem(DISMISS_KEY) || '0', 10);
      return t && (Date.now() - t) < DISMISS_DAYS * 864e5;
    } catch (e) { return false; }
  }
  function setDismissed() { try { localStorage.setItem(DISMISS_KEY, String(Date.now())); } catch (e) {} }

  // ── styles (injected once) ──────────────────────────────────────────────────
  function ensureStyle() {
    if (document.getElementById('ndInstallStyle')) return;
    var s = document.createElement('style');
    s.id = 'ndInstallStyle';
    s.textContent =
      '#ndInstallBar{position:fixed;left:12px;right:12px;bottom:calc(12px + env(safe-area-inset-bottom));z-index:2147483000;' +
      'display:flex;align-items:center;gap:.7rem;background:linear-gradient(90deg,#0c4a6e,#0891b2);color:#fff;' +
      'border:1px solid rgba(6,182,212,.4);border-radius:14px;padding:.7rem .8rem;box-shadow:0 12px 34px rgba(0,0,0,.45);' +
      'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;max-width:520px;margin:0 auto;animation:ndInUp .25s ease}' +
      '@keyframes ndInUp{from{transform:translateY(14px);opacity:0}to{transform:translateY(0);opacity:1}}' +
      '#ndInstallBar img{width:34px;height:34px;border-radius:8px;flex-shrink:0}' +
      '#ndInstallBar .ndi-t{font-weight:800;font-size:.86rem;line-height:1.15}' +
      '#ndInstallBar .ndi-s{font-size:.72rem;color:rgba(255,255,255,.82);margin-top:.1rem}' +
      '#ndInstallBar .ndi-go{background:#fff;color:#0891b2;border:none;padding:.5rem .9rem;border-radius:9px;font-weight:800;font-size:.82rem;cursor:pointer;white-space:nowrap}' +
      '#ndInstallBar .ndi-x{background:rgba(255,255,255,.16);color:#fff;border:none;width:30px;height:30px;border-radius:8px;font-size:.9rem;cursor:pointer;flex-shrink:0}' +
      '#ndInstallModal{position:fixed;inset:0;z-index:2147483001;background:rgba(0,0,0,.72);backdrop-filter:blur(5px);display:flex;align-items:flex-end;justify-content:center;padding:0}' +
      '#ndInstallModal .ndi-sheet{background:#0a1628;color:#fff;border:1px solid rgba(255,255,255,.16);border-radius:18px 18px 0 0;width:100%;max-width:520px;padding:1.25rem 1.25rem calc(1.5rem + env(safe-area-inset-bottom));font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;animation:ndSheet .28s ease}' +
      '@keyframes ndSheet{from{transform:translateY(100%)}to{transform:translateY(0)}}' +
      '#ndInstallModal h3{font-size:1.05rem;font-weight:800;margin:0 0 .3rem}' +
      '#ndInstallModal p{font-size:.86rem;color:rgba(255,255,255,.72);margin:0 0 1rem;line-height:1.45}' +
      '#ndInstallModal ol{margin:0 0 1rem;padding-left:1.1rem;font-size:.9rem;line-height:1.7}' +
      '#ndInstallModal .ndi-share{display:inline-flex;width:20px;height:20px;vertical-align:-4px;background:#22d3ee;border-radius:5px;color:#04121f;align-items:center;justify-content:center;font-weight:900;font-size:.8rem}' +
      '#ndInstallModal .ndi-close{width:100%;background:#22d3ee;color:#04121f;border:none;padding:.8rem;border-radius:10px;font-weight:800;font-size:.92rem;cursor:pointer}';
    document.head.appendChild(s);
  }

  function removeBar() { var b = document.getElementById('ndInstallBar'); if (b) b.remove(); }

  // ── Android / Chrome install bar (uses the captured prompt) ─────────────────
  function showAndroidBar() {
    if (document.getElementById('ndInstallBar') || !document.body) return;
    ensureStyle();
    var bar = document.createElement('div');
    bar.id = 'ndInstallBar';
    bar.innerHTML =
      '<img src="/static/nidaan_logo.png" alt="">' +
      '<div style="flex:1;min-width:0">' +
        '<div class="ndi-t">📲 Install the ' + APP_NAME + ' app</div>' +
        '<div class="ndi-s">Home-screen icon · instant notifications · faster</div>' +
      '</div>' +
      '<button class="ndi-go">Install</button>' +
      '<button class="ndi-x" aria-label="Dismiss">✕</button>';
    bar.querySelector('.ndi-go').onclick = doAndroidInstall;
    bar.querySelector('.ndi-x').onclick  = function () { removeBar(); setDismissed(); };
    document.body.appendChild(bar);
  }

  function doAndroidInstall() {
    if (!deferred) { removeBar(); return; }
    deferred.prompt();
    deferred.userChoice.then(function () { deferred = null; removeBar(); });
  }

  // ── iOS install bar + instruction sheet ─────────────────────────────────────
  function showIOSBar() {
    if (document.getElementById('ndInstallBar') || !document.body) return;
    ensureStyle();
    var bar = document.createElement('div');
    bar.id = 'ndInstallBar';
    bar.innerHTML =
      '<img src="/static/nidaan_logo.png" alt="">' +
      '<div style="flex:1;min-width:0">' +
        '<div class="ndi-t">📲 Add ' + APP_NAME + ' to your Home Screen</div>' +
        '<div class="ndi-s">Needed for app notifications on iPhone</div>' +
      '</div>' +
      '<button class="ndi-go">How</button>' +
      '<button class="ndi-x" aria-label="Dismiss">✕</button>';
    bar.querySelector('.ndi-go').onclick = showIOSSheet;
    bar.querySelector('.ndi-x').onclick  = function () { removeBar(); setDismissed(); };
    document.body.appendChild(bar);
  }

  function showIOSSheet() {
    ensureStyle();
    var m = document.getElementById('ndInstallModal');
    if (m) m.remove();
    m = document.createElement('div');
    m.id = 'ndInstallModal';
    m.innerHTML =
      '<div class="ndi-sheet">' +
        '<h3>Add ' + APP_NAME + ' to Home Screen</h3>' +
        '<p>This installs the app so it opens full-screen and can send you real notifications (iPhone allows notifications only for installed apps).</p>' +
        '<ol>' +
          '<li>Tap the <span class="ndi-share">⬆</span> <b>Share</b> button in Safari\'s toolbar.</li>' +
          '<li>Scroll down and tap <b>“Add to Home Screen”</b>.</li>' +
          '<li>Tap <b>Add</b> — then open ' + APP_NAME + ' from your home screen.</li>' +
        '</ol>' +
        '<button class="ndi-close">Got it</button>' +
      '</div>';
    m.addEventListener('click', function (e) { if (e.target === m) m.remove(); });
    m.querySelector('.ndi-close').onclick = function () { m.remove(); removeBar(); setDismissed(); };
    document.body.appendChild(m);
  }

  // ── wiring ──────────────────────────────────────────────────────────────────
  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    deferred = e;
    if (isStandalone() || dismissedRecently()) return;
    showAndroidBar();
  });
  window.addEventListener('appinstalled', function () { removeBar(); setDismissed(); deferred = null; });

  function maybeOfferIOS() {
    if (isStandalone() || dismissedRecently()) return;
    if (isIOS()) setTimeout(showIOSBar, 1400);   // iOS never fires beforeinstallprompt
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', maybeOfferIOS);
  } else { maybeOfferIOS(); }

  // ── public API (for an in-app "Enable notifications / Get the app" button) ──
  window.NidaanInstall = {
    isStandalone: isStandalone,
    available: function () { return !!deferred || (isIOS() && !isStandalone()); },
    show: function () {
      if (deferred) doAndroidInstall();
      else if (isIOS()) showIOSSheet();
      else if (isAndroid()) showAndroidBar();
    }
  };
})();
