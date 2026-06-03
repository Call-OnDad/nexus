'use strict';

// localStorage items take priority — used by Playwright tests to override the Tailscale URL
const LOCAL_URL    = localStorage.getItem('__nexus_api__') || (window.NEXUS_CONFIG && window.NEXUS_CONFIG.localUrl)    || 'http://192.168.0.60:5000';
const EXTERNAL_URL = localStorage.getItem('__nexus_api__') || (window.NEXUS_CONFIG && window.NEXUS_CONFIG.externalUrl) || 'https://nexus.call-on.media';
let apiUrl = LOCAL_URL;

const IS_NATIVE = !!(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform());

async function resolveApiUrl() {
  for (const url of [LOCAL_URL, EXTERNAL_URL]) {
    try {
      const r = await fetch(`${url}/health`, { signal: AbortSignal.timeout(3000) });
      if (r.ok) { apiUrl = url; setDot('api-dot', true); return; }
    } catch (_) {}
  }
  apiUrl = EXTERNAL_URL;
  setDot('api-dot', false);
}

// ── Service metadata ───────────────────────────────────────────────────────
const SERVICES_META = {
  ha: {
    description: 'Home automation hub — controls lights, climate, presence detection, and integrates with all smart home devices across the property.',
    cards: [
      { label: 'ENDPOINT',  value: 'ha.call-on.media' },
      { label: 'PORT',      value: '8123' },
      { label: 'ROLE',      value: 'SMART HOME' },
      { label: 'CONTAINER', value: 'BARE METAL · .9' },
    ],
  },
  plex: {
    description: 'Personal media server streaming movies, TV shows, and music to all devices on the network — managed by Sonarr and Radarr.',
    cards: [
      { label: 'ENDPOINT',  value: 'watch.call-on.media' },
      { label: 'CT',        value: '101 · 192.168.0.34' },
      { label: 'ROLE',      value: 'MEDIA SERVER' },
      { label: 'BACKEND',   value: 'DOCKER' },
    ],
  },
  n8n: {
    description: 'Workflow automation engine — connects apps, schedules tasks, and orchestrates data pipelines across the homelab and external services.',
    cards: [
      { label: 'ENDPOINT',  value: '192.168.0.28:5678' },
      { label: 'CT',        value: '112 · 192.168.0.28' },
      { label: 'ROLE',      value: 'AUTOMATION' },
      { label: 'BACKEND',   value: 'DOCKER' },
    ],
  },
  prox: {
    description: 'Proxmox VE virtualisation platform — the core infrastructure layer hosting 15+ LXC containers and VMs powering the entire homelab.',
    cards: [
      { label: 'ENDPOINT',  value: '192.168.0.10:8006' },
      { label: 'ROLE',      value: 'HYPERVISOR' },
      { label: 'CONTAINERS', value: '15+' },
      { label: 'STORAGE',   value: 'ZFS' },
    ],
  },
  dns: {
    description: 'Pi-hole DNS resolver and network-wide ad blocker. Filters advertising and tracking domains for every device on the local network.',
    cards: [
      { label: 'ENDPOINT',  value: '192.168.0.3/admin' },
      { label: 'CT',        value: '105 · 192.168.0.3' },
      { label: 'ROLE',      value: 'DNS + ADBLOCK' },
      { label: 'TAILSCALE', value: '100.78.52.118' },
    ],
  },
  ai: {
    description: 'Open WebUI interface for local AI models via Ollama (llama3, phi4-mini) and cloud models. Speak to NEXUS directly to use AI without opening this.',
    cards: [
      { label: 'ENDPOINT',  value: 'chat.call-on.media' },
      { label: 'CT',        value: '113 · 192.168.0.45' },
      { label: 'MODELS',    value: 'LLAMA3 · PHI4' },
      { label: 'BACKEND',   value: 'DOCKER' },
    ],
  },
};

// ── Department metadata (Phase 3 mobile) ──────────────────────────────────
const DEPARTMENTS_META = {
  nexus: {
    icon: '🧠', accent: '#00d4ff',
    description: 'Central NEXUS brain — claude-haiku-4-5 with persistent memory, background cache pools, and tool access across all departments.',
    loader: 'loadDeptNexus',
  },
  infra: {
    icon: '🖥', accent: '#00ff88',
    description: 'Proxmox host + 11 LXC containers. Live CPU, RAM, load average, container state, and storage pools.',
    loader: 'loadDeptInfra',
  },
  marketing: {
    icon: '📣', accent: '#ff3399',
    description: 'Marketing department. Discord feed from #marketing — quick-send to agent for briefs, captions, SEO drafts.',
    loader: 'loadDeptDiscord', channel: 'marketing', agent: 'marketing',
  },
  business: {
    icon: '💼', accent: '#ffc800',
    description: 'Business & operations. Discord feed from #business — agent handles ops, finance flags, manager escalations.',
    loader: 'loadDeptDiscord', channel: 'business', agent: 'business',
  },
  community: {
    icon: '👥', accent: '#7c3aed',
    description: 'Call-on.dad and Call-on.mom community stats — users, topics, messages, contact form submissions.',
    loader: 'loadDeptCommunity',
  },
  security: {
    icon: '🛡', accent: '#ff4d4d',
    description: 'Security department. Discord feed from #security — CrowdSec events, fail2ban, suspicious activity.',
    loader: 'loadDeptDiscord', channel: 'security', agent: 'security',
  },
  email: {
    icon: '📧', accent: '#00b4ff',
    description: 'Unified inbox — Gmail + Yahoo, cached every 10 minutes.',
    loader: 'loadDeptEmail',
  },
};

// ── Prose parsers (Proxmox endpoints return narrative strings) ────────────
function parseCPU(t)  { const m=String(t).match(/CPU at ([\d.]+)%/); return m?parseFloat(m[1]):null; }
function parseRAM(t)  { const m=String(t).match(/RAM ([\d.]+) of ([\d.]+) gigabytes used \(([\d.]+)%\)/); return m?{used:parseFloat(m[1]),total:parseFloat(m[2]),pct:parseFloat(m[3])}:null; }
function parseLoad(t) { const m=String(t).match(/Load average ([\d.]+), ([\d.]+), ([\d.]+)/); return m?`${m[1]} / ${m[2]} / ${m[3]}`:'—'; }
function parseStorage(t) { const p=[],re=/([a-z0-9_-]+): ([\d.]+)% of ([\d.]+) gigabytes/gi; let m; while((m=re.exec(String(t)))!==null) p.push({name:m[1],pct:parseFloat(m[2]),gb:parseFloat(m[3])}); return p; }
function parseContainers(t) {
  const s=String(t), run=s.match(/(\d+) containers? running/), stop=s.match(/(\d+) stopped/), items=[];
  const rp=s.match(/running: (.+?)(?:\. \d+ stopped|\.$|$)/s), sp=s.match(/stopped: (.+?)\.?\s*$/s);
  if(rp) rp[1].split(',').map(x=>x.trim()).filter(Boolean).forEach(x=>items.push({name:x,up:true}));
  if(sp) sp[1].split(',').map(x=>x.trim()).filter(Boolean).forEach(x=>items.push({name:x,up:false}));
  return {running:run?parseInt(run[1]):0, stopped:stop?parseInt(stop[1]):0, items};
}
function barColor(p) { return p>=90?'#ff4d4d':p>=75?'#ffc800':'#00d4ff'; }
function escHtml(s)  { return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

async function deptApi(path) {
  const r = await fetch(apiUrl + path, { signal: AbortSignal.timeout(15000) });
  return r.json();
}

// ── State ──────────────────────────────────────────────────────────────────
let orbState      = 'idle';
let ttsEnabled    = true;
let currentAudio  = null;
let mediaRecorder = null;
let audioChunks   = [];
let isRecording   = false;
let chatOpen      = false;
let menuOpen      = false;
let wakeEnabled   = false;
let silenceTimer  = null;
let activeDetail  = null;   // currently open service detail id

// ── Desktop sidebar detection ─────────────────────────────────────────────
function isDesktop() { return window.innerWidth >= 800; }

// ── DOM ────────────────────────────────────────────────────────────────────
const $orbBtn      = document.getElementById('orb-btn');
const $orbStatus   = document.getElementById('orb-status');
const $chatPanel   = document.getElementById('chat-panel-mobile');
const $chatScroll  = document.getElementById('chat-scroll');
const $typingRow   = document.getElementById('typing-row');
const $micBtn      = document.getElementById('mic-btn');
const $textInput   = document.getElementById('text-input');
const $sendBtn     = document.getElementById('send-btn');
const $menuBtn     = document.getElementById('menu-btn');
const $ttsBtn      = document.getElementById('tts-btn');
const $clearBtn    = document.getElementById('clear-btn');
const $overlayBtn  = document.getElementById('overlay-btn');
const $wakeBtn     = document.getElementById('wake-btn');
const $dragHandle  = document.getElementById('drag-handle');
const $ctrlTray    = document.getElementById('ctrl-tray');
const $clock       = document.getElementById('clock');
const $sidebarClock = document.getElementById('sidebar-clock');
const $svcCards    = document.getElementById('svc-cards');

// Mobile fallback elements
const $chatScrollMobile  = document.getElementById('chat-scroll-mobile');
const $typingRowMobile   = document.getElementById('typing-row-mobile');
const $micBtnMobile      = document.getElementById('mic-btn-mobile');
const $textInputMobile   = document.getElementById('text-input-mobile');
const $sendBtnMobile     = document.getElementById('send-btn-mobile');
const $menuBtnMobile     = document.getElementById('menu-btn-mobile');
const $svcDetail   = document.getElementById('service-detail');
const $detailBack  = document.getElementById('detail-back');
const $detailIcon  = document.getElementById('detail-icon');
const $detailName  = document.getElementById('detail-name');
const $detailHdot  = document.getElementById('detail-hdot');
const $detailHtext = document.getElementById('detail-htext');
const $detailDesc  = document.getElementById('detail-desc');
const $detailGrid  = document.getElementById('detail-grid');
const $detailActs  = document.getElementById('detail-acts');
const $detailPanel = document.getElementById('detail-panel');

// ── Clock ──────────────────────────────────────────────────────────────────
function tickClock() {
  const t = new Date().toTimeString().slice(0, 5);
  if ($clock) $clock.textContent = t;
  if ($sidebarClock) $sidebarClock.textContent = t;
}
setInterval(tickClock, 10000);
tickClock();

// ── Status dots ────────────────────────────────────────────────────────────
function setDot(id, up) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle('offline', !up);
}

// ── Orb state ──────────────────────────────────────────────────────────────
const STATUS_TEXT = { idle:'READY', listening:'LISTENING', thinking:'THINKING', speaking:'SPEAKING' };
function setOrb(state) {
  orbState = state;
  if ($orbBtn)    $orbBtn.className = 'orb-btn' + (state !== 'idle' ? ' ' + state : '');
  if ($orbStatus) $orbStatus.textContent = STATUS_TEXT[state] || 'READY';
  if (state !== 'idle') openChat();
}

// ── Chat panel ─────────────────────────────────────────────────────────────
function openChat()   { chatOpen = true;  if ($chatPanel) $chatPanel.classList.add('open'); }
function closeChat()  { chatOpen = false; if ($chatPanel) $chatPanel.classList.remove('open'); }
function toggleChat() { chatOpen ? closeChat() : openChat(); }

// ── Controls tray ──────────────────────────────────────────────────────────
function openMenu()  {
  menuOpen = true;
  if ($ctrlTray) $ctrlTray.classList.add('open');
  if ($menuBtn)  $menuBtn.classList.add('active');
  closeChat();
  closeDetail();
}
function closeMenu() {
  menuOpen = false;
  if ($ctrlTray) $ctrlTray.classList.remove('open');
  if ($menuBtn)  $menuBtn.classList.remove('active');
}
function toggleMenu() { menuOpen ? closeMenu() : openMenu(); }

// ── Department detail (Phase 3 mobile) ────────────────────────────────────
async function openDeptDetail(bubble) {
  if (!$svcDetail) return;
  const deptId = bubble.dataset.dept;
  const meta   = DEPARTMENTS_META[deptId];
  if (!meta) return;
  const label  = bubble.dataset.label || deptId.toUpperCase();

  $detailPanel && $detailPanel.style.setProperty('--detail-accent', meta.accent);
  $svcDetail.style.setProperty('--detail-accent', meta.accent);
  if ($detailIcon) $detailIcon.textContent = meta.icon;
  if ($detailName) $detailName.textContent = label;
  if ($detailHdot) $detailHdot.className   = 'detail-hdot';
  if ($detailHtext) $detailHtext.textContent = 'LIVE';
  if ($detailDesc) $detailDesc.textContent = meta.description || '';
  if ($detailGrid) $detailGrid.innerHTML   = '<div class="dept-loading">Loading…</div>';
  if ($detailActs) $detailActs.innerHTML   = '';

  document.querySelectorAll('.bubble.selected').forEach(b => b.classList.remove('selected'));
  bubble.classList.add('selected');
  activeDetail = deptId;
  $svcDetail.setAttribute('aria-hidden', 'false');
  $svcDetail.classList.add('open');
  closeChat(); closeMenu();

  // Quick-action: ask NEXUS about this dept
  if ($detailActs) {
    const ask = document.createElement('button');
    ask.className = 'detail-act';
    ask.textContent = `ASK NEXUS ABOUT ${label}`;
    ask.addEventListener('click', () => {
      closeDetail();
      if ($textInput) $textInput.value = `Give me a ${deptId} status report.`;
      openChat();
      if ($textInput) $textInput.focus();
    });
    $detailActs.appendChild(ask);
  }

  const fn = window[meta.loader];
  if (typeof fn === 'function') {
    try { await fn(meta); } catch (e) {
      if ($detailGrid) $detailGrid.innerHTML = `<div class="dept-error">Load failed: ${escHtml(e.message)}</div>`;
    }
  }
}

// ── NEXUS dept renderer ────────────────────────────────────────────────────
async function loadDeptNexus() {
  const [health, host] = await Promise.all([
    deptApi('/health').catch(() => ({})),
    deptApi('/api/proxmox/host').catch(() => ({ data: '' })),
  ]);
  const cpu = parseCPU(host.data), ram = parseRAM(host.data), load = parseLoad(host.data);
  const cards = [
    { l: 'VERSION', v: health.version || '—' },
    { l: 'MEMORY',  v: (health.memory || 0) + ' msg' },
    { l: 'POOLS',   v: (health.cache_keys?.length || 0) + ' cached' },
    { l: 'HOST CPU', v: cpu != null ? cpu.toFixed(1) + '%' : '—' },
    { l: 'HOST RAM', v: ram ? `${ram.used}/${ram.total} GB` : '—' },
    { l: 'LOAD AVG', v: load },
  ];
  $detailGrid.innerHTML = cards.map(c =>
    `<div class="detail-card"><span class="detail-card-label">${c.l}</span><span class="detail-card-value">${escHtml(c.v)}</span></div>`
  ).join('');
}

// ── Infra dept renderer ───────────────────────────────────────────────────
async function loadDeptInfra() {
  const [hR, cR, sR] = await Promise.all([
    deptApi('/api/proxmox/host').catch(() => ({ data: '' })),
    deptApi('/api/proxmox/containers').catch(() => ({ data: '' })),
    deptApi('/api/proxmox/storage').catch(() => ({ data: '' })),
  ]);
  const cpu = parseCPU(hR.data), ram = parseRAM(hR.data), load = parseLoad(hR.data);
  const cts = parseContainers(cR.data), pools = parseStorage(sR.data);

  let html = '';
  // CPU + RAM cards with bars
  html += `<div class="dept-bar-card"><div class="dept-bar-top"><span class="detail-card-label">CPU</span><span class="detail-card-value">${cpu!=null?cpu.toFixed(1)+'%':'—'}</span></div><div class="dept-bar-wrap"><div class="dept-bar" style="width:${cpu||0}%;background:${barColor(cpu||0)}"></div></div></div>`;
  html += `<div class="dept-bar-card"><div class="dept-bar-top"><span class="detail-card-label">RAM</span><span class="detail-card-value">${ram?ram.used+'/'+ram.total+' GB':'—'}</span></div><div class="dept-bar-wrap"><div class="dept-bar" style="width:${ram?ram.pct:0}%;background:${barColor(ram?ram.pct:0)}"></div></div></div>`;
  html += `<div class="detail-card"><span class="detail-card-label">LOAD AVG</span><span class="detail-card-value">${load}</span></div>`;
  html += `<div class="detail-card"><span class="detail-card-label">CONTAINERS</span><span class="detail-card-value">${cts.running} up · ${cts.stopped} down</span></div>`;
  // Container chip grid spanning full width
  html += `<div class="dept-ct-grid">${cts.items.map(c => `<span class="dept-ct-chip ${c.up?'up':'down'}">${escHtml(c.name)}</span>`).join('')}</div>`;
  // Storage pools spanning full width
  html += '<div class="dept-storage">' + pools.map(p =>
    `<div class="stor-row"><div class="stor-name">${escHtml(p.name)}</div><div class="stor-bar-wrap"><div class="stor-bar" style="width:${p.pct}%;background:${barColor(p.pct)}"></div></div><div class="stor-stat">${p.pct}% · ${p.gb} GB</div></div>`
  ).join('') + '</div>';
  $detailGrid.innerHTML = html;
}

// ── Discord-backed dept renderer (marketing/business/security) ────────────
async function loadDeptDiscord(meta) {
  const channel = meta.channel, agent = meta.agent;
  const d = await deptApi('/api/discord/channel/' + channel).catch(e => ({ error: e.message }));
  let html = '';
  if (d.error) {
    html += `<div class="dept-error">Discord: ${escHtml(d.error)}</div>`;
  } else {
    const msgs = (d.messages || []).slice(0, 10);
    if (!msgs.length) html += '<div class="dept-empty">No messages.</div>';
    else html += '<div class="dept-feed">' + msgs.map(m =>
      `<div class="disc-msg"><span class="disc-author">${escHtml(m.author)}</span><span class="disc-ts">${escHtml(m.ts)}</span><div class="disc-body">${escHtml((m.content||'').slice(0,260))}</div></div>`
    ).join('') + '</div>';
  }
  // Quick-send row
  html += `<div class="dept-send"><input type="text" id="dept-send-input" class="dept-send-input" placeholder="Message #${escHtml(channel)} via ${escHtml(agent)} agent..." autocomplete="off"><button type="button" id="dept-send-btn" class="dept-send-btn">SEND</button></div>`;
  $detailGrid.innerHTML = html;
  const $in = document.getElementById('dept-send-input');
  const $btn = document.getElementById('dept-send-btn');
  const send = async () => {
    const text = ($in.value || '').trim(); if (!text) return;
    $btn.disabled = true; $btn.textContent = '...';
    try {
      const r = await fetch(apiUrl + '/api/agent/' + agent, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
        signal: AbortSignal.timeout(60000),
      });
      const j = await r.json();
      addMsg('user', text);
      addMsg('assistant', j.reply || j.error || '(no reply)');
      $in.value = ''; closeDetail(); openChat();
    } catch (e) {
      $btn.textContent = 'ERROR';
    } finally { $btn.disabled = false; if ($btn.textContent === '...') $btn.textContent = 'SEND'; }
  };
  if ($btn) $btn.addEventListener('click', send);
  if ($in)  $in.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); send(); } });
}

// ── Community dept renderer ───────────────────────────────────────────────
async function loadDeptCommunity() {
  const d = await deptApi('/api/community/stats');
  const rows = [];
  for (const site of ['dad', 'mom']) {
    const s = d[site] || {};
    rows.push(`<div class="dept-section-title">call-on.${site}</div>`);
    const cards = Object.entries(s).map(([k, v]) =>
      `<div class="detail-card"><span class="detail-card-label">${escHtml(k.toUpperCase())}</span><span class="detail-card-value">${escHtml(v)}</span></div>`
    ).join('');
    rows.push(`<div class="dept-substats">${cards}</div>`);
  }
  $detailGrid.innerHTML = rows.join('');
}

// ── Email dept renderer ───────────────────────────────────────────────────
async function loadDeptEmail() {
  $detailGrid.innerHTML = '<div class="dept-loading">Fetching inbox (may take 30s)…</div>';
  const d = await deptApi('/api/email/inbox').catch(e => ({ error: e.message }));
  if (d.error) { $detailGrid.innerHTML = `<div class="dept-error">${escHtml(d.error)}</div>`; return; }
  const renderList = msgs => (msgs || []).slice(0, 10).map(m =>
    `<div class="mail-row"><span class="mail-from">${escHtml(m.from||'')}</span><span class="mail-subj">${escHtml(m.subject||'(no subject)')}</span><span class="mail-prev">${escHtml((m.preview||'').slice(0,140))}</span></div>`
  ).join('') || '<div class="dept-empty">Empty.</div>';
  $detailGrid.innerHTML = `<div class="dept-section-title">Gmail</div><div class="dept-mail-list">${renderList(d.gmail)}</div><div class="dept-section-title">Yahoo</div><div class="dept-mail-list">${renderList(d.yahoo)}</div>`;
}

// ── Service detail page (legacy desktop bubbles) ──────────────────────────
function openDetail(bubble) {
  if (bubble.dataset.dept) return openDeptDetail(bubble);
  if (!$svcDetail) return;
  const detailId = bubble.dataset.detail;
  const label    = bubble.dataset.label || 'SERVICE';
  const url      = bubble.dataset.url   || '#';
  const meta     = SERVICES_META[detailId] || {};
  const accent   = getComputedStyle(bubble).getPropertyValue('--accent').trim() || 'var(--cyan)';

  // Accent colour on panel
  $detailPanel && $detailPanel.style.setProperty('--detail-accent', accent);
  $svcDetail.style.setProperty('--detail-accent', accent);

  // Header
  if ($detailIcon) $detailIcon.textContent = bubble.querySelector('.bubble-icon')?.textContent || '⚙';
  if ($detailName) $detailName.textContent  = label;

  // Status from bubble's current class
  const statusClass = bubble.classList.contains('up') ? 'up' : bubble.classList.contains('down') ? 'down' : '';
  if ($detailHdot)  { $detailHdot.className  = 'detail-hdot' + (statusClass ? ' ' + statusClass : ''); }
  if ($detailHtext) $detailHtext.textContent  = statusClass === 'up' ? 'ONLINE' : statusClass === 'down' ? 'OFFLINE' : 'CHECKING';

  // Description
  if ($detailDesc) $detailDesc.textContent = meta.description || '';

  // Info cards
  if ($detailGrid) {
    $detailGrid.innerHTML = '';
    (meta.cards || []).forEach(({ label: l, value: v }) => {
      const card = document.createElement('div');
      card.className = 'detail-card';
      card.innerHTML = `<span class="detail-card-label">${l}</span><span class="detail-card-value">${v}</span>`;
      $detailGrid.appendChild(card);
    });
  }

  // Action buttons
  if ($detailActs) {
    $detailActs.innerHTML = '';
    // Open service
    const openLink = document.createElement('a');
    openLink.className = 'detail-act primary';
    openLink.href = url; openLink.target = '_blank'; openLink.rel = 'noopener noreferrer';
    openLink.textContent = `OPEN ${label.split(' ')[0]}`;
    $detailActs.appendChild(openLink);
    // Ask NEXUS
    const askBtn = document.createElement('button');
    askBtn.className = 'detail-act';
    askBtn.textContent = `ASK NEXUS ABOUT ${label.split(' ')[0]}`;
    askBtn.addEventListener('click', () => {
      closeDetail();
      if ($textInput) $textInput.value = `Tell me about ${label.toLowerCase()} status`;
      openChat();
      if ($textInput) $textInput.focus();
    });
    $detailActs.appendChild(askBtn);
  }

  // Mark bubble selected
  document.querySelectorAll('.bubble.selected').forEach(b => b.classList.remove('selected'));
  bubble.classList.add('selected');

  activeDetail = detailId;
  $svcDetail.removeAttribute('aria-hidden');
  $svcDetail.setAttribute('aria-hidden', 'false');
  $svcDetail.classList.add('open');

  closeChat(); closeMenu();
}

function closeDetail() {
  if (!$svcDetail) return;
  $svcDetail.classList.remove('open');
  $svcDetail.setAttribute('aria-hidden', 'true');
  document.querySelectorAll('.bubble.selected').forEach(b => b.classList.remove('selected'));
  if ($svcCards) $svcCards.querySelectorAll('.svc-card').forEach(c => c.classList.remove('active'));
  activeDetail = null;
}

// ── Messages ───────────────────────────────────────────────────────────────
function addMsg(role, text) {
  // Add to both desktop sidebar chat and mobile chat
  const targets = [$chatScroll, $chatScrollMobile].filter(Boolean);
  if (!targets.length) return;
  for (const scroll of targets) {
    const wrap   = document.createElement('div');
    wrap.className = `msg ${role}`;
    const who    = document.createElement('span');
    who.className  = 'msg-who';
    who.textContent = role === 'user' ? 'YOU' : 'NEXUS';
    const bubble = document.createElement('span');
    bubble.className  = 'msg-text';
    bubble.textContent = text;
    wrap.append(who, bubble);
    scroll.appendChild(wrap);
    requestAnimationFrame(() => { scroll.scrollTop = scroll.scrollHeight; });
  }
  openChat();
}

// ── Phone commands ─────────────────────────────────────────────────────────
function parseAndExec(reply) {
  const callM = reply.match(/<<CALL:([^>]+)>>/);
  const smsM  = reply.match(/<<SMS:([^:>]+):([^>]+)>>/);
  const openM = reply.match(/<<OPEN:([^>]+)>>/);
  const urlM  = reply.match(/<<URL:([^>]+)>>/);
  try {
    if (callM) window.location.href = `tel:${callM[1].replace(/\s/g, '')}`;
    if (smsM)  window.location.href = `sms:${smsM[1]}${smsM[2] ? `?body=${encodeURIComponent(smsM[2])}` : ''}`;
    if (openM) window.open(openM[1], '_blank', 'noopener');
    if (urlM)  window.open(urlM[1],  '_blank', 'noopener');
  } catch (_) {}
}
function cleanReply(t) {
  return t.replace(/<<(CALL|SMS|OPEN|URL):[^>]+>>/g, '').trim();
}

// ── Audio ──────────────────────────────────────────────────────────────────
let audioCtx = null;
function unlockAudio() {
  if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  if (audioCtx.state === 'suspended') audioCtx.resume();
}
function stopPlayback() {
  if (currentAudio) { currentAudio.pause(); currentAudio.src = ''; currentAudio = null; }
}
function speak(b64) {
  if (!ttsEnabled || !b64) return;
  stopPlayback(); unlockAudio();
  try {
    const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    const url   = URL.createObjectURL(new Blob([bytes], { type: 'audio/mpeg' }));
    currentAudio = new Audio(url);
    currentAudio.onended = () => { URL.revokeObjectURL(url); currentAudio = null; setOrb('idle'); };
    currentAudio.onerror = () => { currentAudio = null; setOrb('idle'); };
    currentAudio.play().catch(() => setOrb('idle'));
  } catch (_) { setOrb('idle'); }
}

// ── Haptics ────────────────────────────────────────────────────────────────
function haptic() {
  try {
    if (IS_NATIVE) {
      const H = window.Capacitor.Plugins && window.Capacitor.Plugins.Haptics;
      if (H) { H.impact({ style: 'MEDIUM' }); return; }
    }
  } catch (_) {}
  if (navigator.vibrate) navigator.vibrate(40);
}

// ── Send ───────────────────────────────────────────────────────────────────
async function sendMessage(text) {
  text = text.trim();
  if (!text || orbState === 'thinking') return;
  addMsg('user', text);
  if ($textInput) $textInput.value = '';
  if ($textInputMobile) $textInputMobile.value = '';
  setOrb('thinking');
  if ($typingRow) $typingRow.classList.add('visible');
  if ($typingRowMobile) $typingRowMobile.classList.add('visible');
  if ($sendBtn)   $sendBtn.disabled = true;
  if ($sendBtnMobile) $sendBtnMobile.disabled = true;
  try {
    const r = await fetch(`${apiUrl}/api/ask`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ message: text }),
      signal: AbortSignal.timeout(45000),
    });
    if (!r.ok) throw new Error(`API ${r.status}`);
    const data = await r.json();
    if (data.error) throw new Error(data.error);
    const reply = data.reply || '';
    addMsg('assistant', cleanReply(reply));
    parseAndExec(reply);
    if (data.audio) { setOrb('speaking'); speak(data.audio); }
    else setOrb('idle');
  } catch (e) {
    addMsg('assistant', `Error: ${e.message}`);
    setOrb('idle');
  } finally {
    if ($typingRow) $typingRow.classList.remove('visible');
    if ($typingRowMobile) $typingRowMobile.classList.remove('visible');
    if ($sendBtn)   $sendBtn.disabled = false;
    if ($sendBtnMobile) $sendBtnMobile.disabled = false;
  }
}

// ── MediaRecorder voice ────────────────────────────────────────────────────
async function requestMicPermission() {
  if (IS_NATIVE) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach(t => t.stop());
      return true;
    } catch (_) { return false; }
  }
  return true;
}

async function startMediaRec() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  audioChunks = [];
  const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus'
             : MediaRecorder.isTypeSupported('audio/webm')              ? 'audio/webm'
             : MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')   ? 'audio/ogg;codecs=opus'
             : '';
  const opts = mime ? { mimeType: mime } : {};
  mediaRecorder = new MediaRecorder(stream, opts);
  mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunks.push(e.data); };
  mediaRecorder.start(250);
  isRecording = true;
  setOrb('listening');
  if ($micBtn) { $micBtn.classList.add('recording'); $micBtn.textContent = '⏹'; }
  haptic();
  silenceTimer = setTimeout(() => { if (isRecording) stopMediaRec(); }, 15000);
}

async function stopMediaRec() {
  clearTimeout(silenceTimer);
  if (!mediaRecorder) return;
  return new Promise(resolve => {
    mediaRecorder.onstop = async () => {
      const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
      mediaRecorder.stream.getTracks().forEach(t => t.stop());
      mediaRecorder = null; audioChunks = [];
      isRecording = false;
      if ($micBtn) { $micBtn.classList.remove('recording'); $micBtn.textContent = '🎙'; }
      if (blob.size < 2000) { setOrb('idle'); resolve(); return; }
      setOrb('thinking');
      if ($typingRow) $typingRow.classList.add('visible');
      try {
        const fd = new FormData();
        fd.append('audio', blob, 'rec.webm');
        const r = await fetch(`${apiUrl}/api/transcribe`, {
          method: 'POST', body: fd, signal: AbortSignal.timeout(30000)
        });
        if (!r.ok) throw new Error('Transcription failed');
        const { transcript } = await r.json();
        if (transcript && transcript.trim()) await sendMessage(transcript);
        else setOrb('idle');
      } catch (e) {
        addMsg('assistant', `Error: ${e.message}`);
        setOrb('idle');
      } finally { if ($typingRow) $typingRow.classList.remove('visible'); }
      resolve();
    };
    mediaRecorder.stop();
  });
}

// ── Browser SpeechRecognition (web only) ──────────────────────────────────
function tryWebSpeechRec() {
  if (IS_NATIVE) return false;
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return false;
  const rec = new SR();
  rec.lang = 'en-GB'; rec.interimResults = false; rec.maxAlternatives = 1;
  rec.onstart = () => {
    isRecording = true; setOrb('listening');
    if ($micBtn) { $micBtn.classList.add('recording'); $micBtn.textContent = '⏹'; }
    haptic();
  };
  rec.onresult = (e) => sendMessage(e.results[0][0].transcript);
  rec.onerror = rec.onend = () => {
    isRecording = false;
    if ($micBtn) { $micBtn.classList.remove('recording'); $micBtn.textContent = '🎙'; }
    if (orbState === 'listening') setOrb('idle');
  };
  rec.start();
  return true;
}

// ── Main voice handler ─────────────────────────────────────────────────────
async function handleVoice() {
  if (orbState === 'speaking') { stopPlayback(); setOrb('idle'); return; }
  if (orbState === 'thinking') { setOrb('idle'); if ($typingRow) $typingRow.classList.remove('visible'); return; }
  if (isRecording) { if (mediaRecorder) await stopMediaRec(); return; }
  haptic();
  closeMenu(); closeDetail();
  if (!tryWebSpeechRec()) {
    try { await startMediaRec(); }
    catch (e) { addMsg('assistant', `Mic error: ${e.message}`); }
  }
}

// ── Wake word ──────────────────────────────────────────────────────────────
async function toggleWakeWord() {
  if (!IS_NATIVE) {
    addMsg('assistant', 'Wake word only works on the native Android app.');
    return;
  }
  const WW = window.Capacitor.Plugins && window.Capacitor.Plugins.WakeWord;
  if (!WW) { addMsg('assistant', 'WakeWord plugin not available.'); return; }
  if (wakeEnabled) {
    await WW.stop();
    wakeEnabled = false;
    if ($wakeBtn) { $wakeBtn.textContent = '🎙 WAKE WORD'; $wakeBtn.classList.remove('active'); }
    addMsg('assistant', 'Wake word disabled.');
  } else {
    await WW.start();
    wakeEnabled = true;
    if ($wakeBtn) { $wakeBtn.textContent = '🔴 WAKE ON'; $wakeBtn.classList.add('active'); }
    closeMenu();
    addMsg('assistant', 'Listening for "Hey NEXUS". I\'ll activate when I hear you.');
  }
}

window.__nexusWakeWord = async function () {
  if (orbState !== 'idle') return;
  haptic(); setOrb('listening');
  if ($orbStatus) $orbStatus.textContent = 'TAP NOW';
  let pulses = 0;
  const pulse = setInterval(() => {
    haptic(); pulses++;
    if (pulses >= 3 || orbState !== 'listening') clearInterval(pulse);
  }, 600);
  setTimeout(() => {
    if (orbState === 'listening') { clearInterval(pulse); setOrb('idle'); }
  }, 5000);
};

// ── Overlay ────────────────────────────────────────────────────────────────
let overlayActive = false;
async function toggleOverlay() {
  if (!IS_NATIVE) {
    addMsg('assistant', 'Overlay only works on the Android native app.');
    return;
  }
  const FW = window.Capacitor.Plugins && window.Capacitor.Plugins.FloatingWindow;
  if (!FW) return;
  if (overlayActive) {
    await FW.stop(); overlayActive = false;
    if ($overlayBtn) { $overlayBtn.textContent = '▶ OVERLAY'; $overlayBtn.classList.remove('active'); }
  } else {
    const res = await FW.start();
    if (res.status === 'permission_required') {
      addMsg('assistant', 'Enable "Display over other apps" for NEXUS in Settings, then try again.');
    } else {
      overlayActive = true;
      if ($overlayBtn) { $overlayBtn.textContent = '⏸ OVERLAY ON'; $overlayBtn.classList.add('active'); }
      closeMenu();
    }
  }
}

// ── Service status checking ────────────────────────────────────────────────
const NODE_SVC_MAP = {
  ha:     'node-ha',
  plex:   'node-plex',
  n8n:    'node-n8n',
  pihole: 'node-dns',
};

function applyBubbleStatus(nodeId, status) {
  const node = document.getElementById(nodeId);
  if (!node) return;
  node.classList.remove('up', 'down', 'checking');
  node.classList.add(status);
  const dot = node.querySelector('.bubble-dot');
  if (dot) {
    dot.classList.remove('up', 'down');
    if (status === 'up' || status === 'down') dot.classList.add(status);
  }
  // Update sidebar card dot
  const cardDot = document.querySelector(`[data-card-dot="${node.dataset.detail}"]`);
  if (cardDot) {
    cardDot.classList.remove('up', 'down');
    if (status === 'up' || status === 'down') cardDot.classList.add(status);
  }
  // Update detail page header dot if this service is currently open
  if (activeDetail && node.dataset.detail === activeDetail) {
    if ($detailHdot)  { $detailHdot.className  = 'detail-hdot' + (status !== 'checking' ? ' ' + status : ''); }
    if ($detailHtext) $detailHtext.textContent  = status === 'up' ? 'ONLINE' : status === 'down' ? 'OFFLINE' : 'CHECKING';
  }
}

async function checkServices() {
  try {
    const r = await fetch(`${apiUrl}/api/status`, { signal: AbortSignal.timeout(8000) });
    if (!r.ok) throw new Error('Status error');
    const data = await r.json();
    for (const [key, nodeId] of Object.entries(NODE_SVC_MAP)) {
      applyBubbleStatus(nodeId, data[key] === 'up' ? 'up' : 'down');
    }
    setDot('ha-dot', data.ha === 'up');
  } catch (_) {}
}

// ── Constellation canvas ───────────────────────────────────────────────────
// Bubble offsets in px (must match inline --nx/--ny values in HTML)
const BUBBLE_OFFSETS = [
  { id: 'node-ha',   nx: -150, ny: -190 },
  { id: 'node-plex', nx:  120, ny: -190 },
  { id: 'node-n8n',  nx:  218, ny:  -30 },
  { id: 'node-prox', nx:  148, ny:  158 },
  { id: 'node-dns',  nx: -148, ny:  158 },
  { id: 'node-ai',   nx: -228, ny:  -30 },
];

function drawConstellation() {
  const canvas = document.getElementById('constellation-canvas');
  if (!canvas) return;
  canvas.width  = window.innerWidth;
  canvas.height = window.innerHeight;
  const ctx = canvas.getContext('2d');
  const styles = getComputedStyle(document.documentElement);
  const s   = parseFloat(styles.getPropertyValue('--s')) || 1;
  const cxPct = parseFloat(styles.getPropertyValue('--cx')) || 50;
  const cx  = canvas.width * (cxPct / 100);
  const cy  = canvas.height / 2;

  for (const b of BUBBLE_OFFSETS) {
    const bx = cx + b.nx * s;
    const by = cy + b.ny * s;
    const grad = ctx.createLinearGradient(cx, cy, bx, by);
    grad.addColorStop(0,   'rgba(0,180,255,0.28)');
    grad.addColorStop(0.6, 'rgba(0,140,255,0.1)');
    grad.addColorStop(1,   'rgba(0,100,255,0.02)');
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(bx, by);
    ctx.strokeStyle = grad;
    ctx.lineWidth   = 1;
    ctx.setLineDash([4, 9]);
    ctx.stroke();
    ctx.setLineDash([]);
  }
}

// ── Mobile constellation lines (centre orb → each dept bubble) ─────────────
function drawMobileLinks() {
  const svg = document.getElementById('orb-links');
  if (!svg) return;
  const zone = svg.parentElement;
  if (!zone) return;
  const rect = zone.getBoundingClientRect();
  const W = rect.width, H = rect.height;
  if (!W || !H) return;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.innerHTML = '';
  const cx = W / 2, cy = H / 2;
  document.querySelectorAll('.dept-constellation .bubble').forEach(b => {
    const br = b.getBoundingClientRect();
    const bx = (br.left - rect.left) + br.width / 2;
    const by = (br.top  - rect.top)  + br.height / 2;
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', cx); line.setAttribute('y1', cy);
    line.setAttribute('x2', bx); line.setAttribute('y2', by);
    line.setAttribute('stroke', 'rgba(0,180,255,0.18)');
    line.setAttribute('stroke-width', '1');
    line.setAttribute('stroke-dasharray', '3 6');
    svg.appendChild(line);
  });
}

// ── Sidebar service cards ──────────────────────────────────────────────────
const SVC_CARD_MAP = {};  // detailId -> card element for status updates
function buildSidebarCards() {
  if (!$svcCards) return;
  $svcCards.innerHTML = '';
  const bubbles = document.querySelectorAll('#bubbles-layer .bubble');
  bubbles.forEach(bubble => {
    const detailId = bubble.dataset.detail;
    const label    = bubble.dataset.label || 'SERVICE';
    const icon     = bubble.querySelector('.bubble-icon')?.textContent || '⚙';
    const accent   = getComputedStyle(bubble).getPropertyValue('--accent').trim() || 'var(--cyan)';
    const meta     = SERVICES_META[detailId] || {};
    const role     = (meta.cards || []).find(c => c.label === 'ROLE')?.value
                  || (meta.cards || []).find(c => c.label === 'MODELS')?.value || '';

    const card = document.createElement('div');
    card.className = 'svc-card';
    card.style.setProperty('--card-accent', accent);
    card.innerHTML = `
      <div class="svc-card-top">
        <span class="svc-card-icon">${icon}</span>
        <span class="svc-card-dot" data-card-dot="${detailId}"></span>
      </div>
      <span class="svc-card-name">${label.split(' ')[0]}</span>
      <span class="svc-card-role">${role}</span>
    `;
    card.addEventListener('click', () => {
      $svcCards.querySelectorAll('.svc-card').forEach(c => c.classList.remove('active'));
      card.classList.add('active');
      openDetail(bubble);
    });
    $svcCards.appendChild(card);
    SVC_CARD_MAP[detailId] = card;
  });
}

// ── Viewport scale ─────────────────────────────────────────────────────────
function updateScale() {
  const vmin = Math.min(window.innerWidth, window.innerHeight);
  const s    = Math.min(1.1, Math.max(0.55, vmin / 700));
  document.documentElement.style.setProperty('--s', s);
  drawConstellation();
  drawMobileLinks();
}

// ── Bubble click handlers ──────────────────────────────────────────────────
document.querySelectorAll('#bubbles-layer .bubble').forEach(bubble => {
  bubble.addEventListener('click', (e) => {
    e.stopPropagation();
    closeMenu(); closeChat();
    if (activeDetail === bubble.dataset.detail) { closeDetail(); return; }
    openDetail(bubble);
  });
});

// ── Detail back button ─────────────────────────────────────────────────────
if ($detailBack) {
  $detailBack.addEventListener('click', closeDetail);
}

// ── Dismiss on background tap ──────────────────────────────────────────────
document.addEventListener('click', (e) => {
  if (menuOpen && $ctrlTray && !$ctrlTray.contains(e.target) && e.target !== $menuBtn) {
    closeMenu();
  }
  if (chatOpen && e.target === document.body) {
    closeChat();
  }
});

// ── Key events ─────────────────────────────────────────────────────────────
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { closeDetail(); closeMenu(); closeChat(); }
});

// ── Core event listeners ───────────────────────────────────────────────────
if ($orbBtn) {
  $orbBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    closeMenu(); closeDetail();
    handleVoice();
  });
}
if ($micBtn)     $micBtn.addEventListener('click', handleVoice);
if ($sendBtn)    $sendBtn.addEventListener('click', () => sendMessage($textInput?.value));
if ($textInput)  $textInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage($textInput.value); }
});
if ($menuBtn)    $menuBtn.addEventListener('click', (e) => { e.stopPropagation(); toggleMenu(); });
if ($dragHandle) $dragHandle.addEventListener('click', toggleChat);

if ($ttsBtn) {
  $ttsBtn.addEventListener('click', () => {
    ttsEnabled = !ttsEnabled;
    if (!ttsEnabled) stopPlayback();
    $ttsBtn.textContent = ttsEnabled ? '🔊 TTS ON' : '🔇 TTS OFF';
    ttsEnabled ? $ttsBtn.classList.add('active') : $ttsBtn.classList.remove('active');
    setDot('tts-dot', ttsEnabled);
  });
}

if ($clearBtn) {
  $clearBtn.addEventListener('click', async () => {
    try { await fetch(`${apiUrl}/api/clear`, { method: 'POST' }); } catch (_) {}
    stopPlayback();
    if ($chatScroll) $chatScroll.innerHTML = '<div class="msg assistant"><span class="msg-who">NEXUS</span><span class="msg-text">Memory cleared. Ready.</span></div>';
    setOrb('idle');
    closeMenu();
  });
}

if ($overlayBtn) $overlayBtn.addEventListener('click', () => { closeMenu(); toggleOverlay(); });
if ($wakeBtn)    $wakeBtn.addEventListener('click', toggleWakeWord);

// Wire mobile-only input elements (mirrors of sidebar inputs)
if ($sendBtnMobile)   $sendBtnMobile.addEventListener('click', () => sendMessage($textInputMobile?.value));
if ($textInputMobile) $textInputMobile.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage($textInputMobile.value); }
});
if ($micBtnMobile)    $micBtnMobile.addEventListener('click', handleVoice);
if ($menuBtnMobile)   $menuBtnMobile.addEventListener('click', (e) => { e.stopPropagation(); toggleMenu(); });

document.addEventListener('touchstart', unlockAudio, { once: true, passive: true });
document.addEventListener('click',      unlockAudio, { once: true, passive: true });

// ── Init ───────────────────────────────────────────────────────────────────
async function init() {
  updateScale();
  window.addEventListener('resize', updateScale);
  buildSidebarCards();

  await resolveApiUrl();
  if (IS_NATIVE) await requestMicPermission();

  // Wire native wake word listener
  if (IS_NATIVE) {
    const WW = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.WakeWord;
    if (WW && WW.addListener) {
      WW.addListener('detected', () => { window.__nexusWakeWord && window.__nexusWakeWord(); });
    }
  }

  await checkServices();
  setInterval(checkServices, 30000);

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('./sw.js').catch(() => {});
  }
}

document.addEventListener('DOMContentLoaded', init);
