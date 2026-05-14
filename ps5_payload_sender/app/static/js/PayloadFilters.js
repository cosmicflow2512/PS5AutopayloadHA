'use strict';

// ── Payload Filters ──────────────────────────────────────────────
const FILTER_DEFS = [
  { key: 'all',       label: 'All'           },
  { key: 'favorites', label: '★ Favorites'  },
  { key: 'elf',       label: 'ELF'           },
  { key: 'lua',       label: 'LUA'           },
];

function renderPayloadFilters() {
  const container = document.getElementById('payload-filters');
  if (!container) return;
  container.innerHTML = '';
  FILTER_DEFS.forEach(({ key, label }) => {
    const btn = document.createElement('button');
    btn.className = 'filter-btn' + (state.payloadFilter === key ? ' filter-active' : '');
    btn.textContent = label;
    btn.addEventListener('click', () => setPayloadFilter(key));
    container.appendChild(btn);
  });
}

function setPayloadFilter(filter) {
  state.payloadFilter = filter;
  renderPayloadFilters();
  renderPayloads();
  scheduleSave();
}

function getFilteredPayloads() {
  const query = (state.payloadSearch || '').trim().toLowerCase();
  let pool = state.payloads;

  // Apply type filter first
  if (state.payloadFilter === 'favorites') {
    pool = pool.filter(p => state.payloadFavorites.includes(p.name));
  } else if (state.payloadFilter === 'elf') {
    pool = pool.filter(p => p.ext === '.elf' || p.ext === '.bin');
  } else if (state.payloadFilter === 'lua') {
    pool = pool.filter(p => p.ext === '.lua');
  }

  // Apply search
  if (query) {
    pool = pool.filter(p => p.name.toLowerCase().includes(query));
    // Smart sort: names that START with query come first
    pool.sort((a, b) => {
      const aStarts = a.name.toLowerCase().startsWith(query);
      const bStarts = b.name.toLowerCase().startsWith(query);
      if (aStarts && !bStarts) return -1;
      if (!aStarts && bStarts) return 1;
      return 0;
    });
    // Favorites still float to top within each group
    const favs = pool.filter(p =>  state.payloadFavorites.includes(p.name));
    const rest = pool.filter(p => !state.payloadFavorites.includes(p.name));
    return [...favs, ...rest];
  }

  // No search: favorites float to top
  const favs = pool.filter(p =>  state.payloadFavorites.includes(p.name));
  const rest = pool.filter(p => !state.payloadFavorites.includes(p.name));
  return [...favs, ...rest];
}
