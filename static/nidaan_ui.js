/* ═══════════════════════════════════════════════════════════════════════════
   NIDAAN UI COMPONENTS v1.0  —  Jun 2026
   Drop-in JS helpers used across Nidaan pages. No dependencies.
   Include AFTER the page body:  <script src="/static/nidaan_ui.js"></script>

   Exposed globals on `window.ndUI`:
     toast(msg, type='info', duration=3500)
     dismissAllToasts()
     openModal(id)
     closeModal(id)
     skeleton(el, lines=3)           — fill an element with skeleton placeholders
     clearSkeleton(el)
     copyToClipboard(text, label?)   — copies + shows toast
     downloadFile(filename, content, mime?)
     formatINR(amount)               — ₹ formatter
     formatDate(iso)
     timeAgo(iso)
     debounce(fn, ms=200)
     escapeHtml(s)

   Plus a CSS-class-based tab switcher:
     <div class="nd-tabs"><button class="nd-tab active" data-target="#pane-a">A</button>...
     <div id="pane-a">...</div>
     Call ndUI.bindTabs() once after DOM ready.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  const ndUI = {};

  /* ── Toast stack ───────────────────────────────────────────────────────── */
  function ensureToastStack() {
    let s = document.getElementById('nd-toast-stack');
    if (!s) {
      s = document.createElement('div');
      s.id = 'nd-toast-stack';
      document.body.appendChild(s);
    }
    return s;
  }

  ndUI.toast = function (msg, type, duration) {
    type = type || 'info';
    duration = duration == null ? 3500 : duration;
    const stack = ensureToastStack();
    const t = document.createElement('div');
    t.className = 'nd-toast nd-toast-' + type;
    const iconMap = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' };
    t.innerHTML =
      '<span style="flex-shrink:0">' + (iconMap[type] || 'ℹ') + '</span>' +
      '<span style="flex:1">' + ndUI.escapeHtml(String(msg)) + '</span>';
    stack.appendChild(t);
    if (duration > 0) {
      setTimeout(() => {
        t.classList.add('out');
        setTimeout(() => { if (t.parentNode) t.parentNode.removeChild(t); }, 250);
      }, duration);
    }
    return t;
  };

  ndUI.dismissAllToasts = function () {
    const s = document.getElementById('nd-toast-stack');
    if (s) { while (s.firstChild) s.removeChild(s.firstChild); }
  };

  /* ── Modal helpers ─────────────────────────────────────────────────────── */
  ndUI.openModal = function (id) {
    const m = document.getElementById(id);
    if (!m) return;
    m.classList.add('open');
    // Lock body scroll
    document.documentElement.style.overflow = 'hidden';
    // Focus the first focusable element
    setTimeout(() => {
      const first = m.querySelector('input,select,textarea,button,[tabindex]:not([tabindex="-1"])');
      if (first) try { first.focus(); } catch (_) {}
    }, 50);
    // ESC to close
    const onKey = e => { if (e.key === 'Escape') ndUI.closeModal(id); };
    m._ndEscHandler = onKey;
    document.addEventListener('keydown', onKey);
  };

  ndUI.closeModal = function (id) {
    const m = document.getElementById(id);
    if (!m) return;
    m.classList.remove('open');
    document.documentElement.style.overflow = '';
    if (m._ndEscHandler) {
      document.removeEventListener('keydown', m._ndEscHandler);
      m._ndEscHandler = null;
    }
  };

  // Close modal on backdrop click
  document.addEventListener('click', function (e) {
    if (e.target && e.target.classList && e.target.classList.contains('nd-modal-bg')
        && e.target.classList.contains('open')) {
      // Only if click was directly on the backdrop, not inside the modal
      ndUI.closeModal(e.target.id);
    }
  });

  /* ── Skeleton placeholders ─────────────────────────────────────────────── */
  ndUI.skeleton = function (el, lines) {
    if (!el) return;
    if (typeof el === 'string') el = document.getElementById(el) || document.querySelector(el);
    if (!el) return;
    lines = lines || 3;
    const html = [];
    for (let i = 0; i < lines; i++) {
      const widths = ['w-100', 'w-75', 'w-50'];
      html.push('<div class="nd-skeleton nd-skeleton-text ' + widths[i % widths.length] + '"></div>');
    }
    el.innerHTML = html.join('');
  };

  ndUI.clearSkeleton = function (el) {
    if (typeof el === 'string') el = document.getElementById(el) || document.querySelector(el);
    if (!el) return;
    // Caller is expected to set new content; we just remove the skeleton flag
    [].forEach.call(el.querySelectorAll('.nd-skeleton'), n => { if (n.parentNode === el) n.remove(); });
  };

  /* ── Clipboard ─────────────────────────────────────────────────────────── */
  ndUI.copyToClipboard = function (text, label) {
    const fallback = function () {
      try {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        ndUI.toast('Copied' + (label ? ': ' + label : ''), 'success');
      } catch (_) {
        ndUI.toast('Copy failed — please copy manually', 'error');
      }
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        () => ndUI.toast('Copied' + (label ? ': ' + label : ''), 'success'),
        fallback
      );
    } else fallback();
  };

  /* ── File download (vCard, CSV, etc.) ──────────────────────────────────── */
  ndUI.downloadFile = function (filename, content, mime) {
    mime = mime || 'application/octet-stream';
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  };

  /* ── Formatters ────────────────────────────────────────────────────────── */
  ndUI.formatINR = function (amount) {
    if (amount == null || isNaN(amount)) return '—';
    try { return '₹' + Number(amount).toLocaleString('en-IN'); }
    catch (_) { return '₹' + amount; }
  };

  // Server stores SQLite CURRENT_TIMESTAMP as "YYYY-MM-DD HH:MM:SS" (UTC, no
  // timezone marker). Browsers parse such strings as LOCAL time, which on IST
  // browsers produces a -5h30m skew (everything shows "5h ago" right after
  // creation). Normalize: replace space with T, and append Z if no tz marker.
  ndUI.parseServerTime = function (iso) {
    if (!iso) return null;
    let s = String(iso);
    if (s.indexOf(' ') !== -1 && s.indexOf('T') === -1) s = s.replace(' ', 'T');
    if (!/[zZ]$|[+-]\d{2}:?\d{2}$/.test(s)) s += 'Z';
    const d = new Date(s);
    return isNaN(d.getTime()) ? null : d;
  };

  ndUI.formatDate = function (iso) {
    if (!iso) return '—';
    const d = ndUI.parseServerTime(iso);
    if (!d) return iso;
    return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  };

  ndUI.timeAgo = function (iso) {
    if (!iso) return '—';
    const d = ndUI.parseServerTime(iso);
    if (!d) return iso;
    const s = Math.floor((Date.now() - d.getTime()) / 1000);
    if (s < 0)      return 'just now';   // clock skew safety
    if (s < 60)     return s + 's ago';
    if (s < 3600)   return Math.floor(s / 60) + 'm ago';
    if (s < 86400)  return Math.floor(s / 3600) + 'h ago';
    if (s < 2592000) return Math.floor(s / 86400) + 'd ago';
    return ndUI.formatDate(iso);
  };

  /* ── Misc helpers ──────────────────────────────────────────────────────── */
  ndUI.debounce = function (fn, ms) {
    ms = ms || 200;
    let t;
    return function () {
      const ctx = this, args = arguments;
      clearTimeout(t);
      t = setTimeout(() => fn.apply(ctx, args), ms);
    };
  };

  ndUI.escapeHtml = function (s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  };

  /* ── Tab binding ───────────────────────────────────────────────────────── */
  ndUI.bindTabs = function (root) {
    root = root || document;
    [].forEach.call(root.querySelectorAll('.nd-tabs'), function (tg) {
      const tabs = tg.querySelectorAll('.nd-tab');
      tabs.forEach(function (btn) {
        if (btn._ndBound) return;
        btn._ndBound = true;
        btn.addEventListener('click', function () {
          tabs.forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          const target = btn.getAttribute('data-target');
          if (target) {
            // Hide siblings of the target's container that have similar id pattern
            const targetEl = document.querySelector(target);
            if (targetEl && targetEl.parentElement) {
              const peers = targetEl.parentElement.querySelectorAll('[data-tab-pane]');
              if (peers.length) {
                peers.forEach(p => p.style.display = 'none');
              }
              targetEl.style.display = '';
            }
          }
        });
      });
    });
  };

  /* ── Auto-init when DOM is ready ───────────────────────────────────────── */
  function init() {
    ensureToastStack();
    ndUI.bindTabs(document);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.ndUI = ndUI;
})();
