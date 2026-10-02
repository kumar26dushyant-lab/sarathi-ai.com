/* ONE CLAIM INTAKE BLOCK, ON EVERY FORM (founder, 2 Oct 2026).
 *
 * The seven core details every door asks, drawn and checked the same way everywhere - the subscriber
 * dashboard, Get started, the Authorized Partner portal, My Business and Raise for a Subscriber.
 * The server (biz_nidaan_intake.py) applies the same rules again and is the one that decides; the
 * checks here only save a person a round trip.
 *
 *   1. Patient / insured  - name required; mobile + email optional
 *   2. Complainant        - name + mobile + email required ("we use them for the whole case")
 *   3. Insurance type     - the one list, served by /nidaan/api/intake/types
 *   4. Insurance company  - NidaanInsurers (nidaan_insurers.js must be loaded first)
 *   5. Disputed amount    - required, shown back IN WORDS (lakh / crore) so a missing zero shows
 *   6. Policy no.         - optional
 *   7. Rejection letter   - uploaded the moment it is picked (virus-checked on the server) and sent
 *                           with the claim as a single-use token. AP and staff doors may instead
 *                           give a reason; the letter is then due in 7 days.
 *
 * Usage:
 *   NidaanIntake.mount('box', {lang:'hi', letterUrl:'/nidaan/branch/api/intake/letter',
 *                              headers:()=>({Authorization:'Bearer '+t}), allowNoLetter:true});
 *   const v = NidaanIntake.collect('box');          // {ok, data} or {ok:false, field, msg}
 *   if (v.ok && await NidaanIntake.confirm('box')) { ...POST Object.assign(scenario, v.data) }
 *   NidaanIntake.serverError('box', json)           // the server's answer, in the form's language
 *   NidaanIntake.reset('box')
 */
(function () {
  'use strict';
  var S = {};                     // per-mount state
  var TYPES = null, typesWait = null;

  function L(st, en, hi) { return st.lang === 'hi' ? hi : en; }
  function esc(x) {
    return String(x == null ? '' : x).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function $(id) { return document.getElementById(id); }

  // ── amount in words, Indian system ─────────────────────────────────────────────────────
  var EN1 = ['', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven',
    'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen'];
  var EN10 = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety'];
  var HI = ('शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस ' +
    'बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस ' +
    'छत्तीस सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस ' +
    'उनचास पचास इक्यावन बावन तिरेपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ इकसठ बासठ तिरेसठ चौंसठ ' +
    'पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर ' +
    'उन्यासी अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी नब्बे इक्यानवे बानवे ' +
    'तिरानवे चौरानवे पचानवे छियानवे सत्तानवे अट्ठानवे निन्यानवे').split(' ');

  function en99(n) { return n < 20 ? EN1[n] : EN10[Math.floor(n / 10)] + (n % 10 ? '-' + EN1[n % 10] : ''); }
  function en999(n) {
    var h = Math.floor(n / 100), r = n % 100, out = [];
    if (h) out.push(EN1[h] + ' hundred');
    if (r) out.push(en99(r));
    return out.join(' ');
  }
  function hi999(n) {
    var h = Math.floor(n / 100), r = n % 100, out = [];
    if (h) out.push(HI[h] + ' सौ');
    if (r) out.push(HI[r]);
    return out.join(' ');
  }
  function words(n, lang) {
    n = Math.floor(Number(n) || 0);
    if (n <= 0) return '';
    var cr = Math.floor(n / 10000000), lk = Math.floor(n / 100000) % 100,
        th = Math.floor(n / 1000) % 100, rest = n % 1000, out = [];
    var hi = lang === 'hi', w = hi ? hi999 : en999;
    if (cr) out.push(w(cr) + (hi ? ' करोड़' : ' crore'));
    if (lk) out.push((hi ? HI[lk] : en99(lk)) + (hi ? ' लाख' : ' lakh'));
    if (th) out.push((hi ? HI[th] : en99(th)) + (hi ? ' हज़ार' : ' thousand'));
    if (rest) out.push(w(rest));
    var s = out.join(' ') + (hi ? ' रुपये' : ' rupees');
    return hi ? s : s.charAt(0).toUpperCase() + s.slice(1);
  }
  function inr(n) {
    var s = String(Math.floor(Number(n) || 0)), last = s.slice(-3), rest = s.slice(0, -3);
    return '₹' + (rest ? rest.replace(/\B(?=(\d{2})+(?!\d))/g, ',') + ',' : '') + last;
  }

  // ── the same rules as the server ───────────────────────────────────────────────────────
  function mobile(v) {
    var d = String(v || '').replace(/\D/g, '');
    if (d.length === 12 && d.indexOf('91') === 0) d = d.slice(2);
    else if (d.length === 11 && d.charAt(0) === '0') d = d.slice(1);
    else if (d.length === 13 && d.indexOf('091') === 0) d = d.slice(3);
    return /^[6-9]\d{9}$/.test(d) ? d : '';
  }
  function email(v) {
    v = String(v || '').trim().toLowerCase();
    return (v.length <= 254 && /^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$/.test(v) && v.indexOf('..') < 0) ? v : '';
  }
  var NAME_OK = /^[\p{L}\p{M} .'\-]+$/u, FIRM_OK = /^[\p{L}\p{M}\d .'\-&\/(),]+$/u, LETTER = /\p{L}/gu;
  // The insured can be a firm (M/S SHARMA TRADERS); the complainant is always a person.
  function nameOk(v, firm) { v = String(v || '').trim(); return v.length <= 120 && (firm ? FIRM_OK : NAME_OK).test(v) && (v.match(LETTER) || []).length >= 2; }
  function amountOf(v) { var n = parseInt(String(v || '').replace(/[^\d]/g, ''), 10); return isFinite(n) ? n : 0; }

  // ── styles (theme variables only, both themes) ─────────────────────────────────────────
  function styles() {
    if ($('ndik-css')) return;
    var c = document.createElement('style');
    c.id = 'ndik-css';
    c.textContent = [
      '.ndik{display:flex;flex-direction:column;gap:.9rem}',
      '.ndik fieldset{border:1px solid var(--nd-border,#cbd5e1);border-radius:12px;padding:.7rem .8rem .8rem;margin:0;min-width:0}',
      '.ndik legend{font-weight:800;font-size:.86rem;color:var(--nd-text-primary,inherit);padding:0 .3rem}',
      '.ndik .g{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:.55rem}',
      '.ndik label{display:flex;flex-direction:column;gap:.25rem;font-size:.78rem;font-weight:600;color:var(--nd-text-secondary,inherit);min-width:0}',
      '.ndik input,.ndik select,.ndik textarea{font-size:16px;min-height:44px;box-sizing:border-box;width:100%;background:var(--nd-bg-surface-2,transparent);color:var(--nd-text-primary,inherit);border:1px solid var(--nd-border-strong,#94a3b8);border-radius:9px;padding:.5rem .65rem;font-family:inherit}',
      '.ndik textarea{min-height:64px;resize:vertical}',
      '.ndik .bad{border-color:var(--nd-danger-text,#dc2626)!important;box-shadow:0 0 0 2px var(--nd-danger-soft,rgba(220,38,38,.15))}',
      '.ndik .req{color:var(--nd-danger-text,#dc2626)}',
      '.ndik .opt{font-weight:400;color:var(--nd-text-faint,#64748b)}',
      '.ndik .hint{font-size:.74rem;color:var(--nd-text-muted,#64748b);font-weight:400}',
      '.ndik .note{font-size:.76rem;color:var(--nd-warning-text,#92400e);background:var(--nd-warning-soft,rgba(245,158,11,.1));border-radius:8px;padding:.45rem .6rem;margin-top:.5rem}',
      '.ndik .same{display:flex;flex-direction:row;align-items:center;gap:.45rem;font-weight:600;min-height:44px;cursor:pointer}',
      '.ndik .same input{width:20px;height:20px;min-height:0}',
      '.ndik .words{font-size:.8rem;font-weight:700;color:var(--nd-text-primary,inherit);min-height:1.1em}',
      '.ndik .letter{border:2px dashed var(--nd-border-strong,#94a3b8);border-radius:10px;padding:.7rem;display:flex;flex-direction:column;gap:.45rem}',
      '.ndik .letter.ok{border-style:solid;border-color:var(--nd-success-text,#16a34a)}',
      '.ndik .btnf{min-height:44px;border-radius:9px;border:1px solid var(--nd-border-strong,#94a3b8);background:var(--nd-bg-surface,transparent);color:var(--nd-text-primary,inherit);font-weight:700;font-size:.88rem;padding:.5rem .9rem;cursor:pointer;align-self:flex-start}',
      '.ndik .bar{height:6px;border-radius:4px;background:var(--nd-border,#e2e8f0);overflow:hidden}',
      '.ndik .bar i{display:block;height:100%;width:0;background:var(--nd-success-text,#16a34a);transition:width .2s}',
      '.ndik .link{background:none;border:none;padding:.3rem 0;color:var(--nd-link,#2563eb);text-decoration:underline;cursor:pointer;font-size:.8rem;align-self:flex-start;min-height:44px}',
      '.ndik-ov{position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:100000;display:flex;align-items:center;justify-content:center;padding:16px}',
      '.ndik-dlg{background:var(--nd-bg-surface,#fff);color:var(--nd-text-primary,#0f172a);border-radius:14px;max-width:520px;width:100%;max-height:90vh;overflow:auto;padding:1rem 1.1rem;box-shadow:0 20px 60px rgba(0,0,0,.35)}',
      '.ndik-dlg h3{margin:.1rem 0 .3rem;font-size:1.05rem}',
      '.ndik-dlg table{width:100%;border-collapse:collapse;font-size:.88rem;margin:.6rem 0}',
      '.ndik-dlg td{padding:.4rem .3rem;border-bottom:1px solid var(--nd-border,#e2e8f0);vertical-align:top}',
      '.ndik-dlg td:first-child{color:var(--nd-text-muted,#64748b);width:40%}',
      '.ndik-dlg .amt{font-size:1.1rem;font-weight:800}',
      '.ndik-dlg .row{display:flex;gap:.5rem;flex-wrap:wrap;justify-content:flex-end;margin-top:.6rem}',
      '.ndik-dlg button{min-height:44px;border-radius:9px;padding:.5rem 1rem;font-weight:700;font-size:.9rem;cursor:pointer;border:1px solid var(--nd-border-strong,#94a3b8);background:var(--nd-bg-surface-2,#f1f5f9);color:var(--nd-text-primary,#0f172a)}',
      '.ndik-dlg button.go{background:var(--nd-success-text,#16a34a);border-color:transparent;color:#fff}'
    ].join('\n');
    document.head.appendChild(c);
  }

  function loadTypes() {
    if (TYPES) return Promise.resolve(TYPES);
    if (typesWait) return typesWait;
    typesWait = fetch('/nidaan/api/intake/types').then(function (r) { return r.json(); })
      .then(function (d) { TYPES = (d && d.types) || []; return TYPES; })
      .catch(function () { typesWait = null; return []; });
    return typesWait;
  }

  // ── drawing ────────────────────────────────────────────────────────────────────────────
  function field(id, labelHtml, inputHtml, hint) {
    return '<label for="' + id + '">' + labelHtml + inputHtml + (hint ? '<span class="hint">' + hint + '</span>' : '') + '</label>';
  }
  function draw(box) {
    var st = S[box], p = box + '_', v = st.values || {};
    var R = ' <span class="req" aria-hidden="true">*</span>';
    var O = ' <span class="opt">(' + L(st, 'optional', 'वैकल्पिक') + ')</span>';
    var inp = function (k, type, extra) {
      return '<input id="' + p + k + '" name="' + k + '" type="' + type + '" value="' + esc(v[k] || '') + '"' + (extra || '') + '>';
    };
    var typeOpts = '<option value="">' + L(st, 'Choose…', 'चुनें…') + '</option>' + (TYPES || []).map(function (t) {
      return '<option value="' + esc(t.code) + '"' + (v.claim_type === t.code ? ' selected' : '') + '>' + esc(st.lang === 'hi' ? t.hi : t.en) + '</option>';
    }).join('');
    var letter = st.letter;
    var html =
      '<div class="ndik">' +
      '<fieldset><legend>' + L(st, 'Patient / insured person', 'मरीज़ / बीमित व्यक्ति') + '</legend><div class="g">' +
        field(p + 'insured_name', L(st, 'Full name', 'पूरा नाम') + R, inp('insured_name', 'text', ' autocomplete="off" style="text-transform:uppercase"')) +
        field(p + 'insured_phone', L(st, 'Mobile', 'मोबाइल') + O, inp('insured_phone', 'tel', ' inputmode="numeric" autocomplete="off" maxlength="16"')) +
        field(p + 'insured_email', L(st, 'Email', 'ईमेल') + O, inp('insured_email', 'email', ' autocomplete="off" inputmode="email"')) +
      '</div></fieldset>' +
      '<fieldset><legend>' + L(st, 'Complainant - the person we talk to', 'शिकायतकर्ता - जिनसे हम बात करेंगे') + '</legend>' +
        '<label class="same"><input type="checkbox" id="' + p + 'same"' + (st.same ? ' checked' : '') + '> ' +
          L(st, 'Same person as the patient', 'मरीज़ ही शिकायतकर्ता हैं') + '</label>' +
        '<div class="g">' +
        field(p + 'complainant_name', L(st, 'Full name', 'पूरा नाम') + R, inp('complainant_name', 'text', ' autocomplete="off" style="text-transform:uppercase"' + (st.same ? ' readonly' : ''))) +
        field(p + 'complainant_phone', L(st, 'Mobile (WhatsApp)', 'मोबाइल (व्हाट्सऐप)') + R, inp('complainant_phone', 'tel', ' inputmode="numeric" autocomplete="off" maxlength="16"')) +
        field(p + 'complainant_email', L(st, 'Email', 'ईमेल') + R, inp('complainant_email', 'email', ' autocomplete="off" inputmode="email"')) +
        '</div>' +
        '<div class="note">' + L(st, 'Please check the mobile and email twice - we use this WhatsApp and email for the whole case.',
          'मोबाइल और ईमेल दो बार जाँच लें - पूरे केस में इसी व्हाट्सऐप और ईमेल पर बात होगी।') + '</div>' +
      '</fieldset>' +
      '<fieldset><legend>' + L(st, 'The claim', 'क्लेम') + '</legend><div class="g">' +
        field(p + 'claim_type', L(st, 'Insurance type', 'बीमा का प्रकार') + R, '<select id="' + p + 'claim_type" name="claim_type">' + typeOpts + '</select>') +
        '<label>' + L(st, 'Insurance company', 'बीमा कंपनी') + R + '<span id="' + p + 'ins" style="display:block;min-width:0"></span></label>' +
        field(p + 'disputed_amount', L(st, 'Disputed amount (₹)', 'विवादित राशि (₹)') + R,
              inp('disputed_amount', 'text', ' inputmode="numeric" autocomplete="off" placeholder="' + L(st, 'e.g. 150000', 'जैसे 150000') + '"'),
              '<span class="words" id="' + p + 'words"></span>') +
        field(p + 'policy_no', L(st, 'Policy no.', 'पॉलिसी नं.') + O, inp('policy_no', 'text', ' autocomplete="off" maxlength="80"')) +
      '</div></fieldset>' +
      '<fieldset><legend>' + L(st, "Insurer's rejection letter", 'बीमा कंपनी का रिजेक्शन लेटर') + R + '</legend>' +
        '<div class="letter' + (letter.token ? ' ok' : '') + '" id="' + p + 'letter">' +
          (letter.token
            ? '<div>✅ ' + esc(letter.name) + ' <span class="hint">' + L(st, 'uploaded and checked', 'अपलोड और जाँच हो गई') + '</span></div>' +
              '<button type="button" class="btnf" data-act="pick">' + L(st, 'Change the letter', 'लेटर बदलें') + '</button>'
            : (st.noLetter
              ? '<label for="' + p + 'reason">' + L(st, 'Why is the letter not attached?', 'लेटर क्यों नहीं लगा है?') + R +
                '<textarea id="' + p + 'reason" maxlength="300">' + esc(st.reason || '') + '</textarea></label>' +
                '<div class="note">' + L(st, 'Send the letter within 7 days. If it does not come, the claim is archived (not deleted). You will be reminded every day.',
                  '7 दिन के अंदर लेटर भेजें। न आने पर क्लेम आर्काइव हो जाएगा (डिलीट नहीं)। रोज़ याद दिलाया जाएगा।') + '</div>' +
                '<button type="button" class="link" data-act="haveit">' + L(st, 'I have the letter - attach it', 'लेटर है - लगाएँ') + '</button>'
              : '<button type="button" class="btnf" data-act="pick">📄 ' + L(st, 'Attach the letter (photo or PDF)', 'लेटर लगाएँ (फ़ोटो या PDF)') + '</button>' +
                '<div class="hint">' + L(st, 'A claim cannot be raised without it. Up to 25 MB.', 'इसके बिना क्लेम दर्ज नहीं होता। 25 MB तक।') + '</div>' +
                (letter.busy ? '<div class="bar"><i id="' + p + 'bar"></i></div><div class="hint">' + L(st, 'Uploading and checking…', 'अपलोड और जाँच हो रही है…') + '</div>' : '') +
                (letter.err ? '<div class="hint" style="color:var(--nd-danger-text,#dc2626)">' + esc(letter.err) + '</div>' : '') +
                (st.allowNoLetter ? '<button type="button" class="link" data-act="noletter">' + L(st, "I don't have the letter yet", 'अभी लेटर नहीं है') + '</button>' : ''))) +
          '<input type="file" id="' + p + 'file" accept="application/pdf,image/*,.docx" style="display:none">' +
        '</div>' +
      '</fieldset>' +
      '</div>';
    st.el.innerHTML = html;
    try { window.NidaanInsurers.mount(p + 'ins', { value: v.insurer_name || '', style: 'width:100%' }); } catch (e) { /* insurer list not loaded on this page */ }
    showWords(box);
  }

  function read(box) {
    var st = S[box], p = box + '_', out = {};
    ['insured_name', 'insured_phone', 'insured_email', 'complainant_name', 'complainant_phone',
     'complainant_email', 'claim_type', 'disputed_amount', 'policy_no'].forEach(function (k) {
      var e = $(p + k); out[k] = e ? String(e.value || '').trim() : '';
    });
    try { out.insurer_name = window.NidaanInsurers.value(p + 'ins'); } catch (e) { out.insurer_name = ''; }
    var r = $(p + 'reason'); if (r) st.reason = r.value;
    return out;
  }

  function showWords(box) {
    var st = S[box], e = $(box + '_disputed_amount'), w = $(box + '_words');
    if (!e || !w) return;
    var n = amountOf(e.value);
    w.textContent = n ? inr(n) + ' = ' + words(n, st.lang) : '';
  }

  function syncSame(box) {
    var st = S[box], p = box + '_';
    if (!st.same) return;
    var a = $(p + 'insured_name'), b = $(p + 'complainant_name');
    if (a && b) b.value = a.value;
  }

  function wire(box) {
    var st = S[box], p = box + '_';
    st.el.addEventListener('input', function (ev) {
      var id = ev.target && ev.target.id;
      if (id === p + 'disputed_amount') showWords(box);
      if (id === p + 'insured_name') syncSame(box);
      if (ev.target.classList) ev.target.classList.remove('bad');
    });
    st.el.addEventListener('change', function (ev) {
      var t = ev.target;
      if (t.id === p + 'same') {
        st.values = read(box); st.same = t.checked;
        if (st.same) st.values.complainant_name = st.values.insured_name;
        draw(box); return;
      }
      if (t.id === p + 'file') { var f = t.files && t.files[0]; t.value = ''; if (f) upload(box, f); }
      if ((t.type === 'tel') && t.value) { var m = mobile(t.value); if (m) t.value = m; }
    });
    st.el.addEventListener('click', function (ev) {
      var b = ev.target.closest ? ev.target.closest('[data-act]') : null;
      if (!b) return;
      var act = b.getAttribute('data-act');
      st.values = read(box);
      if (act === 'pick') { var f = $(p + 'file'); if (f) f.click(); return; }
      if (act === 'noletter') { st.noLetter = true; draw(box); return; }
      if (act === 'haveit') { st.noLetter = false; draw(box); var f2 = $(p + 'file'); if (f2) f2.click(); }
    });
  }

  function upload(box, file) {
    var st = S[box];
    st.values = read(box);
    if (file.size > 25 * 1024 * 1024) {
      st.letter = { err: L(st, file.name + ' is over 25 MB.', file.name + ' 25 MB से बड़ी है।') };
      draw(box); return;
    }
    st.letter = { busy: true }; draw(box);
    var fd = new FormData(); fd.append('file', file);
    var x = new XMLHttpRequest();
    x.open('POST', st.letterUrl);
    var h = (st.headers && st.headers()) || {};
    Object.keys(h).forEach(function (k) { x.setRequestHeader(k, h[k]); });
    x.upload.onprogress = function (e) {
      var b = $(box + '_bar'); if (b && e.lengthComputable) b.style.width = Math.round(e.loaded * 100 / e.total) + '%';
    };
    x.onload = function () {
      var d = {}; try { d = JSON.parse(x.responseText || '{}'); } catch (e) { /* not JSON */ }
      if (x.status === 200 && d.token) st.letter = { token: d.token, name: d.name || file.name };
      else st.letter = { err: (st.lang === 'hi' && d.detail_hi) || (typeof d.detail === 'string' ? d.detail : L(st, 'Could not upload the letter - please try again.', 'लेटर अपलोड नहीं हुआ - फिर कोशिश करें।')) };
      st.values = read(box); draw(box);
    };
    x.onerror = function () {
      st.letter = { err: L(st, 'Network problem - please try again.', 'नेटवर्क की दिक्कत - फिर कोशिश करें।') };
      draw(box);
    };
    x.send(fd);
  }

  // ── public ─────────────────────────────────────────────────────────────────────────────
  function mount(box, opts) {
    var el = $(box); if (!el) return;
    opts = opts || {};
    styles();
    var prev = S[box];
    S[box] = {
      el: el, lang: opts.lang === 'hi' ? 'hi' : 'en', letterUrl: opts.letterUrl, headers: opts.headers,
      allowNoLetter: !!opts.allowNoLetter, values: prev ? read(box) : {}, same: prev ? prev.same : false,
      letter: prev ? prev.letter : {}, noLetter: prev ? prev.noLetter : false, reason: prev ? prev.reason : ''
    };
    if (!prev || prev.el !== el) wire(box);
    draw(box);
    loadTypes().then(function () { if (S[box]) { S[box].values = read(box); draw(box); } });
  }

  function mark(box, field) {
    var e = $(box + '_' + field) || (field === 'insurer_name' ? $(box + '_ins_pick') : null)
      || (field === 'rejection_letter' || field === 'no_letter_reason' ? $(box + '_letter') : null);
    if (e) { if (e.classList) e.classList.add('bad'); try { e.focus({ preventScroll: true }); } catch (x) { /* old browser */ } e.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
  }

  function collect(box) {
    var st = S[box]; if (!st) return { ok: false, msg: 'form missing' };
    var v = read(box), bad = function (f, en, hi) { mark(box, f); return { ok: false, field: f, msg: L(st, en, hi) }; };
    if (!nameOk(v.insured_name, true)) return bad('insured_name', "Enter the patient's / insured's full name.", 'मरीज़ / बीमित का पूरा नाम लिखें।');
    if (v.insured_phone && !mobile(v.insured_phone)) return bad('insured_phone', "The patient's mobile is not a valid 10-digit number - or leave it blank.", 'मरीज़ का मोबाइल सही नहीं - या खाली छोड़ें।');
    if (v.insured_email && !email(v.insured_email)) return bad('insured_email', "The patient's email does not look right - or leave it blank.", 'मरीज़ का ईमेल सही नहीं - या खाली छोड़ें।');
    if (!nameOk(v.complainant_name)) return bad('complainant_name', "Enter the complainant's full name (letters only).", 'शिकायतकर्ता का पूरा नाम लिखें (सिर्फ़ अक्षर)।');
    if (!mobile(v.complainant_phone)) return bad('complainant_phone', "Enter the complainant's 10-digit mobile.", 'शिकायतकर्ता का 10 अंकों का मोबाइल लिखें।');
    if (!email(v.complainant_email)) return bad('complainant_email', "Enter the complainant's email.", 'शिकायतकर्ता का ईमेल लिखें।');
    if (!v.claim_type) return bad('claim_type', 'Choose the insurance type.', 'बीमा का प्रकार चुनें।');
    if ((v.insurer_name || '').length < 2) return bad('insurer_name', 'Choose the insurance company.', 'बीमा कंपनी चुनें।');
    var amt = amountOf(v.disputed_amount);
    if (amt < 1) return bad('disputed_amount', 'Enter the disputed amount.', 'विवादित राशि लिखें।');
    if (amt > 1000000000) return bad('disputed_amount', 'That is above ₹100 crore - please check the zeros.', 'यह 100 करोड़ से ज़्यादा है - शून्य जाँचें।');
    if (v.policy_no && !/^[A-Za-z0-9\/\-._# ]{1,80}$/.test(v.policy_no)) return bad('policy_no', 'The policy number has characters it should not.', 'पॉलिसी नंबर में गलत चिह्न हैं।');
    var data = {
      insured_name: v.insured_name, insured_phone: v.insured_phone ? mobile(v.insured_phone) : '',
      insured_email: v.insured_email ? email(v.insured_email) : '',
      complainant_name: v.complainant_name, complainant_phone: mobile(v.complainant_phone),
      complainant_email: email(v.complainant_email), claim_type: v.claim_type,
      insurer_name: v.insurer_name, disputed_amount: amt, policy_no: v.policy_no
    };
    if (st.letter && st.letter.token) data.letter_token = st.letter.token;
    else if (st.noLetter && st.allowNoLetter) {
      var why = String(st.reason || '').trim();
      if (why.length < 10) return bad('no_letter_reason', 'Say in a few words why the letter is not attached.', 'कुछ शब्दों में बताएँ कि लेटर क्यों नहीं है।');
      data.no_letter_reason = why;
    } else if (st.letter && st.letter.busy) {
      return bad('rejection_letter', 'The letter is still uploading - wait a moment.', 'लेटर अभी अपलोड हो रहा है - ज़रा रुकें।');
    } else {
      return bad('rejection_letter', "Attach the insurer's rejection letter.", 'बीमा कंपनी का रिजेक्शन लेटर लगाएँ।');
    }
    return { ok: true, data: data };
  }

  // The double-check: people mistype mobiles and drop zeros. Show it back, in words, before it goes.
  function confirm(box) {
    var st = S[box], v = collect(box);
    if (!v.ok) return Promise.resolve(false);
    var d = v.data, t = (TYPES || []).filter(function (x) { return x.code === d.claim_type; })[0];
    var ph = function (m) { return m ? '+91 ' + m.slice(0, 5) + ' ' + m.slice(5) : '-'; };
    var row = function (k, val) { return '<tr><td>' + k + '</td><td>' + val + '</td></tr>'; };
    return new Promise(function (resolve) {
      var ov = document.createElement('div');
      ov.className = 'ndik-ov';
      ov.innerHTML = '<div class="ndik-dlg" role="dialog" aria-modal="true" aria-labelledby="ndikh">' +
        '<h3 id="ndikh">' + L(st, 'Please check before submitting', 'जमा करने से पहले जाँच लें') + '</h3>' +
        '<div class="hint" style="font-size:.82rem">' + L(st, 'People often type a mobile or an amount wrong at first. Is everything right?',
          'अक्सर पहली बार मोबाइल या राशि गलत लिख जाती है। क्या सब सही है?') + '</div>' +
        '<table>' +
        row(L(st, 'Patient', 'मरीज़'), esc(d.insured_name.toUpperCase())) +
        row(L(st, 'Complainant', 'शिकायतकर्ता'), esc(d.complainant_name.toUpperCase())) +
        row(L(st, 'WhatsApp mobile', 'व्हाट्सऐप मोबाइल'), '<b>' + esc(ph(d.complainant_phone)) + '</b>') +
        row(L(st, 'Email', 'ईमेल'), '<b>' + esc(d.complainant_email) + '</b>') +
        row(L(st, 'Insurance', 'बीमा'), esc(t ? (st.lang === 'hi' ? t.hi : t.en) : d.claim_type) + ' · ' + esc(d.insurer_name)) +
        row(L(st, 'Disputed amount', 'विवादित राशि'), '<div class="amt">' + inr(d.disputed_amount) + '</div><div>' + esc(words(d.disputed_amount, st.lang)) + '</div>') +
        (d.policy_no ? row(L(st, 'Policy no.', 'पॉलिसी नं.'), esc(d.policy_no)) : '') +
        row(L(st, 'Rejection letter', 'रिजेक्शन लेटर'), d.letter_token ? '✅ ' + esc(st.letter.name || '') : '⚠️ ' + L(st, 'Not attached - due in 7 days', 'नहीं लगा - 7 दिन में चाहिए')) +
        '</table>' +
        '<div class="row"><button type="button" data-a="no">' + L(st, 'Go back and fix', 'वापस जाकर ठीक करें') + '</button>' +
        '<button type="button" class="go" data-a="yes">' + L(st, 'Yes, all correct - submit', 'हाँ, सब सही है - जमा करें') + '</button></div>' +
        '</div>';
      var done = function (ok) { document.removeEventListener('keydown', key); ov.remove(); resolve(ok); };
      var key = function (e) { if (e.key === 'Escape') done(false); };
      ov.addEventListener('click', function (e) {
        var a = e.target.getAttribute && e.target.getAttribute('data-a');
        if (a === 'yes') done(true); else if (a === 'no' || e.target === ov) done(false);
      });
      document.addEventListener('keydown', key);
      document.body.appendChild(ov);
      var go = ov.querySelector('button.go'); if (go) go.focus();
    });
  }

  function serverError(box, d) {
    var st = S[box] || { lang: 'en' };
    d = d || {};
    if (d.field) {
      mark(box, d.field);
      if (d.field === 'rejection_letter' && S[box]) { S[box].letter = {}; S[box].values = read(box); draw(box); mark(box, d.field); }
    }
    if (st.lang === 'hi' && d.detail_hi) return d.detail_hi;
    if (typeof d.detail === 'string') return d.detail;
    if (Array.isArray(d.detail) && d.detail[0] && d.detail[0].msg) return d.detail[0].msg;
    return L(st, 'Could not submit - please check the details.', 'जमा नहीं हुआ - कृपया विवरण जाँचें।');
  }

  // Pre-fill details we already know (e.g. the signed-in person as the complainant). Never
  // overwrites what somebody has typed.
  function fill(box, vals) {
    var st = S[box]; if (!st) return;
    st.values = read(box);
    Object.keys(vals || {}).forEach(function (k) { if (!st.values[k] && vals[k]) st.values[k] = vals[k]; });
    draw(box);
  }

  function reset(box) {
    var st = S[box]; if (!st) return;
    st.values = {}; st.same = false; st.letter = {}; st.noLetter = false; st.reason = '';
    draw(box);
  }

  window.NidaanIntake = { mount: mount, collect: collect, confirm: confirm, serverError: serverError,
                          reset: reset, fill: fill, words: words, inr: inr, mobile: mobile };
})();
