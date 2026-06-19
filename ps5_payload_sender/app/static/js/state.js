'use strict';

// ── Injected by server from X-Ingress-Path header ────────────────
const BASE = (window.PS5_BASE || '').replace(/\/$/, '');

// ── Central state (single source of truth) ───────────────────────
const state = {
  ws:              null,
  wsRetries:       0,
  payloads:        [],
  profiles:        [],
  devices:         [],
  favorites:       [],         // profile quick-launch favorites
  payloadFavorites:[],         // payload star favorites
  payloadFilter:    'all',      // 'all' | 'favorites' | 'elf' | 'lua'
  payloadSearch:    '',
  selectedPayloads: new Set(), // filenames checked for bulk ops
  advancedMode:     false,     // show/hide port inputs
  execState:        'idle',    // idle | running | paused | stopped | completed | failed
  runningProfile:   '',        // filename of currently running profile
  sources:          [],        // GitHub payload sources
  updateResults:    {},        // filename → {latest_version, download_url, ...}
  updateCheckDone:  false,     // true after first update check completes
  isUpdating:       false,     // true while a switch-version batch is in flight
  ftpHost:          '',        // FTP host for autoload upload (empty = use PS5 IP)
  ftpPath:          '/mnt/usb0/ps5_autoloader/',
};

// Builder lives here so every module can access it
const builder = { steps: [] };

// ── Theme ────────────────────────────────────────────────────────
function initTheme() {
  const saved = sessionStorage.getItem('ps5_theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
  document.getElementById('btn-theme').innerHTML  = saved === 'dark' ? icon('sun') : icon('moon');
}

function toggleTheme() {
  const cur  = document.documentElement.getAttribute('data-theme') || 'dark';
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  sessionStorage.setItem('ps5_theme', next);
  document.getElementById('btn-theme').innerHTML  = next === 'dark' ? icon('sun') : icon('moon');
}

// ── Advanced Mode ─────────────────────────────────────────────────
function applyAdvancedMode() {
  if (state.advancedMode) {
    document.body.classList.add('advanced-mode');
  } else {
    document.body.classList.remove('advanced-mode');
  }
}

// ── Toast notification ────────────────────────────────────────────────────────
function showToast(msg, duration = 2200) {
  let toast = document.getElementById('ps5-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'ps5-toast';
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.className = 'ps5-toast ps5-toast-show';
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { toast.className = 'ps5-toast'; }, duration);
}

// ── API fetch ────────────────────────────────────────────────────
async function api(path, opts = {}) {
  // Auto-encode plain-object bodies as JSON. Without this, fetch() stringifies
  // `{foo: 1}` to the literal text "[object Object]" and never sets the
  // Content-Type header, so FastAPI replies 422 and the notification path
  // (or any other JSON endpoint) is never actually called.
  // Existing callers that pre-stringify keep working — strings are passed
  // straight through and any explicit Content-Type they set wins.
  if (opts.body && typeof opts.body === 'object'
      && !(opts.body instanceof FormData)
      && !(opts.body instanceof Blob)
      && !(opts.body instanceof URLSearchParams)
      && !(opts.body instanceof ArrayBuffer)) {
    opts = {
      ...opts,
      body: JSON.stringify(opts.body),
      headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    };
  }
  const res = await fetch(BASE + path, opts);
  if (!res.ok) {
    const txt = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status} ${txt}`);
  }
  return res.json();
}

// ── Helpers ──────────────────────────────────────────────────────
function getHost() {
  const h = document.getElementById('ps5-ip').value.trim();
  if (!h) { alert('Please enter PS5 IP address!'); return null; }
  return h;
}

function fmt(b) {
  if (b < 1024)     return `${b} B`;
  if (b < 1048576)  return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1048576).toFixed(2)} MB`;
}

function fmtDate(ts) {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) +
    ' ' + d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
}

function validateIp() {
  const val  = document.getElementById('ps5-ip').value.trim();
  const warn = document.getElementById('ip-warn');
  if (!val) { warn.style.display = 'none'; return; }
  const valid = /^(\d{1,3}\.){3}\d{1,3}$/.test(val) &&
    val.split('.').every(n => parseInt(n) <= 255);
  warn.style.display = valid ? 'none' : '';
}

// ── State persistence (/data/state.json) ─────────────────────────
let _saveTimer = null;

function scheduleSave() {
  clearTimeout(_saveTimer);
  _saveTimer = setTimeout(persistState, 800);
}

async function persistState() {
  try {
    await api('/api/state', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ps5_ip:               document.getElementById('ps5-ip').value.trim(),
        advanced_mode:        state.advancedMode,
        favorites:            state.favorites,
        payload_favorites:    state.payloadFavorites,
        payload_filter:       state.payloadFilter,
        builder_steps:        builder.steps,
        builder_profile_name: document.getElementById('builder-profile-name').value,
        // Flow Notifications config — keep the user's in-progress
        // settings across reloads, just like builder_steps.
        flow_notify_config:   typeof flowNotifyReadConfig === 'function'
                                ? flowNotifyReadConfig() : null,
        ftp_host:             state.ftpHost,
        ftp_path:             state.ftpPath,
      }),
    });
  } catch (_) { /* silent */ }
}

async function loadPersistedState() {
  try {
    const saved = await api('/api/state');
    if (saved.ps5_ip) {
      document.getElementById('ps5-ip').value = saved.ps5_ip;
      onIpChange();
    }
    if (typeof saved.advanced_mode === 'boolean') {
      state.advancedMode = saved.advanced_mode;
      const tog = document.getElementById('advanced-mode-toggle');
      if (tog) tog.checked = saved.advanced_mode;
      applyAdvancedMode();
    }
    if (Array.isArray(saved.favorites))          state.favorites          = saved.favorites;
    if (Array.isArray(saved.payload_favorites))  state.payloadFavorites   = saved.payload_favorites;
    if (saved.payload_filter)                    state.payloadFilter      = saved.payload_filter;
    if (Array.isArray(saved.builder_steps) && saved.builder_steps.length) {
      builder.steps = saved.builder_steps;
      builderRenderList();
    }
    if (saved.builder_profile_name)
      document.getElementById('builder-profile-name').value = saved.builder_profile_name;
    if (saved.flow_notify_config && typeof flowNotifyApplyConfig === 'function')
      flowNotifyApplyConfig(saved.flow_notify_config);
    if (saved.ftp_host !== undefined) {
      state.ftpHost = saved.ftp_host || '';
      const hi = document.getElementById('ftp-host-input');
      if (hi) hi.value = state.ftpHost;
    }
    if (saved.ftp_path) {
      state.ftpPath = saved.ftp_path;
      const pi = document.getElementById('ftp-path-input');
      if (pi) pi.value = state.ftpPath;
    }
  } catch (_) { /* first run */ }
}

// ── Version display ───────────────────────────────────────────────
async function loadVersion() {
  try {
    const data  = await api('/api/version');
    const badge = document.getElementById('version-badge');
    if (badge) badge.textContent = `v${data.version}`;
  } catch (_) { /* ignore */ }
}
