/* NidaanPartner — lightweight analytics tracker (public pages).
 * Captures acquisition attribution (ref code + UTM) first-touch, keeps an anonymous
 * session id, and fires funnel/abandonment beacons to /nidaan/api/track.
 * Depth = "failures + abandonment": we DO NOT log page views; we log flow starts and
 * abandonment (started signup/review/pay but left) + the server logs payment failures.
 * Fire-and-forget; never blocks or errors the page. */
(function () {
  var AKEY = 'nidaan_attr', SKEY = 'nidaan_sid', TTL = 90 * 864e5; // 90 days first-touch

  function rid() { return Date.now().toString(36) + Math.random().toString(36).slice(2, 10); }

  function sid() {
    try { var s = localStorage.getItem(SKEY); if (!s) { s = rid(); localStorage.setItem(SKEY, s); } return s; }
    catch (e) { return ''; }
  }

  function capture() {
    try {
      var p = new URLSearchParams(location.search);
      var ref = (p.get('ref') || p.get('branch') || '').trim().toUpperCase();
      var us = (p.get('utm_source') || '').trim();
      var um = (p.get('utm_medium') || '').trim();
      var uc = (p.get('utm_campaign') || '').trim();
      var cur = {}; try { cur = JSON.parse(localStorage.getItem(AKEY) || '{}'); } catch (e) {}
      // Expire stale first-touch, then start fresh from this visit.
      if (cur.t && (Date.now() - cur.t) > TTL) cur = {};
      var next = {
        ref: cur.ref || ref || '',
        utm_source: cur.utm_source || us || '',
        utm_medium: cur.utm_medium || um || '',
        utm_campaign: cur.utm_campaign || uc || '',
        t: cur.t || Date.now()
      };
      localStorage.setItem(AKEY, JSON.stringify(next));
    } catch (e) {}
  }

  function attr() {
    var a = {}; try { a = JSON.parse(localStorage.getItem(AKEY) || '{}'); } catch (e) {}
    return {
      ref: a.ref || '', utm_source: a.utm_source || '', utm_medium: a.utm_medium || '',
      utm_campaign: a.utm_campaign || '', session_id: sid()
    };
  }

  function event(type, extra) {
    try {
      var a = attr();
      var body = {
        event_type: type, session_id: a.session_id, ref: a.ref,
        utm_source: a.utm_source, utm_medium: a.utm_medium, utm_campaign: a.utm_campaign
      };
      if (extra) for (var k in extra) if (extra[k] != null) body[k] = extra[k];
      var json = JSON.stringify(body);
      if (navigator.sendBeacon) {
        navigator.sendBeacon('/nidaan/api/track', new Blob([json], { type: 'application/json' }));
      } else {
        fetch('/nidaan/api/track', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: json, keepalive: true
        }).catch(function () {});
      }
    } catch (e) {}
  }

  // One active flow at a time (signup | review | pay). If the user leaves before
  // completeFlow(), we emit an 'abandoned' event with the flow's purpose.
  var _flow = null;
  var _startMap = { signup: 'signup_started', review: 'review_started', pay: 'pay_opened' };
  function startFlow(name, purpose) {
    _flow = { name: name, purpose: purpose || name, done: false };
    if (_startMap[name]) event(_startMap[name], purpose ? { purpose: purpose } : {});
  }
  function completeFlow() { if (_flow) _flow.done = true; }
  function abandon() {
    if (_flow && !_flow.done) { _flow.done = true; event('abandoned', { purpose: _flow.purpose }); }
  }
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') abandon();
  });
  window.addEventListener('pagehide', abandon);

  capture();
  window.NidaanTrack = {
    capture: capture, attr: attr, event: event,
    startFlow: startFlow, completeFlow: completeFlow, abandon: abandon
  };
})();
