/* NidaanPartner — reusable dashboard USER GUIDE (voice + readable), v2.
   Mounts a MIC control into the dashboard's top menu; voice defaults to Hindi and stays
   in SYNC with the dashboard language. Readable steps expand on demand.
   Usage:
     NidaanGuide.init({
       key:'subscriber', mount:'#guideMic',          // where the mic goes (top nav)
       lang:'hi', onLangChange:function(l){ ... },     // sync back to the dashboard
       title:{hi,en}, greeting:{hi,en}, steps:[{hi:{t,b},en:{t,b}}...] });
     NidaanGuide.setLang('hi');                        // called by the dashboard's own toggle
   Self-contained (own CSS + Web Speech TTS). No account data. */
(function () {
  var CY = '#06b6d4', CY2 = '#0891b2', INK = '#0f172a';
  var G = { cfg: null, lang: 'hi', queue: [], playing: false, paused: false, mic: null, panel: null };

  function T(o){ return (o ? (G.lang === 'hi' ? o.hi : o.en) : '') || (o && (o.hi || o.en)) || ''; }

  // ---- TTS (browser Web Speech API) -------------------------------------------
  function loadVoices(){ try{ window.speechSynthesis.getVoices(); }catch(e){} }
  if (window.speechSynthesis){ loadVoices(); try{ window.speechSynthesis.onvoiceschanged = loadVoices; }catch(e){} }
  function pickVoice(lang){
    var vs = []; try{ vs = window.speechSynthesis.getVoices() || []; }catch(e){}
    var pref = lang === 'hi' ? ['hi-in','hi'] : ['en-in','en-gb','en-us','en'];
    for (var p = 0; p < pref.length; p++){
      var cand = vs.filter(function(v){ return (v.lang||'').toLowerCase().indexOf(pref[p]) === 0; });
      if (cand.length){
        var fem = cand.filter(function(v){ return /female|woman|google|microsoft/i.test(v.name||''); });
        return fem[0] || cand[0];
      }
    }
    return null;
  }
  function splitSentences(t){ return String(t||'').replace(/\s+/g,' ').trim().split(/(?<=[.!?।])\s+/).filter(Boolean); }

  function stopSpeech(){ G.playing=false; G.paused=false; try{ window.speechSynthesis.cancel(); }catch(e){} updateControls(); clearHighlight(); }

  function play(){
    if (!window.speechSynthesis){ openPanel(); return; }
    G.playing=true; G.paused=false;
    var voice = pickVoice(G.lang), chunks=[];
    for (var i=0;i<G.queue.length;i++){ var seg=G.queue[i], ss=splitSentences(seg.text);
      for (var s=0;s<ss.length;s++) chunks.push({step:seg.step, text:ss[s], first:(s===0)}); }
    var ci=0;
    function next(){
      if (!G.playing || ci>=chunks.length){ if (ci>=chunks.length) stopSpeech(); return; }
      var c=chunks[ci++]; if (c.first) highlightStep(c.step);
      var u=new SpeechSynthesisUtterance(c.text);
      u.lang=(G.lang==='hi'?'hi-IN':'en-IN'); if (voice) u.voice=voice; u.rate=0.96; u.pitch=1.0;
      u.onend=function(){ if (G.playing && !G.paused) next(); };
      u.onerror=function(){ if (G.playing && !G.paused) next(); };
      try{ window.speechSynthesis.speak(u); }catch(e){ next(); }
    }
    try{ window.speechSynthesis.cancel(); }catch(e){}
    next(); updateControls();
  }
  function toggle(){
    if (G.playing && !G.paused){ G.paused=true; try{ window.speechSynthesis.pause(); }catch(e){} updateControls(); }
    else if (G.playing && G.paused){ G.paused=false; try{ window.speechSynthesis.resume(); }catch(e){} updateControls(); }
    else { play(); }
  }

  // ---- Rendering ---------------------------------------------------------------
  function el(tag, cls, html){ var d=document.createElement(tag); if(cls)d.className=cls; if(html!=null)d.innerHTML=html; return d; }
  function escapeHtml(s){ return String(s==null?'':s).replace(/[&<>"']/g,function(c){return({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c];}); }

  function highlightStep(step){ clearHighlight();
    var n=G.panel && G.panel.querySelector('[data-step="'+step+'"]');
    if(n){ n.classList.add('ng-active'); if (G.panel.classList.contains('open')) n.scrollIntoView({behavior:'smooth',block:'center'}); } }
  function clearHighlight(){ if(!G.panel)return; G.panel.querySelectorAll('.ng-step.ng-active').forEach(function(n){n.classList.remove('ng-active');}); }

  function playLabel(){ return G.playing && !G.paused ? '⏸' : (G.paused ? '▶' : '🎧'); }
  function updateControls(){
    if (G.mic){ var mp=G.mic.querySelector('.ngm-play'); if(mp){ mp.firstChild ? (mp.childNodes[0].nodeValue=playLabel()) : (mp.textContent=playLabel());
      mp.classList.toggle('on', G.playing && !G.paused); } }
    if (G.panel){ var pp=G.panel.querySelector('#ngPlay'); if(pp) pp.textContent = G.playing && !G.paused
      ? (G.lang==='hi'?'⏸ रोकें':'⏸ Pause') : (G.lang==='hi'?'▶ सुनें':'▶ Listen'); }
  }

  function buildQueue(){ G.queue=[]; G.queue.push({step:0,text:T(G.cfg.greeting)});
    G.cfg.steps.forEach(function(st,i){ G.queue.push({step:i+1,text:T(st).t+'. '+T(st).b}); }); }

  function renderSteps(){
    var wrap=G.panel.querySelector('#ngSteps'); wrap.innerHTML='';
    var intro=el('div','ng-step ng-intro'); intro.setAttribute('data-step','0');
    intro.innerHTML='<div class="ng-s-b">'+escapeHtml(T(G.cfg.greeting))+'</div>'; wrap.appendChild(intro);
    G.cfg.steps.forEach(function(st,i){ var s=el('div','ng-step'); s.setAttribute('data-step',String(i+1));
      s.innerHTML='<div class="ng-s-n">'+(i+1)+'</div><div><div class="ng-s-t">'+escapeHtml(T(st).t)+'</div><div class="ng-s-b">'+escapeHtml(T(st).b)+'</div></div>';
      wrap.appendChild(s); }); }

  function applyLang(){
    var c=G.cfg;
    if (G.mic){ var l=G.mic.querySelector('.ngm-lbl'); if(l) l.textContent=(G.lang==='hi'?'गाइड':'Guide');
      G.mic.querySelector('.ngm-play').title=(G.lang==='hi'?'गाइड सुनें':'Listen to the guide');
      var ex=G.mic.querySelector('.ngm-exp'); if(ex) ex.title=(G.lang==='hi'?'पढ़ें':'Read'); }
    if (G.panel){
      G.panel.querySelector('#ngTitle').textContent=T(c.title);
      G.panel.querySelector('#ngHi').classList.toggle('on',G.lang==='hi');
      G.panel.querySelector('#ngEn').classList.toggle('on',G.lang==='en');
      G.panel.querySelector('#ngHint').textContent=(G.lang==='hi'
        ? '🎧 बटन से सुनें, या नीचे पढ़ें। भाषा बदलने पर डैशबोर्ड भी उसी भाषा में हो जाता है।'
        : 'Tap 🎧 to listen, or read below. Changing the language also switches the dashboard.');
      buildQueue(); renderSteps();
    }
    updateControls();
  }

  function openPanel(){ if(!G.panel) buildPanel(); G.panel.classList.add('open'); }
  function closePanel(){ if(G.panel) G.panel.classList.remove('open'); }

  function injectCss(){
    if (document.getElementById('ngCss')) return;
    var css=''
      + '.ngm{display:inline-flex;align-items:center;gap:2px;vertical-align:middle}'
      + '.ngm button{background:'+CY+';color:#fff;border:none;cursor:pointer;font-family:inherit;font-weight:700}'
      + '.ngm .ngm-play{display:inline-flex;align-items:center;gap:5px;border-radius:999px 0 0 999px;padding:7px 11px;font-size:14px}'
      + '.ngm .ngm-play.on{background:'+CY2+';animation:ngpulse 1.4s ease-in-out infinite}'
      + '@keyframes ngpulse{0%,100%{box-shadow:0 0 0 0 rgba(6,182,212,.5)}50%{box-shadow:0 0 0 5px rgba(6,182,212,0)}}'
      + '.ngm .ngm-exp{border-radius:0 999px 999px 0;padding:7px 9px;font-size:12px;border-left:1px solid rgba(255,255,255,.35)}'
      + '.ngm button:hover{background:'+CY2+'}'
      + '.ng-panel{position:fixed;left:18px;bottom:18px;z-index:2147483600;width:400px;max-width:calc(100vw - 24px);'
      + 'height:600px;max-height:calc(100vh - 32px);background:#fff;color:'+INK+';border-radius:18px;box-shadow:0 20px 54px rgba(0,0,0,.32);'
      + 'display:none;flex-direction:column;overflow:hidden;font-family:inherit}'
      + '.ng-panel.open{display:flex}'
      + '.ng-hdr{background:linear-gradient(135deg,'+CY+','+CY2+');color:#fff;padding:13px 15px;display:flex;align-items:center;gap:10px}'
      + '.ng-hdr .ng-av{width:34px;height:34px;border-radius:50%;background:rgba(255,255,255,.2);display:flex;align-items:center;justify-content:center;font-size:18px}'
      + '.ng-hdr h4{margin:0;font-size:15px;font-weight:800}'
      + '.ng-lang{display:flex;border:1px solid rgba(255,255,255,.5);border-radius:8px;overflow:hidden;margin-left:auto}'
      + '.ng-lang button{background:transparent;color:#fff;border:none;padding:5px 9px;font-size:12px;font-weight:700;cursor:pointer}'
      + '.ng-lang button.on{background:#fff;color:'+CY2+'}'
      + '.ng-x{background:none;border:none;color:#fff;font-size:22px;cursor:pointer;line-height:1;margin-left:4px}'
      + '.ng-ctrl{display:flex;gap:.5rem;padding:10px 14px;background:#ecfeff;border-bottom:1px solid #cffafe;align-items:center;flex-wrap:wrap}'
      + '.ng-ctrl button{border:none;border-radius:9px;padding:9px 14px;font-weight:700;font-size:13.5px;cursor:pointer}'
      + '#ngPlay{background:'+CY+';color:#fff}#ngStop{background:#fff;color:#334155;border:1px solid #cbd5e1}'
      + '.ng-hint{font-size:11px;color:#0e7490;flex:1;min-width:120px}'
      + '.ng-body{flex:1;overflow-y:auto;padding:12px 14px;background:#f8fafc;display:flex;flex-direction:column;gap:9px}'
      + '.ng-step{display:flex;gap:10px;background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:11px 12px;transition:box-shadow .2s,border-color .2s}'
      + '.ng-step.ng-active{border-color:'+CY+';box-shadow:0 0 0 3px rgba(6,182,212,.18)}'
      + '.ng-intro{background:linear-gradient(135deg,#ecfeff,#f0f9ff);border-color:#a5f3fc;font-weight:600}'
      + '.ng-s-n{flex:none;width:26px;height:26px;border-radius:50%;background:'+CY+';color:#fff;font-weight:800;font-size:13px;display:flex;align-items:center;justify-content:center}'
      + '.ng-s-t{font-weight:700;font-size:14px;margin-bottom:2px}.ng-s-b{font-size:13.5px;line-height:1.55;color:#334155}'
      + '@media(max-width:480px){.ng-panel{left:0;bottom:0;width:100vw;max-width:100vw;height:88vh;max-height:88vh;border-radius:16px 16px 0 0}'
      + '.ngm .ngm-lbl{display:none}}';
    var st=el('style'); st.id='ngCss'; st.textContent=css; document.head.appendChild(st);
  }

  function buildMic(mountEl){
    var m=el('span','ngm');
    m.innerHTML='<button class="ngm-play" type="button">🎧<span class="ngm-lbl">गाइड</span></button>'
              + '<button class="ngm-exp" type="button">▾</button>';
    mountEl.appendChild(m); G.mic=m;
    m.querySelector('.ngm-play').addEventListener('click', toggle);
    m.querySelector('.ngm-exp').addEventListener('click', function(){ if(G.panel && G.panel.classList.contains('open')) closePanel(); else openPanel(); });
  }
  function buildPanel(){
    var pn=el('div','ng-panel');
    pn.innerHTML='<div class="ng-hdr"><div class="ng-av">🧭</div><h4 id="ngTitle"></h4>'
      + '<div class="ng-lang"><button id="ngHi">हिंदी</button><button id="ngEn">EN</button></div>'
      + '<button class="ng-x" aria-label="Close">×</button></div>'
      + '<div class="ng-ctrl"><button id="ngPlay">▶ सुनें</button><button id="ngStop">⏹</button><span class="ng-hint" id="ngHint"></span></div>'
      + '<div class="ng-body" id="ngSteps"></div>';
    document.body.appendChild(pn); G.panel=pn;
    pn.querySelector('.ng-x').addEventListener('click', closePanel);
    pn.querySelector('#ngHi').addEventListener('click', function(){ setLang('hi', true); });
    pn.querySelector('#ngEn').addEventListener('click', function(){ setLang('en', true); });
    pn.querySelector('#ngPlay').addEventListener('click', toggle);
    pn.querySelector('#ngStop').addEventListener('click', stopSpeech);
    applyLang();
  }

  // fromUser=true → user changed it in the guide → also switch the dashboard (onLangChange).
  function setLang(l, fromUser){
    if (l!=='hi' && l!=='en') return;
    if (l===G.lang){ return; }
    stopSpeech(); G.lang=l;
    try{ localStorage.setItem('nidaan_guide_lang', l); }catch(e){}
    applyLang();
    if (fromUser && G.cfg && typeof G.cfg.onLangChange==='function'){ try{ G.cfg.onLangChange(l); }catch(e){} }
  }

  var API = {
    init: function(cfg){
      if (!cfg || !cfg.steps || G.cfg) return;
      G.cfg=cfg;
      G.lang=(cfg.lang==='en'||cfg.lang==='hi') ? cfg.lang : 'hi';   // default Hindi
      var run=function(){
        injectCss();
        var mount = typeof cfg.mount==='string' ? document.querySelector(cfg.mount) : cfg.mount;
        if (mount){ buildMic(mount); } else {
          // Fallback: a floating button if no top-menu slot is provided.
          var b=el('button','ngm'); b.style.cssText='position:fixed;left:16px;bottom:16px;z-index:2147483600;border-radius:999px';
          b.innerHTML='<button class="ngm-play" type="button">🎧<span class="ngm-lbl">गाइड</span></button>';
          document.body.appendChild(b); G.mic=b; b.querySelector('.ngm-play').addEventListener('click', toggle);
        }
        applyLang();
      };
      if (document.readyState==='loading') document.addEventListener('DOMContentLoaded', run); else run();
    },
    setLang: function(l){ setLang(l, false); },   // external sync from the dashboard's own toggle
    play: play, toggle: toggle, open: openPanel
  };
  window.NidaanGuide = API;
})();
