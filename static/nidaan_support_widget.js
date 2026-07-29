/* Nidaan Partner — AI support + lead-gen chat widget (self-contained, mobile-first).
   S1: preferred-language picker, greeting + quick-reply chips, and live polling so
   staff replies appear without a refresh. Talks to /nidaan/api/support/*.
   Conversation persists via thread_id + thread_key in localStorage. */
(function () {
  if (window.__nidaanSupportLoaded) return;
  window.__nidaanSupportLoaded = true;

  // Mode: 'support' (dashboard — the page sets window.NIDAAN_SUPPORT_MODE, account-aware) or
  // 'guide' (homepage — lead-gen/info only, NEVER sends the customer token). Threads are kept
  // separate per mode so a homepage guide chat and a dashboard support chat don't mix.
  var wmode = (window.NIDAAN_SUPPORT_MODE === 'support') ? 'support' : 'guide';
  var TKEY = 'nidaan_support_thread' + (wmode === 'support' ? '_s' : '');
  var LKEY = 'nidaan_support_lang';
  function authHeaders(){
    var h = { 'Content-Type': 'application/json' };
    if (wmode === 'support') { var t=null; try{ t=localStorage.getItem('nidaan_token'); }catch(e){} if(t) h['Authorization']='Bearer '+t; }
    return h;
  }
  var thread = null, lang = '';
  try { thread = JSON.parse(localStorage.getItem(TKEY) || 'null'); } catch (e) { thread = null; }
  try { lang = localStorage.getItem(LKEY) || ''; } catch (e) { lang = ''; }
  var lastMsgId = 0, pollTimer = null, busy = false, greeted = false;
  var supportOpen = true, LEADKEY = 'nidaan_support_lead';

  var OFFLINE = {
    en: "Our team is offline right now. I can still answer your questions — or leave your details and we'll get back to you.",
    hi: "हमारी टीम अभी ऑफ़लाइन है। मैं आपके सवालों का जवाब दे सकता हूँ — या अपना विवरण छोड़ें, हम आपसे संपर्क करेंगे।",
    hinglish: "Hamari team abhi offline hai. Main aapke sawaalon ka jawab de sakta hoon — ya apna detail chhod dein, hum aapse contact karenge."
  };
  var LEADCHIP = { en: "📝 Leave my details", hi: "📝 मेरा विवरण छोड़ें", hinglish: "📝 Apna detail chhodein" };
  var LEADLABELS = {
    en: { name: "Your name", contact: "Email or mobile", msg: "How can we help? (optional)", submit: "Submit", done: "✅ Thanks! Ticket #", follow: " — our team will reach out during working hours." },
    hi: { name: "आपका नाम", contact: "ईमेल या मोबाइल", msg: "हम कैसे मदद करें? (वैकल्पिक)", submit: "भेजें", done: "✅ धन्यवाद! टिकट #", follow: " — हमारी टीम कार्य समय में संपर्क करेगी।" },
    hinglish: { name: "Aapka naam", contact: "Email ya mobile", msg: "Hum kaise help karein? (optional)", submit: "Bhejein", done: "✅ Dhanyawaad! Ticket #", follow: " — hamari team working hours mein contact karegi." }
  };

  var GREET = {
    en: "Namaste! 🙏 I'm NidaanMitra, from the Nidaan Partner team. If your insurance claim was rejected or underpaid, you're in the right place. Tell me what happened — I'm here to help you take the next step.",
    hi: "नमस्ते! 🙏 मैं NidaanMitra हूँ, Nidaan Partner टीम से। अगर आपका बीमा क्लेम रिजेक्ट या कम भुगतान हुआ है, तो आप सही जगह पर हैं। मुझे बताइए क्या हुआ — मैं आपकी मदद के लिए यहाँ हूँ।",
    hinglish: "Namaste! 🙏 Main NidaanMitra hoon, Nidaan Partner team se. Agar aapka insurance claim reject ya kam settle hua hai, to aap sahi jagah par hain. Mujhe bataiye kya hua — main aapki help ke liye yahan hoon."
  };
  var CHIPS = {
    en: ["🛡️ Check my rejected claim", "💳 Plans & pricing", "🙋 Talk to a human"],
    hi: ["🛡️ मेरा रिजेक्ट क्लेम जांचें", "💳 प्लान्स और कीमत", "🙋 इंसान से बात करें"],
    hinglish: ["🛡️ Mera rejected claim check karein", "💳 Plans aur pricing", "🙋 Insaan se baat karein"]
  };
  // Header language control shows the CURRENT language in words (clear for every user) — not a globe.
  var LANGLABEL = { en: 'English', hi: 'हिंदी', hinglish: 'Hinglish' };
  // GROUND RULE: every visible string converts with the selected language — header, subtitle,
  // placeholder, chips, greeting, lead form. (chips/greeting/lead already have per-lang maps.)
  var HDRTITLE = { en: 'Chat with NidaanMitra', hi: 'NidaanMitra से बात करें', hinglish: 'NidaanMitra se baat karein' };
  var HDRSUB = {
    en: 'Nidaan Partner · team online Mon–Fri, 10am–6pm IST',
    hi: 'Nidaan Partner · टीम सोम–शुक्र, सुबह 10 – शाम 6 बजे',
    hinglish: 'Nidaan Partner · team Mon–Fri, subah 10 – shaam 6 baje'
  };
  var PLACEHOLD = { en: 'Type your question…', hi: 'अपना सवाल यहाँ लिखें…', hinglish: 'Apna sawaal yahan likhein…' };
  function updateLangLabel(){
    var L = lang || 'en';
    var e2=document.getElementById('nswLangLabel'); if(e2) e2.textContent = LANGLABEL[lang] || 'भाषा';
    var t=document.getElementById('nswHdrTitle'); if(t) t.textContent = HDRTITLE[L] || HDRTITLE.en;
    var s=document.getElementById('nswHdrSub'); if(s) s.textContent = HDRSUB[L] || HDRSUB.en;
    var inp=document.getElementById('nswInput'); if(inp) inp.setAttribute('placeholder', PLACEHOLD[L] || PLACEHOLD.en);
    setChatId();
  }
  // Show the Chat ID (same number our team sees) once a conversation exists — for transparency
  // and so an agent can look it up. Bilingual label.
  var CHATIDLBL = { en: 'Chat ID: #', hi: 'चैट ID: #', hinglish: 'Chat ID: #' };
  function setChatId(){
    var e = document.getElementById('nswChatId');
    if(!e) return;
    if(thread && thread.id){ e.textContent = (CHATIDLBL[lang] || CHATIDLBL.en) + thread.id; e.style.display=''; }
    else { e.style.display='none'; }
  }

  var css = ''
    + '.nsw-btn{position:fixed;right:18px;bottom:18px;z-index:99998;width:58px;height:58px;border-radius:50%;border:none;cursor:pointer;background:linear-gradient(135deg,#06b6d4,#0891b2);color:#fff;font-size:26px;box-shadow:0 6px 20px rgba(6,182,212,.45);display:flex;align-items:center;justify-content:center;transition:transform .15s}'
    + '.nsw-btn:active{transform:scale(.92)}'
    + '.nsw-panel{position:fixed;right:18px;bottom:86px;z-index:99999;width:360px;max-width:calc(100vw - 24px);height:540px;max-height:calc(100vh - 110px);background:#0a1628;border:1px solid rgba(255,255,255,.12);border-radius:16px;display:none;flex-direction:column;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,.5);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}'
    + '.nsw-panel.open{display:flex}'
    + '.nsw-hdr{background:linear-gradient(135deg,#06b6d4,#0891b2);color:#fff;padding:.85rem 8rem .85rem 1rem;position:relative}'
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
    + '.nsw-langbtn{position:absolute;top:.6rem;right:2.7rem;display:flex;align-items:center;gap:.2rem;white-space:nowrap;background:rgba(255,255,255,.2);border:1px solid rgba(255,255,255,.5);color:#fff;font-size:.8rem;font-weight:700;line-height:1;cursor:pointer;opacity:1;border-radius:16px;padding:.32rem .6rem}'
    + '.nsw-langbtn:active{background:rgba(255,255,255,.32)}'
    + '.nsw-langbtn .cx{font-size:.62rem;opacity:.9}'
    + '.nsw-langmenu{position:absolute;top:2.5rem;right:.6rem;background:#0f1e3a;border:1px solid rgba(255,255,255,.16);border-radius:10px;padding:.3rem;display:none;flex-direction:column;gap:.15rem;z-index:6;box-shadow:0 6px 18px rgba(0,0,0,.4)}'
    + '.nsw-langmenu.open{display:flex}'
    + '.nsw-langmenu button{background:none;border:none;color:#e2e8f0;text-align:left;padding:.4rem .8rem;border-radius:6px;cursor:pointer;font-size:.85rem;white-space:nowrap}'
    + '.nsw-langmenu button:active{background:rgba(6,182,212,.25)}'
    + '@media(max-width:480px){.nsw-panel{left:8px;right:8px;width:auto;max-width:none;bottom:78px;'
    +   'height:calc(100vh - 138px);height:calc(100dvh - 138px)}}';
  var style = document.createElement('style'); style.textContent = css; document.head.appendChild(style);

  var btn = document.createElement('button');
  btn.className = 'nsw-btn'; btn.setAttribute('aria-label', 'Chat with us'); btn.innerHTML = '💬';
  document.body.appendChild(btn);

  var panel = document.createElement('div');
  panel.className = 'nsw-panel';
  panel.innerHTML =
    '<div class="nsw-hdr"><h4 id="nswHdrTitle">Chat with NidaanMitra</h4>'
    + '<p id="nswHdrSub">Nidaan Partner · team online Mon–Fri, 10am–6pm IST</p>'
    + '<div id="nswChatId" style="font-size:.68rem;opacity:.92;margin-top:.15rem;display:none"></div>'
    + '<button class="nsw-langbtn" id="nswLangBtn" title="भाषा बदलें / Change language" aria-label="Change language"><span id="nswLangLabel">भाषा</span><span class="cx">▾</span></button>'
    + '<button class="nsw-x" aria-label="Close">×</button>'
    + '<div class="nsw-langmenu" id="nswLangMenu"><button data-l="en">English</button><button data-l="hi">हिंदी</button><button data-l="hinglish">Hinglish</button></div></div>'
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
  function linkify(html){
    // clickable absolute URLs + site paths (/nidaan/… , /#plans) so the AI can guide visitors
    html = html.replace(/(https?:\/\/[^\s<]+)/g, function(u){ return '<a href="'+u+'" target="_blank" rel="noopener" style="color:#67e8f9">'+u+'</a>'; });
    html = html.replace(/(^|[\s(])(\/(?:nidaan[^\s<]*|#[a-z]+))/g, function(m,pre,path){ return pre+'<a href="'+path+'" target="_blank" rel="noopener" style="color:#67e8f9">'+path+'</a>'; });
    return html;
  }
  function bubble(text, who){
    var b=document.createElement('div');
    b.className='nsw-b '+(who==='customer'?'me':(who==='staff'?'staff':'ai'));
    var tag = who==='staff' ? '<div class="nsw-tag">Support agent</div>' : '';
    var content = (who==='customer') ? el(text) : linkify(el(text));
    b.innerHTML = tag + content; msgs.appendChild(b); scroll();
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
    updateLangLabel();
    var lp=document.getElementById('nswLang'); if(lp) lp.remove();
    inBox.style.display=''; showGreeting(); startPoll();
    setTimeout(function(){ input.focus(); }, 80);
  }
  async function fetchStatus(){
    try{ var r=await fetch('/nidaan/api/support/status'); if(r.ok){ var d=await r.json(); supportOpen=!!d.open; } }catch(e){}
  }
  async function showGreeting(){
    if(greeted) return; greeted = true;
    await fetchStatus();
    bubble(GREET[lang]||GREET.en, 'ai');
    if(!supportOpen) bubble(OFFLINE[lang]||OFFLINE.en, 'ai');
    renderChips();
  }
  function leadDoneTicket(){ try{ return localStorage.getItem(LEADKEY); }catch(e){ return null; } }
  function renderChips(){
    var chipList = (CHIPS[lang]||CHIPS.en).map(function(t){ return {label:t, action:'send'}; });
    if(!supportOpen && !leadDoneTicket()) chipList.push({label:(LEADCHIP[lang]||LEADCHIP.en), action:'lead'});
    chipsBox.style.display='flex'; chipsBox.innerHTML='';
    chipList.forEach(function(c){
      var ch=document.createElement('div'); ch.className='nsw-chip'; ch.textContent=c.label;
      ch.onclick=function(){
        chipsBox.style.display='none'; chipsBox.innerHTML='';
        var human=/human|इंसान|insaan/i.test(c.label);
        if(c.action==='lead' || (human && !supportOpen && !leadDoneTicket())) showLeadForm();
        else send(c.label.replace(/^[^\wऀ-ॿ]+/, '').trim());
      };
      chipsBox.appendChild(ch);
    });
  }
  function showLeadForm(){
    var done=leadDoneTicket(); var L=LEADLABELS[lang]||LEADLABELS.en;
    if(done){ bubble(L.done+done+L.follow, 'ai'); return; }
    inBox.style.display='none';
    var f=document.createElement('div'); f.id='nswLeadForm';
    f.style.cssText='align-self:stretch;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);border-radius:12px;padding:.8rem;display:flex;flex-direction:column;gap:.5rem';
    var inS='background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14);border-radius:8px;padding:.55rem;color:#fff;font-size:.9rem';
    f.innerHTML='<input id="nswLeadName" placeholder="'+el(L.name)+'" style="'+inS+'">'
      +'<input id="nswLeadContact" placeholder="'+el(L.contact)+'" style="'+inS+'">'
      +'<textarea id="nswLeadMsg" rows="2" placeholder="'+el(L.msg)+'" style="'+inS+';font-family:inherit;resize:none"></textarea>'
      +'<button id="nswLeadSubmit" style="background:#06b6d4;border:none;border-radius:8px;color:#fff;padding:.55rem;font-weight:700;cursor:pointer">'+el(L.submit)+'</button>'
      +'<div id="nswLeadErr" style="color:#f87171;font-size:.78rem"></div>';
    msgs.appendChild(f); scroll();
    f.querySelector('#nswLeadSubmit').onclick=submitLead;
  }
  async function submitLead(){
    var name=(document.getElementById('nswLeadName').value||'').trim();
    var contact=(document.getElementById('nswLeadContact').value||'').trim();
    var m=(document.getElementById('nswLeadMsg').value||'').trim();
    var errEl=document.getElementById('nswLeadErr');
    if(name.length<1){ errEl.textContent='Please enter your name.'; return; }
    if(contact.length<3){ errEl.textContent='Please enter your email or mobile.'; return; }
    var btn=document.getElementById('nswLeadSubmit'); btn.disabled=true; errEl.textContent='';
    try{
      var body={ name:name, contact:contact, message:m, lang:lang };
      if(thread){ body.thread_id=thread.id; body.thread_key=thread.key; }
      var r=await fetch('/nidaan/api/support/lead',{ method:'POST', headers:authHeaders(), body:JSON.stringify(body) });
      var d=await r.json().catch(function(){return {};});
      if(!r.ok){ errEl.textContent=d.detail||'Could not submit. Please try again later.'; btn.disabled=false; return; }
      if(d.thread_key && d.ticket){ thread={id:d.ticket, key:d.thread_key}; localStorage.setItem(TKEY, JSON.stringify(thread)); setChatId(); }
      try{ localStorage.setItem(LEADKEY, String(d.ticket)); }catch(e){}
      var lf=document.getElementById('nswLeadForm'); if(lf) lf.remove();
      inBox.style.display='';
      var L=LEADLABELS[lang]||LEADLABELS.en;
      bubble(L.done+d.ticket+L.follow, 'ai');
    }catch(e){ errEl.textContent='Network issue — please try again.'; btn.disabled=false; }
  }

  async function loadHistory(){
    await fetchStatus();
    if(!thread){ if(!lang) showLangPicker(); else { showGreeting(); startPoll(); } return; }
    // existing conversation → pull full history
    try{
      var r = await fetch('/nidaan/api/support/thread?thread_id='+thread.id+'&thread_key='+encodeURIComponent(thread.key)+'&after_id=0');
      if(!r.ok){ thread=null; localStorage.removeItem(TKEY); if(!lang) showLangPicker(); else { showGreeting(); startPoll(); } return; }
      var d = await r.json();
      (d.messages||[]).forEach(function(m){ bubble(m.body, m.sender_type); if(m.msg_id>lastMsgId) lastMsgId=m.msg_id; });
      if(!(d.messages||[]).length) showGreeting();
      else if(!supportOpen && !leadDoneTicket()) renderChips();   // offer leave-details when offline
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

  // ── Language: always-available switcher (header 🌐) + intent detection ──
  var langBtn = panel.querySelector('#nswLangBtn'), langMenu = panel.querySelector('#nswLangMenu');
  updateLangLabel();   // reflect stored language on load
  langBtn.addEventListener('click', function(e){ e.stopPropagation(); langMenu.classList.toggle('open'); });
  document.addEventListener('click', function(){ langMenu.classList.remove('open'); });
  Array.prototype.forEach.call(langMenu.querySelectorAll('button'), function(b){
    b.addEventListener('click', function(e){ e.stopPropagation(); switchLang(b.getAttribute('data-l'), true); });
  });
  var LANGCONF = {
    en: "Done — I'll continue in English. 😊 How can I help?",
    hi: "हो गया — मैं अब हिंदी में बात करूँगा। 😊 मैं आपकी कैसे मदद करूँ?",
    hinglish: "Done — ab main Hinglish mein baat karunga. 😊 Bataiye, kaise help karun?"
  };
  var LANGASK = {
    en: "Sure! Which language would you prefer? You can also tap the हिंदी/English button at the top anytime.",
    hi: "ज़रूर! आप कौन-सी भाषा पसंद करेंगे? आप ऊपर हिंदी/English बटन पर भी टैप कर सकते हैं।",
    hinglish: "Sure! Aap kaunsi language prefer karenge? Upar हिंदी/English button par bhi tap kar sakte hain."
  };
  function switchLang(l, announce){
    if(!GREET[l]) l = 'en';
    lang = l; try{ localStorage.setItem(LKEY, l); }catch(e){}
    langMenu.classList.remove('open'); updateLangLabel();
    if(announce && panel.classList.contains('open')){ if(!greeted){ greeted = true; startPoll(); } bubble(LANGCONF[l] || LANGCONF.en, 'ai'); }
  }
  // Detect a short "please use language X" / "change language" request (not a real question).
  function langIntent(text){
    var t = (text || '').trim().toLowerCase();
    if(t.length > 45) return null;
    if(/hinglish/.test(t)) return { lang: 'hinglish' };
    if(/\b(english|angre[zj]i|inglish)\b/.test(t)) return { lang: 'en' };
    if(/(हिंदी|हिन्दी|\bhindi\b)/.test(t)) return { lang: 'hi' };
    if(/(change|switch|badl|बदल).*(lang|bhasha|भाषा)|(lang|bhasha|भाषा).*(change|switch|badl|बदल)/.test(t)) return { menu: true };
    return null;
  }

  input.addEventListener('input', function(){ input.style.height='auto'; input.style.height=Math.min(input.scrollHeight,90)+'px'; });
  input.addEventListener('keydown', function(e){ if(e.key==='Enter'&&!e.shiftKey){ e.preventDefault(); send(); } });
  sendBtn.addEventListener('click', function(){ send(); });

  function showLangChips(){
    chipsBox.style.display='flex'; chipsBox.innerHTML='';
    [['en','English'],['hi','हिंदी'],['hinglish','Hinglish']].forEach(function(p){
      var ch=document.createElement('div'); ch.className='nsw-chip'; ch.textContent=p[1];
      ch.onclick=function(){ chipsBox.style.display='none'; chipsBox.innerHTML=''; switchLang(p[0], true); };
      chipsBox.appendChild(ch);
    });
  }
  async function send(preset){
    var text = (preset!=null?preset:(input.value||'')).trim();
    if(!text || busy) return;
    // Understand a language request like a human — switch + confirm, no AI round-trip.
    var li = langIntent(text);
    if(li){
      bubble(text, 'customer');
      if(preset==null){ input.value=''; input.style.height='auto'; }
      if(chipsBox.style.display!=='none'){ chipsBox.style.display='none'; chipsBox.innerHTML=''; }
      if(li.menu){ bubble(LANGASK[lang] || LANGASK.en, 'ai'); showLangChips(); }
      else { switchLang(li.lang, true); }
      return;
    }
    busy=true; sendBtn.disabled=true;
    if(chipsBox.style.display!=='none'){ chipsBox.style.display='none'; chipsBox.innerHTML=''; }
    var optimistic=document.createElement('div'); optimistic.className='nsw-b me'; optimistic.innerHTML=el(text); msgs.appendChild(optimistic); scroll();
    if(preset==null){ input.value=''; input.style.height='auto'; }
    var typing=document.createElement('div'); typing.className='nsw-typing'; typing.textContent='…'; msgs.appendChild(typing); scroll();
    try{
      var body={ message:text, lang:lang };
      if(thread){ body.thread_id=thread.id; body.thread_key=thread.key; }
      var r = await fetch('/nidaan/api/support/message', { method:'POST', headers:authHeaders(), body:JSON.stringify(body) });
      typing.remove();
      var d = await r.json().catch(function(){ return {}; });
      if(!r.ok){ bubble(d.detail||'Sorry, something went wrong. Please try again.', 'ai'); busy=false; sendBtn.disabled=false; return; }
      if(d.thread_id && d.thread_key){ thread={ id:d.thread_id, key:d.thread_key }; localStorage.setItem(TKEY, JSON.stringify(thread)); setChatId(); }
      optimistic.remove();                 // replace optimistic bubble with server truth
      busy=false;                          // allow sync to run
      await syncMessages();                // pulls the stored customer msg + AI reply (with ids)
      if(d.escalated) note('🔔 A team member will follow up during support hours (Mon–Fri, 10am–6pm IST).');
      startPoll();
    }catch(e){ typing.remove(); bubble('Network issue — please try again.', 'ai'); }
    busy=false; sendBtn.disabled=false; if(input.offsetParent) input.focus();
  }

  // Deep-link reopen: an email nudge links to /?nchat=<id>&k=<key> → reopen the SAME conversation.
  try{
    var _q = new URLSearchParams(location.search);
    var _nc = _q.get('nchat'), _nk = _q.get('k');
    if(_nc && _nk && /^\d+$/.test(_nc)){
      thread = { id: parseInt(_nc, 10), key: _nk };
      try{ localStorage.setItem(TKEY, JSON.stringify(thread)); }catch(e){}
      // strip the key from the address bar / history
      try{ _q.delete('nchat'); _q.delete('k'); history.replaceState(null, '', location.pathname + (_q.toString()?('?'+_q.toString()):'') + location.hash); }catch(e){}
      setTimeout(function(){ openPanel(); }, 500);
    }
  }catch(e){}
})();
