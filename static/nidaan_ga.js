/* Google Analytics (GA4) for nidaanpartner.com.
 *
 * TWO GATES, AND THE SECOND ONE IS NEW.
 *
 *   1. Only on the live host - never staging.* or localhost, so test traffic never pollutes
 *      the numbers.
 *   2. Only AFTER the visitor has allowed analytics. Until 28 Sep this file loaded gtag the
 *      moment any public page opened, which set _ga cookies on people who had never been asked
 *      - and no banner shown afterwards could undo that. Nothing here runs now until
 *      nidaan_cookies.js says permission was given.
 *
 * Not decided yet is NOT permission. If the banner is still open, or storage is blocked and the
 * answer could not be kept, nothing loads: the safe direction is no tracking.
 *
 * It also listens, so accepting on the banner starts analytics immediately without a reload -
 * otherwise the first visit of everybody who accepts is invisible, and we would be quietly
 * under-counting exactly the people who said yes.
 */
(function () {
  var started = false;

  function isLiveHost() {
    var h = (location.hostname || '').toLowerCase();
    return h === 'nidaanpartner.com' || h === 'www.nidaanpartner.com';
  }

  function allowed() {
    // No consent module on the page means nobody could have been asked - so, no.
    return !!(window.nidaanCookies && window.nidaanCookies.allows('analytics'));
  }

  function start() {
    if (started || !isLiveHost() || !allowed()) return;
    started = true;
    var s = document.createElement('script');
    s.async = true;
    s.src = 'https://www.googletagmanager.com/gtag/js?id=G-CJMN1DJGFM';
    document.head.appendChild(s);
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { dataLayer.push(arguments); };
    gtag('js', new Date());
    // Belt and braces: even once loaded, tell Google not to use advertising signals here.
    gtag('config', 'G-CJMN1DJGFM', { anonymize_ip: true, allow_google_signals: false });
  }

  // Now (a repeat visitor who already agreed), and again whenever the answer changes.
  window.addEventListener('nidaan-consent', start);
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
