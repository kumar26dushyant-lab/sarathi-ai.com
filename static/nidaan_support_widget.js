/* Nidaan Partner — AI support chat widget (self-contained, mobile-first).
   Injects a floating button + chat panel; talks to /nidaan/api/support/message.
   Conversation persists via thread_id + thread_key in localStorage. */
(function () {
  if (window.__nidaanSupportLoaded) return;
  window.__nidaanSupportLoaded = true;

  var TKEY = 'nidaan_support_thread';
  var thread = null;
  try { thread = JSON.parse(localStorage.getItem(TKEY) || 'null'); } catch (e) { thread = null; }

  var css = ''
    + '.nsw-btn{position:fixed;right:18px;bottom:18px;z-index:99998;width:58px;height:58px;border-radius:50%;'
    + 'border:none;cursor:pointer;background:linear-gradient(135deg,#06b6d4,#0891b2);color:#fff;font-size:26px;'
    + 'box-shadow:0 6px 20px rgba(6,182,212,.45);display:flex;align-items:center;justify-content:center;transition:transform .15s}'
    + '.nsw-btn:active{transform:scale(.92)}'
    + '.nsw-panel{position:fixed;right:18px;bottom:86px;z-index:99999;width:360px;max-width:calc(100vw - 24px);'
    + 'height:520px;max-height:calc(100vh - 110px);background:#0a1628;border:1px solid rgba(255,255,255,.12);'
    + 'border-radius:16px;display:none;flex-direction:column;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,.5);'
    + 'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}'
    + '.nsw-panel.open{display:flex}'
    + '.nsw-hdr{background:linear-gradient(135deg,#06b6d4,#0891b2);color:#fff;padding:.85rem 1rem}'
    + '.nsw-hdr h4{margin:0;font-size:1rem;font-weight:800}'
    + '.nsw-hdr p{margin:.15rem 0 0;font-size:.72rem;opacity:.9}'
    + '.nsw-hdr .nsw-x{position:absolute;top:.7rem;right:.8rem;background:none;border:none;color:#fff;font-size:1.3rem;cursor:pointer;line-height:1}'
    + '.nsw-msgs{flex:1;overflow-y:auto;padding:1rem;display:flex;flex-direction:column;gap:.6rem;background:#0a1628}'
    + '.nsw-b{max-width:82%;padding:.6rem .8rem;border-radius:14px;font-size:.9rem;line-height:1.45;white-space:pre-wrap;word-wrap:break-word}'
    + '.nsw-b.ai{align-self:flex-start;background:rgba(255,255,255,.07);color:#e2e8f0;border-bottom-left-radius:4px}'
    + '.nsw-b.me{align-self:flex-end;background:linear-gradient(135deg,#06b6d4,#0891b2);color:#fff;border-bottom-right-radius:4px}'
    + '.nsw-note{align-self:center;font-size:.72rem;color:#fbbf24;text-align:center;padding:.2rem .5rem}'
    + '.nsw-typing{align-self:flex-start;color:rgba(255,255,255,.4);font-size:.8rem;font-style:italic}'
    + '.nsw-in{display:flex;gap:.5rem;padding:.7rem;border-top:1px solid rgba(255,255,255,.1);background:#0a1628}'
    + '.nsw-in textarea{flex:1;resize:none;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14);'
    + 'border-radius:10px;padding:.6rem;color:#fff;font-size:.9rem;font-family:inherit;max-height:90px}'
    + '.nsw-in textarea:focus{outline:none;border-color:#22d3ee}'
    + '.nsw-in button{background:#06b6d4;border:none;border-radius:10px;color:#fff;padding:0 1rem;font-weight:700;cursor:pointer;font-size:1.1rem}'
    + '.nsw-in button:disabled{opacity:.5;cursor:default}'
    + '@media(max-width:480px){.nsw-panel{right:8px;bottom:78px;height:calc(100vh - 96px)}}';

  var style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  var btn = document.createElement('button');
  btn.className = 'nsw-btn';
  btn.setAttribute('aria-label', 'Chat with us');
  btn.innerHTML = '💬';
  document.body.appendChild(btn);

  var panel = document.createElement('div');
  panel.className = 'nsw-panel';
  panel.innerHTML =
    '<div class="nsw-hdr" style="position:relative">'
    + '<h4>Chat with Nidaan Partner</h4>'
    + '<p>AI assistant · human team Mon–Fri, 10am–6pm IST</p>'
    + '<button class="nsw-x" aria-label="Close">×</button></div>'
    + '<div class="nsw-msgs" id="nswMsgs"></div>'
    + '<div class="nsw-in"><textarea id="nswInput" rows="1" placeholder="Type your question…"></textarea>'
    + '<button id="nswSend">➤</button></div>';
  document.body.appendChild(panel);

  var msgs = panel.querySelector('#nswMsgs');
  var input = panel.querySelector('#nswInput');
  var sendBtn = panel.querySelector('#nswSend');
  var opened = false;

  function esc(s) { var d = document.createElement('div'); d.textContent = s == null ? '' : s; return d.innerHTML; }
  function scroll() { msgs.scrollTop = msgs.scrollHeight; }

  function bubble(text, who) {
    var el = document.createElement('div');
    el.className = 'nsw-b ' + (who === 'customer' ? 'me' : 'ai');
    el.innerHTML = esc(text);
    msgs.appendChild(el); scroll();
  }
  function note(text) {
    var el = document.createElement('div'); el.className = 'nsw-note'; el.innerHTML = esc(text);
    msgs.appendChild(el); scroll();
  }

  async function loadHistory() {
    if (!thread) {
      bubble('Hi! 👋 I can help with questions about claim reviews, plans, and how Nidaan Partner works. What would you like to know?', 'ai');
      return;
    }
    try {
      var r = await fetch('/nidaan/api/support/thread?thread_id=' + thread.id + '&thread_key=' + encodeURIComponent(thread.key));
      if (!r.ok) { thread = null; localStorage.removeItem(TKEY); bubble('Hi again! How can I help?', 'ai'); return; }
      var d = await r.json();
      (d.messages || []).forEach(function (m) { if (m.sender_type !== 'staff') bubble(m.body, m.sender_type); else bubble(m.body, 'ai'); });
      if (!(d.messages || []).length) bubble('Hi again! How can I help?', 'ai');
    } catch (e) { bubble('Hi! How can I help?', 'ai'); }
  }

  function openPanel() {
    panel.classList.add('open');
    if (!opened) { opened = true; loadHistory(); }
    setTimeout(function () { input.focus(); }, 100);
  }
  function closePanel() { panel.classList.remove('open'); }

  btn.addEventListener('click', function () { panel.classList.contains('open') ? closePanel() : openPanel(); });
  panel.querySelector('.nsw-x').addEventListener('click', closePanel);

  input.addEventListener('input', function () { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 90) + 'px'; });
  input.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
  sendBtn.addEventListener('click', send);

  var busy = false;
  async function send() {
    var text = (input.value || '').trim();
    if (!text || busy) return;
    busy = true; sendBtn.disabled = true;
    bubble(text, 'customer');
    input.value = ''; input.style.height = 'auto';
    var typing = document.createElement('div'); typing.className = 'nsw-typing'; typing.textContent = 'typing…';
    msgs.appendChild(typing); scroll();
    try {
      var body = { message: text };
      if (thread) { body.thread_id = thread.id; body.thread_key = thread.key; }
      var r = await fetch('/nidaan/api/support/message', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
      });
      typing.remove();
      var d = await r.json().catch(function () { return {}; });
      if (!r.ok) { bubble(d.detail || 'Sorry, something went wrong. Please try again.', 'ai'); }
      else {
        if (d.thread_id && d.thread_key) { thread = { id: d.thread_id, key: d.thread_key }; localStorage.setItem(TKEY, JSON.stringify(thread)); }
        bubble(d.reply || 'Thanks for reaching out!', 'ai');
        if (d.escalated) note('🔔 A team member will follow up during support hours (Mon–Fri, 10am–6pm IST).');
      }
    } catch (e) { typing.remove(); bubble('Network issue — please try again.', 'ai'); }
    busy = false; sendBtn.disabled = false; input.focus();
  }
})();
