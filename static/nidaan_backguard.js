/* Shared PWA back-button guard (Nidaan/Sarathi dashboards).
 *
 * Problem: when installed as a PWA (display:standalone), pressing the phone's Back button
 * with no in-app history EXITS the app — the user has to reopen and lose their place.
 *
 * Fix: keep one "guard" entry in history. On Back:
 *   - if an overlay (modal/drawer) is open → close the top one and stay in the app;
 *   - else, in an installed PWA → re-arm so the app is never accidentally dropped;
 *   - else (normal browser tab, nothing open) → let Back behave normally.
 *
 * Pages register their overlays:  PWABack.register(isOpenFn, closeFn)
 * (most-recently-registered open overlay is treated as the topmost).
 */
(function () {
  var overlays = [];
  var standalone = false;
  try {
    standalone = (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches)
              || window.navigator.standalone === true;
  } catch (e) {}

  function arm() { try { history.pushState({ _bg: 1 }, ''); } catch (e) {} }
  function topOpen() {
    for (var i = overlays.length - 1; i >= 0; i--) {
      try { if (overlays[i].isOpen()) return overlays[i]; } catch (e) {}
    }
    return null;
  }

  window.PWABack = {
    register: function (isOpen, close) {
      if (typeof isOpen === 'function' && typeof close === 'function') {
        overlays.push({ isOpen: isOpen, close: close });
      }
    },
    // Convenience for elements toggled purely by inline display (none <-> flex/block).
    registerEl: function (id, closeFn) {
      var self = this;
      self.register(
        function () { var e = document.getElementById(id); return !!e && getComputedStyle(e).display !== 'none'; },
        closeFn || function () { var e = document.getElementById(id); if (e) e.style.display = 'none'; }
      );
    },
    // Convenience for overlays toggled by an 'open' class.
    registerClass: function (id, closeFn) {
      this.register(
        function () { var e = document.getElementById(id); return !!e && e.classList.contains('open'); },
        closeFn
      );
    }
  };

  window.addEventListener('load', function () { arm(); });
  window.addEventListener('popstate', function () {
    var o = topOpen();
    if (o) { try { o.close(); } catch (e) {} arm(); return; }  // closed an overlay → stay
    if (standalone) { arm(); }                                 // installed app → don't drop out
    // browser tab with nothing open → allow normal Back
  });
})();
