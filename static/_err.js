/* ─────────────────────────────────────────────────────────────────────────────
 * Robust FastAPI error extraction.
 *
 * `data.detail` from a FastAPI error response can be:
 *   (a) a plain string ......... HTTPException(detail="...")
 *   (b) a Pydantic 422 array ... [{loc:[...], msg:"...", type:"..."}, ...]
 *   (c) a structured object .... custom conflict/structured-error responses
 *
 * Without normalization, `new Error(data.detail).message` becomes
 * `"[object Object]"` for (b) and (c). This helper renders a safe string
 * for all three shapes.
 *
 * Usage: throw new Error(_extractErr(data, 'Save failed'));
 * ───────────────────────────────────────────────────────────────────────────── */
(function (root) {
  function _extractErr(data, fallback) {
    if (!data) return fallback || 'Something went wrong';
    var d = data.detail;
    if (d == null) return data.message || data.msg || data.error || fallback || 'Something went wrong';
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) {
      var parts = d.map(function (e) {
        if (!e) return '';
        if (typeof e === 'string') return e;
        var field = Array.isArray(e.loc) && e.loc.length ? e.loc[e.loc.length - 1] : '';
        var msg = e.msg || e.message || '';
        if (field && msg) return field + ': ' + msg;
        return msg || field || '';
      }).filter(Boolean);
      return parts.length ? parts.join('; ') : (fallback || 'Validation failed. Please check your inputs.');
    }
    if (typeof d === 'object') {
      return d.message || d.msg || d.error || d.title || (fallback || 'Something went wrong');
    }
    return String(d) || (fallback || 'Something went wrong');
  }
  root._extractErr = _extractErr;
})(typeof window !== 'undefined' ? window : this);
