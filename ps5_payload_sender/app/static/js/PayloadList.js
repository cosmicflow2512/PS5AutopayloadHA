'use strict';

// ── Payload List ─────────────────────────────────────────────────
async function refreshPayloads() {
  try {
    const data = await api('/api/payloads');
    state.payloads = data.payloads || [];
    // Remove stale selections
    state.selectedPayloads = new Set(
      [...(state.selectedPayloads || new Set())].filter(
        n => state.payloads.some(p => p.name === n)
      )
    );
    renderPayloadFilters();
    renderPayloads();
    if (typeof updatePayloadsSummary === 'function') updatePayloadsSummary();
  } catch (e) { log('Load payloads: ' + e.message, 'error'); }
}

function renderPayloads() {
  builderUpdatePayloadDropdown();
  const c        = document.getElementById('payload-list');
  c.innerHTML    = '';
  const filtered = getFilteredPayloads();
  if (!filtered.length) {
    const query = (state.payloadSearch || '').trim();
    c.innerHTML = `<div class="empty-state">${
      query
        ? 'No payloads found.'
        : state.payloadFilter === 'favorites'
          ? 'No favorites yet. Click ★ on a payload to add it.'
          : 'No payloads. Upload a .lua, .elf or .bin file.'
    }</div>`;
    renderBulkBar();
    return;
  }
  filtered.forEach(p => c.appendChild(buildPayloadItem(p)));
  renderBulkBar();
}

function renderBulkBar() {
  const bar = document.getElementById('bulk-action-bar');
  if (!bar) return;
  const sel = state.selectedPayloads || new Set();
  if (sel.size === 0) {
    bar.style.display = 'none';
    return;
  }
  bar.style.display = '';
  const countEl = bar.querySelector('#bulk-count');
  if (countEl) countEl.textContent = `${sel.size} selected`;
  // Sync select-all checkbox
  const allCb = document.getElementById('payload-select-all');
  if (allCb) {
    const filtered = getFilteredPayloads();
    allCb.checked = filtered.length > 0 && filtered.every(p => sel.has(p.name));
    allCb.indeterminate = sel.size > 0 && !allCb.checked;
  }
}

function buildPayloadItem(p) {
  const isFav = state.payloadFavorites.includes(p.name);
  const isSel = (state.selectedPayloads || new Set()).has(p.name);
  const el    = document.createElement('div');
  el.className = 'payload-item fade' + (isFav ? ' payload-fav' : '') + (isSel ? ' payload-selected' : '');

  // ── Row 1: checkbox + badge + name ───────────────────────────────
  const rowTop = document.createElement('div');
  rowTop.className = 'p-row-top';

  const cb = document.createElement('input');
  cb.type    = 'checkbox'; cb.className = 'p-checkbox'; cb.checked = isSel;
  cb.addEventListener('change', e => {
    e.stopPropagation();
    if (!state.selectedPayloads) state.selectedPayloads = new Set();
    if (cb.checked) state.selectedPayloads.add(p.name);
    else            state.selectedPayloads.delete(p.name);
    el.classList.toggle('payload-selected', cb.checked);
    renderBulkBar();
  });

  const badge = document.createElement('span');
  badge.className  = `badge ${p.ext === '.lua' ? 'badge-lua' : 'badge-elf'}`;
  if (p.ext === '.bin') badge.title = 'Treated as ELF — sent to port 9021';
  badge.textContent = p.ext.replace('.', '').toUpperCase();

  const name = document.createElement('span');
  name.className  = 'p-name'; name.textContent = p.name;

  rowTop.appendChild(cb); rowTop.appendChild(badge); rowTop.appendChild(name);

  // ── Row 2: meta + port override + actions ────────────────────────
  const rowBot = document.createElement('div');
  rowBot.className = 'p-row-bottom';

  const meta = document.createElement('span');
  meta.className  = 'p-meta';
  meta.textContent = fmt(p.size) + (p.mtime ? '  ' + fmtDate(p.mtime) : '');

  const portInput       = document.createElement('input');
  portInput.type        = 'number';
  portInput.className   = 'p-port-input advanced-only';
  portInput.placeholder = String(p.auto_port);
  portInput.min         = '1';
  portInput.max         = '65535';
  portInput.title       = 'Override port (empty = auto)';

  const favBtn = document.createElement('button');
  favBtn.className   = 'p-fav' + (isFav ? ' p-fav-active' : '');
  favBtn.innerHTML  = icon('star', {filled:true});
  favBtn.title       = isFav ? 'Remove from favorites' : 'Add to favorites';
  favBtn.addEventListener('click', e => { e.stopPropagation(); togglePayloadFavorite(p.name); });

  const sendBtn = document.createElement('button');
  sendBtn.className   = 'p-send';
  sendBtn.innerHTML  = icon('play') + ' Send to PS5';
  sendBtn.addEventListener('click', async e => {
    e.stopPropagation();
    await sendDirect(p.name, p.auto_port, portInput, sendBtn);
  });

  const del = document.createElement('button');
  del.className   = 'p-del';
  del.innerHTML  = icon('x');
  del.title       = 'Delete';
  del.addEventListener('click', async e => {
    e.stopPropagation();
    if (!confirm(`Delete '${p.name}'?`)) return;
    try {
      await api(`/api/payloads/${encodeURIComponent(p.name)}`, { method: 'DELETE' });
      state.payloadFavorites = state.payloadFavorites.filter(f => f !== p.name);
      if (state.selectedPayloads) state.selectedPayloads.delete(p.name);
      await refreshPayloads();
      log(`'${p.name}' deleted`);
    } catch (err) { log('Delete: ' + err.message, 'error'); }
  });

  rowBot.appendChild(meta);
  rowBot.appendChild(portInput); rowBot.appendChild(favBtn);
  rowBot.appendChild(sendBtn); rowBot.appendChild(del);

  el.appendChild(rowTop);
  el.appendChild(rowBot);

  // ── Row 3: source info + version (always rendered) ──────────────
  {
    const rowSrc = document.createElement('div');
    rowSrc.className = 'p-row-source';

    if (p.source) {
      // GitHub-sourced payload
      const srcBadge = document.createElement('span');
      srcBadge.className   = 'source-badge';
      srcBadge.textContent = '⎔ ' + (p.source.display_name || p.source.repo);
      srcBadge.title       = p.source.repo;
      rowSrc.appendChild(srcBadge);

      const versions = Array.isArray(p.source.versions) ? p.source.versions : [];
      if (versions.length > 0) {
        const verSel = document.createElement('select');
        verSel.className = 'p-ver-select';
        versions.forEach((v, i) => {
          const opt = document.createElement('option');
          opt.value               = v.tag;
          opt.textContent         = v.tag === p.source.latest_version ? `${v.tag} (latest)` : v.tag;
          opt.dataset.downloadUrl = v.download_url;
          if (v.tag === p.source.version) opt.selected = true;
          verSel.appendChild(opt);
        });
        verSel.addEventListener('change', async () => {
          const newVer = verSel.value;
          if (newVer === p.source.version) return;
          try {
            await api(`/api/payloads/${encodeURIComponent(p.name)}/set-default-version`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ version: newVer }),
            });
            p.source.version = newVer;
            showToast(`Default → ${newVer}`);
            renderPayloadList();
          } catch (e) {
            log('Set default version: ' + e.message, 'error');
            verSel.value = p.source.version;
          }
        });
        rowSrc.appendChild(verSel);
      } else {
        // No version history — show disabled dropdown with appropriate message
        const verSel = document.createElement('select');
        verSel.className = 'p-ver-select';
        verSel.disabled  = true;
        const opt = document.createElement('option');
        opt.textContent = p.source.version || 'No versions available';
        if (p.source.version) opt.value = p.source.version;
        opt.selected = true;
        verSel.appendChild(opt);
        rowSrc.appendChild(verSel);
      }
    } else {
      // Local payload — no source control
      const localBadge = document.createElement('span');
      localBadge.className   = 'p-local-file';
      localBadge.textContent = 'Local file · No version control';
      rowSrc.appendChild(localBadge);
    }

    // ── Update / up-to-date indicator (sourced payloads only) ────────
    const updateInfo = p.source ? (state.updateResults || {})[p.name] : null;
    if (p.source && updateInfo) {
      // New version available
      const warnEl = document.createElement('span');
      warnEl.className   = 'payload-update-warn';
      warnEl.innerHTML  = icon('alert-triangle') + ` ${updateInfo.latest_version}`;
      warnEl.title       = 'New version available on GitHub';
      const updBtn = document.createElement('button');
      updBtn.className   = 'btn btn-sm source-update-btn';
      updBtn.textContent = 'Update flows';
      updBtn.addEventListener('click', async ev => {
        ev.stopPropagation();
        updBtn.disabled    = true;
        updBtn.textContent = 'Loading…';
        let usedInProfiles = [];
        try {
          const u = await api(`/api/payloads/${encodeURIComponent(p.name)}/usage`);
          usedInProfiles = u.used_in || [];
        } catch (_) {}
        // Fetch version-pin metadata for each used flow in parallel
        const flowDetails = {};
        await Promise.all(usedInProfiles.map(async name => {
          const fname = name.endsWith('.txt') ? name : name + '.txt';
          try {
            const data = await api(`/api/autoload/parse/${encodeURIComponent(fname)}`);
            flowDetails[name] = { versionPin: (data.version_pins || {})[p.name] || null };
          } catch (_) {}
        }));
        const builderMatches = builder.steps
          .map((s, idx) => ({ step: s, idx }))
          .filter(({ step }) => step.type === 'payload' && step.filename === p.name);
        updBtn.disabled    = false;
        updBtn.textContent = 'Update flows';
        _openUpdateFlowsDialog(p, updateInfo, usedInProfiles, builderMatches, flowDetails);
      });
      rowSrc.appendChild(warnEl);
      rowSrc.appendChild(updBtn);
    } else if (p.source && state.updateCheckDone) {
      // Check has run and this payload is current
      const upToDate = document.createElement('span');
      upToDate.className   = 'payload-uptodate';
      upToDate.textContent = '✔ Up to date';
      rowSrc.appendChild(upToDate);
    }

    // ── Builder / saved-flow usage: "Apply to flows" button or simple badge ──
    // (Distinct from the "Update flows" button above: this one applies the
    // currently-selected dropdown version to all flows that reference this
    // payload, while "Update flows" pulls a newer version from GitHub.)
    {
      const builderMatches = builder.steps
        .map((s, idx) => ({ step: s, idx }))
        .filter(({ step }) => step.type === 'payload' && step.filename === p.name);
      const hasMultiVer = (Array.isArray(p.source && p.source.versions) ? p.source.versions : []).length > 1;
      if (builderMatches.length && hasMultiVer) {
        const updBtn = document.createElement('button');
        updBtn.className   = 'btn btn-sm source-apply-btn';
        updBtn.textContent = 'Apply to flows';
        updBtn.title       = 'Apply the currently selected version to every flow that uses this payload';
        updBtn.addEventListener('click', async ev => {
          ev.stopPropagation();
          updBtn.disabled    = true;
          updBtn.textContent = 'Loading…';
          console.log('Scanning flows for payload:', p.name);
          let usedInProfiles = [];
          try {
            const u = await api(`/api/payloads/${encodeURIComponent(p.name)}/usage`);
            usedInProfiles = u.used_in || [];
          } catch (_) {}
          const flowDetails = {};
          await Promise.all(usedInProfiles.map(async name => {
            const fname = name.endsWith('.txt') ? name : name + '.txt';
            try {
              const data = await api(`/api/autoload/parse/${encodeURIComponent(fname)}`);
              const pin  = (data.version_pins || {})[p.name] || null;
              flowDetails[name] = { versionPin: pin };
              console.log('Found in flow:', name, 'pin:', pin);
            } catch (_) {}
          }));
          if (usedInProfiles.length + builderMatches.length <= 1) {
            console.log('Only 1 usage found. All flows:', state.profiles);
          }
          updBtn.disabled    = false;
          updBtn.textContent = 'Apply to flows';
          _openUpdateUsagesDialog(p, builderMatches, usedInProfiles, flowDetails);
        });
        rowSrc.appendChild(updBtn);
      } else if (builderMatches.length) {
        const usedWarn = document.createElement('span');
        usedWarn.className   = 'payload-used-warn';
        usedWarn.textContent = 'In builder';
        usedWarn.title       = `Used in ${builderMatches.length} builder step${builderMatches.length > 1 ? 's' : ''}`;
        rowSrc.appendChild(usedWarn);
      }
    }

    // Rollback button if backup exists (sourced payloads only)
    if (p.source && p.source.backup_version) {
      const rbBtn = document.createElement('button');
      rbBtn.className   = 'btn btn-sm';
      rbBtn.textContent = `↩ ${p.source.backup_version}`;
      rbBtn.title       = 'Rollback to previous version';
      rbBtn.style.marginLeft = 'auto';
      rbBtn.addEventListener('click', async ev => {
        ev.stopPropagation();
        if (!confirm(`Roll back '${p.name}' to ${p.source.backup_version}?`)) return;
        rbBtn.disabled = true; rbBtn.textContent = 'Rolling back…';
        try {
          await api(`/api/payloads/${encodeURIComponent(p.name)}/rollback`, { method: 'POST' });
          showToast(`Rolled back to ${p.source.backup_version}`);
          await refreshPayloads();
        } catch (e) {
          log('Rollback: ' + e.message, 'error');
          rbBtn.disabled = false; rbBtn.textContent = `↩ ${p.source.backup_version}`;
        }
      });
      rowSrc.appendChild(rbBtn);
    }

    el.appendChild(rowSrc);
  }

  return el;
}

function togglePayloadFavorite(filename) {
  if (state.payloadFavorites.includes(filename)) {
    state.payloadFavorites = state.payloadFavorites.filter(f => f !== filename);
  } else {
    state.payloadFavorites.push(filename);
  }
  renderPayloads();
  scheduleSave();
}

async function sendDirect(filename, autoPort, portInput, btn) {
  const host    = getHost(); if (!host) return;
  const portVal = parseInt(portInput.value, 10);
  const port    = (portVal > 0 && portVal <= 65535) ? portVal : autoPort;
  btn.disabled  = true; btn.textContent = 'Sending…';
  try {
    await api('/api/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ host, filename, port }),
    });
    btn.textContent = 'Sent ✔'; btn.className = 'p-send ok';
  } catch (e) {
    log('Send: ' + e.message, 'error');
    btn.textContent = 'Failed ❌'; btn.className = 'p-send err';
  }
  setTimeout(() => { btn.disabled = false; btn.innerHTML  = icon('play') + ' Send to PS5'; btn.className = 'p-send'; }, 2500);
}

async function bulkDeleteSelected() {
  const sel = state.selectedPayloads;
  if (!sel || sel.size === 0) return;
  if (!confirm(`Delete ${sel.size} payload(s)? This cannot be undone.`)) return;
  const names = [...sel];
  let deleted = 0;
  for (const name of names) {
    try {
      await api(`/api/payloads/${encodeURIComponent(name)}`, { method: 'DELETE' });
      state.payloadFavorites = state.payloadFavorites.filter(f => f !== name);
      deleted++;
    } catch (e) { log(`Delete '${name}': ${e.message}`, 'error'); }
  }
  state.selectedPayloads = new Set();
  await refreshPayloads();
  if (deleted > 0) { log(`${deleted} payload(s) deleted`, 'success'); showToast(`${deleted} payload(s) deleted`); }
}

function _openUpdateFlowsDialog(p, updateInfo, usedInProfiles, builderMatches, flowDetails) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  const box = document.createElement('div');
  box.className = 'modal-box';

  const title = document.createElement('div');
  title.className   = 'modal-title';
  title.textContent = `Update — ${p.name}`;
  box.appendChild(title);

  const verInfo = document.createElement('div');
  verInfo.className   = 'modal-ver-info';
  verInfo.textContent = `New version: ${updateInfo.latest_version}`;
  box.appendChild(verInfo);

  const allCbs = [];  // all checkboxes for updateConfirmBtn + select-all
  let builderCb = null;

  if (usedInProfiles.length || builderMatches.length) {
    const totalRows = usedInProfiles.length + (builderMatches.length ? 1 : 0);
    if (totalRows > 1) {
      const quickRow = document.createElement('div');
      quickRow.className = 'modal-quick-row';
      const selAll = document.createElement('button');
      selAll.className   = 'btn-link'; selAll.textContent = 'Select all';
      selAll.addEventListener('click', () => { allCbs.forEach(cb => { cb.disabled || (cb.checked = true); }); sync(); });
      const deselAll = document.createElement('button');
      deselAll.className   = 'btn-link'; deselAll.textContent = 'Deselect all';
      deselAll.addEventListener('click', () => { allCbs.forEach(cb => { cb.disabled || (cb.checked = false); }); sync(); });
      quickRow.appendChild(selAll);
      quickRow.appendChild(deselAll);
      box.appendChild(quickRow);
    }

    const flowList = document.createElement('div');
    flowList.className = 'modal-step-list';

    usedInProfiles.forEach(name => {
      const detail        = (flowDetails || {})[name] || {};
      const currentVer    = detail.versionPin || null;
      const upToDate      = currentVer === updateInfo.latest_version;

      const label = document.createElement('label');
      label.className = 'modal-step-row modal-flow-group';

      const cb = document.createElement('input');
      cb.type             = 'checkbox';
      cb.checked          = !upToDate;
      cb.disabled         = upToDate;
      cb.dataset.flowName = name;
      allCbs.push(cb);
      cb.addEventListener('change', sync);

      const wrap     = document.createElement('span'); wrap.className = 'modal-flow-label';
      const nameSpan = document.createElement('span'); nameSpan.className = 'modal-flow-name';
      nameSpan.textContent = name;
      const verSpan  = document.createElement('span'); verSpan.className = 'modal-flow-ver';
      verSpan.textContent = upToDate
        ? 'already up-to-date'
        : currentVer
          ? `${currentVer}  →  ${updateInfo.latest_version}`
          : `→  ${updateInfo.latest_version}`;

      wrap.appendChild(nameSpan); wrap.appendChild(verSpan);
      label.appendChild(cb); label.appendChild(wrap);
      flowList.appendChild(label);
    });

    if (builderMatches.length) {
      const flowName = (document.getElementById('builder-profile-name').value || '').trim() || 'Builder';
      const fromVers = [...new Set(builderMatches.map(m => m.step.version || '(unset)'))];
      const label    = document.createElement('label');
      label.className = 'modal-step-row modal-flow-group';
      builderCb       = document.createElement('input');
      builderCb.type    = 'checkbox';
      builderCb.checked = false;
      allCbs.push(builderCb);
      builderCb.addEventListener('change', sync);
      const wrap     = document.createElement('span'); wrap.className = 'modal-flow-label';
      const nameSpan = document.createElement('span'); nameSpan.className = 'modal-flow-name';
      nameSpan.textContent = builderMatches.length > 1
        ? `${flowName}  (${builderMatches.length} usages)`
        : flowName;
      const verSpan  = document.createElement('span'); verSpan.className = 'modal-flow-ver';
      verSpan.textContent = `${fromVers.join(', ')}  →  ${updateInfo.latest_version}`;
      wrap.appendChild(nameSpan); wrap.appendChild(verSpan);
      label.appendChild(builderCb); label.appendChild(wrap);
      flowList.appendChild(label);
    }

    box.appendChild(flowList);
  }

  const btnRow = document.createElement('div');
  btnRow.className = 'modal-btn-row';

  const cancelBtn = document.createElement('button');
  cancelBtn.className   = 'btn btn-sm';
  cancelBtn.textContent = 'Cancel';
  cancelBtn.addEventListener('click', () => overlay.remove());

  const confirmBtn = document.createElement('button');
  confirmBtn.className   = 'btn btn-sm btn-primary';
  confirmBtn.textContent = 'Update selected';

  function sync() {
    confirmBtn.disabled = !allCbs.some(cb => cb.checked);
  }
  sync();

  confirmBtn.addEventListener('click', async () => {
    confirmBtn.disabled    = true;
    confirmBtn.textContent = 'Updating…';
    try {
      await api(`/api/payloads/${encodeURIComponent(p.name)}/switch-version`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo:         updateInfo.repo,
          asset_name:   updateInfo.asset_name,
          download_url: updateInfo.download_url,
          version:      updateInfo.latest_version,
        }),
      });
      // Patch version pins in each checked saved flow
      const savedChecked = allCbs.filter(cb => cb.checked && cb.dataset.flowName);
      await Promise.all(savedChecked.map(cb =>
        api(`/api/autoload/patch-versions/${encodeURIComponent(cb.dataset.flowName + '.txt')}`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ filename: p.name, version: updateInfo.latest_version }),
        })
      ));
      if (builderCb && builderCb.checked) {
        builderMatches.forEach(({ idx }) => { builder.steps[idx].version = updateInfo.latest_version; });
        scheduleSave();
      }
      delete state.updateResults[p.name];
      overlay.remove();
      showToast(`Updated to ${updateInfo.latest_version}`);
      await refreshPayloads();
      if (typeof checkAllUpdates === 'function') checkAllUpdates();
    } catch (e) {
      log('Update: ' + e.message, 'error');
      confirmBtn.disabled    = false;
      confirmBtn.textContent = 'Update selected';
    }
  });

  btnRow.appendChild(cancelBtn);
  btnRow.appendChild(confirmBtn);
  box.appendChild(btnRow);
  overlay.appendChild(box);
  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
  document.body.appendChild(overlay);
}

function _openUpdateUsagesDialog(p, stepMatches, usedInProfiles, flowDetails) {
  const targetVer  = p.source.version;
  const builderName = (document.getElementById('builder-profile-name').value || '').trim() || 'Builder';
  usedInProfiles = usedInProfiles || [];
  flowDetails    = flowDetails    || {};

  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  const box = document.createElement('div');
  box.className = 'modal-box';

  const title = document.createElement('div');
  title.className   = 'modal-title';
  title.textContent = `Apply to flows — ${p.name}`;
  box.appendChild(title);

  const verInfo = document.createElement('div');
  verInfo.className   = 'modal-ver-info';
  verInfo.textContent = `Target version: ${targetVer}`;
  box.appendChild(verInfo);

  const allCbs = [];

  const totalRows = usedInProfiles.length + (stepMatches.length ? 1 : 0);
  if (totalRows > 1) {
    const quickRow = document.createElement('div');
    quickRow.className = 'modal-quick-row';
    const selAll = document.createElement('button');
    selAll.className   = 'btn-link'; selAll.textContent = 'Select all';
    selAll.addEventListener('click', () => { allCbs.forEach(cb => { cb.disabled || (cb.checked = true); }); sync(); });
    const deselAll = document.createElement('button');
    deselAll.className   = 'btn-link'; deselAll.textContent = 'Deselect all';
    deselAll.addEventListener('click', () => { allCbs.forEach(cb => { cb.disabled || (cb.checked = false); }); sync(); });
    quickRow.appendChild(selAll);
    quickRow.appendChild(deselAll);
    box.appendChild(quickRow);
  }

  const flowList = document.createElement('div');
  flowList.className = 'modal-step-list';

  // Saved flows
  usedInProfiles.forEach(name => {
    const currentVer = (flowDetails[name] || {}).versionPin || null;
    const upToDate   = currentVer === targetVer;
    const label      = document.createElement('label');
    label.className  = 'modal-step-row modal-flow-group';
    const cb         = document.createElement('input');
    cb.type             = 'checkbox';
    cb.checked          = !upToDate;
    cb.disabled         = upToDate;
    cb.dataset.flowName = name;
    allCbs.push(cb);
    cb.addEventListener('change', sync);
    const wrap     = document.createElement('span'); wrap.className = 'modal-flow-label';
    const nameSpan = document.createElement('span'); nameSpan.className = 'modal-flow-name';
    nameSpan.textContent = name;
    const verSpan  = document.createElement('span'); verSpan.className = 'modal-flow-ver';
    verSpan.textContent = upToDate
      ? 'already up-to-date'
      : currentVer ? `${currentVer}  →  ${targetVer}` : `→  ${targetVer}`;
    wrap.appendChild(nameSpan); wrap.appendChild(verSpan);
    label.appendChild(cb); label.appendChild(wrap);
    flowList.appendChild(label);
  });

  // Builder steps grouped by current version
  if (stepMatches.length) {
    const byVer = {};
    stepMatches.forEach(({ step, idx }) => {
      const v = step.version || '(unset)';
      if (!byVer[v]) byVer[v] = [];
      byVer[v].push(idx);
    });
    Object.entries(byVer).forEach(([fromVer, idxList]) => {
      const upToDate = fromVer === targetVer;
      const label    = document.createElement('label');
      label.className = 'modal-step-row modal-flow-group';
      const cb        = document.createElement('input');
      cb.type                = 'checkbox';
      cb.checked             = !upToDate;
      cb.disabled            = upToDate;
      cb.dataset.stepIdxList = JSON.stringify(idxList);
      allCbs.push(cb);
      cb.addEventListener('change', sync);
      const wrap     = document.createElement('span'); wrap.className = 'modal-flow-label';
      const nameSpan = document.createElement('span'); nameSpan.className = 'modal-flow-name';
      nameSpan.textContent = idxList.length > 1
        ? `${builderName}  (${idxList.length} usages)`
        : builderName;
      const verSpan  = document.createElement('span'); verSpan.className = 'modal-flow-ver';
      verSpan.textContent = upToDate ? 'already up-to-date' : `${fromVer}  →  ${targetVer}`;
      wrap.appendChild(nameSpan); wrap.appendChild(verSpan);
      label.appendChild(cb); label.appendChild(wrap);
      flowList.appendChild(label);
    });
  }

  box.appendChild(flowList);

  const btnRow = document.createElement('div');
  btnRow.className = 'modal-btn-row';

  const cancelBtn = document.createElement('button');
  cancelBtn.className   = 'btn btn-sm';
  cancelBtn.textContent = 'Cancel';
  cancelBtn.addEventListener('click', () => overlay.remove());

  const confirmBtn = document.createElement('button');
  confirmBtn.className   = 'btn btn-sm btn-primary';
  confirmBtn.textContent = 'Update selected';

  function sync() { confirmBtn.disabled = !allCbs.some(cb => cb.checked); }
  sync();

  confirmBtn.addEventListener('click', async () => {
    confirmBtn.disabled    = true;
    confirmBtn.textContent = 'Updating…';
    // Patch saved flows
    const savedChecked = allCbs.filter(cb => cb.checked && cb.dataset.flowName);
    try {
      await Promise.all(savedChecked.map(cb =>
        api(`/api/autoload/patch-versions/${encodeURIComponent(cb.dataset.flowName + '.txt')}`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ filename: p.name, version: targetVer }),
        })
      ));
    } catch (e) { log('Patch flow versions: ' + e.message, 'error'); }
    // Update builder steps
    const allIdxs = [];
    allCbs.filter(cb => cb.checked && cb.dataset.stepIdxList).forEach(cb => {
      JSON.parse(cb.dataset.stepIdxList).forEach(i => allIdxs.push(i));
    });
    allIdxs.forEach(i => { builder.steps[i].version = targetVer; });
    if (allIdxs.length) scheduleSave();
    const total = savedChecked.length + allIdxs.length;
    showToast(`Updated ${total} usage${total !== 1 ? 's' : ''} to ${targetVer}`);
    overlay.remove();
    renderPayloadList();
    if (typeof builderRenderList === 'function') builderRenderList();
  });

  btnRow.appendChild(cancelBtn);
  btnRow.appendChild(confirmBtn);
  box.appendChild(btnRow);
  overlay.appendChild(box);
  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
  document.body.appendChild(overlay);
}

async function uploadPayloads(files) {
  if (!files || !files.length) return;
  const bar   = document.getElementById('upload-bar');
  const label = document.getElementById('upload-label');
  const prog  = document.getElementById('upload-progress');
  prog.style.display = 'block';
  for (let i = 0; i < files.length; i++) {
    label.textContent   = `${files[i].name} (${i + 1}/${files.length})`;
    bar.style.width     = `${(i / files.length) * 100}%`;
    const fd = new FormData(); fd.append('file', files[i]);
    try {
      const d = await api('/api/payloads/upload', { method: 'POST', body: fd });
      log(`'${d.filename}' uploaded (${fmt(d.size)}, port ${d.auto_port})`, 'success');
    } catch (e) { log(`Upload '${files[i].name}': ${e.message}`, 'error'); }
  }
  bar.style.width   = '100%';
  label.textContent = 'Done!';
  setTimeout(() => { prog.style.display = 'none'; bar.style.width = '0'; }, 2000);
  document.getElementById('payload-upload').value = '';
  await refreshPayloads();
}
