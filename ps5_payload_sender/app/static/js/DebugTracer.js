'use strict';

// ── Debug Tracer (Advanced Mode) ─────────────────────────────────
// Intercepts all api() calls and named button clicks when Advanced
// Mode is on, logging them at trace level so the Execution Log can
// be filtered to "Trace" for a step-by-step view of what happened.

const _origApi = typeof api === 'function' ? api : null;

function initTracer() {
  if (!_origApi) return;

  // Replace the global api() with a tracing wrapper.
  // Because every call site resolves `api` from the global scope at
  // call time (not at definition time) this intercepts all callers.
  window.api = async function tracedApi(path, opts = {}) {
    if (!state.advancedMode) return _origApi(path, opts);

    const method = (opts.method || 'GET').toUpperCase();
    const t0 = Date.now();
    dtrace(`→ ${method} ${path}`);

    try {
      const result = await _origApi(path, opts);
      const ms = Date.now() - t0;

      // Summarise large payloads so the log stays readable
      let summary = '';
      if (result && typeof result === 'object') {
        const keys = Object.keys(result);
        if (keys.length <= 5) {
          summary = keys.map(k => {
            const v = result[k];
            if (Array.isArray(v))       return `${k}[${v.length}]`;
            if (typeof v === 'object' && v) return `${k}{…}`;
            return `${k}=${JSON.stringify(v)}`;
          }).join(' ');
        } else {
          summary = `{${keys.slice(0, 5).join(', ')}, …}`;
        }
      }
      dtrace(`← ${method} ${path} ${ms}ms${summary ? '  ' + summary : ''}`);
      return result;
    } catch (err) {
      const ms = Date.now() - t0;
      dtrace(`✗ ${method} ${path} ${ms}ms  ${err.message}`);
      throw err;
    }
  };

  // Log named button and link clicks.
  document.addEventListener('click', _onTracerClick, true);
}

function _onTracerClick(e) {
  if (!state.advancedMode) return;
  const el = e.target.closest('button, a[href], [data-trace]');
  if (!el) return;
  const tag   = el.tagName.toLowerCase();
  const label = (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 70);
  const id    = el.id ? `#${el.id}` : '';
  if (label || id) dtrace(`Click ${tag}${id}${label ? ` "${label}"` : ''}`);
}
