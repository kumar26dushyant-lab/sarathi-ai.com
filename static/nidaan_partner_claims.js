/* =============================================================================
 *  nidaan_partner_claims.js — SHARED partner claims + Level-2 renderer
 * =============================================================================
 *  ONE source of truth for the "your raised claims" list + the Level-2 money
 *  flow (pay / advance-free / share-link / confirmation), used by BOTH the
 *  branch portal (nidaan_branch.html) and the staff "My Business" panel
 *  (nidaan_ops.html). Behaviour is identical on both; only the transport
 *  (API base + auth), the data source, and the language differ — all injected
 *  via init(cfg). One instance per page (each page has a single partner list).
 *
 *  cfg = {
 *    mount:      element id to render the claims list into,
 *    getClaims:  () => Array,                 // current claims
 *    getL2:      () => { fee, charge_required },
 *    hi:         () => bool,                   // Hindi?  (branch → false)
 *    api:        (path, opts) => Promise<Response>,  // base + auth baked in
 *    l2Path:     (id, action) => string,      // e.g. '/claims/'+id+'/'+action
 *    reload:     () => void                    // re-fetch claims then render()
 *  }
 * ========================================================================== */
(function () {
  let CFG = null;
  let VIEW = 'active';

  function hi() { return !!(CFG && CFG.hi && CFG.hi()); }
  function esc(s) { return String(s == null ? '' : s).replace(/[<>&"]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' }[c])); }
  function fmt(n) { return (Number(n) || 0).toLocaleString('en-IN'); }
  function fmtDate(s) { if (!s) return '—'; const d = new Date(String(s).replace(' ', 'T') + 'Z'); return isNaN(d) ? String(s).slice(0, 10) : d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }); }
  function mountEl() { return document.getElementById(CFG.mount); }

  function render() {
    const wrap = mountEl(); if (!wrap) return;
    const h = hi();
    const all = (CFG.getClaims && CFG.getClaims()) || [];
    const active = all.filter(c => !c.archived), archived = all.filter(c => c.archived);
    const claims = VIEW === 'archived' ? archived : active;
    const tabs = `<div style="display:flex;gap:.4rem;margin-bottom:.6rem">
      <button class="btn ${VIEW === 'active' ? 'btn-primary btn-cyan' : 'btn-ghost'}" style="font-size:.78rem;padding:.3rem .7rem" onclick="NidaanPartnerClaims.setTab('active')">${h ? 'सक्रिय' : 'Active'} (${active.length})</button>
      <button class="btn ${VIEW === 'archived' ? 'btn-primary btn-cyan' : 'btn-ghost'}" style="font-size:.78rem;padding:.3rem .7rem" onclick="NidaanPartnerClaims.setTab('archived')">🗄️ ${h ? 'संग्रहित' : 'Archived'} (${archived.length})</button></div>`;
    if (!all.length) { wrap.innerHTML = `<div class="empty">${h ? 'अभी कोई क्लेम नहीं। ऊपर फ़ॉर्म से दर्ज करें।' : "No claims yet — use the form above to submit your customer's rejected claim."}</div>`; return; }
    if (!claims.length) { wrap.innerHTML = tabs + `<div class="empty">${VIEW === 'archived' ? (h ? 'कोई संग्रहित क्लेम नहीं।' : 'No archived claims.') : (h ? 'कोई सक्रिय क्लेम नहीं।' : 'No active claims.')}</div>`; return; }
    const l2cfg = (CFG.getL2 && CFG.getL2()) || { fee: 0, charge_required: false };
    const bs = 'padding:.35rem .6rem;font-size:.76rem;margin-top:.3rem';
    const rows = claims.map(c => {
      let l2 = `<span style="color:var(--nd-text-faint)">${h ? 'समीक्षाधीन' : 'Under review'}</span>`;
      if (c.l2_payment_status === 'paid') {
        l2 = `<span style="color:var(--nd-success-text);font-weight:700">${h ? 'लीगल के लिए भेजा ✓' : 'Queued for legal ✓'}</span>`;
      } else if (c.review_outcome === 'can_fight') {
        const f = (c.l2_fee != null ? c.l2_fee : l2cfg.fee);
        const badge = `<div style="color:var(--nd-success-text);font-weight:600;margin-bottom:.15rem">${h ? ('🎉 समीक्षा: लड़ा जा सकता है — Level-2 भेजने के लिए ₹' + f + ' + GST दें') : ('🎉 Reviewed: can be challenged — pay ₹' + f + ' + GST to move it to Level-2')}</div>`;
        if (l2cfg.charge_required) {
          l2 = badge
            + `<button class="btn btn-primary btn-cyan" style="${bs}" onclick="NidaanPartnerClaims.pay(${c.claim_id})">${h ? ('₹' + f + ' + GST भुगतान करें') : ('Pay ₹' + f + ' + GST now')}</button>`
            + `<button class="btn-sm btn-ghost" style="${bs};margin-left:.3rem;color:var(--nd-cyan-text)" onclick="NidaanPartnerClaims.link(${c.claim_id})">🔗 ${h ? 'लिंक भेजें' : 'Share link'}</button>`;
        } else {
          l2 = badge + `<button class="btn btn-primary btn-cyan" style="${bs}" onclick="NidaanPartnerClaims.advance(${c.claim_id})">${h ? 'Level-2 भेजें (मुफ़्त)' : 'Send to Level-2 (free)'}</button>`;
        }
      } else if (c.review_outcome === 'no_scope') {
        l2 = `<span style="color:var(--nd-warning-text)">${h ? 'समीक्षा: कोई गुंजाइश नहीं' : 'Reviewed: no scope'}</span>`;
      }
      return `<tr>
        <td>${esc(c.insured_name || '')}<br><span style="font-size:.74rem;color:var(--nd-text-faint)">${esc(c.insured_phone || '')}</span></td>
        <td>${esc((c.claim_type || '').replace(/_/g, ' '))}</td>
        <td style="text-align:right">${c.disputed_amount ? ('₹' + fmt(c.disputed_amount)) : '—'}</td>
        <td>${esc((c.status || '').replace(/_/g, ' '))}</td>
        <td>${l2}</td>
        <td><button class="btn-sm btn-ghost" style="${bs};white-space:nowrap" onclick="NidaanPartnerClaims.docs(${c.claim_id})">📎 ${h ? 'दस्तावेज़' : 'Documents'}</button></td>
        <td style="font-size:.74rem;color:var(--nd-text-faint)">${fmtDate(c.created_at)}</td>
      </tr>
      <tr id="npDocRow_${c.claim_id}" style="display:none"><td colspan="7" style="background:var(--nd-bg-surface-2,#f8fafc);padding:.7rem .9rem">
        <div id="npDocPanel_${c.claim_id}" style="font-size:.82rem">…</div>
      </td></tr>`;
    }).join('');
    wrap.innerHTML = tabs + `<div class="table-wrap"><table>
      <thead><tr><th>${h ? 'ग्राहक' : 'Customer'}</th><th>${h ? 'प्रकार' : 'Type'}</th><th>${h ? 'राशि' : 'Amount'}</th><th>${h ? 'स्थिति' : 'Status'}</th><th>Level-2</th><th>${h ? 'दस्तावेज़' : 'Documents'}</th><th>${h ? 'दर्ज' : 'Raised'}</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
  }

  function ensureRzp(cb) {
    if (window.Razorpay) { cb(); return; }
    const s = document.createElement('script');
    s.src = 'https://checkout.razorpay.com/v1/checkout.js';
    s.onload = cb;
    s.onerror = () => alert(hi() ? 'भुगतान लाइब्रेरी लोड नहीं हुई। कनेक्शन जांचें।' : 'Could not load the payment gateway. Check your connection and try again.');
    document.head.appendChild(s);
  }

  // Screenshot-friendly "moving to Level-2" confirmation (share with the customer).
  function confirmMovedToL2(claimId) {
    const h = hi();
    const ov = document.createElement('div'); ov.setAttribute('data-l2c', '1');
    ov.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.72);z-index:10001;display:flex;align-items:center;justify-content:center;padding:1rem';
    ov.innerHTML = '<div style="background:#0f1e3a;border:1px solid rgba(52,211,153,.45);border-radius:16px;max-width:420px;width:100%;padding:1.6rem;text-align:center;box-shadow:0 10px 40px rgba(0,0,0,.5)">'
      + '<div style="font-size:2.6rem">⚖️✅</div>'
      + '<div style="font-size:1.2rem;font-weight:800;color:#6ee7b7;margin:.5rem 0">' + (h ? 'आपका क्लेम Level-2 पर जा रहा है!' : 'Your claim is moving to Level-2!') + '</div>'
      + '<div style="color:rgba(255,255,255,.8);font-size:.92rem;line-height:1.55">' + (h ? ('क्लेम #' + String(claimId).padStart(3, '0') + ' — भुगतान प्राप्त ✓। हमारी कानूनी टीम अब सही क्लेम के लिए लड़ेगी।') : ('Claim #' + String(claimId).padStart(3, '0') + ' — payment received ✓. Our legal team will now take up the fight for the rightful claim.')) + '</div>'
      + '<div style="font-size:.76rem;color:rgba(255,255,255,.4);margin-top:.7rem">📸 ' + (h ? 'ग्राहक को दिखाने के लिए स्क्रीनशॉट लें।' : 'You can screenshot this to reassure your customer.') + '</div>'
      + '<button onclick="this.closest(\'[data-l2c]\').remove()" style="margin-top:1rem;background:#06b6d4;color:#fff;border:none;border-radius:8px;padding:.6rem 1.6rem;font-weight:700;cursor:pointer">' + (h ? 'ठीक है' : 'Done') + '</button>'
      + '</div>';
    document.body.appendChild(ov);
  }

  async function pay(claimId) {
    const h = hi();
    try {
      const r = await CFG.api(CFG.l2Path(claimId, 'l2-pay'), { method: 'POST' });
      const o = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(o.detail || 'Could not start the payment');
      ensureRzp(() => {
        const rzp = new Razorpay({
          key: o.razorpay_key_id, amount: o.amount, currency: o.currency || 'INR',
          name: 'Nidaan Partner', description: 'Level-2 fee — Claim #' + claimId,
          order_id: o.order_id, theme: { color: '#06b6d4' },
          handler: async function (resp) {
            try {
              const v = await CFG.api(CFG.l2Path(claimId, 'l2-pay-verify'), {
                method: 'POST',
                body: JSON.stringify({ razorpay_order_id: resp.razorpay_order_id, razorpay_payment_id: resp.razorpay_payment_id, razorpay_signature: resp.razorpay_signature })
              });
              const vd = await v.json().catch(() => ({}));
              if (v.ok && vd.status === 'pending') { alert(vd.message || (h ? 'भुगतान प्रोसेस हो रहा है — जल्द पुष्टि होगी।' : 'Payment is still processing — we will confirm shortly.')); CFG.reload(); return; }
              if (!v.ok) throw new Error(vd.detail || 'Payment verification failed');
              confirmMovedToL2(claimId); CFG.reload();
            } catch (e) { alert(e.message); }
          }
        });
        rzp.on('payment.failed', function () { alert(h ? 'भुगतान विफल या रद्द। कृपया फिर प्रयास करें।' : 'Payment failed or was cancelled. Please try again.'); });
        rzp.open();
      });
    } catch (e) { alert(e.message); }
  }

  async function advance(claimId) {
    const h = hi();
    if (!confirm(h ? ('क्लेम #' + claimId + ' को Level-2 (कानूनी टीम) पर भेजें? कोई शुल्क नहीं।') : ('Send Claim #' + claimId + ' to the legal team (Level-2)? No charge applies.'))) return;
    try {
      const r = await CFG.api(CFG.l2Path(claimId, 'l2-advance'), { method: 'POST' });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || 'Could not send to Level-2');
      confirmMovedToL2(claimId); CFG.reload();
    } catch (e) { alert(e.message); }
  }

  async function link(claimId) {
    const h = hi();
    try {
      const r = await CFG.api(CFG.l2Path(claimId, 'l2-payment-link'), { method: 'POST' });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || 'Could not create payment link');
      const url = d.short_url;
      const wa = 'https://wa.me/?text=' + encodeURIComponent((h ? ('Namaste! Apne insurance claim ka Level-2 legal process shuru karne ke liye ₹' + d.fee + ' yahan pay karein (Nidaan Partner): ') : ('Namaste! Apne insurance claim ka Level-2 legal process shuru karne ke liye ₹' + d.fee + ' yahan pay karein (Nidaan Partner): ')) + url);
      const ov = document.createElement('div');
      ov.style.cssText = 'position:fixed;inset:0;z-index:10000;background:rgba(2,12,27,.9);display:flex;align-items:center;justify-content:center;padding:1.2rem';
      ov.innerHTML = '<div style="max-width:420px;width:100%;background:#0f2038;border:1px solid rgba(6,182,212,.4);border-radius:14px;padding:1.4rem">'
        + '<div style="font-weight:800;color:#fff;font-size:1.05rem;margin-bottom:.5rem">🔗 ' + (h ? 'भुगतान लिंक तैयार — क्लेम #' : 'Payment link ready — Claim #') + claimId + '</div>'
        + '<div style="font-size:.82rem;color:rgba(255,255,255,.6);margin-bottom:.8rem">' + (h ? ('ग्राहक को यह भेजें ताकि वे ₹' + d.fee + ' Level-2 शुल्क दें। 3 दिन मान्य। भुगतान होते ही क्लेम अपने-आप Level-2 पर चला जाएगा।') : ('Share this with your customer to pay the ₹' + d.fee + ' Level-2 fee. Valid 3 days. The claim moves to Level-2 automatically once paid.')) + '</div>'
        + '<input readonly value="' + esc(url) + '" onclick="this.select()" style="width:100%;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14);color:#fff;padding:.55rem .7rem;border-radius:8px;font-size:.8rem;margin-bottom:.7rem">'
        + '<div style="display:flex;gap:.5rem;flex-wrap:wrap">'
        + '<button id="npcPlCopy" class="btn btn-primary btn-cyan" style="flex:1">📋 ' + (h ? 'कॉपी' : 'Copy') + '</button>'
        + '<a href="' + esc(wa) + '" target="_blank" rel="noopener" class="btn" style="flex:1;background:#25D366;color:#053b1e;font-weight:700;text-align:center;text-decoration:none;line-height:1.9">💬 WhatsApp</a>'
        + '<button id="npcPlClose" class="btn btn-ghost">' + (h ? 'बंद करें' : 'Close') + '</button>'
        + '</div></div>';
      document.body.appendChild(ov);
      document.getElementById('npcPlClose').onclick = () => ov.remove();
      document.getElementById('npcPlCopy').onclick = () => { try { navigator.clipboard.writeText(url); } catch (e) { } document.getElementById('npcPlCopy').textContent = h ? '✓ कॉपी हुआ' : '✓ Copied'; };
      CFG.reload();
    } catch (e) { alert(e.message); }
  }

  // ── Documents on a claim the partner raised ────────────────────────────────
  // Partners could raise a claim but never attach paperwork afterwards, and could not see what
  // was already on file - so they re-sent the same documents. This panel lists what is attached
  // (so no duplication), lets them add more later, and lets them remove a wrong one.
  function docApi(claimId, extra, opts) {
    return CFG.api('/' + (CFG.docsBase || 'claims') + '/' + claimId + '/documents' + (extra || ''), opts);
  }

  async function loadDocs(claimId) {
    const box = document.getElementById('npDocPanel_' + claimId);
    if (!box) return;
    const h = hi();
    box.innerHTML = h ? 'लोड हो रहा है…' : 'Loading…';
    let docs = [];
    try {
      const r = await docApi(claimId, '');
      if (!r.ok) throw 0;
      docs = (await r.json()).docs || [];
    } catch (e) {
      box.innerHTML = `<span style="color:var(--nd-danger-text,#b91c1c)">${h ? 'दस्तावेज़ लोड नहीं हुए।' : 'Could not load documents.'}</span>`;
      return;
    }
    const list = docs.length
      ? docs.map(d => `<div style="display:flex;gap:.5rem;align-items:center;padding:.3rem 0;border-bottom:1px dashed var(--nd-border,#e2e8f0)">
            <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">📄 ${esc(d.original_name || d.stored_name || 'document')}</span>
            <span style="font-size:.72rem;color:var(--nd-text-faint)">${fmtDate(d.uploaded_at || d.created_at)}</span>
            ${d.url ? `<a href="${esc(d.url)}" target="_blank" rel="noopener" style="font-size:.74rem;color:var(--nd-cyan-text,#0891b2)">${h ? 'देखें' : 'View'}</a>` : ''}
            <button class="btn-sm btn-ghost" style="font-size:.72rem;padding:.15rem .45rem;color:var(--nd-danger-text,#b91c1c)"
                    onclick="NidaanPartnerClaims.delDoc(${claimId}, ${d.doc_id})" title="${h ? 'हटाएँ' : 'Remove'}">✕</button>
          </div>`).join('')
      : `<div style="color:var(--nd-text-faint);padding:.2rem 0">${h ? 'अभी कोई दस्तावेज़ नहीं जुड़ा।' : 'No documents attached yet.'}</div>`;
    box.innerHTML = `
      <div style="font-weight:700;margin-bottom:.3rem">${h ? 'जुड़े दस्तावेज़' : 'Attached documents'} (${docs.length})</div>
      ${list}
      <div style="display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;margin-top:.6rem">
        <input type="file" id="npDocFile_${claimId}" multiple accept=".pdf,.jpg,.jpeg,.png,.webp"
               style="font-size:.78rem;max-width:230px">
        <button class="btn btn-primary btn-cyan" style="padding:.3rem .7rem;font-size:.76rem"
                onclick="NidaanPartnerClaims.upDoc(${claimId}, this)">${h ? 'अपलोड करें' : 'Upload'}</button>
        <span id="npDocMsg_${claimId}" style="font-size:.76rem;color:var(--nd-text-muted)"></span>
      </div>
      <div style="font-size:.72rem;color:var(--nd-text-faint);margin-top:.35rem">${h ? 'PDF / JPG / PNG · एक बार में 5 तक' : 'PDF / JPG / PNG · up to 5 at a time'}</div>`;
  }

  function toggleDocs(claimId) {
    const row = document.getElementById('npDocRow_' + claimId);
    if (!row) return;
    const show = row.style.display === 'none';
    row.style.display = show ? '' : 'none';
    if (show) loadDocs(claimId);
  }

  async function uploadDocs(claimId, btn) {
    const h = hi();
    const inp = document.getElementById('npDocFile_' + claimId);
    const msg = document.getElementById('npDocMsg_' + claimId);
    if (!inp || !inp.files.length) { if (msg) msg.textContent = h ? 'पहले फ़ाइल चुनें।' : 'Choose a file first.'; return; }
    const fd = new FormData();
    for (const f of inp.files) fd.append('files', f);
    const orig = btn.textContent; btn.disabled = true; btn.textContent = h ? 'भेजा जा रहा…' : 'Uploading…';
    try {
      // Multipart must NOT carry a JSON Content-Type, so pages inject a dedicated uploader.
      const r = CFG.upload ? await CFG.upload('/' + (CFG.docsBase || 'claims') + '/' + claimId + '/documents/upload', fd)
                           : await docApi(claimId, '/upload', { method: 'POST', body: fd });
      if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'Upload failed'); }
      if (msg) { msg.style.color = 'var(--nd-success-text,#047857)'; msg.textContent = h ? 'अपलोड हो गया ✓' : 'Uploaded ✓'; }
      await loadDocs(claimId);
    } catch (e) {
      if (msg) { msg.style.color = 'var(--nd-danger-text,#b91c1c)'; msg.textContent = '✕ ' + (e.message || 'Upload failed'); }
    } finally { btn.disabled = false; btn.textContent = orig; }
  }

  async function deleteDoc(claimId, docId) {
    const h = hi();
    if (!confirm(h ? 'यह दस्तावेज़ हटाएँ? यह वापस नहीं आएगा।' : 'Remove this document? This cannot be undone.')) return;
    try {
      const r = await docApi(claimId, '/' + docId, { method: 'DELETE' });
      if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'Could not remove'); }
      await loadDocs(claimId);
    } catch (e) { alert(e.message || 'Could not remove the document.'); }
  }

  window.NidaanPartnerClaims = {
    init: function (cfg) { CFG = cfg; VIEW = 'active'; },
    render: render,
    setTab: function (v) { VIEW = v; render(); },
    pay: pay, advance: advance, link: link,
    docs: toggleDocs, upDoc: uploadDocs, delDoc: deleteDoc
  };
})();
