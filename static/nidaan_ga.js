/* Google Analytics (GA4) for nidaanpartner.com.
 * Loads ONLY on the live production host — never on staging.* or localhost — so
 * test traffic never pollutes analytics. Shared by every nidaan public page. */
(function () {
  var h = (location.hostname || '').toLowerCase();
  if (h !== 'nidaanpartner.com' && h !== 'www.nidaanpartner.com') return;
  var s = document.createElement('script');
  s.async = true;
  s.src = 'https://www.googletagmanager.com/gtag/js?id=G-CJMN1DJGFM';
  document.head.appendChild(s);
  window.dataLayer = window.dataLayer || [];
  window.gtag = function () { dataLayer.push(arguments); };
  gtag('js', new Date());
  gtag('config', 'G-CJMN1DJGFM');
})();
