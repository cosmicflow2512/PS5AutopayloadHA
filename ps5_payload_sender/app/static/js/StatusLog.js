'use strict';

// ── Log history (in-memory, max 500 entries) ──────────────────────
const _logHistory = [];

function _ts() {
  return new Date().toLocaleTimeString('en-GB', { hour12: false });
}

function dtrace(msg) { log(msg, 'trace'); }

function log(msg, level = 'info') {
  _logHistory.push({ ts: _ts(), msg, level });
  if (_logHistory.length > 500) _logHistory.shift();

  const container = document.getElementById('status-log');
  if (!container) return;

  const filter = document.getElementById('log-filter')?.value || 'all';
  if (!_matchesFilter({ msg, level }, filter)) return;

  const el = document.createElement('div');
  el.className = `log-entry log-${level} fade`;
  const tsEl = document.createElement('span');
  tsEl.className = 'log-ts'; tsEl.textContent = _ts();
  el.appendChild(tsEl);
  el.appendChild(document.createTextNode(' ' + msg));
  container.appendChild(el);
  container.scrollTop = container.scrollHeight;
}

function clearLog() {
  document.getElementById('status-log').innerHTML = '';
  _logHistory.length = 0;
}

// ── Filter ────────────────────────────────────────────────────────
function _matchesFilter(e, f) {
  if (f === 'all')     return true;
  if (f === 'port')    return /port/i.test(e.msg);
  if (f === 'payload') return /send|payload|import/i.test(e.msg);
  if (f === 'trace')   return e.level === 'trace';
  return true;
}

function applyLogFilter() {
  const container = document.getElementById('status-log');
  if (!container) return;
  const filter = document.getElementById('log-filter')?.value || 'all';
  container.innerHTML = '';
  _logHistory.filter(e => _matchesFilter(e, filter)).forEach(e => {
    const el = document.createElement('div');
    el.className = `log-entry log-${e.level}`;
    const tsEl = document.createElement('span');
    tsEl.className = 'log-ts'; tsEl.textContent = e.ts;
    el.appendChild(tsEl);
    el.appendChild(document.createTextNode(' ' + e.msg));
    container.appendChild(el);
  });
  container.scrollTop = container.scrollHeight;
}

// ── Export ────────────────────────────────────────────────────────
async function exportLog(fmt = 'txt') {
  if (!_logHistory.length) { showToast('No log entries to export'); return; }
  try {
    const res = await fetch(BASE + '/api/logs/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entries: _logHistory, format: fmt }),
    });
    const blob = await res.blob();
    const cd   = res.headers.get('Content-Disposition') || '';
    const name = cd.match(/filename="([^"]+)"/)?.[1] || `ps5-log.${fmt}`;
    const url  = URL.createObjectURL(blob);
    const a    = Object.assign(document.createElement('a'), { href: url, download: name });
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    showToast('Log exported');
  } catch (e) { showToast('Export failed: ' + e.message); }
}

// ── Port check ────────────────────────────────────────────────────
async function checkPortOnce() {
  const host    = getHost(); if (!host) return;
  const port    = parseInt(document.getElementById('check-port').value, 10);
  const timeout = parseFloat(document.getElementById('check-timeout').value) || 5;
  if (!port || port < 1 || port > 65535) { alert('Invalid port!'); return; }
  const el = document.getElementById('port-check-result');
  el.style.display = 'none'; el.className = '';
  log(`Checking port ${port} on ${host} …`);
  try {
    const d = await api('/api/port/check', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ host, port, timeout }),
    });
    el.style.display = 'block';
    el.className  = d.reachable ? 'res-ok' : 'res-fail';
    el.textContent = d.reachable ? `✓ Port ${port} is reachable` : `✗ Port ${port} not reachable`;
    log(el.textContent, d.reachable ? 'success' : 'warn');
  } catch (e) { log('Port check: ' + e.message, 'error'); }
}

async function waitForPort() {
  const host     = getHost(); if (!host) return;
  const port     = parseInt(document.getElementById('check-port').value, 10);
  const timeout  = parseFloat(document.getElementById('check-timeout').value) || 10;
  const interval = parseFloat(document.getElementById('check-interval').value) / 1000 || 0.5;
  if (!port || port < 1 || port > 65535) { alert('Invalid port!'); return; }
  const el = document.getElementById('port-check-result');
  el.style.display = 'none'; el.className = '';
  const startIso = new Date().toISOString();
  const t0 = Date.now();
  try {
    const d = await api('/api/port/wait', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ host, port, timeout, interval }),
    });
    const dur = Date.now() - t0;
    el.style.display = 'block';
    el.className   = d.reachable ? 'res-ok' : 'res-fail';
    el.textContent = d.reachable ? `✓ Port ${port} reachable (${(dur/1000).toFixed(1)}s)` : `✗ Timeout`;
    if (d.reachable)
      recordPortTiming(port, dur, startIso, new Date().toISOString()).catch(() => {});
  } catch (e) { log('Wait: ' + e.message, 'error'); }
}
