/* =============================================================================
 *  nidaan_theme.js — light/dark theme engine for NidaanPartner pages
 * =============================================================================
 *  Sets <html data-theme="dark|light"> from the user's saved choice (default
 *  dark, so nothing changes for existing users). Load it in <head> BEFORE the
 *  body so the theme is applied before first paint (no flash). Any element with
 *  class "nd-theme-toggle" becomes a ☀️/🌙 switch automatically.
 *
 *  API: window.nidaanTheme.get() / .set('light'|'dark') / .toggle()
 * ========================================================================== */
(function () {
  var KEY = 'nidaan_theme';
  var root = document.documentElement;
  function eff(t) { return t === 'light' ? 'light' : 'dark'; }
  function saved() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
  function apply(t) { root.setAttribute('data-theme', eff(t)); }

  // Apply immediately (script is in <head>) to avoid a flash of the wrong theme.
  apply(saved() || 'dark');

  function refreshButtons() {
    var dark = (window.nidaanTheme.get() !== 'light');
    var btns = document.querySelectorAll('.nd-theme-toggle');
    for (var i = 0; i < btns.length; i++) {
      var b = btns[i];
      // Show the mode you'd switch TO, with a plain-language label (Tier II/III).
      b.innerHTML = dark
        ? '☀️ <span class="en">Light</span><span class="hi">लाइट</span>'
        : '🌙 <span class="en">Dark</span><span class="hi">डार्क</span>';
      b.title = dark ? 'Switch to light mode' : 'Switch to dark mode';
      b.setAttribute('aria-label', b.title);
    }
    // keep the HI/EN spans in sync with the page's current language, if any
    try {
      if (typeof getLang === 'function' || document.documentElement.getAttribute('data-lang')) {
        var hi = (document.documentElement.getAttribute('data-lang') === 'hi');
        document.querySelectorAll('.nd-theme-toggle .en').forEach(function (e) { e.style.display = hi ? 'none' : ''; });
        document.querySelectorAll('.nd-theme-toggle .hi').forEach(function (e) { e.style.display = hi ? '' : 'none'; });
      }
    } catch (e) { }
  }

  window.nidaanTheme = {
    get: function () { return saved() || 'dark'; },
    set: function (t) { t = eff(t); try { localStorage.setItem(KEY, t); } catch (e) { } apply(t); refreshButtons(); try { document.dispatchEvent(new CustomEvent('nidaanthemechange', { detail: t })); } catch (e) { } },
    toggle: function () { this.set(this.get() === 'light' ? 'dark' : 'light'); }
  };

  document.addEventListener('DOMContentLoaded', function () {
    var btns = document.querySelectorAll('.nd-theme-toggle');
    for (var i = 0; i < btns.length; i++) {
      btns[i].addEventListener('click', function () { window.nidaanTheme.toggle(); });
    }
    refreshButtons();
  });
})();
