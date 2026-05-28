'use strict';

// ── AutoLoad Builder ─────────────────────────────────────────────
// builder object is declared in state.js

// ── Step run-status tracking ──────────────────────────────────────
// Strict single-source-of-truth using currentStepIndex:
//   idx < current  → done
//   idx === current → running
//   idx > current  → idle
const _stepRunStatus = {};  // index(str) → 'running' | 'done' | 'error'
let _currentStepIdx = -1;

function handleBuilderStepStatus(msg) {
  if (!msg || msg.type !== 'status') return;
  const m = /^\[(\d+)\/(\d+)\]/.exec(msg.message);

  if (m) {
    const idx   = parseInt(m[1], 10) - 1;  // 0-based step index
    const level = msg.level || 'info';

    if (level === 'success') {
      // Explicit step-N success confirmation
      _stepRunStatus[idx] = 'done';
      if (_currentStepIdx === idx) _currentStepIdx = idx + 1;
    } else if (level === 'error') {
      _stepRunStatus[idx] = 'error';
    } else {
      // Step N is starting: enforce strict ordering
      // All prior steps not yet marked → mark done
      for (let i = 0; i < idx; i++) {
        if (!_stepRunStatus[i] || _stepRunStatus[i] === 'running') {
          _stepRunStatus[i] = 'done';
        }
      }
      _currentStepIdx = idx;
      _stepRunStatus[idx] = 'running';
      // Clear any stale status for future steps
      for (let i = idx + 1; i < builder.steps.length; i++) {
        delete _stepRunStatus[i];
      }
    }
  } else {
    // Result message without [N/M] prefix → applies to current running step
    if (_currentStepIdx >= 0) {
      const level = msg.level || 'info';
      if (level === 'success') {
        _stepRunStatus[_currentStepIdx] = 'done';
      } else if (level === 'error') {
        _stepRunStatus[_currentStepIdx] = 'error';
      }
    }
  }

  updateStepStatusBadges();
}

function updateStepStatusBadges() {
  Object.entries(_stepRunStatus).forEach(([idx, status]) => {
    const stepEl = document.querySelector(`.builder-step[data-step-idx="${idx}"]`);
    if (!stepEl) return;
    const el = stepEl.querySelector('.step-run-status');
    if (el) {
      el.className = `step-run-status step-${status}`;
      el.textContent = status === 'running' ? '⏳' : status === 'done' ? '✔' : '✗';
    }
  });
}

function clearStepRunStatus() {
  _currentStepIdx = -1;
  Object.keys(_stepRunStatus).forEach(k => delete _stepRunStatus[k]);
  document.querySelectorAll('.step-run-status').forEach(el => {
    el.className = 'step-run-status'; el.textContent = '';
  });
}

// ── Run/Stop button state ─────────────────────────────────────────
function _setBuilderRunning(running) {
  const btn = document.getElementById('btn-builder-run');
  if (!btn) return;
  if (running) {
    btn.className = 'btn btn-danger btn-xl';
    btn.innerHTML  = icon('square', {filled:true}) + ' Stop';
  } else {
    btn.className = 'btn btn-primary btn-xl';
    btn.innerHTML  = icon('play') + ' Run';
  }
}

// Called from ws.js when exec_state + profile change
function handleExecState(execState, profile) {
  const active = execState === 'running' || execState === 'paused';

  // Builder run→stop button (always responds since any execution can be stopped here)
  _setBuilderRunning(active);

  // Resolve final step state before clearing
  if (!active) {
    if (execState === 'completed') {
      // Mark any still-running step as done
      Object.keys(_stepRunStatus).forEach(k => {
        if (_stepRunStatus[k] === 'running') _stepRunStatus[k] = 'done';
      });
      updateStepStatusBadges();
    } else if (execState === 'failed') {
      Object.keys(_stepRunStatus).forEach(k => {
        if (_stepRunStatus[k] === 'running') _stepRunStatus[k] = 'error';
      });
      updateStepStatusBadges();
    }
    // Delay clear so user can see final ✔/✗ briefly
    setTimeout(clearStepRunStatus, 1800);
    // Refresh recent-runs history after a terminal transition
    if (typeof flowHistoryRefresh === 'function') flowHistoryRefresh();
  }

  // Sync Quick Start tiles and profile list
  if (typeof renderFavorites === 'function')      renderFavorites();
  if (typeof renderProfileList === 'function')    renderProfileList();
}

// ── Dropdown ─────────────────────────────────────────────────────
function builderUpdatePayloadDropdown() {
  const sel = document.getElementById('panel-payload-select');
  // Clear ALL children (including optgroup) – options-only removal misses optgroups
  sel.innerHTML = '<option value="">– Select a payload –</option>';

  const searchEl = document.getElementById('builder-payload-search');
  const query    = (searchEl ? searchEl.value : '').trim().toLowerCase();
  let payloads   = state.payloads.slice();

  if (query) {
    payloads = payloads.filter(p => p.name.toLowerCase().includes(query));
    payloads.sort((a, b) => {
      const aS = a.name.toLowerCase().startsWith(query);
      const bS = b.name.toLowerCase().startsWith(query);
      return (aS && !bS) ? -1 : (!aS && bS) ? 1 : 0;
    });
  }

  const favs = payloads.filter(p =>  state.payloadFavorites.includes(p.name));
  const rest = payloads.filter(p => !state.payloadFavorites.includes(p.name));

  function addGroup(label, items) {
    if (!items.length) return;
    const grp = document.createElement('optgroup');
    grp.label = label;
    items.forEach(p => {
      const opt = document.createElement('option');
      opt.value          = p.name;
      opt.textContent    = (state.payloadFavorites.includes(p.name) ? '★ ' : '') + p.name;
      opt.dataset.autoPort = String(p.auto_port);
      grp.appendChild(opt);
    });
    sel.appendChild(grp);
  }

  if (favs.length) addGroup('— Favorites —', favs);
  addGroup(favs.length ? '— All Payloads —' : '— Payloads —', rest);
}

// ── Panels ───────────────────────────────────────────────────────
function builderTogglePanel(type) {
  const panels = {
    payload: 'panel-payload',
    delay:   'panel-delay',
    wait:    'panel-wait',
    notify:  'panel-notify',
  };
  Object.entries(panels).forEach(([t, id]) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.style.display = (t === type && el.style.display === 'none') ? '' : 'none';
  });
}

function builderAddNotifyStep() {
  const title = (document.getElementById('panel-notify-title').value || '').trim();
  const msg   = (document.getElementById('panel-notify-msg').value   || '').trim();
  const svc   = (document.getElementById('panel-notify-svc')?.value  || '').trim();
  if (!title) { alert('Title is required'); return; }
  if (svc && !svc.startsWith('notify.')) {
    alert('Service override must start with notify.');
    return;
  }
  builder.steps.push({
    type: 'notify', title, message: msg, service_override: svc || '',
  });
  document.getElementById('panel-notify-title').value = '';
  document.getElementById('panel-notify-msg').value   = '';
  if (document.getElementById('panel-notify-svc')) {
    document.getElementById('panel-notify-svc').value = '';
  }
  document.getElementById('panel-notify').style.display = 'none';
  builderRenderList(); scheduleSave();
}

// Called when user selects a payload in the dropdown (basic mode: immediate add)
function builderAddPayloadStepFromSelect() {
  const sel = document.getElementById('panel-payload-select');
  if (!sel.value) return;
  const filename = sel.value;
  const autoPort = parseInt(sel.options[sel.selectedIndex].dataset.autoPort, 10);
  const p = state.payloads.find(x => x.name === filename);
  const version = (p && p.source) ? p.source.version : null;
  builder.steps.push({ type: 'payload', filename, autoPort, portOverride: null, version });
  sel.value = '';                                    // reset selector
  document.getElementById('panel-payload').style.display = 'none';
  builderRenderList(); scheduleSave();
}

function builderAddPayloadStep() {
  const sel      = document.getElementById('panel-payload-select');
  const filename = sel.value;
  if (!filename) { alert('Select a payload!'); return; }
  const autoPort    = parseInt(sel.options[sel.selectedIndex].dataset.autoPort, 10);
  const portVal     = parseInt(document.getElementById('panel-payload-port').value, 10);
  const portOverride = (portVal > 0 && portVal <= 65535) ? portVal : null;
  const p = state.payloads.find(x => x.name === filename);
  const version = (p && p.source) ? p.source.version : null;
  builder.steps.push({ type: 'payload', filename, autoPort, portOverride, version });
  document.getElementById('panel-payload-port').value  = '';
  sel.value = '';
  document.getElementById('panel-payload').style.display = 'none';
  builderRenderList(); scheduleSave();
}

function builderAddDelayStep(ms) {
  if (!ms || ms <= 0) return;
  builder.steps.push({ type: 'delay', ms });
  builderRenderList(); scheduleSave();
}

function builderAddWaitStep() {
  const port     = parseInt(document.getElementById('panel-wait-port').value, 10);
  const toEl     = document.getElementById('panel-wait-to');
  const ivEl     = document.getElementById('panel-wait-interval');
  const timeout  = toEl ? (parseInt(toEl.value,  10) || 90)  : 90;
  const interval = ivEl ? (parseInt(ivEl.value,  10) || 500) : 500;
  if (!port || port < 1 || port > 65535) { alert('Invalid port!'); return; }
  builder.steps.push({ type: 'wait_port', port, timeout, interval_ms: Math.max(100, interval) });
  document.getElementById('panel-wait').style.display = 'none';
  builderRenderList(); scheduleSave();
}

// ── Drag & drop ──────────────────────────────────────────────────
function _builderMakeDragDrop(el, idx) {
  el.addEventListener('dragstart', e => {
    e.dataTransfer.setData('text/plain', String(idx));
    e.dataTransfer.effectAllowed = 'move';
    setTimeout(() => el.classList.add('dragging'), 0);
  });
  el.addEventListener('dragend', () => {
    el.classList.remove('dragging');
    el.setAttribute('draggable', 'false');
  });
  el.addEventListener('dragover',  e => { e.preventDefault(); el.classList.add('drag-over'); });
  el.addEventListener('dragleave', e => {
    if (!el.contains(e.relatedTarget)) el.classList.remove('drag-over');
  });
  el.addEventListener('drop', e => {
    e.preventDefault(); el.classList.remove('drag-over');
    const from = parseInt(e.dataTransfer.getData('text/plain'), 10);
    if (isNaN(from) || from === idx) return;
    const moved = builder.steps.splice(from, 1)[0];
    builder.steps.splice(idx, 0, moved);
    builderRenderList(); scheduleSave();
  });
}

function _builderMakeDragHandle(stepEl) {
  const drag = document.createElement('span');
  drag.className   = 'drag-handle';
  drag.textContent = '☰';
  drag.title       = 'Drag to reorder';
  drag.addEventListener('mousedown',  () => stepEl.setAttribute('draggable', 'true'));
  drag.addEventListener('touchstart', () => stepEl.setAttribute('draggable', 'true'), { passive: true });
  return drag;
}

function _makeStepNum(idx) {
  const num = document.createElement('span');
  num.className   = 'step-num';
  num.textContent = idx + 1;
  return num;
}

function _makeStepStatusBadge(idx) {
  const badge = document.createElement('span');
  badge.className = 'step-run-status';
  const cur = _stepRunStatus[idx];
  if (cur) {
    badge.classList.add(`step-${cur}`);
    badge.textContent = cur === 'running' ? '⏳' : cur === 'done' ? '✔' : '✗';
  }
  return badge;
}

function _builderMakeOrderBtns(idx) {
  const btns   = document.createElement('div');
  btns.className = 'step-btns';
  const upBtn  = document.createElement('button');
  upBtn.className   = 'btn btn-sm'; upBtn.textContent  = '↑'; upBtn.disabled = idx === 0;
  upBtn.addEventListener('click', () => builderMoveStep(idx, -1));
  const downBtn = document.createElement('button');
  downBtn.className   = 'btn btn-sm'; downBtn.textContent = '↓';
  downBtn.disabled = idx === builder.steps.length - 1;
  downBtn.addEventListener('click', () => builderMoveStep(idx, 1));
  const delBtn = document.createElement('button');
  delBtn.className   = 'btn btn-sm btn-danger'; delBtn.innerHTML  = icon('x');
  delBtn.addEventListener('click', () => builderDeleteStep(idx));
  btns.appendChild(upBtn); btns.appendChild(downBtn); btns.appendChild(delBtn);
  return btns;
}

// ── Inline payload edit panel (payload-replace only) ─────────────
function _buildPayloadEditPanel(step, idx) {
  const panel = document.createElement('div');
  panel.className    = 'step-edit-panel';
  panel.style.display = 'none';

  const sel = document.createElement('select');
  sel.className = 'step-edit-select';

  function populate() {
    sel.innerHTML = '<option value="">– Replace payload –</option>';
    const favs = state.payloads.filter(p =>  state.payloadFavorites.includes(p.name));
    const rest = state.payloads.filter(p => !state.payloadFavorites.includes(p.name));
    function addGroup(label, items) {
      if (!items.length) return;
      const grp = document.createElement('optgroup');
      grp.label = label;
      items.forEach(p => {
        const opt = document.createElement('option');
        opt.value            = p.name;
        opt.textContent      = (state.payloadFavorites.includes(p.name) ? '★ ' : '') + p.name;
        opt.dataset.autoPort = String(p.auto_port);
        if (p.name === step.filename) opt.selected = true;
        grp.appendChild(opt);
      });
      sel.appendChild(grp);
    }
    addGroup('— Favorites —', favs);
    addGroup(favs.length ? '— All Payloads —' : '— Payloads —', rest);
  }

  sel.addEventListener('change', () => {
    if (!sel.value) return;
    const opt = sel.options[sel.selectedIndex];
    const newP = state.payloads.find(x => x.name === sel.value);
    builder.steps[idx].filename     = sel.value;
    builder.steps[idx].autoPort     = parseInt(opt.dataset.autoPort, 10);
    builder.steps[idx].portOverride = null;
    builder.steps[idx].version      = (newP && newP.source) ? newP.source.version : null;
    panel.style.display = 'none';
    builderRenderList(); scheduleSave();
  });

  const cancelBtn = document.createElement('button');
  cancelBtn.className   = 'btn btn-sm';
  cancelBtn.innerHTML  = icon('x');
  cancelBtn.title       = 'Cancel';
  cancelBtn.addEventListener('click', () => { panel.style.display = 'none'; });

  panel.appendChild(sel);
  panel.appendChild(cancelBtn);
  panel.open = () => { populate(); panel.style.display = panel.style.display === 'none' ? '' : 'none'; };
  return panel;
}

// ── WorkflowStep renderers ────────────────────────────────────────
function _buildPayloadStep(step, idx, stepEl, mainRow, btns) {
  const fn = step.filename.toLowerCase();
  const labelCls = fn.endsWith('.lua') ? 'lua'
                 : fn.endsWith('.jar') ? 'jar'
                 : fn.endsWith('.js')  ? 'js'
                 : 'elf';

  const badge = document.createElement('span');
  badge.className   = `payload-label ${labelCls}`;
  badge.textContent = 'Payload';

  const fnEl = document.createElement('span');
  fnEl.className   = 'step-filename';
  fnEl.textContent = step.filename;
  fnEl.title       = step.filename;

  const portHint = document.createElement('span');
  portHint.className   = 'step-autoport';
  portHint.textContent = `→ ${step.portOverride || step.autoPort}`;

  const editPanel = _buildPayloadEditPanel(step, idx);
  const editBtn   = document.createElement('button');
  editBtn.className   = 'btn btn-sm btn-edit-payload';
  editBtn.textContent = 'Edit';
  editBtn.title       = 'Replace payload';
  editBtn.addEventListener('click', e => { e.stopPropagation(); editPanel.open(); });

  // Row 1: drag + num + badge + run-status + spacer + edit + btns
  mainRow.appendChild(_builderMakeDragHandle(stepEl));
  mainRow.appendChild(_makeStepNum(idx));
  mainRow.appendChild(badge);
  mainRow.appendChild(_makeStepStatusBadge(idx));
  const hSpacer = document.createElement('span'); hSpacer.style.flex = '1';
  mainRow.appendChild(hSpacer);
  mainRow.appendChild(editBtn);
  mainRow.appendChild(btns);
  stepEl.appendChild(mainRow);

  // Row 2: filename (full width, wraps freely)
  const nameRow = document.createElement('div');
  nameRow.className = 'step-name-row';
  nameRow.appendChild(fnEl);
  stepEl.appendChild(nameRow);

  // Row 3: port hint + repo (adv-only) + version dropdown or local label
  const infoRow = document.createElement('div');
  infoRow.className = 'step-info-row';
  infoRow.appendChild(portHint);

  const p = state.payloads.find(x => x.name === step.filename);
  if (p && p.source) {
    if (!step.version) step.version = p.source.version;
    const versions = Array.isArray(p.source.versions) ? p.source.versions : [];
    const curVer   = step.version || p.source.version;

    const repoEl = document.createElement('span');
    repoEl.className   = 'step-src-repo advanced-only';
    repoEl.textContent = p.source.display_name || p.source.repo;
    repoEl.title       = p.source.repo;
    infoRow.appendChild(repoEl);

    if (versions.length >= 1) {
      const verSel = document.createElement('select');
      verSel.className = 'step-ver-inline';
      versions.forEach(v => {
        const opt = document.createElement('option');
        opt.value               = v.tag;
        opt.textContent         = v.tag === p.source.latest_version ? `${v.tag} (latest)` : v.tag;
        opt.dataset.downloadUrl = v.download_url;
        if (v.tag === curVer) opt.selected = true;
        verSel.appendChild(opt);
      });
      verSel.addEventListener('change', () => {
        builder.steps[idx].version = verSel.value;
        scheduleSave();
        showToast(`Step ${idx + 1} → ${verSel.value}`);
      });
      infoRow.appendChild(verSel);
    } else {
      const verSel = document.createElement('select');
      verSel.className = 'step-ver-inline';
      verSel.disabled  = true;
      const opt = document.createElement('option');
      opt.textContent = curVer || 'No versions';
      if (curVer) opt.value = curVer;
      opt.selected = true;
      verSel.appendChild(opt);
      infoRow.appendChild(verSel);
    }
  } else {
    const localEl = document.createElement('span');
    localEl.className   = 'step-local-file';
    localEl.textContent = 'Local file';
    infoRow.appendChild(localEl);
  }
  stepEl.appendChild(infoRow);

  stepEl.appendChild(editPanel);

  // Port override input (advanced only)
  const details   = document.createElement('div');
  details.className = 'step-details advanced-only';
  const portField = document.createElement('div');
  portField.className = 'step-field';
  const portLabel = document.createElement('span');
  portLabel.className = 'step-field-label'; portLabel.textContent = 'Port';
  const portInp = document.createElement('input');
  portInp.type        = 'number'; portInp.className = 'step-input';
  portInp.placeholder = String(step.autoPort); portInp.min = '1'; portInp.max = '65535';
  if (step.portOverride) portInp.value = step.portOverride;
  portInp.addEventListener('input', e => {
    const v = parseInt(e.target.value, 10);
    builder.steps[idx].portOverride = (v > 0 && v <= 65535) ? v : null;
    portHint.textContent = `→ ${builder.steps[idx].portOverride || step.autoPort}`;
    scheduleSave();
  });
  portField.appendChild(portLabel); portField.appendChild(portInp);
  details.appendChild(portField);
  stepEl.appendChild(details);
}

function _buildDelayStep(step, idx, stepEl, mainRow, btns) {
  const badge = document.createElement('span');
  badge.className = 'step-type step-delay'; badge.textContent = 'DELAY';

  // Row 1: drag + num + badge + run-status + spacer + btns
  mainRow.appendChild(_builderMakeDragHandle(stepEl));
  mainRow.appendChild(_makeStepNum(idx));
  mainRow.appendChild(badge);
  mainRow.appendChild(_makeStepStatusBadge(idx));
  const hSpacer = document.createElement('span'); hSpacer.style.flex = '1';
  mainRow.appendChild(hSpacer);
  mainRow.appendChild(btns);
  stepEl.appendChild(mainRow);

  // Row 2: ms value
  const contentRow = document.createElement('div');
  contentRow.className = 'step-content-row';
  const msInp = document.createElement('input');
  msInp.type = 'number'; msInp.className = 'step-input';
  msInp.value = step.ms; msInp.min = '1';
  msInp.addEventListener('input', e => {
    const v = parseInt(e.target.value, 10);
    if (v > 0) { builder.steps[idx].ms = v; scheduleSave(); }
  });
  const msUnit = document.createElement('span');
  msUnit.className = 'step-unit'; msUnit.textContent = 'ms';
  contentRow.appendChild(msInp);
  contentRow.appendChild(msUnit);
  stepEl.appendChild(contentRow);
}

function _buildWaitStep(step, idx, stepEl, mainRow, btns) {
  const badge = document.createElement('span');
  badge.className = 'step-type step-wait'; badge.textContent = 'WAIT';

  // Row 1: drag + num + badge + run-status + spacer + btns
  mainRow.appendChild(_builderMakeDragHandle(stepEl));
  mainRow.appendChild(_makeStepNum(idx));
  mainRow.appendChild(badge);
  mainRow.appendChild(_makeStepStatusBadge(idx));
  const hSpacer = document.createElement('span'); hSpacer.style.flex = '1';
  mainRow.appendChild(hSpacer);
  mainRow.appendChild(btns);
  stepEl.appendChild(mainRow);

  function makeField(labelText, value, min, max, unit, onChange) {
    const field = document.createElement('div');
    field.className = 'step-field';
    const lbl = document.createElement('span');
    lbl.className = 'step-field-label'; lbl.textContent = labelText;
    const inp = document.createElement('input');
    inp.type = 'number'; inp.className = 'step-input';
    inp.value = value; inp.min = String(min);
    if (max) inp.max = String(max);
    inp.addEventListener('input', e => onChange(parseInt(e.target.value, 10)));
    const u = document.createElement('span');
    u.className = 'step-unit'; u.textContent = unit;
    field.appendChild(lbl); field.appendChild(inp); field.appendChild(u);
    return field;
  }

  // Row 2: Port (always visible)
  const portRow = document.createElement('div');
  portRow.className = 'step-content-row';
  portRow.appendChild(makeField('Port', step.port, 1, 65535, '', v => {
    if (v > 0 && v <= 65535) { builder.steps[idx].port = v; scheduleSave(); }
  }));
  stepEl.appendChild(portRow);

  // Row 3: Timeout + Interval (advanced only)
  const advDetails = document.createElement('div');
  advDetails.className = 'step-details advanced-only';
  advDetails.appendChild(makeField('Timeout', step.timeout, 1, null, 's', v => {
    if (v > 0) { builder.steps[idx].timeout = v; scheduleSave(); }
  }));
  advDetails.appendChild(makeField('Interval', step.interval_ms || 500, 100, null, 'ms', v => {
    if (v >= 100) { builder.steps[idx].interval_ms = v; scheduleSave(); }
  }));
  stepEl.appendChild(advDetails);
}

function _buildNotifyStep(step, idx, stepEl, mainRow, btns) {
  const badge = document.createElement('span');
  badge.className = 'step-type step-notify';
  badge.textContent = 'NOTIFY';

  mainRow.appendChild(_builderMakeDragHandle(stepEl));
  mainRow.appendChild(_makeStepNum(idx));
  mainRow.appendChild(badge);
  mainRow.appendChild(_makeStepStatusBadge(idx));
  const hSpacer = document.createElement('span'); hSpacer.style.flex = '1';
  mainRow.appendChild(hSpacer);
  mainRow.appendChild(btns);
  stepEl.appendChild(mainRow);

  // Title + message inline editing
  function makeInput(label, value, onChange, advanced = false) {
    const field = document.createElement('div');
    field.className = 'step-field' + (advanced ? ' advanced-only' : '');
    const lbl = document.createElement('span');
    lbl.className = 'step-field-label'; lbl.textContent = label;
    const inp = document.createElement('input');
    inp.type = 'text'; inp.className = 'step-input';
    inp.style.flex = '1';
    inp.value = value || '';
    inp.addEventListener('input', e => onChange(e.target.value));
    field.appendChild(lbl); field.appendChild(inp);
    return field;
  }

  const row = document.createElement('div');
  row.className = 'step-content-row';
  row.appendChild(makeInput('Title', step.title, v => {
    builder.steps[idx].title = v; scheduleSave();
  }));
  stepEl.appendChild(row);

  const row2 = document.createElement('div');
  row2.className = 'step-content-row';
  row2.appendChild(makeInput('Message', step.message, v => {
    builder.steps[idx].message = v; scheduleSave();
  }));
  stepEl.appendChild(row2);

  const adv = document.createElement('div');
  adv.className = 'step-content-row advanced-only';
  adv.appendChild(makeInput('Override', step.service_override, v => {
    const val = (v || '').trim();
    if (val && !val.startsWith('notify.')) return;   // ignore invalid
    builder.steps[idx].service_override = val; scheduleSave();
  }, true));
  stepEl.appendChild(adv);
}

// ── List render ───────────────────────────────────────────────────
function builderRenderList() {
  const container = document.getElementById('builder-steps');
  container.innerHTML = '';
  // Kept as a no-op call site in case future builder events need
  // to re-evaluate flow-notify-panel visibility after step changes.
  if (typeof flowNotifyRefreshWarn === 'function') flowNotifyRefreshWarn();
  if (!builder.steps.length) {
    container.innerHTML = '<div class="empty-state">Add your first payload to start.</div>';
    return;
  }
  builder.steps.forEach((step, idx) => {
    const stepEl  = document.createElement('div');
    stepEl.className = 'builder-step fade';
    stepEl.dataset.stepIdx = String(idx);
    _builderMakeDragDrop(stepEl, idx);
    const mainRow = document.createElement('div');
    mainRow.className = 'step-main';
    const btns = _builderMakeOrderBtns(idx);

    if      (step.type === 'payload')   _buildPayloadStep(step, idx, stepEl, mainRow, btns);
    else if (step.type === 'delay')     _buildDelayStep(step,   idx, stepEl, mainRow, btns);
    else if (step.type === 'wait_port') _buildWaitStep(step,    idx, stepEl, mainRow, btns);
    else if (step.type === 'notify')    _buildNotifyStep(step,  idx, stepEl, mainRow, btns);
    else                                _buildWaitStep(step,    idx, stepEl, mainRow, btns);

    container.appendChild(stepEl);
  });
  if (typeof updateBuilderSummary === 'function') updateBuilderSummary();
}

function builderMoveStep(idx, dir) {
  const newIdx = idx + dir;
  if (newIdx < 0 || newIdx >= builder.steps.length) return;
  [builder.steps[idx], builder.steps[newIdx]] = [builder.steps[newIdx], builder.steps[idx]];
  builderRenderList(); scheduleSave();
}

function builderDeleteStep(idx) {
  builder.steps.splice(idx, 1);
  builderRenderList(); scheduleSave();
}

function builderGenerate() {
  // Collect one ~version pin per payload filename (first occurrence wins)
  const pins = [];
  const pinned = new Set();
  builder.steps.forEach(step => {
    if (step.type === 'payload' && step.version && !pinned.has(step.filename)) {
      pins.push(`# ~version ${step.filename} ${step.version}`);
      pinned.add(step.filename);
    }
  });
  const directives = builder.steps
    .filter(step => step.type !== 'wait_for_loader')   // deprecated; toggle drives this now
    .map(step => {
    if (step.type === 'payload')
      return step.portOverride ? `${step.filename} ${step.portOverride}` : step.filename;
    if (step.type === 'delay') return `!${step.ms}`;
    if (step.type === 'notify') {
      const t   = (step.title   || '').replace(/"/g, '\\"');
      const msg = (step.message || '').replace(/"/g, '\\"');
      const svc = (step.service_override || '').trim();
      return svc ? `@notify "${t}" "${msg}" ${svc}` : `@notify "${t}" "${msg}"`;
    }
    // wait_port (default)
    const intervalMs = step.interval_ms || 500;
    return `?${step.port} ${step.timeout} ${intervalMs}`;
  });
  // Per-flow notify config header — emitted only if the helper is present
  // and at least one event is enabled or a service is set.
  let header = [];
  if (typeof flowNotifyReadConfig === 'function') {
    const cfg = flowNotifyReadConfig();
    const anyOn = cfg.loader_ready || cfg.flow_started || cfg.flow_completed || cfg.flow_failed;
    if (anyOn || cfg.service) {
      header.push(flowNotifyRenderHeader(cfg));
    }
  }
  return [...header, ...pins, ...directives].join('\n');
}

async function builderSave() {
  if (!builder.steps.length) { alert('No steps to save!'); return; }
  const raw = document.getElementById('builder-profile-name').value.trim();
  if (!raw) { alert('Enter a profile name!'); return; }
  const safe     = raw.replace(/[^a-zA-Z0-9_\-.]/g, '_');
  const filename = safe.endsWith('.txt') ? safe : `${safe}.txt`;
  const content  = `# Created by Auto-Load Builder\n${builderGenerate()}\n`;
  try {
    await api('/api/autoload/content', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile: filename, content }),
    });
    log(`Profile '${filename}' saved`, 'success');
    await refreshProfiles();
    scheduleSave();
  } catch (e) { log('Save: ' + e.message, 'error'); }
}

async function stopAutoload() {
  try {
    await api('/api/autoload/stop', { method: 'POST' });
  } catch (e) { log('Stop: ' + e.message, 'error'); }
}

async function _ensureBuilderVersions() {
  // For each payload step that has a specific version, switch the file to that version
  // before the run starts so the correct binary is sent.
  const seen = {}; // filename → version already set this run
  for (const step of builder.steps) {
    if (step.type !== 'payload' || !step.version) continue;
    if (seen[step.filename] === step.version) continue; // already set
    const p = state.payloads.find(x => x.name === step.filename);
    if (!p || !p.source || p.source.version === step.version) {
      seen[step.filename] = step.version;
      continue;
    }
    const vers    = Array.isArray(p.source.versions) ? p.source.versions : [];
    const target  = vers.find(v => v.tag === step.version);
    if (!target) { log(`Version ${step.version} not found for '${step.filename}', using current`, 'warn'); continue; }
    try {
      log(`Switching '${step.filename}' → ${step.version} …`, 'info');
      await api(`/api/payloads/${encodeURIComponent(step.filename)}/switch-version`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo: p.source.repo, asset_name: p.source.asset,
          download_url: target.download_url, version: step.version,
        }),
      });
      p.source.version = step.version;
      seen[step.filename] = step.version;
    } catch (e) { log(`Pre-switch '${step.filename}': ${e.message}`, 'error'); }
  }
}

// ── Autoload ZIP export ───────────────────────────────────────────
async function exportAutoloadZip() {
  if (!builder.steps.length) { alert('No steps to export!'); return; }

  const lines    = [];
  const payloads = [];
  const warnings = [];

  for (const step of builder.steps) {
    if (step.type === 'delay') {
      lines.push(`!${step.ms}`);
    } else if (step.type === 'wait_port') {
      warnings.push(`WAIT port ${step.port} (not supported by autoloader)`);
    } else if (step.type === 'payload') {
      const fn = step.filename.toLowerCase();
      if (fn.endsWith('.lua')) {
        warnings.push(`Lua payload ${step.filename} (skipped)`);
      } else if (fn.endsWith('.jar')) {
        warnings.push(`JAR payload ${step.filename} (skipped — BD-UN-JB cannot be autoloaded)`);
      } else if (fn.endsWith('.js')) {
        warnings.push(`JS payload ${step.filename} (skipped — Y2JB WebKit-stage cannot be autoloaded)`);
      } else {
        lines.push(step.filename);
        payloads.push(step.filename);
      }
    }
  }

  if (!payloads.length) {
    alert('No exportable payloads in the builder.\nAdd at least one ELF payload.');
    return;
  }

  if (warnings.length) {
    log('Export ZIP — some steps skipped:\n' + warnings.map(w => '  • ' + w).join('\n'), 'warn');
    showToast(`${warnings.length} step${warnings.length > 1 ? 's' : ''} skipped — check log`);
  }

  try {
    const res = await fetch(BASE + '/api/autoload/export-zip', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ autoload_txt: lines.join('\n') + '\n', payloads }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = Object.assign(document.createElement('a'), { href: url, download: 'autoload.zip' });
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    if (!warnings.length) showToast('autoload.zip downloaded');
  } catch (e) {
    showToast('Export failed: ' + e.message);
    log('Export ZIP: ' + e.message, 'error');
  }
}

async function builderRunDirect() {
  if (!builder.steps.length) { alert('No steps to run!'); return; }
  const host = getHost(); if (!host) return;
  if (state.execState === 'running' || state.execState === 'paused') {
    showToast('Already running'); return;
  }
  clearStepRunStatus();
  _setBuilderRunning(true);
  state.execState = 'running'; // optimistic guard – prevents second click racing in
  try {
    // Ensure each step's payload is at the correct version before sending
    await _ensureBuilderVersions();

    const tmpProfile = '_builder_run.txt';
    const content    = `# Auto-Load Builder direct run\n${builderGenerate()}\n`;
    await api('/api/autoload/content', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile: tmpProfile, content }),
    });
    await api('/api/autoload/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ host, profile: tmpProfile, continue_on_error: false }),
    });
  } catch (e) {
    if (e.message.includes('409')) {
      showToast('Already running');
    } else {
      log('Run: ' + e.message, 'error');
    }
  } finally {
    _setBuilderRunning(false);
  }
}
