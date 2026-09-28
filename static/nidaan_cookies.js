/* Cookie consent for NidaanPartner.com — advisor pages and the policyholder portal.
 *
 * WHY THIS IS REAL AND NOT A NOTICE. Until today Google Analytics loaded on five public pages
 * the moment they opened, setting _ga cookies before anybody was asked. A banner that appears
 * while the tracking has already started is theatre, so this one GATES: nidaan_ga.js does not
 * load until analytics is accepted, and if it is later refused the _ga cookies are deleted.
 *
 * THE RULES IT FOLLOWS
 *   - Refusing is exactly as easy as accepting. "Only essential" sits next to "Accept all",
 *     same size, same prominence. A refusal buried two screens down is not a choice.
 *   - Nothing optional is on until it is switched on. No pre-ticked boxes.
 *   - Closing or ignoring the banner consents to NOTHING. There is no dismiss-means-yes.
 *   - It can be changed later, from a link in the footer of every page, including to withdraw.
 *   - It says plainly what each group does, in words a Tier II/III reader can follow, in
 *     English and Hindi.
 *
 * TWO AUDIENCES, TWO LANGUAGE KEYS. The advisor pages keep the chosen language in
 * localStorage.nidaan_lang; the policyholder portal keeps it in claim_lang and defaults to
 * Hindi. This reads whichever is there rather than imposing a third, and re-renders when the
 * page's own language toggle fires.
 *
 * WHERE THE ANSWER IS KEPT. A first-party cookie (so it survives and could be read server-side
 * if we ever need to prove what was agreed) AND localStorage, because either can be blocked.
 * Both are wrapped: a browser with storage disabled must still show a working page, and it will
 * simply ask again next time, which is the safe direction.
 */
(function () {
  "use strict";

  // Raising this re-asks everybody. Raise it when the GROUPS or their purpose change - not for
  // wording. Re-asking without a reason trains people to click the first button they see.
  var VERSION = 1;
  var COOKIE = "nidaan_consent";
  var STORE = "nidaan_consent_v" + VERSION;
  var POLICY_URL = "/nidaan/cookies";

  // ── what the answer is kept in ────────────────────────────────────────────
  function readCookie(name) {
    try {
      var m = ("; " + document.cookie).split("; " + name + "=");
      return m.length === 2 ? decodeURIComponent(m.pop().split(";").shift()) : "";
    } catch (e) { return ""; }
  }
  function writeCookie(name, value, days) {
    try {
      var d = new Date();
      d.setTime(d.getTime() + days * 864e5);
      document.cookie = name + "=" + encodeURIComponent(value) + ";expires=" + d.toUTCString() +
        ";path=/;SameSite=Lax" + (location.protocol === "https:" ? ";Secure" : "");
    } catch (e) { /* storage blocked - we will ask again, which is the safe direction */ }
  }

  function load() {
    var raw = "";
    try { raw = localStorage.getItem(STORE) || ""; } catch (e) {}
    if (!raw) raw = readCookie(COOKIE);
    if (!raw) return null;
    try {
      var v = JSON.parse(raw);
      if (!v || v.v !== VERSION) return null;      // an older answer is not an answer to this
      return v;
    } catch (e) { return null; }
  }

  function save(consent) {
    var v = { v: VERSION, analytics: !!consent.analytics, at: new Date().toISOString() };
    var raw = JSON.stringify(v);
    try { localStorage.setItem(STORE, raw); } catch (e) {}
    writeCookie(COOKIE, raw, 180);
    return v;
  }

  // ── the words ─────────────────────────────────────────────────────────────
  var T = {
    en: {
      title: "Cookies on this site",
      body: "We use cookies to keep you signed in and to keep your account safe. " +
            "With your permission, we would also like to count visits so we can see which " +
            "pages help people and which do not.",
      acceptAll: "Accept all",
      essentialOnly: "Only essential",
      choose: "Choose what to allow",
      save: "Save my choice",
      policy: "Read our cookie policy",
      close: "Close",
      essentialName: "Essential — always on",
      essentialWhy: "Signing in, keeping your session safe, and remembering which partner " +
                    "referred you so they are credited. The site cannot work without these, " +
                    "so they cannot be switched off.",
      analyticsName: "Help us improve the site",
      analyticsWhy: "Counts visits and which pages are used, through Google Analytics. " +
                    "It never sees your documents or your claim. Switching this off changes " +
                    "nothing about how the site works for you.",
      on: "On", off: "Off",
      changedLater: "You can change this at any time from “Cookie settings” at the bottom of " +
                    "any page.",
      savedMsg: "Saved. Thank you."
    },
    hi: {
      title: "इस साइट पर कुकीज़",
      body: "हम कुकीज़ का उपयोग आपको लॉग-इन रखने और आपके खाते को सुरक्षित रखने के लिए करते हैं। " +
            "आपकी अनुमति से हम यह भी गिनना चाहेंगे कि कौन से पेज लोगों के काम आते हैं और कौन से नहीं।",
      acceptAll: "सभी स्वीकार करें",
      essentialOnly: "केवल ज़रूरी",
      choose: "चुनिए क्या-क्या अनुमति है",
      save: "मेरी पसंद सेव करें",
      policy: "हमारी कुकी नीति पढ़िए",
      close: "बंद करें",
      essentialName: "ज़रूरी — हमेशा चालू",
      essentialWhy: "लॉग-इन करना, आपका सेशन सुरक्षित रखना, और यह याद रखना कि किस पार्टनर ने आपको " +
                    "भेजा है ताकि उन्हें श्रेय मिले। इनके बिना साइट काम नहीं कर सकती, इसलिए ये बंद " +
                    "नहीं हो सकतीं।",
      analyticsName: "साइट बेहतर बनाने में मदद कीजिए",
      analyticsWhy: "Google Analytics के ज़रिए यह गिनता है कि कितने लोग आए और कौन से पेज देखे। " +
                    "यह आपके दस्तावेज़ या आपका क्लेम कभी नहीं देखता। इसे बंद करने से आपके लिए साइट " +
                    "के काम करने में कोई फ़र्क़ नहीं पड़ता।",
      on: "चालू", off: "बंद",
      changedLater: "आप इसे कभी भी किसी भी पेज के नीचे “कुकी सेटिंग्स” से बदल सकते हैं।",
      savedMsg: "सेव हो गया। धन्यवाद।"
    }
  };

  function lang() {
    var l = "";
    try { l = localStorage.getItem("nidaan_lang") || localStorage.getItem("claim_lang") || ""; }
    catch (e) {}
    if (!l) l = (document.documentElement.lang || "").toLowerCase();
    return (l.indexOf("hi") === 0) ? "hi" : "en";
  }
  function t(k) { return (T[lang()] || T.en)[k] || T.en[k] || k; }

  // ── telling the rest of the page ──────────────────────────────────────────
  function announce(consent) {
    try {
      window.dispatchEvent(new CustomEvent("nidaan-consent", { detail: consent }));
    } catch (e) {
      // Older browsers: fall back to the constructor form rather than failing silently, or a
      // gated script would never learn that permission had been given.
      try {
        var ev = document.createEvent("CustomEvent");
        ev.initCustomEvent("nidaan-consent", false, false, consent);
        window.dispatchEvent(ev);
      } catch (e2) {}
    }
  }

  // Refusing after accepting must actually REMOVE what was set, or "off" is only a label.
  function dropAnalyticsCookies() {
    try {
      var host = location.hostname.replace(/^www\./, "");
      (document.cookie || "").split(";").forEach(function (c) {
        var name = c.split("=")[0].trim();
        if (!/^_ga/.test(name) && !/^_gid$/.test(name)) return;
        [location.hostname, "." + host, host].forEach(function (d) {
          document.cookie = name + "=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/;domain=" + d;
        });
        document.cookie = name + "=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/";
      });
    } catch (e) {}
  }

  // ── the banner ────────────────────────────────────────────────────────────
  var el = null;

  function styles() {
    if (document.getElementById("ndck-style")) return;
    var s = document.createElement("style");
    s.id = "ndck-style";
    // Own tokens, light and dark, because these pages do not share one theme system. Both are
    // defined up front so no state inherits a colour from the other.
    s.textContent = [
      "#ndck{--ndck-bg:#fff;--ndck-fg:#0f172a;--ndck-mut:#475569;--ndck-line:#e2e8f0;",
      "--ndck-accent:#0f766e;--ndck-accent-fg:#fff;--ndck-soft:#f1f5f9;",
      "position:fixed;left:0;right:0;bottom:0;z-index:2147483000;",
      "background:var(--ndck-bg);color:var(--ndck-fg);",
      "border-top:1px solid var(--ndck-line);box-shadow:0 -6px 24px rgba(0,0,0,.14);",
      "font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;",
      "padding:1rem 1rem calc(1rem + env(safe-area-inset-bottom,0px));",
      "max-height:85vh;overflow-y:auto}",
      "@media (prefers-color-scheme:dark){#ndck{--ndck-bg:#0f172a;--ndck-fg:#e2e8f0;",
      "--ndck-mut:#94a3b8;--ndck-line:#1e293b;--ndck-accent:#14b8a6;--ndck-accent-fg:#052e2b;",
      "--ndck-soft:#1e293b}}",
      "#ndck .ndck-in{max-width:44rem;margin:0 auto}",
      "#ndck h2{margin:0 0 .35rem;font-size:1.02rem;line-height:1.35}",
      "#ndck p{margin:0 0 .75rem;font-size:.88rem;line-height:1.6;color:var(--ndck-mut)}",
      "#ndck .ndck-btns{display:flex;flex-wrap:wrap;gap:.5rem}",
      "#ndck button{font:inherit;font-size:.88rem;font-weight:600;border-radius:8px;",
      "padding:.65rem 1rem;cursor:pointer;border:1px solid var(--ndck-line);",
      "background:var(--ndck-soft);color:var(--ndck-fg);flex:1 1 auto;min-width:9.5rem}",
      "#ndck button.ndck-primary{background:var(--ndck-accent);color:var(--ndck-accent-fg);",
      "border-color:var(--ndck-accent)}",
      "#ndck button:focus-visible{outline:3px solid var(--ndck-accent);outline-offset:2px}",
      "#ndck a{color:var(--ndck-accent);font-size:.82rem}",
      "#ndck .ndck-grp{border:1px solid var(--ndck-line);border-radius:10px;padding:.7rem .8rem;",
      "margin-bottom:.6rem;background:var(--ndck-soft)}",
      "#ndck .ndck-grp h3{margin:0 0 .25rem;font-size:.9rem;display:flex;gap:.5rem;",
      "align-items:center;justify-content:space-between}",
      "#ndck .ndck-grp p{margin:0;font-size:.82rem}",
      "#ndck .ndck-sw{font-size:.78rem;font-weight:700;padding:.2rem .6rem;border-radius:999px;",
      "border:1px solid var(--ndck-line);background:var(--ndck-bg);color:var(--ndck-mut);",
      "cursor:pointer;white-space:nowrap}",
      "#ndck .ndck-sw[aria-checked='true']{background:var(--ndck-accent);",
      "color:var(--ndck-accent-fg);border-color:var(--ndck-accent)}",
      "#ndck .ndck-sw[disabled]{cursor:default;opacity:.85}",
      "@media (max-width:26rem){#ndck button{flex:1 1 100%}}"
    ].join("");
    document.head.appendChild(s);
  }

  function close() {
    if (el && el.parentNode) el.parentNode.removeChild(el);
    el = null;
  }

  function decide(analytics) {
    var c = save({ analytics: analytics });
    if (!analytics) dropAnalyticsCookies();
    close();
    announce(c);
  }

  function render(showDetail) {
    styles();
    close();
    el = document.createElement("div");
    el.id = "ndck";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-modal", "false");
    el.setAttribute("aria-label", t("title"));

    var wrap = document.createElement("div");
    wrap.className = "ndck-in";

    var h = document.createElement("h2");
    h.textContent = t("title");
    wrap.appendChild(h);

    var p = document.createElement("p");
    p.textContent = t("body");
    wrap.appendChild(p);

    var current = load();
    var wantAnalytics = !!(current && current.analytics);

    if (showDetail) {
      wrap.appendChild(group(t("essentialName"), t("essentialWhy"), true, true, null));
      var swRef = {};
      wrap.appendChild(group(t("analyticsName"), t("analyticsWhy"), wantAnalytics, false,
        function (on) { wantAnalytics = on; }, swRef));
    }

    var btns = document.createElement("div");
    btns.className = "ndck-btns";

    if (showDetail) {
      btns.appendChild(button(t("save"), "ndck-primary", function () { decide(wantAnalytics); }));
      btns.appendChild(button(t("acceptAll"), "", function () { decide(true); }));
    } else {
      // Accept and refuse are the same size, side by side. A refusal that is harder to reach
      // than an acceptance is not a free choice.
      btns.appendChild(button(t("acceptAll"), "ndck-primary", function () { decide(true); }));
      btns.appendChild(button(t("essentialOnly"), "", function () { decide(false); }));
      btns.appendChild(button(t("choose"), "", function () { render(true); }));
    }
    wrap.appendChild(btns);

    var foot = document.createElement("p");
    foot.style.margin = ".7rem 0 0";
    foot.style.fontSize = ".78rem";
    var a = document.createElement("a");
    a.href = POLICY_URL;
    a.textContent = t("policy");
    foot.appendChild(a);
    foot.appendChild(document.createTextNode(" · " + t("changedLater")));
    wrap.appendChild(foot);

    el.appendChild(wrap);
    document.body.appendChild(el);
    var first = el.querySelector("button");
    if (first) { try { first.focus(); } catch (e) {} }
  }

  function button(label, cls, fn) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = cls;
    b.textContent = label;        // textContent, never innerHTML - nothing here is markup
    b.addEventListener("click", fn);
    return b;
  }

  function group(name, why, on, locked, onChange) {
    var d = document.createElement("div");
    d.className = "ndck-grp";
    var h = document.createElement("h3");
    h.appendChild(document.createTextNode(name));
    var sw = document.createElement("button");
    sw.type = "button";
    sw.className = "ndck-sw";
    sw.setAttribute("role", "switch");
    sw.setAttribute("aria-checked", on ? "true" : "false");
    sw.textContent = on ? t("on") : t("off");
    if (locked) {
      sw.disabled = true;
    } else {
      sw.addEventListener("click", function () {
        on = !on;
        sw.setAttribute("aria-checked", on ? "true" : "false");
        sw.textContent = on ? t("on") : t("off");
        if (onChange) onChange(on);
      });
    }
    h.appendChild(sw);
    d.appendChild(h);
    var p = document.createElement("p");
    p.textContent = why;
    d.appendChild(p);
    return d;
  }

  // ── what the rest of the site uses ────────────────────────────────────────
  var api = {
    /* Has this group been allowed? Anything not decided is NOT allowed. */
    allows: function (group) {
      // Essential first, and without consulting the stored answer: it is allowed by definition,
      // it is what the banner tells people cannot be switched off, and it is true before anybody
      // has answered anything. Checking the answer first made this say "no" to signing somebody
      // in until they had dismissed a banner - the function contradicting the page.
      if (group === "essential") return true;
      var c = load();
      if (!c) return false;                       // undecided is NOT permission for anything else
      return group === "analytics" ? !!c.analytics : false;
    },
    decided: function () { return !!load(); },
    /* The footer link, and the way to withdraw. */
    open: function () { render(true); },
    onChange: function (fn) {
      window.addEventListener("nidaan-consent", function (e) { fn(e.detail || load()); });
    }
  };
  window.nidaanCookies = api;

  // The page's own language toggle should change the banner too, rather than leaving a Hindi
  // reader looking at English while they decide something that matters.
  window.addEventListener("storage", function (e) {
    if (el && e && (e.key === "nidaan_lang" || e.key === "claim_lang")) {
      render(!!el.querySelector(".ndck-grp"));
    }
  });

  function start() {
    if (!load()) render(false);
    else announce(load());          // so gated scripts on a repeat visit still get told
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
