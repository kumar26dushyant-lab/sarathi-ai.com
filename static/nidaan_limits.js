/* HOW BIG A DOCUMENT MAY BE - the pages' copy of biz_nidaan_limits.py (3 Oct 2026).
   deploy/verify-limits.py fails the build if these numbers and the server's disagree.
   95 MB, not 100: Cloudflare refuses a request over 100 MB, and a request is the file plus a
   little form data. */
(function(){
  if (window.NidaanLimits) return;
  var MB = 1000 * 1000;            // decimal megabytes: they pass however Cloudflare counts its 100
  window.NidaanLimits = {
    docMaxMB: 95,
    docMaxBytes: 95 * MB,          // one document
    requestMaxBytes: 99 * MB,      // one upload request
    filesPerRequest: 20,           // the server's own count per request
    // Bigger than one request allows? Send it alone. Smaller ones are grouped under this.
    tooBig: function(file){ return !!file && file.size > this.docMaxBytes; },
    // The files in `files` that are over the limit - tell the person before sending anything.
    oversize: function(files){
      var self = this;
      return Array.prototype.filter.call(files || [], function(f){ return f.size > self.docMaxBytes; });
    },
    // Split files into requests that each stay under the request limit and the per-request count,
    // so choosing several big files works instead of being refused as one huge request. Files over
    // the document limit are left out - check oversize() first and say so.
    batches: function(files, maxCount){
      var out = [], cur = [], tot = 0, n = maxCount || this.filesPerRequest, self = this;
      Array.prototype.forEach.call(files || [], function(f){
        if (f.size > self.docMaxBytes) return;
        if (cur.length && (tot + f.size > self.requestMaxBytes || cur.length >= n)){ out.push(cur); cur = []; tot = 0; }
        cur.push(f); tot += f.size;
      });
      if (cur.length) out.push(cur);
      return out;
    },
    // Send files to `url` in batches that fit, one request after another, and say exactly what
    // happened: {ok, sent, refused: [names over the limit], failed: [names that did not go],
    // detail: the server's last words}. Nothing is swallowed - the caller tells the person.
    // opts: field ('files'), headers, extra {name: value} on every request, onProgress(i, n).
    send: async function(url, files, opts){
      opts = opts || {};
      var self = this, field = opts.field || 'files';
      var refused = this.oversize(files).map(function(f){ return f.name; });
      var groups = this.batches(files), sent = 0, failed = [], detail = '';
      for (var i = 0; i < groups.length; i++){
        var fd = new FormData();
        groups[i].forEach(function(f){ fd.append(field, f); });
        if (opts.extra) Object.keys(opts.extra).forEach(function(k){ fd.append(k, opts.extra[k]); });
        if (opts.onProgress) { try { opts.onProgress(i + 1, groups.length); } catch (e) {} }
        try {
          var r = await fetch(url, { method: 'POST', headers: opts.headers || {}, body: fd });
          var d = {}; try { d = await r.json(); } catch (e) {}
          if (r.ok) sent += groups[i].length;
          else {
            failed = failed.concat(groups[i].map(function(f){ return f.name; }));
            detail = (typeof d.detail === 'string' && d.detail) || ('Upload failed (' + r.status + ')');
          }
        } catch (e) {
          failed = failed.concat(groups[i].map(function(f){ return f.name; }));
          detail = 'Connection lost';
        }
      }
      return { ok: !refused.length && !failed.length, sent: sent, refused: refused, failed: failed, detail: detail };
    },
    // One sentence for what send() reported, in the page's language. '' when everything went.
    report: function(res, hi){
      var bits = [];
      if (res.refused && res.refused.length) bits.push((hi ? 'सीमा (' + this.docMaxMB + ' MB) से बड़ी, नहीं भेजी: ' : 'Over the ' + this.docMaxMB + ' MB limit, not sent: ') + res.refused.join(', '));
      if (res.failed && res.failed.length) bits.push((hi ? 'अपलोड नहीं हुई: ' : 'Did not upload: ') + res.failed.join(', ') + (res.detail ? ' (' + res.detail + ')' : ''));
      return bits.join(' · ');
    },
    text: function(hi){ return hi ? ('हर फ़ाइल ' + this.docMaxMB + ' MB तक') : ('Up to ' + this.docMaxMB + ' MB each'); },
    refusal: function(name, size, hi){
      var got = Math.round(size / MB) + ' MB', lim = this.docMaxMB + ' MB';
      return hi ? (name + ' ' + got + ' की है - सीमा ' + lim + ' है। इसे PDF में भेजें, या हिस्सों में बाँटें।')
                : (name + ' is ' + got + ' - the limit is ' + lim + '. Send it as a PDF, or split it into parts.');
    }
  };
})();
