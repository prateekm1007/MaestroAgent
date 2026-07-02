// VIRTUALIZATION — render only visible items for large lists
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Render a large list with windowing — only visible items are in the DOM.
 * Uses IntersectionObserver for infinite scroll.
 *
 * @param {HTMLElement} container - The scroll container
 * @param {Array} items - All items
 * @param {Function} renderFn - (item, index) => HTML string
 * @param {number} pageSize - Items per page (default 50)
 */
function renderVirtualized(container, items, renderFn, pageSize = 50) {
  let visibleCount = Math.min(pageSize, items.length);
  let offset = 0;

  function renderPage() {
    const page = items.slice(0, visibleCount);
    container.innerHTML = page.map((item, i) => renderFn(item, i)).join('');

    // Add "Load more" sentinel if there are more items
    if (visibleCount < items.length) {
      const sentinel = document.createElement('div');
      sentinel.id = 'virtualized-sentinel';
      sentinel.className = 'text-center py-3 text-[11px] text-fg-500 cursor-pointer hover:text-fg-300';
      sentinel.textContent = `Load more (${items.length - visibleCount} remaining)`;
      sentinel.onclick = () => {
        visibleCount = Math.min(visibleCount + pageSize, items.length);
        renderPage();
      };
      container.appendChild(sentinel);
    }
  }

  renderPage();
}

function formatConfidence(c) {
  if (c == null) return '—';
  return Number(c).toFixed(2);
}

function formatTimestamp(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return escapeHtml(ts);
    return d.toLocaleString();
  } catch (e) {
    return escapeHtml(ts);
  }
}

function loadingHTML(el, msg) {
  el.innerHTML = `<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>`;
}
function errorHTML(el, msg, retryFn) {
  const retryBtn = retryFn ? `<button onclick="${retryFn}" class="btn btn-ghost text-[10px] ml-2">Retry</button>` : '';
  el.innerHTML = `<div class="error-state">${escapeHtml(msg)}${retryBtn}</div>`;
}
function emptyHTML(el, msg) {
  el.innerHTML = `<div class="empty-state">${escapeHtml(msg)}</div>`;
}

// ═══════════════════════════════════════════════════════════════════════════
// SURFACE LOADER DISPATCH
// ═══════════════════════════════════════════════════════════════════════════

function loadSurfaceData(surface) {
  switch (surface) {
    // Round 46 — 4 unified meta-surfaces (Today/Memory/Ask/More)
    case 'today': loadToday(); break;
    case 'memory': loadUnifiedMemory(); break;  // Round 46 — unified memory feed
    case 'ask-v2': loadAskV2(); break;
    case 'more': openMoreMenu(); break;  // Round 46 — More opens the action sheet
    // Legacy meta-surfaces (kept for backward compat, accessible via Ctrl+K)
    case 'work': loadWork(); break;
    case 'learn': loadLearn(); break;
    case 'evolution': loadEvolution(); break;
    case 'cognition': loadCognition(); break;
    case 'autobiography': loadAutobiography(); break;
    case 'playbook': loadPlaybook('sales'); break;
    case 'personal': loadPersonalMode(); break;
    // Deep capabilities (existing surfaces)
    case 'home': loadDashboard(); break;
    case 'inbox': loadInbox(); break;
    case 'simulator': loadSimulator(); break;
    case 'hayek': loadHayek(); break;
    case 'flow': loadKnowledge(); break;
    case 'physics': loadLaws(''); break;
    case 'debate': loadDebate(); break;
    case 'customer': loadCustomerJudgment(); break;
    // Cognitive-model surfaces
    case 'intents': loadIntentCascade(); break;
    case 'contradictions': loadContradictions(); break;
    case 'predictions': loadPredictionMarket(); break;
    case 'assumptions': loadAssumptions(); break;
    case 'eng-signals': loadEngSignals(); break;
    case 'eng-oem': loadEngOEM(); break;
    case 'eng-audit': loadEngAudit(); break;
    case 'eng-settings': loadEngSettings(); break;
    // Round 47 — Block 1: Canvas + Per-Teammate (command-palette access)
    case 'canvas': if (typeof loadCanvas === 'function') loadCanvas(); break;
    case 'teammate': if (typeof loadTeammate === 'function') loadTeammate(); break;
    case 'coordination': if (typeof loadCoordination === 'function') loadCoordination(); break;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Round 46 — UNIFIED MEMORY surface
// Combines the Work Timeline (V8 Daily Work #1) and Personal Memory
// Replay into one chronological feed. The filter pill narrows the view
// (All/Work/Personal). Each item has a mode indicator dot.
// ═══════════════════════════════════════════════════════════════════════════

async function loadUnifiedMemory() {
  const el = document.getElementById('memory-content') || document.getElementById('main-content');
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const filter = getCurrentFilter ? getCurrentFilter() : 'all';
    const data = await api.getPersonal(`/memory?filter=${filter}&limit=50`);
    const items = data.items || [];
    const counts = data.counts || {};

    let html = `<div class="b-mw700-m0auto">`;

    // Header + filter pill container
    html += `
      <div class="b-flex-u-8">
        <div>
          <div class="b-fs18-fw800">Memory</div>
          <div class="b-fs12-text-7">${counts.all || 0} item${(counts.all || 0) === 1 ? '' : 's'} · most recent first</div>
        </div>
        <div id="filter-pill-container"></div>
      </div>
    `;

    if (items.length === 0) {
      html += `<div class="calm-empty" class="b-text-center-9">
        <div class="b-fs18-fw800-4">No memories yet.</div>
        <div class="meta-text">Connect work tools (Jira, Slack, GitHub) or personal tools (calendar, email) to see your unified memory here.</div>
      </div>`;
    } else {
      items.forEach((item, i) => {
        const mode = item._mode || 'work';
        const dotColor = mode === 'personal' ? '#FF6B6B' : '#2196F3';
        const dotTitle = mode === 'personal' ? 'Personal' : 'Work';
        const provider = item.provider || '';
        const description = item.description || '';
        const actor = item.actor || '';
        const domain = item.domain || '';
        const timestamp = item.timestamp || '';

        // Format timestamp
        let timeDisplay = '';
        if (timestamp) {
          try {
            const d = new Date(timestamp);
            const now = new Date();
            const diffMs = now - d;
            const diffMin = Math.floor(diffMs / 60000);
            const diffHr = Math.floor(diffMin / 60);
            const diffDay = Math.floor(diffHr / 24);
            if (diffMin < 1) timeDisplay = 'just now';
            else if (diffMin < 60) timeDisplay = `${diffMin}m ago`;
            else if (diffHr < 24) timeDisplay = `${diffHr}h ago`;
            else if (diffDay < 7) timeDisplay = `${diffDay}d ago`;
            else timeDisplay = d.toLocaleDateString();
          } catch (e) { timeDisplay = String(timestamp).slice(0, 10); }
        }

        html += `
          <div class="maestro-card" class="b-mb12-pos">
            <div class="b-pos-absolute-4" title="${dotTitle}" aria-label="Mode: ${dotTitle}"></div>
            ${provider ? `<div class="swipe-card-category ${mode === 'work' ? 'decision' : 'habit'}" class="mb-8">${escapeHtml(provider.toUpperCase())}</div>` : ''}
            <div class="b-fs15-fw700">${escapeHtml(humanize(description))}</div>
            ${actor ? `<div class="b-fs12-fw600-5">by ${escapeHtml(humanize(actor))}</div>` : ''}
            ${domain ? `<div class="b-fs11-text-2">${escapeHtml(humanize(domain))}</div>` : ''}
            ${timeDisplay ? `<div class="b-fs11-text-3">${escapeHtml(timeDisplay)}</div>` : ''}
          </div>
        `;
      });
    }

    html += `</div>`;
    el.innerHTML = html;

    // Render the filter pill into the container
    if (typeof renderFilterPill === 'function') {
      renderFilterPill('filter-pill-container');
    }
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed to load memory: ${escapeHtml(e.message)}</div>`;
  }
}

// ═══════════════════════════════════════════════════════════════════════════