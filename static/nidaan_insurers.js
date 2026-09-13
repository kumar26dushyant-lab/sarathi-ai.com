/* NidaanPartner — the insurance companies we see on claims.
 *
 * ONE list, used by every form that asks the question. It lived as duplicated <option> markup on
 * two pages while four other forms asked for the company as free text — which is how a claim ends
 * up with the complainant's own name typed into the insurer field, and why the same company
 * arrives spelled four different ways and cannot be counted.
 *
 * Always ends with "Other", because the list will never be complete and a form that cannot accept
 * a real answer just teaches people to put the real answer somewhere else.
 */
(function () {
  var LIST = [
    // Life
    'LIC of India', 'HDFC Life', 'ICICI Prudential Life', 'SBI Life', 'Max Life',
    'Bajaj Allianz Life', 'Kotak Life', 'Tata AIA Life', 'PNB MetLife',
    'Aditya Birla Sun Life',
    // Health
    'Star Health', 'HDFC ERGO', 'Care Health', 'Niva Bupa (Max Bupa)', 'ManipalCigna',
    'Aditya Birla Health', 'Reliance Health',
    // General / motor / other
    'ICICI Lombard', 'Bajaj Allianz General', 'New India Assurance', 'Tata AIG',
    'Reliance General', 'Cholamandalam MS', 'SBI General', 'National Insurance',
    'Oriental Insurance', 'United India Insurance', 'IFFCO-Tokio', 'Digit Insurance',
    'Acko', 'Future Generali', 'Liberty General', 'Shriram General', 'Royal Sundaram',
    'Universal Sompo', 'Magma HDI', 'Navi General', 'Zuno (Edelweiss)'
  ];

  var OTHER = '__other';

  function options(selected) {
    var cur = (selected || '').trim();
    var inList = false;
    var html = '<option value="">— Select the insurance company —</option>';
    for (var i = 0; i < LIST.length; i++) {
      var sel = (cur && cur.toLowerCase() === LIST[i].toLowerCase());
      if (sel) inList = true;
      html += '<option' + (sel ? ' selected' : '') + '>' + LIST[i] + '</option>';
    }
    // An existing claim may already carry a company that is not on the list. Keep it selectable
    // rather than silently blanking someone's data when they open the form to edit something else.
    html += '<option value="' + OTHER + '"' + (cur && !inList ? ' selected' : '') +
            '>Other — type the name</option>';
    return html;
  }

  /* Renders the select + the "other" box into `mountId`.
     The chosen value is always readable from NidaanInsurers.value(id). */
  function mount(mountId, opts) {
    var el = document.getElementById(mountId);
    if (!el) return;
    opts = opts || {};
    var cur = (opts.value || '').trim();
    var style = opts.style || '';
    el.innerHTML =
        '<select id="' + mountId + '_pick" style="' + style + '" ' +
          'onchange="NidaanInsurers.sync(\'' + mountId + '\')">' + options(cur) + '</select>' +
        '<input type="text" id="' + mountId + '_other" autocomplete="off" ' +
          'placeholder="Type the insurance company name" style="' + style +
          ';margin-top:.4rem;display:none" ' +
          'oninput="NidaanInsurers.sync(\'' + mountId + '\', true)">';
    var other = document.getElementById(mountId + '_other');
    var pick = document.getElementById(mountId + '_pick');
    if (cur && pick && pick.value === OTHER) { other.value = cur; other.style.display = ''; }
    sync(mountId);
  }

  function sync(mountId, fromText) {
    var pick = document.getElementById(mountId + '_pick');
    var other = document.getElementById(mountId + '_other');
    if (!pick || !other) return;
    if (pick.value === OTHER) {
      if (other.style.display === 'none') { other.style.display = ''; if (!fromText) other.focus(); }
    } else {
      other.style.display = 'none';
    }
  }

  function value(mountId) {
    var pick = document.getElementById(mountId + '_pick');
    var other = document.getElementById(mountId + '_other');
    if (!pick) return '';
    if (pick.value === OTHER) return (other ? other.value : '').trim();
    return (pick.value || '').trim();
  }

  /* For the two pages that already have their own <select> markup: replace the hardcoded options
     with this list, keeping their element ids and handlers exactly as they are. */
  function fill(selectId, selected) {
    var s = document.getElementById(selectId);
    if (!s) return;
    var cur = (selected || s.value || '').trim();
    s.innerHTML = options(cur);
  }

  window.NidaanInsurers = {
    list: LIST, OTHER: OTHER, options: options,
    mount: mount, sync: sync, value: value, fill: fill
  };
})();
