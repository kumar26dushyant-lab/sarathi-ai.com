/* Sarathi-AI.com — homepage AI guide widget (self-contained, mobile-first, sales-aware).
   Anonymous product/pricing Q&A → /api/guide/ask. No account data. Nudges the free trial. */
(function () {
  if (window.__sarathiGuideLoaded) return;
  window.__sarathiGuideLoaded = true;

  var TEAL = '#0d9488', TEAL2 = '#0f766e', INK = '#0f172a';
  var history = [];        // [{role:'user'|'bot', text}]
  var busy = false, opened = false;

  var css = ''
    + '.sg-btn{position:fixed;right:18px;bottom:18px;z-index:2147483000;display:flex;align-items:center;gap:.5rem;'
    + 'background:' + TEAL + ';color:#fff;border:none;border-radius:999px;padding:12px 18px;font-weight:700;font-size:15px;'
    + 'box-shadow:0 8px 24px rgba(13,148,136,.4);cursor:pointer;font-family:inherit}'
    + '.sg-btn:hover{background:' + TEAL2 + '}'
    + '.sg-btn .sg-ico{font-size:18px;line-height:1}'
    + '.sg-panel{position:fixed;right:18px;bottom:18px;z-index:2147483000;width:370px;max-width:calc(100vw - 24px);'
    + 'height:560px;max-height:calc(100vh - 32px);background:#fff;border-radius:18px;box-shadow:0 18px 50px rgba(0,0,0,.28);'
    + 'display:none;flex-direction:column;overflow:hidden;font-family:inherit}'
    + '.sg-panel.open{display:flex}'
    + '.sg-hdr{background:linear-gradient(135deg,' + TEAL + ',' + TEAL2 + ');color:#fff;padding:14px 16px;display:flex;align-items:center;gap:10px}'
    + '.sg-hdr .sg-av{width:34px;height:34px;border-radius:50%;background:rgba(255,255,255,.2);display:flex;align-items:center;justify-content:center;font-size:18px}'
    + '.sg-hdr h4{margin:0;font-size:15px;font-weight:800}'
    + '.sg-hdr .sg-sub{font-size:11.5px;opacity:.9;margin-top:1px}'
    + '.sg-x{margin-left:auto;background:none;border:none;color:#fff;font-size:22px;cursor:pointer;line-height:1;opacity:.9}'
    + '.sg-body{flex:1;overflow-y:auto;padding:14px;background:#f8fafc;display:flex;flex-direction:column;gap:10px}'
    + '.sg-msg{max-width:82%;padding:9px 12px;border-radius:14px;font-size:14px;line-height:1.5;white-space:pre-wrap;word-wrap:break-word}'
    + '.sg-bot{align-self:flex-start;background:#fff;color:' + INK + ';border:1px solid #e2e8f0;border-bottom-left-radius:4px}'
    + '.sg-user{align-self:flex-end;background:' + TEAL + ';color:#fff;border-bottom-right-radius:4px}'
    + '.sg-cta{align-self:flex-start;display:inline-block;margin-top:-2px;background:#f59e0b;color:#111;text-decoration:none;'
    + 'font-weight:700;font-size:13.5px;padding:9px 16px;border-radius:10px}'
    + '.sg-cta.human{background:#fff;color:' + TEAL2 + ';border:1.5px solid ' + TEAL + '}'
    + '.sg-typing{align-self:flex-start;color:#64748b;font-size:13px;padding:4px 6px}'
    + '.sg-foot{border-top:1px solid #e2e8f0;padding:10px;display:flex;gap:8px;background:#fff}'
    + '.sg-inp{flex:1;border:1px solid #cbd5e1;border-radius:10px;padding:10px 12px;font-size:14px;font-family:inherit;outline:none}'
    + '.sg-inp:focus{border-color:' + TEAL + '}'
    + '.sg-send{background:' + TEAL + ';color:#fff;border:none;border-radius:10px;padding:0 16px;font-weight:700;cursor:pointer;font-size:14px}'
    + '.sg-send:disabled{opacity:.5;cursor:default}'
    + '.sg-note{font-size:10.5px;color:#94a3b8;text-align:center;padding:0 10px 8px;background:#fff}'
    + '@media(max-width:480px){.sg-panel{right:0;bottom:0;width:100vw;max-width:100vw;height:88vh;max-height:88vh;border-radius:16px 16px 0 0}'
    + '.sg-btn{right:14px;bottom:14px;padding:11px 15px;font-size:14px}}';

  var style = document.createElement('style'); style.textContent = css; document.head.appendChild(style);

  var btn = document.createElement('button');
  btn.className = 'sg-btn'; btn.type = 'button';
  btn.innerHTML = '<span class="sg-ico">💬</span><span>Ask Sarathi</span>';
  document.body.appendChild(btn);

  var panel = document.createElement('div');
  panel.className = 'sg-panel';
  panel.innerHTML =
      '<div class="sg-hdr"><div class="sg-av">🤖</div><div><h4>Sarathi Assistant</h4>'
    + '<div class="sg-sub">Ask about pricing, features & free trial</div></div>'
    + '<button class="sg-x" aria-label="Close">×</button></div>'
    + '<div class="sg-body" id="sgBody"></div>'
    + '<div class="sg-foot"><input class="sg-inp" id="sgInp" type="text" autocomplete="off" '
    + 'placeholder="Type your question…" maxlength="1000"><button class="sg-send" id="sgSend">Send</button></div>'
    + '<div class="sg-note">AI assistant · general info only · not account-specific</div>';
  document.body.appendChild(panel);

  var body = panel.querySelector('#sgBody');
  var inp = panel.querySelector('#sgInp');
  var sendBtn = panel.querySelector('#sgSend');

  function scrollDown(){ body.scrollTop = body.scrollHeight; }

  function addMsg(role, text){
    var d = document.createElement('div');
    d.className = 'sg-msg ' + (role === 'user' ? 'sg-user' : 'sg-bot');
    d.textContent = text;
    body.appendChild(d); scrollDown();
    return d;
  }
  function addCta(kind){
    var a = document.createElement('a');
    a.className = 'sg-cta' + (kind === 'human' ? ' human' : '');
    if (kind === 'human'){ a.textContent = '💬 Talk to our team'; a.href = '/support'; }
    else { a.textContent = '🎉 Start Free Trial'; a.href = '/#pricing'; }
    body.appendChild(a); scrollDown();
  }

  function greet(){
    if (history.length) return;
    addMsg('bot', "Namaste! 👋 I'm Sarathi's assistant. Ask me anything about Sarathi-AI — pricing, features, the Telegram voice CRM, or how the free trial works.");
  }

  function openPanel(){
    panel.classList.add('open'); btn.style.display = 'none'; opened = true;
    greet(); setTimeout(function(){ inp.focus(); }, 100);
  }
  function closePanel(){ panel.classList.remove('open'); btn.style.display = ''; }

  btn.addEventListener('click', openPanel);
  panel.querySelector('.sg-x').addEventListener('click', closePanel);

  async function send(){
    var msg = (inp.value || '').trim();
    if (!msg || busy) return;
    inp.value = '';
    addMsg('user', msg);
    history.push({ role: 'user', text: msg });
    busy = true; sendBtn.disabled = true;
    var typing = document.createElement('div');
    typing.className = 'sg-typing'; typing.textContent = 'Sarathi is typing…';
    body.appendChild(typing); scrollDown();
    // Stable per-visitor id (invisible) so the team reads the chat as ONE thread in Support.
    // A gap of > 30 min starts a fresh session — a new visit becomes a new conversation card.
    var _sk = '', _seen = [];
    try {
      var _now = Date.now(), _ts = parseInt(localStorage.getItem('sg_sess_ts') || '0', 10);
      _sk = localStorage.getItem('sg_sess') || '';
      if (!_sk || !_ts || (_now - _ts) > 1800000) { _sk = 'r' + _now.toString(36) + Math.random().toString(36).slice(2, 8); localStorage.setItem('sg_sess', _sk); }
      localStorage.setItem('sg_sess_ts', String(_now));
      try { _seen = JSON.parse(localStorage.getItem('sg_seen_stories') || '[]') || []; } catch (e) { _seen = []; }
    } catch (e) {}
    try {
      var res = await fetch('/api/guide/ask', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg, history: history.slice(-8), lang: '', session_key: _sk, seen_stories: _seen })
      });
      var data = await res.json();
      // Remember any example we were told, so the same one is never repeated to this visitor.
      try { if (data && data.story_id) { if (_seen.indexOf(data.story_id) < 0) _seen.push(data.story_id); localStorage.setItem('sg_seen_stories', JSON.stringify(_seen.slice(-40))); } } catch (e) {}
      typing.remove();
      var ans = (data && data.answer) || "Sorry, I couldn't answer that. Please try again.";
      addMsg('bot', ans);
      history.push({ role: 'bot', text: ans });
      if (data && (data.cta === 'trial')) addCta('trial');
      else if (data && (data.cta === 'human' || data.escalate)) addCta('human');
    } catch (e) {
      typing.remove();
      addMsg('bot', "I'm having trouble connecting. You can start a free trial from the homepage, or reach us at /support.");
      addCta('human');
    }
    busy = false; sendBtn.disabled = false; inp.focus();
  }

  sendBtn.addEventListener('click', send);
  inp.addEventListener('keydown', function(e){ if (e.key === 'Enter') { e.preventDefault(); send(); } });
})();
