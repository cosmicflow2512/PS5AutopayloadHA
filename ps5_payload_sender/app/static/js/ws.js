'use strict';

// ── WebSocket ────────────────────────────────────────────────────
function connectWS() {
  const dot = document.getElementById('ws-indicator');
  dot.className = 'ws-dot ws-connecting';
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws    = new WebSocket(`${proto}://${location.host}${BASE}/ws`);
  state.ws    = ws;

  ws.onopen = () => {
    dot.className   = 'ws-dot ws-online';
    state.wsRetries = 0;
    log('Connected ✓', 'success');
    ws._ping = setInterval(() => {
      if (ws.readyState === 1) ws.send(JSON.stringify({ type: 'ping' }));
    }, 25000);
  };

  ws.onmessage = ({ data }) => {
    try { handleWS(JSON.parse(data)); } catch (_) { /* ignore */ }
  };

  ws.onclose = () => {
    dot.className = 'ws-dot ws-offline';
    clearInterval(ws._ping);
    const delay = Math.min(1000 * Math.pow(1.5, state.wsRetries++), 20000);
    if (state.wsRetries <= 12) setTimeout(connectWS, delay);
    else log('Connection lost. Please reload the page.', 'error');
  };

  ws.onerror = () => ws.close();
}

function handleWS(msg) {
  if (msg.type === 'pong') return;
  if (msg.type === 'config') {
    const ip = document.getElementById('ps5-ip');
    if (msg.ps5_ip && !ip.value) ip.value = msg.ps5_ip;
    return;
  }
  if (msg.type === 'exec_state') {
    state.execState   = msg.state;
    state.runningProfile = msg.profile || '';
    handleExecState(msg.state, msg.profile || '');
    return;
  }
  if (msg.type === 'status') {
    log(msg.message, msg.level || 'info');
    handleBuilderStepStatus(msg);
    // Auto-refresh the payload list when a server-side import or
    // switch-version completes — without this, a second browser tab
    // (or the HA mobile app sidebar) never sees the new payload until
    // a full reload. Debounced so a burst of imports fires one refresh
    // instead of N.
    if (msg.level === 'success' && msg.message &&
        (msg.message.includes('imported') || msg.message.includes('switched to'))) {
      clearTimeout(handleWS._refreshTimer);
      handleWS._refreshTimer = setTimeout(() => {
        if (typeof refreshPayloads === 'function') refreshPayloads();
      }, 500);
    }
    return;
  }
  if (msg.type === 'flow_wait_check' || msg.type === 'flow_simulation') {
    if (typeof handleFlowNotifyEvent === 'function') handleFlowNotifyEvent(msg);
    return;
  }
}
