/* NidaanPartner — shared file-picker list with a REMOVE control.
 *
 * GROUND RULE: wherever a person can attach something, they must be able to take it off again.
 * Picking the wrong file is ordinary — a phone camera roll is full of near-identical photos, and
 * a shared PC has three similar PDFs in Downloads. Without a remove button the only escape is to
 * reload the page and start the form over, and on a multi-file input there is no escape at all:
 * re-picking replaces the whole set, so one wrong file out of four means redoing all four.
 *
 * A file input's `files` is a read-only FileList, which is why this got skipped everywhere. It IS
 * writable via DataTransfer, which every browser we support has had for years; where it is not,
 * we fall back to clearing the input, because leaving a file the person asked to remove is worse
 * than making them re-pick.
 *
 * Usage — the input keeps its own onchange, which simply calls this:
 *     <input type="file" id="claimDocs" multiple onchange="ndFiles('claimDocs','claimDocList')">
 *     <div id="claimDocList"></div>
 * Optional 3rd arg runs after every render (show/hide an upload button, enable submit, …).
 */
(function (w, d) {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c];
    });
  }

  function kb(bytes) {
    var n = Number(bytes) || 0;
    return n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB";
  }

  // Registered so a removal can re-run the same callback the picker was set up with.
  var HOOKS = {};

  /** Render the chosen files, each with a Remove control. */
  function ndFiles(inputId, listId, onRender) {
    var inp = d.getElementById(inputId);
    var list = d.getElementById(listId);
    if (!inp || !list) return;
    if (typeof onRender === "function") HOOKS[inputId] = onRender;

    var files = Array.prototype.slice.call(inp.files || []);
    if (!files.length) {
      list.innerHTML = "";
      var cb0 = HOOKS[inputId];
      if (cb0) cb0(0);
      return;
    }

    list.innerHTML = files.map(function (f, i) {
      return '<div class="ndf-row">'
        + '<span class="ndf-nm" title="' + esc(f.name) + '">📄 ' + esc(f.name) + '</span>'
        + '<span class="ndf-sz">' + kb(f.size) + "</span>"
        + '<button type="button" class="ndf-x" data-i="' + i + '"'
        + ' aria-label="Remove ' + esc(f.name) + '">Remove</button>'
        + "</div>";
    }).join("");

    // Delegated so re-rendering never leaves a dead handler behind.
    Array.prototype.forEach.call(list.querySelectorAll(".ndf-x"), function (b) {
      b.onclick = function () { ndFileRemove(inputId, listId, parseInt(b.dataset.i, 10)); };
    });

    var cb = HOOKS[inputId];
    if (cb) cb(files.length);
  }

  /** Drop one file from the picker and re-render. */
  function ndFileRemove(inputId, listId, idx) {
    var inp = d.getElementById(inputId);
    if (!inp) return;
    var keep = Array.prototype.slice.call(inp.files || []).filter(function (_, i) { return i !== idx; });
    try {
      var dt = new DataTransfer();
      keep.forEach(function (f) { dt.items.add(f); });
      inp.files = dt.files;
    } catch (e) {
      // No DataTransfer: clear the lot rather than keep a file the person just removed.
      inp.value = "";
    }
    ndFiles(inputId, listId);
    // Let anything else listening (validation, submit-enable) know the selection changed.
    try { inp.dispatchEvent(new Event("change", {bubbles: true})); } catch (e2) {}
  }

  /** True when the picker currently holds at least one file — for "this is required" checks. */
  function ndHasFile(inputId) {
    var inp = d.getElementById(inputId);
    return !!(inp && inp.files && inp.files.length);
  }

  // One stylesheet, injected once, using the app's own tokens so it reads in both themes.
  function styles() {
    if (d.getElementById("ndFilesCss")) return;
    var st = d.createElement("style");
    st.id = "ndFilesCss";
    st.textContent =
      ".ndf-row{display:flex;align-items:center;gap:.5rem;padding:.35rem .5rem;margin-top:.35rem;"
      + "background:var(--nd-bg-surface-2,rgba(148,163,184,.10));border:1px solid var(--nd-border,rgba(148,163,184,.28));"
      + "border-radius:8px;font-size:.82rem;color:var(--nd-text-secondary,#475569);text-align:left}"
      + ".ndf-nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}"
      + ".ndf-sz{color:var(--nd-text-faint,#94a3b8);font-size:.74rem;white-space:nowrap}"
      + ".ndf-x{background:none;border:1px solid var(--nd-border,rgba(148,163,184,.35));"
      + "color:var(--nd-danger-text,#dc2626);border-radius:6px;padding:.2rem .55rem;font-size:.74rem;"
      + "font-weight:700;cursor:pointer;font-family:inherit;white-space:nowrap;line-height:1.3}"
      + ".ndf-x:hover{background:var(--nd-danger-soft,rgba(220,38,38,.12))}"
      + "@media(max-width:420px){.ndf-sz{display:none}}";
    (d.head || d.documentElement).appendChild(st);
  }
  if (d.readyState === "loading") d.addEventListener("DOMContentLoaded", styles);
  else styles();

  w.ndFiles = ndFiles;
  w.ndFileRemove = ndFileRemove;
  w.ndHasFile = ndHasFile;
})(window, document);
