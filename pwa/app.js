'use strict';

// ── Config ──────────────────────────────────────────────────────────────────
// Reads from window.NEXUS_CONFIG (set by config.js loaded in index.html)
// Falls back to sensible defaults so the app still loads without config.js

const LOCAL_URL    = (window.NEXUS_CONFIG && window.NEXUS_CONFIG.localUrl)    || 'http://YOUR_SERVER_IP:5000';
const EXTERNAL_URL = (window.NEXUS_CONFIG && window.NEXUS_CONFIG.externalUrl) || 'https://YOUR_NEXUS_DOMAIN';
let apiUrl = LOCAL_URL;

async function resolveApiUrl() {
  for (const url of [LOCAL_URL, EXTERNAL_URL]) {
    try {
      const r = await fetch(`${url}/health`, { signal: AbortSignal.timeout(3000) });
      if (r.ok) { apiUrl = url; return; }
    } catch (_) {}
  }
  apiUrl = LOCAL_URL;
}

// ── State ────────────────────────────────────────────────────────────────────

let status = 'idle';        // idle | listening | thinking | speaking
let showText = false;
let mediaRecorder = null;
let audioChunks = [];
let currentAudio = null;

// ── DOM refs ─────────────────────────────────────────────────────────────────

const $loader    = document.getElementById('loader');
const $messages  = document.getElementById('messages');
const $emptyState= document.getElementById('empty-state');
const $orbRing   = document.getElementById('orb-ring');
const $orbBtn    = document.getElementById('orb-btn');
const $orbLabel  = document.getElementById('orb-label');
const $toggleBtn = document.getElementById('toggle-btn');
const $textArea  = document.getElementById('text-area');
const $textInput = document.getElementById('text-input');
const $sendBtn   = document.getElementById('send-btn');

// ── Orb status ────────────────────────────────────────────────────────────────

const STATUS_LABELS = {
  idle:      'TAP TO SPEAK',
  listening: 'LISTENING...',
  thinking:  'THINKING...',
  speaking:  'TAP TO STOP',
};

function setStatus(s) {
  status = s;
  $orbRing.className = `orb-ring ${s}`;
  $orbLabel.textContent = STATUS_LABELS[s] || 'TAP TO SPEAK';
  $sendBtn.disabled = (s !== 'idle');
  $textInput.disabled = (s !== 'idle');
}

// ── Messages ─────────────────────────────────────────────────────────────────

function addMessage(role, text) {
  $emptyState.style.display = 'none';
  const row = document.createElement('div');
  row.className = `msg-row ${role}`;
  if (role === 'assistant') {
    const av = document.createElement('span');
    av.className = 'avatar';
    av.textContent = 'N';
    row.appendChild(av);
  }
  const bubble = document.createElement('div');
  bubble.className = `bubble ${role}`;
  bubble.textContent = text;
  row.appendChild(bubble);
  $messages.appendChild(row);
  requestAnimationFrame(() => { $messages.scrollTop = $messages.scrollHeight; });
}

// ── Phone commands ────────────────────────────────────────────────────────────

function parsePhoneCommands(reply) {
  const cmds = [];
  const callMatch = reply.match(/<<CALL:([^>]+)>>/);
  const smsMatch  = reply.match(/<<SMS:([^:>]+):([^>]+)>>/);
  const openMatch = reply.match(/<<OPEN:([^>]+)>>/);
  const urlMatch  = reply.match(/<<URL:([^>]+)>>/);
  if (callMatch) cmds.push({ type: 'call', number: callMatch[1] });
  if (smsMatch)  cmds.push({ type: 'sms',  number: smsMatch[1], message: smsMatch[2] });
  if (openMatch) cmds.push({ type: 'open', scheme: openMatch[1] });
  if (urlMatch)  cmds.push({ type: 'url',  url: urlMatch[1] });
  return cmds;
}

function executePhoneCommands(cmds) {
  for (const cmd of cmds) {
    try {
      if (cmd.type === 'call') window.location.href = `tel:${cmd.number.replace(/\s/g,'')}`;
      else if (cmd.type === 'sms') window.location.href = `sms:${cmd.number}${cmd.message ? `?body=${encodeURIComponent(cmd.message)}` : ''}`;
      else if (cmd.type === 'open') window.open(cmd.scheme, '_blank', 'noopener');
      else if (cmd.type === 'url')  window.open(cmd.url,    '_blank', 'noopener');
    } catch (e) { console.warn('[NEXUS phone]', e.message); }
  }
}

function cleanReply(reply) {
  return reply.replace(/<<(CALL|SMS|OPEN|URL):[^>]+>>/g, '').trim();
}

// ── API calls ─────────────────────────────────────────────────────────────────

async function chat(userMessage) {
  const r = await fetch(`${apiUrl}/api/ask`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ message: userMessage }),
  });
  if (!r.ok) throw new Error(`NEXUS error: ${await r.text()}`);
  const data = await r.json();
  if (data.error) throw new Error(data.error);
  return { reply: data.reply || '', audioB64: data.audio || null };
}

async function transcribeBlob(blob) {
  const fd = new FormData();
  fd.append('audio', blob, 'recording.webm');
  const r = await fetch(`${apiUrl}/api/transcribe`, { method: 'POST', body: fd });
  if (!r.ok) throw new Error('Transcription failed');
  const data = await r.json();
  return data.transcript || '';
}

// ── Audio playback ────────────────────────────────────────────────────────────

function stopPlayback() {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.src = '';
    currentAudio = null;
  }
}

function playBase64Audio(b64) {
  return new Promise((resolve) => {
    stopPlayback();
    const audio = new Audio(`data:audio/mp3;base64,${b64}`);
    currentAudio = audio;
    audio.onended = () => { currentAudio = null; resolve(); };
    audio.onerror = () => { currentAudio = null; resolve(); };
    audio.play().catch(() => resolve());
  });
}

// ── Recording ─────────────────────────────────────────────────────────────────

async function hapticFeedback() {
  // Use Capacitor Haptics when available (native app), fall back to Vibration API
  try {
    if (window.Capacitor && window.Capacitor.isNativePlatform()) {
      const { Haptics, ImpactStyle } = await import('@capacitor/haptics');
      await Haptics.impact({ style: ImpactStyle.Medium });
      return;
    }
  } catch (_) {}
  if (navigator.vibrate) navigator.vibrate(40);
}

async function startRecording() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  audioChunks = [];
  const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
    ? 'audio/webm;codecs=opus'
    : MediaRecorder.isTypeSupported('audio/webm')
    ? 'audio/webm'
    : 'audio/ogg;codecs=opus';
  mediaRecorder = new MediaRecorder(stream, { mimeType });
  mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunks.push(e.data); };
  mediaRecorder.start(100);
  await hapticFeedback();
}

async function stopRecording() {
  if (!mediaRecorder) return null;
  return new Promise((resolve) => {
    mediaRecorder.onstop = () => {
      const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType });
      mediaRecorder.stream.getTracks().forEach(t => t.stop());
      mediaRecorder = null;
      audioChunks = [];
      resolve(blob);
    };
    mediaRecorder.stop();
  });
}

// ── Main response flow ────────────────────────────────────────────────────────

async function handleResponse(userText) {
  addMessage('user', userText);
  setStatus('thinking');
  try {
    const { reply, audioB64 } = await chat(userText);
    const displayText = cleanReply(reply);
    addMessage('assistant', displayText);
    const cmds = parsePhoneCommands(reply);
    if (cmds.length) executePhoneCommands(cmds);
    if (audioB64) {
      setStatus('speaking');
      await playBase64Audio(audioB64);
    }
  } catch (e) {
    addMessage('assistant', `Error: ${e.message}`);
  }
  setStatus('idle');
}

// ── Orb press ─────────────────────────────────────────────────────────────────

async function handleOrbPress() {
  if (status === 'speaking') {
    stopPlayback();
    setStatus('idle');
    return;
  }
  if (status === 'thinking') return;
  if (status === 'idle') {
    try {
      await startRecording();
      setStatus('listening');
    } catch (e) {
      addMessage('assistant', `Mic error: ${e.message}`);
      showTextInput(true);
    }
    return;
  }
  if (status === 'listening') {
    setStatus('thinking');
    try {
      const blob = await stopRecording();
      if (!blob || blob.size < 1000) { setStatus('idle'); return; }
      const transcript = await transcribeBlob(blob);
      if (!transcript) { setStatus('idle'); return; }
      await handleResponse(transcript);
    } catch (e) {
      addMessage('assistant', `Error: ${e.message}`);
      setStatus('idle');
    }
  }
}

// ── Text input toggle ─────────────────────────────────────────────────────────

function showTextInput(force) {
  showText = (force !== undefined) ? force : !showText;
  $textArea.classList.toggle('hidden', !showText);
  $toggleBtn.textContent = showText ? '🎤' : '⌨️';
  if (showText) $textInput.focus();
}

// ── Init ──────────────────────────────────────────────────────────────────────

async function init() {
  await resolveApiUrl();
  $loader.classList.add('hidden');

  // Check mic availability — fall back to text if not available
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    showTextInput(true);
  }

  $orbBtn.addEventListener('click', handleOrbPress);
  $toggleBtn.addEventListener('click', () => showTextInput());

  $sendBtn.addEventListener('click', async () => {
    const text = $textInput.value.trim();
    if (!text || status !== 'idle') return;
    $textInput.value = '';
    await handleResponse(text);
  });

  $textInput.addEventListener('keydown', async (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      const text = $textInput.value.trim();
      if (!text || status !== 'idle') return;
      $textInput.value = '';
      await handleResponse(text);
    }
  });
}

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('./sw.js').catch(() => {});
  });
}

document.addEventListener('DOMContentLoaded', init);
