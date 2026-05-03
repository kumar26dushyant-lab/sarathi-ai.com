/* ═══════════════════════════════════════════════════════════
   SARATHI-AI — Dark Mode Toggle Logic
   Loaded in <head> for FOUC prevention + toggle management.
   Saves to localStorage('sarathi_theme').
   ═══════════════════════════════════════════════════════════ */

// ── FOUC prevention: apply saved theme immediately ──────
(function() {
  var t = localStorage.getItem('sarathi_theme');
  if (t === 'dark' || (!t && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    document.documentElement.setAttribute('data-theme', 'dark');
  }
})();

// ── Toggle function ─────────────────────────────────────
function toggleTheme() {
  var html = document.documentElement;
  var isDark = html.getAttribute('data-theme') === 'dark';
  var next = isDark ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  localStorage.setItem('sarathi_theme', next);
  _updateToggleIcons();
}

// ── Update all toggle icons on page ─────────────────────
function _updateToggleIcons() {
  var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  var btns = document.querySelectorAll('.theme-toggle');
  for (var i = 0; i < btns.length; i++) {
    btns[i].textContent = isDark ? '☀️' : '🌙';
    btns[i].title = isDark ? 'Switch to light mode' : 'Switch to dark mode';
    btns[i].setAttribute('aria-label', isDark ? 'Switch to light mode' : 'Switch to dark mode');
  }
}

// ── Listen for system theme changes ─────────────────────
if (window.matchMedia) {
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(e) {
    // Only auto-switch if user hasn't manually set a preference
    if (!localStorage.getItem('sarathi_theme')) {
      document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light');
      _updateToggleIcons();
    }
  });
}

// ── Init icons on DOM ready ─────────────────────────────
document.addEventListener('DOMContentLoaded', _updateToggleIcons);
