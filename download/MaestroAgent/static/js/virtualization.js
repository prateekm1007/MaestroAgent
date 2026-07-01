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
  el.innerHTML = `<div class="loading-state"><span class="spinner"></span> ${msg || 'Loading…'}</div>`;
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
    // Constitution v2 — 4 meta-surfaces
    case 'today': loadToday(); break;
    case 'work': loadWork(); break;
    case 'ask-v2': loadAskV2(); break;
    case 'learn': loadLearn(); break;
    case 'evolution': loadEvolution(); break;
    case 'cognition': loadCognition(); break;
    case 'autobiography': loadAutobiography(); break;
    // Deep capabilities (existing surfaces)
    case 'home': loadDashboard(); break;
    case 'inbox': loadInbox(); break;
    case 'simulator': loadSimulator(); break;
    case 'hayek': loadHayek(); break;
    case 'flow': loadKnowledge(); break;
    case 'memory': loadMemory(); break;
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
  }
}

// ═══════════════════════════════════════════════════════════════════════════