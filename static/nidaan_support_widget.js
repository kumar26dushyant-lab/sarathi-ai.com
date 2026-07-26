/* Nidaan Partner — AI support + lead-gen chat widget (self-contained, mobile-first).
   S1: preferred-language picker, greeting + quick-reply chips, and live polling so
   staff replies appear without a refresh. Talks to /nidaan/api/support/*.
   Conversation persists via thread_id + thread_key in localStorage. */
(function () {
  if (window.__nidaanSupportLoaded) return;
  window.__nidaanSupportLoaded = true;

  var TKEY = 'nidaan_support_thread';
  var LKEY = 'nidaan_support_lang';
  var thread = null, lang = '';
  try { thread = JSON.parse(localStorage.getItem(TKEY) || 'null'); } catch (e) { thread = null; }
  try { lang = localStorage.getItem(LKEY) || ''; } catch (e) { lang = ''; }
  var lastMsgId = 0, pollTimer = null, busy = false, greeted = false;

  var GREET = {
    en: "Hi! 👋 I'm the Nidaan Partner assistant. I can help with rejected or underpaid claim reviews, our plans, and how everything works. What would you like to know?",
    hi: "नमस्ते! 👋 मैं Nidaan Partner असिस्टेंट हूँ। रिजेक्ट या कम भुगतान वाले क्लेम की समीक्षा, हमारे प्लान्स और प्रक्रिया में मदद कर सकता हूँ। आप क्या जानना चाहेंगे?",
    hinglish: "Namaste! 👋 Main Nidaan Partner assistant hoon. Rejected ya underpaid claim review, plans aur process ke baare mein help kar sakta hoon. Aap kya jaanna chahenge?"
  };
  var CHIPS = {
    en: ["🛡️ Check my rejected claim", "💳 Plans & pricing", "🙋 Talk to a human"],
    hi: ["🛡️ मेरा रिजेक्ट क्लेम जांचें", "💳 प्लान्स और कीमत", "🙋 इंसान से बात करें"],
    hinglish: ["🛡️ Mera rejected claim check karein", "💳 Plans aur pricing", "🙋 Insaan se baat karein"]
  };

  var css = ''
    + '.nsw-btn{position:fixed;right:18px;bottom:18px;z-index:99998;width:58px;height:58px;border-radius:50%;border:none;cursor:pointer;background:linear-gradient(135deg,#06b6d4,#0891b2);color:#fff;font-size:26px;box-shadow:0 6px 20px rgba(6,182,212,.45);display:flex;align-items:center;justify-content:center;transition:transform .15s}'
    + '.nsw-btn:active{transform:scale(.92)}'
    + '.nsw-panel{position:fixed;right:18px;bottom:86px;z-index:99999;width:360px;max-width:calc(100vw - 24px);height:540px;max-height:calc(100vh - 110px);background:#0a1628;border:1px solid rgba(255,255,255,.12);border-radius:16px;display:none;flex-direction:column;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,.5);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}'
    + '.nsw-panel.open{display:flex}'
    + '.nsw-hdr{background:linear-gradient(135deg,#06b6d4,#0891b2);color:#fff;padding:.85rem 1rem;position:relative}'
    + '.nsw-hdr h4{margin:0;font-size:1rem;font-weight:800}.nsw-hdr p{margin:.15rem 0 0;font-size:.72rem;opacity:.9}'
    + '.nsw-x{position:absolute;top:.7rem;right:.8rem;background:none;border:none;color:#fff;font-size:1.3rem;cursor:pointer;line-height:1}'
    + '.nsw-msgs{flex:1;overflow-y:auto;padding:1rem;display:flex;flex-direction:column;gap:.6rem;background:#0a1628}'
    + '.nsw-b{max-width:82%;padding:.6rem .8rem;border-radius:14px;font-size:.9rem;line-height:1.45;white-space:pre-wrap;word-wrap:break-word}'
    + '.nsw-b.ai{align-self:flex-start;background:rgba(255,255,255,.07);color:#e2e8f0;border-bottom-left-radius:4px}'
    + '.nsw-b.staff{align-self:flex-start;background:rgba(52,211,153,.14);color:#d1fae5;border-bottom-left-radius:4px}'
    + '.nsw-b.me{align-self:flex-end;background:linear-gradient(135deg,#06b6d4,#0891b2);color:#fff;border-bottom-right-radius:4px}'
    + '.nsw-tag{font-size:.6rem;opacity:.55;margin-bottom:.15rem}'
    + '.nsw-note{align-self:center;font-size:.72rem;color:#fbbf24;text-align:center;padding:.2rem .5rem}'
    + '.nsw-typing{align-self:flex-start;color:rgba(255,255,255,.4);font-size:.8rem;font-style:italic}'
    + '.nsw-chips{display:flex;flex-wrap:wrap;gap:.4rem;padding:0 1rem .5rem}'
    + '.nsw-chip{background:rgba(34,211,238,.1);border:1px solid rgba(34,211,238,.3);color:#67e8f9;border-radius:16px;padding:.35rem .7rem;font-size:.8rem;cursor:pointer}'
    + '.nsw-chip:active{opacity:.7}'
    + '.nsw-lang{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:.7rem;padding:2rem 1.2rem;text-align:center}'
    + '.nsw-lang p{color:#e2e8f0;font-size:.95rem;margin:0 0 .3rem}'
    + '.nsw-lang button{width:100%;max-width:220px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.16);color:#fff;border-radius:10px;padding:.7rem;font-size:1rem;cursor:pointer}'
    + '.nsw-lang button:active{background:rgba(6,182,212,.25)}'
    + '.nsw-in{display:flex;gap:.5rem;padding:.7rem;border-top:1px solid rgba(255,255,255,.1);background:#0a1628}'
    + '.nsw-in textarea{flex:1;resize:none;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14);border-radius:10px;padding:.6rem;color:#fff;font-size:.9rem;font-family:inherit;max-height:90px}'
    + '.nsw-in textarea:focus{outline:none;border-color:#22d3ee}'
    + '.nsw-in button{background:#06b6d4;border:none;border-radius:10px;color:#fff;padding:0 1rem;font-weight:700;cursor:pointer;font-size:1.1rem}'
    + '.nsw-in button:disabled{opacity:.5;cursor:default}'
    + '@media(max-width:480px){.nsw-panel{right:8px;bottom:78px;height:calc(100vh - 96px)}}';
  var style = document.createElement('style'); style.textContent = css; document.head.appendChild(style);

  var btn = document.createElement('button');
  btn.className = 'nsw-btn'; btn.setAttribute('aria-label', 'Chat with us'); btn.innerHTML = '💬';
  document.body.appendChild(btn);

  var panel = document.createElement('div');
  panel.className = 'nsw-panel';
  panel.innerHTML =
    '<div class="nsw-hdr"><h4>Chat with Nidaan Partner</h4>'
    + '<p>AI assistant · human team Mon–Fri, 10am–6pm IST</p>'
    + '<button class="nsw-x" aria-label="Close">×</button></div>'
    + '<div class="nsw-msgs" id="nswMsgs"></div>'
    + '<div class="nsw-chips" id="nswChips"></div>'
    + '<div class="nsw-in" id="nswIn"><textarea id="nswInput" rows="1" placeholder="Type your question…"></textarea>'
    + '<button id="nswSend">➤</button></div>';
  document.body.appendChild(panel);

  var msgs = panel.querySelector('#nswMsgs');
  var chipsBox = panel.querySelector('#nswChips');
  var inBox = panel.querySelector('#nswIn');
  var input = panel.querySelector('#nswInput');
  var sendBtn = panel.querySelector('#nswSend');

  function el(s){ var d=document.createElement('div'); d.textContent=s==null?'':s; return d.innerHTML; }
  function scroll(){ msgs.scrollTop = msgs.scrollHeight; }
  function bubble(text, who){
    var b=document.createElement('div');
    b.className='nsw-b '+(who==='customer'?'me':(who==='staff'?'staff':'ai'));
    var tag = who==='staff' ? '<div class="nsw-tag">Support agent</div>' : '';
    b.innerHTML = tag + el(text); msgs.appendChild(b); scroll();
  }
  function note(text){ var n=document.createElement('div'); n.className='nsw-note'; n.innerHTML=el(text); msgs.appendChild(n); scroll(); }

  function showLangPicker(){
    inBox.style.display='none'; chipsBox.style.display='none';
    var w=document.createElement('div'); w.className='nsw-lang'; w.id='nswLang';
    w.innerHTML = '<p>Choose your language<br><span style="opacity:.6;font-size:.82rem">अपनी भाषा चुनें</span></p>'
      + '<button data-l="en">English</button>'
      + '<button data-l="hi">हिंदी</button>'
      + '<button data-l="hinglish">Hinglish</button>';
    msgs.appendChild(w);
    w.querySelectorAll('button').forEach(function(bt){ bt.onclick=function(){ chooseLang(bt.getAttribute('data-l')); }; });
  }
  function chooseLang(l){
    lang = l; try{ localStorage.setItem(LKEY, l); }catch(e){}
    var lp=document.getElementById('nswLang'); if(lp) lp.remove();
    inBox.style.display=''; showGreeting(); startPoll();
    setTimeout(function(){ input.focus(); }, 80);
  }
  function showGreeting(){
    if(greeted) return; greeted = true;
    bubble(GREET[lang]||GREET.en, 'ai');
    renderChips();
  }
  function renderChips(){
    var c = CHIPS[lang]||CHIPS.en;
    chipsBox.style.display='flex';
    chipsBox.innerHTML = c.map(function(t){ return '<div class="nsw-chip">'+el(t)+'</div>'; }).join('');
    Array.prototype.forEach.call(chipsBox.querySelectorAll('.nsw-chip'), function(ch){
      ch.onclick=function(){ chipsBox.style.display='none'; chipsBox.innerHTML=''; send(ch.textContent.replace(/^[^\wऀ-ॿ]+/, '').trim()); };
    });
  }

  async function loadHistory(){
    if(!thread){ if(!lang) showLangPicker(); else { showGreeting(); startPoll(); } return; }
    // existing conversation → pull full history
    try{
      var r = await fetch('/nidaan/api/support/thread?thread_id='+thread.id+'&thread_key='+encodeURIComponent(thread.key)+'&after_id=0');
      if(!r.ok){ thread=null; localStorage.removeItem(TKEY); if(!lang) showLangPicker(); else { showGreeting(); startPoll(); } return; }
      var d = await r.json();
      (d.messages||[]).forEach(function(m){ bubble(m.body, m.sender_type); if(m.msg_id>lastMsgId) lastMsgId=m.msg_id; });
      if(!(d.messages||[]).length) showGreeting();
      greeted = true; startPoll();
    }catch(e){ showGreeting(); startPoll(); }
  }

  async function syncMessages(){
    if(!thread || busy) return;
    try{
      var r = await fetch('/nidaan/api/support/thread?thread_id='+thread.id+'&thread_key='+encodeURIComponent(thread.key)+'&after_id='+lastMsgId);
      if(!r.ok) return;
      var d = await r.json();
      (d.messages||[]).forEach(function(m){ if(m.msg_id>lastMsgId){ bubble(m.body, m.sender_type); lastMsgId=m.msg_id; } });
    }catch(e){}
  }
  function startPoll(){ if(pollTimer) return; pollTimer=setInterval(syncMessages, 4000); }
  function stopPoll(){ if(pollTimer){ clearInterval(pollTimer); pollTimer=null; } }

  var openedOnce=false;
  function openPanel(){ panel.classList.add('open'); if(!openedOnce){ openedOnce=true; loadHistory(); } else startPoll(); setTimeout(function(){ if(input.offsetParent) input.focus(); },100); }
  function closePanel(){ panel.classList.remove('open'); stopPoll(); }
  btn.addEventListener('click', function(){ panel.classList.contains('open')?closePanel():openPanel(); });
  panel.querySelector('.nsw-x').addEventListener('click', closePanel);

  input.addEventListener('input', function(){ input.style.height='auto'; input.style.height=Math.min(input.scrollHeight,90)+'px'; });
  input.addEventListener('keydown', function(e){ if(e.key==='Enter'&&!e.shiftKey){ e.preventDefault(); send(); } });
  sendBtn.addEventListener('click', function(){ send(); });

  async function send(preset){
    var text = (preset!=null?preset:(input.value||'')).trim();
    if(!text || busy) return;
    busy=true; sendBtn.disabled=true;
    if(chipsBox.style.display!=='none'){ chipsBox.style.display='none'; chipsBox.innerHTML=''; }
    var optimistic=document.createElement('div'); optimistic.className='nsw-b me'; optimistic.innerHTML=el(text); msgs.appendChild(optimistic); scroll();
    if(preset==null){ input.value=''; input.style.height='auto'; }
    var typing=document.createElement('div'); typing.className='nsw-typing'; typing.textContent='…'; msgs.appendChild(typing); scroll();
    try{
      var body={ message:text, lang:lang };
      if(thread){ body.thread_id=thread.id; body.thread_key=thread.key; }
      var r = await fetch('/nidaan/api/support/message', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) });
      typing.remove();
      var d = await r.json().catch(function(){ return {}; });
      if(!r.ok){ bubble(d.detail||'Sorry, something went wrong. Please try again.', 'ai'); busy=false; sendBtn.disabled=false; return; }
      if(d.thread_id && d.thread_key){ thread={ id:d.thread_id, key:d.thread_key }; localStorage.setItem(TKEY, JSON.stringify(thread)); }
      optimistic.remove();                 // replace optimistic bubble with server truth
      busy=false;                          // allow sync to run
      await syncMessages();                // pulls the stored customer msg + AI reply (with ids)
      if(d.escalated) note('🔔 A team member will follow up during support hours (Mon–Fri, 10am–6pm IST).');
      startPoll();
    }catch(e){ typing.remove(); bubble('Network issue — please try again.', 'ai'); }
    busy=false; sendBtn.disabled=false; if(input.offsetParent) input.focus();
  }
})();
