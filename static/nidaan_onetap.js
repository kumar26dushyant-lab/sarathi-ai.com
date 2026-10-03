/* ONE TAP, ONE ACTION - every Nidaan page loads this (founder, 2 Oct 2026).

   Impatient taps are not a user error: people tap again when a button gives nothing back. This
   swallows the extra taps until the work the first one started has finished (or 10 s), and shows
   the first one landed. One capture-phase listener, before any onclick runs - a button does not
   have to know it is protected. deploy/verify-onetap.py fails the build if a page that talks to
   the server does not load this file.
   A button that must fire repeatedly (a counter, a stepper) opts out with data-nd-rapid="1". */
(function(){
  if (window.__ndOneTap) return;
  window.__ndOneTap = true;

  // Every request the page makes, with the moment it started. Used to answer one question:
  // "has the work THIS tap started finished yet?" Nothing else is done with it.
  let recent = [];
  const origFetch = window.fetch;
  window.fetch = function(){
    const p = origFetch.apply(window, arguments);
    try{
      recent.push({t: Date.now(), p: p});
      if (recent.length > 60) recent = recent.slice(-60);
    }catch(e){}
    return p;
  };

  // Uploads use XMLHttpRequest, not fetch: the same question applies to them.
  try{
    const origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function(){
      const x = this;
      try{
        const p = new Promise(function(res){ x.addEventListener('loadend', res); });
        recent.push({t: Date.now(), p: p});
        if (recent.length > 60) recent = recent.slice(-60);
      }catch(e){}
      return origSend.apply(x, arguments);
    };
  }catch(e){}

  // How a working button looks - dimmed, with a dot that moves so it never looks frozen.
  try{
    const st = document.createElement('style');
    st.textContent = `
  /* A button that has been tapped and is working. Dimmed so it reads as "doing something", with
     a dot that moves so it does not look frozen - the whole reason people tap twice. */
  .nd-working{opacity:.65;cursor:progress;position:relative}
  .nd-working::after{content:'';position:absolute;right:.28rem;top:50%;width:.36rem;
    height:.36rem;margin-top:-.18rem;border-radius:50%;background:currentColor;
    animation:ndWork .7s ease-in-out infinite}
  @keyframes ndWork{0%,100%{opacity:.25}50%{opacity:1}}
  @media (prefers-reduced-motion:reduce){ .nd-working::after{animation:none;opacity:.7} }
`;
    (document.head || document.documentElement).appendChild(st);
  }catch(e){}

  const WATCH_MS = 200;     // a request this tap starts will have started by now
  const CEILING_MS = 10000; // and the button comes back even if that request never finishes

  function release(btn){
    if (!btn || btn.dataset.ndTap !== '1') return;
    delete btn.dataset.ndTap;
    btn.classList.remove('nd-working');
    btn.removeAttribute('aria-busy');
  }

  document.addEventListener('click', function(e){
    // A click that lands on a form control (a file picker, a tick box, a dropdown) is the browser
    // carrying the person's own tap to it - often sent on by a <label> styled as a button, as a
    // second click straight after the first. Swallowing it as a "double tap" is what stopped the
    // Doc Splitter's file picker opening (3 Oct). Controls are never held.
    const tgt = e.target;
    if (tgt && tgt.matches && tgt.matches(
        'input:not([type=submit]):not([type=button]):not([type=image]):not([type=reset]), select, textarea, option')) return;
    // Buttons, and the other things people actually tap on these screens: a claim row, a board
    // or task card, a tab. closest() finds the NEAREST one, so a button inside a clickable row
    // is guarded as the button, not as the row.
    const btn = e.target && e.target.closest
      ? e.target.closest('button, input[type=submit], a.l2mv, a.btn, .btn, .btn-pay, .plan-cta, .l2mv, .csrpen, .pen, '
                       + 'tr[onclick], td[onclick], .board-card, .task-card, .tab-pill, .wai-row')
      : null;
    if (!btn) return;
    // A label does nothing itself - it hands the tap to its control, which is checked above.
    if (btn.tagName === 'LABEL') return;
    if (btn.dataset.ndRapid === '1' || btn.hasAttribute('data-nd-rapid')) return;

    // A dialog that has only just appeared, under a finger still coming down. Or already
    // working: this is the second tap. Either way the onclick does not run.
    if (btn.dataset.ndArming === '1' || btn.dataset.ndTap === '1'){
      e.preventDefault();
      e.stopPropagation();
      if (e.stopImmediatePropagation) e.stopImmediatePropagation();
      return;
    }
    if (btn.disabled) return;

    btn.dataset.ndTap = '1';
    btn.classList.add('nd-working');
    btn.setAttribute('aria-busy', 'true');

    const t0 = Date.now();
    let freed = false;
    const free = function(){ if (freed) return; freed = true; release(btn); };
    setTimeout(free, CEILING_MS);

    setTimeout(function(){
      let mine = [];
      try{
        mine = recent.filter(function(r){ return r.t >= t0 && r.t <= t0 + WATCH_MS; })
                     .map(function(r){ return r.p; });
      }catch(err){ mine = []; }
      if (!mine.length) return free();        // sent nothing: a pencil, a tab, a menu
      let left = mine.length;
      const one = function(){ if (--left <= 0) free(); };
      mine.forEach(function(p){
        try{ p.then(one, one); }catch(err){ one(); }
      });
    }, WATCH_MS);
  }, true);
})();
