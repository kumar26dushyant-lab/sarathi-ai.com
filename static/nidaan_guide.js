/* NidaanPartner — reusable dashboard USER GUIDE (voice + readable, Hindi-default, bilingual).
   Usage on any dashboard:
     <script src="/static/nidaan_guide.js?v=1" defer></script>
     <script>NidaanGuide.init({ key:'subscriber', title:{hi:'…',en:'…'},
                greeting:{hi:'…',en:'…'}, steps:[{hi:{t,b}, en:{t,b}}, …] });</script>
   Self-contained (own CSS + Web Speech TTS). No account data. */
(function () {
  var CY = '#06b6d4', CY2 = '#0891b2', INK = '#0f172a';
  var G = { cfg: null, lang: 'hi', queue: [], qi: 0, playing: false, paused: false };

  function T(o){ return (G.lang === 'hi' ? o.hi : o.en) || o.hi || o.en || ''; }

  // ---- Text-to-speech (browser Web Speech API) --------------------------------
  var voicesReady = false;
  function loadVoices(){ try{ (window.speechSynthesis.getVoices()||[]); voicesReady = true; }catch(e){} }
  if (window.speechSynthesis){ loadVoices(); window.speechSynthesis.onvoiceschanged = loadVoices; }

  function pickVoice(lang){
    var vs = []; try{ vs = window.speechSynthesis.getVoices() || []; }catch(e){}
    var pref = lang === 'hi' ? ['hi-in','hi'] : ['en-in','en-gb','en-us','en'];
    for (var p = 0; p < pref.length; p++){
      var cand = vs.filter(function(v){ return (v.lang||'').toLowerCase().indexOf(pref[p]) === 0; });
      if (cand.length){
        // prefer a female / Google / Microsoft voice when present
        var fem = cand.filter(function(v){ return /female|woman|google|microsoft/i.test(v.name||''); });
        return (fem[0] || cand[0]);
      }
    }
    return null;
  }
  function splitSentences(t){
    return String(t || '').replace(/\s+/g, ' ').trim()
      .split(/(?<=[.!?।])\s+/).filter(Boolean);
  }

  function stopSpeech(){
    G.playing = false; G.paused = false;
    try{ window.speechSynthesis.cancel(); }catch(e){}
    updateControls(); clearHighlight();
  }

  function speakQueueFrom(idx){
    if (!window.speechSynthesis){ return; }
    G.qi = idx; G.playing = true; G.paused = false;
    var voice = pickVoice(G.lang);
    var chunks = [];
    // Flatten: each queue item (a step) → sentences, tagged with its step index.
    for (var i = G.qi; i < G.queue.length; i++){
      var seg = G.queue[i];
      var sents = splitSentences(seg.text);
      for (var s = 0; s < sents.length; s++) chunks.push({ step: seg.step, text: sents[s], first: (s === 0) });
    }
    var ci = 0;
    function next(){
      if (!G.playing || ci >= chunks.length){ if (ci >= chunks.length){ stopSpeech(); } return; }
      var c = chunks[ci++];
      if (c.first) highlightStep(c.step);
      var u = new SpeechSynthesisUtterance(c.text);
      u.lang = (G.lang === 'hi' ? 'hi-IN' : 'en-IN');
      if (voice) u.voice = voice;
      u.rate = 0.96; u.pitch = 1.0;
      u.onend = function(){ if (G.playing && !G.paused) next(); };
      u.onerror = function(){ if (G.playing && !G.paused) next(); };
      try{ window.speechSynthesis.speak(u); }catch(e){ next(); }
    }
    try{ window.speechSynthesis.cancel(); }catch(e){}
    next(); updateControls();
  }

  // ---- Rendering ---------------------------------------------------------------
  function el(tag, cls, html){ var d = document.createElement(tag); if (cls) d.className = cls; if (html != null) d.innerHTML = html; return d; }

  function highlightStep(step){
    clearHighlight();
    var node = G.panel && G.panel.querySelector('[data-step="' + step + '"]');
    if (node){ node.classList.add('ng-active'); node.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
  }
  function clearHighlight(){
    if (!G.panel) return;
    G.panel.querySelectorAll('.ng-step.ng-active').forEach(function(n){ n.classList.remove('ng-active'); });
  }
  function updateControls(){
    if (!G.panel) return;
    var play = G.panel.querySelector('#ngPlay');
    if (play) play.innerHTML = G.playing && !G.paused
      ? (G.lang==='hi'?'⏸ रोकें':'⏸ Pause')
      : (G.lang==='hi'?'▶ सुनें':'▶ Listen');
  }

  function buildQueue(){
    G.queue = [];
    G.queue.push({ step: 0, text: T(G.cfg.greeting) });      // greeting → intro card (step 0)
    G.cfg.steps.forEach(function(st, i){
      G.queue.push({ step: i + 1, text: T(st).t + '. ' + T(st).b });
    });
  }

  function renderSteps(){
    var wrap = G.panel.querySelector('#ngSteps'); wrap.innerHTML = '';
    // Intro (step 0)
    var intro = el('div', 'ng-step ng-intro'); intro.setAttribute('data-step', '0');
    intro.innerHTML = '<div class="ng-s-b">' + escapeHtml(T(G.cfg.greeting)) + '</div>';
    wrap.appendChild(intro);
    G.cfg.steps.forEach(function(st, i){
      var s = el('div', 'ng-step'); s.setAttribute('data-step', String(i + 1));
      s.innerHTML = '<div class="ng-s-n">' + (i + 1) + '</div>'
        + '<div><div class="ng-s-t">' + escapeHtml(T(st).t) + '</div>'
        + '<div class="ng-s-b">' + escapeHtml(T(st).b) + '</div></div>';
      wrap.appendChild(s);
    });
  }
  function escapeHtml(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]; }); }

  function applyLang(){
    var c = G.cfg;
    G.panel.querySelector('#ngTitle').textContent = T(c.title);
    G.panel.querySelector('#ngHi').classList.toggle('on', G.lang === 'hi');
    G.panel.querySelector('#ngEn').classList.toggle('on', G.lang === 'en');
    G.panel.querySelector('#ngHint').textContent = G.lang === 'hi'
      ? 'नीचे दिए बटन से सुनें, या पढ़ें। कभी भी "गाइड" बटन दबाकर दोबारा देख सकते हैं।'
      : 'Tap Listen to hear it, or just read. Reopen anytime from the "Guide" button.';
    buildQueue(); renderSteps(); updateControls();
  }

  function openPanel(){ G.panel.classList.add('open'); G.btn.style.display = 'none'; }
  function closePanel(){ stopSpeech(); G.panel.classList.remove('open'); G.btn.style.display = ''; }

  function injectCss(){
    if (document.getElementById('ngCss')) return;
    var css = ''
      + '.ng-btn{position:fixed;left:18px;bottom:18px;z-index:2147483600;display:flex;align-items:center;gap:.5rem;'
      + 'background:' + CY + ';color:#fff;border:none;border-radius:999px;padding:12px 18px;font-weight:700;font-size:15px;'
      + 'box-shadow:0 8px 24px rgba(6,182,212,.42);cursor:pointer;font-family:inherit}'
      + '.ng-btn:hover{background:' + CY2 + '}'
      + '.ng-panel{position:fixed;left:18px;bottom:18px;z-index:2147483600;width:400px;max-width:calc(100vw - 24px);'
      + 'height:620px;max-height:calc(100vh - 32px);background:#fff;color:' + INK + ';border-radius:18px;'
      + 'box-shadow:0 20px 54px rgba(0,0,0,.32);display:none;flex-direction:column;overflow:hidden;font-family:inherit}'
      + '.ng-panel.open{display:flex}'
      + '.ng-hdr{background:linear-gradient(135deg,' + CY + ',' + CY2 + ');color:#fff;padding:13px 15px;display:flex;align-items:center;gap:10px}'
      + '.ng-hdr .ng-av{width:34px;height:34px;border-radius:50%;background:rgba(255,255,255,.2);display:flex;align-items:center;justify-content:center;font-size:18px}'
      + '.ng-hdr h4{margin:0;font-size:15px;font-weight:800}'
      + '.ng-lang{display:flex;border:1px solid rgba(255,255,255,.5);border-radius:8px;overflow:hidden;margin-left:auto}'
      + '.ng-lang button{background:transparent;color:#fff;border:none;padding:5px 9px;font-size:12px;font-weight:700;cursor:pointer}'
      + '.ng-lang button.on{background:#fff;color:' + CY2 + '}'
      + '.ng-x{background:none;border:none;color:#fff;font-size:22px;cursor:pointer;line-height:1;margin-left:4px}'
      + '.ng-ctrl{display:flex;gap:.5rem;padding:10px 14px;background:#ecfeff;border-bottom:1px solid #cffafe;align-items:center;flex-wrap:wrap}'
      + '.ng-ctrl button{border:none;border-radius:9px;padding:9px 14px;font-weight:700;font-size:13.5px;cursor:pointer}'
      + '#ngPlay{background:' + CY + ';color:#fff}#ngStop{background:#fff;color:#334155;border:1px solid #cbd5e1}'
      + '.ng-hint{font-size:11px;color:#0e7490;flex:1;min-width:120px}'
      + '.ng-body{flex:1;overflow-y:auto;padding:12px 14px;background:#f8fafc;display:flex;flex-direction:column;gap:9px}'
      + '.ng-step{display:flex;gap:10px;background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:11px 12px;transition:box-shadow .2s,border-color .2s}'
      + '.ng-step.ng-active{border-color:' + CY + ';box-shadow:0 0 0 3px rgba(6,182,212,.18)}'
      + '.ng-intro{background:linear-gradient(135deg,#ecfeff,#f0f9ff);border-color:#a5f3fc;font-weight:600}'
      + '.ng-s-n{flex:none;width:26px;height:26px;border-radius:50%;background:' + CY + ';color:#fff;font-weight:800;font-size:13px;display:flex;align-items:center;justify-content:center}'
      + '.ng-s-t{font-weight:700;font-size:14px;margin-bottom:2px}.ng-s-b{font-size:13.5px;line-height:1.55;color:#334155}'
      + '@media(max-width:480px){.ng-panel{left:0;bottom:0;width:100vw;max-width:100vw;height:90vh;max-height:90vh;border-radius:16px 16px 0 0}'
      + '.ng-btn{left:14px;bottom:14px;padding:11px 15px;font-size:14px}}';
    var st = el('style'); st.id = 'ngCss'; st.textContent = css; document.head.appendChild(st);
  }

  function build(){
    injectCss();
    G.btn = el('button', 'ng-btn');
    G.btn.type = 'button';
    G.btn.innerHTML = '<span style="font-size:18px">📖</span><span>' + (G.lang === 'hi' ? 'गाइड सुनें' : 'Guide') + '</span>';
    document.body.appendChild(G.btn);

    G.panel = el('div', 'ng-panel');
    G.panel.innerHTML =
        '<div class="ng-hdr"><div class="ng-av">🧭</div><h4 id="ngTitle"></h4>'
      + '<div class="ng-lang"><button id="ngHi">हिंदी</button><button id="ngEn">EN</button></div>'
      + '<button class="ng-x" aria-label="Close">×</button></div>'
      + '<div class="ng-ctrl"><button id="ngPlay">▶ सुनें</button><button id="ngStop">⏹</button>'
      + '<span class="ng-hint" id="ngHint"></span></div>'
      + '<div class="ng-body" id="ngSteps"></div>';
    document.body.appendChild(G.panel);

    G.btn.addEventListener('click', function(){ openPanel(); });
    G.panel.querySelector('.ng-x').addEventListener('click', closePanel);
    G.panel.querySelector('#ngHi').addEventListener('click', function(){ setLang('hi'); });
    G.panel.querySelector('#ngEn').addEventListener('click', function(){ setLang('en'); });
    G.panel.querySelector('#ngPlay').addEventListener('click', function(){
      if (G.playing && !G.paused){ // pause
        G.paused = true; try{ window.speechSynthesis.pause(); }catch(e){} updateControls();
      } else if (G.playing && G.paused){ // resume
        G.paused = false; try{ window.speechSynthesis.resume(); }catch(e){} updateControls();
      } else { speakQueueFrom(0); }   // start from greeting
    });
    G.panel.querySelector('#ngStop').addEventListener('click', stopSpeech);

    applyLang();
  }

  function setLang(l){ if (l === G.lang) return; stopSpeech(); G.lang = l;
    try{ localStorage.setItem('nidaan_guide_lang', l); }catch(e){}
    G.btn.querySelector('span:last-child').textContent = (l === 'hi' ? 'गाइड सुनें' : 'Guide'); applyLang(); }

  var API = {
    init: function (cfg){
      if (!cfg || !cfg.steps || G.cfg) return;
      G.cfg = cfg;
      // Default HINDI always (per product requirement). Only switch to English if the user
      // previously chose it in the guide (remembered) — the page's own language is ignored.
      var saved = null; try{ saved = localStorage.getItem('nidaan_guide_lang'); }catch(e){}
      G.lang = (saved === 'en') ? 'en' : 'hi';
      var run = function(){
        build();
        // First visit → auto-OPEN (visual greeting). Voice starts on the user's tap (browser policy).
        var seen; try{ seen = localStorage.getItem('nidaan_guide_seen_' + cfg.key); }catch(e){}
        if (!seen){ setTimeout(function(){ openPanel(); try{ localStorage.setItem('nidaan_guide_seen_' + cfg.key, '1'); }catch(e){} }, 900); }
      };
      if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run); else run();
    },
    open: function(){ if (G.panel) openPanel(); },
    setLang: setLang
  };
  window.NidaanGuide = API;
})();
