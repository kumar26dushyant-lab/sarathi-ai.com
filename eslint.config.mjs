// What this is for, in one sentence: to answer "does every name this code uses actually exist?"
//
// On 19 September a single typo - `to` where the parameter is called `toKey` - stopped every
// claim being moved forward from the ops screen, and nothing said so. The browser threw the
// error into a console nobody had open; the button simply did nothing. It took a founder report
// two days later to find it. `no-undef` is the rule that would have caught it the moment it was
// written, because `to` is not a name that exists in that function.
//
// So this config turns on ONE rule and leaves style alone. It is not here to tidy the code; it
// is here to stop a button silently doing nothing. A linter that also complains about spacing is
// a linter people switch off.

export default [
  {
    files: ["**/*.js", "**/*.mjs"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: {
        // The browser. Everything the ops page legitimately reaches for.
        window: "readonly", document: "readonly", console: "readonly", navigator: "readonly",
        location: "readonly", history: "readonly", localStorage: "readonly",
        sessionStorage: "readonly", fetch: "readonly", alert: "readonly", confirm: "readonly",
        prompt: "readonly", setTimeout: "readonly", clearTimeout: "readonly",
        setInterval: "readonly", clearInterval: "readonly", requestAnimationFrame: "readonly",
        FormData: "readonly", Blob: "readonly", File: "readonly", FileReader: "readonly",
        Image: "readonly", Audio: "readonly", URL: "readonly", URLSearchParams: "readonly",
        DOMParser: "readonly", IntersectionObserver: "readonly", MutationObserver: "readonly",
        AbortController: "readonly", TextDecoder: "readonly", TextEncoder: "readonly",
        atob: "readonly", btoa: "readonly", structuredClone: "readonly", Event: "readonly",
        CustomEvent: "readonly", getComputedStyle: "readonly", matchMedia: "readonly",
        Notification: "readonly", speechSynthesis: "readonly",
        SpeechSynthesisUtterance: "readonly", performance: "readonly", screen: "readonly",
        crypto: "readonly", scrollTo: "readonly", requestIdleCallback: "readonly",
        Node: "readonly", Element: "readonly", HTMLElement: "readonly", NodeList: "readonly",
        NodeFilter: "readonly", XMLHttpRequest: "readonly", WebSocket: "readonly",
        // Used to hand Gmail a draft as text/html AND text/plain at once, which is the whole
        // point of the Copy button. A real browser global; the code guards on window.ClipboardItem
        // before touching it, because it is missing on an http:// page.
        ClipboardItem: "readonly",

        // Third-party scripts loaded from somebody else's CDN, which this machine cannot read to
        // discover what they define. Each one is here because the page really does load it.
        google: "readonly",      // accounts.google.com/gsi/client  - Google sign-in
        Razorpay: "readonly",    // checkout.razorpay.com           - payments
        grecaptcha: "readonly",  // recaptcha
        Chart: "readonly",       // chart.js   - the cockpit's graphs
        QRCode: "readonly",      // qrcode.js  - payment and login QR codes
        MediaRecorder: "readonly", MediaStream: "readonly",   // voice notes
        // `event` without declaring it is the old implicit window.event. It works in Chrome and
        // is used deliberately in inline handlers on these pages, so it is allowed rather than
        // rewritten across screens that are working today.
        event: "readonly",

        // NOTHING FROM OUR OWN SCRIPT FILES IS LISTED HERE. deploy/verify-page-js.mjs reads the
        // <script src> tags on the page and discovers what those files put on window. A list
        // kept by hand goes stale, and every stale entry is a name the linter quietly stops
        // checking - which is the one failure this whole config exists to prevent.
      },
    },
    linterOptions: { reportUnusedDisableDirectives: true },
    rules: {
      // THE ONE THAT MATTERS.
      "no-undef": "error",
      // Two more that produce the same symptom - code that looks fine and does nothing.
      "no-unsafe-negation": "error",
      "no-unreachable": "error",
      "no-dupe-keys": "error",
      "no-dupe-args": "error",
      "no-cond-assign": "error",
      // Deliberately silent: style, unused variables, formatting. Not what this is for.
    },
  },
];
