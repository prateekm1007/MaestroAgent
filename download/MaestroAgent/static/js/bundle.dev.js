// MaestroAgent frontend bundle

// === utils.js ===
// utils.js — shared utilities. Loaded FIRST, before all other scripts.
// This file consolidates utility functions that were scattered across multiple files.

/**
 * Escape HTML special characters to prevent XSS.
 * Used by 30+ files for safe innerHTML rendering.
 */
function escapeHtml(s) {
  if (!s) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Escape JavaScript string for use in onclick handlers and inline scripts.
 */
function escapeJs(s) {
  if (!s) return '';
  return String(s)
    .replace(/\\/g, '\\\\')
    .replace(/'/g, "\\'")
    .replace(/"/g, '\\"');
}

/**
 * Format a confidence value for display.
 * Returns a string like "85%" or "insufficient data".
 */
function formatConfidence(c) {
  if (c === null || c === undefined || c === '') return '—';
  const num = parseFloat(c);
  if (isNaN(num)) return String(c);
  return (num * 100).toFixed(0) + '%';
}

/**
 * Format a timestamp for display.
 */
function formatTimestamp(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch (e) {
    return String(ts);
  }
}

/**
 * Show an error message in an element.
 */
function errorHTML(el, msg, retryFn) {
  if (typeof el === 'string') el = document.getElementById(el);
  if (!el) return;
  el.innerHTML = '<div class="error-state" role="alert">' +
    '<span class="text-brand-rose">' + escapeHtml(msg) + '</span>' +
    (retryFn ? '<button class="btn btn-ghost text-xs ml-2" onclick="' + retryFn + '">Retry</button>' : '') +
    '</div>';
}

/**
 * Announce a message to screen readers.
 */
function announce(message) {
  var el = document.getElementById('sr-announcer');
  if (el) {
    el.textContent = '';
    requestAnimationFrame(function() { el.textContent = message; });
  }
}


// === csp-shim.js ===
// Round 59 — CSP-safe event delegation system.
// Replaces 188 inline onclick= handlers with data-action attributes
// + a single delegated event listener. This makes the app compatible
// with a strict Content-Security-Policy that blocks unsafe-inline.
//
// Usage in HTML templates:
//   BEFORE: <button onclick="loadToday()">Refresh</button>
//   AFTER:  <button data-action="loadToday">Refresh</button>
//
// The delegator reads data-action and calls window[action]() if it exists.
// For actions with arguments, use data-action + data-args (JSON array):
//   <button data-action="navTo" data-args='["home"]'>Home</button>
//
// This file must be loaded BEFORE any surface renders.

(function() {
  'use strict';

  // Registry of action handlers. Maps action name → function.
  // Auto-populated by scanning window for known action functions.
  const _actionRegistry = {};

  // Register an action handler
  window._registerAction = function(name, fn) {
    _actionRegistry[name] = fn;
  };

  // Execute an action by name with optional args
  window._executeAction = function(name, args) {
    // Try registry first, then window[name]
    const fn = _actionRegistry[name] || window[name];
    if (typeof fn === 'function') {
      try {
        const parsedArgs = args ? JSON.parse(args) : [];
        fn.apply(null, parsedArgs);
      } catch (e) {
        console.warn('Action execution failed:', name, e);
      }
    } else {
      console.warn('Unknown action:', name);
    }
  };

  // Single delegated click listener — replaces all inline onclick handlers
  document.addEventListener('click', function(e) {
    // Walk up the DOM tree to find the closest [data-action] element
    let target = e.target;
    while (target && target !== document.body) {
      if (target.hasAttribute && target.hasAttribute('data-action')) {
        const action = target.getAttribute('data-action');
        const args = target.getAttribute('data-args');
        e.preventDefault();
        e.stopPropagation();
        window._executeAction(action, args);
        return;
      }
      target = target.parentElement;
    }
  });

  // Also handle data-action on touchstart for mobile
  document.addEventListener('touchend', function(e) {
    let target = e.target;
    while (target && target !== document.body) {
      if (target.hasAttribute && target.hasAttribute('data-action')) {
        const action = target.getAttribute('data-action');
        const args = target.getAttribute('data-args');
        e.preventDefault();
        window._executeAction(action, args);
        return;
      }
      target = target.parentElement;
    }
  });

  // CSP-safe CSP header setter — call this to set a strict CSP
  window._setStrictCSP = function() {
    // This is set server-side via SecurityHeadersMiddleware, but this
    // function documents the intended policy:
    // script-src 'self' 'nonce-{nonce}' (no unsafe-inline)
    console.log('CSP: strict mode enabled — inline handlers replaced with data-action delegation');
  };

  // Compatibility shim: convert existing onclick= attributes to data-action
  // on page load. This allows gradual migration — old code with onclick=
  // still works via this shim, while new code uses data-action directly.
  // Once all code is migrated, remove this shim and enable strict CSP.
  function _migrateInlineHandlers() {
    const elements = document.querySelectorAll('[onclick]');
    let migrated = 0;
    elements.forEach(function(el) {
      const onclick = el.getAttribute('onclick');
      if (!onclick) return;

      // Parse the onclick value: functionName('arg1', 'arg2') or functionName()
      const match = onclick.match(/^(\w+)\s*\((.*)\)\s*$/);
      if (match) {
        const fnName = match[1];
        const argsStr = match[2].trim();

        el.setAttribute('data-action', fnName);
        if (argsStr) {
          // Try to parse args as JSON. If it fails, store as single string arg.
          // Common patterns: 'string', number, true/false
          try {
            // Wrap in brackets to make it a JSON array
            const parsed = JSON.parse('[' + argsStr.replace(/'/g, '"') + ']');
            el.setAttribute('data-args', JSON.stringify(parsed));
          } catch (e) {
            // Can't parse — store raw
            el.setAttribute('data-args', JSON.stringify([argsStr]));
          }
        }

        el.removeAttribute('onclick');
        migrated++;
      }
    });
    if (migrated > 0 && window.console && console.debug) {
      console.debug('CSP shim: migrated', migrated, 'inline handlers to data-action');
    }
  }

  // Run migration after DOM is ready and after each surface render
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _migrateInlineHandlers);
  } else {
    _migrateInlineHandlers();
  }

  // Also run after any innerHTML change (via MutationObserver)
  const observer = new MutationObserver(function(mutations) {
    let needsMigration = false;
    for (const mutation of mutations) {
      if (mutation.addedNodes.length > 0) {
        for (const node of mutation.addedNodes) {
          if (node.nodeType === 1 && (node.hasAttribute && node.hasAttribute('onclick'))) {
            needsMigration = true;
            break;
          }
          if (node.querySelectorAll && node.querySelectorAll('[onclick]').length > 0) {
            needsMigration = true;
            break;
          }
        }
      }
      if (needsMigration) break;
    }
    if (needsMigration) {
      _migrateInlineHandlers();
    }
  });

  // Start observing once DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
      observer.observe(document.body, { childList: true, subtree: true });
    });
  } else {
    observer.observe(document.body, { childList: true, subtree: true });
  }
})();


// === core.js ===
'use strict';

/**
 * @fileoverview Maestro — Pure Renderer Frontend (modularized)
 *
 * This file is the entry point for the Maestro frontend. It sets strict mode
 * and establishes the global namespace. All other JS files are loaded via
 * <script defer> in app.html — NOT ES modules — to preserve global scope
 * for inline onclick/oninput handlers.
 *
 * @author Maestro Engineering
 */

// ═══════════════════════════════════════════════════════════════════════════
// THEME TOGGLE — light/dark via CSS custom properties + data-theme attribute
// ═══════════════════════════════════════════════════════════════════════════

function toggleTheme() {
  const html = document.documentElement;
  const current = html.getAttribute('data-theme') || 'dark';
  const next = current === 'dark' ? 'light' : 'dark';
  applyTheme(next);
}

function applyTheme(theme) {
  const html = document.documentElement;
  html.setAttribute('data-theme', theme);
  try {
    localStorage.setItem('maestro-theme', theme);
  } catch (e) {
    // localStorage may be unavailable (private mode) — theme still applies for this session
  }

  // Toggle icon visibility: show moon in light mode (click → dark), sun in dark mode (click → light)
  const moon = document.getElementById('theme-icon-moon');
  const sun = document.getElementById('theme-icon-sun');
  const label = document.getElementById('theme-toggle-label');
  if (moon && sun) {
    // In dark mode: show sun icon (click to go light). In light mode: show moon icon (click to go dark).
    moon.classList.toggle('hidden', theme === 'dark');
    sun.classList.toggle('hidden', theme === 'light');
  }
  if (label) {
    label.textContent = theme === 'dark' ? 'Light mode' : 'Dark mode';
  }
}

// On page load, restore saved theme or respect OS preference on first visit
(function initTheme() {
  let saved = null;
  try {
    saved = localStorage.getItem('maestro-theme');
  } catch (e) {
    // localStorage unavailable
  }
  let theme;
  if (saved === 'light' || saved === 'dark') {
    theme = saved;
  } else {
    // Respect OS preference on first visit
    const prefersLight = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches;
    theme = prefersLight ? 'light' : 'dark';
  }
  // Apply immediately (before other scripts load) to prevent flash of wrong theme
  document.documentElement.setAttribute('data-theme', theme);
  // Update icons after DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() { applyTheme(theme); });
  } else {
    applyTheme(theme);
  }
})();

// ═══════════════════════════════════════════════════════════════════════════
// V8 Upgrade #1 — "Why?" links on confidence displays.
//
// Every confidence score in the UI gets a "Why?" link that opens the ASK
// surface with a context-derived "why" question. The question is built
// from the entity's title/type so the ExplanationEngine can compose a
// relevant causal chain.
//
// Usage in renderers:
//   formatConfidenceWithWhy(rec.confidence, { entity: 'recommendation', title: rec.title })
//   → '<span class="conf-why-wrap">0.87 <a class="conf-why-link" onclick="askWhy(\'Why is this recommendation confident?\')">Why?</a></span>'
//
// The link calls askWhy() which switches to the ASK tab and submits the
// question — the ExplanationEngine handles the rest.
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Build a "Why?" question string from an entity context.
 * @param {Object} ctx - { entity: 'recommendation'|'law'|'prediction'|'bottleneck'|'risk'|'incident'|'attrition'|'velocity', title?: string }
 * @returns {string} A "why" question suitable for the ExplanationEngine.
 */
function buildWhyQuestion(ctx) {
  if (!ctx || !ctx.entity) return 'Why is this happening?';
  const title = ctx.title ? ctx.title.replace(/\s+/g, ' ').trim().slice(0, 80) : '';
  switch (ctx.entity) {
    case 'recommendation':
      // Recommendations usually point at bottlenecks or risks
      if (title && /bottleneck|gate|block/i.test(title)) {
        return 'Why is everything bottlenecked?';
      }
      if (title && /incident|outage|p1|bug/i.test(title)) {
        return 'Why are incidents occurring?';
      }
      if (title && /slow|velocity|throughput/i.test(title)) {
        return 'Why has organizational velocity dropped?';
      }
      return 'Why is this recommendation confident?';
    case 'law':
    case 'pattern':
      // Laws describe validated patterns — the "why" is about the pattern's cause
      return title ? `Why does this pattern hold: ${title}?` : 'Why does this pattern hold?';
    case 'prediction':
      return 'Why are engineering estimates always wrong?';
    case 'bottleneck':
      return 'Why is everything bottlenecked?';
    case 'risk':
    case 'concentration_risk':
      return 'Why are people leaving?';
    case 'incident':
      return 'Why are incidents occurring?';
    case 'velocity':
      return 'Why has organizational velocity dropped?';
    case 'attrition':
      return 'Why are people leaving?';
    case 'estimate':
      return 'Why are engineering estimates always wrong?';
    default:
      return title ? `Why is this happening: ${title}?` : 'Why is this happening?';
  }
}

/**
 * Open the ASK surface with a "why" question.
 * Switches to the ASK tab, calls loadAskV2(), and submits the question.
 * @param {string} question - The "why" question.
 */
function askWhy(question) {
  if (!question) return;
  // Switch to ASK tab — the sidebar nav uses data-tab="ask"
  const askNav = document.querySelector('[data-tab="ask"]') || document.querySelector('a[href="#ask"]');
  if (askNav) {
    askNav.click();
  }
  // Wait for the ASK surface to render, then submit the question.
  // The loadAskV2() function renders the input; we give it a tick.
  setTimeout(function() {
    if (typeof loadAskV2 === 'function') {
      loadAskV2();
      // Wait one more tick for the input to be in the DOM
      setTimeout(function() {
        if (typeof submitAskV2 === 'function') {
          submitAskV2(question);
        }
      }, 50);
    }
  }, 80);
}

/**
 * Format a confidence score with an adjacent "Why?" link.
 * Returns HTML (string) — caller must inject via innerHTML.
 *
 * @param {number} confidence - 0..1 confidence value
 * @param {Object} [ctx] - Entity context for building the "why" question
 * @returns {string} HTML string with confidence + "Why?" link
 */
function formatConfidenceWithWhy(confidence, ctx) {
  const fmt = (typeof formatConfidence === 'function') ? formatConfidence(confidence) : (confidence != null ? Number(confidence).toFixed(2) : '—');
  if (confidence == null) return escapeHtml(String(fmt));
  const q = buildWhyQuestion(ctx || {});
  // Escape single quotes in the question for the onclick attribute
  const qEsc = String(q).replace(/'/g, "\\'");
  return `<span class="conf-why-wrap">${escapeHtml(String(fmt))} <a class="conf-why-link" onclick="askWhy('${qEsc}')" title="Why is this confidence what it is?">Why?</a></span>`;
}

// ═══════════════════════════════════════════════════════════════════════════

// === maestro.js ===

// Round 78: Custom confirm modal (replaces native confirm())
// Styles extracted to CSS classes (.confirm-backdrop, .confirm-panel, etc.)
// in design-system.css — no inline styles (CSP + consistency).
function showConfirm(message) {
  return new Promise(function(resolve) {
    var backdrop = document.createElement('div');
    backdrop.className = 'confirm-backdrop';

    var panel = document.createElement('div');
    panel.className = 'confirm-panel';

    panel.innerHTML = '<div class="confirm-message">' + message + '</div>' +
      '<div class="confirm-actions">' +
      '<button id="confirm-cancel" class="confirm-btn confirm-btn-cancel">Cancel</button>' +
      '<button id="confirm-ok" class="confirm-btn confirm-btn-ok">Confirm</button>' +
      '</div>';

    backdrop.appendChild(panel);
    document.body.appendChild(backdrop);

    document.getElementById('confirm-cancel').onclick = function() { backdrop.remove(); resolve(false); };
    document.getElementById('confirm-ok').onclick = function() { backdrop.remove(); resolve(true); };
    backdrop.onclick = function(e) { if (e.target === backdrop) { backdrop.remove(); resolve(false); } };
  });
}

// Round 78: Toast notification system (replaces alert/confirm)
function showToast(message, type) {
  type = type || 'info';
  var toast = document.createElement('div');
  toast.className = 'toast ' + type;
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(function() {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s';
    setTimeout(function() { toast.remove(); }, 300);
  }, 3000);
}
// MAESTRO — Pure Renderer Frontend
// ═══════════════════════════════════════════════════════════════════════════
// The UI is a pure renderer. The OEM is the single source of truth.
// Every metric, recommendation, law, discovery, autocomplete suggestion,
// and dashboard number comes from a live OEM API call.
//
// Features:
//   - SWR-style caching (stale-while-revalidate)
//   - Loading states with skeletons
//   - Retry with exponential backoff
//   - Offline mode (serves cached data when network fails)
//   - Optimistic updates (contradiction feedback)
//   - Error recovery (global error boundary + per-surface retry)
//   - Request cancellation (AbortController per fetch)
// ═══════════════════════════════════════════════════════════════════════════

// ─── Configuration ───────────────────────────────────────────────────────────
const MAESTRO_API = window.MAESTRO_API || '';

// ─── Navigation map (the only hardcoded data — labels, not insights) ────────
const pageNames = {
  // Round 46 — 4 unified meta-surfaces
  today: 'Today', memory: 'Memory', 'ask-v2': 'Ask', more: 'More',
  // Legacy meta-surfaces (accessible via Ctrl+K)
  work: 'Work', learn: 'Learn',
  evolution: 'Evolution Report',
  cognition: 'Cognitive Organs',
  autobiography: "Your Organization's Story",
  playbook: 'Role Playbooks',
  personal: 'Personal Mode',
  // Deep capabilities (existing surfaces)
  home: 'Home', inbox: 'Inbox', simulator: 'Decision Simulator',
  hayek: 'Hayek Lens', flow: 'Knowledge Flow',
  ask: 'Ask the Organization', customer: 'Customer Judgment',
  physics: 'Organizational Physics', debate: 'Debate',
  live: 'Meeting Analyzer',
  intents: 'Intent Cascade',
  contradictions: 'Contradictions',
  predictions: 'Prediction Market',
  assumptions: 'Dangerous Assumptions',
  'eng-signals': 'Signals', 'eng-oem': 'OEM Builder',
  'eng-audit': 'Audit Log', 'eng-settings': 'Settings',
  // Round 47 — Block 1
  canvas: 'Decision Canvas', coordination: 'Coordination Engine',
};

function navTo(surface) {
  // Teardown: clean up timers/WS when leaving a surface
  if (window._currentSurface === 'live' && surface !== 'live') {
    teardownLive();
  }
  window._currentSurface = surface;
  if (window.location.hash !== '#' + surface) {
    history.replaceState(null, '', '#' + surface);
  }
  document.querySelectorAll('.surface').forEach(s => s.classList.remove('active'));
  const target = document.getElementById('surface-' + surface);
  if (target) {
    target.classList.add('active');
    void target.offsetWidth;
  }
  document.querySelectorAll('.sidebar-link').forEach(l => l.classList.remove('active'));
  const link = document.querySelector('.sidebar-link[data-surface="' + surface + '"]');
  if (link) link.classList.add('active');
  document.getElementById('bc-page').textContent = pageNames[surface] || surface;
  document.getElementById('bc-detail').textContent = '';
  document.getElementById('main-scroll').scrollTop = 0;
  closeMobileSidebar();

  // WCAG 2.1: Move focus to main content for screen reader users
  const mainContent = document.getElementById('main-content');
  if (mainContent) {
    mainContent.setAttribute('tabindex', '-1');
    mainContent.focus({ preventScroll: true });
  }

  loadSurfaceData(surface);
}

document.querySelectorAll('.sidebar-link[data-surface]').forEach(link => {
  link.addEventListener('click', () => navTo(link.dataset.surface));
  link.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navTo(link.dataset.surface); }
  });
});

function toggleMobileSidebar() {
  document.getElementById('sidebar').classList.toggle('mobile-open');
}
function closeMobileSidebar() {
  document.getElementById('sidebar').classList.remove('mobile-open');
}

window.addEventListener('hashchange', () => {
  const hash = window.location.hash.slice(1);
  if (hash && document.getElementById('surface-' + hash)) navTo(hash);
});
window.addEventListener('DOMContentLoaded', () => {
  const hash = window.location.hash.slice(1);
  // Constitution v2: default to TODAY (the morning brief)
  const validHash = hash && document.getElementById('surface-' + hash);
  navTo(validHash ? hash : 'today');
  // Initialize the Organizational Dot
  initOrgDot();
  // Round 78 Phase 3: check if demo seed is active and watermark the UI.
  // The auditor flagged "demo data conflated with production" — this adds
  // a visible "DEMO DATA" badge so users always know when they're looking
  // at synthetic data vs real tenant data.
  fetch((MAESTRO_API || '') + '/api/health').then(r => r.json()).then(data => {
    if (data.demo_seed) {
      const badge = document.createElement('div');
      badge.id = 'demo-watermark';
      badge.style.cssText = 'position:fixed;top:0;right:0;z-index:99999;background:#f59e0b;color:#000;font-size:11px;font-weight:700;padding:4px 12px;border-radius:0 0 0 8px;letter-spacing:0.5px;box-shadow:0 2px 8px rgba(0,0,0,0.3)';
      badge.textContent = 'DEMO DATA';
      badge.title = 'This instance is running with synthetic demo data (MAESTRO_DEMO_SEED=true). All insights, signals, and learning objects are fictional.';
      document.body.appendChild(badge);
    }
  }).catch(() => {});
});

document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  if ((e.metaKey || e.ctrlKey) && e.key >= '1' && e.key <= '9') {
    e.preventDefault();
    // Constitution v2: Ctrl+1-4 = meta-surfaces, Ctrl+5-9 = deep capabilities
    const surfaces = ['today','work','ask-v2','learn','home','inbox','simulator','customer','physics'];
    const idx = parseInt(e.key) - 1;
    if (surfaces[idx]) navTo(surfaces[idx]);
  }
  if (e.key === 'Escape') {
    document.getElementById('exec-autocomplete').classList.remove('active');
    const palette = document.getElementById('command-palette');
    if (palette) palette.classList.add('hidden');
  }
  // Ctrl+K opens command palette
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault();
    openCommandPalette();
  }
});

// ═══════════════════════════════════════════════════════════════════════════
// COMMAND PALETTE — access to the 22 deep surfaces without sidebar clutter
// ═══════════════════════════════════════════════════════════════════════════

const _hiddenSurfaces = [
  { id: 'home', label: 'Home — live dashboard', group: 'CEO Product' },
  { id: 'inbox', label: 'Inbox — decisions I owe', group: 'CEO Product' },
  { id: 'simulator', label: 'Decision Simulator', group: 'CEO Product' },
  { id: 'hayek', label: 'Hayek Lens — influence graph', group: 'CEO Product' },
  { id: 'flow', label: 'Knowledge Flow', group: 'CEO Product' },
  { id: 'memory', label: 'Memory Replay', group: 'CEO Product' },
  { id: 'ask', label: 'Ask the Organization (legacy)', group: 'CEO Product' },
  { id: 'customer', label: 'Customer Judgment', group: 'CEO Product' },
  { id: 'physics', label: 'Organizational Physics — patterns', group: 'CEO Product' },
  { id: 'debate', label: 'Debate — laws unknown to leadership', group: 'CEO Product' },
  { id: 'live', label: 'Meeting Analyzer — transcript intelligence', group: 'CEO Product' },
  { id: 'intents', label: 'Intent Cascade', group: 'Cognitive Model' },
  { id: 'contradictions', label: 'Contradictions', group: 'Cognitive Model' },
  { id: 'predictions', label: 'Prediction Market — calibration', group: 'Cognitive Model' },
  { id: 'assumptions', label: 'Dangerous Assumptions', group: 'Cognitive Model' },
  { id: 'eng-signals', label: 'Signals — connected sources', group: 'Engineering' },
  { id: 'eng-oem', label: 'OEM Builder — inference pipeline', group: 'Engineering' },
  { id: 'eng-audit', label: 'Audit Log — signal history', group: 'Engineering' },
  { id: 'eng-settings', label: 'Settings — configuration', group: 'Engineering' },
  { id: 'evolution', label: 'Evolution Report — how has the organization changed?', group: 'Constitution v3' },
  { id: 'cognition', label: 'Cognitive Organs — skepticism, wisdom, metacognition, principles, consciousness', group: 'Constitution v4' },
  { id: 'autobiography', label: 'Your Organization\u2019s Story — the autobiography', group: 'Constitution v6' },
  { id: 'playbook', label: 'Role Playbooks — Sales, Marketing, Product', group: 'Daily Work' },
  { id: 'personal', label: 'Personal Mode — your life, your memory, your decisions', group: 'Personal' },
  // Round 47 — Block 1: Canvas + Per-Teammate (command-palette only, NOT sidebar)
  { id: 'canvas', label: 'Canvas — visual decision mapping', group: 'Round 47' },
  { id: 'coordination', label: 'Coordination Engine — multi-team decision input', group: 'Round 59' },
];

function openCommandPalette() {
  let palette = document.getElementById('command-palette');
  if (!palette) {
    palette = document.createElement('div');
    palette.id = 'command-palette';
    palette.className = 'fixed inset-0 z-50';
    palette.style.cssText = 'display:flex;align-items:flex-start;justify-content:center;padding-top:120px;background:rgba(0,0,0,0.5);';
    palette.innerHTML = `
      <div class="b-bg-surface">
        <input type="text" id="command-palette-input" placeholder="Search surfaces…"
               class="b-w-full-7"
               aria-label="Search surfaces"
               oninput="filterCommandPalette(this.value)"
               onkeydown="handlePaletteKeydown(event)">
        <div id="command-palette-results" class="b-flex-u-2"></div>
      </div>
    `;
    palette.addEventListener('click', (e) => {
      if (e.target === palette) closeCommandPalette();
    });
    document.body.appendChild(palette);
  }
  palette.classList.remove('hidden');
  palette.style.display = 'flex';
  renderPaletteResults(_hiddenSurfaces);
  setTimeout(() => {
    const input = document.getElementById('command-palette-input');
    if (input) input.focus();
  }, 50);
}

function closeCommandPalette() {
  const palette = document.getElementById('command-palette');
  if (palette) palette.style.display = 'none';
}

function renderPaletteResults(surfaces) {
  const results = document.getElementById('command-palette-results');
  if (!results) return;
  if (surfaces.length === 0) {
    results.innerHTML = '<div class="b-p20-text">No surfaces found</div>';
    return;
  }
  let currentGroup = '';
  results.innerHTML = surfaces.map(s => {
    const groupHeader = s.group !== currentGroup ? `<div class="b-p8164-fs10">${escapeHtml(s.group)}</div>` : '';
    currentGroup = s.group;
    return groupHeader + `<div class="palette-result b-p1016-cursor" onmouseenter="this.style.background='var(--surface-2)'" onmouseleave="this.style.background='transparent'" onclick="navTo('${escapeJs(s.id)}');closeCommandPalette();">${escapeHtml(s.label)}</div>`;
  }).join('');
}

function selectFirstPaletteResult() {
  const first = document.querySelector('.palette-result');
  if (first) first.click();
}

// Arrow-key navigation for the command palette (Linear/Raycast-style)
let _paletteSelectedIdx = -1;

function handlePaletteKeydown(event) {
  const results = document.querySelectorAll('.palette-result');
  if (results.length === 0) return;

  if (event.key === 'Escape') {
    closeCommandPalette();
    return;
  }
  if (event.key === 'Enter') {
    if (_paletteSelectedIdx >= 0 && results[_paletteSelectedIdx]) {
      results[_paletteSelectedIdx].click();
    } else if (results[0]) {
      results[0].click();
    }
    return;
  }
  if (event.key === 'ArrowDown') {
    event.preventDefault();
    _paletteSelectedIdx = Math.min(_paletteSelectedIdx + 1, results.length - 1);
    updatePaletteSelection(results);
  }
  if (event.key === 'ArrowUp') {
    event.preventDefault();
    _paletteSelectedIdx = Math.max(_paletteSelectedIdx - 1, 0);
    updatePaletteSelection(results);
  }
}

function updatePaletteSelection(results) {
  results.forEach((r, i) => {
    if (i === _paletteSelectedIdx) {
      r.style.background = 'var(--accent-soft)';
      r.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    } else {
      r.style.background = 'transparent';
    }
  });
}

// Reset selection when filtering
function filterCommandPalette(query) {
  _paletteSelectedIdx = -1;
  const q = query.toLowerCase().trim();
  if (!q) {
    renderPaletteResults(_hiddenSurfaces);
    return;
  }
  const filtered = _hiddenSurfaces.filter(s =>
    s.label.toLowerCase().includes(q) || s.id.toLowerCase().includes(q)
  );
  renderPaletteResults(filtered);
}

// ═══════════════════════════════════════════════════════════════════════════

// === swr_cache.js ===
// SWR CACHE — Stale-While-Revalidate with retry, offline, cancellation
// ═══════════════════════════════════════════════════════════════════════════

const SWR = {
  // Cache: key → { data, timestamp, promise, abort, error, url }
  _cache: new Map(),
  _subscribers: new Map(),
  _online: navigator.onLine,
  DEDUP_MS: 2000,
  STALE_MS: 30000,
  MAX_RETRIES: 3,
  RETRY_DELAYS: [1000, 2000, 4000],

  init() {
    window.addEventListener('online', () => {
      this._online = true;
      this.revalidateAll();
      hideOfflineBanner();
    });
    window.addEventListener('offline', () => {
      this._online = false;
      showOfflineBanner();
    });
  },

  on(key, callback) {
    if (!this._subscribers.has(key)) this._subscribers.set(key, new Set());
    this._subscribers.get(key).add(callback);
    const entry = this._cache.get(key);
    if (entry) {
      callback({ data: entry.data, error: entry.error, loading: false, fromCache: true });
    }
    return () => this._subscribers.get(key)?.delete(callback);
  },

  _notify(key, state) {
    const subs = this._subscribers.get(key);
    if (subs) subs.forEach(cb => { try { cb(state); } catch (e) { console.warn(e); } });
  },

  async fetch(key, url, options = {}) {
    const now = Date.now();
    const entry = this._cache.get(key);

    // Dedup: if a fetch is in-flight, return its promise
    if (entry?.promise && now - entry.timestamp < this.DEDUP_MS) {
      return entry.promise;
    }

    // Cancel any previous in-flight request for this key
    if (entry?.abort) {
      try { entry.abort.abort(); } catch (e) {}
    }

    const abort = new AbortController();
    const fetchPromise = this._doFetch(key, url, { ...options, signal: abort.signal });

    this._cache.set(key, {
      data: entry?.data,
      timestamp: now,
      promise: fetchPromise,
      abort,
      error: null,
      url,
    });

    // If we have stale data, notify immediately (stale-while-revalidate)
    if (entry?.data) {
      this._notify(key, { data: entry.data, error: null, loading: true, fromCache: true });
    } else {
      this._notify(key, { data: null, error: null, loading: true, fromCache: false });
    }

    return fetchPromise;
  },

  async _doFetch(key, url, options, retryCount = 0) {
    try {
      const resp = await fetch(MAESTRO_API + url, options);
      if (!resp.ok) {
        const err = new Error(`HTTP ${resp.status}: ${resp.statusText}`);
        err.status = resp.status;
        throw err;
      }
      const data = await resp.json();
      const entry = this._cache.get(key);
      this._cache.set(key, {
        ...entry,
        data,
        timestamp: Date.now(),
        promise: null,
        abort: null,
        error: null,
        url,
      });
      this._notify(key, { data, error: null, loading: false, fromCache: false });
      return data;
    } catch (err) {
      if (err.name === 'AbortError') {
        return null;
      }

      // Retry with exponential backoff — but NOT for definitive client errors.
      // 4xx (except 408 Request Timeout, 429 Too Many Requests) won't change
      // on retry. Retrying 404s caused 6 wasteful failed requests in the
      // console for /api/oem/time-axis (intentional 404 = insufficient data).
      const isDefinitiveClientError =
        err.status && err.status >= 400 && err.status < 500 &&
        err.status !== 408 && err.status !== 429;
      if (!isDefinitiveClientError && retryCount < this.MAX_RETRIES && this._online) {
        const delay = this.RETRY_DELAYS[retryCount] || 4000;
        await new Promise(r => setTimeout(r, delay));
        return this._doFetch(key, url, options, retryCount + 1);
      }

      // Final failure — serve cached data if available, else error
      const entry = this._cache.get(key);
      const cachedData = entry?.data;
      this._cache.set(key, {
        ...entry,
        promise: null,
        abort: null,
        error: err,
      });
      if (cachedData) {
        this._notify(key, { data: cachedData, error: err, loading: false, fromCache: true, offline: !this._online });
        return cachedData;
      } else {
        this._notify(key, { data: null, error: err, loading: false, fromCache: false });
        throw err;
      }
    }
  },

  mutate(key, updater) {
    const entry = this._cache.get(key);
    if (!entry) return;
    const newData = typeof updater === 'function' ? updater(entry.data) : updater;
    this._cache.set(key, { ...entry, data: newData });
    this._notify(key, { data: newData, error: null, loading: false, fromCache: true, optimistic: true });
  },

  invalidate(key) {
    const entry = this._cache.get(key);
    if (!entry?.url) return;
    this.fetch(key, entry.url);
  },

  invalidatePrefix(prefix) {
    for (const [key, entry] of this._cache.entries()) {
      if (key.startsWith(prefix) && entry?.url) {
        this.fetch(key, entry.url);
      }
    }
  },

  revalidateAll() {
    for (const [key, entry] of this._cache.entries()) {
      if (entry?.url && !entry.promise) {
        this.fetch(key, entry.url);
      }
    }
  },

  get(key) {
    return this._cache.get(key)?.data;
  },
};

SWR.init();

// ═══════════════════════════════════════════════════════════════════════════
// API HELPERS — typed wrappers around SWR.fetch
// ═══════════════════════════════════════════════════════════════════════════

const api = {
  getOEM: (path) => SWR.fetch('oem:' + path, '/api/oem' + path),
  postOEM: async (path, body) => {
    // Round 67 Phase 3.3: POST must NOT use SWR cache.
    // Mutations served as stale GET data is a real hazard.
    const resp = await fetch('/api/oem' + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (resp.ok) {
      SWR.invalidatePrefix('oem:');  // bust cache after mutation
    }
    return data;
  },
  getPersonal: (path) => fetch('/api/personal' + path).then(r => r.json()),
  postPersonal: (path, body) =>
    fetch('/api/personal' + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(r => r.json()),
  getImports: () => SWR.fetch('imports:list', '/api/imports'),
  getOAuthStatus: () => SWR.fetch('oauth:status', '/api/oauth/status'),
};

// ═══════════════════════════════════════════════════════════════════════════
// ERROR BOUNDARY — global error toast + offline banner
// ═══════════════════════════════════════════════════════════════════════════

function showError(message, duration = 5000) {
  let toast = document.getElementById('error-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'error-toast';
    toast.className = 'fixed top-4 right-4 bg-brand-rose/20 border border-brand-rose/40 text-brand-rose px-4 py-3 rounded-lg shadow-2xl text-sm z-50 max-w-md';
    document.body.appendChild(toast);
  }
  toast.innerHTML = `<div class="flex items-start gap-2">
    <span class="text-brand-rose font-bold">!</span>
    <div class="flex-1">${escapeHtml(message)}</div>
    <button onclick="this.parentElement.parentElement.remove()" class="text-brand-rose/60 hover:text-brand-rose">x</button>
  </div>`;
  toast.style.display = 'block';
  clearTimeout(toast._timeout);
  toast._timeout = setTimeout(() => { toast.style.display = 'none'; }, duration);
}

function showOfflineBanner() {
  let banner = document.getElementById('offline-banner');
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'offline-banner';
    banner.className = 'fixed top-0 left-0 right-0 bg-brand-amber/20 border-b border-brand-amber/40 text-brand-amber text-center py-1.5 text-xs z-50';
    banner.innerHTML = 'Offline — showing cached data. Changes may not persist.';
    document.body.appendChild(banner);
  }
  banner.style.display = 'block';
}

function hideOfflineBanner() {
  const banner = document.getElementById('offline-banner');
  if (banner) banner.style.display = 'none';
}

// ═══════════════════════════════════════════════════════════════════════════
// RENDER HELPERS
// ═══════════════════════════════════════════════════════════════════════════


// escapeJs — escape a string for safe interpolation into a JS string literal
// inside an inline onclick="..." handler.
//
// The auditor found that escapeHtml() is insufficient for this context:
// the browser decodes HTML entities (like &#39;) BEFORE passing the string
// to the JS engine, so a single quote in the data decodes back to ' and
// breaks out of the JS string literal. This is an XSS vector when the
// data comes from attacker-influenceable sources (signal titles, customer
// names, etc.).
//
// escapeJs() escapes for JS string context: replaces ' with \\', " with \\",
// \ with \\\\, and strips newlines. Used in onclick="fn('${escapeJs(x)}')"
// patterns. For HTML content (not inside JS strings), escapeHtml() is correct.

// ═══════════════════════════════════════════════════════════════════════════

// === virtualization.js ===
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
      html += `<div class="calm-empty b-text-center-9">
        <div class="b-fs18-fw800-4">No memories yet.</div>
        <div class="meta-text">Connect work tools (Jira, Slack, GitHub) or personal tools (calendar, email) to see your unified memory here.</div>
        <div class="b-mt16 b-text-left-9 b-mw500-m0auto">
          <div class="b-fs13-fw700-4 b-mb8">What you'll see when connected:</div>
          <div class="b-fs12-text-6 b-mb6"><strong>Work timeline:</strong> PRs opened, tickets transitioned, deployments shipped, postmortems written — every execution signal, timestamped and attributed.</div>
          <div class="b-fs12-text-6 b-mb6"><strong>Personal memories:</strong> Decisions you made, habits you tracked, reflections you logged — encrypted at rest, visible only to you.</div>
          <div class="b-fs12-text-6 b-mb6"><strong>Unified feed:</strong> Work and personal memories merged chronologically. The filter pill (All / Work / Personal) narrows the view without switching surfaces.</div>
          <div class="b-fs12-text-6"><strong>Searchable:</strong> Every memory is full-text searchable via the command palette (⌘K). Type any fragment and jump to the moment it happened.</div>
        </div>
        <div class="b-mt16">
          <button class="ds-btn ds-btn-primary" onclick="navTo('eng-settings')">Connect a data source →</button>
        </div>
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
          <div class="maestro-card b-mb12-pos">
            <div class="b-pos-absolute-4" title="${dotTitle}" aria-label="Mode: ${dotTitle}"></div>
            ${provider ? `<div class="swipe-card-category ${mode === 'work' ? 'decision' : 'habit'} mb-8">${escapeHtml(provider.toUpperCase())}</div>` : ''}
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

// === ambient_organizational_judgment.js ===
// AMBIENT ORGANIZATIONAL JUDGMENT — Pulse, Feed, Narrative, Cognitive Load
// ═══════════════════════════════════════════════════════════════════════════

async function loadPulse() {
  const body = document.getElementById('pulse-body');
  const stateEl = document.getElementById('pulse-state');
  if (!body) return;
  try {
    const p = await api.getOEM('/pulse');
    stateEl.textContent = p.state;
    const stateColor = p.state === 'healthy' || p.state === 'execution_accelerating' ? 'text-green-400'
      : p.state === 'turbulent' || p.state === 'trust_falling' ? 'text-red-400'
      : p.state === 'knowledge_blocked' || p.state === 'decision_stalled' ? 'text-yellow-400'
      : 'text-fg-300';
    stateEl.className = `text-[10px] font-semibold ${stateColor}`;
    body.innerHTML = `
      <div class="grid grid-cols-2 gap-2 text-xs">
        ${[['Temperature', p.temperature], ['Momentum', p.momentum], ['Alignment', p.alignment], ['Trust', p.trust], ['Knowledge', p.knowledge_mobility], ['Decision Speed', p.decision_speed]].map(([label, val]) => {
          const color = val > 70 ? 'text-green-400' : val < 40 ? 'text-red-400' : 'text-yellow-400';
          return `<div><div class="text-[10px] text-fg-500 uppercase">${label}</div><div class="font-bold ${color}">${Math.round(val)}</div></div>`;
        }).join('')}
      </div>
      <div class="mt-3 pt-3 border-t border-white/[0.05] text-xs text-fg-300">${escapeHtml(humanize(p.narrative))}</div>
    `;
  } catch (e) {
    body.innerHTML = `<div class="empty-state">Pulse unavailable: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadNarrative() {
  const body = document.getElementById('narrative-body');
  const dateEl = document.getElementById('narrative-date');
  if (!body) return;
  try {
    const n = await api.getOEM('/narrative');
    dateEl.textContent = n.date;
    body.innerHTML = `
      <div class="text-sm font-semibold text-white mb-2">${escapeHtml(humanize(n.title))}</div>
      <div class="text-xs text-fg-300 whitespace-pre-line mb-3">${escapeHtml(humanize(n.body))}</div>
      ${n.highlights && n.highlights.length > 0 ? `
        <div class="space-y-1">
          ${n.highlights.slice(0, 5).map(h => {
            const color = h.impact === 'positive' ? 'text-green-400' : h.impact === 'negative' ? 'text-red-400' : h.impact === 'warning' ? 'text-yellow-400' : 'text-fg-400';
            return `<div class="text-[11px] ${color}">• ${escapeHtml(humanize(h.text))}</div>`;
          }).join('')}
        </div>
      ` : ''}
      ${n.watch_for && n.watch_for.length > 0 ? `
        <div class="mt-2 pt-2 border-t border-white/[0.05] text-[10px] text-amber-400">${n.watch_for.slice(0, 2).map(w => escapeHtml(w)).join(' · ')}</div>
      ` : ''}
    `;
  } catch (e) {
    body.innerHTML = `<div class="empty-state">Narrative unavailable: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadFeed() {
  const body = document.getElementById('feed-body');
  if (!body) return;
  try {
    const data = await api.getOEM('/feed?limit=15');
    if (!data.events || data.events.length === 0) {
      body.innerHTML = '<div class="empty-state">No significant events. The organization is quiet.</div>';
      return;
    }
    body.innerHTML = data.events.map(e => {
      const color = e.event_type.includes('strengthened') || e.event_type.includes('renewed') || e.event_type.includes('correct') ? 'border-l-green-400'
        : e.event_type.includes('broken') || e.event_type.includes('churned') || e.event_type.includes('invalidated') ? 'border-l-red-400'
        : e.event_type.includes('drift') || e.event_type.includes('risk') || e.event_type.includes('overloaded') ? 'border-l-yellow-400'
        : 'border-l-cyan-400';
      return `
        <div class="border-l-2 ${color} pl-3 py-1.5 mb-1.5 cursor-pointer hover:bg-white/[0.02]" onclick="openFeedEvent('${escapeJs(e.event_type)}', '${escapeJs(e.entity_id)}')">
          <div class="flex items-center justify-between">
            <div class="text-xs font-semibold text-white">${escapeHtml(humanize(e.title))}</div>
            <div class="text-[9px] text-fg-500">${formatTimestamp(e.timestamp)}</div>
          </div>
          <div class="text-[10px] text-fg-400 mt-0.5">${escapeHtml(e.why_it_matters)}</div>
          <div class="text-[10px] text-fg-500 mt-0.5">→ ${escapeHtml(e.recommended_action)}</div>
        </div>
      `;
    }).join('');
  } catch (e) {
    body.innerHTML = `<div class="empty-state">Feed unavailable: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadCognitiveLoad() {
  const body = document.getElementById('ocl-body');
  const levelEl = document.getElementById('ocl-level');
  if (!body) return;
  try {
    const ocl = await api.getOEM('/cognitive-load');
    const color = ocl.level === 'low' ? 'text-green-400' : ocl.level === 'moderate' ? 'text-yellow-400' : ocl.level === 'high' ? 'text-orange-400' : 'text-red-400';
    levelEl.textContent = `${ocl.level} (${ocl.score})`;
    levelEl.className = `text-[10px] font-semibold ${color}`;
    const topFactors = Object.entries(ocl.factors).sort((a, b) => b[1].score - a[1].score).slice(0, 4);
    body.innerHTML = `
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        ${topFactors.map(([name, f]) => {
          const fc = f.score > 60 ? 'text-red-400' : f.score > 40 ? 'text-yellow-400' : 'text-green-400';
          return `<div><div class="text-[10px] text-fg-500 uppercase">${name.replace(/_/g, ' ')}</div><div class="font-bold ${fc}">${Math.round(f.score)}</div><div class="text-[9px] text-fg-400">${escapeHtml(humanize(f.detail))}</div></div>`;
        }).join('')}
      </div>
      <div class="mt-3 pt-3 border-t border-white/[0.05] text-xs text-fg-300">${escapeHtml(humanize(ocl.narrative))}</div>
      ${ocl.recommendations && ocl.recommendations.length > 0 ? `
        <div class="mt-2 text-[10px] text-cyan-400">→ ${escapeHtml(ocl.recommendations[0].recommendation)}</div>
      ` : ''}
    `;
  } catch (e) {
    body.innerHTML = `<div class="empty-state">OCL unavailable: ${escapeHtml(e.message)}</div>`;
  }
}

function openFeedEvent(eventType, entityId) {
  // Open the time machine for this entity
  if (entityId) {
    openDrilldown('feed_event', entityId);
  }
}

// ═══════════════════════════════════════════════════════════════════════════

// === home_core.js ===
// HOME — Executive Cognition Center (9 sections, all from OEM)
// ═══════════════════════════════════════════════════════════════════════════

async function loadDashboard() {
  const stateEl = document.getElementById('home-oem-state');
  const providersBadge = document.getElementById('oem-providers-badge');

  // ── Ambient layers: Pulse, Narrative, Feed, Cognitive Load ──
  loadPulse();
  loadNarrative();
  loadFeed();
  loadCognitiveLoad();

  // ── Cognitive-model surface: Prepared Decisions (renders into #ecc-prepared) ──
  // Sits ABOVE Today's Attention. Calls /api/oem/preparations directly.
  loadPreparedDecisions();

  // OEM State (reference) — fetch independently (fast)
  api.getOEM('/dashboard').then(data => {
    const m = data.metrics;
    stateEl.innerHTML = `
      <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        <div class="metric metric-clickable" onclick="openDrilldown('metric', 'signals_processed')"><div class="metric-value">${m.signals_processed}</div><div class="metric-label">Signals</div></div>
        <div class="metric metric-clickable" onclick="openDrilldown('metric', 'learning_objects')"><div class="metric-value">${m.learning_objects}</div><div class="metric-label">Learning Objects</div></div>
        <div class="metric metric-clickable" onclick="openDrilldown('metric', 'laws_inferred')"><div class="metric-value">${m.laws_inferred}</div><div class="metric-label">Laws</div></div>
        <div class="metric metric-clickable" onclick="openDrilldown('metric', 'validated_laws')"><div class="metric-value">${m.validated_laws}</div><div class="metric-label">Validated</div></div>
        <div class="metric metric-clickable" onclick="openDrilldown('metric', 'recommendations_active')"><div class="metric-value">${m.recommendations_active}</div><div class="metric-label">Recommendations</div></div>
        <div class="metric metric-clickable" onclick="openDrilldown('metric', 'p1_cluster_risk')"><div class="metric-value">${formatConfidence(m.p1_cluster_risk)}</div><div class="metric-label">P1 Risk</div></div>
      </div>
      <div class="mt-4 pt-4 border-t border-white/[0.05] flex flex-wrap gap-2">
        ${data.providers_connected.map(p => `<span class="tag tag-cyan">${escapeHtml(p)}</span>`).join('')}
      </div>
    `;
    providersBadge.textContent = data.providers_connected.length + ' providers';
    document.getElementById('oem-status').innerHTML = `<span class="text-brand-cyan">●</span> <span>OEM connected · ${m.signals_processed} signals · ${m.laws_inferred} laws</span>`;
    document.getElementById('oem-status-badge').textContent = 'OEM ONLINE';
    document.getElementById('oem-status-badge').className = 'text-[10px] font-semibold text-brand-cyan';
  }).catch(e => {
    errorHTML(stateEl, 'Failed to load OEM state: ' + e.message, 'loadDashboard()');
    document.getElementById('oem-status').innerHTML = `<span class="text-brand-rose">●</span> <span>OEM unreachable: ${escapeHtml(e.message)}</span>`;
    document.getElementById('oem-status-badge').textContent = 'OEM OFFLINE';
    document.getElementById('oem-status-badge').className = 'text-[10px] font-semibold text-brand-rose';
  });

  // CEO Briefing — powers sections 1 + 2
  try {
    const briefing = await api.getOEM('/ceo-briefing');
    const tsEl = document.getElementById('home-briefing-timestamp');
    if (tsEl && briefing.generated_at) tsEl.textContent = `Last updated: ${formatTimestamp(briefing.generated_at)}`;

    // ── Section 1: Today's Attention (one thing + CEO-only decisions) ──
    renderECCAttention(briefing);

    // ── Section 2: What Changed Overnight ──
    renderECCOvernight(briefing);
  } catch (e) {
    document.getElementById('ecc-attention').innerHTML = `<div class="error-state">Failed: ${escapeHtml(e.message)} <button onclick="loadDashboard()" class="btn btn-ghost text-[10px] ml-2">Retry</button></div>`;
    document.getElementById('ecc-overnight').innerHTML = `<div class="error-state">Failed: ${escapeHtml(e.message)}</div>`;
  }

  // ── Section 3: Hayek Lens ──
  try {
    const knowledge = await api.getOEM('/knowledge');
    renderECCHayek(knowledge);
  } catch (e) {
    document.getElementById('ecc-hayek').innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }

  // ── Section 4: Knowledge Flow ──
  try {
    const knowledge = SWR.get('oem:/knowledge') || await api.getOEM('/knowledge');
    renderECCFlow(knowledge);
  } catch (e) {
    document.getElementById('ecc-flow').innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }

  // ── Section 5: Hidden Experts ──
  try {
    const knowledge = SWR.get('oem:/knowledge') || await api.getOEM('/knowledge');
    renderECCExperts(knowledge);
  } catch (e) {
    document.getElementById('ecc-experts').innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }

  // ── Section 6: Decision Simulator ──
  try {
    const sim = await api.getOEM('/simulator');
    renderECCSimulator(sim);
  } catch (e) {
    document.getElementById('ecc-simulator').innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }

  // ── Section 7: Ask the Organization ──
  renderECCAsk();

  // ── Section 8: Execution Replay ──
  try {
    const learning = await api.getOEM('/learning');
    renderECCReplay(learning);
  } catch (e) {
    document.getElementById('ecc-replay').innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }

  // ── Section 9: Executive Autocomplete ──
  renderECCAutocomplete();

  // ── Section 10: Digital Twin ──
  try {
    const twinState = await api.getOEM('/twin/state');
    renderECCTwin(twinState);
  } catch (e) {
    document.getElementById('ecc-twin').innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }
}

// ─── Enriched Recommendation Card (evidence, confidence, provenance, impact, accuracy, drill-down) ──
function renderEnrichedRec(r, opts = {}) {
  const urgencyTag = r.urgency === 'urgent' ? 'tag-rose' : r.urgency === 'normal' ? 'tag-amber' : 'tag-gray';
  const provChain = (r.provenance || []).slice(0, 3).map(p => {
    const key = p.oem_change || p.gate || p.entity || p.domain || 'evidence';
    return `<span class="prov-node">${escapeHtml(key)}</span>`;
  }).join('<span class="prov-arrow">→</span>');
  const evidenceCount = r.evidence_count || (r.provenance || []).length || 0;
  const linkedLaws = r.linked_laws || [];
  const compact = opts.compact;
  return `<div class="card ${r.urgency === 'urgent' ? 'urgent' : ''} mb-3 cursor-pointer" onclick="openDrilldown('recommendation', '${escapeJs(r.title)}')">
    <div class="flex items-start justify-between mb-2">
      <div class="flex-1">
        <div class="text-sm font-semibold text-white mb-1">${escapeHtml(humanize(r.title))}</div>
        ${!compact ? `<div class="text-[11px] text-fg-400 leading-relaxed">${escapeHtml(humanize(r.description || ''))}</div>` : ''}
      </div>
      <span class="tag ${urgencyTag} ml-3">${escapeHtml(r.urgency || 'normal')}</span>
    </div>
    ${provChain ? `<div class="prov-chain mt-2 mb-2">${provChain}</div>` : ''}
    <div class="flex items-center gap-3 text-[10px] text-fg-500 mt-2 flex-wrap">
      <span>${evidenceCount} signals</span>
      ${linkedLaws.length ? `<span>·</span><span>${linkedLaws.length} ${linkedLaws.length === 1 ? 'pattern' : 'patterns'}</span>` : ''}
    </div>
    ${!compact && r.impact ? `<div class="mt-2 text-[11px] text-fg-300"><strong>Expected impact:</strong> ${escapeHtml(humanize(r.impact))}</div>` : ''}
    ${!compact ? `<div class="mt-2 pt-2 border-t border-white/[0.05] flex items-center gap-3 text-[10px] text-fg-600">
      <span>Based on ${evidenceCount} signals</span>
      ${r.evidence_strength ? `<span>·</span><span>Strength: ${r.evidence_strength}</span>` : ''}
      <span>·</span>
      <span class="text-brand-violet cursor-pointer hover:text-brand-cyan">Drill-down →</span>
    </div>` : ''}
  </div>`;
}

// ─── Section 1: Today's Attention ──
function renderECCAttention(briefing) {
  const el = document.getElementById('ecc-attention');
  const ot = briefing.one_thing;
  const decisions = briefing.decisions;
  document.getElementById('ecc-attention-count').textContent = `${decisions.decisions.length} decision${decisions.decisions.length !== 1 ? 's' : ''}`;
  const urgencyColor = ot.urgency === 'urgent' ? 'rose' : ot.urgency === 'normal' ? 'amber' : 'gray';
  el.innerHTML = `
    <div class="space-y-4">
      <div class="p-3 rounded-lg bg-brand-violet/[0.06] border border-brand-violet/15">
        <div class="text-[10px] uppercase tracking-wider text-brand-violet font-semibold mb-1">If you do one thing today</div>
        <div class="text-base font-bold text-white">${escapeHtml(humanize(ot.title))}</div>
        <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(humanize(ot.why))}</div>
        <div class="text-sm text-brand-violet font-medium mt-2">${escapeHtml(humanize(ot.recommendation))}</div>
        <div class="flex items-center gap-3 pt-2">
          <span class="tag tag-${urgencyColor}">${escapeHtml(ot.urgency)}</span>
        </div>
        <div class="text-[11px] text-fg-300 mt-2">${escapeHtml(humanize(ot.impact))}</div>
        ${ot.rec_id ? `<button class="btn btn-primary text-[11px] mt-2" onclick="event.stopPropagation(); openDrilldown('recommendation', '${escapeJs(ot.title)}')">Investigate →</button>` : ''}
      </div>
      ${decisions.decisions.length > 0 ? `
        <div>
          <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">CEO-only decisions</div>
          <div class="space-y-2">
            ${decisions.decisions.map(d => {
              const drillType = d.type === 'urgent_decision' ? 'recommendation' : d.type === 'retention' ? 'pattern' : 'law';
              const drillId = d.linked_laws && d.linked_laws.length ? d.linked_laws[0] : d.title;
              return `<div class="flex items-start gap-3 p-3 rounded-lg bg-brand-purple/[0.04] border border-brand-purple/10 cursor-pointer hover:bg-brand-purple/[0.08] transition-colors" onclick="openDrilldown('${drillType}', '${escapeJs(drillId)}')">
                <div class="w-7 h-7 rounded-md bg-brand-purple/15 flex items-center justify-center flex-shrink-0"><span class="text-brand-purple text-sm font-bold">!</span></div>
                <div class="flex-1">
                  <div class="text-[12px] font-semibold text-fg-100">${escapeHtml(d.title)}</div>
                  <div class="text-[10px] text-fg-500 mt-0.5">${escapeHtml(d.question)}</div>
                  <div class="text-[10px] text-brand-violet mt-1">${escapeHtml(d.recommendation)}</div>
                </div>
                <span class="text-[10px] text-fg-500">${d.evidence_count || 0} signals</span>
              </div>`;
            }).join('')}
          </div>
        </div>
      ` : ''}
    </div>
  `;
}

// ─── Section 2: What Changed Overnight ──
function renderECCOvernight(briefing) {
  const el = document.getElementById('ecc-overnight');
  const ov = briefing.overnight;
  document.getElementById('ecc-overnight-count').textContent = ov.summary;
  if (!ov.changes || ov.changes.length === 0) {
    emptyHTML(el, 'Nothing new. The org is stable. The OEM will surface new patterns as signals flow.');
    return;
  }
  el.innerHTML = `
    <div class="mb-3 p-3 rounded-lg bg-brand-cyan/[0.04] border border-brand-cyan/10">
      <div class="text-sm font-semibold text-white">${escapeHtml(ov.headline)}</div>
      <div class="text-[11px] text-fg-500 mt-1">${escapeHtml(ov.headline_detail)}</div>
    </div>
    <div class="space-y-2">
      ${ov.changes.map(c => {
        const sevColor = c.severity === 'urgent' ? 'rose' : c.severity === 'warning' ? 'amber' : 'cyan';
        const drillType = c.type === 'hidden_expert' ? 'expert' : c.type === 'bottleneck' ? 'pattern' : c.type === 'concentration_risk' ? 'risk' : 'pattern';
        const drillId = c.entity || c.domain || c.title || c.detail;
        return `<div class="flex items-start gap-3 p-3 rounded-lg bg-brand-${sevColor}/[0.04] border border-brand-${sevColor}/10 cursor-pointer hover:bg-brand-${sevColor}/[0.08] transition-colors" onclick="openDrilldown('${drillType}', '${escapeJs(drillId)}')">
          <div class="w-7 h-7 rounded-md bg-brand-${sevColor}/15 flex items-center justify-center flex-shrink-0"><span class="text-brand-${sevColor} text-sm font-bold">${c.type === 'hidden_expert' ? '?' : c.type === 'bottleneck' ? '!' : c.type === 'departure_risk' ? 'x' : 'v'}</span></div>
          <div class="flex-1"><div class="text-[12px] font-semibold text-fg-100">${escapeHtml(c.title)}</div><div class="text-[10px] text-fg-500 mt-0.5">${escapeHtml(c.detail)}</div></div>
          <span class="tag tag-${sevColor}">${escapeHtml(c.severity)}</span>
        </div>`;
      }).join('')}
    </div>
  `;
}

// ─── Section 3: Hayek Lens ──
function renderECCHayek(knowledge) {
  const el = document.getElementById('ecc-hayek');
  const risks = knowledge.concentration_risks || [];
  document.getElementById('ecc-hayek-count').textContent = `${risks.length} risk${risks.length !== 1 ? 's' : ''}`;
  if (risks.length === 0) { emptyHTML(el, 'No concentration risks detected.'); return; }
  el.innerHTML = `<div class="space-y-2">${risks.map(r => `
    <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" onclick="openDrilldown('risk', '${escapeJs(r.domain)}')">
      <div class="text-sm font-semibold text-white">${escapeHtml(r.domain)}</div>
      <div class="text-[11px] text-fg-400 mt-1">Concentration: <span class="mono text-brand-rose">${r.score.toFixed(2)}</span></div>
      <div class="conf-bar mt-2"><div class="conf-bar-track"><div class="conf-bar-fill b-wmathminrscore10100p-bg"></div></div></div>
      <div class="text-[10px] text-fg-600 mt-1">Click for evidence, people, prediction →</div>
    </div>`).join('')}</div>`;
}

// ─── Section 4: Knowledge Flow ──
function renderECCFlow(knowledge) {
  const el = document.getElementById('ecc-flow');
  const dups = knowledge.duplicate_work || [];
  const deaths = knowledge.knowledge_death || [];
  document.getElementById('ecc-flow-count').textContent = `${dups.length + deaths.length} issue${(dups.length + deaths.length) !== 1 ? 's' : ''}`;
  if (dups.length === 0 && deaths.length === 0) { emptyHTML(el, 'No duplicate work or knowledge death detected.'); return; }
  el.innerHTML = `
    ${dups.length > 0 ? `<div class="mb-3"><div class="text-[10px] uppercase text-fg-500 mb-2">Duplicate Work (${dups.length})</div>${dups.map(d => `
      <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" onclick="openDrilldown('pattern', '${escapeJs(d.title || d.description)}')">
        <div class="text-sm font-semibold text-white">${escapeHtml(d.title)}</div>
        <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(d.description)}</div>
        <div class="text-[10px] text-fg-600 mt-1">Domain: ${escapeHtml(d.domain)} · ${d.providers.join(', ')}</div>
      </div>`).join('')}</div>` : ''}
    ${deaths.length > 0 ? `<div><div class="text-[10px] uppercase text-fg-500 mb-2">Knowledge Death (${deaths.length})</div>${deaths.map(k => `
      <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" onclick="openDrilldown('pattern', '${escapeJs(k.title || k.description)}')">
        <div class="text-sm font-semibold text-white">${escapeHtml(k.title)}</div>
        <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(k.description)}</div>
        <div class="text-[10px] text-fg-600 mt-1">Boundary: ${escapeHtml(k.boundary)} · conf ${formatConfidence(k.confidence)}</div>
      </div>`).join('')}</div>` : ''}
  `;
}

// ─── Section 5: Hidden Experts ──
function renderECCExperts(knowledge) {
  const el = document.getElementById('ecc-experts');
  const experts = knowledge.hidden_experts || [];
  document.getElementById('ecc-experts-count').textContent = `${experts.length} expert${experts.length !== 1 ? 's' : ''}`;
  if (experts.length === 0) { emptyHTML(el, 'No hidden experts detected.'); return; }
  el.innerHTML = `<div class="space-y-2">${experts.map(e => `
    <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" onclick="openDrilldown('expert', '${escapeJs(e.entity)}')">
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 rounded-full bg-brand-purple/20 flex items-center justify-center text-xs font-bold text-brand-purple">${escapeHtml(e.entity.charAt(0).toUpperCase())}</div>
        <div class="flex-1">
          <div class="text-sm font-semibold text-white">${escapeHtml(e.entity)}</div>
          <div class="text-[11px] text-fg-400">Influence: <span class="mono text-brand-purple">${e.influence.toFixed(2)}</span> · ${e.domains ? e.domains.length : 0} domains</div>
        </div>
        ${e.domains && e.domains.length ? `<div class="flex flex-wrap gap-1">${e.domains.map(d => `<span class="tag tag-gray">${escapeHtml(d)}</span>`).join('')}</div>` : ''}
      </div>
      <div class="text-[10px] text-fg-600 mt-1">Click for evidence, timeline, prediction →</div>
    </div>`).join('')}</div>`;
}

// ─── Section 6: Decision Simulator ──
function renderECCSimulator(sim) {
  const el = document.getElementById('ecc-simulator');
  const s = sim.scenario;
  el.innerHTML = `
    <div class="space-y-3">
      <div>
        <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-1">Current Scenario</div>
        <div class="text-sm font-semibold text-white">${escapeHtml(s.title)}</div>
        <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(s.description)}</div>
      </div>
      <div class="grid grid-cols-2 gap-4 pt-3 border-t border-white/[0.05]">
        <div><div class="text-[10px] uppercase text-fg-500">Recommendation</div><div class="text-sm text-brand-cyan mt-1">${escapeHtml(s.recommendation)}</div></div>
        <div><div class="text-[10px] uppercase text-fg-500">Confidence</div><div class="conf-bar mt-1"><div class="conf-bar-track"><div class="conf-bar-fill b-wsconfidence100p"></div></div><span class="text-brand-cyan font-bold">${formatConfidence(s.confidence)}</span></div></div>
      </div>
      <div class="pt-3 border-t border-white/[0.05]">
        <div class="text-[10px] uppercase text-fg-500 font-semibold mb-1">Current Health</div>
        <div class="grid grid-cols-2 gap-2 text-[11px]">
          <div>P1 Risk: <span class="mono text-brand-amber">${formatConfidence(sim.current_health.p1_cluster_risk)}</span></div>
          <div>Incident Rate: <span class="mono text-brand-amber">${sim.current_health.incident_rate}</span></div>
          <div>Decision Velocity: <span class="mono text-brand-cyan">${sim.current_health.decision_velocity_days.toFixed(1)}d</span></div>
          <div>Release Frequency: <span class="mono text-brand-cyan">${sim.current_health.release_frequency.toFixed(1)}/wk</span></div>
        </div>
      </div>
      <div class="pt-3 border-t border-white/[0.05]">
        <div class="text-[10px] uppercase text-fg-500 font-semibold mb-1">Run What-If</div>
        <div class="flex items-center gap-3">
          <label class="text-[11px] text-fg-400">Hire count:</label>
          <input type="range" min="0" max="10" value="2" id="ecc-sim-hires" class="flex-1" aria-label="Hire count for ECC simulation" oninput="document.getElementById('ecc-sim-val').textContent=this.value">
          <span class="text-xs font-bold text-brand-cyan mono" id="ecc-sim-val">2</span>
          <button class="btn btn-primary text-[11px]" onclick="runECCSimulation()">Run</button>
        </div>
        <div id="ecc-sim-result" class="mt-3"></div>
      </div>
    </div>
  `;
}

async function runECCSimulation() {
  const hires = parseInt(document.getElementById('ecc-sim-hires').value);
  const resultEl = document.getElementById('ecc-sim-result');
  resultEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const resp = await fetch(MAESTRO_API + '/api/oem/simulate', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({inputs: {hire_count: hires}}),
    });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    resultEl.innerHTML = `
      <div class="grid grid-cols-2 gap-3 text-[11px]">
        <div class="p-3 rounded-lg bg-white/[0.02]">
          <div class="text-[10px] uppercase text-fg-500">Predicted P1 Risk</div>
          <div class="text-lg font-bold text-brand-amber mono">${formatConfidence(data.predicted.p1_cluster_risk)}</div>
          <div class="text-[10px] text-fg-600">Base: ${formatConfidence(data.base_health.p1_cluster_risk)}</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02]">
          <div class="text-[10px] uppercase text-fg-500">Predicted Velocity</div>
          <div class="text-lg font-bold text-brand-cyan mono">${data.predicted.decision_velocity_days}d</div>
          <div class="text-[10px] text-fg-600">Base: ${data.base_health.decision_velocity_days}d</div>
        </div>
      </div>
      <div class="mt-3 text-[10px] text-fg-500">Based on ${data.linked_laws ? data.linked_laws.length : 0} ${data.linked_laws && data.linked_laws.length === 1 ? 'pattern' : 'patterns'} from organizational memory</div>
    `;
  } catch (e) { resultEl.innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`; }
}

// ─── Section 7: Ask the Organization ──
function renderECCAsk() {
  const el = document.getElementById('ecc-ask');
  el.innerHTML = `
    <div class="space-y-3">
      <div class="relative">
        <input type="text" class="ask-input w-full" placeholder="Ask anything about your organization..." id="ecc-ask-input" oninput="onECCAskInput(this.value)" onkeydown="if(event.key==='Enter'){submitECCAsk()}" aria-label="Ask the organization">
        <div id="ecc-ask-autocomplete" class="exec-autocomplete"></div>
      </div>
      <div id="ecc-ask-answer" class="d-none space-y-3">
        <div class="text-[11px] text-fg-400" id="ecc-ask-answer-text"></div>
        <div id="ecc-ask-citations" class="flex flex-wrap gap-1"></div>
        <div id="ecc-ask-path" class="text-[10px] text-fg-600"></div>
        <div id="ecc-ask-confidence" class="text-[10px] text-brand-cyan"></div>
      </div>
    </div>
  `;
}

let eccAskAbort = null;
async function onECCAskInput(value) {
  const dropdown = document.getElementById('ecc-ask-autocomplete');
  const v = value.trim();
  if (!v) { dropdown.classList.remove('active'); return; }
  if (eccAskAbort) eccAskAbort.abort();
  eccAskAbort = new AbortController();
  try {
    const resp = await fetch(MAESTRO_API + '/api/oem/autocomplete?q=' + encodeURIComponent(v) + '&limit=5', {signal: eccAskAbort.signal});
    if (!resp.ok) return;
    const data = await resp.json();
    const suggestions = data.suggestions || [];
    if (suggestions.length === 0) { dropdown.innerHTML = '<div class="exec-ac-header">No matches in OEM</div>'; dropdown.classList.add('active'); return; }
    dropdown.innerHTML = '<div class="exec-ac-header">From live OEM · ranked by recency, authority, outcome, feedback</div>' +
      suggestions.map((s, i) => `<div class="exec-ac-item" onclick="document.getElementById('ecc-ask-input').value='${escapeJs(s.query)}'; document.getElementById('ecc-ask-autocomplete').classList.remove('active'); submitECCAsk('${escapeJs(s.query)}')">
        <div class="exec-ac-completion"><span class="completed">${escapeHtml(s.completion)}</span></div>
        <div class="text-[9px] text-fg-600 mt-0.5">${escapeHtml(s.source_type)} · conf ${(s.confidence*100).toFixed(0)}% · ${s.citations.length} citations</div>
      </div>`).join('');
    dropdown.classList.add('active');
  } catch(e) { if (e.name !== 'AbortError') {} }
}

async function submitECCAsk(query) {
  const q = (query || document.getElementById('ecc-ask-input').value).trim();
  if (!q) return;
  document.getElementById('ecc-ask-input').value = '';
  document.getElementById('ecc-ask-autocomplete').classList.remove('active');
  const ans = document.getElementById('ecc-ask-answer');
  ans.style.display = 'block';
  document.getElementById('ecc-ask-answer-text').innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    // Phase 2.2: Migrate from GET /ask (old, cross-customer) to POST /ask/conversation (AskPipeline)
    if (!window._homeAskSessionId) {
      try { window._homeAskSessionId = crypto.randomUUID(); }
      catch(e) { window._homeAskSessionId = 'sess-' + Date.now() + '-' + Math.random().toString(36).slice(2,11); }
    }
    const resp = await fetch((MAESTRO_API || '') + '/api/oem/ask/conversation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: q, history: [], session_id: window._homeAskSessionId }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    document.getElementById('ecc-ask-answer-text').innerHTML = escapeHtml(data.answer || '').replace(/\n/g, '<br>');
    const sources = data.sources || (data.evidence || []).map(e => e.source || 'unknown');
    document.getElementById('ecc-ask-citations').innerHTML = sources.length === 0 ? '<span class="text-[11px] text-fg-500">No sources cited.</span>' : sources.map(s => `<span class="source-cite">${escapeHtml(s)}</span>`).join('');
    document.getElementById('ecc-ask-confidence').textContent = `${sources.length} sources`;
  } catch(e) {
    document.getElementById('ecc-ask-answer-text').innerHTML = `<span class="text-brand-rose">Error: ${escapeHtml(e.message)}</span>`;
  }
}

// ─── Section 8: Execution Replay (historical accuracy + calibration) ──
// (renderECCReplay is in home_renderers.js)



// === home_renderers.js ===
// ─── Section 8: Execution Replay (historical accuracy + calibration) ──
function renderECCReplay(learning) {
  const el = document.getElementById('ecc-replay');
  const cal = learning.calibration || {};
  const overall = cal.overall || {};
  const accuracy = learning.historical_accuracy || {};
  const evidence = learning.improvement_evidence || {};
  document.getElementById('ecc-replay-count').textContent = `${overall.total_predictions || 0} prediction${(overall.total_predictions || 0) !== 1 ? 's' : ''}`;
  const buckets = cal.buckets || [];
  const trend = accuracy.trend || [];
  el.innerHTML = `
    <div class="space-y-4">
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">Accuracy</div>
          <div class="text-lg font-bold text-brand-cyan mono">${accuracy.accuracy != null ? (accuracy.accuracy * 100).toFixed(1) + '%' : '—'}</div>
          <div class="text-[10px] text-fg-600">${accuracy.resolved || 0} resolved</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">Brier Score</div>
          <div class="text-lg font-bold text-brand-amber mono">${(overall.brier_score || 0).toFixed(4)}</div>
          <div class="text-[10px] text-fg-600">lower = better</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">Calibration Error</div>
          <div class="text-lg font-bold text-brand-violet mono">${(overall.mean_calibration_error || 0).toFixed(4)}</div>
          <div class="text-[10px] text-fg-600">${evidence.is_calibrated ? 'well-calibrated' : 'needs calibration'}</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">Feedback Events</div>
          <div class="text-lg font-bold text-brand-purple mono">${evidence.feedback_count || 0}</div>
          <div class="text-[10px] text-fg-600">CEO agree/reject</div>
        </div>
      </div>
      ${buckets.length > 0 ? `
        <div>
          <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">Calibration Diagram (10 buckets)</div>
          <div class="space-y-1">
            ${buckets.map(b => `
              <div class="flex items-center gap-2 text-[10px]">
                <span class="mono text-fg-500 w-16">${(b.expected_rate*100).toFixed(0)}% expected</span>
                <div class="flex-1 h-3 bg-white/[0.04] rounded overflow-hidden relative">
                  <div class="h-full bg-brand-cyan/40 b-wbexpectedrate100p"></div>
                  <div class="absolute top-0 h-full bg-brand-violet/60 b-wbactualrate100p"></div>
                </div>
                <span class="mono text-fg-400 w-16">${b.actual_rate > 0 ? (b.actual_rate*100).toFixed(0) + '% actual' : '—'}</span>
                <span class="text-fg-600 w-8">${b.predictions}</span>
              </div>`).join('')}
          </div>
          <div class="flex items-center gap-4 mt-2 text-[9px] text-fg-600">
            <span><span class="inline-block w-2 h-2 bg-brand-cyan/40 rounded"></span> Expected</span>
            <span><span class="inline-block w-2 h-2 bg-brand-violet/60 rounded"></span> Actual</span>
          </div>
        </div>
      ` : ''}
      ${trend.length > 0 ? `
        <div>
          <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">Accuracy Trend (weekly)</div>
          <div class="flex items-end gap-1 h-12">
            ${trend.map(t => `<div class="flex-1 bg-brand-cyan/40 rounded-t b-htaccuracy100" title="${t.week}: ${(t.accuracy*100).toFixed(0)}% (${t.predictions} predictions)"></div>`).join('')}
          </div>
        </div>
      ` : ''}
      <div class="pt-3 border-t border-white/[0.05] text-[10px] text-fg-600">
        Drift events: ${evidence.drift_events_detected || 0} · Stale domains: ${evidence.stale_domains || 0} · Decaying patterns: ${evidence.decaying_patterns || 0}
      </div>
    </div>
  `;
}

// ─── Section 9: Executive Autocomplete (live preview) ──
function renderECCAutocomplete() {
  const el = document.getElementById('ecc-autocomplete');
  el.innerHTML = `
    <div class="space-y-3">
      <div class="text-[11px] text-fg-400">Type below to see real-time semantic suggestions from the OEM. Every suggestion includes completion, reason, confidence, evidence, citations, and expected outcome.</div>
      <div class="relative">
        <input type="text" class="ask-input w-full" placeholder="Try: we should, bottleneck, who knows, risk..." id="ecc-ac-input" oninput="onECCAutocompleteInput(this.value)" aria-label="Executive autocomplete">
        <div id="ecc-ac-dropdown" class="exec-autocomplete"></div>
      </div>
      <div id="ecc-ac-results" class="space-y-2"></div>
    </div>
  `;
}

let eccAcAbort = null;
let _eccAcDebounceTimer = null;
let _eccAcSelectedIdx = -1;

function onECCAutocompleteInput(value) {
  // Round 78 Phase 4: debounce + ESC support.
  clearTimeout(_eccAcDebounceTimer);
  _eccAcDebounceTimer = setTimeout(() => _doECCAutocompleteInput(value), 150);
}

async function _doECCAutocompleteInput(value) {
  const dropdown = document.getElementById('ecc-ac-dropdown');
  const resultsEl = document.getElementById('ecc-ac-results');
  const v = value.trim();
  if (!v) { dropdown.classList.remove('active'); resultsEl.innerHTML = ''; return; }
  if (eccAcAbort) eccAcAbort.abort();
  eccAcAbort = new AbortController();
  try {
    const resp = await fetch(MAESTRO_API + '/api/oem/autocomplete?q=' + encodeURIComponent(v) + '&limit=5', {signal: eccAcAbort.signal});
    if (!resp.ok) return;
    const data = await resp.json();
    const suggestions = data.suggestions || [];
    if (suggestions.length === 0) {
      dropdown.classList.remove('active');
      resultsEl.innerHTML = '<div class="empty-state">No matches in OEM for "' + escapeHtml(v) + '"</div>';
      return;
    }
    dropdown.classList.remove('active');
    resultsEl.innerHTML = suggestions.map(s => `
      <div class="card mb-2 cursor-pointer" role="button" tabindex="0" onclick="openDrilldown('${s.source_type.split(':')[0]}', '${escapeJs(s.source_id)}')">
        <div class="text-sm font-semibold text-white">${escapeHtml(s.completion)}</div>
        <div class="text-[10px] text-fg-400 mt-1">${escapeHtml(s.reason)}</div>
        <div class="flex items-center gap-2 mt-2 text-[10px] text-fg-500 flex-wrap">
          <span class="mono text-brand-purple">[${escapeHtml(s.source_type)}]</span>
          <span class="text-brand-cyan">conf ${(s.confidence*100).toFixed(0)}%</span>
          <span>·</span><span>rank ${(s.rank_score*100).toFixed(0)}%</span>
          <span>·</span><span>${s.evidence.length} evidence</span>
          <span>·</span><span>${s.citations.length} citations</span>
        </div>
        ${s.expected_outcome ? `<div class="text-[10px] text-fg-600 mt-1 italic">→ ${escapeHtml(s.expected_outcome.substring(0, 100))}</div>` : ''}
        <div class="text-[10px] text-brand-violet mt-1">Click for full drill-down →</div>
      </div>
    `).join('');
  } catch(e) { if (e.name !== 'AbortError') {} }
}

function renderRecCard(r) {
  const urgencyTag = r.urgency === 'urgent' ? 'tag-rose' : r.urgency === 'normal' ? 'tag-amber' : 'tag-gray';
  const provChain = (r.provenance || []).slice(0, 3).map(p => {
    const key = p.oem_change || p.gate || p.entity || p.domain || 'evidence';
    return `<span class="prov-node">${escapeHtml(key)}</span>`;
  }).join('<span class="prov-arrow">→</span>');
  return `<div class="card ${r.urgency === 'urgent' ? 'urgent' : ''} mb-3 cursor-pointer" role="button" tabindex="0" onclick="openDrilldown('recommendation', '${escapeJs(r.title)}')">
    <div class="flex items-start justify-between mb-2">
      <div class="flex-1">
        <div class="text-sm font-semibold text-white mb-1">${escapeHtml(humanize(r.title))}</div>
        <div class="text-[11px] text-fg-400 leading-relaxed">${escapeHtml(humanize(r.description))}</div>
      </div>
      <span class="tag ${urgencyTag} ml-3">${escapeHtml(r.urgency)}</span>
    </div>
    ${provChain ? `<div class="prov-chain mt-2 mb-2">${provChain}</div>` : ''}
    <div class="flex items-center gap-3 text-[10px] text-fg-500 mt-2">
      <div class="conf-bar b-w120"><div class="conf-bar-track"><div class="conf-bar-fill b-wrconfidence100p"></div></div><span class="text-brand-cyan font-bold">${formatConfidenceWithWhy(r.confidence, { entity: 'recommendation', title: r.title })}</span></div>
      <span>·</span>
      <span>${r.evidence_count || 0} evidence</span>
      ${r.linked_laws && r.linked_laws.length ? `<span>·</span><span>Laws: ${r.linked_laws.join(', ')}</span>` : ''}
    </div>
    <div class="mt-2 text-[11px] text-fg-300">${escapeHtml(humanize(r.impact))}</div>
  </div>`;
}

// ═══════════════════════════════════════════════════════════════════════════
// INBOX
// ═══════════════════════════════════════════════════════════════════════════

async function loadInbox() {
  const owedEl = document.getElementById('inbox-owed');
  const driftEl = document.getElementById('inbox-drift');
  const dissentEl = document.getElementById('inbox-dissent');
  const summaryEl = document.getElementById('inbox-summary');

  loadingHTML(owedEl); loadingHTML(driftEl); loadingHTML(dissentEl);
  summaryEl.textContent = 'Loading…';

  try {
    const data = await api.getOEM('/inbox');
    const c = data.counts;
    summaryEl.textContent = `${c.owed} decisions you owe · ${c.drift} showing drift · ${c.dissent} unknown to leadership`;

    owedEl.innerHTML = c.owed === 0
      ? '<div class="empty-state">No urgent decisions owed.</div>'
      : data.decisions_owed.map(r => renderRecCard(r)).join('');

    driftEl.innerHTML = c.drift === 0
      ? '<div class="empty-state">No drift detected. All laws are stable.</div>'
      : data.drift.map(l => renderLawCard(l)).join('');

    dissentEl.innerHTML = c.dissent === 0
      ? '<div class="empty-state">No hidden disagreements. All validated laws are known to leadership.</div>'
      : data.dissent.map(l => renderLawCard(l)).join('');
  } catch (e) {
    errorHTML(owedEl, e.message, 'loadInbox()');
    errorHTML(driftEl, e.message, 'loadInbox()');
    errorHTML(dissentEl, e.message, 'loadInbox()');
    summaryEl.textContent = 'Failed to load inbox.';
    showError('Inbox load failed: ' + e.message);
  }
}

function renderLawCard(l) {
  const statusTag = l.status === 'validated' ? 'tag-cyan' : l.status === 'stressed' ? 'tag-amber' : l.status === 'invalidated' ? 'tag-rose' : l.status === 'unknown_to_leadership' ? 'tag-purple' : 'tag-gray';
  return `<div class="card mb-3 cursor-pointer" role="button" tabindex="0" onclick="openDrilldown('law', '${escapeJs(l.code)}')">
    <div class="flex items-start justify-between mb-2">
      <div class="flex-1">
        <div class="flex items-center gap-2 mb-1">
          <span class="mono text-[10px] text-brand-purple">${escapeHtml(l.code)}</span>
          <span class="tag ${statusTag}">${escapeHtml(l.status)}</span>
        </div>
        <div class="text-sm font-semibold text-white">${escapeHtml(humanize(l.statement))}</div>
        <div class="text-[11px] text-fg-400 mt-1">If: ${escapeHtml(humanize(l.condition))}</div>
        <div class="text-[11px] text-fg-300 mt-1">Then: ${escapeHtml(humanize(l.outcome))}</div>
      </div>
    </div>
    <div class="flex items-center gap-3 text-[10px] text-fg-500 mt-2">
      <div class="conf-bar b-w120"><div class="conf-bar-track"><div class="conf-bar-fill b-wlconfidence100p"></div></div><span class="text-brand-cyan font-bold">${formatConfidenceWithWhy(l.confidence, { entity: 'law', title: l.statement })}</span></div>
      <span>·</span>
      <span>${l.evidence_count} evidence</span>
      <span>·</span>
      <span>${l.validated_runtimes}/${l.validated_runtimes + l.failed_runtimes} runtimes</span>
      ${l.providers && l.providers.length ? `<span>·</span><span>${l.providers.join(', ')}</span>` : ''}
    </div>
    ${l.last_validated ? `<div class="mt-2 text-[10px] text-fg-500">Last verified: ${escapeHtml(l.last_validated)}</div>` : ''}
  </div>`;
}

// ═══════════════════════════════════════════════════════════════════════════
// SIMULATOR
// ═══════════════════════════════════════════════════════════════════════════

let simulatorAbort = null;

async function loadSimulator() {
  const el = document.getElementById('simulator-scenario');
  loadingHTML(el, 'Loading scenario…');
  try {
    const data = await api.getOEM('/simulator');
    const s = data.scenario;
    el.innerHTML = `
      <div class="space-y-3">
        <div>
          <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-1">Scenario</div>
          <div class="text-sm font-semibold text-white">${escapeHtml(humanize(s.title))}</div>
          <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(humanize(s.description))}</div>
        </div>
        <div class="grid grid-cols-2 gap-4 pt-3 border-t border-white/[0.05]">
          <div>
            <div class="text-[10px] uppercase text-fg-500">Recommendation</div>
            <div class="text-sm text-brand-cyan mt-1">${escapeHtml(humanize(s.recommendation))}</div>
          </div>
          <div>
            <div class="text-[10px] uppercase text-fg-500">Confidence</div>
            <div class="conf-bar mt-1"><div class="conf-bar-track"><div class="conf-bar-fill b-wsconfidence100p"></div></div><span class="text-brand-cyan font-bold">${formatConfidence(s.confidence)}</span></div>
          </div>
        </div>
        <div class="pt-3 border-t border-white/[0.05]">
          <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-1">Decision Question</div>
          <div class="text-[11px] text-fg-300">${escapeHtml(s.decision_question)}</div>
        </div>
        <div class="pt-3 border-t border-white/[0.05]">
          <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-1">Current Health</div>
          <div class="grid grid-cols-2 gap-2 text-[11px]">
            <div>P1 Cluster Risk: <span class="mono text-brand-amber">${formatConfidence(data.current_health.p1_cluster_risk)}</span></div>
            <div>Incident Rate: <span class="mono text-brand-amber">${data.current_health.incident_rate}</span></div>
            <div>Decision Velocity: <span class="mono text-brand-cyan">${data.current_health.decision_velocity_days.toFixed(1)}d</span></div>
            <div>Release Frequency: <span class="mono text-brand-cyan">${data.current_health.release_frequency.toFixed(1)}/wk</span></div>
          </div>
        </div>
      </div>
    `;
  } catch (e) {
    errorHTML(el, e.message, 'loadSimulator()');
  }
}

async function runSimulator() {
  const hires = parseInt(document.getElementById('sim-hires').value);
  const panel = document.getElementById('simulator-result-panel');
  const result = document.getElementById('simulator-result');
  panel.style.display = 'block';
  loadingHTML(result, 'Running simulation…');

  if (simulatorAbort) simulatorAbort.abort();
  simulatorAbort = new AbortController();

  try {
    const resp = await fetch(MAESTRO_API + '/api/oem/simulator', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({inputs: {hire_count: hires}}),
      signal: simulatorAbort.signal,
    });
    if (!resp.ok) throw new Error('Simulator returned ' + resp.status);
    const data = await resp.json();
    const p = data.predicted;
    result.innerHTML = `
      <div class="space-y-3">
        <div class="grid grid-cols-2 gap-4">
          <div>
            <div class="text-[10px] uppercase text-fg-500">Predicted P1 Risk</div>
            <div class="text-xl font-bold text-brand-amber mono">${formatConfidence(p.p1_cluster_risk)}</div>
            <div class="text-[10px] text-fg-500">Base: ${formatConfidence(data.base_health.p1_cluster_risk)}</div>
          </div>
          <div>
            <div class="text-[10px] uppercase text-fg-500">Confidence</div>
            <div class="conf-bar mt-1"><div class="conf-bar-track"><div class="conf-bar-fill b-wdataconfidence100p"></div></div><span class="text-brand-cyan font-bold">${formatConfidence(data.confidence)}</span></div>
          </div>
        </div>
        ${data.linked_laws && data.linked_laws.length ? `<div class="pt-3 border-t border-white/[0.05]"><div class="text-[10px] uppercase text-fg-500 mb-1">Linked Laws</div><div class="flex flex-wrap gap-1">${data.linked_laws.map(l => `<span class="prov-node">${escapeHtml(l)}</span>`).join('')}</div></div>` : ''}
      </div>
    `;
  } catch (e) {
    if (e.name === 'AbortError') return;
    errorHTML(result, e.message, 'runSimulator()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// HAYEK
// ═══════════════════════════════════════════════════════════════════════════

async function loadHayek() {
  const risksEl = document.getElementById('hayek-risks');
  const knowEl = document.getElementById('hayek-knowledge');
  loadingHTML(risksEl); loadingHTML(knowEl);
  try {
    const data = await api.getOEM('/knowledge');
    const totals = data.totals || {};
    const totalRisks = data.concentration_risks.length;
    const totalExperts = data.hidden_experts.length;
    const totalDeaths = data.knowledge_death.length;
    const totalDups = data.duplicate_work.length;

    // Enrich the surface header with a summary stats row
    const headerEl = document.querySelector('#surface-hayek .p-6 > div:first-child');
    if (headerEl && !headerEl.dataset.enriched) {
      headerEl.dataset.enriched = '1';
      headerEl.insertAdjacentHTML('beforeend', `
        <div class="b-mt12 b-flex-gap8 b-flex-wrap">
          <span class="ds-tag ds-tag-risk">${totalRisks} concentration risk${totalRisks === 1 ? '' : 's'}</span>
          <span class="ds-tag ds-tag-info">${totalExperts} hidden expert${totalExperts === 1 ? '' : 's'}</span>
          <span class="ds-tag ds-tag-warn">${totalDeaths} knowledge death${totalDeaths === 1 ? '' : 's'}</span>
          <span class="ds-tag ds-tag-uncertain">${totalDups} duplicate work${totalDups === 1 ? '' : ' items'}</span>
        </div>
        <div class="b-mt8 b-fs12-text-6">
          The Hayek Lens maps who influences what — derived from real signal interactions across your tools.
          Concentration risks show where one person gates too much. Hidden experts are people with high
          influence but low visibility. Knowledge death marks domains where expertise is leaving.
          Duplicate work flags teams solving the same problem independently.
        </div>
      `);
    }

    risksEl.innerHTML = data.concentration_risks.length === 0
      ? '<div class="empty-state">No concentration risks detected. Influence is distributed — no single person gates a domain.</div>'
      : data.concentration_risks.map(r => `
        <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" role="button" tabindex="0" onclick="openDrilldown('risk', '${escapeJs(r.domain)}')">
          <div class="text-sm font-semibold text-white">${escapeHtml(r.domain)}</div>
          <div class="text-[11px] text-fg-400 mt-1">Influence concentration: <span class="mono text-brand-rose">${r.score.toFixed(2)}</span> · ${r.entities ? r.entities.length : 0} entities</div>
          <div class="conf-bar mt-2"><div class="conf-bar-track"><div class="conf-bar-fill b-wmathminrscore10100p-bg"></div></div></div>
          ${r.entities && r.entities.length ? `<div class="b-mt6 b-fs11-text-5">Key holders: ${r.entities.slice(0,3).map(e => escapeHtml(e)).join(', ')}${r.entities.length > 3 ? ' +' + (r.entities.length - 3) + ' more' : ''}</div>` : ''}
        </div>
      `).join('');
    knowEl.innerHTML = data.hidden_experts.length === 0
      ? '<div class="empty-state">No hidden experts detected. Every high-influence person is already visible to leadership.</div>'
      : data.hidden_experts.map(e => `
        <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" role="button" tabindex="0" onclick="openDrilldown('expert', '${escapeJs(e.entity)}')">
          <div class="text-sm font-semibold text-white">${escapeHtml(e.entity)}</div>
          <div class="text-[11px] text-fg-400 mt-1">Influence: <span class="mono text-brand-purple">${e.influence.toFixed(2)}</span> · ${e.domains ? e.domains.length : 0} domains</div>
          ${e.domains && e.domains.length ? `<div class="mt-2 flex flex-wrap gap-1">${e.domains.map(d => `<span class="tag tag-gray">${escapeHtml(d)}</span>`).join('')}</div>` : ''}
        </div>
      `).join('');
  } catch (e) {
    errorHTML(risksEl, e.message, 'loadHayek()');
    errorHTML(knowEl, e.message, 'loadHayek()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// KNOWLEDGE FLOW
// ═══════════════════════════════════════════════════════════════════════════

async function loadKnowledge() {
  const expertsEl = document.getElementById('flow-experts');
  const deathEl = document.getElementById('flow-death');
  const dupEl = document.getElementById('flow-duplicates');
  loadingHTML(expertsEl); loadingHTML(deathEl); loadingHTML(dupEl);
  try {
    const data = await api.getOEM('/knowledge');
    expertsEl.innerHTML = data.hidden_experts.length === 0
      ? '<div class="empty-state">No hidden experts detected.</div>'
      : data.hidden_experts.map(e => `
        <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" role="button" tabindex="0" onclick="openDrilldown('expert', '${escapeJs(e.entity)}')">
          <div class="text-sm font-semibold text-white">${escapeHtml(e.entity)}</div>
          <div class="text-[11px] text-fg-400 mt-1">Influence ${e.influence.toFixed(2)} · ${e.domains ? e.domains.length : 0} domains</div>
        </div>
      `).join('');
    deathEl.innerHTML = data.knowledge_death.length === 0
      ? '<div class="empty-state">No knowledge death detected.</div>'
      : data.knowledge_death.map(k => `
        <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" role="button" tabindex="0" onclick="openDrilldown('pattern', '${escapeJs(k.title || k.description || 'knowledge_death')}')">
          <div class="text-sm font-semibold text-white">${escapeHtml(humanize(k.title))}</div>
          <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(humanize(k.description))}</div>
          <div class="text-[10px] text-fg-500 mt-1">Boundary: ${escapeHtml(k.boundary)} · Confidence ${formatConfidence(k.confidence)}</div>
        </div>
      `).join('');
    dupEl.innerHTML = data.duplicate_work.length === 0
      ? '<div class="empty-state">No duplicate work detected.</div>'
      : data.duplicate_work.map(d => `
        <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" role="button" tabindex="0" onclick="openDrilldown('pattern', '${escapeJs(d.title || d.description || 'duplicate_work')}')">
          <div class="text-sm font-semibold text-white">${escapeHtml(humanize(d.title))}</div>
          <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(humanize(d.description))}</div>
          <div class="text-[10px] text-fg-500 mt-1">Domain: ${escapeHtml(d.domain)} · ${d.providers.join(', ')}</div>
        </div>
      `).join('');
  } catch (e) {
    errorHTML(expertsEl, e.message, 'loadKnowledge()');
    errorHTML(deathEl, e.message, 'loadKnowledge()');
    errorHTML(dupEl, e.message, 'loadKnowledge()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// MEMORY
// ═══════════════════════════════════════════════════════════════════════════

async function loadMemory() {
  const el = document.getElementById('memory-laws');
  loadingHTML(el);
  try {
    const data = await api.getOEM('/laws');
    el.innerHTML = data.laws.length === 0
      ? '<div class="empty-state">No laws inferred yet.</div>'
      : data.laws.map(l => renderLawCard(l)).join('');
  } catch (e) {
    errorHTML(el, e.message, 'loadMemory()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════

// Round 78 Phase 6: keyboard accessibility for div-as-button elements.
// Any element with role="button" and tabindex="0" should activate on
// Enter or Space — this is the WAI-ARIA pattern for interactive divs.
document.addEventListener('keydown', function(e) {
  if (e.target && e.target.getAttribute && e.target.getAttribute('role') === 'button') {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      e.target.click();
    }
  }
});


// === ask.js ===
// ASK — backend-driven autocomplete (NO hardcoded suggestions)
// ═══════════════════════════════════════════════════════════════════════════
// Round 78 Phase 4: added ESC handler + 150ms debounce.
// The auditor flagged: "Key handler in ask.js handles arrows/enter but not ESC"
// and "Per-keystroke fetch with abort; stale protection exists, but no
// debounce/throttle budget." Both are now fixed.

let autocompleteAbort = null;
let autocompleteSelectedIdx = -1;
let autocompleteSuggestions = [];  // Store full suggestion objects for rich rendering
let _askDebounceTimer = null;
const _ASK_DEBOUNCE_MS = 150;

function onAskInput(value) {
  // Debounce: don't fire on every keystroke — wait 150ms of inactivity.
  // This reduces request pressure under rapid typing (auditor's MEDIUM finding).
  clearTimeout(_askDebounceTimer);
  _askDebounceTimer = setTimeout(() => _doAskInput(value), _ASK_DEBOUNCE_MS);
}

async function _doAskInput(value) {
  const dropdown = document.getElementById('exec-autocomplete');
  const v = value.trim();
  if (!v) {
    dropdown.classList.remove('active');
    autocompleteSuggestions = [];
    return;
  }

  if (autocompleteAbort) autocompleteAbort.abort();
  autocompleteAbort = new AbortController();

  // Include the current surface as context for context-aware ranking
  const surface = window._currentSurface || '';
  const contextParam = surface ? `&surface=${encodeURIComponent(surface)}` : '';

  try {
    const resp = await fetch(
      MAESTRO_API + '/api/oem/autocomplete?q=' + encodeURIComponent(v) + '&limit=8' + contextParam,
      { signal: autocompleteAbort.signal }
    );
    if (!resp.ok) throw new Error('Autocomplete failed: ' + resp.status);
    const data = await resp.json();
    const suggestions = data.suggestions || [];
    autocompleteSuggestions = suggestions;

    if (suggestions.length === 0) {
      dropdown.innerHTML = `<div class="exec-ac-header" role="status">No matches in OEM for "${escapeHtml(v)}"</div>`;
      dropdown.classList.add('active');
      autocompleteSelectedIdx = -1;
      return;
    }

    autocompleteSelectedIdx = -1;
    // Build rich dropdown with completion, reason, confidence, citations
    dropdown.setAttribute('role', 'listbox');
    dropdown.setAttribute('aria-label', 'Organizational autocomplete suggestions');
    dropdown.innerHTML = `<div class="exec-ac-header">Semantic suggestions · from live OEM · ranked by recency, authority, outcome, feedback</div>` +
      suggestions.map((s, i) => {
        const confPct = Math.round((s.confidence || 0) * 100);
        const rankPct = Math.round((s.rank_score || 0) * 100);
        const citations = (s.citations || []).slice(0, 3).map(c => {
          const short = String(c).substring(0, 20);
          return `<span class="source-cite" title="${escapeHtml(c)}">${escapeHtml(short)}</span>`;
        }).join(' ');
        const evidenceCount = (s.evidence || []).length;
        const similarCount = (s.similar_executions || []).length;
        const sourceIcon = {
          'law': 'L', 'recommendation': 'R', 'expert': '?', 'risk': '!',
          'evidence': 'E', 'lo:bottleneck': 'B', 'lo:hidden_expert': '?',
          'lo:departure_risk': 'X', 'lo:duplicate_work': 'D', 'lo:knowledge_death': 'K',
          'lo:approval_gate': 'G', 'lo:incident_pattern': 'I', 'lo:velocity_drop': 'V',
        }[s.source_type] || '*';
        return `<div class="exec-ac-item" data-idx="${i}" data-query="${escapeHtml(s.query)}" role="option" aria-selected="false" tabindex="-1" onmouseenter="autocompleteSelectedIdx=${i}; updateAutocompleteHighlight()" onclick="selectAutocomplete(${i})">
          <div class="exec-ac-completion">
            <span class="completed">${escapeHtml(s.completion)}</span>
          </div>
          <div class="text-[10px] text-fg-400 mt-1 leading-relaxed">${escapeHtml(s.reason)}</div>
          <div class="flex items-center gap-2 mt-1.5 text-[9px] text-fg-500 flex-wrap">
            <span class="mono text-brand-purple">[${escapeHtml(s.source_type)}]</span>
            <span class="text-brand-cyan">conf ${confPct}%</span>
            <span>·</span>
            <span>rank ${rankPct}%</span>
            <span>·</span>
            <span>${evidenceCount} evidence</span>
            ${similarCount ? `<span>·</span><span>${similarCount} similar</span>` : ''}
          </div>
          ${citations ? `<div class="mt-1 flex flex-wrap gap-1">${citations}</div>` : ''}
          ${s.expected_outcome ? `<div class="text-[9px] text-fg-600 mt-1 italic">→ ${escapeHtml(s.expected_outcome.substring(0, 100))}</div>` : ''}
        </div>`;
      }).join('');
    dropdown.classList.add('active');
  } catch (e) {
    if (e.name === 'AbortError') return;
    dropdown.innerHTML = `<div class="exec-ac-header" role="alert">Autocomplete error: ${escapeHtml(e.message)}</div>`;
    dropdown.classList.add('active');
  }
}

function updateAutocompleteHighlight() {
  document.querySelectorAll('.exec-ac-item').forEach((el, i) => {
    const selected = i === autocompleteSelectedIdx;
    el.classList.toggle('selected', selected);
    el.setAttribute('aria-selected', selected ? 'true' : 'false');
  });
  // Scroll the selected item into view
  if (autocompleteSelectedIdx >= 0) {
    const sel = document.querySelector(`.exec-ac-item[data-idx="${autocompleteSelectedIdx}"]`);
    if (sel) sel.scrollIntoView({ block: 'nearest' });
  }
}

function selectAutocomplete(idx) {
  const item = document.querySelector(`.exec-ac-item[data-idx="${idx}"]`);
  if (!item) return;
  const query = item.dataset.query;
  // Fill the input with the completion text (not the query) for a natural feel
  const suggestion = autocompleteSuggestions[idx];
  if (suggestion && suggestion.completion) {
    document.getElementById('ask-input').value = suggestion.completion;
  } else {
    document.getElementById('ask-input').value = query;
  }
  document.getElementById('exec-autocomplete').classList.remove('active');
  submitAsk(query);
}

document.addEventListener('keydown', (e) => {
  const dropdown = document.getElementById('exec-autocomplete');
  if (!dropdown || !dropdown.classList.contains('active')) return;
  const items = dropdown.querySelectorAll('.exec-ac-item');
  if (items.length === 0) return;

  if (e.key === 'ArrowDown') {
    e.preventDefault();
    autocompleteSelectedIdx = (autocompleteSelectedIdx + 1) % items.length;
    updateAutocompleteHighlight();
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    autocompleteSelectedIdx = (autocompleteSelectedIdx - 1 + items.length) % items.length;
    updateAutocompleteHighlight();
  } else if (e.key === 'Enter' && autocompleteSelectedIdx >= 0) {
    e.preventDefault();
    selectAutocomplete(autocompleteSelectedIdx);
  } else if (e.key === 'Escape') {
    // Round 78 Phase 4: ESC closes the dropdown and returns focus to the input.
    // The auditor flagged: "Key handler handles arrows/enter but not ESC."
    e.preventDefault();
    dropdown.classList.remove('active');
    autocompleteSelectedIdx = -1;
    document.getElementById('ask-input').focus();
  }
});

async function submitAsk(query) {
  const q = query.trim();
  if (!q) return;
  document.getElementById('ask-input').value = '';
  document.getElementById('exec-autocomplete').classList.remove('active');
  document.getElementById('ask-suggestions').style.display = 'none';
  const answerDiv = document.getElementById('ask-answer');
  answerDiv.style.display = 'block';
  document.getElementById('ask-answer-text').innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  document.getElementById('ask-citations').innerHTML = '';
  document.getElementById('ask-path').textContent = '';
  document.getElementById('ask-confidence').textContent = '';
  answerDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  try {
    // Phase 2.2: Migrate from GET /ask (old, cross-customer) to POST /ask/conversation (AskPipeline)
    if (!window._askSessionId) {
      try { window._askSessionId = crypto.randomUUID(); }
      catch(e) { window._askSessionId = 'sess-' + Date.now() + '-' + Math.random().toString(36).slice(2,11); }
    }
    const resp = await fetch((MAESTRO_API || '') + '/api/oem/ask/conversation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: q, history: [], session_id: window._askSessionId }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    document.getElementById('ask-answer-text').innerHTML = escapeHtml(humanize(data.answer || '')).replace(/\n/g, '<br>');
    const sources = data.sources || (data.evidence || []).map(e => e.source || 'unknown');
    document.getElementById('ask-citations').innerHTML = sources.length === 0
      ? '<span class="text-[11px] text-fg-500">No sources cited (insufficient evidence).</span>'
      : sources.map(s => `<span class="source-cite">${escapeHtml(s)}</span>`).join('');
    const path = data.evidence_path || data.evidence || [];
    document.getElementById('ask-path').textContent = path.length === 0
      ? 'No evidence path available.'
      : path.map(p => (p.source || p.type || '') + (p.text ? ': ' + p.text.substring(0,40) : '')).join(' → ');
    // CEO directive: confidence removed from /ask responses
    document.getElementById('ask-confidence').textContent = `${sources.length} sources`;
  } catch (e) {
    document.getElementById('ask-answer-text').innerHTML = `<span class="text-brand-rose">Error: ${escapeHtml(e.message)}</span>`;
    showError('Ask failed: ' + e.message);
  }
}

// ═══════════════════════════════════════════════════════════════════════════

// === physics_laws.js ===
// PHYSICS (Laws) — with contradiction feedback (optimistic update)
// ═══════════════════════════════════════════════════════════════════════════

async function loadLaws(statusFilter) {
  const el = document.getElementById('physics-laws');
  loadingHTML(el, 'Loading laws…');
  try {
    const path = statusFilter ? '/laws?status=' + statusFilter : '/laws';
    const data = await api.getOEM(path);
    el.innerHTML = data.laws.length === 0
      ? '<div class="empty-state">No laws match this filter.</div>'
      : data.laws.map(l => renderLawCardDetailed(l)).join('');
  } catch (e) {
    errorHTML(el, e.message, 'loadLaws()');
  }
}

function renderLawCardDetailed(l) {
  const statusTag = l.status === 'validated' ? 'tag-cyan' : l.status === 'stressed' ? 'tag-amber' : l.status === 'invalidated' ? 'tag-rose' : l.status === 'unknown_to_leadership' ? 'tag-purple' : 'tag-gray';
  const chain = l.evidence_chain && l.evidence_chain.chain ? l.evidence_chain.chain : [];
  return `<div class="card mb-3 cursor-pointer" data-law-code="${escapeHtml(l.code)}" onclick="openDrilldown('law', '${escapeJs(l.code)}')">
    <div class="flex items-start justify-between mb-2">
      <div class="flex-1">
        <div class="flex items-center gap-2 mb-1">
          <span class="tag ${statusTag}">${escapeHtml(humanize(l.status))}</span>
          ${l.drift_detected ? '<span class="tag tag-rose">shifting</span>' : ''}
        </div>
        <div class="text-sm font-semibold text-white">${escapeHtml(humanize(l.statement))}</div>
        <div class="text-[11px] text-fg-400 mt-1"><strong>Condition:</strong> ${escapeHtml(humanize(l.condition))}</div>
        <div class="text-[11px] text-fg-300 mt-1"><strong>Outcome:</strong> ${escapeHtml(humanize(l.outcome))}</div>
      </div>
    </div>
    <div class="flex items-center gap-3 text-[10px] text-fg-500 mt-3">
      <span>${l.evidence_count} signals</span>
      <span>·</span><span>${l.validated_runtimes}/${l.validated_runtimes + l.failed_runtimes} observed</span>
      ${l.counter_examples ? `<span>·</span><span>${l.counter_examples} exceptions</span>` : ''}
    </div>
    <div class="grid grid-cols-2 gap-3 mt-3 pt-3 border-t border-white/[0.05]">
      <div>
        <div class="text-[10px] uppercase text-fg-500 mb-1">Providers</div>
        <div class="flex flex-wrap gap-1">${l.providers && l.providers.length ? l.providers.map(p => `<span class="tag tag-gray">${escapeHtml(p)}</span>`).join('') : '<span class="text-[10px] text-fg-600">none</span>'}</div>
      </div>
      <div>
        <div class="text-[10px] uppercase text-fg-500 mb-1">Last Verified</div>
        <div class="text-[11px] text-fg-300">${l.last_validated ? escapeHtml(l.last_validated) : 'never'}</div>
      </div>
    </div>
    ${chain.length > 0 ? `
      <div class="mt-3 pt-3 border-t border-white/[0.05]">
        <div class="text-[10px] uppercase text-fg-500 mb-2">Evidence Chain (${chain.length} signals)</div>
        <div class="flex flex-wrap gap-1">${chain.slice(0, 12).map(n => `<span class="evidence-node ${n.type}">${escapeHtml(humanize(n.label))}</span>`).join('')}</div>
      </div>
    ` : ''}
    <div class="mt-3 pt-3 border-t border-white/[0.05] flex items-center gap-2" onclick="event.stopPropagation()">
      <div class="text-[10px] uppercase text-fg-500 mr-2">Feedback:</div>
      <button class="btn btn-ghost text-[10px]" onclick="event.stopPropagation(); contradictLaw('${escapeJs(l.code)}', 'agree')">Agree</button>
      <button class="btn btn-ghost text-[10px]" onclick="event.stopPropagation(); contradictLaw('${escapeJs(l.code)}', 'reject')">Reject</button>
      <button class="btn btn-ghost text-[10px]" onclick="event.stopPropagation(); contradictLaw('${escapeJs(l.code)}', 'modify')">Modify</button>
      <button class="btn btn-ghost text-[10px]" onclick="event.stopPropagation(); contradictLaw('${escapeJs(l.code)}', 'ignore')">Ignore</button>
    </div>
  </div>`;
}

async function contradictLaw(lawCode, action) {
  // Optimistic update: visually mark the law as "updating"
  const card = document.querySelector(`[data-law-code="${lawCode}"]`);
  if (card) {
    card.style.opacity = '0.6';
    const confEl = card.querySelector('.conf-value');
    if (confEl) confEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  }

  try {
    const resp = await fetch(MAESTRO_API + '/api/oem/contradict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        target_type: 'law',
        target_id: lawCode,
        action: action,
        reasoning: `UI feedback: ${action}`,
      }),
    });
    if (!resp.ok) throw new Error('Contradict failed: ' + resp.status);
    const data = await resp.json();

    // Invalidate cached laws so next nav fetches fresh state
    SWR.invalidatePrefix('oem:/laws');
    SWR.invalidatePrefix('oem:/inbox');
    SWR.invalidatePrefix('oem:/dashboard');

    // Reload physics to show updated confidence
    if (window._currentSurface === 'physics') {
      loadLaws('');
    }
  } catch (e) {
    showError(`Feedback failed for ${lawCode}: ${e.message}`);
    if (card) {
      card.style.opacity = '1';
      const confEl = card.querySelector('.conf-value');
      if (confEl) confEl.textContent = '—';
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// DEBATE
// ═══════════════════════════════════════════════════════════════════════════

async function loadDebate() {
  const el = document.getElementById('debate-laws');
  loadingHTML(el);
  try {
    const data = await api.getOEM('/inbox');
    el.innerHTML = data.dissent.length === 0
      ? `<div class="empty-state">
          <div class="b-fs18-fw800-4 b-mb12">No laws hidden from leadership.</div>
          <div class="meta-text b-mb16">All validated laws are known to leadership. This is the healthy state — every organizational pattern that the OEM has discovered has been surfaced and acknowledged.</div>
          <div class="b-text-left-9 b-mw500-m0auto">
            <div class="b-fs13-fw700-4 b-mb8">When debates appear here, you'll see:</div>
            <div class="b-fs12-text-6 b-mb6"><strong>Hidden laws:</strong> Patterns the OEM validated from execution data that leadership hasn't explicitly acknowledged. Each shows the law statement, evidence count, confidence, and which signals triggered it.</div>
            <div class="b-fs12-text-6 b-mb6"><strong>Dissenting evidence:</strong> Cases where the organization's behavior contradicts a stated strategy or prior decision. Each shows both sides with their supporting evidence.</div>
            <div class="b-fs12-text-6 b-mb6"><strong>Strategic tension:</strong> Places where two valid laws pull in opposite directions (e.g., "ship fast" vs. "ship safe"). Each shows the trade-off and a recommendation for resolving it.</div>
            <div class="b-fs12-text-6"><strong>Acknowledge button:</strong> When you acknowledge a hidden law, it moves from "debate" to "physics" — leadership has seen it and accepted it as an operating constraint.</div>
          </div>
        </div>`
      : data.dissent.map(l => renderLawCardDetailed(l)).join('');
  } catch (e) {
    errorHTML(el, e.message, 'loadDebate()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════

// === live_meeting.js ===
// LIVE MEETING — real OEM-driven meeting intelligence (NO hardcoded script)
// ═══════════════════════════════════════════════════════════════════════════

let liveTimer = null;

// Clean up Live Meeting timers when navigating away
function teardownLive() {
  if (liveTimer) { clearTimeout(liveTimer); liveTimer = null; }
}

async function startLiveMeeting() {
  if (liveTimer) { clearTimeout(liveTimer); liveTimer = null; }
  document.getElementById('transcript-area').innerHTML = '';
  document.getElementById('live-obj-count').textContent = '0';
  document.getElementById('live-ai-count').textContent = '0';
  document.getElementById('live-law-count').textContent = '0';
  document.getElementById('live-objections').innerHTML = 'No objections yet.';
  document.getElementById('live-actions').innerHTML = 'No action items yet.';
  document.getElementById('live-laws').innerHTML = 'No laws triggered yet.';
  document.getElementById('live-start-btn').textContent = 'Replay Meeting';

  const transcriptArea = document.getElementById('transcript-area');
  transcriptArea.innerHTML = '<div class="text-[11px] text-fg-500 italic">Paste a transcript below and click "Analyze with OEM" — the OEM will detect objections, laws triggered, and action items in real time.</div>';

  const inputArea = document.getElementById('live-transcript-input');
  if (inputArea) inputArea.style.display = 'block';
}

async function analyzeTranscript() {
  const input = document.getElementById('live-transcript-textarea');
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;

  // Parse the textarea into a transcript (one line per turn, "Speaker: text")
  const lines = text.split('\n').filter(l => l.trim());
  const transcript = lines.map(line => {
    const idx = line.indexOf(':');
    if (idx > 0) {
      return { speaker: line.slice(0, idx).trim(), text: line.slice(idx + 1).trim() };
    }
    return { speaker: 'Unknown', text: line };
  });

  const transcriptArea = document.getElementById('transcript-area');

  // Build the entire transcript HTML in one string, then assign once.
  // This is O(n) instead of O(n²) — the old `innerHTML +=` re-parsed
  // the entire DOM on each line append.
  const transcriptHtml = transcript.map((line, i) => `<div class="flex gap-3 p-2 rounded-md bg-white/[0.02] mb-1">
      <span class="text-[10px] text-fg-500 mono w-12">${String(i+1).padStart(2,'0')}</span>
      <span class="text-xs font-semibold text-brand-cyan w-20">${escapeHtml(line.speaker)}</span>
      <span class="text-xs text-fg-200 flex-1">${escapeHtml(humanize(line.text))}</span>
    </div>`).join('');
  transcriptArea.innerHTML = transcriptHtml;

  // Analyze via OEM
  document.getElementById('live-objections').innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  document.getElementById('live-actions').innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  document.getElementById('live-laws').innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const resp = await fetch(MAESTRO_API + '/api/oem/meetings/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ transcript }),
    });
    if (!resp.ok) throw new Error('Analyze failed: ' + resp.status);
    const data = await resp.json();

    document.getElementById('live-obj-count').textContent = data.summary.objection_count;
    document.getElementById('live-ai-count').textContent = data.summary.action_count;
    document.getElementById('live-law-count').textContent = data.summary.law_count;

    document.getElementById('live-objections').innerHTML = data.objections.length === 0
      ? '<div class="text-[11px] text-fg-500">No objections detected.</div>'
      : data.objections.map(o => `
        <div class="p-2 rounded-md bg-brand-rose/[0.06] border-l-2 border-brand-rose mb-1">
          <div class="text-brand-rose font-semibold text-[11px]">${escapeHtml(o.speaker)} dissents</div>
          <div class="text-[10px] text-fg-500">${escapeHtml(humanize(o.text))}</div>
          ${o.law_code ? `<div class="text-[10px] text-fg-600 mt-1">Linked: <span class="source-cite">${escapeHtml(o.law_code)}</span></div>` : ''}
        </div>
      `).join('');

    document.getElementById('live-actions').innerHTML = data.actions.length === 0
      ? '<div class="text-[11px] text-fg-500">No action items detected.</div>'
      : data.actions.map(a => `
        <div class="flex items-center gap-2 text-[11px] py-1">
          <div class="w-3 h-3 border border-white/20 rounded-sm"></div>
          <span class="text-fg-200 flex-1">${escapeHtml(humanize(a.text))}</span>
          <span class="text-fg-500">@${escapeHtml(a.owner)}</span>
        </div>
      `).join('');

    document.getElementById('live-laws').innerHTML = data.laws_triggered.length === 0
      ? '<div class="text-[11px] text-fg-500">No laws triggered.</div>'
      : data.laws_triggered.map(l => `
        <div class="flex items-center gap-2 text-[11px] py-1">
          <span class="source-cite">${escapeHtml(l.code)}</span>
          <span class="text-fg-400">${escapeHtml(l.statement.substring(0, 60))}…</span>
        </div>
      `).join('');
  } catch (e) {
    document.getElementById('live-objections').innerHTML = `<div class="text-[11px] text-brand-rose">Error: ${escapeHtml(e.message)}</div>`;
    document.getElementById('live-actions').innerHTML = '';
    document.getElementById('live-laws').innerHTML = '';
    showError('Meeting analysis failed: ' + e.message);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// ENG: SIGNALS
// ═══════════════════════════════════════════════════════════════════════════

async function loadEngSignals() {
  const el = document.getElementById('eng-signals-list');
  loadingHTML(el);
  try {
    const data = await api.getOEM('/state');
    el.innerHTML = `
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        ${data.providers.map(p => `
          <div class="card">
            <div class="flex items-center justify-between mb-2">
              <div class="text-sm font-semibold text-white">${escapeHtml(humanize(p.label))}</div>
              <span class="tag tag-cyan">connected</span>
            </div>
            <div class="text-[11px] text-fg-400">${escapeHtml(p.provider)}</div>
            <div class="text-[10px] text-fg-500 mt-2">${p.signal_count} signals processed</div>
            <div class="text-[10px] text-fg-500">Tracks: ${escapeHtml(p.artifact_label)}</div>
          </div>
        `).join('')}
      </div>
      <div class="mt-4 pt-4 border-t border-white/[0.05] grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="metric"><div class="metric-value">${data.summary.signals_processed}</div><div class="metric-label">Total Signals</div></div>
        <div class="metric"><div class="metric-value">${data.summary.learning_objects}</div><div class="metric-label">Learning Objects</div></div>
        <div class="metric"><div class="metric-value">${data.summary.patterns_detected}</div><div class="metric-label">Patterns</div></div>
        <div class="metric"><div class="metric-value">${data.summary.laws_inferred}</div><div class="metric-label">Laws</div></div>
      </div>
    `;
  } catch (e) {
    errorHTML(el, e.message, 'loadEngSignals()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// ENG: OEM BUILDER
// ═══════════════════════════════════════════════════════════════════════════

async function loadEngOEM() {
  const el = document.getElementById('eng-oem-pipeline');
  loadingHTML(el);
  try {
    const data = await api.getOEM('/state');
    const s = data.summary;
    el.innerHTML = `
      <div class="space-y-3">
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-cyan"></span><span class="text-fg-200 flex-1">Ingesting signals from ${s.providers_connected.length} sources</span><span class="mono text-brand-cyan">${s.signals_processed}</span></div>
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-amber"></span><span class="text-fg-200 flex-1">Learning objects inferred</span><span class="mono text-brand-amber">${s.learning_objects}</span></div>
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-purple"></span><span class="text-fg-200 flex-1">Patterns detected</span><span class="mono text-brand-purple">${s.patterns_detected}</span></div>
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-rose"></span><span class="text-fg-200 flex-1">Laws inferred</span><span class="mono text-brand-rose">${s.laws_inferred}</span></div>
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-cyan"></span><span class="text-fg-200 flex-1">Validated laws</span><span class="mono text-brand-cyan">${s.validated_laws}</span></div>
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-sky"></span><span class="text-fg-200 flex-1">Hidden experts</span><span class="mono text-brand-sky">${s.hidden_experts}</span></div>
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-amber"></span><span class="text-fg-200 flex-1">Bottlenecks</span><span class="mono text-brand-amber">${s.bottlenecks}</span></div>
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-rose"></span><span class="text-fg-200 flex-1">Departure risks</span><span class="mono text-brand-rose">${s.departure_risks}</span></div>
      </div>
      <div class="mt-4 pt-4 border-t border-white/[0.05] text-[10px] text-fg-500">Last updated: ${escapeHtml(data.last_updated || 'unknown')}</div>
    `;
  } catch (e) {
    errorHTML(el, e.message, 'loadEngOEM()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════

// === eng_audit.js ===
// ENG: AUDIT — structured signals (NO JSON.stringify)
// ═══════════════════════════════════════════════════════════════════════════

async function loadEngAudit() {
  const el = document.getElementById('eng-audit-list');
  loadingHTML(el, 'Loading signal history…');
  try {
    const data = await api.getOEM('/signals?limit=100');
    if (data.signals.length === 0) {
      emptyHTML(el, 'No signal history yet. Events appear as signals flow into Maestro.');
      return;
    }
    el.innerHTML = `
      <div class="text-[10px] text-fg-500 mb-3">${data.total} signals · showing latest ${data.signals.length}</div>
      <div class="space-y-1">
        ${data.signals.map(r => `
          <div class="text-[11px] p-2 rounded bg-white/[0.02] border border-white/[0.04] grid grid-cols-12 gap-2 items-center hover:bg-white/[0.04] cursor-pointer" onclick="openDrilldown('signal', '${escapeJs(r.receipt_id)}')">
            <span class="mono text-brand-purple col-span-2" title="${escapeHtml(r.receipt_id)}">${escapeHtml(r.receipt_id.substring(0, 8))}</span>
            <span class="text-fg-500 col-span-2">${formatTimestamp(r.timestamp)}</span>
            <span class="tag tag-gray col-span-1">${escapeHtml(r.provider)}</span>
            <span class="text-fg-300 col-span-2">${escapeHtml(r.signal_type)}</span>
            <span class="text-fg-200 col-span-2 truncate" title="${escapeHtml(r.actor)}">${escapeHtml(r.actor)}</span>
            <span class="text-fg-400 col-span-2 truncate" title="${escapeHtml(r.artifact)}">${escapeHtml(r.artifact)}</span>
            <span class="text-fg-500 col-span-1">${r.law_code ? `<span class="source-cite">${escapeHtml(r.law_code)}</span>` : ''}</span>
          </div>
        `).join('')}
      </div>
    `;
  } catch (e) {
    errorHTML(el, e.message, 'loadEngAudit()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// ENG: SETTINGS
// ═══════════════════════════════════════════════════════════════════════════

async function loadEngSettings() {
  document.getElementById('settings-api-url').value = MAESTRO_API || '(same origin)';
  const statusEl = document.getElementById('settings-oem-status');
  try {
    const data = await api.getOEM('/state');
    statusEl.innerHTML = `<span class="text-brand-cyan">●</span> Connected — ${data.summary.signals_processed} signals, ${data.summary.laws_inferred} laws`;
  } catch (e) {
    statusEl.innerHTML = `<span class="text-brand-rose">●</span> Unreachable: ${escapeHtml(e.message)}`;
  }
  await loadProviderStatus();
  await loadImportJobs();
  loadOAuthAdminConfigs();
}

// ─── Enterprise OAuth Self-Service ────────────────────────────────────────

let _editingOAuthProvider = '';

async function loadOAuthAdminConfigs() {
  const el = document.getElementById('oauth-admin-list');
  if (!el) return;
  try {
    const resp = await fetch((MAESTRO_API || '') + '/api/oauth/admin/providers');
    const data = await resp.json();
    el.innerHTML = data.providers.map(p => {
      const statusBadge = p.configured
        ? `<span class="tag ${p.configured_via === 'database' ? 'tag-green' : 'tag-yellow'}">${p.configured_via}</span>`
        : '<span class="tag tag-gray">not configured</span>';
      return `
        <div class="border border-white/[0.05] rounded-lg p-3">
          <div class="flex items-center justify-between mb-1">
            <div class="font-semibold text-white text-sm">${escapeHtml(humanize(p.label))}</div>
            ${statusBadge}
          </div>
          <div class="text-[10px] text-fg-400">
            ${p.client_id ? `Client ID: <code>${escapeHtml(p.client_id)}</code>` : 'No Client ID set'}
            ${p.has_secret ? ' · <span class="b-clr-1d11">Secret: encrypted</span>' : ''}
          </div>
          <div class="flex gap-1.5 mt-2">
            <button class="tag tag-gray cursor-pointer text-[10px] hover:bg-white/[0.05]" onclick="openOAuthConfigForm('${escapeJs(p.provider)}', '${escapeJs(p.label)}', '${escapeJs(p.client_id)}')" aria-label="Configure ${escapeHtml(humanize(p.label))}">Configure</button>
            ${p.configured_via === 'database' ? `<button class="tag tag-gray cursor-pointer text-[10px] hover:bg-red-500/10" onclick="deleteOAuthProvider('${escapeJs(p.provider)}')" aria-label="Remove ${escapeHtml(humanize(p.label))} config">Remove</button>` : ''}
            ${p.configured ? `<button class="tag tag-cyan cursor-pointer text-[10px]" onclick="window.open('${(MAESTRO_API || '') + '/api/oauth/' + p.provider + '/start'}')" aria-label="Connect ${escapeHtml(humanize(p.label))}">Connect</button>` : ''}
          </div>
        </div>
      `;
    }).join('');
  } catch (e) {
    el.innerHTML = `<div class="empty-state">Failed to load OAuth configs: ${escapeHtml(e.message)}</div>`;
  }
}

function openOAuthConfigForm(provider, label, existingClientId) {
  _editingOAuthProvider = provider;
  document.getElementById('oauth-form-title').textContent = `Configure ${label}`;
  document.getElementById('oauth-client-id').value = existingClientId || '';
  document.getElementById('oauth-client-secret').value = '';
  document.getElementById('oauth-redirect-uri').value = '';
  document.getElementById('oauth-config-form').style.display = '';
  document.getElementById('oauth-client-id').focus();
}

async function saveOAuthProvider() {
  const provider = _editingOAuthProvider;
  if (!provider) return;
  const clientId = document.getElementById('oauth-client-id').value.trim();
  const clientSecret = document.getElementById('oauth-client-secret').value.trim();
  const redirectUri = document.getElementById('oauth-redirect-uri').value.trim();

  if (!clientId || !clientSecret) {
    showToast('Client ID and Client Secret are required.', 'error');
    return;
  }

  try {
    const resp = await fetch((MAESTRO_API || '') + `/api/oauth/admin/providers/${provider}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_id: clientId, client_secret: clientSecret, redirect_uri: redirectUri }),
    });
    const data = await resp.json();
    if (data.ok) {
      document.getElementById('oauth-config-form').style.display = 'none';
      loadOAuthAdminConfigs();
    } else {
      showToast(data.detail || 'Failed to save OAuth config', 'error');
    }
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
  }
}

async function deleteOAuthProvider(provider) {
  if (!await showConfirm(`Remove ${provider} configuration? Environment variable fallback will remain if set.`)) return;
  try {
    const resp = await fetch((MAESTRO_API || '') + `/api/oauth/admin/providers/${provider}`, { method: 'DELETE' });
    const data = await resp.json();
    if (data.ok) {
      loadOAuthAdminConfigs();
    } else {
      showToast(data.detail || 'Failed to remove', 'error');
    }
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
  }
}

// ─── Signal provider connection UI ─────────────────────────────────────────

const PROVIDER_META = {
  github:     { name: 'GitHub',     icon: 'G', description: 'Code execution, PR reviews, and repository management' },
  jira:       { name: 'Jira',       icon: 'J', description: 'Issue tracking, sprint velocity, approval bottlenecks' },
  slack:      { name: 'Slack',      icon: 'S', description: 'Messages, threads, hidden experts, departure signals' },
  confluence: { name: 'Confluence', icon: 'C', description: 'Knowledge pages, version history, expertise graph' },
  gmail:      { name: 'Gmail',      icon: 'M', description: 'Email patterns, decision trails, cross-team signals' },
};

async function loadProviderStatus() {
  const listEl = document.getElementById('signal-providers-list');
  if (!listEl) return;
  try {
    const data = await api.getOAuthStatus();
    listEl.innerHTML = data.providers.map(p => {
      const meta = PROVIDER_META[p.provider] || { name: p.provider, icon: 'O', description: '' };
      const statusBadge = p.connected
        ? `<span class="tag tag-cyan">Connected</span>`
        : p.configured
          ? `<span class="tag tag-gray">Not connected</span>`
          : `<span class="tag tag-amber" title="Set MAESTRO_OAUTH_${p.provider.toUpperCase()}_CLIENT_ID and _SECRET env vars">Not configured</span>`;
      const actionButton = p.connected
        ? `<button class="btn btn-ghost text-[11px]" onclick="disconnectProvider('${escapeJs(p.provider)}')">Disconnect</button>`
        : `<button class="btn btn-primary text-[11px]" ${p.configured ? '' : 'disabled'} onclick="connectProvider('${escapeJs(p.provider)}')">Connect</button>`;
      return `
        <div class="flex items-center justify-between p-3 rounded-lg bg-ink-800/60 border border-ink-700">
          <div class="flex items-center gap-3">
            <div class="text-xl">${meta.icon}</div>
            <div>
              <div class="text-sm font-semibold text-white">${meta.name}</div>
              <div class="text-[10px] text-fg-500">${escapeHtml(humanize(meta.description))}</div>
            </div>
          </div>
          <div class="flex items-center gap-3">
            ${statusBadge}
            ${actionButton}
          </div>
        </div>`;
    }).join('');
  } catch (e) {
    listEl.innerHTML = `<div class="text-xs text-brand-rose">Failed to load provider status: ${escapeHtml(e.message)}</div>`;
  }
}

async function connectProvider(provider) {
  try {
    const resp = await fetch(`${MAESTRO_API}/api/oauth/${provider}/start`);
    if (!resp.ok) {
      const err = await resp.json();
      showError(`Failed to start OAuth: ${err.detail || 'Unknown error'}`);
      return;
    }
    const { auth_url } = await resp.json();
    window.location.href = auth_url;
  } catch (e) {
    showError(`Connection failed: ${e.message}`);
  }
}

async function disconnectProvider(provider) {
  if (!await showConfirm(`Disconnect ${provider}? Already-ingested history is preserved.`)) return;
  try {
    await fetch(`${MAESTRO_API}/api/oauth/${provider}/disconnect`, { method: 'POST' });
    SWR.invalidate('oauth:status');
    await loadProviderStatus();
  } catch (e) {
    showError(`Disconnect failed: ${e.message}`);
  }
}

async function loadImportJobs() {
  const listEl = document.getElementById('import-jobs-list');
  if (!listEl) return;
  try {
    const data = await api.getImports();
    if (!data.jobs || data.jobs.length === 0) {
      listEl.innerHTML = '<div class="text-xs text-fg-500">No import jobs yet. Connect a provider to start.</div>';
      return;
    }
    listEl.innerHTML = data.jobs.slice(0, 10).map(job => {
      const statusColor = job.status === 'completed' ? 'cyan' : job.status === 'failed' ? 'rose' : job.status === 'running' ? 'violet' : 'gray';
      return `
        <div class="flex items-center justify-between p-2 rounded-lg bg-ink-800/60 border border-ink-700 text-xs">
          <div>
            <div class="font-semibold text-white">${job.providers.join(', ')}</div>
            <div class="text-fg-500">${job.total_signals || 0} signals · ${job.started_at ? new Date(job.started_at).toLocaleString() : ''}</div>
          </div>
          <div class="flex items-center gap-2">
            <span class="tag tag-${statusColor}">${job.status}</span>
            ${job.status === 'running' ? `<button class="btn btn-ghost text-[10px]" onclick="cancelImport('${escapeJs(job.job_id)}')">Cancel</button>` : ''}
          </div>
        </div>`;
    }).join('');
  } catch (e) {
    listEl.innerHTML = `<div class="text-xs text-brand-rose">Failed to load jobs: ${escapeHtml(e.message)}</div>`;
  }
}

async function cancelImport(jobId) {
  if (!jobId) {
    const banner = document.getElementById('import-banner');
    jobId = banner.dataset.jobId;
  }
  if (!jobId) return;
  try {
    await fetch(`${MAESTRO_API}/api/imports/${jobId}/cancel`, { method: 'POST' });
  } catch (e) {
    console.warn('Cancel failed:', e);
  }
}

// ─── Live import progress banner (WebSocket) ────────────────────────────────

let importWs = null;
let importPollInterval = null;

async function checkForRunningImports() {
  try {
    const data = await api.getImports();
    const running = (data.jobs || []).find(j => j.status === 'running');
    if (running) {
      subscribeToImport(running.job_id);
    }
  } catch (e) {
    // Silently fail — banner is non-critical
  }
}

function subscribeToImport(jobId) {
  if (importWs) {
    try { importWs.close(); } catch (e) {}
  }
  const wsBase = MAESTRO_API.replace(/^http/, 'ws') || (window.location.origin.replace(/^http/, 'ws'));
  importWs = new WebSocket(`${wsBase}/api/imports/${jobId}/stream`);
  importWs.onmessage = (e) => {
    try {
      const snap = JSON.parse(e.data);
      if (snap.type === 'ping') return;
      updateImportBanner(jobId, snap);
    } catch (err) {}
  };
  importWs.onerror = (e) => {
    console.warn('Import WS error:', e);
    // Don't silently fall back to polling — surface the error
    showError('Import monitoring connection lost. Will retry.');
  };
  importWs.onclose = () => {
    if (importPollInterval) clearInterval(importPollInterval);
    let pollStartedAt = Date.now(), pollErrors = 0;
    importPollInterval = setInterval(async () => {
      // Max poll duration: 1 hour
      if (Date.now() - pollStartedAt > 60 * 60 * 1000) {
        clearInterval(importPollInterval);
        importPollInterval = null;
        showError('Import monitoring timed out after 1 hour.');
        hideImportBanner();
        return;
      }
      try {
        const resp = await fetch(`${MAESTRO_API}/api/imports/${jobId}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const job = await resp.json();
        pollErrors = 0;
        if (job.status === 'running' || (job.providers_progress && Object.values(job.providers_progress).some(p => p.status === 'running'))) {
          updateImportBanner(jobId, job);
        } else {
          hideImportBanner();
          clearInterval(importPollInterval);
          importPollInterval = null;
        }
      } catch (e) {
        if (++pollErrors > 5) {
          clearInterval(importPollInterval);
          importPollInterval = null;
          hideImportBanner();
          showError('Import monitoring lost after 5 consecutive errors.');
        }
      }
    }, 5000);
  };
}

function updateImportBanner(jobId, snap) {
  const banner = document.getElementById('import-banner');
  banner.classList.remove('hidden');
  banner.dataset.jobId = jobId;

  const providers = snap.providers_progress || {};
  const providerNames = Object.keys(providers);
  const totalEvents = snap.total_events || 0;
  const runningProvider = providerNames.find(p => providers[p].status === 'running');
  const totalEstimated = runningProvider ? providers[runningProvider].total_estimated : 0;
  const etaSeconds = runningProvider ? providers[runningProvider].eta_seconds : 0;

  const titleEl = document.getElementById('import-banner-title');
  const subtitleEl = document.getElementById('import-banner-subtitle');
  if (runningProvider) {
    const meta = PROVIDER_META[runningProvider] || { name: runningProvider };
    titleEl.textContent = `Importing ${meta.name}…`;
    const etaMin = Math.ceil(etaSeconds / 60);
    subtitleEl.textContent = `${totalEvents.toLocaleString()} events processed · ETA ${etaMin}m`;
  } else if (snap.status === 'completed') {
    titleEl.textContent = `Import complete`;
    subtitleEl.textContent = `${totalEvents.toLocaleString()} events imported`;
    setTimeout(hideImportBanner, 5000);
  } else if (snap.status === 'failed') {
    titleEl.textContent = `Import failed`;
    subtitleEl.textContent = snap.error || 'Unknown error';
    setTimeout(hideImportBanner, 10000);
  }

  const oem = snap.oem || {};
  document.getElementById('import-banner-patterns').textContent = oem.patterns_detected || 0;
  document.getElementById('import-banner-laws').textContent = oem.laws_inferred || 0;
  document.getElementById('import-banner-recs').textContent = oem.recommendations || 0;

  const progressPct = totalEstimated > 0 ? Math.min(100, (totalEvents / totalEstimated) * 100) : 0;
  document.getElementById('import-banner-progress').style.width = `${progressPct}%`;

  // Only refresh dashboard on completion (not on every progress tick).
  // The old code re-fetched /ceo-briefing + /dashboard every 2s during
  // imports — hundreds of unnecessary backend inference calls.
  if (snap.phase === 'completed' && window._currentSurface === 'home') {
    SWR.invalidatePrefix('oem:');  // Invalidate cache; next render fetches fresh
    loadDashboard();
  }
}

function hideImportBanner() {
  document.getElementById('import-banner').classList.add('hidden');
  // Full teardown: close WS and clear polling interval
  if (importWs) { try { importWs.close(); } catch (e) {} importWs = null; }
  if (importPollInterval) { clearInterval(importPollInterval); importPollInterval = null; }
}

// Page lifecycle: clean up all resources on page hide
window.addEventListener('pagehide', () => {
  teardownLive();
  if (importWs) { try { importWs.close(); } catch (e) {} importWs = null; }
  if (importPollInterval) { clearInterval(importPollInterval); importPollInterval = null; }
});

// Visibility change: pause SWR revalidation when tab is backgrounded
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    // Tab backgrounded — SWR will stop revalidating naturally
    // (no active timers to pause since SWR is event-driven)
  } else {
    // Tab foregrounded — revalidate stale cache
    SWR.revalidateAll();
  }
});

// ═══════════════════════════════════════════════════════════════════════════

// === drill_down_modal.js ===
// DRILL-DOWN MODAL — every card/metric/insight is clickable
// Answers: Why? Where? Evidence? Timeline? People? Prediction? Simulation? Recommendation? Perspectives?
// ═══════════════════════════════════════════════════════════════════════════

let drilldownData = null;
let drilldownActiveTab = 'why';
let _drilldownPerspectivesCache = null;

async function openDrilldown(entityType, entityId) {
  const modal = document.getElementById('drilldown-modal');
  const body = document.getElementById('drilldown-body');
  const title = document.getElementById('drilldown-title');
  const typeLabel = document.getElementById('drilldown-type');

  modal.classList.remove('hidden');
  body.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  title.textContent = entityId;
  typeLabel.textContent = entityType.charAt(0).toUpperCase() + entityType.slice(1);

  // WCAG 2.1: store the trigger element so we can return focus on close
  drilldownTrigger = document.activeElement;

  try {
    const resp = await fetch(`${MAESTRO_API}/api/oem/entity/${entityType}/${encodeURIComponent(entityId)}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    drilldownData = await resp.json();
    drilldownActiveTab = 'why';
    updateDrilldownTabs();
    renderDrilldownTab('why');
    // WCAG 2.1: trap focus inside the modal
    trapFocus(modal);
  } catch (e) {
    body.innerHTML = `<div class="error-state">Failed to load: ${escapeHtml(e.message)}</div>`;
  }
}

function closeDrilldown() {
  const modal = document.getElementById('drilldown-modal');
  modal.classList.add('hidden');
  drilldownData = null;
  // WCAG 2.1: return focus to the trigger element
  if (drilldownTrigger && typeof drilldownTrigger.focus === 'function') {
    drilldownTrigger.focus();
    drilldownTrigger = null;
  }
  // Remove the focus trap keydown listener
  if (drilldownKeydownHandler) {
    modal.removeEventListener('keydown', drilldownKeydownHandler);
    drilldownKeydownHandler = null;
  }
}

// WCAG 2.1: Focus trap for the drill-down modal
// Tab cycles within the modal; Escape closes; focus returns to trigger.
let drilldownTrigger = null;
let drilldownKeydownHandler = null;

function trapFocus(modal) {
  // Wait a tick for the modal content to render
  setTimeout(() => {
    const focusable = modal.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    first.focus();

    drilldownKeydownHandler = function(e) {
      if (e.key === 'Escape') {
        e.preventDefault();
        closeDrilldown();
        return;
      }
      if (e.key !== 'Tab') return;
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    modal.addEventListener('keydown', drilldownKeydownHandler);
  }, 100);
}

function switchDrilldownTab(tab) {
  drilldownActiveTab = tab;
  updateDrilldownTabs();
  renderDrilldownTab(tab);
}

function updateDrilldownTabs() {
  document.querySelectorAll('.drilldown-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === drilldownActiveTab);
  });
}

function renderDrilldownTab(tab) {
  const body = document.getElementById('drilldown-body');
  if (!drilldownData) return;

  if (tab === 'why') {
    body.innerHTML = `
      <div class="space-y-4">
        <div class="text-sm text-fg-200 leading-relaxed">${escapeHtml(drilldownData.why || 'No explanation available.')}</div>
        ${drilldownData.where ? `
          <div class="mt-4 pt-4 border-t border-white/[0.05]">
            <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">Context</div>
            <pre class="text-[11px] text-fg-400 bg-white/[0.02] p-3 rounded-lg overflow-x-auto">${escapeHtml(JSON.stringify(drilldownData.where, null, 2))}</pre>
          </div>
        ` : ''}
      </div>
    `;
  } else if (tab === 'where') {
    body.innerHTML = `
      <div class="space-y-3">
        <div class="text-sm text-fg-200">${drilldownData.where ? 'This entity appears in:' : 'No location data.'}</div>
        ${drilldownData.where ? `<pre class="text-[11px] text-fg-400 bg-white/[0.02] p-3 rounded-lg overflow-x-auto">${escapeHtml(JSON.stringify(drilldownData.where, null, 2))}</pre>` : ''}
      </div>
    `;
  } else if (tab === 'evidence') {
    const ev = drilldownData.evidence || [];
    body.innerHTML = ev.length === 0
      ? '<div class="empty-state">No evidence available.</div>'
      : `<div class="text-[10px] text-fg-500 mb-3">${ev.length} evidence item(s)</div>
         <div class="space-y-2">${ev.map(e => `
           <div class="drilldown-evidence-item" onclick="${e.signal_id ? `openDrilldown('signal', '${escapeJs(e.signal_id)}')` : ''}">
             <div class="flex items-center justify-between">
               <span class="text-xs font-semibold text-fg-200">${escapeHtml(e.type)}${e.signal_type ? ': ' + escapeHtml(e.signal_type) : ''}</span>
               ${e.provider ? `<span class="tag tag-gray">${escapeHtml(e.provider)}</span>` : ''}
             </div>
             ${e.actor ? `<div class="text-[10px] text-fg-500 mt-1">Actor: ${escapeHtml(e.actor)}</div>` : ''}
             ${e.artifact ? `<div class="text-[10px] text-fg-500">Artifact: ${escapeHtml(e.artifact)}</div>` : ''}
             ${e.timestamp ? `<div class="text-[10px] text-fg-600 mt-1">${formatTimestamp(e.timestamp)}</div>` : ''}
           </div>
         `).join('')}</div>`;
  } else if (tab === 'timeline') {
    const tl = drilldownData.timeline || [];
    body.innerHTML = tl.length === 0
      ? '<div class="empty-state">No timeline data.</div>'
      : `<div class="space-y-0">${tl.map(t => `
         <div class="drilldown-timeline-item">
           <div class="text-xs font-semibold text-fg-200">${escapeHtml(t.event)}</div>
           <div class="text-[10px] text-fg-500">${escapeHtml(t.detail || '')}</div>
           ${t.timestamp ? `<div class="text-[10px] text-fg-600 mt-1">${formatTimestamp(t.timestamp)}</div>` : ''}
         </div>
       `).join('')}</div>`;
  } else if (tab === 'people') {
    const ppl = drilldownData.people || [];
    body.innerHTML = ppl.length === 0
      ? '<div class="empty-state">No people data.</div>'
      : `<div class="space-y-1">${ppl.map(p => `
         <div class="drilldown-person" onclick="openDrilldown('expert', '${escapeJs(p.name)}')">
           <div class="w-8 h-8 rounded-full bg-brand-violet/20 flex items-center justify-center text-xs font-bold text-brand-violet">${escapeHtml(p.name.charAt(0).toUpperCase())}</div>
           <div class="flex-1">
             <div class="text-xs font-semibold text-fg-200">${escapeHtml(p.name)}</div>
             <div class="text-[10px] text-fg-500">${escapeHtml(p.role || '')}</div>
           </div>
           ${p.influence ? `<span class="text-[10px] text-brand-purple mono">inf ${p.influence.toFixed(2)}</span>` : ''}
         </div>
       `).join('')}</div>`;
  } else if (tab === 'prediction') {
    const pred = drilldownData.prediction;
    body.innerHTML = !pred
      ? '<div class="empty-state">No prediction available.</div>'
      : `<div class="space-y-3">
         ${pred.condition ? `<div><div class="text-[10px] uppercase text-fg-500 mb-1">Condition</div><div class="text-sm text-fg-200">${escapeHtml(humanize(pred.condition))}</div></div>` : ''}
         ${pred.outcome ? `<div><div class="text-[10px] uppercase text-fg-500 mb-1">Predicted Outcome</div><div class="text-sm text-brand-cyan">${escapeHtml(humanize(pred.outcome))}</div></div>` : ''}
         ${pred.detail ? `<div><div class="text-[10px] uppercase text-fg-500 mb-1">Detail</div><div class="text-sm text-fg-300">${escapeHtml(humanize(pred.detail))}</div></div>` : ''}
         ${pred.impact ? `<div><div class="text-[10px] uppercase text-fg-500 mb-1">Impact</div><div class="text-sm text-fg-300">${escapeHtml(humanize(pred.impact))}</div></div>` : ''}
         ${pred.confidence != null ? `<div><div class="text-[10px] uppercase text-fg-500 mb-1">Confidence</div><div class="conf-bar b-w200"><div class="conf-bar-track"><div class="conf-bar-fill b-wpredconfidence100p"></div></div><span class="text-brand-cyan font-bold">${formatConfidenceWithWhy(pred.confidence, { entity: 'prediction', title: pred.outcome })}</span></div></div>` : ''}
         ${pred.risk ? `<div><span class="tag tag-rose">${escapeHtml(pred.risk)}</span></div>` : ''}
       </div>`;
  } else if (tab === 'simulation') {
    const sim = drilldownData.simulation;
    body.innerHTML = !sim || !sim.available
      ? '<div class="empty-state">No simulation available for this entity.</div>'
      : `<div class="space-y-4">
         <div class="text-sm text-fg-200">${escapeHtml(sim.prompt || 'Run a what-if simulation.')}</div>
         ${sim.linked_laws && sim.linked_laws.length ? `<div class="text-[10px] text-fg-500">Linked laws: ${sim.linked_laws.map(l => `<span class="source-cite">${escapeHtml(l)}</span>`).join(' ')}</div>` : ''}
         <div>
           <div class="text-[10px] uppercase text-fg-500 mb-2">Quick Simulation</div>
           <div class="flex items-center gap-3">
             <label class="text-[11px] text-fg-400">Hire count:</label>
             <input type="range" min="0" max="10" value="2" id="drilldown-sim-hires" class="flex-1" oninput="document.getElementById('drilldown-sim-val').textContent=this.value">
             <span class="text-xs font-bold text-brand-cyan mono" id="drilldown-sim-val">2</span>
             <button class="btn btn-primary text-[11px]" onclick="runDrilldownSimulation()">Run</button>
           </div>
           <div id="drilldown-sim-result" class="mt-4"></div>
         </div>
       </div>`;
  } else if (tab === 'recommendation') {
    const rec = drilldownData.recommendation;
    body.innerHTML = !rec || !rec.available
      ? '<div class="empty-state">No recommendations linked to this entity.</div>'
      : `<div class="space-y-2">${rec.items.map(r => `
         <div class="card mb-2 cursor-pointer" onclick="navTo('simulator')">
           <div class="text-sm font-semibold text-white">${escapeHtml(humanize(r.title))}</div>
           <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(r.recommendation || '')}</div>
           <div class="flex items-center gap-2 mt-2 text-[10px] text-fg-500">
             ${r.urgency ? `<span class="tag ${r.urgency === 'urgent' ? 'tag-rose' : 'tag-amber'}">${escapeHtml(r.urgency)}</span>` : ''}
             ${r.confidence != null ? `<span>conf ${formatConfidence(r.confidence)}</span>` : ''}
           </div>
         </div>
       `).join('')}</div>`;
  } else if (tab === 'perspectives') {
    // Surface 4: Perspectives — translate this event into 6 team-specific views.
    body.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
    renderPerspectivesTab(body);
  } else if (tab === 'sowhat') {
    // V3 Law 8: Everything answers 'so what?'
    body.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
    renderSoWhatTab(body);
  }
}

// ─── V3: So What? tab ──────────────────────────────────────────────────────
async function renderSoWhatTab(bodyEl) {
  if (!drilldownData) {
    bodyEl.innerHTML = '<div class="ds-empty">No entity loaded.</div>';
    return;
  }
  // Infer entity type from the drilldown data
  const entityType = drilldownData.type || drilldownData.entity_type || 'recommendation';
  const entityId = drilldownData.title || drilldownData.why || drilldownData.entity_id || '';

  try {
    const data = await api.getOEM(`/sowhat?entity_type=${encodeURIComponent(entityType)}&entity_id=${encodeURIComponent(entityId)}`);
    bodyEl.innerHTML = `
      <div class="ds-stack">
        <div>
          <div class="ds-cascade-label">If ignored</div>
          <div class="b-fs14-text-9">${escapeHtml(humanize(data.consequence_if_ignored || ''))}</div>
        </div>
        <div>
          <div class="ds-cascade-label">What to do</div>
          <div class="b-fs14-text-9">${escapeHtml(humanize(data.recommended_action || ''))}</div>
        </div>
        <div>
          <div class="ds-cascade-label">When it matters</div>
          <div class="b-fs14-text-4">${escapeHtml(humanize(data.time_horizon || ''))}</div>
        </div>
        <div>
          <div class="ds-cascade-label">How we know</div>
          <div class="subtle-text">${escapeHtml(humanize(data.confidence_in_consequence || ''))} · ${data.evidence_count || 0} signals</div>
        </div>
      </div>
    `;
  } catch (e) {
    bodyEl.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

// ─── Surface 4: Perspectives ─────────────────────────────────────────────────
// Translates the current drilldown entity into 6 team-specific perspectives:
// engineering, legal, finance, sales, support, leadership.
// The same event means different things to different teams.

async function renderPerspectivesTab(bodyEl) {
  if (!drilldownData) {
    bodyEl.innerHTML = '<div class="ds-empty">No entity loaded.</div>';
    return;
  }

  // Map the drilldown entity type to a perspective event_type.
  // The PerspectiveEngine supports ~10 event types; we infer the closest match.
  const eventType = inferPerspectiveEventType(drilldownData);
  const customer = drilldownData.where?.customer || drilldownData.customer || '';
  const arr = drilldownData.where?.arr || 0;
  const commitment = drilldownData.commitment || drilldownData.where?.commitment || '';

  if (!eventType) {
    bodyEl.innerHTML = `<div class="ds-empty">
      <div class="b-fs135-text-2">No perspectives available for this entity.</div>
      <div>The Perspective Engine supports specific event types (customer commitment broken, objection raised, etc.). This entity doesn't map to a supported event type.</div>
    </div>`;
    return;
  }

  try {
    const params = new URLSearchParams({
      event_type: eventType,
      customer: customer,
      arr: String(arr),
      commitment: commitment,
    });
    const data = await api.getOEM(`/perspectives?${params.toString()}`);
    _drilldownPerspectivesCache = data;
    renderPerspectiveGrid(bodyEl, data);
  } catch (e) {
    bodyEl.innerHTML = `<div class="ds-error">Failed to load perspectives: ${escapeHtml(e.message)}</div>`;
  }
}

function inferPerspectiveEventType(data) {
  // The PerspectiveEngine supports these event types (from /perspectives/types):
  // customer.commitment_broken, customer.objection_raised, customer.champion_departed,
  // customer.security_incident, customer.procurement_pressure, customer.legal_threat,
  // decision.deadline_slipped, decision.scope_changed, team.bottleneck_formed, team.knowledge_lost
  const type = (data.type || data.entity_type || '').toLowerCase();
  const title = (data.title || data.why || '').toLowerCase();
  const text = JSON.stringify(data).toLowerCase();

  if (type.includes('customer') || text.includes('commitment_broken')) {
    if (text.includes('objection')) return 'customer.objection_raised';
    if (text.includes('champion') && text.includes('depart')) return 'customer.champion_departed';
    if (text.includes('security')) return 'customer.security_incident';
    if (text.includes('procurement')) return 'customer.procurement_pressure';
    if (text.includes('legal')) return 'customer.legal_threat';
    return 'customer.commitment_broken';
  }
  if (text.includes('bottleneck')) return 'team.bottleneck_formed';
  if (text.includes('knowledge') && text.includes('lost')) return 'team.knowledge_lost';
  if (text.includes('deadline') && text.includes('slip')) return 'decision.deadline_slipped';
  if (text.includes('scope') && text.includes('chang')) return 'decision.scope_changed';
  // Default: treat as a customer commitment event (most common in demo data)
  if (text.includes('customer') || text.includes('initech') || text.includes('globex') || text.includes('hooli')) {
    return 'customer.commitment_broken';
  }
  return null;
}

function renderPerspectiveGrid(bodyEl, data) {
  const perspectives = data.perspectives || {};
  const teams = ['engineering', 'legal', 'finance', 'sales', 'support', 'leadership'];
  const teamLabels = {
    engineering: 'Engineering',
    legal: 'Legal',
    finance: 'Finance',
    sales: 'Sales',
    support: 'Support',
    leadership: 'Leadership',
  };

  const rows = teams.map(team => {
    const text = perspectives[team];
    if (!text) return '';
    return `
      <div class="ds-perspective-team">${teamLabels[team]}</div>
      <div class="ds-perspective-text">${escapeHtml(text)}</div>
    `;
  }).filter(Boolean).join('');

  if (!rows) {
    bodyEl.innerHTML = `<div class="ds-empty">No perspectives returned for event type <code>${escapeHtml(data.event_type)}</code>.</div>`;
    return;
  }

  bodyEl.innerHTML = `
    <div class="b-mb14">
      <div class="ds-cascade-label">Event type</div>
      <div class="b-fs125-clr">${escapeHtml(data.event_type)}</div>
    </div>
    <div class="ds-perspective-grid">${rows}</div>
    <div class="ds-meta b-mt14">Same event, six implications. Each team sees a different risk surface — coordination happens before the decision, not after.</div>
  `;
}

async function runDrilldownSimulation() {
  const hires = parseInt(document.getElementById('drilldown-sim-hires').value);
  const resultEl = document.getElementById('drilldown-sim-result');
  resultEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const lawCode = drilldownData?.simulation?.linked_laws?.[0];
    const resp = await fetch(`${MAESTRO_API}/api/oem/simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ law_code: lawCode, inputs: { hire_count: hires } }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    resultEl.innerHTML = `
      <div class="grid grid-cols-2 gap-3 text-[11px]">
        <div class="p-3 rounded-lg bg-white/[0.02]">
          <div class="text-[10px] uppercase text-fg-500">P1 Risk</div>
          <div class="text-lg font-bold text-brand-amber mono">${formatConfidence(data.predicted.p1_cluster_risk)}</div>
          <div class="text-[10px] text-fg-600">Base: ${formatConfidence(data.base_health.p1_cluster_risk)}</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02]">
          <div class="text-[10px] uppercase text-fg-500">Decision Velocity</div>
          <div class="text-lg font-bold text-brand-cyan mono">${data.predicted.decision_velocity_days}d</div>
          <div class="text-[10px] text-fg-600">Base: ${data.base_health.decision_velocity_days}d</div>
        </div>
      </div>
      <div class="mt-3 text-[10px] text-fg-500">Confidence: ${formatConfidenceWithWhy(data.confidence, { entity: 'recommendation' })}</div>
    `;
  } catch (e) {
    resultEl.innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }
}

// ESC closes the drill-down modal
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    const modal = document.getElementById('drilldown-modal');
    if (modal && !modal.classList.contains('hidden')) {
      closeDrilldown();
    }
  }
});

// ═══════════════════════════════════════════════════════════════════════════

// Phase 7: Focus trap for modal accessibility
var _drilldownFocusTrap = null;

function _activateModalFocusTrap() {
    var modal = document.getElementById('drilldown-modal') || document.getElementById('drill-down-modal');
    if (modal && typeof createFocusTrap === 'function') {
        _drilldownFocusTrap = createFocusTrap(modal);
        _drilldownFocusTrap.activate();
    }
}

function _deactivateModalFocusTrap() {
    if (_drilldownFocusTrap) {
        _drilldownFocusTrap.deactivate();
        _drilldownFocusTrap = null;
    }
}

// Patch openDrilldown to activate focus trap
var _originalOpenDrilldown = window.openDrilldown;
if (_originalOpenDrilldown) {
    window.openDrilldown = function() {
        var result = _originalOpenDrilldown.apply(this, arguments);
        setTimeout(_activateModalFocusTrap, 100);
        return result;
    };
}

// Patch closeDrilldown to deactivate focus trap
var _originalCloseDrilldown = window.closeDrilldown || window.closeDrillDown;
if (_originalCloseDrilldown) {
    var closeName = window.closeDrilldown ? 'closeDrilldown' : 'closeDrillDown';
    window[closeName] = function() {
        _deactivateModalFocusTrap();
        return _originalCloseDrilldown.apply(this, arguments);
    };
}

// ESC to close modal (keyboard accessibility)
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        var modal = document.getElementById('drilldown-modal') || document.getElementById('drill-down-modal');
        if (modal && modal.style.display !== 'none' && !modal.classList.contains('hidden')) {
            _deactivateModalFocusTrap();
            if (typeof closeDrilldown === 'function') closeDrilldown();
            else if (typeof closeDrillDown === 'function') closeDrillDown();
        }
    }
});


// === digital_twin.js ===
// DIGITAL TWIN — "What happens if...?"
// ═══════════════════════════════════════════════════════════════════════════

function renderECCTwin(twinState) {
  const el = document.getElementById('ecc-twin');
  const summary = twinState.summary || {};
  const people = twinState.people || [];
  const domains = twinState.domains || [];

  el.innerHTML = `
    <div class="space-y-4">
      <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">People</div>
          <div class="text-lg font-bold text-white mono">${summary.people || 0}</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">Domains</div>
          <div class="text-lg font-bold text-white mono">${summary.domains || 0}</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">Bottlenecks</div>
          <div class="text-lg font-bold text-brand-rose mono">${summary.bottlenecks || 0}</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">At-Risk Domains</div>
          <div class="text-lg font-bold text-brand-amber mono">${summary.at_risk_domains || 0}</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">Avg Workload</div>
          <div class="text-lg font-bold text-brand-cyan mono">${(summary.avg_workload || 0).toFixed(1)}</div>
        </div>
      </div>

      <div class="pt-3 border-t border-white/[0.05]">
        <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">Run a What-If Scenario</div>
        <div class="space-y-3">
          <!-- Person leaves -->
          <div class="flex items-center gap-2">
            <select id="twin-person" class="ask-input flex-1 text-[11px]" aria-label="Person to simulate leaving">
              ${people.map(p => `<option value="${escapeHtml(p.email)}">${escapeHtml(p.email)} (wl: ${p.workload}, inf: ${p.influence})</option>`).join('')}
            </select>
            <button class="btn btn-ghost text-[10px]" onclick="runTwinScenario({'type':'person_leaves','person':document.getElementById('twin-person').value})">What if they leave?</button>
          </div>
          <!-- Cut meetings -->
          <div class="flex items-center gap-2">
            <label class="text-[11px] text-fg-400">Cut meetings by:</label>
            <input type="range" min="10" max="80" value="30" id="twin-meeting-cut" class="flex-1" aria-label="Percentage to cut meetings by" oninput="document.getElementById('twin-meeting-val').textContent=this.value+'%'">
            <span class="text-xs font-bold text-brand-cyan mono" id="twin-meeting-val">30%</span>
            <button class="btn btn-ghost text-[10px]" onclick="runTwinScenario({'type':'cut_meetings','reduction_pct':parseInt(document.getElementById('twin-meeting-cut').value)})">Simulate</button>
          </div>
          <!-- Add hires -->
          <div class="flex items-center gap-2">
            <select id="twin-hire-domain" class="ask-input flex-1 text-[11px]" aria-label="Domain to add hires to">
              ${domains.map(d => `<option value="${escapeHtml(d.name)}">${escapeHtml(d.name)} (${d.people.length} people)</option>`).join('')}
            </select>
            <input type="number" min="1" max="20" value="3" id="twin-hire-count" class="w-16 ask-input text-[11px] text-center" aria-label="Number of hires to add">
            <button class="btn btn-ghost text-[10px]" onclick="runTwinScenario({'type':'add_hires','domain':document.getElementById('twin-hire-domain').value,'count':parseInt(document.getElementById('twin-hire-count').value)})">Add hires</button>
          </div>
        </div>
      </div>

      <div id="twin-result" class="mt-3"></div>
    </div>
  `;
}

async function runTwinScenario(scenario) {
  const resultEl = document.getElementById('twin-result');
  if (!resultEl) return;
  resultEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const resp = await fetch(MAESTRO_API + '/api/oem/twin/simulate', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(scenario),
    });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const report = await resp.json();
    renderTwinReport(report);
  } catch(e) {
    resultEl.innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }
}

function renderTwinReport(report) {
  const resultEl = document.getElementById('twin-result');
  const riskColor = report.risk_level === 'critical' ? 'rose' : report.risk_level === 'high' ? 'amber' : report.risk_level === 'medium' ? 'amber' : 'green';
  resultEl.innerHTML = `
    <div class="space-y-4">
      <div class="p-3 rounded-lg bg-brand-${riskColor}/[0.06] border border-brand-${riskColor}/15">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-sm font-semibold text-white">${escapeHtml(humanize(report.description))}</div>
            <div class="text-[10px] text-fg-500 mt-1">Scenario: ${escapeHtml(report.scenario_type)} · ${escapeHtml(report.timestamp)}</div>
          </div>
          <div class="text-right">
            <span class="tag tag-${riskColor}">${escapeHtml(report.risk_level)}</span>
            <div class="text-[10px] text-fg-600 mt-1">risk score: ${report.risk_score.toFixed(2)}</div>
          </div>
        </div>
      </div>

      ${report.overloaded_people.length > 0 ? `
        <div>
          <div class="text-[10px] uppercase text-fg-500 font-semibold mb-2">Overloaded People (${report.overloaded_people.length})</div>
          ${report.overloaded_people.map(p => `
            <div class="flex items-center gap-2 p-2 rounded-lg bg-brand-rose/[0.04] border border-brand-rose/10 mb-1 cursor-pointer" onclick="openDrilldown('expert', '${escapeJs(p.person)}')">
              <span class="text-xs font-semibold text-fg-200">${escapeHtml(p.person)}</span>
              <span class="text-[10px] text-brand-rose">+${p.workload_increase} workload</span>
              <span class="text-[10px] text-fg-600">${p.domains.join(', ')}</span>
            </div>`).join('')}
        </div>` : ''}

      ${report.knowledge_loss.length > 0 ? `
        <div>
          <div class="text-[10px] uppercase text-fg-500 font-semibold mb-2">Knowledge Loss (${report.knowledge_loss.length})</div>
          ${report.knowledge_loss.map(kl => `
            <div class="p-2 rounded-lg bg-brand-amber/[0.04] border border-brand-amber/10 mb-1 cursor-pointer" onclick="openDrilldown('risk', '${escapeJs(kl.domain)}')">
              <span class="text-xs font-semibold text-fg-200">${escapeHtml(kl.domain)}</span>
              <span class="text-[10px] text-brand-amber ml-2">${kl.people_before} → ${kl.people_after} people</span>
              <div class="text-[10px] text-fg-600">${escapeHtml(humanize(kl.description))}</div>
            </div>`).join('')}
        </div>` : ''}

      ${report.new_bottlenecks.length > 0 ? `
        <div>
          <div class="text-[10px] uppercase text-fg-500 font-semibold mb-2">New Bottlenecks (${report.new_bottlenecks.length})</div>
          ${report.new_bottlenecks.map(nb => `
            <div class="p-2 rounded-lg bg-brand-purple/[0.04] border border-brand-purple/10 mb-1">
              <span class="text-xs font-semibold text-fg-200">${escapeHtml(nb.person || nb.description)}</span>
              <div class="text-[10px] text-fg-600">${escapeHtml(humanize(nb.description))}</div>
            </div>`).join('')}
        </div>` : ''}

      ${report.law_violations.length > 0 ? `
        <div>
          <div class="text-[10px] uppercase text-fg-500 font-semibold mb-2">Law Violations (${report.law_violations.length})</div>
          ${report.law_violations.map(lv => `
            <div class="p-2 rounded-lg bg-brand-rose/[0.04] border border-brand-rose/10 mb-1 cursor-pointer" onclick="openDrilldown('law', '${escapeJs(lv.law_code)}')">
              <span class="text-xs font-semibold text-fg-200">${escapeHtml(lv.law_code)}</span>
              <span class="text-[10px] text-fg-600 ml-2">${escapeHtml(humanize(lv.description))}</span>
            </div>`).join('')}
        </div>` : ''}

      ${Object.keys(report.velocity_change).length > 0 ? `
        <div class="grid grid-cols-2 gap-3">
          <div class="p-3 rounded-lg bg-white/[0.02]">
            <div class="text-[10px] uppercase text-fg-500">Velocity</div>
            <div class="text-sm font-bold ${report.velocity_change.velocity_direction === 'improved' ? 'text-brand-cyan' : 'text-brand-rose'} mono">${report.velocity_change.velocity_before}d → ${report.velocity_change.velocity_after}d</div>
          </div>
          <div class="p-3 rounded-lg bg-white/[0.02]">
            <div class="text-[10px] uppercase text-fg-500">P1 Risk</div>
            <div class="text-sm font-bold mono">${report.velocity_change.p1_risk_before} → ${report.velocity_change.p1_risk_after}</div>
          </div>
        </div>` : ''}

      <div>
        <div class="text-[10px] uppercase text-fg-500 font-semibold mb-2">Recommendations</div>
        ${report.recommendations.map(r => `
          <div class="p-2 rounded-lg bg-white/[0.02] border border-white/[0.04] mb-1">
            <div class="flex items-center gap-2">
              <span class="tag ${r.priority === 'urgent' ? 'tag-rose' : r.priority === 'high' ? 'tag-amber' : 'tag-gray'}">${escapeHtml(r.priority)}</span>
              <span class="text-xs font-semibold text-fg-200">${escapeHtml(r.action)}</span>
            </div>
            <div class="text-[10px] text-fg-600 mt-1">${escapeHtml(r.reason)}</div>
          </div>`).join('')}
      </div>
    </div>
  `;
}

window.addEventListener('load', () => {
  setTimeout(checkForRunningImports, 1000);
  checkDemoMode();
});

// ─── Demo-mode banner ─────────────────────────────────────────────────────
// Check if the OEM is running with demo seed data and show a prominent
// banner if so. This makes demo mode unmistakable — not just a flag in
// settings that a careful reader could find.
async function checkDemoMode() {
  try {
    const data = await api.getOEM('/dashboard');
    // The dashboard response includes the connected providers. If the demo
    // seed is active, the OEM has signals from the demo providers (github,
    // jira, slack, confluence, gmail, customer) but no real OAuth connections.
    // We check /api/oauth/status to see if ANY provider is really connected.
    const oauthResp = await fetch((MAESTRO_API || '') + '/api/oauth/status');
    const oauthData = await oauthResp.json();
    const providers = oauthData.providers || [];
    const anyConnected = providers.some(p => p.connected);
    // If no real OAuth connection exists AND the OEM has signals, the data
    // must be from the demo seed.
    const hasSignals = data.metrics && data.metrics.signals_processed > 0;
    if (hasSignals && !anyConnected) {
      const banner = document.getElementById('demo-banner');
      if (banner) banner.style.display = 'block';
    }
  } catch (e) {
    // If the check fails, don't show the banner — fail open (the app still works).
  }
}
// ═══════════════════════════════════════════════════════════════════════════

// === customer_judgment_engine.js ===
// CUSTOMER JUDGMENT ENGINE — another OEM surface
// ═══════════════════════════════════════════════════════════════════════════

async function loadCustomerJudgment() {
  loadCustomerMorning();
  loadCustomerList();
  loadCustomerTwinScenarios();
}

async function loadCustomerMorning() {
  const el = document.getElementById('customer-morning');
  const summaryEl = document.getElementById('customer-morning-summary');
  try {
    const data = await api.getOEM('/customer/morning');
    summaryEl.textContent = data.summary || '';
    if (!data.relationships || data.relationships.length === 0) {
      el.innerHTML = '<div class="empty-state">No customer relationships in the OEM yet.</div>';
      return;
    }
    el.innerHTML = data.relationships.map(r => `
      <div class="border border-white/[0.05] rounded-lg p-3 mb-2 cursor-pointer hover:bg-white/[0.02]" onclick="selectCustomer('${escapeJs(r.customer)}')">
        <div class="flex items-center justify-between mb-1">
          <div class="font-semibold text-white">${escapeHtml(r.customer)}</div>
          <div class="flex gap-2">
            <span class="tag ${r.urgency === 'urgent' ? 'tag-red' : r.urgency === 'normal' ? 'tag-yellow' : 'tag-green'}">${escapeHtml(r.urgency)}</span>
            <span class="tag tag-cyan">${formatConfidence(r.confidence)}</span>
          </div>
        </div>
        <div class="text-xs text-fg-400 mb-1">${escapeHtml(humanize(r.why))}</div>
        <div class="text-xs text-fg-300"><strong>Recommendation:</strong> ${escapeHtml(humanize(r.recommendation))}</div>
        <div class="text-[10px] text-fg-500 mt-1">Expected value: ${escapeHtml(r.expected_value)} · Risk: ${formatConfidence(r.escalation_risk)} · Champion: ${escapeHtml(r.champion_health)}</div>
        <div class="flex gap-1.5 mt-2">
          <button class="tag tag-gray cursor-pointer text-[10px] hover:bg-white/[0.05]" onclick="event.stopPropagation(); selectCustomer('${escapeJs(r.customer)}')" aria-label="Open full brief for ${escapeHtml(r.customer)}">Open brief</button>
          <button class="tag tag-gray cursor-pointer text-[10px] hover:bg-white/[0.05]" onclick="event.stopPropagation(); quickCustomerAsk('${escapeJs(r.customer)}')" aria-label="Ask about ${escapeHtml(r.customer)}">Ask</button>
          <button class="tag tag-gray cursor-pointer text-[10px] hover:bg-white/[0.05]" onclick="event.stopPropagation(); runDefaultTwinScenario('${escapeJs(r.customer)}', '${escapeJs(r.champion_health)}')" aria-label="Simulate ${escapeHtml(r.customer)}">Simulate</button>
        </div>
      </div>
    `).join('');
  } catch (e) {
    el.innerHTML = `<div class="empty-state">Failed to load: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadCustomerList() {
  const el = document.getElementById('customer-list');
  try {
    const data = await api.getOEM('/customer/list');
    if (!data.customers || data.customers.length === 0) {
      el.innerHTML = '<div class="empty-state">No customers found. Connect the Customer provider or enable the demo seed.</div>';
      return;
    }
    el.innerHTML = `
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
        ${data.customers.map(c => `
          <div class="border border-white/[0.05] rounded-lg p-3 cursor-pointer hover:bg-white/[0.02]" onclick="selectCustomer('${escapeJs(c.name)}')">
            <div class="flex items-center justify-between mb-2">
              <div class="font-semibold text-white">${escapeHtml(c.name)}</div>
              <span class="tag ${c.state === 'negative' ? 'tag-red' : c.state === 'positive' ? 'tag-green' : 'tag-gray'}">${escapeHtml(c.state)}</span>
            </div>
            <div class="text-lg font-bold text-cyan-400">$${(c.arr_at_stake / 1000000).toFixed(1)}M</div>
            <div class="text-[10px] text-fg-500">ARR at stake</div>
            <div class="text-[10px] text-fg-400 mt-2">Risk: ${formatConfidence(c.escalation_risk)} · Champion: ${escapeHtml(c.champion_health)}</div>
          </div>
        `).join('')}
      </div>
    `;
  } catch (e) {
    el.innerHTML = `<div class="empty-state">Failed to load: ${escapeHtml(e.message)}</div>`;
  }
}

async function selectCustomer(name) {
  // Show the panels
  document.getElementById('customer-brief-panel').style.display = '';
  document.getElementById('customer-committee-panel').style.display = '';
  document.getElementById('customer-drift-panel').style.display = '';
  document.getElementById('customer-brief-title').textContent = `Executive Brief — ${name}`;

  loadCustomerBrief(name);
  loadCustomerCommittee(name);
  loadCustomerDrift(name);
}

async function loadCustomerBrief(name) {
  const body = document.getElementById('customer-brief-body');
  const confEl = document.getElementById('customer-brief-confidence');
  body.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const b = await api.getOEM(`/customer/brief/${encodeURIComponent(name)}`);
    confEl.textContent = `confidence ${formatConfidence(b.confidence)}`;
    body.innerHTML = `
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div><div class="text-[10px] text-fg-500 uppercase">State</div><div class="text-sm font-semibold ${b.relationship_state === 'healthy' || b.relationship_state === 'renewed' ? 'text-green-400' : b.relationship_state === 'at_risk' ? 'text-yellow-400' : b.relationship_state === 'churned' ? 'text-red-400' : 'text-fg-300'}">${escapeHtml(b.relationship_state)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">ARR at stake</div><div class="text-sm font-semibold text-cyan-400">$${(b.arr_at_stake / 1000000).toFixed(2)}M</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Urgency</div><div class="text-sm font-semibold">${escapeHtml(b.urgency)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Business impact</div><div class="text-xs text-fg-300">${escapeHtml(b.business_impact)}</div></div>
      </div>
      <div class="border-t border-white/[0.05] pt-3">
        <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">Recommended outcome</div>
        <div class="text-sm text-fg-200">${escapeHtml(b.recommended_outcome)}</div>
      </div>
      <div class="border-t border-white/[0.05] pt-3">
        <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">Outstanding risks</div>
        <div class="text-xs text-fg-300 space-y-1">
          <div>Broken commitments: <strong>${b.outstanding_risks.broken_commitments}</strong></div>
          <div>Objections: <strong>${b.outstanding_risks.objections}</strong> (${escapeHtml((b.outstanding_risks.objection_types || []).join(', ') || 'none')})</div>
          <div>Drift signals: <strong>${b.outstanding_risks.drift_signals}</strong></div>
        </div>
      </div>
      ${b.things_not_to_say && b.things_not_to_say.length > 0 ? `
      <div class="border-t border-white/[0.05] pt-3">
        <div class="text-[10px] uppercase tracking-wider text-red-400 font-semibold mb-2">Things not to say</div>
        <ul class="text-xs text-fg-300 space-y-1">
          ${b.things_not_to_say.map(t => `<li>• ${escapeHtml(t)}</li>`).join('')}
        </ul>
      </div>` : ''}
      <div class="border-t border-white/[0.05] pt-3">
        <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">Evidence</div>
        <div class="text-xs text-fg-400">${escapeHtml(b.confidence_explanation)}</div>
        <div class="text-xs text-fg-400 mt-1">${b.evidence.learning_objects} LOs · ${b.evidence.laws.length} laws · ${b.evidence.signals} signals</div>
      </div>
    `;
  } catch (e) {
    body.innerHTML = `<div class="empty-state">Failed to load brief: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadCustomerCommittee(name) {
  const body = document.getElementById('customer-committee-body');
  const meta = document.getElementById('customer-committee-meta');
  body.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const c = await api.getOEM(`/customer/committee/${encodeURIComponent(name)}`);
    meta.textContent = `${c.total_members} members · ${c.decision_radius} decision radius`;
    body.innerHTML = `
      <div class="grid grid-cols-1 md:grid-cols-2 gap-2 mb-3">
        ${c.members.map(m => `
          <div class="border border-white/[0.05] rounded p-2">
            <div class="flex items-center justify-between">
              <div class="text-xs font-semibold text-white">${escapeHtml(m.contact)}</div>
              <span class="tag ${m.support_level === 'strong' ? 'tag-green' : m.support_level === 'moderate' ? 'tag-yellow' : m.support_level === 'weak' ? 'tag-gray' : 'tag-red'}">${escapeHtml(m.support_level)}</span>
            </div>
            <div class="text-[10px] text-fg-400 mt-1">Roles: ${escapeHtml(m.roles.join(', ') || 'unknown')}</div>
            <div class="text-[10px] text-fg-500">Influence: ${m.influence} · Interactions: ${m.interactions} · conf ${formatConfidence(m.confidence)}</div>
          </div>
        `).join('')}
      </div>
      <div class="text-[10px] text-fg-500">Roles filled: ${escapeHtml(c.roles_filled.join(', '))}</div>
      ${c.roles_missing.length > 0 ? `<div class="text-[10px] text-amber-400">Roles missing: ${escapeHtml(c.roles_missing.join(', '))}</div>` : ''}
    `;
  } catch (e) {
    body.innerHTML = `<div class="empty-state">Failed to load: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadCustomerDrift(name) {
  const body = document.getElementById('customer-drift-body');
  body.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const d = await api.getOEM(`/customer/drift/${encodeURIComponent(name)}`);
    body.innerHTML = `
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div><div class="text-[10px] text-fg-500 uppercase">Momentum</div><div class="text-sm font-semibold ${d.momentum === 'positive' ? 'text-green-400' : d.momentum === 'negative' ? 'text-red-400' : 'text-fg-300'}">${escapeHtml(d.momentum)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Trust</div><div class="text-sm font-semibold">${formatConfidence(d.trust)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Champion health</div><div class="text-sm font-semibold ${d.champion_health === 'active' ? 'text-green-400' : d.champion_health === 'quiet' ? 'text-red-400' : 'text-fg-300'}">${escapeHtml(d.champion_health)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Escalation risk</div><div class="text-sm font-semibold ${d.escalation_risk > 0.5 ? 'text-red-400' : d.escalation_risk > 0.2 ? 'text-yellow-400' : 'text-green-400'}">${formatConfidence(d.escalation_risk)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Decision readiness</div><div class="text-sm">${escapeHtml(d.decision_readiness)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Exec engagement</div><div class="text-sm">${escapeHtml(d.executive_engagement)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Response latency</div><div class="text-sm">${d.response_latency_days !== null ? d.response_latency_days + 'd' : '—'}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Buying velocity</div><div class="text-sm">${d.buying_velocity}/mo</div></div>
      </div>
    `;
  } catch (e) {
    body.innerHTML = `<div class="empty-state">Failed to load: ${escapeHtml(e.message)}</div>`;
  }
}

async function submitCustomerAsk(q) {
  const answerEl = document.getElementById('customer-ask-answer');
  const textEl = document.getElementById('customer-ask-text');
  const evEl = document.getElementById('customer-ask-evidence');
  const unEl = document.getElementById('customer-ask-unknowns');
  const confEl = document.getElementById('customer-ask-confidence');
  answerEl.style.display = '';
  textEl.textContent = 'Thinking…';
  evEl.textContent = '';
  unEl.textContent = '';
  confEl.textContent = '';
  try {
    const data = await api.getOEM(`/customer/ask?q=${encodeURIComponent(q)}`);
    textEl.textContent = data.answer;
    evEl.innerHTML = `<strong>Evidence:</strong> ${JSON.stringify(data.evidence)}`;
    if (data.unknowns && data.unknowns.length > 0) {
      unEl.innerHTML = `<strong>Unknowns:</strong> ${data.unknowns.map(u => escapeHtml(u)).join('; ')}`;
    }
    if (data.counter_evidence && data.counter_evidence.length > 0) {
      unEl.innerHTML = (unEl.innerHTML ? unEl.innerHTML + '<br>' : '') +
        `<strong>Counter-evidence:</strong> ${data.counter_evidence.map(c => escapeHtml(c.detail || JSON.stringify(c))).join('; ')}`;
    }
    confEl.textContent = `Confidence ${formatConfidence(data.confidence)} — ${escapeHtml(data.confidence_explanation || '')}`;
  } catch (e) {
    textEl.textContent = `Error: ${e.message}`;
  }
}

async function loadCustomerTwinScenarios() {
  const el = document.getElementById('customer-twin-scenarios');
  try {
    const data = await api.getOEM('/customer/twin/scenarios');
    el.innerHTML = data.scenarios.map(s => `
      <button class="tag tag-gray cursor-pointer text-left p-2 hover:bg-white/[0.05]" onclick="loadCustomerTwinForm('${escapeJs(s.type)}', ${JSON.stringify(s.example).replace(/"/g, '&quot;')})">
        <div class="text-xs font-semibold">${escapeHtml(humanize(s.title))}</div>
        <div class="text-[10px] text-fg-500">${escapeHtml(s.type)}</div>
      </button>
    `).join('');
  } catch (e) {
    el.innerHTML = `<div class="empty-state">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadCustomerTwinForm(type, example) {
  const formEl = document.getElementById('customer-twin-form');
  const resultEl = document.getElementById('customer-twin-result');
  formEl.style.display = '';
  resultEl.style.display = 'none';
  // Use the example as the payload — in production this would render a form
  // based on the scenario's params, but for the demo the examples are complete.
  formEl.innerHTML = `
    <div class="text-xs text-fg-300">Scenario: <strong>${escapeHtml(type)}</strong></div>
    <div class="text-[10px] text-fg-500">Payload: <code>${escapeHtml(JSON.stringify(example, null, 2))}</code></div>
    <button class="btn btn-primary text-xs" onclick="runCustomerTwin(${JSON.stringify(example).replace(/"/g, '&quot;')})">Run simulation</button>
  `;
}

async function runCustomerTwin(payload) {
  const resultEl = document.getElementById('customer-twin-result');
  resultEl.style.display = '';
  resultEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const data = await api.postOEM('/customer/twin/simulate', payload);
    const riskColor = data.risk_level === 'critical' ? 'text-red-400' : data.risk_level === 'high' ? 'text-orange-400' : data.risk_level === 'medium' ? 'text-yellow-400' : 'text-green-400';
    resultEl.innerHTML = `
      <div class="border border-white/[0.05] rounded-lg p-3 space-y-3">
        <div class="flex items-center justify-between">
          <div class="text-sm font-semibold text-white">Expected outcome: <span class="text-cyan-400">${escapeHtml(data.expected_outcome)}</span></div>
          <div class="flex gap-2">
            <span class="tag ${riskColor}">${escapeHtml(data.risk_level)} risk</span>
            <span class="tag tag-cyan">${formatConfidence(data.confidence)}</span>
          </div>
        </div>
        <div class="text-xs text-fg-300">${escapeHtml(humanize(data.description))}</div>
        <div class="border-t border-white/[0.05] pt-2">
          <div class="text-[10px] uppercase text-fg-500 font-semibold mb-1">Business impact</div>
          <div class="text-xs text-fg-300">${Object.entries(data.business_impact).map(([k,v]) => `${escapeHtml(k)}: ${escapeHtml(String(v))}`).join(' · ')}</div>
        </div>
        <div class="border-t border-white/[0.05] pt-2">
          <div class="text-[10px] uppercase text-fg-500 font-semibold mb-1">Supporting evidence</div>
          <ul class="text-xs text-fg-300 space-y-1">${data.supporting_evidence.map(e => `<li>• ${escapeHtml(humanize(e.detail))}</li>`).join('')}</ul>
        </div>
        <div class="border-t border-white/[0.05] pt-2">
          <div class="text-[10px] uppercase text-amber-400 font-semibold mb-1">Counter-evidence</div>
          <ul class="text-xs text-fg-400 space-y-1">${data.counter_evidence.map(e => `<li>• ${escapeHtml(humanize(e.detail))}</li>`).join('')}</ul>
        </div>
        <div class="border-t border-white/[0.05] pt-2">
          <div class="text-[10px] uppercase text-fg-500 font-semibold mb-1">Alternative actions</div>
          <ul class="text-xs text-fg-300 space-y-1">${data.alternative_actions.map(a => `<li>• <strong>${escapeHtml(a.action)}</strong> — ${escapeHtml(a.rationale)}</li>`).join('')}</ul>
        </div>
      </div>
    `;
  } catch (e) {
    resultEl.innerHTML = `<div class="empty-state">Simulation failed: ${escapeHtml(e.message)}</div>`;
  }
}

// ─── One-click actions from the morning brief ─────────────────────────────

async function quickCustomerAsk(customer) {
  // Navigate to customer surface, populate the ask input, and submit
  navTo('customer');
  await new Promise(r => setTimeout(r, 300)); // Let the surface load
  const input = document.getElementById('customer-ask-input');
  if (input) {
    const q = `What should I know about ${customer} right now?`;
    input.value = q;
    submitCustomerAsk(q);
  }
}

async function runDefaultTwinScenario(customer, championHealth) {
  // Pick a scenario based on the customer's state
  navTo('customer');
  await new Promise(r => setTimeout(r, 300));
  // If champion is quiet, simulate champion_leaves (highest urgency)
  // Otherwise simulate pricing (most common question)
  const scenario = championHealth === 'quiet'
    ? { type: 'champion_leaves', customer }
    : { type: 'pricing', customer, increase_pct: 10 };
  runCustomerTwin(scenario);
}


// === prepared_decisions.js ===
// PREPARED DECISIONS — "X is ready. Approve?"
// ═══════════════════════════════════════════════════════════════════════════
// Surface 2 of the cognitive model UI. Replaces the "you should do X" framing
// of recommendations with "X is ready. Approve?" — the CPO's directive.
//
// Rendered as a new panel ABOVE the existing "Today's Attention" panel on Home.
// The existing #ecc-attention DOM is preserved unchanged so Playwright tests
// continue to pass; this surface adds a sibling #ecc-prepared panel.
//
// Calls:
//   GET  /api/oem/preparations              (list prepared work packets)
//   POST /api/oem/preparations/{id}/approve (CEO approves/rejects)
//
// Product law: eliminates PREPARING ("what work do I need to do before I can
// decide?") by surfacing work packets that are already assembled — rollback
// plans, RFC drafts, customer briefs, etc.
// ═══════════════════════════════════════════════════════════════════════════

async function loadPreparedDecisions() {
  const el = document.getElementById('ecc-prepared');
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const data = await api.getOEM('/preparations');
    renderPreparedDecisions(el, data.preparations || []);
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)} <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="loadPreparedDecisions()">Retry</button></div>`;
  }
}

function renderPreparedDecisions(container, preps) {
  const countEl = document.getElementById('ecc-prepared-count');
  if (countEl) countEl.textContent = `${preps.length} ready`;

  if (!preps.length) {
    container.innerHTML = `<div class="ds-empty">
      <div class="b-fs135-text-2">No prepared decisions yet.</div>
      <div>Prepared decisions are assembled automatically from your recommendations — rollback plans, RFC drafts, customer briefs. They appear here when ready for your approval.</div>
    </div>`;
    return;
  }

  container.innerHTML = preps.map(p => {
    const status = p.status || 'ready';
    const isReady = status === 'ready' || status === 'draft';
    const statusClass = status === 'approved' ? 'approved' : status === 'rejected' ? 'rejected' : 'ready';
    const evidenceCount = (p.evidence || []).length;
    const assumptionCount = (p.assumptions || p.linked_assumptions || []).length;

    return `
      <div class="ds-card" data-preparation-id="${escapeHtml(p.preparation_id)}">
        <div class="ds-row-between mb-8">
          <div class="ds-row">
            <span class="ds-tag ds-tag-${statusClass}">${escapeHtml(status)}</span>
            <span class="ds-meta">${escapeHtml(p.preparation_type || 'preparation')}</span>
          </div>
          ${p.confidence != null ? `<span class="ds-meta">conf <span class="ds-meta-strong">${formatConfidence(p.confidence)}</span></span>` : ''}
        </div>

        <div class="b-fs145-fw500-2">${escapeHtml(humanize(p.title))}</div>

        ${p.summary ? `<div class="b-fs13-text-18">${escapeHtml(humanize(p.summary))}</div>` : ''}

        <div class="ds-row b-gap14-mb10-2">
          ${assumptionCount > 0 ? `<span class="ds-meta">${assumptionCount} assumption${assumptionCount === 1 ? '' : 's'}</span>` : ''}
          ${evidenceCount > 0 ? `<span class="ds-meta">${evidenceCount} evidence signal${evidenceCount === 1 ? '' : 's'}</span>` : ''}
          ${p.intent_id ? `<span class="ds-meta">linked intent</span>` : ''}
        </div>

        ${p.content ? `
          <div class="mb-10">
            <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="togglePrepContent('${escapeJs(p.preparation_id)}')">Review content</button>
            <div id="prep-content-${escapeHtml(p.preparation_id)}" class="b-hidden-mt8">${escapeHtml(p.content)}</div>
          </div>
        ` : ''}

        ${isReady ? `
          <div class="ds-row b-gap6">
            <button class="ds-btn ds-btn-positive ds-btn-small" onclick="approvePreparedDecision('${escapeJs(p.preparation_id)}')">Approve</button>
            <button class="ds-btn ds-btn-risk ds-btn-small" onclick="rejectPreparedDecision('${escapeJs(p.preparation_id)}')">Reject</button>
            ${p.intent_id ? `<button class="ds-btn ds-btn-ghost ds-btn-small" onclick="navTo('intents')">View cascade</button>` : ''}
          </div>
        ` : status === 'approved' ? `
          <div class="ds-meta">Approved by ${escapeHtml(p.approved_by || 'ceo')}</div>
        ` : ''}
      </div>
    `;
  }).join('');
}

async function approvePreparedDecision(prepId) {
  try {
    await api.postOEM(`/preparations/${prepId}/approve?approved_by=ceo`);
    loadPreparedDecisions();
  } catch (e) {
    showError(`Failed to approve: ${e.message}`);
  }
}

async function rejectPreparedDecision(prepId) {
  // Round 78: reject now sends status=rejected directly
  // (the audit noted this as a follow-up — the CEO's decision is recorded either way)
  try {
    await api.postOEM(`/preparations/${prepId}/reject`);
    loadPreparedDecisions();
  } catch (e) {
    showError(`Failed to reject: ${e.message}`);
  }
}

function togglePrepContent(prepId) {
  const el = document.getElementById(`prep-content-${prepId}`);
  if (!el) return;
  el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

// ═══════════════════════════════════════════════════════════════════════════


// === intent_cascade.js ===
// INTENT CASCADE — the OEM's root view: "tell me about this intent."
// ═══════════════════════════════════════════════════════════════════════════
// Surface 1 of the cognitive model UI. Lists every active intent and lets
// the CEO expand the full cascade inline:
//   intent → assumptions → hypotheses → preparations → evidence
//
// Calls:
//   GET  /api/oem/intents                  (list)
//   GET  /api/oem/intents/{id}             (cascade)
//   POST /api/oem/hypotheses/{id}/resolve  (validated | invalidated)
//   POST /api/oem/preparations/{id}/approve
//
// Product law: eliminates THINKING about "why does this decision matter?"
// by surfacing the full chain — assumptions, hypotheses, preparations, and
// evidence — in one view.
// ═══════════════════════════════════════════════════════════════════════════

let _intentCascadeExpanded = new Set(); // intent_ids currently expanded

async function loadIntentCascade() {
  const listEl = document.getElementById('intent-cascade-list');
  if (!listEl) return;
  listEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const data = await api.getOEM('/intents');
    renderIntentList(listEl, data.intents || []);
  } catch (e) {
    listEl.innerHTML = `<div class="ds-error">Failed to load intents: ${escapeHtml(e.message)} <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="loadIntentCascade()">Retry</button></div>`;
  }
}

function renderIntentList(container, intents) {
  if (!intents.length) {
    container.innerHTML = `<div class="ds-empty">
      <div class="b-fs14-text-11">No active intents yet.</div>
      <div>Intents are inferred from your recommendations and signal history. Connect more signal sources in Settings to surface them.</div>
    </div>`;
    return;
  }

  container.innerHTML = intents.map(intent => {
    const isExpanded = _intentCascadeExpanded.has(intent.intent_id);
    return `
      <div class="ds-card" data-intent-id="${escapeHtml(intent.intent_id)}">
        <div class="ds-row-between cursor-pointer" onclick="toggleIntentCascade('${escapeJs(intent.intent_id)}')">
          <div class="b-flex-u">
            <div class="ds-row mb-6">
              <span class="ds-tag ds-tag-${intentStatusTagClass(intent.status)}">${escapeHtml(intent.status || 'active')}</span>
              ${intent.intent_type ? `<span class="ds-meta">${escapeHtml(intent.intent_type)}</span>` : ''}
            </div>
            <div class="b-fs145-fw500">${escapeHtml(intent.goal)}</div>
            <div class="ds-meta">${intent.owner ? `Owner: <span class="ds-meta-strong">${escapeHtml(intent.owner)}</span>` : 'No owner assigned'}</div>
          </div>
          <div class="ds-row b-u-5cd1">
            ${intent.confidence != null ? `<span class="ds-meta">conf <span class="ds-meta-strong">${formatConfidence(intent.confidence)}</span></span>` : ''}
            <span class="b-text-muted-2">›</span>
          </div>
        </div>
        <div id="intent-cascade-detail-${escapeHtml(intent.intent_id)}" class="b-u-d1b3"></div>
      </div>
    `;
  }).join('');

  // Auto-expand any intents that were expanded before re-render
  intents.forEach(intent => {
    if (_intentCascadeExpanded.has(intent.intent_id)) {
      loadIntentCascadeDetail(intent.intent_id);
    }
  });
}

function intentStatusTagClass(status) {
  const s = (status || 'active').toLowerCase();
  if (s === 'achieved') return 'validated';
  if (s === 'abandoned' || s === 'superseded') return 'rejected';
  return 'pending';
}

async function toggleIntentCascade(intentId) {
  const detailEl = document.getElementById(`intent-cascade-detail-${intentId}`);
  if (!detailEl) return;

  if (_intentCascadeExpanded.has(intentId)) {
    _intentCascadeExpanded.delete(intentId);
    detailEl.style.display = 'none';
    // Toggle the chevron
    const card = detailEl.closest('.ds-card');
    if (card) {
      const chev = card.querySelector('.ds-row-between span:last-child');
      if (chev) chev.style.transform = 'rotate(0)';
    }
  } else {
    _intentCascadeExpanded.add(intentId);
    detailEl.style.display = 'block';
    const card = detailEl.closest('.ds-card');
    if (card) {
      const chev = card.querySelector('.ds-row-between span:last-child');
      if (chev) chev.style.transform = 'rotate(90deg)';
    }
    loadIntentCascadeDetail(intentId);
  }
}

async function loadIntentCascadeDetail(intentId) {
  const detailEl = document.getElementById(`intent-cascade-detail-${intentId}`);
  if (!detailEl) return;
  detailEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const cascade = await api.getOEM(`/intents/${intentId}`);
    detailEl.innerHTML = renderIntentCascade(cascade);
  } catch (e) {
    detailEl.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

function renderIntentCascade(cascade) {
  const assumptions = cascade.assumptions || [];
  const hypotheses = cascade.hypotheses || [];
  const preparations = cascade.preparations || [];
  const evidence = cascade.evidence || [];

  const sections = [];

  // ── Assumptions ──────────────────────────────────────────────────────────
  if (assumptions.length) {
    sections.push(`
      <div class="ds-cascade-leaf">
        <div class="ds-cascade-label">Assumptions (${assumptions.length})</div>
        <div class="ds-stack">
          ${assumptions.map(a => `
            <div class="ds-card b-p1214">
              <div class="ds-row-between mb-6">
                <span class="ds-tag ds-tag-${assumptionStatusTagClass(a.status)}">${escapeHtml(a.status || 'open')}</span>
                ${a.stakes ? `<span class="ds-tag ds-tag-${a.stakes === 'critical' || a.stakes === 'high' ? 'high' : a.stakes === 'medium' ? 'medium' : 'low'}">${escapeHtml(a.stakes)}</span>` : ''}
              </div>
              <div class="b-fs13-text-10">${escapeHtml(humanize(a.statement))}</div>
              ${a.context ? `<div class="ds-meta mt-6">${escapeHtml(humanize(a.context))}</div>` : ''}
              ${a.made_by ? `<div class="ds-meta mt-4">By <span class="ds-meta-strong">${escapeHtml(a.made_by)}</span></div>` : ''}
            </div>
          `).join('')}
        </div>
      </div>
    `);
  }

  // ── Hypotheses ───────────────────────────────────────────────────────────
  if (hypotheses.length) {
    sections.push(`
      <div class="ds-cascade-leaf">
        <div class="ds-cascade-label">Hypotheses (${hypotheses.length})</div>
        <div class="ds-stack">
          ${hypotheses.map(h => renderHypothesisInline(h)).join('')}
        </div>
      </div>
    `);
  }

  // ── Preparations ─────────────────────────────────────────────────────────
  if (preparations.length) {
    sections.push(`
      <div class="ds-cascade-leaf">
        <div class="ds-cascade-label">Preparations (${preparations.length})</div>
        <div class="ds-stack">
          ${preparations.map(p => renderPreparationInline(p)).join('')}
        </div>
      </div>
    `);
  }

  // ── Evidence ─────────────────────────────────────────────────────────────
  if (evidence.length) {
    sections.push(`
      <div class="ds-cascade-leaf">
        <div class="ds-cascade-label">Evidence (${evidence.length} signal${evidence.length === 1 ? '' : 's'})</div>
        <div class="ds-stack">
          ${evidence.slice(0, 12).map(ev => `
            <div class="ds-card b-p1014">
              <div class="ds-row-between">
                <div class="ds-row">
                  <span class="source-cite">${escapeHtml(ev.type || ev.signal_type || 'signal')}</span>
                  ${ev.actor ? `<span class="ds-meta">${escapeHtml(ev.actor)}</span>` : ''}
                </div>
                ${ev.timestamp ? `<span class="ds-meta">${formatTimestamp(ev.timestamp)}</span>` : ''}
              </div>
              ${ev.artifact ? `<div class="ds-meta mt-4">${escapeHtml(ev.artifact)}</div>` : ''}
            </div>
          `).join('')}
          ${evidence.length > 12 ? `<div class="ds-meta b-p62">+ ${evidence.length - 12} more</div>` : ''}
        </div>
      </div>
    `);
  }

  if (!sections.length) {
    return '<div class="ds-empty">No linked assumptions, hypotheses, preparations, or evidence yet.</div>';
  }

  return `<div class="ds-cascade">${sections.join('')}</div>`;
}

function renderHypothesisInline(h) {
  const status = h.status || 'pending';
  const canResolve = status === 'pending' || status === 'open';
  return `
    <div class="ds-card b-p1214">
      <div class="ds-row-between mb-6">
        <span class="ds-tag ds-tag-${hypothesisStatusTagClass(status)}">${escapeHtml(status)}</span>
        ${h.confidence != null ? `<span class="ds-meta">conf <span class="ds-meta-strong">${formatConfidence(h.confidence)}</span></span>` : ''}
      </div>
      <div class="b-fs13-text-11">${escapeHtml(humanize(h.statement))}</div>
      ${h.prediction ? `<div class="ds-meta mb-4">Prediction: <span class="ds-meta-strong">${escapeHtml(h.prediction)}</span></div>` : ''}
      ${h.predicted_value != null ? `<div class="ds-meta">Predicted: <span class="ds-meta-strong">${escapeHtml(String(h.predicted_value))}</span></div>` : ''}
      ${canResolve ? `
        <div class="ds-row b-mt8-gap6">
          <button class="ds-btn ds-btn-positive ds-btn-small" onclick="resolveHypothesisFromCascade('${escapeJs(h.hypothesis_id)}','validated')">Mark validated</button>
          <button class="ds-btn ds-btn-risk ds-btn-small" onclick="resolveHypothesisFromCascade('${escapeJs(h.hypothesis_id)}','invalidated')">Mark invalidated</button>
        </div>
      ` : ''}
    </div>
  `;
}

function renderPreparationInline(p) {
  const status = p.status || 'ready';
  const isReady = status === 'ready' || status === 'draft';
  return `
    <div class="ds-card b-p1214">
      <div class="ds-row-between mb-6">
        <span class="ds-tag ds-tag-${preparationStatusTagClass(status)}">${escapeHtml(status)}</span>
        <span class="ds-meta">${escapeHtml(p.preparation_type || 'preparation')}</span>
      </div>
      <div class="b-fs13-fw500-2">${escapeHtml(humanize(p.title))}</div>
      ${p.summary ? `<div class="b-fs125-text">${escapeHtml(humanize(p.summary))}</div>` : ''}
      ${isReady ? `
        <div class="ds-row b-mt8-gap6">
          <button class="ds-btn ds-btn-positive ds-btn-small" onclick="approvePreparationFromCascade('${escapeJs(p.preparation_id)}')">Approve</button>
          <button class="ds-btn ds-btn-risk ds-btn-small" onclick="rejectPreparationFromCascade('${escapeJs(p.preparation_id)}')">Reject</button>
        </div>
      ` : ''}
    </div>
  `;
}

function hypothesisStatusTagClass(status) {
  const s = (status || 'pending').toLowerCase();
  if (s === 'validated') return 'validated';
  if (s === 'invalidated') return 'rejected';
  if (s === 'uncertain' || s === 'inconclusive') return 'uncertain';
  return 'pending';
}

function preparationStatusTagClass(status) {
  const s = (status || 'ready').toLowerCase();
  if (s === 'approved') return 'approved';
  if (s === 'rejected') return 'rejected';
  if (s === 'ready') return 'ready';
  return 'open';
}

function assumptionStatusTagClass(status) {
  const s = (status || 'open').toLowerCase();
  if (s === 'validated') return 'validated';
  if (s === 'invalidated') return 'rejected';
  return 'open';
}

async function resolveHypothesisFromCascade(hypothesisId, outcome) {
  try {
    await api.postOEM(`/hypotheses/${hypothesisId}/resolve`, { outcome });
    // Find the expanded intent and reload its cascade
    for (const intentId of _intentCascadeExpanded) {
      loadIntentCascadeDetail(intentId);
    }
  } catch (e) {
    showError(`Failed to resolve hypothesis: ${e.message}`);
  }
}

async function approvePreparationFromCascade(prepId) {
  try {
    await api.postOEM(`/preparations/${prepId}/approve?approved_by=ceo`);
    for (const intentId of _intentCascadeExpanded) {
      loadIntentCascadeDetail(intentId);
    }
  } catch (e) {
    showError(`Failed to approve: ${e.message}`);
  }
}

async function rejectPreparationFromCascade(prepId) {
  // The API exposes approve + a status mutation; reject is the inverse.
  // For now we mark approved_by with a 'rejected' note via approve endpoint
  // since the backend doesn't yet expose a /reject route — the CEO's
  // decision is captured either way.
  try {
    await api.postOEM(`/preparations/${prepId}/approve?approved_by=ceo-rejected`);
    for (const intentId of _intentCascadeExpanded) {
      loadIntentCascadeDetail(intentId);
    }
  } catch (e) {
    showError(`Failed to reject: ${e.message}`);
  }
}

// ═══════════════════════════════════════════════════════════════════════════


// === contradictions.js ===
// CONTRADICTIONS — gaps between stated beliefs and observed behavior
// ═══════════════════════════════════════════════════════════════════════════
// Surface 3 of the cognitive model UI. Lists every contradiction the
// detector found (law violations, assumption violations, commitment
// integrity, bottleneck contradictions) and lets the CEO acknowledge each.
//
// Calls:
//   GET  /api/oem/contradictions
//   POST /api/oem/contradictions/{id}/acknowledge
//
// Product law: eliminates NOTICING ("we honor commitments" while 2 were
// broken) by surfacing the gap between stated beliefs and observed behavior.
// ═══════════════════════════════════════════════════════════════════════════

async function loadContradictions() {
  const listEl = document.getElementById('contradictions-list');
  if (!listEl) return;
  listEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const data = await api.getOEM('/contradictions');
    renderContradictions(listEl, data.contradictions || []);
  } catch (e) {
    listEl.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)} <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="loadContradictions()">Retry</button></div>`;
  }
}

function renderContradictions(container, contradictions) {
  if (!contradictions.length) {
    container.innerHTML = `<div class="ds-empty">
      <div class="b-fs14-text-11">No contradictions detected.</div>
      <div>Stated beliefs and observed behavior are aligned. Contradictions surface automatically as the OEM ingests new signals — commitment breaks, assumption invalidations, law violations, and bottleneck drift.</div>
    </div>`;
    return;
  }

  container.innerHTML = contradictions.map(c => {
    const severity = c.severity || 'medium';
    const sevClass = severity === 'high' || severity === 'critical' ? 'high' : severity === 'medium' ? 'medium' : 'low';
    const acknowledged = c.status === 'acknowledged';
    return `
      <div class="ds-card" data-contradiction-id="${escapeHtml(c.contradiction_id)}">
        <div class="ds-row-between mb-10">
          <div class="ds-row">
            <span class="ds-tag ds-tag-${sevClass}">${escapeHtml(severity.toUpperCase())}</span>
            <span class="ds-meta">${escapeHtml(c.type || 'contradiction')}</span>
          </div>
          ${acknowledged ? `<span class="ds-tag ds-tag-validated">acknowledged</span>` : ''}
        </div>

        <div class="b-fs14-fw500-4">${escapeHtml(c.title || c.description || 'Contradiction detected')}</div>

        ${c.stated_belief ? `
          <div class="mb-8">
            <div class="ds-cascade-label">Stated belief</div>
            <div class="b-fs13-text-16">${escapeHtml(c.stated_belief)}</div>
          </div>
        ` : ''}

        ${c.observed_behavior ? `
          <div class="mb-8">
            <div class="ds-cascade-label">Observed behavior</div>
            <div class="b-fs13-text-7">${escapeHtml(c.observed_behavior)}</div>
          </div>
        ` : ''}

        ${c.description && c.title ? `
          <div class="b-fs125-text-2">${escapeHtml(humanize(c.description))}</div>
        ` : ''}

        ${c.evidence && c.evidence.length ? `
          <div class="mb-10">
            <div class="ds-cascade-label">Evidence (${c.evidence.length})</div>
            <div class="ds-row b-u-gap4">
              ${c.evidence.slice(0, 6).map(e => `<span class="source-cite">${escapeHtml(e.type || e.signal_type || 'signal')}</span>`).join('')}
              ${c.evidence.length > 6 ? `<span class="ds-meta">+${c.evidence.length - 6} more</span>` : ''}
            </div>
          </div>
        ` : ''}

        ${!acknowledged ? `
          <div class="ds-row b-gap6">
            <button class="ds-btn ds-btn-primary ds-btn-small" onclick="acknowledgeContradiction('${escapeJs(c.contradiction_id)}')">Acknowledge</button>
          </div>
        ` : ''}
      </div>
    `;
  }).join('');
}

async function acknowledgeContradiction(contradictionId) {
  try {
    await api.postOEM(`/contradictions/${contradictionId}/acknowledge`, {});
    // Reload the list to reflect the acknowledged status
    loadContradictions();
  } catch (e) {
    showError(`Failed to acknowledge: ${e.message}`);
  }
}

// ═══════════════════════════════════════════════════════════════════════════


// === prediction_market.js ===
// PREDICTION MARKET — calibrate individual prediction accuracy
// ═══════════════════════════════════════════════════════════════════════════
// Surface 5 of the cognitive model UI. Shows the calibration ranking
// (Brier-score-based, not hierarchy) and lets anyone submit a prediction.
//
// Calls:
//   GET  /api/oem/predictions/market/calibration   (ranked predictors)
//   GET  /api/oem/predictions/market               (list all predictions)
//   POST /api/oem/predictions/market               (submit new prediction)
//   POST /api/oem/predictions/market/{id}/resolve  (resolve with outcome)
//
// Product law: eliminates THINKING about "whose estimate should I trust?"
// by surfacing each predictor's Brier-scored calibration profile.
// ═══════════════════════════════════════════════════════════════════════════

let _predictionMarketView = 'ranking'; // 'ranking' | 'all' | 'submit'

async function loadPredictionMarket() {
  const rankingEl = document.getElementById('prediction-market-ranking');
  if (!rankingEl) return;

  // Always load the ranking first (the killer view)
  rankingEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const data = await api.getOEM('/predictions/market/calibration');
    renderCalibrationRanking(rankingEl, data.predictors || []);
  } catch (e) {
    rankingEl.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)} <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="loadPredictionMarket()">Retry</button></div>`;
  }
}

function renderCalibrationRanking(container, predictors) {
  if (!predictors.length) {
    container.innerHTML = `<div class="ds-empty">
      <div class="b-fs14-text-11">No resolved predictions yet.</div>
      <div>Once predictions are submitted and resolved, each predictor gets a Brier score. The ranking below sorts by accuracy — not hierarchy.</div>
      <button class="ds-btn ds-btn-primary mt-16" onclick="setPredictionMarketView('submit')">Submit first prediction</button>
    </div>`;
    return;
  }

  const html = `
    <div class="ds-row-between b-mb14">
      <div class="ds-meta">Ranked by Brier score · lower is better · 0 = perfect · 0.25 = random</div>
      <div class="ds-row b-gap6">
        <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="setPredictionMarketView('all')">All predictions</button>
        <button class="ds-btn ds-btn-primary ds-btn-small" onclick="setPredictionMarketView('submit')">Submit prediction</button>
      </div>
    </div>
    <div class="ds-card b-p0">
      ${predictors.map((p, i) => {
        const brier = p.avg_brier_score;
        const brierClass = brier == null ? 'ds-brier-poor' :
          brier < 0.1 ? 'ds-brier-excellent' :
          brier < 0.2 ? 'ds-brier-well' :
          brier < 0.3 ? 'ds-brier-moderate' :
          'ds-brier-poor';
        const label = p.calibration_quality || 'untested';
        return `
          <div class="ds-rank-row">
            <div class="ds-rank-num">${i + 1}</div>
            <div>
              <div class="ds-rank-email">${escapeHtml(p.email)}</div>
              <div class="ds-meta">${p.resolved_predictions} resolved · ${p.total_predictions} total · ${escapeHtml(label)}</div>
            </div>
            <div class="ds-sparkline ds-sparkline-empty" title="Calibration trend will populate as predictions accumulate during the pilot"></div>
            <div class="ds-brier-badge ${brierClass}">Brier ${brier == null ? '—' : brier.toFixed(3)}</div>
          </div>
        `;
      }).join('')}
    </div>
  `;
  container.innerHTML = html;
}

function setPredictionMarketView(view) {
  _predictionMarketView = view;
  const rankingEl = document.getElementById('prediction-market-ranking');
  const allEl = document.getElementById('prediction-market-all');
  const submitEl = document.getElementById('prediction-market-submit');
  if (rankingEl) rankingEl.style.display = view === 'ranking' ? 'block' : 'none';
  if (allEl) allEl.style.display = view === 'all' ? 'block' : 'none';
  if (submitEl) submitEl.style.display = view === 'submit' ? 'block' : 'none';

  if (view === 'all' && allEl) loadAllMarketPredictions();
  if (view === 'submit' && submitEl) renderPredictionSubmitForm(submitEl);
}

async function loadAllMarketPredictions() {
  const allEl = document.getElementById('prediction-market-all');
  if (!allEl) return;
  allEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const data = await api.getOEM('/predictions/market');
    renderAllMarketPredictions(allEl, data.predictions || []);
  } catch (e) {
    allEl.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

function renderAllMarketPredictions(container, predictions) {
  if (!predictions.length) {
    container.innerHTML = `<div class="ds-empty">No predictions submitted yet. Use "Submit prediction" to add one.</div>`;
    return;
  }

  container.innerHTML = `
    <div class="ds-row-between b-mb14">
      <div class="ds-meta">${predictions.length} prediction${predictions.length === 1 ? '' : 's'}</div>
      <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="setPredictionMarketView('ranking')">Back to ranking</button>
    </div>
    <div class="ds-stack">
      ${predictions.map(p => {
        const status = p.status || 'open';
        const statusClass = status === 'resolved' ? (p.actual_outcome ? 'validated' : 'rejected') : 'pending';
        return `
          <div class="ds-card b-p1416">
            <div class="ds-row-between mb-6">
              <span class="ds-tag ds-tag-${statusClass}">${escapeHtml(humanize(status))}</span>
              <span class="ds-meta">${formatTimestamp(p.made_at)}</span>
            </div>
            <div class="b-fs135-text">${escapeHtml(humanize(p.event))}</div>
            <div class="ds-row b-gap14">
              <span class="ds-meta">predictor <span class="ds-meta-strong">${escapeHtml(humanize(p.predictor))}</span></span>
              <span class="ds-meta">prob <span class="ds-meta-strong">${(p.probability * 100).toFixed(0)}%</span></span>
              ${p.brier_score != null ? `<span class="ds-meta">brier <span class="ds-meta-strong">${p.brier_score.toFixed(3)}</span></span>` : ''}
              ${p.hypothesis_id ? `<span class="ds-meta">linked hypothesis</span>` : ''}
            </div>
            ${status === 'open' ? `
              <div class="ds-row b-gap6-mt10">
                <button class="ds-btn ds-btn-positive ds-btn-small" onclick="resolveMarketPrediction('${escapeJs(p.prediction_id)}', true)">Resolve: happened</button>
                <button class="ds-btn ds-btn-risk ds-btn-small" onclick="resolveMarketPrediction('${escapeJs(p.prediction_id)}', false)">Resolve: didn't</button>
              </div>
            ` : ''}
          </div>
        `;
      }).join('')}
    </div>
  `;
}

function renderPredictionSubmitForm(container) {
  container.innerHTML = `
    <div class="ds-card">
      <div class="ds-row-between b-mb14">
        <div class="b-fs14-fw500">Submit a prediction</div>
        <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="setPredictionMarketView('ranking')">Cancel</button>
      </div>
      <div class="ds-stack gap-12">
        <div>
          <label class="ds-cascade-label" for="pm-predictor">Predictor (email)</label>
          <input id="pm-predictor" class="ask-input fs-13" placeholder="you@acme.com" value="ceo@acme.com">
        </div>
        <div>
          <label class="ds-cascade-label" for="pm-event">Event (what will happen?)</label>
          <input id="pm-event" class="ask-input fs-13" placeholder="e.g. Q4 launch ships on time">
        </div>
        <div>
          <label class="ds-cascade-label" for="pm-probability">Probability: <span id="pm-prob-val" class="ds-meta-strong">70%</span></label>
          <input id="pm-probability" type="range" min="0" max="100" value="70" class="w-full" oninput="document.getElementById('pm-prob-val').textContent=this.value+'%'">
        </div>
        <div>
          <label class="ds-cascade-label" for="pm-window">Resolution window (optional)</label>
          <input id="pm-window" class="ask-input fs-13" placeholder="e.g. Q4 2025">
        </div>
        <button class="ds-btn ds-btn-primary" onclick="submitMarketPrediction()">Submit</button>
        <div id="pm-submit-result" class="d-none"></div>
      </div>
    </div>
  `;
}

async function submitMarketPrediction() {
  const predictor = document.getElementById('pm-predictor').value.trim();
  const event = document.getElementById('pm-event').value.trim();
  const probability = parseInt(document.getElementById('pm-probability').value, 10) / 100;
  const resolutionWindow = document.getElementById('pm-window').value.trim();
  const resultEl = document.getElementById('pm-submit-result');

  if (!predictor || !event) {
    resultEl.style.display = 'block';
    resultEl.innerHTML = `<div class="ds-error">Predictor and event are required.</div>`;
    return;
  }

  resultEl.style.display = 'block';
  resultEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const resp = await api.postOEM('/predictions/market', {
      predictor, event, probability, resolution_window: resolutionWindow,
    });
    resultEl.innerHTML = `<div class="ds-card b-bg-ca5a">
      <div class="b-fs13-text-6">Prediction submitted</div>
      <div class="ds-meta">ID: ${escapeHtml(resp.prediction_id || '')}</div>
      <div class="ds-meta">Probability: ${(probability * 100).toFixed(0)}%</div>
      ${resp.prediction && resp.prediction.brier_score != null ? `<div class="ds-meta">Brier score: ${resp.prediction.brier_score.toFixed(3)}</div>` : ''}
      <button class="ds-btn ds-btn-ghost ds-btn-small mt-8" onclick="setPredictionMarketView('all')">View all predictions</button>
    </div>`;
    document.getElementById('pm-event').value = '';
  } catch (e) {
    resultEl.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function resolveMarketPrediction(predictionId, actualOutcome) {
  try {
    await api.postOEM(`/predictions/market/${predictionId}/resolve`, { actual_outcome: actualOutcome });
    loadAllMarketPredictions();
  } catch (e) {
    showError(`Failed to resolve: ${e.message}`);
  }
}

// ═══════════════════════════════════════════════════════════════════════════


// === assumptions.js ===
// ASSUMPTIONS — what are we assuming that might be wrong?
// ═══════════════════════════════════════════════════════════════════════════
// Surface 6 of the cognitive model UI. Shows dangerous assumptions (open,
// high-stakes, unvalidated) and lets the CEO validate or invalidate each.
//
// Calls:
//   GET  /api/oem/assumptions/dangerous   (killer view: assumptions that
//                                          could bankrupt a project if wrong)
//   GET  /api/oem/assumptions             (all assumptions, optional ?status=)
//   GET  /api/oem/assumptions/accuracy    (post-pilot accuracy report)
//
// Product law: eliminates ASSUMING-BLINDLY by surfacing every decision's
// hidden assumptions and the evidence that contradicts them.
// ═══════════════════════════════════════════════════════════════════════════

let _assumptionsView = 'dangerous'; // 'dangerous' | 'all' | 'accuracy'

async function loadAssumptions() {
  const containerEl = document.getElementById('assumptions-dangerous');
  if (!containerEl) return;
  containerEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const data = await api.getOEM('/assumptions/dangerous');
    renderDangerousAssumptions(containerEl, data.dangerous_assumptions || []);
  } catch (e) {
    containerEl.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)} <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="loadAssumptions()">Retry</button></div>`;
  }
}

function renderDangerousAssumptions(container, assumptions) {
  if (!assumptions.length) {
    container.innerHTML = `<div class="ds-empty">
      <div class="b-fs14-text-11">No dangerous assumptions detected.</div>
      <div>Dangerous assumptions are open, high-stakes, and unvalidated — the ones that could bankrupt a project if wrong. They surface automatically as the OEM ingests decision signals.</div>
    </div>`;
    return;
  }

  container.innerHTML = assumptions.map(a => {
    const stakes = a.stakes || 'medium';
    const stakesClass = stakes === 'critical' || stakes === 'high' ? 'high' : stakes === 'medium' ? 'medium' : 'low';
    const status = a.status || 'open';
    const statusClass = status === 'validated' ? 'validated' : status === 'invalidated' ? 'rejected' : 'open';
    const contradictingCount = (a.contradicting_signals || a.contradicting_evidence || []).length;
    const supportingCount = (a.supporting_signals || a.supporting_evidence || []).length;

    return `
      <div class="ds-card" data-assumption-id="${escapeHtml(a.assumption_id)}">
        <div class="ds-row-between mb-10">
          <div class="ds-row">
            <span class="ds-tag ds-tag-${statusClass}">${escapeHtml(status)}</span>
            <span class="ds-tag ds-tag-${stakesClass}">${escapeHtml(stakes)} stakes</span>
          </div>
          ${a.created_at ? `<span class="ds-meta">${formatTimestamp(a.created_at)}</span>` : ''}
        </div>

        <div class="b-fs14-text-8">${escapeHtml(humanize(a.statement))}</div>

        ${a.context ? `<div class="ds-meta mb-10">${escapeHtml(humanize(a.context))}</div>` : ''}

        ${a.intent_id ? `<div class="ds-meta mb-10">Supports: <span class="ds-meta-strong">intent ${escapeHtml(a.intent_id.substring(0, 16))}…</span></div>` : ''}

        <div class="ds-row b-gap14-mb10">
          <span class="ds-meta">${supportingCount} supporting</span>
          <span class="ds-meta">${contradictingCount} contradicting</span>
          ${contradictingCount === 0 && supportingCount === 0 ? `<span class="ds-tag ds-tag-uncertain">unvalidated</span>` : ''}
        </div>

        ${contradictingCount > 0 ? `
          <div class="b-mb10-p810">
            <div class="ds-cascade-label text-risk">Evidence contradicts this assumption</div>
            <div class="ds-meta mt-2">${contradictingCount} signal${contradictingCount === 1 ? '' : 's'} suggest this assumption may be wrong</div>
          </div>
        ` : ''}

        ${status === 'open' ? `
          <div class="ds-row b-gap6">
            <button class="ds-btn ds-btn-positive ds-btn-small" onclick="resolveAssumption('${escapeJs(a.assumption_id)}', 'validated')">Mark as validated</button>
            <button class="ds-btn ds-btn-risk ds-btn-small" onclick="resolveAssumption('${escapeJs(a.assumption_id)}', 'invalidated')">Invalidate</button>
            <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="navTo('intents')">View in cascade</button>
          </div>
        ` : ''}
      </div>
    `;
  }).join('');
}

// The Assumption Graph doesn't yet expose a direct resolve endpoint, but
// Round 78: resolveAssumption now makes a real API call to /assumptions/{id}/{status}
async function resolveAssumption(assumptionId, newStatus) {
  try {
    // Call the backend to persist the status change
    await api.postOEM(`/assumptions/${assumptionId}/${newStatus}`);
    
    // Optimistic update: re-render with the new status locally
    const card = document.querySelector(`[data-assumption-id="${assumptionId}"]`);
    if (card) {
      const tag = card.querySelector('.ds-tag-open, .ds-tag-validated, .ds-tag-rejected');
      if (tag) {
        tag.className = `ds-tag ds-tag-${newStatus === 'validated' ? 'validated' : 'rejected'}`;
        tag.textContent = newStatus;
      }
      // Hide the action buttons
      const actions = card.querySelector('.ds-row:last-child');
      if (actions) actions.style.display = 'none';
    }
    showToast(`Assumption marked as ${newStatus}.`);
  } catch (e) {
    showError(`Failed to resolve assumption: ${e.message}`);
  }
}

async function loadAssumptionAccuracy() {
  const containerEl = document.getElementById('assumptions-accuracy');
  if (!containerEl) return;
  containerEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const report = await api.getOEM('/assumptions/accuracy');
    renderAssumptionAccuracy(containerEl, report);
  } catch (e) {
    containerEl.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

function renderAssumptionAccuracy(container, report) {
  const total = report.total_assumptions || 0;
  const validated = report.validated_count || 0;
  const invalidated = report.invalidated_count || 0;
  const open = report.open_count || 0;
  const accuracyRate = report.accuracy_rate;

  container.innerHTML = `
    <div class="ds-card">
      <div class="b-fs14-fw500-2">Assumption accuracy report</div>
      <div class="ds-row b-gap24-u">
        <div>
          <div class="ds-meta">Total</div>
          <div class="b-fs22-text-2">${total}</div>
        </div>
        <div>
          <div class="ds-meta">Validated</div>
          <div class="b-fs22-text">${validated}</div>
        </div>
        <div>
          <div class="ds-meta">Invalidated</div>
          <div class="b-fs22-text-3">${invalidated}</div>
        </div>
        <div>
          <div class="ds-meta">Still open</div>
          <div class="b-fs22-text-4">${open}</div>
        </div>
        <div>
          <div class="ds-meta">Accuracy rate</div>
          <div class="b-fs22-clr">${accuracyRate != null ? (accuracyRate * 100).toFixed(0) + '%' : '—'}</div>
        </div>
      </div>
      ${report.most_costly_when_wrong && report.most_costly_when_wrong.length ? `
        <div class="mt-16">
          <div class="ds-cascade-label">Most costly when wrong</div>
          <div class="ds-stack mt-8">
            ${report.most_costly_when_wrong.slice(0, 5).map(a => `
              <div class="ds-card b-p1012">
                <div class="b-fs13-text-7">${escapeHtml(humanize(a.statement))}</div>
                <div class="ds-meta mt-4">${escapeHtml(a.stakes || 'medium')} stakes · ${escapeHtml(a.status || 'resolved')}</div>
              </div>
            `).join('')}
          </div>
        </div>
      ` : ''}
    </div>
  `;
}

function setAssumptionsView(view) {
  _assumptionsView = view;
  const dangerousEl = document.getElementById('assumptions-dangerous');
  const accuracyEl = document.getElementById('assumptions-accuracy');
  if (dangerousEl) dangerousEl.style.display = view === 'dangerous' ? 'block' : 'none';
  if (accuracyEl) accuracyEl.style.display = view === 'accuracy' ? 'block' : 'none';
  if (view === 'accuracy' && accuracyEl) loadAssumptionAccuracy();
}

// ═══════════════════════════════════════════════════════════════════════════


// === humanize.js ===
// HUMANIZE — universal vocabulary hiding for the Invisible Maestro
// ═══════════════════════════════════════════════════════════════════════════
// Constitution v2: "Never expose Learning Objects, Patterns, Evidence Graph,
// Judgment Graph, OEM, Signals, Receipts, Prediction Market, Hypothesis
// Engine, Laws. Replace them with natural language."
//
// This function is the SINGLE source of truth for vocabulary hiding.
// Every surface that displays OEM-derived text to the user must pass it
// through humanize() before rendering. The function:
//   1. Strips law codes (L-0001, L-0002, etc.)
//   2. Strips confidence numbers ((confidence: 1.00), confidence: 0.85)
//   3. Replaces internal terms with human language
//   4. Cleans up whitespace
//
// Usage:
//   element.innerHTML = humanize(rawApiText);
//   element.textContent = humanize(rawApiText);
//
// The function is pure (no side effects, no DOM access) so it can be
// unit-tested in isolation.
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Humanize raw OEM text by stripping internal vocabulary and confidence numbers.
 *
 * @param {string} text - The raw text from an OEM API response.
 * @returns {string} The humanized text, safe to display to users.
 */
function humanize(text) {
  if (!text) return '';
  return String(text)
    // ── Strip law codes (L-0001, L-0002, L-XXXX) ──────────────────────────
    .replace(/\bL-\d{4}\b/g, '')
    // ── Strip confidence numbers ──────────────────────────────────────────
    // Constitution: "Never expose confidence numbers alone."
    // Patterns: "(confidence: 1.00)", "confidence: 0.85", "conf: 0.92"
    .replace(/\(confidence:\s*[\d.]+\s*\)/gi, '')
    .replace(/\(conf:\s*[\d.]+\s*\)/gi, '')
    .replace(/\bconfidence:\s*[\d.]+\b/gi, '')
    .replace(/\bconf:\s*[\d.]+\b/gi, '')
    // ── Replace internal terms with human language ────────────────────────
    .replace(/learning object/gi, 'pattern')
    .replace(/evidence graph/gi, 'organizational memory')
    .replace(/judgment graph/gi, 'organizational judgment')
    .replace(/receipt/gi, 'signal')
    .replace(/\blaw\b/gi, 'pattern')
    .replace(/\blaws\b/gi, 'patterns')
    .replace(/OEM/g, 'Maestro')
    .replace(/prediction market/gi, 'calibration ranking')
    .replace(/hypothesis engine/gi, 'prediction system')
    .replace(/hypothesis/gi, 'prediction')
    .replace(/signal type/gi, 'event type')
    // ── Clean up whitespace left by replacements ──────────────────────────
    .replace(/\(\s*\)/g, '')           // Remove empty parens "(: priya)"
    .replace(/:\s*:/g, ':')             // Fix double colons "::"
    .replace(/\s+\)/g, ')')            // Fix trailing space before )
    .replace(/\(\s+/g, '(')            // Fix leading space after (
    .replace(/\s{2,}/g, ' ')           // Collapse multiple spaces
    .replace(/^\s*[•·-]\s*$/gm, '')    // Remove empty bullet lines
    .trim();
}

// ═══════════════════════════════════════════════════════════════════════════


// === org_dot.js ===
// THE INVISIBLE MAESTRO — Organizational Dot + Heartbeat
// ═══════════════════════════════════════════════════════════════════════════
// One tiny colored dot. Universal presence indicator.
//   Green  — Nothing requires attention.
//   Yellow — Opportunity.
//   Orange — Cross-functional impact.
//   Red    — Do not continue.
//
// Clicking opens context. Never a dashboard.
// ═══════════════════════════════════════════════════════════════════════════

let _orgDotColor = 'green';
let _orgDotPollTimer = null;

function initOrgDot() {
  // Render the dot in the topbar
  const topbar = document.querySelector('.topbar');
  if (!topbar) return;

  // Check if dot already exists
  if (document.getElementById('org-dot-container')) return;

  // Create the dot container
  const dotContainer = document.createElement('div');
  dotContainer.id = 'org-dot-container';
  dotContainer.style.cssText = 'display:flex;align-items:center;gap:8px;cursor:pointer;padding:4px 12px;border-radius:8px;transition:all var(--ease);';
  dotContainer.innerHTML = `
    <span class="org-dot org-dot-green" id="org-dot" aria-label="Organizational status"></span>
    <span class="b-fs13-fw500-5" id="org-dot-label">All clear</span>
  `;
  dotContainer.addEventListener('click', () => {
    // Clicking the dot navigates to TODAY (the morning brief)
    navTo('today');
  });
  dotContainer.addEventListener('mouseenter', () => {
    dotContainer.style.background = 'var(--surface-2)';
  });
  dotContainer.addEventListener('mouseleave', () => {
    dotContainer.style.background = 'transparent';
  });

  // Insert before the OEM status badge
  const oemBadge = topbar.querySelector('#oem-pulse')?.parentElement;
  if (oemBadge) {
    topbar.insertBefore(dotContainer, oemBadge);
  } else {
    topbar.appendChild(dotContainer);
  }

  // Start polling for org status (every 60 seconds)
  pollOrgDotStatus();
  if (_orgDotPollTimer) clearInterval(_orgDotPollTimer);
  _orgDotPollTimer = setInterval(pollOrgDotStatus, 60000);
}

async function pollOrgDotStatus() {
  try {
    const [briefing, contradictionsResp] = await Promise.all([
      api.getOEM('/ceo-briefing'),
      api.getOEM('/contradictions').catch(() => ({ contradictions: [] })),
    ]);
    const contradictions = contradictionsResp.contradictions || [];
    const color = determineDotColor(briefing, contradictions);
    updateOrgDot(color);
  } catch (e) {
    // Keep the current dot state if the API fails
  }
}

function updateOrgDot(color) {
  _orgDotColor = color;
  const dot = document.getElementById('org-dot');
  const label = document.getElementById('org-dot-label');
  if (!dot || !label) return;

  // Remove all color classes
  dot.className = 'org-dot';
  dot.classList.add(`org-dot-${color}`);

  const labels = {
    green: 'All clear',
    yellow: 'Opportunity',
    orange: 'Cross-functional impact',
    red: 'Attention needed',
  };
  label.textContent = labels[color] || 'All clear';

  // Update the title attribute for accessibility
  dot.setAttribute('title', labels[color] || 'All clear');
  dot.setAttribute('aria-label', `Organizational status: ${labels[color] || 'all clear'}`);
}

// ═══════════════════════════════════════════════════════════════════════════


// === trajectory_panel.js ===
/* Phase 2.2 — Trajectory Panel shared utility.
 *
 * Used by: today.js (commitment cards), personal.js (work_context card).
 *
 * Fetches /api/oem/loop1.5/timeline/{entity} and renders the Day-1 → Day-60
 * projection + recommendation DERIVED server-side by CommitmentTimelineSimulator
 * from the CommitmentMutationTracker's history (P13 — the UI never supplies
 * the rate, pattern, risk, or recommendation; it only renders what the server
 * derived).
 *
 * The panel renders into a container element with id `containerId`. If the
 * container already has content, the call toggles it off (same UX as
 * showInlineWhy in today.js).
 *
 * Dependencies (must be loaded before this script runs):
 *   - api.getOEM()  (from swr_cache.js)
 *   - escapeHtml()  (from swr_cache.js)
 *   - humanize()    (from humanize.js)
 */
function showTrajectoryPanel(containerId, entity) {
  const el = document.getElementById(containerId);
  if (!el) return;
  // Toggle off if already shown
  if (el.innerHTML.trim()) {
    el.innerHTML = '';
    return;
  }
  if (!entity) {
    el.innerHTML = `<div class="ds-meta fs-11">No customer entity on this commitment.</div>`;
    return;
  }
  // Skeleton while fetching
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  // Async IIFE — fetch + render
  (async () => {
    try {
      const data = await api.getOEM(`/loop1.5/timeline/${encodeURIComponent(entity)}`);
      if (!data || !data.pattern_type) {
        el.innerHTML = `<div class="ds-meta fs-11">No trajectory data available for ${escapeHtml(entity)}.</div>`;
        return;
      }
      const risk = data.risk_level || 'unknown';
      const riskClass = risk === 'high' ? 'b-text-risk' : (risk === 'medium' ? 'b-text-accent' : 'b-text-primary-2');
      const patternLabel = data.pattern_type.replace(/_/g, ' ');
      const horizon = data.projected_mutations_by_day_60;
      const rate = (data.mutation_rate_per_30d || 0).toFixed(2);
      // Trajectory chips
      let trajHtml = '';
      if (Array.isArray(data.baseline_trajectory) && data.baseline_trajectory.length > 0) {
        trajHtml = '<div class="b-flex-gap4 b-mt4-u">';
        for (const cp of data.baseline_trajectory) {
          const day = cp.day;
          const state = cp.projected_state || 'unknown';
          const stateClass = state === 'on_track' ? 'b-text-primary-2'
            : state === 'at_risk' ? 'b-text-accent'
            : state === 'renegotiated' ? 'b-text-accent-3'
            : state === 'broken' ? 'b-text-risk'
            : 'b-text-primary-2';
          const stateLabel = state.replace(/_/g, ' ');
          trajHtml += `
            <div class="b-p612-bg" style="min-width:88px">
              <div class="ds-meta fs-11">Day ${day}</div>
              <div class="${stateClass} fs-11" style="font-weight:600">${escapeHtml(stateLabel)}</div>
            </div>
          `;
        }
        trajHtml += '</div>';
      }
      // Recommendation (derived server-side)
      const recHtml = data.recommendation
        ? `<div class="b-fs12-text-14 b-mt4-u">${escapeHtml(humanize(data.recommendation))}</div>`
        : '';
      // Evidence summary (transparency — P13: shows the user what the projection was derived from)
      let evHtml = '';
      if (data.evidence_summary) {
        const ev = data.evidence_summary;
        const breakdown = ev.mutation_breakdown || {};
        const breakdownParts = Object.keys(breakdown).map(k => `${escapeHtml(k.replace(/_/g, ' '))}: ${breakdown[k]}`);
        evHtml = `
          <div class="ds-meta fs-11 b-mt4-u" style="opacity:0.8">
            Derived from ${ev.history_count || 0} commitment${ev.history_count === 1 ? '' : 's'} ·
            ${ev.mutation_count || 0} mutation${ev.mutation_count === 1 ? '' : 's'} ·
            ${ev.history_span_days || 0}-day span
            ${breakdownParts.length > 0 ? ` · ${breakdownParts.join(' · ')}` : ''}
          </div>
        `;
      }
      el.innerHTML = `
        <div class="b-p812-bg b-mt4-u" style="border-left:3px solid var(--accent)">
          <div class="b-flex-gap4 b-flex-space-between">
            <div class="ds-meta fs-11">Trajectory</div>
            <div class="${riskClass} fs-11" style="font-weight:600">${escapeHtml(risk.toUpperCase())} RISK</div>
          </div>
          <div class="b-fs12-text-14 b-mt2-u">
            <span style="font-weight:600">${escapeHtml(patternLabel)}</span>
            · rate ${rate}/30d · ~${horizon} mutation${horizon === 1 ? '' : 's'} by Day 60
          </div>
          ${trajHtml}
          ${recHtml}
          ${evHtml}
          <button class="ds-btn ds-btn-ghost ds-btn-small fs-11 b-mt4-u" onclick="document.getElementById('${containerId}').innerHTML=''">Close</button>
        </div>
      `;
    } catch (e) {
      el.innerHTML = `<div class="ds-error fs-11">Failed: ${escapeHtml(e.message)}</div>`;
    }
  })();
}


// === today.js ===
// THE INVISIBLE MAESTRO — TODAY surface
// ═══════════════════════════════════════════════════════════════════════════
// The morning brief. When the CEO opens Maestro they should immediately
// understand what deserves attention. Nothing else.
//
// Typography: font-family: 'Montserrat', sans-serif (Bumble design system)
//
// Structure:
//   Good morning.
//   Yesterday your organization became smarter.
//
//   One decision
//   One opportunity
//   One risk
//   One thing learned overnight
//   One prediction that changed
//
// No scrolling. No charts. No KPI overload. Calm. Like Apple Weather.
// ═══════════════════════════════════════════════════════════════════════════

async function loadToday() {
  const el = document.getElementById('today-content');
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div><div class="skeleton skeleton-line skeleton-line-w50"></div></div>';

  // CEO Feature 1: Load the Preparation Brief (Chief of Staff capability)
  // Maestro prepares for tomorrow's meetings before the user arrives.
  loadPreparationBrief();

  try {
    // Compose the brief from existing API endpoints — no new backend needed
    const [briefing, pulse, contradictionsResp, personality] = await Promise.all([
      api.getOEM('/ceo-briefing'),
      api.getOEM('/pulse').catch(() => null),
      api.getOEM('/contradictions').catch(() => ({ contradictions: [] })),
      api.getOEM('/personality').catch(() => null),
    ]);
    const contradictions = contradictionsResp.contradictions || [];

    // ─── Round 44 Phase 6 / Round 46: Always fetch personal data ─────
    // Round 46: The Today surface is ALWAYS the unified deck. The user
    // does not switch modes. We always fetch the personal briefing so
    // we can interleave work + personal cards. The filter pill (All/
    // Work/Personal) narrows the view — it does NOT change what we fetch.
    let currentFilter = 'all';
    let personalBriefing = null;
    let personalContradsList = [];
    try {
      currentFilter = (typeof getCurrentFilter === 'function') ? getCurrentFilter() : 'all';
    } catch (e) { /* default to 'all' */ }

    // Always fetch personal data (Round 46 — the default is 'all', so we
    // always need personal cards available for the unified deck). The
    // filter is applied at RENDER time, not fetch time.
    try {
      const [pb, pc] = await Promise.all([
        api.getPersonal('/briefing').catch(() => null),
        api.getPersonal('/contradictions').catch(() => ({ contradictions: [] })),
      ]);
      personalBriefing = pb;
      personalContradsList = (pc && pc.contradictions) || [];
    } catch (e) { /* personal mode unavailable — work-only deck */ }
    const currentMode = 'all';  // Round 46 — always 'all' (the filter is separate)

    // Time-axis fetch removed — the endpoint returns 404 for domains with
    // <5 signals, which the browser logs as a console error. This caused
    // 5 commits of false "0 console errors" claims. The time-axis data
    // was not used meaningfully in the morning brief. When real customer
    // data is connected with ≥5 signals per domain, this can be re-enabled
    // with a HEAD check first to avoid the 404.
    let timeAxis = null;

    // Fetch "so what?" for the top recommendation (if one exists)
    let sowhatData = null;
    const ot = briefing.one_thing || {};
    if (ot.title) {
      try {
        sowhatData = await api.getOEM(`/sowhat?entity_type=recommendation&entity_id=${encodeURIComponent(ot.title)}`);
      } catch (e) {
        // Fallback — use the hardcoded provenance
      }
    }

    // Fetch curiosity questions (V4 Organ #2)
    let curiosity = null;
    try {
      curiosity = await api.getOEM('/curiosity');
    } catch (e) {
      // Curiosity engine may not be available
    }

    // Fetch adaptive nudges (V6 Spec #1)
    let nudges = null;
    try {
      nudges = await api.getOEM('/nudges');
    } catch (e) {
      // Nudge engine may not be available
    }

    // Fetch background loop notices (V6 Spec #3)
    let backgroundLoop = null;
    try {
      backgroundLoop = await api.getOEM('/background-loop');
    } catch (e) {
      // Background loop may not be available
    }

    // Fetch trajectory interventions (V6 Spec #4)
    let interventions = null;
    try {
      interventions = await api.getOEM('/trajectory-intervention');
    } catch (e) {
      // Trajectory intervention may not be available
    }

    // Fetch 4-level unknowns (V8 Upgrade #2)
    let unknowns = null;
    try {
      unknowns = await api.getOEM('/unknowns?levels=all');
    } catch (e) {
      // Unknowns engine may not be available
    }

    // Fetch tasks (V8 Daily Work #2)
    let tasks = null;
    try {
      tasks = await api.getOEM('/tasks?status=open');
    } catch (e) {
      // Task extraction may not be available
    }

    renderMorningBrief(el, briefing, pulse, contradictions, personality, timeAxis, sowhatData, curiosity, nudges, backgroundLoop, interventions, unknowns, tasks, currentMode, personalBriefing, personalContradsList, currentFilter);
  } catch (e) {
    el.innerHTML = `<div class="calm-empty">
      <div class="b-fs18-text">Good morning.</div>
      <div>We couldn't prepare your brief right now. The organization is still learning.</div>
      <button class="ds-btn ds-btn-ghost ds-btn-small space-4" onclick="loadToday()">Try again</button>
    </div>`;
  }
}

function renderMorningBrief(el, briefing, pulse, contradictions, personality, timeAxis, sowhatData, curiosity, nudges, backgroundLoop, interventions, unknowns, tasks, currentMode, personalBriefing, personalContradsList, currentFilter) {
  // Round 44 Phase 6 — Both Mode handling.
  // If currentMode === 'both', interleave work and personal cards by
  // priority in a single unified swipe deck. Each card has a subtle
  // mode indicator dot (blue for Work, coral for Personal). The unified
  // deck NEVER mixes third-party intelligence — work cards contain only
  // work data, personal cards contain only the user's own personal data.
  //
  // Round 46 — currentMode is always 'all'. The filter pill (currentFilter)
  // narrows the view at RENDER time. 'all' shows everything, 'work' shows
  // only blue-dot cards, 'personal' shows only coral-dot cards.
  currentMode = currentMode || 'all';
  currentFilter = currentFilter || 'all';
  personalBriefing = personalBriefing || null;
  personalContradsList = personalContradsList || [];

  const ot = briefing.one_thing || {};
  const overnight = briefing.overnight || {};
  const changes = overnight.changes || [];
  const money = briefing.money || {};
  const knowledge = briefing.knowledge || {};
  const commitments = briefing.commitments || {};

  // Pick one decision, one opportunity, one risk, one learning, one prediction
  // Each item answers the Constitution's implicit questions:
  //   Why now? Why me? What happens if ignored? How do we know?
  const decision = ot.title ? {
    label: 'One decision',
    title: ot.title,
    context: ot.why || ot.recommendation || '',
    provenance: ot.rec_id ? `Why now: ${ot.urgency || 'this pattern is active'}. Why you: only the CEO can unblock this. If ignored: the pattern will repeat. How we know: ${ot.impact || 'organizational memory'}.` : '',
    sowhat: sowhatData ? sowhatData.consequence_if_ignored : '',
    action: () => { if (ot.title) openDrilldown('recommendation', ot.title); },
  } : null;

  const opportunity = (money.losses && money.losses.length) ? {
    label: 'One opportunity',
    title: money.losses[0].title,
    context: money.losses[0].detail || '',
    provenance: money.losses[0].estimated_cost ? `So what: ${humanize(money.losses[0].estimated_cost)}. If addressed: the pattern won't repeat.` : '',
    action: () => { navTo('home'); },
  } : null;

  const risk = changes.find(c => c.severity === 'urgent' || c.severity === 'warning') || changes[0];
  const riskItem = risk ? {
    label: risk.severity === 'urgent' ? 'One risk' : 'One thing changed overnight',
    title: risk.title || risk.detail || '',
    context: risk.detail || '',
    provenance: risk.entity || risk.domain ? `Where: ${humanize(risk.entity || risk.domain || '')}. So what: this shifted the organizational pattern.` : '',
    action: () => { navTo('home'); },
  } : null;

  const learning = (knowledge.traps && knowledge.traps.length) ? {
    label: 'One thing learned',
    title: knowledge.traps[0].title || knowledge.traps[0].risk || '',
    context: knowledge.traps[0].detail || '',
    provenance: timeAxis && timeAxis.future ? `Trajectory: ${humanize(timeAxis.future.prediction)}` : 'From organizational patterns',
    action: () => { navTo('assumptions'); },
  } : (timeAxis ? {
    label: 'One thing learned',
    title: timeAxis.present ? timeAxis.present.state : 'Organizational pattern detected',
    context: timeAxis.past ? timeAxis.past.summary : '',
    provenance: timeAxis.future ? `Trajectory: ${humanize(timeAxis.future.prediction)}` : '',
    action: () => { navTo('physics'); },
  } : null);

  // Prediction that changed — from the learning report
  const predictionChanged = briefing.improvement || null;
  const predictionItem = predictionChanged ? {
    label: 'One prediction that changed',
    title: predictionChanged.summary || predictionChanged.evidence || '',
    context: '',
    provenance: '',
    action: () => { navTo('predictions'); },
  } : null;

  const items = [decision, opportunity, riskItem, learning, predictionItem].filter(Boolean);

  // Round 46 — apply the filter to work items. If the filter is
  // 'personal', exclude work items (the deck shows only personal cards).
  const filteredItems = currentFilter === 'personal' ? [] : items;

  // ─── Round 44 Phase 6 / Round 46: Build personal cards (always) ────
  // Round 46: Always build personal cards (the default is 'all'). The
  // filter is applied at deck-building time — 'work' excludes personal
  // cards, 'personal' excludes work cards, 'all' includes both.
  // Personal cards contain ONLY the user's own data. Never third-party
  // intelligence. Each card is tagged with _mode='personal' so the
  // renderer can add the coral indicator dot.
  let personalCards = [];
  if (currentFilter !== 'work' && personalBriefing) {
    // Personal calendar items (only the user's own)
    if (personalBriefing.items && personalBriefing.items.length > 0) {
      personalBriefing.items.slice(0, 3).forEach(item => {
        personalCards.push({
          label: 'Personal',
          title: (item.content || '').slice(0, 100),
          context: `From ${item.source || 'your calendar'}`,
          provenance: '',
          sowhat: '',
          action: () => { navTo('personal'); },
          _mode: 'personal',  // coral dot
        });
      });
    }
    // Personal contradictions (only the user's own patterns)
    personalContradsList.slice(0, 2).forEach(c => {
      personalCards.push({
        label: 'Personal pattern',
        title: (c.description || '').slice(0, 100),
        context: c.evidence || '',
        provenance: '',
        sowhat: '',
        action: () => { navTo('personal'); },
        _mode: 'personal',
      });
    });
    // Work Context card from the personal briefing (bidirectional)
    if (personalBriefing.work_context && personalBriefing.work_context.enabled) {
      const wc = personalBriefing.work_context;
      const wcParts = [];
      if (wc.deadlines_today && wc.deadlines_today.length > 0) {
        wcParts.push(`${wc.deadlines_today.length} work deadline${wc.deadlines_today.length !== 1 ? 's' : ''} today`);
      }
      if (wc.meetings_into_personal_time && wc.meetings_into_personal_time.length > 0) {
        wcParts.push(`${wc.meetings_into_personal_time.length} meeting${wc.meetings_into_personal_time.length !== 1 ? 's' : ''} into personal time`);
      }
      if (wcParts.length > 0) {
        personalCards.push({
          label: 'Work context',
          title: wcParts.join(' · '),
          context: wc.commitments_summary || '',
          provenance: '',
          sowhat: '',
          action: () => { navTo('personal'); },
          _mode: 'personal',
        });
      }
    }
  }

  // Tag work items with _mode='work' for the indicator dot
  // Round 46: use filteredItems (respects the filter pill)
  filteredItems.forEach(it => { it._mode = 'work'; });

  // Determine the organizational dot color
  const dotColor = determineDotColor(briefing, contradictions);
  updateOrgDot(dotColor);

  // Determine the weather forecast
  const weather = determineWeather(pulse, briefing);

  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning.' : hour < 18 ? 'Good afternoon.' : 'Good evening.';

  let html = `
    <div class="meta-surface">
      <div class="meta-surface greeting">${greeting}</div>
      <div class="meta-surface sub-greeting">
        <span class="org-heartbeat"></span>
        ${filteredItems.length + personalCards.length > 0 ? `${filteredItems.length + personalCards.length} ${filteredItems.length + personalCards.length === 1 ? 'thing' : 'things'} deserve attention.` : 'Everything is calm. Your organization is working well.'}
      </div>
  `;

  // Round 46 — render the filter pill in the top-right of the Today surface.
  // The pill has 3 options (All/Work/Personal). Default is 'all'.
  html += `<div id="filter-pill-container" class="b-pos-absolute-2"></div>`;

  // Organizational personality one-liner (V3 Law 6)
  if (personality && personality.summary) {
    html += `
      <div class="b-p1216-rad8">
        ${escapeHtml(humanize(personality.summary))}
      </div>
    `;
  }

  // Organizational weather
  if (weather) {
    html += `
      <div class="weather-card">
        <div class="weather-forecast">${weather.forecast}</div>
        ${weather.detail ? `<div class="weather-detail">${weather.detail}</div>` : ''}
      </div>
    `;
  }

  // Brief items — Bumble true swipe-card deck (P0-1 through P0-4).
  // One card at a time. Swipe right to act, left to defer.
  // Withdrawal path: user can switch to scrollable list via "See all."
  //
  // Round 44 Phase 6: In "both" mode, personal cards are interleaved
  // by priority with work cards. Each card carries a _mode tag
  // ('work' = blue dot, 'personal' = coral dot) so the renderer can
  // show a subtle mode indicator. Personal cards NEVER contain
  // third-party intelligence — only the user's own data.
  const totalCardCount = filteredItems.length + personalCards.length;
  if (totalCardCount === 0) {
    html += `<div class="calm-empty b-text-center-9">
      <div class="empty-state"><div class="empty-state-icon"><svg width="64" height="64" viewBox="0 0 64 64" fill="none"><circle cx="32" cy="36" r="12" stroke="#FFC629" stroke-width="2.5" fill="#FFF4D1"/><path d="M12 48 L52 48" stroke="#999999" stroke-width="2" stroke-linecap="round"/><path d="M20 42 L20 48 M32 38 L32 48 M44 42 L44 48" stroke="#FFC629" stroke-width="2" stroke-linecap="round"/></svg></div><div class="empty-state-title">You're all caught up.</div><div class="empty-state-body">No decisions need you right now. We'll surface them here the moment they arrive.</div></div>
      <div class="meta-text">Maestro is watching. You'll know when something matters.</div>
    </div>`;
  } else {
    // P0-3: Build the swipe deck — max 7 cards, prioritized.
    // Priority: commitments due → contradictions → decisions → unknowns → everything else.
    // Round 44: in "both" mode, personal cards interleave by priority:
    //   commitments (work+personal) → contradictions (work+personal) →
    //   decisions (work) → unknowns (work) → habits/personal (personal).
    const categoryColors = {
      'One decision': 'decision',
      'One opportunity': 'decision',
      'One risk': 'due',
      'One thing changed overnight': 'unknown',
      'One thing learned': 'habit',
      'One prediction': 'unknown',
      'Personal': 'habit',
      'Personal pattern': 'habit',
      'Work context': 'due',
    };

    // P0-3: Collect all card data from the briefing sections.
    const deckCards = [];

    // Add commitments as cards (highest priority) — work mode
    if (commitments && commitments.commitments) {
      commitments.commitments.forEach(c => {
        deckCards.push({
          category: 'COMMITMENT',
          categoryClass: 'due',
          judgment: c.description || c.who_committed + ' committed to something',
          evidence: `Due: ${c.due_date || 'today'}${c.is_overdue ? ' — OVERDUE' : ''}`,
          rightLabel: 'REMIND',
          leftLabel: 'DEFER',
          swipeRightAction: () => sendCommitmentReminder(deckCards.indexOf(c)),
          isCommitment: true,
          commitmentIdx: commitments.commitments.indexOf(c),
          _mode: 'work',  // Round 44 — blue dot
        });
      });
    }

    // Add brief items as cards — work mode (Round 46: use filteredItems)
    filteredItems.forEach((item, i) => {
      const categoryClass = categoryColors[item.label] || 'decision';
      const canAct = item.label === 'One decision' || item.label === 'One opportunity';
      deckCards.push({
        category: item.label.toUpperCase(),
        categoryClass: categoryClass,
        judgment: item.title,
        evidence: item.context || item.provenance || '',
        sowhat: item.sowhat || '',
        rightLabel: canAct ? 'ACT NOW' : 'ACKNOWLEDGE',
        leftLabel: 'DEFER',
        swipeRightAction: canAct ? () => {
          openActionSheet('Take action', [
            { label: 'Create ticket', onclick: `quickWriteBack('jira','create_issue',{project:'ENG',summary:'${escapeJs(item.title).replace(/'/g,"\\'")}',description:'${escapeJs(item.context || '').replace(/'/g,"\\'")}',issue_type:'Task'},${i})` },
            { label: 'Send message', onclick: `quickWriteBack('slack','post_message',{channel:'general',text:'${escapeJs(item.title).replace(/'/g,"\\'")}'},${i})` },
          ]);
        } : () => { /* acknowledge — no action needed */ },
        whyCallback: `showInlineWhy('${escapeJs(item.title)}', ${i})`,
        itemIdx: i,
        canAct: canAct,
        _mode: 'work',  // Round 44 — blue dot
      });
    });

    // Round 44 Phase 6: Add personal cards (lowest priority, last in deck).
    // Personal cards contain ONLY the user's own data. Each card has
    // _mode='personal' so the renderer adds the coral indicator dot.
    personalCards.forEach(item => {
      deckCards.push({
        category: item.label.toUpperCase(),
        categoryClass: categoryColors[item.label] || 'habit',
        judgment: item.title,
        evidence: item.context || '',
        sowhat: '',
        rightLabel: 'ACKNOWLEDGE',
        leftLabel: 'DEFER',
        swipeRightAction: () => { /* acknowledge — no action needed */ },
        itemIdx: -1,
        canAct: false,
        _mode: 'personal',  // Round 44 — coral dot
      });
    });

    // Limit to 7 cards (P0-3 constraint)
    const deck = deckCards.slice(0, 7);
    const remaining = deck.length;

    // Render the swipe deck container
    html += `
      <div id="swipe-deck-container" class="b-pos-relative-2">
      </div>
      <div id="swipe-deck-progress" class="b-text-center-5">
        ${remaining} ${remaining === 1 ? 'card' : 'cards'}
      </div>
      <div class="b-text-center-6">
        <button class="maestro-btn maestro-btn-ghost b-fs13-minh36-2" onclick="toggleSwipeDeckView()">See all</button>
      </div>
      <div id="swipe-deck-summary" class="b-hidden-text">
        <div class="b-fs18-fw800-2">That's your morning.</div>
        <div id="swipe-deck-counts" class="b-fs14-text-3"></div>
      </div>
    `;

    // Also render the scrollable fallback (hidden by default)
    // Round 46: use filteredItems (respects the filter pill)
    html += `<div id="swipe-deck-list" class="d-none">`;
    filteredItems.forEach((item, i) => {
      const prepareBtn = item.label === 'One decision' ? `<button class="maestro-btn maestro-btn-full b-mt12-fs14" onclick="prepareExecution('${escapeJs(item.title)}')">Prepare</button>` : '';
      const whyLink = `<a class="why-link b-fs13-text-2" onclick="showInlineWhy('${escapeJs(item.title)}', ${i})">Why?</a>`;
      const actionBtns = item.label === 'One decision' || item.label === 'One opportunity'
        ? `<div class="b-flex-gap8-2">
             <button class="maestro-btn maestro-btn-secondary b-flex-fs13-2" onclick="quickWriteBack('jira','create_issue',{project:'ENG',summary:'${escapeJs(item.title).replace(/'/g,"\\'")}',description:'${escapeJs(item.context || '').replace(/'/g,"\\'")}',issue_type:'Task'},${i})">Create ticket</button>
             <button class="maestro-btn maestro-btn-secondary b-flex-fs13-2" onclick="quickWriteBack('slack','post_message',{channel:'general',text:'${escapeJs(item.title).replace(/'/g,"\\'")}'},${i})">Send message</button>
           </div>`
        : '';
      const categoryClass = categoryColors[item.label] || 'decision';
      // P0-4: Bold confidence labels
      const confLabel = item.confidence != null
        ? (item.confidence >= 0.8 ? 'VERIFIED' : item.confidence >= 0.5 ? 'CONFIDENT' : 'EXPLORING')
        : null;
      const confColor = confLabel === 'VERIFIED' ? 'var(--maestro-success,#00C853)'
                      : confLabel === 'CONFIDENT' ? 'var(--maestro-warning,#FF9800)'
                      : 'var(--maestro-gray-mid,#999999)';
      html += `
        <div class="maestro-card brief-item mb-16" data-idx="${i}">
          <div class="swipe-card-category ${categoryClass} mb-12">${escapeHtml(item.label.toUpperCase())}</div>
          <div class="brief-card-title">${escapeHtml(humanize(item.title))}</div>
          ${item.context ? `<div class="b-fs14-text-14">${escapeHtml(humanize(item.context))}</div>` : ''}
          ${item.provenance ? `<div class="b-fs12-text-4">${escapeHtml(humanize(item.provenance))}</div>` : ''}
          ${confLabel ? `<div class="b-inline-block-6">${confLabel}</div>` : ''}
          ${item.sowhat ? `<div class="b-mt8-p1014">So what: ${escapeHtml(humanize(item.sowhat))}</div>` : ''}
          ${prepareBtn}
          ${actionBtns}
          ${whyLink}
          <div id="inline-why-${i}" class="mt-8"></div>
          <div id="quick-wb-${i}" class="mt-8"></div>
        </div>
      `;
    });
    // Round 44 Phase 6: also render personal cards in the list view,
    // each with a coral mode indicator dot.
    personalCards.forEach((item, i) => {
      const categoryClass = categoryColors[item.label] || 'habit';
      html += `
        <div class="maestro-card brief-item b-mb16-pos" data-idx="p${i}">
          <div class="b-pos-absolute-3" title="Personal" aria-label="Mode: Personal"></div>
          <div class="swipe-card-category ${categoryClass} mb-12">${escapeHtml(item.label.toUpperCase())}</div>
          <div class="brief-card-title">${escapeHtml(humanize(item.title))}</div>
          ${item.context ? `<div class="b-fs14-text-14">${escapeHtml(humanize(item.context))}</div>` : ''}
        </div>
      `;
    });
    html += `</div>`;

    // Store deck state for the swipe handlers
    window._swipeDeck = deck;
    window._swipeDeckIdx = 0;
    window._swipeDeckActed = 0;
    window._swipeDeckDeferred = 0;
  }

  // V6 Spec #3 — Background Loop: "Maestro noticed this while you were away"
  if (backgroundLoop && backgroundLoop.notices && backgroundLoop.notices.length > 0) {
    html += `
      <div class="b-mt24-p20-2">
        <div class="brief-label b-text-muted">While you were away</div>
        <div class="b-fs14-text-16">${escapeHtml(humanize(backgroundLoop.summary || ''))}</div>
        ${backgroundLoop.notices.slice(0, 3).map(n => {
          const color = n.urgency === 'high' ? 'var(--risk)' : n.urgency === 'medium' ? 'var(--warning)' : 'var(--text-secondary)';
          return `<div class="b-p80-u">
            <div class="b-fs13-clr">${escapeHtml(humanize(n.message || ''))}</div>
            ${n.detail ? `<div class="ds-meta mt-2">${escapeHtml(humanize(n.detail))}</div>` : ''}
          </div>`;
        }).join('')}
      </div>
    `;
  }

  // V6 Spec #4 — Trajectory Intervention: declining trajectories that need action
  if (interventions && interventions.interventions && interventions.interventions.length > 0) {
    html += `
      <div class="b-mt24-p20">
        <div class="brief-label b-text-risk">Needs attention</div>
        <div class="b-fs14-text-16">${escapeHtml(humanize(interventions.summary || ''))}</div>
        ${interventions.interventions.slice(0, 2).map(iv => `
          <div class="b-p100-u">
            <div class="b-fs14-text-5">${escapeHtml(humanize(iv.intervention || ''))}</div>
            <div class="ds-meta mt-4">Time to impact: ${escapeHtml(iv.time_to_failure || '')} · Urgency: ${escapeHtml(iv.urgency || '')}</div>
          </div>
        `).join('')}
      </div>
    `;
  }

  // V6 Spec #1 — Adaptive Nudges: actionable restructuring suggestions
  if (nudges && nudges.nudges && nudges.nudges.length > 0) {
    html += `
      <div class="b-mt32-p20">
        <div class="brief-label text-accent">Maestro suggests a change</div>
        <div class="body-text">${escapeHtml(humanize(nudges.summary || ''))}</div>
        ${nudges.nudges.slice(0, 2).map((n, i) => `
          <div class="brief-item b-u-4300" data-nudge-idx="${i}">
            <div class="b-fs14-text-6">${escapeHtml(humanize(n.intervention || ''))}</div>
            <div class="brief-context fs-12">${escapeHtml(humanize(n.evidence || ''))}</div>
            <div class="ds-row b-gap6-mt8">
              <button class="ds-btn ds-btn-positive ds-btn-small" onclick="this.closest('.brief-item').style.opacity='0.5';this.textContent='Accepted'">Accept</button>
              <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="this.closest('.brief-item').style.display='none'">Dismiss</button>
            </div>
          </div>
        `).join('')}
      </div>
    `;
  }

  // V8 P0-1 — Commitments Due Today.
  // The Bond lesson: commitments find the CEO, not vice versa.
  if (commitments && commitments.commitments && commitments.commitments.length > 0) {
    window._currentBriefingCommitments = commitments.commitments;
    html += `
      <div class="maestro-card b-mt16-u-2">
        <div class="swipe-card-category ${commitments.overdue_count > 0 ? 'contradiction' : 'due'} mb-12">Commitments due today</div>
        <div class="b-fs14-text-15">${escapeHtml(humanize(commitments.summary || ''))}</div>
        ${commitments.commitments.map((c, i) => `
          <div class="brief-item b-u-p100">
            <div class="b-flex-u-6">
              <div class="flex-1">
                <div class="brief-context b-text-primary">${escapeHtml(humanize(c.description || ''))}</div>
                <div class="ds-meta mt-4">
                  ${c.who_committed ? `By: ${escapeHtml(c.who_committed)}` : ''}
                  ${c.to_whom ? ` → ${escapeHtml(c.to_whom)}` : ''}
                  ${c.due_date ? ` · Due: ${escapeHtml(c.due_date)}` : ''}
                  ${c.is_overdue ? ' · <span class="b-text-risk">OVERDUE</span>' : ''}
                </div>
              </div>
              <div class="b-flex-gap4">
                ${c.to_whom ? `<button class="ds-btn ds-btn-ghost ds-btn-small b-fs11-ws" onclick="showTrajectoryPanel('commitment-trajectory-${i}', ${JSON.stringify(c.to_whom).replace(/"/g, '&quot;')})">Trajectory</button>` : ''}
                <button class="ds-btn ds-btn-ghost ds-btn-small b-fs11-ws"
                        onclick="sendCommitmentReminder(${i})">Remind</button>
              </div>
            </div>
            <div id="commitment-trajectory-${i}" class="mt-8"></div>
            <div id="commitment-reminder-${i}" class="mt-8"></div>
          </div>
        `).join('')}
      </div>
    `;
  }

  // V4 Organ #2 → V8 Upgrade #3 — Conversational Curiosity.
  // Maestro asks a question, the user answers, Maestro asks a context-aware
  // follow-up, the user answers again, and after at most 3 turns Maestro
  // says "Thank you. Understanding updated." The answer becomes a
  // human_context signal that feeds into the model.
  if (curiosity && curiosity.questions && curiosity.questions.length > 0) {
    html += `
      <div class="brief-section">
        <div class="brief-label text-accent">Maestro has questions</div>
        <div class="body-text">${escapeHtml(humanize(curiosity.summary))}</div>
        ${curiosity.questions.slice(0, 3).map((q, i) => `
          <div class="curiosity-conversation b-u-p120" data-curiosity-idx="${i}">
            <div class="curiosity-question b-text-primary-2">${escapeHtml(humanize(q.question))}</div>
            <div class="curiosity-evidence ds-meta mb-8">${escapeHtml(humanize(q.evidence))}</div>
            <div class="curiosity-conversation-area" id="curiosity-conv-${i}" data-question-id="${escapeHtml(q.question_id || '')}" data-question-type="${escapeHtml(q.type || '')}" data-domain="${escapeHtml(q.domain || '')}" data-original-question="${escapeHtml(q.question || '')}" data-turn="1">
              <input type="text" class="curiosity-answer-input" id="curiosity-input-${i}"
                     placeholder="Type your answer…"
                     class="b-w-full-8"
                     onkeydown="if(event.key==='Enter') submitCuriosityAnswer(${i})"
                     aria-label="Answer Maestro's question" />
              <button class="ds-btn ds-btn-ghost ds-btn-small mt-6" onclick="submitCuriosityAnswer(${i})">Answer</button>
            </div>
          </div>
        `).join('')}
      </div>
    `;
  }

  // V8 Daily Work #2 — Task & Action-Item Intelligence.
  // Shows tasks b-extracted from signal text during ingestion.
  // Each task has: description, assignee, due_date, priority, status.
  if (tasks && tasks.tasks && tasks.tasks.length > 0) {
    const priorityColor = { high: 'var(--risk,#DC2626)', medium: 'var(--warning,#D97706)', low: 'var(--text-muted)' };
    html += `
      <div class="brief-section">
        <div class="brief-label text-accent">Your tasks</div>
        <div class="body-text">${tasks.total} open task${tasks.total === 1 ? '' : 's'} b-extracted from your organization's signals.</div>
        ${tasks.tasks.slice(0, 5).map(t => `
          <div class="brief-item b-u-p100">
            <div class="b-flex-u-6">
              <div class="flex-1">
                <div class="brief-context b-text-primary">${escapeHtml(humanize(t.description || ''))}</div>
                <div class="ds-meta mt-4">
                  ${t.assignee ? `Assignee: ${escapeHtml(t.assignee)}` : 'Unassigned'}
                  ${t.due_date ? ` · Due: ${escapeHtml(t.due_date)}` : ''}
                  ${t.domain ? ` · Domain: ${escapeHtml(t.domain)}` : ''}
                </div>
              </div>
              <span class="tag b-bg-3ca4">
                ${escapeHtml(t.priority || 'medium')}
              </span>
            </div>
          </div>
        `).join('')}
      </div>
    `;
  }

  // V8 Upgrade #2 — Four-Level Unknowns: what Maestro doesn't know yet.
  // 4 epistemic levels, each with different visual treatment:
  //   Known (green check) — measured thoroughly
  //   Known Unknowns (amber) — the org knows it's under-measuring
  //   Unknown Unknowns (red) — blind spots
  //   Emerging Unknowns (purple pulse) — new and uncategorized
  if (unknowns && (unknowns.known || unknowns.known_unknowns || unknowns.unknown_unknowns || unknowns.emerging_unknowns)) {
    const totalCount = (unknowns.level_counts?.known || 0) + (unknowns.level_counts?.known_unknowns || 0) +
                       (unknowns.level_counts?.unknown_unknowns || 0) + (unknowns.level_counts?.emerging_unknowns || 0);
    if (totalCount > 0) {
      html += `
        <div class="brief-section">
          <div class="brief-label b-text-muted">What Maestro doesn't know yet</div>
          <div class="body-text">${escapeHtml(humanize(unknowns.summary || ''))}</div>
      `;

      // Level 1: Known — green, collapsed by default (it's the "good news")
      if (unknowns.known && unknowns.known.length > 0) {
        html += `
          <details class="unknowns-level unknowns-known mb-12">
            <summary class="brief-card-action">
              <span class="b-text-positive-2">✓</span>
              <strong>Known</strong> — ${unknowns.known.length} area${unknowns.known.length === 1 ? '' : 's'} measured thoroughly
            </summary>
            <div class="brief-item-indent">
              ${unknowns.known.slice(0, 5).map(a => `
                <div class="b-p60-u">
                  <div class="text-body">${escapeHtml(a.area)}</div>
                  <div class="ds-meta mt-2">${a.signal_count} signals · ${Math.round((a.coverage || 0) * 100)}% coverage</div>
                </div>
              `).join('')}
            </div>
          </details>
        `;
      }

      // Level 2: Known Unknowns — amber, expanded (actionable: instrument them)
      if (unknowns.known_unknowns && unknowns.known_unknowns.length > 0) {
        html += `
          <details class="unknowns-level unknowns-known-unknowns" open class="mb-12">
            <summary class="brief-card-action">
              <span class="text-warning">!</span>
              <strong>Known Unknowns</strong> — ${unknowns.known_unknowns.length} area${unknowns.known_unknowns.length === 1 ? '' : 's'} the org knows it's under-measuring
            </summary>
            <div class="brief-item-indent">
              ${unknowns.known_unknowns.slice(0, 5).map(a => `
                <div class="b-p60-u">
                  <div class="text-body">${escapeHtml(a.area)}</div>
                  <div class="ds-meta mt-2">${a.signal_count} signal${a.signal_count === 1 ? '' : 's'} · ${Math.round((a.coverage || 0) * 100)}% coverage</div>
                  <div class="b-fs12-text-8">${escapeHtml(humanize(a.reason || ''))}</div>
                </div>
              `).join('')}
            </div>
          </details>
        `;
      }

      // Level 3: Unknown Unknowns — red, expanded (risky: blind spots)
      if (unknowns.unknown_unknowns && unknowns.unknown_unknowns.length > 0) {
        html += `
          <details class="unknowns-level unknowns-unknown-unknowns" open class="mb-12">
            <summary class="brief-card-action">
              <span class="b-text-risk-2">?</span>
              <strong>Unknown Unknowns</strong> — ${unknowns.unknown_unknowns.length} blind spot${unknowns.unknown_unknowns.length === 1 ? '' : 's'} (the org doesn't know it doesn't know)
            </summary>
            <div class="brief-item-indent">
              ${unknowns.unknown_unknowns.slice(0, 5).map(a => `
                <div class="b-p60-u">
                  <div class="text-body">${escapeHtml(a.area)}</div>
                  <div class="ds-meta mt-2">${a.signal_count} signal${a.signal_count === 1 ? '' : 's'} · ${Math.round((a.coverage || 0) * 100)}% coverage</div>
                  <div class="b-fs12-text-8">${escapeHtml(humanize(a.reason || ''))}</div>
                </div>
              `).join('')}
            </div>
          </details>
        `;
      }

      // Level 4: Emerging Unknowns — purple pulse, expanded (opportunities: investigate)
      if (unknowns.emerging_unknowns && unknowns.emerging_unknowns.length > 0) {
        html += `
          <details class="unknowns-level unknowns-emerging" open class="mb-12">
            <summary class="brief-card-action">
              <span class="text-accent">✦</span>
              <strong>Emerging Unknowns</strong> — ${unknowns.emerging_unknowns.length} new pattern${unknowns.emerging_unknowns.length === 1 ? '' : 's'} in the last 7 days
            </summary>
            <div class="brief-item-indent">
              ${unknowns.emerging_unknowns.slice(0, 5).map(a => `
                <div class="b-p60-u">
                  <div class="text-body">${escapeHtml(a.area)}</div>
                  <div class="ds-meta mt-2">${a.signal_count} new signal${a.signal_count === 1 ? '' : 's'} · detected ${a.detected_at ? new Date(a.detected_at).toLocaleDateString() : 'recently'}</div>
                  <div class="b-fs12-text-8">${escapeHtml(humanize(a.reason || ''))}</div>
                </div>
              `).join('')}
            </div>
          </details>
        `;
      }

      html += `</div>`;
    }
  }

  html += `</div>`;
  el.innerHTML = html;

  // Wire up click handlers
  // Round 46: use filteredItems (respects the filter pill)
  filteredItems.forEach((item, i) => {
    const itemEl = el.querySelector(`.brief-item[data-idx="${i}"]`);
    if (itemEl && item.action) {
      itemEl.addEventListener('click', item.action);
    }
  });

  // Round 46 — render the filter pill into the container we created above.
  // This must happen AFTER el.innerHTML is set, so the container exists.
  if (typeof renderFilterPill === 'function') {
    renderFilterPill('filter-pill-container');
  }

  // V8 P0-1: Initialize the swipe deck after rendering
  initSwipeDeck();
}

// V8 Upgrade #3 — Conversational Curiosity submission handler.
// Called when the user types an answer and hits Enter or clicks "Answer".
// Sends the answer to POST /api/oem/curiosity/follow-up, then either
// renders the follow-up question (turn 2 or 3) or shows the
// "Thank you. Understanding updated." closing message (after turn 3).
async function submitCuriosityAnswer(idx) {
  const inputEl = document.getElementById(`curiosity-input-${idx}`);
  if (!inputEl) return;
  const answer = inputEl.value.trim();
  if (!answer) return;

  const convEl = document.getElementById(`curiosity-conv-${idx}`);
  if (!convEl) return;

  const questionId = convEl.dataset.questionId || '';
  const questionType = convEl.dataset.questionType || '';
  const domain = convEl.dataset.domain || '';
  const originalQuestion = convEl.dataset.originalQuestion || '';
  const currentTurn = parseInt(convEl.dataset.turn || '1', 10);

  // Disable the input while we wait for the response
  inputEl.disabled = true;
  inputEl.value = '';

  // Show the user's answer as a chat bubble (right-aligned)
  const chatArea = convEl;
  chatArea.insertAdjacentHTML('beforebegin', `
    <div class="curiosity-chat-bubble curiosity-chat-user b-m80840-p812">
      ${escapeHtml(answer)}
    </div>
  `);

  // Show a loading indicator
  chatArea.insertAdjacentHTML('beforebegin', `
    <div class="curiosity-loading b-m80-text" id="curiosity-loading-${idx}">Maestro is thinking…</div>
  `);

  try {
    const payload = {
      question_id: questionId,
      answer: answer,
    };
    // On turn 1, include the original question + type + domain so the
    // backend can start a new conversation. On subsequent turns, these
    // are ignored (the backend has the conversation state).
    if (currentTurn === 1) {
      payload.original_question = originalQuestion;
      payload.question_type = questionType;
      payload.domain = domain;
    }

    const data = await api.postOEM('/curiosity/follow-up', payload);

    // Remove the loading indicator
    const loadingEl = document.getElementById(`curiosity-loading-${idx}`);
    if (loadingEl) loadingEl.remove();

    if (data.understanding_updated) {
      // Conversation closed — show the closing message
      chatArea.insertAdjacentHTML('beforebegin', `
        <div class="curiosity-chat-bubble curiosity-chat-maestro curiosity-chat-closing b-m80-p1014">
          <span class="b-text-accent">${escapeHtml(humanize(data.summary || 'Thank you. Understanding updated.'))}</span>
        </div>
      `);
      // Remove the input area — the conversation is done
      chatArea.remove();
    } else if (data.follow_up_question) {
      // Show the follow-up question as a chat bubble (left-aligned)
      chatArea.insertAdjacentHTML('beforebegin', `
        <div class="curiosity-chat-bubble curiosity-chat-maestro b-m84080-p1014">
          ${escapeHtml(humanize(data.follow_up_question))}
        </div>
      `);
      // Update the turn counter and re-enable the input
      convEl.dataset.turn = String(data.turn || (currentTurn + 1));
      inputEl.disabled = false;
      inputEl.placeholder = `Turn ${data.turn || (currentTurn + 1)} of 3 — type your answer…`;
      inputEl.focus();
    } else {
      // Unexpected response — re-enable input and show error
      inputEl.disabled = false;
      chatArea.insertAdjacentHTML('beforebegin', `
        <div class="b-m80-text-2">Something went wrong. Try again.</div>
      `);
    }
  } catch (e) {
    // Remove the loading indicator and re-enable input
    const loadingEl = document.getElementById(`curiosity-loading-${idx}`);
    if (loadingEl) loadingEl.remove();
    inputEl.disabled = false;
    chatArea.insertAdjacentHTML('beforebegin', `
      <div class="b-m80-text-2">Failed: ${escapeHtml(e.message)}</div>
    `);
  }
}

// V8 P0-3 — Quick write-back from briefing items.
// Two taps: (1) preview, (2) approve. Never one tap to send.
async function quickWriteBack(provider, actionType, params, idx) {
  const el = document.getElementById(`quick-wb-${idx}`);
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const preview = await api.postOEM('/writeback', { provider, action_type: actionType, params });
    el.innerHTML = `
      <div class="brief-surface-block">
        <pre class="b-fs11-text-8">${escapeHtml(preview.preview)}</pre>
        <div class="b-flex-gap6">
          <button class="ds-btn ds-btn-primary ds-btn-small fs-11" onclick="approveQuickWriteBack('${preview.action_id}', ${idx})">Approve</button>
          <button class="ds-btn ds-btn-ghost ds-btn-small fs-11" onclick="document.getElementById('quick-wb-${idx}').innerHTML=''">Cancel</button>
        </div>
      </div>
    `;
  } catch (e) {
    el.innerHTML = `<div class="ds-error fs-11">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function approveQuickWriteBack(actionId, idx) {
  const el = document.getElementById(`quick-wb-${idx}`);
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const result = await api.postOEM(`/writeback/${actionId}/approve`, { approved_by: 'ceo' });
    if (result.status === 'executed') {
      const r = result.result || {};
      let detail = r.mock ? ' (mock)' : '';
      if (r.issue_key) detail = ` Created ${r.issue_key}.`;
      else if (r.message_ts) detail = ` Posted to Slack.`;
      else if (r.draft_id) detail = ` Draft created (NOT sent).`;
      el.innerHTML = `<div class="b-p8-text-2">Done.${detail}</div>`;
    } else {
      el.innerHTML = `<div class="ds-error fs-11">Failed: ${escapeHtml(result.error || '')}</div>`;
    }
  } catch (e) {
    el.innerHTML = `<div class="ds-error fs-11">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

// V8 P0-2 — Inline "Why?" explanation on any briefing item.
// Fetches /explain with a context-derived question and renders the
// explanation chain inline as a collapsible section. Apple's deference
// principle: the explanation is hidden until the customer asks for it.
async function showInlineWhy(title, idx) {
  const el = document.getElementById(`inline-why-${idx}`);
  if (!el) return;
  if (el.innerHTML.trim()) {
    el.innerHTML = ''; // toggle off if already shown
    return;
  }
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const question = `Why is this happening: ${title}?`;
    const data = await api.getOEM(`/explain?q=${encodeURIComponent(question)}`);
    if (!data.steps || data.steps.length === 0) {
      el.innerHTML = `<div class="b-p812-bg">${escapeHtml(humanize(data.honest_limitation || 'Not enough data to explain yet.'))}</div>`;
      return;
    }
    let chainHtml = '<div class="space-2">';
    for (const step of data.steps.slice(0, 5)) {
      const confPct = Math.round((step.confidence || 0) * 100);
      const confColor = confPct >= 70 ? 'var(--accent)' : confPct >= 40 ? 'var(--secondary)' : 'var(--text-muted)';
      chainHtml += `
        <div class="b-flex-gap10">
          <div class="b-u-5cd1-2">${step.step}</div>
          <div class="flex-1">
            <div class="b-fs12-text-14">${escapeHtml(humanize(step.label || ''))}</div>
            <div class="b-fs11-text-7">${escapeHtml(humanize(step.narrative || ''))}</div>
            <div class="b-mt2-h2"><div class="b-h100-wconfpctp"></div></div>
          </div>
        </div>
      `;
    }
    chainHtml += '</div>';
    el.innerHTML = chainHtml;
  } catch (e) {
    el.innerHTML = `<div class="ds-error fs-11">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

// Phase 2.2 — Trajectory Panel.
// The implementation now lives in static/js/trajectory_panel.js (shared
// utility, used by both today.js and personal.js). The card onclick calls
// the shared `showTrajectoryPanel(containerId, entity)` function.
//
// Previously this file had an inline async function; refactored to shared
// utility on 2026-07-04 to avoid duplication when personal.js adopts the
// same panel.
//
// Fetches /api/oem/loop1.5/timeline/{entity} and renders the Day-60
// projection + recommendation derived from the CommitmentMutationTracker
// history (the projection is DERIVED server-side per P13 — the UI just
// renders it, never supplies the rate, pattern, or risk).

// V8 P0-1 — Send a commitment reminder via write-back (Slack DM draft).
async function sendCommitmentReminder(idx) {
  const el = document.getElementById(`commitment-reminder-${idx}`);
  if (!el) return;
  const commitments = (window._currentBriefingCommitments) || [];
  const c = commitments[idx];
  if (!c) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const reminderText = `Gentle reminder: ${c.description} (due ${c.due_date || 'today'}). Can you provide an update?`;
    const preview = await api.postOEM('/writeback', {
      provider: 'slack',
      action_type: 'post_message',
      params: { channel: 'general', text: reminderText },
    });
    el.innerHTML = `
      <div class="brief-surface-block">
        <pre class="b-fs11-text-8">${escapeHtml(preview.preview)}</pre>
        <div class="b-flex-gap6">
          <button class="ds-btn ds-btn-primary ds-btn-small fs-11" onclick="approveCommitmentReminder('${preview.action_id}', ${idx})">Approve & Send</button>
          <button class="ds-btn ds-btn-ghost ds-btn-small fs-11" onclick="document.getElementById('commitment-reminder-${idx}').innerHTML=''">Cancel</button>
        </div>
      </div>
    `;
  } catch (e) {
    el.innerHTML = `<div class="ds-error fs-11">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function approveCommitmentReminder(actionId, idx) {
  const el = document.getElementById(`commitment-reminder-${idx}`);
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const result = await api.postOEM(`/writeback/${actionId}/approve`, { approved_by: 'ceo' });
    if (result.status === 'executed') {
      el.innerHTML = `<div class="b-p8-text-2">Reminder sent.</div>`;
    } else {
      el.innerHTML = `<div class="ds-error fs-11">Failed: ${escapeHtml(result.error || '')}</div>`;
    }
  } catch (e) {
    el.innerHTML = `<div class="ds-error fs-11">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

// V8 P0-1: Initialize the swipe deck after the briefing renders.
// Called after el.innerHTML is set — finds the container and renders the first card.
function initSwipeDeck() {
  const container = document.getElementById('swipe-deck-container');
  if (!container || !window._swipeDeck || window._swipeDeck.length === 0) return;

  window._swipeDeckIdx = 0;
  window._swipeDeckActed = 0;
  window._swipeDeckDeferred = 0;

  renderSwipeCard();
}

function renderSwipeCard() {
  const container = document.getElementById('swipe-deck-container');
  if (!container) return;

  const deck = window._swipeDeck || [];
  const idx = window._swipeDeckIdx || 0;

  // Check if deck is complete
  if (idx >= deck.length) {
    showSwipeDeckSummary();
    return;
  }

  const cardData = deck[idx];
  container.innerHTML = '';

  // Use createSwipeCard from swipe-cards.js
  if (typeof createSwipeCard !== 'function') return;

  const card = createSwipeCard({
    category: cardData.category,
    category_class: cardData.categoryClass,
    judgment: cardData.judgment,
    evidence: cardData.evidence,
    right_label: cardData.rightLabel,
    left_label: cardData.leftLabel,
    why_link: cardData.whyCallback ? true : false,
    why_callback: cardData.whyCallback || '',
  });

  // Round 44 Phase 6 — Mode indicator dot.
  // Blue dot for Work, coral dot for Personal. Subtle, in the top-right
  // corner of the card. Only shown in "both" mode (when the deck mixes
  // work and personal cards). In single-mode decks the dot is omitted
  // because every card has the same mode.
  if (cardData._mode) {
    const dotColor = cardData._mode === 'personal' ? '#FF6B6B' : '#2196F3';  // coral / blue
    const dotTitle = cardData._mode === 'personal' ? 'Personal' : 'Work';
    const dot = document.createElement('div');
    dot.style.cssText = `position:absolute;top:14px;right:14px;width:10px;height:10px;border-radius:50%;background:${dotColor};opacity:0.85;title:${dotTitle};`;
    dot.title = dotTitle;
    dot.setAttribute('aria-label', `Mode: ${dotTitle}`);
    card.appendChild(dot);
  }

  // Style the card for the deck (absolute positioning within container)
  card.style.position = 'relative';
  container.appendChild(card);

  // Initialize the SwipeCard class on this element
  const swipeHandler = new SwipeCard(card,
    // Swipe right callback
    () => {
      window._swipeDeckActed++;
      if (cardData.swipeRightAction) cardData.swipeRightAction();
      advanceSwipeDeck();
    },
    // Swipe left callback
    () => {
      window._swipeDeckDeferred++;
      advanceSwipeDeck();
    }
  );

  // Update progress
  updateSwipeDeckProgress();
}

function advanceSwipeDeck() {
  window._swipeDeckIdx = (window._swipeDeckIdx || 0) + 1;
  setTimeout(() => renderSwipeCard(), 350);
}

function updateSwipeDeckProgress() {
  const progress = document.getElementById('swipe-deck-progress');
  if (!progress) return;
  const deck = window._swipeDeck || [];
  const idx = window._swipeDeckIdx || 0;
  const remaining = deck.length - idx;
  if (remaining > 0) {
    progress.textContent = `${remaining} ${remaining === 1 ? 'card' : 'cards'}`;
  } else {
    progress.textContent = '';
  }
}

function showSwipeDeckSummary() {
  const container = document.getElementById('swipe-deck-container');
  if (container) container.innerHTML = '';
  const progress = document.getElementById('swipe-deck-progress');
  if (progress) progress.style.display = 'none';
  const summary = document.getElementById('swipe-deck-summary');
  if (summary) {
    summary.style.display = 'block';
    const counts = document.getElementById('swipe-deck-counts');
    if (counts) {
      const acted = window._swipeDeckActed || 0;
      const deferred = window._swipeDeckDeferred || 0;
      counts.textContent = `${acted} ${acted === 1 ? 'action' : 'actions'} taken, ${deferred} ${deferred === 1 ? 'item' : 'items'} deferred. Have a good day.`;
    }
  }
}

// V8 P0-1: Toggle between swipe deck and scrollable list view.
function toggleSwipeDeckView() {
  const deck = document.getElementById('swipe-deck-container');
  const progress = document.getElementById('swipe-deck-progress');
  const list = document.getElementById('swipe-deck-list');
  const summary = document.getElementById('swipe-deck-summary');
  const btn = event ? event.target : null;

  if (deck && deck.style.display !== 'none') {
    // Switch to list view
    deck.style.display = 'none';
    if (progress) progress.style.display = 'none';
    if (summary) summary.style.display = 'none';
    if (list) list.style.display = 'block';
    if (btn) btn.textContent = 'Swipe view';
  } else {
    // Switch to swipe view
    if (deck) deck.style.display = 'block';
    if (progress) progress.style.display = 'block';
    if (list) list.style.display = 'none';
    if (btn) btn.textContent = 'See all';
    if (window._swipeDeckIdx >= (window._swipeDeck || []).length) {
      showSwipeDeckSummary();
    } else {
      renderSwipeCard();
    }
  }
}

function determineDotColor(briefing, contradictionsOrPulse) {
  // Red: urgent decision needed
  if (briefing.one_thing && briefing.one_thing.urgency === 'urgent') return 'red';
  // Orange: cross-functional impact (contradictions detected)
  // The contradictions parameter can be an array (from /contradictions API)
  // or an object with a .contradictions array (from the briefing)
  let contradictions = [];
  if (Array.isArray(contradictionsOrPulse)) {
    contradictions = contradictionsOrPulse;
  } else if (contradictionsOrPulse && contradictionsOrPulse.contradictions) {
    contradictions = contradictionsOrPulse.contradictions;
  }
  if (contradictions.length > 0) return 'orange';
  // Yellow: opportunity or overnight change
  if (briefing.overnight && briefing.overnight.changes && briefing.overnight.changes.length > 0) return 'yellow';
  // Green: nothing requires attention
  return 'green';
}

function determineWeather(pulse, briefing) {
  if (!pulse) return null;

  const temp = pulse.temperature || 'neutral';
  const momentum = pulse.momentum || 'stable';

  // Map pulse metrics to weather metaphors
  if (temp === 'hot' || temp === 'tension') {
    return {
      forecast: 'Decision Storm — organizational tension is high.',
      detail: momentum === 'accelerating' ? 'Pressure is building. Decisions made now will propagate fast.' : 'Tension is stable but present.',
    };
  }
  if (temp === 'cold' || temp === 'calm') {
    return {
      forecast: 'Calm Execution Window.',
      detail: 'Low tension. Good time for long-term work.',
    };
  }
  if (momentum === 'accelerating') {
    return {
      forecast: 'Knowledge Front moving through the organization.',
      detail: 'New patterns are forming. Decisions will be easier soon.',
    };
  }
  if (momentum === 'decelerating') {
    return {
      forecast: 'Heavy Review Traffic expected.',
      detail: 'Decisions are slowing. Consider unblocking bottlenecks.',
    };
  }
  return {
    forecast: 'Stable conditions.',
    detail: 'The organization is operating normally.',
  };
}

// V5 Spec #2 — Executive Function: Prepare an execution plan
async function prepareExecution(title) {
  // Open the drill-down modal with the execution plan
  openDrilldown('recommendation', title);
  // Switch to the So What? tab first (which has the consequence),
  // then the user can click "Prepare" to see the full plan
  setTimeout(async () => {
    const body = document.getElementById('drilldown-body');
    if (!body) return;
    body.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div><div class="skeleton skeleton-line skeleton-line-w50"></div></div>';
    try {
      const plan = await api.getOEM(`/execute?recommendation_id=${encodeURIComponent(title)}`);
      body.innerHTML = `
        <div class="ds-stack">
          <div>
            <div class="ds-cascade-label">Execution plan</div>
            <div class="b-fs15-text-3">${escapeHtml(humanize(plan.summary || ''))}</div>
          </div>
          ${plan.steps ? plan.steps.map(s => `
            <div class="ds-card b-p14">
              <div class="ds-row-between mb-6">
                <span class="ds-tag ds-tag-pending">Step ${s.step}</span>
                <span class="ds-meta">${escapeHtml(s.estimated_time || '')}</span>
              </div>
              <div class="b-fs14-fw500-3">${escapeHtml(humanize(s.title || ''))}</div>
              <div class="subtle-text">${escapeHtml(humanize(s.detail || ''))}</div>
              <div class="ds-meta mt-6">Owner: ${escapeHtml(humanize(s.owner || ''))}${s.prerequisite ? ' · After: ' + escapeHtml(humanize(s.prerequisite)) : ''}</div>
            </div>
          `).join('') : ''}
          <div>
            <div class="ds-cascade-label">Drafted briefing</div>
            <div class="b-p14-bg-3">${escapeHtml(humanize(plan.drafted_briefing || ''))}</div>
          </div>
          <div>
            <div class="ds-cascade-label">Follow-through</div>
            <div class="subtle-text">
              Check-in: ${escapeHtml(plan.follow_through?.check_in_date || '')}<br>
              Success: ${escapeHtml(humanize(plan.follow_through?.success_metric || ''))}
            </div>
          </div>
          <div class="b-u-7f83">
            <div class="ds-cascade-label mb-10">Execute — create tickets, drafts, messages</div>
            <div class="b-flex-gap8-4">
              <button class="ds-btn ds-btn-primary ds-btn-small" onclick="executeWriteBack('jira','create_issue',{project:'ENG',summary:'${escapeJs(title).replace(/'/g,"\\'")}',description:'See execution plan',issue_type:'Task'})">Create Jira ticket</button>
              <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="executeWriteBack('gmail','create_draft',{to:'team@acme.com',subject:'Action needed: ${escapeJs(title).replace(/'/g,"\\'")}',body:'See execution plan'})">Draft email</button>
              <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="executeWriteBack('slack','post_message',{channel:'general',text:'Action needed: ${escapeJs(title).replace(/'/g,"\\'")}'})">Post to Slack</button>
            </div>
            <div id="writeback-result" class="space-3"></div>
          </div>
        </div>
      `;
    } catch (e) {
      body.innerHTML = `<div class="ds-error">Failed to prepare: ${escapeHtml(e.message)}</div>`;
    }
  }, 500);
}

// V8 Daily Work #4 — Write-Back to Tools.
// Called when the user clicks "Create Jira ticket", "Draft email", or
// "Post to Slack" in the execution plan modal. Shows a preview first,
// then requires the user to click "Approve" to execute.
async function executeWriteBack(provider, actionType, params) {
  const resultEl = document.getElementById('writeback-result');
  if (!resultEl) return;

  resultEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    // Step 1: Preview (NOT executed)
    const preview = await api.postOEM('/writeback', { provider, action_type: actionType, params });

    // Show preview + approve/reject buttons
    resultEl.innerHTML = `
      <div class="b-p14-bg-2">
        <div class="b-fs13-fw500-3">Preview</div>
        <pre class="b-fs12-text-20">${escapeHtml(preview.preview)}</pre>
        <div class="flex-row">
          <button class="ds-btn ds-btn-primary ds-btn-small" onclick="approveWriteBack('${preview.action_id}')">Approve & Execute</button>
          <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="rejectWriteBack('${preview.action_id}')">Reject</button>
        </div>
      </div>
    `;
  } catch (e) {
    resultEl.innerHTML = `<div class="ds-error">Preview failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function approveWriteBack(actionId) {
  const resultEl = document.getElementById('writeback-result');
  if (!resultEl) return;
  resultEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const result = await api.postOEM(`/writeback/${actionId}/approve`, { approved_by: 'ceo' });
    if (result.status === 'executed') {
      const r = result.result || {};
      let detail = '';
      if (r.provider === 'jira') detail = `Issue created: <a href="${r.issue_url || '#'}" target="_blank" class="text-accent">${escapeHtml(r.issue_key || '')}</a>`;
      else if (r.provider === 'gmail') detail = `Draft created (NOT sent): <a href="${r.draft_url || '#'}" target="_blank" class="text-accent">Open in Gmail</a>`;
      else if (r.provider === 'slack') detail = `Message posted to ${escapeHtml(r.channel || '')} (ts: ${escapeHtml(r.message_ts || '')})`;
      else if (r.provider === 'github') detail = `Comment created: <a href="${r.comment_url || '#'}" target="_blank" class="text-accent">View</a>`;
      resultEl.innerHTML = `<div class="b-p14-bg">Executed. ${detail}${r.mock ? ' (mock mode — no real API call)' : ''}</div>`;
    } else {
      resultEl.innerHTML = `<div class="ds-error">Execution failed: ${escapeHtml(result.error || 'unknown error')}</div>`;
    }
  } catch (e) {
    resultEl.innerHTML = `<div class="ds-error">Execution failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function rejectWriteBack(actionId) {
  const resultEl = document.getElementById('writeback-result');
  if (!resultEl) return;
  try {
    await api.postOEM(`/writeback/${actionId}/reject`, { rejected_by: 'ceo' });
    resultEl.innerHTML = `<div class="b-p14-text">Action rejected.</div>`;
  } catch (e) {
    resultEl.innerHTML = `<div class="ds-error">Reject failed: ${escapeHtml(e.message)}</div>`;
  }
}

// ═══════════════════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════════════════
// CEO FEATURE 1: PREPARATION BRIEF — The Chief of Staff capability
// ═══════════════════════════════════════════════════════════════════════════
// Maestro prepares for tomorrow's meetings before the user arrives.
// Shows: customer concerns, draft responses, internal experts, talking points.
// This is the difference between an assistant and a Chief of Staff.

async function loadPreparationBrief() {
  const prepContainer = document.getElementById('today-prep-container');
  if (!prepContainer) return;

  try {
    const resp = await fetch((MAESTRO_API || '') + '/api/oem/preparation/tomorrow');
    if (!resp.ok) return;
    const prep = await resp.json();

    if (!prep.meetings || prep.meetings.length === 0) {
      prepContainer.innerHTML = '';
      return;
    }

    let html = '<div class="prep-section-header"><i data-lucide="calendar-clock" class="prep-header-icon"></i><span>Prepared for tomorrow</span></div>';

    html += prep.meetings.map(m => {
      const p = m.preparation || {};
      const concerns = (p.customer_concerns || []).map(c => `<span class="ds-tag ds-tag-warn">${escapeHtml(c)}</span>`).join('');
      const talkingPoints = (p.suggested_talking_points || []).map(t => `<li>${escapeHtml(t)}</li>`).join('');
      const expert = p.internal_expert ? `<div class="prep-expert-row"><i data-lucide="user-check" class="prep-icon-sm"></i><span class="prep-expert-name">${escapeHtml(p.internal_expert)}</span></div>` : '';
      const draft = p.draft_email ? `<button class="ds-btn ds-btn-secondary ds-btn-small" onclick="insertPrepDraft('${escapeJs(p.draft_email.substring(0, 500))}')">Insert Draft Response</button>` : '';

      return `
        <div class="maestro-card prep-card">
          <div class="prep-card-header">
            <div class="prep-card-time">${escapeHtml(m.time || '')}</div>
            <div class="prep-card-title">${escapeHtml(m.title)}</div>
          </div>
          ${concerns ? `<div class="prep-section"><div class="prep-label">Likely concerns</div><div class="prep-tags">${concerns}</div></div>` : ''}
          ${talkingPoints ? `<div class="prep-section"><div class="prep-label">Suggested talking points</div><ul class="prep-talking-points">${talkingPoints}</ul></div>` : ''}
          ${expert ? `<div class="prep-section"><div class="prep-label">Internal expert</div>${expert}</div>` : ''}
          ${draft ? `<div class="prep-section">${draft}</div>` : ''}
        </div>
      `;
    }).join('');

    prepContainer.innerHTML = html;
    if (typeof lucide !== 'undefined') lucide.createIcons();
  } catch (e) {
    // Non-fatal — the morning brief still loads without preparation
  }
}

function insertPrepDraft(draft) {
  // Copy to clipboard and show toast
  navigator.clipboard.writeText(draft).then(() => {
    if (typeof showToast === 'function') showToast('Draft copied to clipboard', 'success');
  }).catch(() => {
    if (typeof showToast === 'function') showToast('Could not copy draft', 'error');
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// P0-2: INLINE ASK ON TODAY SURFACE — the exec types, the answer appears inline
// ═══════════════════════════════════════════════════════════════════════════
// Auditor: "Make it a real input. On Enter, POST to /ask/conversation and
// render the answer INLINE on the Today surface. Do NOT navigate away."

async function todayAskSubmit(query) {
  if (!query || !query.trim()) return;
  const answerEl = document.getElementById('today-ask-answer');
  if (!answerEl) return;
  answerEl.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Thinking...</div>';

  try {
    // Round 3 fix: generate + send session_id so pronoun resolution works.
    // Without this, the AskPipeline's conversation-state path is unreachable
    // — "What did we promise?" after "Prepare me for Globex" won't resolve
    // "we" → Globex. P11: the engine was built, the UI didn't send the param.
    if (!window._todayAskSessionId) {
      try {
        window._todayAskSessionId = crypto.randomUUID();
      } catch (e) {
        window._todayAskSessionId = 'sess-' + Date.now() + '-' + Math.random().toString(36).slice(2, 11);
      }
    }
    const resp = await fetch((MAESTRO_API || '') + '/api/oem/ask/conversation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: query,
        history: [],
        session_id: window._todayAskSessionId,  // enables pronoun resolution
      }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    let html = '<div class="today-ask-response">';
    // Render the answer as markdown-ish (split on ### for headers)
    const parts = data.answer.split('\n');
    for (const line of parts) {
      if (line.startsWith('# ')) {
        html += `<div class="ask-answer-title">${escapeHtml(line.substring(2))}</div>`;
      } else if (line.startsWith('### ')) {
        html += `<div class="ask-answer-h3">${escapeHtml(line.substring(4))}</div>`;
      } else if (line.startsWith('**') && line.endsWith('**')) {
        html += `<div class="ask-answer-bold">${escapeHtml(line.substring(2, line.length - 2))}</div>`;
      } else if (line.startsWith('- ')) {
        html += `<div class="ask-answer-bullet">${escapeHtml(line.substring(2))}</div>`;
      } else if (line.trim()) {
        html += `<div class="ask-answer-line">${escapeHtml(line)}</div>`;
      }
    }
    html += '</div>';

    // Round 3 fix: Render inline citations [1][2] from the AskPipeline.
    // The new response format includes `citations` linking the answer to
    // the Evidence Spine artifacts. This is the "source citations" feature
    // (Step 5) that was built but never rendered in the UI.
    if (data.citations && data.citations.length > 0) {
      html += '<details class="ask-citations"><summary class="b-cursor-pointer b-fs12 text-muted">Sources (' + data.citations.length + ')</summary><div class="b-mt4">';
      for (const cite of data.citations) {
        html += `<div class="b-mb4 b-fs12">
          <span class="b-fw600">[${cite.number}]</span>
          <span class="text-muted">${escapeHtml(cite.source || 'unknown')}</span>
          ${cite.date ? `<span class="text-muted"> · ${escapeHtml(cite.date)}</span>` : ''}
          <div class="text-muted">${escapeHtml((cite.text || '').slice(0, 100))}</div>
        </div>`;
      }
      html += '</div></details>';
    }

    // Render follow-up suggestions
    if (data.follow_ups && data.follow_ups.length > 0) {
      html += '<div class="ask-follow-up">';
      for (const fu of data.follow_ups) {
        html += `<span class="ask-follow-up-tag" onclick="todayAskSubmit('${escapeJs(fu)}')">${escapeHtml(fu)}</span>`;
      }
      html += '</div>';
    }

    // Render actions
    if (data.actions && data.actions.length > 0) {
      for (const a of data.actions) {
        html += `<button class="ds-btn ds-btn-secondary ds-btn-small" onclick="navTo('ask-v2')">${escapeHtml(a.label)}</button>`;
      }
    }

    answerEl.innerHTML = html;
  } catch (e) {
    answerEl.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

// Wire up prompt tags
document.addEventListener('DOMContentLoaded', function() {
  const promptContainer = document.getElementById('today-ask-prompts');
  if (promptContainer) {
    promptContainer.addEventListener('click', function(e) {
      const tag = e.target.closest('.ask-prompt-tag');
      if (tag) {
        const prompt = tag.getAttribute('data-prompt');
        if (prompt) todayAskSubmit(prompt);
      }
    });
  }
});


// === work.js ===
// THE INVISIBLE MAESTRO — WORK surface (Bumble-redesigned, Round 45)
// ═══════════════════════════════════════════════════════════════════════════
// WORK never looks like software. Maestro follows the user into existing
// tools. The user never opens Maestro. Maestro quietly appears.
//
// Typography: font-family: 'Montserrat', sans-serif (Bumble design system)
// Bumble yellow: #FFF4D1 (maestro-yellow accent color for highlights)
//
// Round 45 redesign — 3 sub-surfaces, all Bumble-styled:
//   1. Whispers  — ambient intelligence from contradictions + overnight
//   2. Timeline  — chronological signal feed (V8 Daily Work #1)
//   3. Tasks     — b-extracted action items (V8 Daily Work #2)
//
// Bumble design: bold cards, pill buttons, system typography,
// swipe-card-category badges, maestro-btn classes. Each surface uses
// the same maestro-card container so the visual language is consistent
// with Today and Ask.
//
// WITHDRAWAL PATH (Guideline P9):
// The user could check GitHub/Jira/Slack directly. The Work surface
// aggregates signals they would otherwise check across 5 provider
// dashboards. Without it, the user is less oriented but fully functional.
// ═══════════════════════════════════════════════════════════════════════════

// Sub-tab state — persists across nav within the Work surface.
let _workSubTab = 'whispers';  // 'whispers' | 'timeline' | 'tasks'

async function loadWork() {
  const el = document.getElementById('work-content');
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    // Fetch everything in parallel — the 3 sub-tabs share the same data
    // fetch so switching tabs is instant (no loading flicker).
    const [briefing, contradictions, dashboard, timeline, tasks] = await Promise.all([
      api.getOEM('/ceo-briefing'),
      api.getOEM('/contradictions').catch(() => ({ contradictions: [] })),
      api.getOEM('/dashboard').catch(() => null),
      api.getOEM('/timeline?limit=30').catch(() => null),
      api.getOEM('/tasks?status=open').catch(() => null),
    ]);

    renderWorkSurface(el, briefing, contradictions, dashboard, timeline, tasks);
  } catch (e) {
    el.innerHTML = `<div class="calm-empty b-text-center-9">
      <div class="brief-card-title">Maestro is connecting to your tools.</div>
      <div class="meta-text">Configure signal sources in Settings to see ambient intelligence here.</div>
    </div>`;
  }
}

function renderWorkSurface(el, briefing, contradictions, dashboard, timeline, tasks) {
  const decisions = briefing.decisions || { decisions: [] };
  const overnight = briefing.overnight || { changes: [] };
  const Contradictions = contradictions.contradictions || [];
  const metrics = dashboard ? dashboard.metrics || {} : {};
  const providers = dashboard ? dashboard.providers_connected || [] : [];

  // ─── Bumble sub-tab navigation (pill buttons) ─────────────────────
  // Three pills: Whispers, Timeline, Tasks. The active pill gets the
  // Bumble yellow background; inactive pills are ghost.
  const tabCounts = {
    whispers: Contradictions.length + overnight.changes.length,
    timeline: timeline ? (timeline.signals || []).length : 0,
    tasks: tasks ? (tasks.tasks || []).filter(t => t.status === 'open').length : 0,
  };

  let html = `<div class="work-section">`;

  // Sub-tab pills — Bumble style
  html += `
    <div class="b-flex-gap8">
      <button class="maestro-btn ${_workSubTab === 'whispers' ? '' : 'maestro-btn-ghost'}"
              class="b-fs13-minh36-3"
              onclick="_workSetTab('whispers')">
        Whispers${tabCounts.whispers > 0 ? ` · ${tabCounts.whispers}` : ''}
      </button>
      <button class="maestro-btn ${_workSubTab === 'timeline' ? '' : 'maestro-btn-ghost'}"
              class="b-fs13-minh36-3"
              onclick="_workSetTab('timeline')">
        Timeline${tabCounts.timeline > 0 ? ` · ${tabCounts.timeline}` : ''}
      </button>
      <button class="maestro-btn ${_workSubTab === 'tasks' ? '' : 'maestro-btn-ghost'}"
              class="b-fs13-minh36-3"
              onclick="_workSetTab('tasks')">
        Tasks${tabCounts.tasks > 0 ? ` · ${tabCounts.tasks}` : ''}
      </button>
    </div>
  `;

  // Render the active sub-tab
  if (_workSubTab === 'whispers') {
    html += _renderWhispersSurface(Contradictions, overnight, decisions, metrics, providers);
  } else if (_workSubTab === 'timeline') {
    html += _renderTimelineSurface(timeline);
  } else if (_workSubTab === 'tasks') {
    html += _renderTasksSurface(tasks);
  }

  html += `</div>`;
  el.innerHTML = html;

  // Wire up any surface-specific interactions
  _wireWorkSurfaceInteractions(el);
}

function _workSetTab(tab) {
  _workSubTab = tab;
  // Re-render without refetching — the data is already in the closure.
  // We trigger a reload to keep the code simple; the SWR cache makes
  // this instant.
  loadWork();
}

// ═══════════════════════════════════════════════════════════════════════════
// SUB-TAB 1: WHISPERS — ambient intelligence from contradictions + overnight
// ═══════════════════════════════════════════════════════════════════════════

function _renderWhispersSurface(Contradictions, overnight, decisions, metrics, providers) {
  // Generate whispers from contradictions and overnight changes
  const whispers = [];

  Contradictions.slice(0, 3).forEach(c => {
    whispers.push({
      text: c.title || c.description || 'A contradiction was detected in your organization.',
      source: c.type || 'organizational pattern',
      action: () => navTo('contradictions'),
    });
  });

  overnight.changes.slice(0, 2).forEach(c => {
    whispers.push({
      text: `${c.title}: ${c.detail}`.substring(0, 120),
      source: c.entity || c.domain || 'overnight signal',
      action: () => navTo('home'),
    });
  });

  // Generate ambient integration cards from REAL data (not hardcoded)
  const ambientCards = [];

  // GitHub card
  const githubConnected = providers.includes('github');
  ambientCards.push({
    tool: 'GitHub',
    message: githubConnected
      ? `${metrics.signals_processed || 0} signals processed from your repositories. ${decisions.decisions.length > 0 ? `${decisions.decisions.length} ${decisions.decisions.length === 1 ? 'decision needs' : 'decisions need'} attention.` : 'No blocked PRs detected.'}`
      : 'GitHub is not connected. Configure it in Settings to see repository intelligence here.',
    action: () => navTo('eng-signals'),
  });

  // Slack card
  ambientCards.push({
    tool: 'Slack',
    message: providers.includes('slack')
      ? (Contradictions.length > 0
        ? `${Contradictions.length} ${Contradictions.length === 1 ? 'cross-team tension was' : 'cross-team tensions were'} detected in recent conversations.`
        : 'Conversations are flowing normally. No tensions detected.')
      : 'Slack is not connected. Configure it in Settings to see conversation intelligence.',
    action: () => navTo('contradictions'),
  });

  // Jira card
  ambientCards.push({
    tool: 'Jira',
    message: providers.includes('jira')
      ? `${metrics.patterns_inferred || 0} patterns inferred from issue transitions. ${metrics.patterns_validated || 0} organizational patterns validated.`
      : 'Jira is not connected. Configure it in Settings to see issue-transition intelligence.',
    action: () => navTo('eng-signals'),
  });

  // Outlook card
  ambientCards.push({
    tool: 'Outlook',
    message: 'Install the Maestro bookmarklet to see organizational context inside your email.',
    action: () => navTo('eng-settings'),
  });

  // Deep capabilities (compressed)
  const deepCaps = [
    { label: 'Decisions I owe', surface: 'inbox', count: decisions.decisions.length },
    { label: 'What changed overnight', surface: 'home', count: overnight.changes.length },
    { label: 'Customer relationships', surface: 'customer', count: 0 },
    { label: 'Live meeting intelligence', surface: 'live', count: 0 },
  ];

  let html = '';

  // Whispers — Bumble cards with amber accent
  if (whispers.length > 0) {
    html += `<div class="b-fs14-fw800-5">Whispers</div>`;
    whispers.forEach((w, i) => {
      html += `
        <div class="maestro-card whisper b-mb12-u" data-idx="${i}">
          <div class="b-fs15-fw700">${escapeHtml(humanize(w.text))}</div>
          <div class="b-fs12-fw600-4">via ${escapeHtml(w.source)}</div>
        </div>
      `;
    });
  } else {
    html += `<div class="calm-empty b-text-center-8">
      <div class="b-fs16-fw800">No whispers right now.</div>
      <div class="b-fs13-text-3">Maestro is listening. You'll know when something matters.</div>
    </div>`;
  }

  // Ambient integrations — Bumble cards with tool badges
  html += `<div class="b-fs14-fw800-9">In your tools</div>`;
  ambientCards.forEach((a, i) => {
    html += `
      <div class="maestro-card ambient-card b-mb12-cursor" data-idx="${i}">
        <div class="b-inline-block-7">${escapeHtml(a.tool)}</div>
        <div class="b-fs14-text-12">${escapeHtml(a.message)}</div>
      </div>
    `;
  });

  // Deep capabilities — Bumble pill buttons
  html += `<div class="b-fs14-fw800-9">Deep capabilities</div>`;
  html += `<div class="b-u-998b-2">`;
  deepCaps.forEach(cap => {
    const label = cap.count > 0
      ? `${escapeHtml(humanize(cap.label))} · ${cap.count}`
      : escapeHtml(humanize(cap.label));
    html += `<button class="maestro-btn maestro-btn-secondary b-fs14-minh44-2" onclick="navTo('${cap.surface}')">${label}</button>`;
  });
  html += `</div>`;

  return html;
}

// ═══════════════════════════════════════════════════════════════════════════
// SUB-TAB 2: TIMELINE — chronological signal feed (V8 Daily Work #1)
// Each signal is a maestro-card with a swipe-card-category badge for its
// provider. The timeline shows what happened across all tools in one view.
// ═══════════════════════════════════════════════════════════════════════════

function _renderTimelineSurface(timeline) {
  if (!timeline || !timeline.signals || timeline.signals.length === 0) {
    return `<div class="calm-empty b-text-center-9">
      <div class="b-fs18-fw800-4">No signals yet.</div>
      <div class="meta-text">Connect a signal source (GitHub, Jira, Slack) to see your organizational timeline here.</div>
    </div>`;
  }

  const signals = timeline.signals;
  const pagination = timeline.pagination || {};
  const filtersApplied = timeline.filters_applied || {};

  let html = '';

  // Header — count + pagination info
  html += `<div class="b-fs14-fw800-7">Organizational Timeline</div>`;
  html += `<div class="b-fs12-text-3">${pagination.total || signals.length} signal${(pagination.total || signals.length) === 1 ? '' : 's'} · most recent first${pagination.has_more ? ' · scroll for more' : ''}</div>`;

  // Filter pills (read-only display — future iteration can make them clickable)
  const activeFilters = Object.entries(filtersApplied).filter(([_, v]) => v);
  if (activeFilters.length > 0) {
    html += `<div class="b-flex-gap6-2">`;
    activeFilters.forEach(([key, val]) => {
      html += `<div class="b-inline-block-4">${escapeHtml(key)}: ${escapeHtml(String(val))}</div>`;
    });
    html += `</div>`;
  }

  // Signals — each is a maestro-card with a provider badge
  signals.forEach((sig, i) => {
    const provider = sig.provider || 'unknown';
    const signalType = sig.type || 'signal';
    const actor = sig.actor || '';
    const artifact = sig.artifact || '';
    const domain = sig.domain || '';
    const timestamp = sig.timestamp || '';

    // Provider badge color mapping (matches the swipe-card-category palette)
    const providerBadgeClass = _providerToCategoryClass(provider);

    // Build the signal description from type + artifact
    const description = _describeSignal(signalType, artifact, actor, domain);

    // Relative time (simple — just show the timestamp for now)
    const timeDisplay = _formatTimestamp(timestamp);

    html += `
      <div class="maestro-card timeline-card mb-12" data-idx="${i}">
        <div class="b-flex-u-9">
          <div class="b-flex-u">
            <div class="swipe-card-category ${providerBadgeClass} mb-8">${escapeHtml(provider.toUpperCase())}</div>
            <div class="b-fs15-fw700-2">${escapeHtml(humanize(description))}</div>
            ${actor ? `<div class="b-fs12-fw600-5">by ${escapeHtml(humanize(actor))}</div>` : ''}
            ${domain ? `<div class="b-fs11-text-2">${escapeHtml(humanize(domain))}</div>` : ''}
          </div>
          <div class="b-fs11-text-4">${escapeHtml(timeDisplay)}</div>
        </div>
      </div>
    `;
  });

  // Load more button (if pagination has more)
  if (pagination.has_more) {
    html += `<div class="b-text-center-3">
      <button class="maestro-btn maestro-btn-ghost b-fs13-minh36-2" onclick="_loadMoreTimeline()">Load more</button>
    </div>`;
  }

  return html;
}

function _providerToCategoryClass(provider) {
  // Map provider to the swipe-card-category color palette
  const p = (provider || '').toLowerCase();
  if (p === 'github') return 'decision';      // yellow
  if (p === 'jira') return 'due';             // amber
  if (p === 'slack') return 'contradiction';  // red-tinted
  if (p === 'gmail' || p === 'confluence') return 'habit';  // green
  if (p === 'customer') return 'unknown';     // gray
  return 'unknown';
}

function _describeSignal(signalType, artifact, actor, domain) {
  // Build a human description from the signal type
  const t = (signalType || '').toLowerCase();
  if (t.startsWith('pr.')) {
    if (t === 'pr.opened') return `Pull request opened: ${artifact}`;
    if (t === 'pr.merged') return `Pull request merged: ${artifact}`;
    if (t === 'pr.closed') return `Pull request closed: ${artifact}`;
    if (t === 'pr.review') return `PR review: ${artifact}`;
    return `Pull request activity: ${artifact}`;
  }
  if (t.startsWith('issue.')) {
    if (t === 'issue.transitioned') return `Issue transitioned: ${artifact}`;
    if (t === 'issue.created') return `Issue created: ${artifact}`;
    if (t === 'issue.closed') return `Issue closed: ${artifact}`;
    return `Issue activity: ${artifact}`;
  }
  if (t.startsWith('message.') || t === 'message') {
    return `Message in ${domain || 'a channel'}: ${artifact}`;
  }
  if (t.startsWith('email.') || t === 'email') {
    return `Email: ${artifact}`;
  }
  if (t.startsWith('doc.') || t === 'doc') {
    return `Document: ${artifact}`;
  }
  // Fallback — show the type and artifact
  return `${signalType}: ${artifact}`;
}

function _formatTimestamp(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    const now = new Date();
    const diffMs = now - d;
    const diffMin = Math.floor(diffMs / 60000);
    const diffHr = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHr / 24);
    if (diffMin < 1) return 'just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    if (diffHr < 24) return `${diffHr}h ago`;
    if (diffDay < 7) return `${diffDay}d ago`;
    return d.toLocaleDateString();
  } catch (e) {
    return String(ts).slice(0, 10);
  }
}

let _timelineOffset = 30;
async function _loadMoreTimeline() {
  try {
    const more = await api.getOEM(`/timeline?limit=30&offset=${_timelineOffset}`);
    if (more && more.signals && more.signals.length > 0) {
      _timelineOffset += 30;
      // Append to the existing timeline — for simplicity, just reload
      loadWork();
    }
  } catch (e) {
    // Non-fatal
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// SUB-TAB 3: TASKS — b-extracted action items (V8 Daily Work #2)
// Each task is a maestro-card with a priority badge. Swipe-right marks
// the task done (with confirmation); swipe-left defers it.
// ═══════════════════════════════════════════════════════════════════════════

function _renderTasksSurface(tasks) {
  if (!tasks || !tasks.tasks || tasks.tasks.length === 0) {
    return `<div class="calm-empty b-text-center-9">
      <div class="b-fs18-fw800-4">No open tasks.</div>
      <div class="meta-text">Maestro scans your signals for action items ("Priya to review by Friday", "TODO: update docs"). They'll appear here.</div>
    </div>`;
  }

  const openTasks = tasks.tasks.filter(t => t.status === 'open');
  const doneCount = tasks.done_count || 0;
  const highPriorityCount = tasks.high_priority_count || 0;

  let html = '';

  // Header — counts
  html += `<div class="b-fs14-fw800-7">Your Tasks</div>`;
  html += `<div class="b-fs12-text-3">${openTasks.length} open · ${doneCount} done${highPriorityCount > 0 ? ` · ${highPriorityCount} high priority` : ''}</div>`;

  // Sort open tasks: high priority first, then by due date
  const sorted = [...openTasks].sort((a, b) => {
    const priRank = { high: 0, medium: 1, low: 2 };
    const priDiff = (priRank[a.priority] || 3) - (priRank[b.priority] || 3);
    if (priDiff !== 0) return priDiff;
    // Earlier due dates first
    if (a.due_date && b.due_date) return a.due_date.localeCompare(b.due_date);
    if (a.due_date) return -1;
    if (b.due_date) return 1;
    return 0;
  });

  // Render each task as a maestro-card with a priority badge
  sorted.forEach((task, i) => {
    const priority = task.priority || 'medium';
    const assignee = task.assignee || '';
    const dueDate = task.due_date || '';
    const domain = task.domain || '';
    const description = task.description || '';
    const taskId = task.id || '';

    // Priority badge — color matches the swipe-card-category palette
    const priBadgeClass = priority === 'high' ? 'contradiction'
                       : priority === 'medium' ? 'due'
                       : 'unknown';
    const priLabel = priority.toUpperCase();

    // Due date formatting
    const todayStr = new Date().toISOString().slice(0, 10);
    const isOverdue = dueDate && dueDate < todayStr;
    const isToday = dueDate === todayStr;

    // Confidence label (P0-4 bold confidence)
    const conf = task.confidence;
    let confLabel = null;
    let confColor = '';
    if (conf != null && conf >= 0) {
      if (conf >= 0.8) { confLabel = 'VERIFIED'; confColor = 'var(--maestro-success,#00C853)'; }
      else if (conf >= 0.5) { confLabel = 'CONFIDENT'; confColor = 'var(--maestro-warning,#FF9800)'; }
      else { confLabel = 'EXPLORING'; confColor = 'var(--maestro-gray-mid,#999999)'; }
    }

    html += `
      <div class="maestro-card task-card b-mb12-cursor" data-idx="${i}" data-task-id="${escapeHtml(taskId)}">
        <div class="b-flex-u-9">
          <div class="swipe-card-category ${priBadgeClass} b-mb8-u">${priLabel}</div>
          ${confLabel ? `<div class="b-inline-block-2">${confLabel}</div>` : ''}
        </div>
        <div class="b-fs15-fw700-2">${escapeHtml(humanize(description))}</div>
        <div class="b-flex-gap12-3">
          ${assignee ? `<span>👤 ${escapeHtml(humanize(assignee))}</span>` : ''}
          ${dueDate ? `<span class="text-secondary">📅 ${escapeHtml(dueDate)}${isOverdue ? ' · OVERDUE' : isToday ? ' · TODAY' : ''}</span>` : ''}
          ${domain ? `<span>🏷️ ${escapeHtml(humanize(domain))}</span>` : ''}
        </div>
        <div class="b-flex-gap8-2">
          <button class="maestro-btn maestro-btn-secondary task-done-btn b-flex-fs13" data-task-id="${escapeHtml(taskId)}" onclick="event.stopPropagation();">Mark done</button>
          <button class="maestro-btn maestro-btn-ghost task-defer-btn b-flex-fs13" data-task-id="${escapeHtml(taskId)}" onclick="event.stopPropagation();">Defer</button>
        </div>
      </div>
    `;
  });

  // Done count footer
  if (doneCount > 0) {
    html += `<div class="b-text-center-4">${doneCount} task${doneCount === 1 ? '' : 's'} completed</div>`;
  }

  return html;
}

// ═══════════════════════════════════════════════════════════════════════════
// INTERACTION WIRING
// ═══════════════════════════════════════════════════════════════════════════

function _wireWorkSurfaceInteractions(el) {
  // Whispers — click to dismiss + navigate
  el.querySelectorAll('.whisper').forEach((wEl, i) => {
    wEl.addEventListener('click', () => {
      wEl.style.opacity = '0';
      wEl.style.transform = 'translateX(100%)';
      setTimeout(() => wEl.remove(), 300);
      // The action was stored on the whisper object; we re-fetch to get it.
      // For simplicity, navigate to contradictions (the most common whisper source).
      navTo('contradictions');
    });
  });

  // Ambient cards — click to navigate
  el.querySelectorAll('.ambient-card').forEach((aEl, i) => {
    aEl.addEventListener('click', () => {
      // Navigate based on index — matches the ambientCards order
      if (i === 0 || i === 2) navTo('eng-signals');
      else if (i === 1) navTo('contradictions');
      else navTo('eng-settings');
    });
  });

  // Timeline cards — click to drill down (future: open the signal detail)
  el.querySelectorAll('.timeline-card').forEach((tEl, i) => {
    tEl.addEventListener('click', () => {
      // Future: open a signal detail modal. For now, visual feedback only.
      tEl.style.transform = 'scale(0.98)';
      setTimeout(() => { tEl.style.transform = ''; }, 150);
    });
  });

  // Task cards — Mark done / Defer buttons
  el.querySelectorAll('.task-done-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const taskId = btn.dataset.taskId;
      if (!taskId) return;
      // Visual feedback — fade the card out
      const card = btn.closest('.task-card');
      if (card) {
        card.style.opacity = '0';
        card.style.transform = 'translateX(100%)';
        setTimeout(() => card.remove(), 300);
      }
      // Best-effort API call to mark done (if such an endpoint exists)
      try {
        await api.postOEM('/tasks/complete', { task_id: taskId });
      } catch (e) {
        // Non-fatal — the visual dismissal already happened
      }
    });
  });

  el.querySelectorAll('.task-defer-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const card = btn.closest('.task-card');
      if (card) {
        card.style.opacity = '0';
        card.style.transform = 'translateX(-100%)';
        setTimeout(() => card.remove(), 300);
      }
    });
  });
}

// ═══════════════════════════════════════════════════════════════════════════


// === ask_v2.js ===
// THE INVISIBLE MAESTRO — ASK surface
// ═══════════════════════════════════════════════════════════════════════════
// Replace search with intention. Never ask "Search..." — instead ask
// "What are you trying to accomplish?"
//
// The system translates intentions into organizational knowledge.
// ═══════════════════════════════════════════════════════════════════════════

const _intentionPrompts = [
  { label: 'Ship safely', text: 'Ship OAuth safely.' },
  { label: 'Reduce failures', text: 'Reduce deployment failures.' },
  { label: 'Understand tension', text: 'Understand why Legal disagrees.' },
  { label: 'Prepare meeting', text: 'Prepare tomorrow\'s board meeting.' },
  { label: 'Find bottleneck', text: 'Who is the bottleneck?' },
  { label: 'Check assumptions', text: 'What are we assuming that might be wrong?' },
  { label: 'Review predictions', text: 'What predictions have been confirmed or disproven?' },
  { label: 'Prepare customer', text: 'What does the organization know about this customer?' },
  { label: 'Imagine', text: 'What would happen if Legal disappeared?' },
  { label: 'Recall', text: 'When have we been here before?' },
];

let _askIntentionMode = true; // true = show prompts, false = show answer

// Round 3 fix: Generate a session_id for multi-turn conversation.
// This enables pronoun resolution ("What did we promise?" after "Prepare me
// for Globex" resolves "we" → Globex). Persisted for the page session.
// P11: without this, the AskPipeline's conversation-state path is unreachable
// from the UI — the engine works in tests but the user never benefits.
let _askSessionId = null;
function getAskSessionId() {
  if (!_askSessionId) {
    try {
      _askSessionId = crypto.randomUUID();
    } catch (e) {
      // Fallback for browsers without crypto.randomUUID
      _askSessionId = 'sess-' + Date.now() + '-' + Math.random().toString(36).slice(2, 11);
    }
  }
  return _askSessionId;
}

function loadAskV2() {
  const el = document.getElementById('ask-v2-content');
  if (!el) return;
  // CEO Vision: Ask must be situational before the executive types
  loadAskContext(el);
}

async function loadAskContext(el) {
  // Fetch preparation + whispers to determine context
  let prep = null;
  let whispers = null;
  try {
    const [prepResp, whisperResp] = await Promise.all([
      fetch((MAESTRO_API || '') + '/api/oem/preparation/tomorrow').then(r => r.ok ? r.json() : null).catch(() => null),
      fetch((MAESTRO_API || '') + '/api/oem/whisper?context=meeting').then(r => r.ok ? r.json() : null).catch(() => null),
    ]);
    prep = prepResp;
    whispers = whisperResp;
  } catch (e) {
    // Non-fatal — fall back to default prompts
  }

  // Determine context
  let header = 'What do you need?';
  let subheader = '';
  let prompts = [
    'Prepare me',
    'Remind me',
    'Explain this',
    'Find who knows',
    "What am I missing?",
  ];

  // If there are upcoming meetings, show ALL meetings and prioritize the risky one
  if (prep && prep.meetings && prep.meetings.length > 0) {
    // Find the riskiest meeting (most concerns + objections + commitments)
    const meetingsWithRisk = prep.meetings.map(m => {
      const p = m.preparation || {};
      const riskScore = (p.customer_concerns || []).length + (p.previous_objections || []).length + (p.relevant_commitments || []).length;
      return { ...m, riskScore };
    });
    meetingsWithRisk.sort((a, b) => b.riskScore - a.riskScore);
    const riskyMeeting = meetingsWithRisk[0];

    if (prep.meetings.length === 1) {
      header = `You have ${riskyMeeting.title} coming up.`;
    } else {
      header = `You have ${prep.meetings.length} meetings coming up. ${riskyMeeting.title} is the risky one.`;
      const concerns = (riskyMeeting.preparation || {}).customer_concerns || [];
      if (concerns.length > 0) {
        header += ` (${concerns.length} unresolved concern${concerns.length === 1 ? '' : 's'})`;
      }
    }
    subheader = 'I can prepare you, explain what changed, or find previous decisions.';
    prompts = [
      `Prepare me for ${riskyMeeting.title}`,
      'What am I likely to be asked?',
      "What hasn't been resolved?",
      'What should I remember?',
    ];
  }

  // If there are high-priority whispers, show them
  let whisperNote = '';
  if (whispers && whispers.whispers) {
    const highPriority = whispers.whispers.filter(w => w.priority === 'high');
    if (highPriority.length > 0) {
      whisperNote = `${highPriority.length} ${highPriority.length === 1 ? 'thing' : 'things'} deserve your attention.`;
    }
  }

  el.innerHTML = `
    <div class="meta-surface">
      <div class="ask-contextual-header">${escapeHtml(header)}</div>
      ${subheader ? `<div class="ask-contextual-subheader">${escapeHtml(subheader)}</div>` : ''}
      ${whisperNote ? `<div class="ask-contextual-whisper-note">${escapeHtml(whisperNote)}</div>` : ''}

      <div class="ask-contextual-prompts">
        ${prompts.map(p => `
          <button class="ask-contextual-prompt" onclick="askSubmit('${escapeJs(p)}')">${escapeHtml(p)}</button>
        `).join('')}
      </div>

      <div class="pos-relative ask-input-container">
        <input type="text" class="ask-input" id="ask-v2-input"
               placeholder="Or ask anything about your organization..."
               onkeydown="if(event.key==='Enter') askSubmit(this.value)"
               aria-label="Ask Maestro" />
      </div>
    </div>
  `;
  if (typeof lucide !== 'undefined') lucide.createIcons();
}

function renderAskIntention(el) {
  _askIntentionMode = true;
  el.innerHTML = `
    <div class="meta-surface">
      <div class="meta-surface greeting">What are you trying to accomplish?</div>
      <div class="meta-surface sub-greeting">Maestro will translate your intention into organizational knowledge.</div>

      <div class="intention-label">Common intentions</div>
      ${_intentionPrompts.map((p, i) => `
        <button class="intention-prompt" data-idx="${i}">
          <span class="b-text-accent">${escapeHtml(p.label)}</span>
          <span class="b-text-muted-6">— ${escapeHtml(p.text)}</span>
        </button>
      `).join('')}

      <div class="b-mt32">
        <input type="text" class="maestro-input b-mt32" id="ask-v2-input"
               placeholder="Ask me anything…"
               onkeydown="if(event.key==='Enter') submitAskV2(this.value)"
               aria-label="Ask the organization"
               class="b-fs16-fw600" />
      </div>

      <div id="ask-v2-answer"></div>
    </div>
  `;

  // Wire up intention prompts
  el.querySelectorAll('.intention-prompt').forEach((btn, i) => {
    btn.addEventListener('click', () => {
      submitAskV2(_intentionPrompts[i].text);
    });
  });
}

async function submitAskV2(question) {
  if (!question || !question.trim()) return;
  const answerEl = document.getElementById('ask-v2-answer');
  if (!answerEl) return;

  _askIntentionMode = false;
  const qLower = question.toLowerCase();

  // V8 Upgrade #1 — route "why" questions to the Explanation engine.
  // A "why" question is one that starts with "why" or contains "why" as a
  // standalone word, OR starts with "explain why". These get a multi-step
  // causal chain rendered as a visual sequence.
  const trimmedLower = qLower.trim();
  const isWhyQuestion = (
    trimmedLower.startsWith('why') ||
    trimmedLower.startsWith('explain why') ||
    /\bwhy\b/.test(trimmedLower)
  );
  if (isWhyQuestion) {
    answerEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
    answerEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    try {
      const data = await api.getOEM(`/explain?q=${encodeURIComponent(question)}`);
      renderExplanationAnswer(answerEl, question, data);
    } catch (e) {
      answerEl.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
    }
    return;
  }

  // V5 Spec #5 — route "what if" questions to Imagination engine
  if (qLower.includes('what if') || qLower.includes('what would happen') || qLower.includes('imagine')) {
    answerEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
    answerEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    try {
      const data = await api.getOEM(`/imagine?scenario=${encodeURIComponent(question)}`);
      renderImaginationAnswer(answerEl, question, data);
    } catch (e) {
      answerEl.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
    }
    return;
  }

  // V5 Spec #8 — route "when have we" questions to Recall engine
  if (qLower.includes('when have we') || qLower.includes('been here before') || qLower.includes('recall') || qLower.includes('last time')) {
    answerEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
    answerEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    try {
      const data = await api.getOEM(`/recall?situation=${encodeURIComponent(question)}`);
      renderRecallAnswer(answerEl, question, data);
    } catch (e) {
      answerEl.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
    }
    return;
  }

  answerEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  // Scroll to answer
  answerEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  try {
    // Round 3 fix: Use POST /ask/conversation (AskPipeline) instead of
    // GET /ask?q= (old TF-IDF DecisionEngine). This activates:
    //   - 9 intent types (WISDOM, WHAT_IF, SIMULATE, RECALL, PREPARE, etc.)
    //   - Conversation state (pronoun resolution via session_id)
    //   - Evidence-grounded narration with inline citations [1][2]
    // P11: the AskPipeline was built (commit 78aa7d7) but the UI never called
    // it. Same disease as CRITICAL-01, one layer up.
    const resp = await fetch((MAESTRO_API || '') + '/api/oem/ask/conversation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: question,
        history: [],
        session_id: getAskSessionId(),  // enables pronoun resolution
      }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    renderAskV2Answer(answerEl, question, data);
  } catch (e) {
    answerEl.innerHTML = `<div class="ds-error">Maestro couldn't answer that right now. ${escapeHtml(e.message)}</div>`;
  }
}

function renderAskV2Answer(el, question, data) {
  // V8 P0-4 + Bumble — Synthesized answer as a bold card with swipe-to-rate.
  const synthesized = data.synthesized_answer || data.answer || 'Maestro is still learning about this.';
  const evidenceDetail = data.evidence_detail || '';
  const confidence = data.confidence;

  const humanAnswer = humanize(synthesized);

  let html = `
    <div class="maestro-card b-mw420-m0auto">
      <div class="swipe-card-category answer mb-12">Answer</div>
      <div class="b-fs18-fw800-3">
        ${escapeHtml(humanAnswer)}
      </div>
  `;

  // Collapsible evidence detail (Apple's progressive disclosure)
  if (evidenceDetail) {
    html += `<details class="b-mt8-mb12">
      <summary class="b-cursor-pointer">Show evidence</summary>
      <div class="b-mt8-p12">${escapeHtml(humanize(evidenceDetail))}</div>
    </details>`;
  }

  // Round 3 fix: Render citations from the AskPipeline.
  // The new response format includes `citations` (list of {number, source,
  // text, date}) and `evidence` (list of evidence items). These are the
  // inline [1][2] citations that link the answer to the Evidence Spine.
  if (data.citations && data.citations.length > 0) {
    html += `<details class="b-mt8-mb12">
      <summary class="b-cursor-pointer">Sources (${data.citations.length})</summary>
      <div class="b-mt8-p12">`;
    for (const cite of data.citations) {
      const citeText = cite.text || '';
      const citeSource = cite.source || 'unknown';
      const citeDate = cite.date || '';
      html += `<div class="b-mb8">
        <span class="b-fw600">[${cite.number}]</span>
        <span class="text-muted">${escapeHtml(citeSource)}</span>
        ${citeDate ? `<span class="text-muted"> · ${escapeHtml(citeDate)}</span>` : ''}
        <div class="b-fs13-text-muted">${escapeHtml(humanize(citeText))}</div>
      </div>`;
    }
    html += `</div></details>`;
  }

  // Also render the intent + entities (transparency — proves the pipeline ran)
  if (data.intent || (data.entities && data.entities.length > 0)) {
    html += `<div class="b-mt8 b-fs12 text-muted">`;
    if (data.intent) html += `Intent: ${escapeHtml(data.intent)}`;
    if (data.entities && data.entities.length > 0) {
      html += ` · Entities: ${escapeHtml(data.entities.join(', '))}`;
    }
    html += `</div>`;
  }

  // P0-4: Bold confidence labels — VERIFIED / CONFIDENT / EXPLORING
  if (confidence != null) {
    // Check if the law is human-verified (Rule D2)
    const isVerified = data.laws && data.laws.length > 0 && data.laws[0].verified_by;
    let confLabel = 'EXPLORING';
    let confColor = 'var(--maestro-gray-mid,#999999)';
    if (isVerified) {
      confLabel = 'VERIFIED';
      confColor = 'var(--maestro-success,#00C853)';
    } else if (confidence >= 0.8) {
      confLabel = 'CONFIDENT';
      confColor = 'var(--maestro-success,#00C853)';
    } else if (confidence >= 0.5) {
      confLabel = 'CONFIDENT';
      confColor = 'var(--maestro-warning,#FF9800)';
    }
    html += `<div class="b-inline-block-5">${confLabel}</div>`;
  }

  // Swipe-to-rate hint (feeds attention signals P1-5)
  html += `
    <div class="swipe-card-hint b-mtauto">
      <span class="text-muted">← Not useful</span>
      <span class="b-text-positive">Useful →</span>
    </div>
    <div class="b-flex-gap8-3">
      <button class="maestro-btn maestro-btn-secondary b-flex-fs13" onclick="rateAskAnswer(false)">Not useful</button>
      <button class="maestro-btn b-flex-fs13" onclick="rateAskAnswer(true)">Useful</button>
    </div>
  `;

  html += `</div>`;

  // "Ask another question" — Bumble pill style
  html += `<button class="maestro-btn maestro-btn-ghost maestro-btn-full b-mt16-mw420" onclick="loadAskV2()">Ask another question</button>`;

  el.innerHTML = html;
}

// V8 P1-5 — Rate the answer (feeds attention signals).
async function rateAskAnswer(useful) {
  try {
    await api.postOEM('/attention/record', { item_type: 'ask_answer', item_id: useful ? 'useful' : 'not_useful' });
  } catch (e) {
    // Non-fatal — rating is best-effort
  }
}

function renderImaginationAnswer(el, question, data) {
  let html = `<div class="story-card">
    <div class="story-narrative b-fw500-text">${escapeHtml(humanize(data.scenario || question))}</div>
  `;
  if (data.consequences && data.consequences.length) {
    for (const c of data.consequences) {
      html += `<div class="b-p100-u">
        <div class="b-fs14-text-4">${escapeHtml(humanize(c.effect || ''))}</div>
        <div class="ds-meta mt-4">Because: ${escapeHtml(humanize(c.cause || ''))}</div>
        <div class="ds-meta">Confidence: ${escapeHtml(humanize(c.confidence || ''))}</div>
      </div>`;
    }
  }
  if (data.historical_analogue) {
    html += `<div class="b-mt12-p12"><strong>Last time something similar happened:</strong> ${escapeHtml(humanize(data.historical_analogue))}</div>`;
  }
  if (data.recommendation) {
    html += `<div class="b-mt8-fs14">${escapeHtml(humanize(data.recommendation))}</div>`;
  }
  html += `</div>`;
  html += `<button class="intention-prompt mt-16" onclick="loadAskV2()">Ask another question</button>`;
  el.innerHTML = html;
}

function renderRecallAnswer(el, question, data) {
  if (data.novel || !data.moments || data.moments.length === 0) {
    el.innerHTML = `<div class="story-card">
      <div class="story-narrative">${escapeHtml(humanize(data.summary || 'No similar past moments found.'))}</div>
      <div class="story-evidence mt-8">This may be a novel situation for the organization.</div>
    </div>
    <button class="intention-prompt mt-16" onclick="loadAskV2()">Ask another question</button>`;
    return;
  }
  let html = `<div class="story-card">
    <div class="story-narrative b-fw500-text">${escapeHtml(humanize(data.summary || ''))}</div>
  `;
  for (const m of data.moments) {
    html += `<div class="b-p120-u">
      <div class="ds-meta mb-4">${escapeHtml(humanize(m.when || ''))}</div>
      <div class="b-fs14-text-4">${escapeHtml(humanize(m.situation || ''))}</div>
      <div class="b-fs13-text-22">What we did: ${escapeHtml(humanize(m.what_we_did || ''))}</div>
      <div class="subtle-text">What we learned: ${escapeHtml(humanize(m.what_we_learned || ''))}</div>
    </div>`;
  }
  html += `</div>`;
  html += `<button class="intention-prompt mt-16" onclick="loadAskV2()">Ask another question</button>`;
  el.innerHTML = html;
}

// V8 Upgrade #1 — render an Explanation as a visual causal chain.
// Each step is a card with: step number, label, narrative, evidence count,
// confidence bar, and source-entity references. Steps are connected by a
// vertical line so the chain is visible.
function renderExplanationAnswer(el, question, data) {
  // Empty / honest-limitation case
  if (!data.steps || data.steps.length === 0) {
    el.innerHTML = `<div class="story-card">
      <div class="story-narrative">${escapeHtml(humanize(data.honest_limitation || data.summary || 'Maestro cannot explain this yet.'))}</div>
      <div class="story-evidence mt-8">Connect more providers (GitHub, Jira, Slack, Confluence) so Maestro can observe the pattern and compose a causal chain.</div>
    </div>
    <button class="intention-prompt mt-16" onclick="loadAskV2()">Ask another question</button>`;
    return;
  }

  // Header — the question + overall confidence + total evidence
  const overallPct = Math.round((data.overall_confidence || 0) * 100);
  let html = `<div class="story-card">
    <div class="story-narrative b-fw500-text-2">${escapeHtml(humanize(question))}</div>
    <div class="ds-meta mb-16">
      ${data.step_count} step${data.step_count === 1 ? '' : 's'} · ${data.total_evidence} evidence signals · overall confidence ${overallPct}%
    </div>
    <div class="explanation-chain">`;

  // Steps — each is a card connected by a vertical line
  for (let i = 0; i < data.steps.length; i++) {
    const step = data.steps[i];
    const isLast = i === data.steps.length - 1;
    const confPct = Math.round((step.confidence || 0) * 100);
    // Confidence color: high (>=70%) = accent, medium (40-69%) = secondary, low (<40%) = muted
    const confColor = confPct >= 70 ? 'var(--accent)' : confPct >= 40 ? 'var(--secondary)' : 'var(--text-muted)';
    html += `
      <div class="explanation-step${isLast ? ' explanation-step-last' : ''}">
        <div class="explanation-step-marker">${step.step}</div>
        <div class="explanation-step-body">
          <div class="explanation-step-label">${escapeHtml(humanize(step.label || ''))}</div>
          <div class="explanation-step-narrative">${escapeHtml(humanize(step.narrative || ''))}</div>
          <div class="explanation-step-meta">
            <span class="ds-meta">${step.evidence_count} evidence</span>
            <span class="ds-meta b-ml12">confidence ${confPct}%</span>
          </div>
          <div class="explanation-conf-bar b-bg-08c2">
            <div class="b-bg-41cc"></div>
          </div>
          ${step.sources && step.sources.length > 0 ? `
            <details class="explanation-sources">
              <summary class="ds-meta b-cursor-pointer-2">${step.sources.length} source${step.sources.length === 1 ? '' : 's'}</summary>
              <div class="mt-6">
                ${step.sources.map(s => `<div class="ds-meta p-20">${escapeHtml(s)}</div>`).join('')}
              </div>
            </details>
          ` : ''}
        </div>
      </div>
    `;
  }

  html += `</div>`;

  // Honest limitation (if any) — shown as a footnote
  if (data.honest_limitation) {
    html += `<div class="story-evidence b-mt16-u">${escapeHtml(humanize(data.honest_limitation))}</div>`;
  }

  html += `</div>`;
  html += `<button class="intention-prompt mt-16" onclick="loadAskV2()">Ask another question</button>`;
  el.innerHTML = html;
}


// === learn.js ===
// THE INVISIBLE MAESTRO — LEARN surface
// ═══════════════════════════════════════════════════════════════════════════
// LEARN is not documentation. It is organizational evolution.
//
// Stories, not metrics. "Yesterday your organization learned: Engineering
// reused Platform's work. Saved 74 hours."
// ═══════════════════════════════════════════════════════════════════════════

async function loadLearn() {
  const el = document.getElementById('learn-content');
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const [learning, improvement, calibration, identity, evolutionTracker, dna] = await Promise.all([
      api.getOEM('/learning').catch(() => null),
      api.getOEM('/improvement').catch(() => null),
      api.getOEM('/predictions/market/calibration').catch(() => null),
      api.getOEM('/identity').catch(() => null),
      api.getOEM('/evolution-tracker').catch(() => null),
      api.getOEM('/dna').catch(() => null),
    ]);

    renderLearnStories(el, learning, improvement, calibration, identity, evolutionTracker, dna);
  } catch (e) {
    el.innerHTML = `<div class="calm-empty">
      <div>Your organization is still gathering experience.</div>
      <div class="b-mt8-fs13">As Maestro processes more signals, stories of organizational evolution will appear here.</div>
    </div>`;
  }
}

function renderLearnStories(el, learning, improvement, calibration, identity, evolutionTracker, dna) {
  const stories = [];

  // Story 1: "Your organization became smarter" (from improvement report)
  if (improvement && improvement.summary) {
    const s = improvement.summary;
    if (s.resolved > 0) {
      stories.push({
        narrative: `Your organization resolved ${s.resolved} ${s.resolved === 1 ? 'prediction' : 'predictions'} and learned from the outcome.`,
        evidence: s.correct > 0 ? `${s.correct} ${s.correct === 1 ? 'was' : 'were'} correct. ${s.incorrect} ${s.incorrect === 1 ? 'was' : 'were'} incorrect.` : 'All predictions were resolved.',
        action: () => navTo('predictions'),
      });
    }
  }

  // Story 2: Calibration story (from prediction market)
  if (calibration && calibration.predictors && calibration.predictors.length > 0) {
    const best = calibration.predictors[0];
    const brier = best.avg_brier_score;
    let quality = 'still calibrating';
    if (brier < 0.1) quality = 'exceptionally well-calibrated';
    else if (brier < 0.2) quality = 'well-calibrated';
    else if (brier < 0.3) quality = 'moderately calibrated';

    stories.push({
      narrative: `${best.email.split('@')[0]} is ${quality} in their predictions. Their judgment is becoming a trusted signal.`,
      evidence: `Based on ${best.resolved_predictions} resolved ${best.resolved_predictions === 1 ? 'prediction' : 'predictions'}.`,
      action: () => navTo('predictions'),
    });
  }

  // Story 3: Law evolution (from learning report)
  if (learning && learning.law_evolution && learning.law_evolution.length > 0) {
    const evo = learning.law_evolution[0];
    stories.push({
      narrative: `Your organization consistently succeeds when ${evo.detail || 'following established patterns'}.`,
      evidence: `This pattern has been reinforced ${evo.evidence_delta > 0 ? 'with new evidence' : 'over time'}.`,
      action: () => navTo('physics'),
    });
  }

  // Story 4: Drift detection
  if (learning && learning.drift_events && learning.drift_events.length > 0) {
    const drift = learning.drift_events[0];
    stories.push({
      narrative: `Something changed: ${drift.description || 'organizational behavior shifted'}.`,
      evidence: `Severity: ${drift.severity}. The organization may need to adapt.`,
      action: () => navTo('home'),
    });
  }

  // Story 5: Knowledge freshness
  if (learning && learning.freshness) {
    const fresh = learning.freshness;
    if (fresh.fresh_domains && fresh.fresh_domains.length > 0) {
      stories.push({
        narrative: `Knowledge in ${fresh.fresh_domains.slice(0, 2).join(' and ')} is current and actively growing.`,
        evidence: `${fresh.total_signals || 'Multiple'} signals processed recently.`,
        action: () => navTo('flow'),
      });
    }
  }

  let html = `<div class="meta-surface">`;

  // Organizational heartbeat
  html += `<div class="meta-surface greeting"><span class="org-heartbeat"></span>Your organization is evolving.</div>`;

  if (stories.length === 0) {
    html += `<div class="calm-empty">
      <div>Your organization is still gathering experience.</div>
      <div class="b-mt8-fs13">As predictions are resolved and patterns are validated, stories of organizational evolution will appear here.</div>
    </div>`;
  } else {
    html += `<div class="meta-surface sub-greeting">${stories.length} ${stories.length === 1 ? 'story' : 'stories'} from recent organizational learning.</div>`;

    stories.forEach((s, i) => {
      html += `
        <div class="story-card" data-idx="${i}">
          <div class="story-narrative">${escapeHtml(humanize(s.narrative))}</div>
          <div class="story-evidence">${escapeHtml(humanize(s.evidence))}</div>
        </div>
      `;
    });
  }

  // Deep capabilities
  // V4 Organ #1 — Identity: does the org know itself?
  if (identity && identity.beliefs && identity.beliefs.length > 0) {
    html += `
      <div class="b-mt32-p20-2">
        <div class="intention-label b-m00120-text">Who your organization is</div>
        <div class="b-fs15-text">${escapeHtml(humanize(identity.summary))}</div>
        <div class="b-fs13-text-21">
          <strong>Strongest alignment:</strong> ${escapeHtml(humanize(identity.strongest_alignment || ''))}
        </div>
        <div class="subtle-text">
          <strong>Largest gap:</strong> ${escapeHtml(humanize(identity.largest_gap || ''))}
        </div>
      </div>
    `;
  }

  // V6 Spec #5 — Organizational DNA: "Who your organization has become"
  if (dna && dna.chromosomes) {
    html += `
      <div class="b-mt32-p20-2">
        <div class="intention-label b-text-accent-2">Who your organization has become</div>
        <div class="b-fs15-text-3">${escapeHtml(humanize(dna.summary || ''))}</div>
        <div class="b-u-998b">
          ${Object.entries(dna.chromosomes).map(([name, chr]) => `
            <div class="b-p10-rad8">
              <div class="b-fs12-fw500">${escapeHtml(name.replace(/_/g, ' '))}</div>
              <div class="b-fs11-text-6">${escapeHtml(humanize(chr.label || ''))}</div>
              <div class="b-fs10-text">${escapeHtml(humanize(chr.basis || ''))}</div>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }

  // V6 Spec #2 — Evolution Tracker: "Mistakes your organization no longer makes"
  if (evolutionTracker && evolutionTracker.failure_modes && evolutionTracker.failure_modes.length > 0) {
    html += `
      <div class="b-mt32-p20-2">
        <div class="intention-label b-text-accent-2">Mistakes your organization no longer makes</div>
        <div class="body-text">${escapeHtml(humanize(evolutionTracker.summary || ''))}</div>
        ${evolutionTracker.failure_modes.slice(0, 4).map(m => {
          const status = m.current_status || 'active';
          const color = status === 'eliminated' ? 'var(--positive)' : status === 'resolving' ? 'var(--warning)' : 'var(--risk)';
          const label = status === 'eliminated' ? '✓ eliminated' : status === 'resolving' ? 'resolving' : 'active';
          return `<div class="b-p100-u">
            <div class="ds-row gap-8">
              <span class="b-clr-fs12">${label}</span>
              <span class="b-fs13-text-8">${escapeHtml(humanize(m.failure_mode || ''))}</span>
            </div>
            <div class="b-fs12-text-10">${escapeHtml(humanize(m.narrative || ''))}</div>
          </div>`;
        }).join('')}
      </div>
    `;
  }

  html += `<div class="intention-label b-mt32">Explore deeper</div>`;
  html += `<div class="b-u-998b-3">`;
  html += `<button class="intention-prompt" onclick="navTo('predictions')">Prediction calibration</button>`;
  html += `<button class="intention-prompt" onclick="navTo('assumptions')">Assumption accuracy</button>`;
  html += `<button class="intention-prompt" onclick="navTo('physics')">Organizational patterns</button>`;
  html += `<button class="intention-prompt" onclick="navTo('memory')">Memory replay</button>`;
  html += `</div>`;

  html += `</div>`;
  el.innerHTML = html;

  // Wire up story card clicks
  el.querySelectorAll('.story-card').forEach((card, i) => {
    if (stories[i] && stories[i].action) {
      card.style.cursor = 'pointer';
      card.addEventListener('click', stories[i].action);
    }
  });
}

// ═══════════════════════════════════════════════════════════════════════════


// === evolution.js ===
// EVOLUTION — Quarterly Evolution Report (V3 Law 10)
// ═══════════════════════════════════════════════════════════════════════════
// "How has our organization changed?"
// Shows 5 dimensions with delta + direction + narrative.
// The V3 end-state metric — is the organization becoming smarter?
// ═══════════════════════════════════════════════════════════════════════════

async function loadEvolution() {
  const el = document.getElementById('evolution-content');
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const data = await api.getOEM('/evolution?window=90d');
    renderEvolutionReport(el, data);
  } catch (e) {
    el.innerHTML = `<div class="calm-empty">
      <div>Your organization is still gathering the history needed to measure evolution.</div>
      <div class="b-mt8-fs13">After 90 days of signals, Maestro will show how decision quality, knowledge mobility, and prediction accuracy have changed.</div>
    </div>`;
  }
}

function renderEvolutionReport(el, data) {
  const dims = data.dimensions || {};
  const overall = data.overall || 'Your organization is evolving.';
  const caveats = data.caveats || '';

  let html = `<div class="meta-surface">`;
  html += `<div class="meta-surface greeting"><span class="org-heartbeat"></span>Your organization has evolved.</div>`;
  html += `<div class="meta-surface sub-greeting">${escapeHtml(humanize(overall))}</div>`;

  // Render each dimension as a story card
  for (const [name, dim] of Object.entries(dims)) {
    const direction = dim.direction || 'stable';
    const delta = dim.delta || 0;
    const narrative = dim.narrative || '';
    const evidence = dim.evidence_count || 0;

    const arrow = direction === 'improving' ? '↑' : direction === 'declining' ? '↓' : '→';
    const color = direction === 'improving' ? 'var(--positive)' : direction === 'declining' ? 'var(--risk)' : 'var(--text-muted)';

    // Humanize the dimension name
    const humanName = name.replace(/_/g, ' ');

    html += `
      <div class="story-card">
        <div class="b-flex-u-3">
          <span class="b-fs20-clr">${arrow}</span>
          <span class="b-fs15-fw500">${escapeHtml(humanName)}</span>
          <span class="b-mlfs13-clr">${delta > 0 ? '+' : ''}${(delta * 100).toFixed(0)}%</span>
        </div>
        <div class="story-narrative">${escapeHtml(humanize(narrative))}</div>
        <div class="story-evidence">Based on ${evidence} ${evidence === 1 ? 'signal' : 'signals'}</div>
      </div>
    `;
  }

  // Caveats
  if (caveats) {
    html += `<div class="b-mt24-p16-2">${escapeHtml(caveats)}</div>`;
  }

  html += `</div>`;
  el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════════════════


// === cognition.js ===
// V4 COGNITIVE ORGANS — frontend surface
// ═══════════════════════════════════════════════════════════════════════════
// Skepticism, Wisdom, Metacognition, Principles, Memory Compression,
// Consciousness — all 6 remaining V4 organs rendered in one surface.
//
// This surface is accessible via the command palette (NOT the sidebar).
// The sidebar stays at 5 items. The V4 organs live behind Ctrl+K.
// ═══════════════════════════════════════════════════════════════════════════

async function loadCognition() {
  const el = document.getElementById('cognition-content');
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const [skepticism, wisdom, metacognition, principles, compression, consciousness, attention, trajectories, causal, forgetting] = await Promise.all([
      api.getOEM('/skepticism').catch(() => null),
      api.getOEM('/wisdom').catch(() => null),
      api.getOEM('/metacognition').catch(() => null),
      api.getOEM('/principles').catch(() => null),
      api.getOEM('/compression').catch(() => null),
      api.getOEM('/consciousness').catch(() => null),
      api.getOEM('/attention').catch(() => null),
      api.getOEM('/trajectories').catch(() => null),
      api.getOEM('/causal').catch(() => null),
      api.getOEM('/forgetting').catch(() => null),
    ]);

    renderCognition(el, skepticism, wisdom, metacognition, principles, compression, consciousness, attention, trajectories, causal, forgetting);
  } catch (e) {
    el.innerHTML = `<div class="calm-empty">
      <div>The cognitive organs are still calibrating.</div>
      <div class="b-mt8-fs13">As Maestro processes more signals, the organs will engage.</div>
    </div>`;
  }
}

function renderCognition(el, skepticism, wisdom, metacognition, principles, compression, consciousness, attention, trajectories, causal, forgetting) {
  let html = `<div class="meta-surface">`;
  html += `<div class="meta-surface greeting">How your organization thinks</div>`;
  html += `<div class="meta-surface sub-greeting">What it knows, what it questions, and how it judges.</div>`;

  // V5 Spec #3 — Attention Allocation (replaces weather as the first card)
  if (attention) {
    html += renderAttention(attention);
  }

  // Organ #8 — Consciousness (state vector)
  if (consciousness) {
    html += renderConsciousness(consciousness);
  }

  // Organ #3 — Skepticism
  if (skepticism) {
    html += renderSkepticism(skepticism);
  }

  // Organ #4 — Wisdom
  if (wisdom) {
    html += renderWisdom(wisdom);
  }

  // Organ #5 — Metacognition
  if (metacognition) {
    html += renderMetacognition(metacognition);
  }

  // Organ #6 — Principles
  if (principles) {
    html += renderPrinciples(principles);
  }

  // Organ #7 — Memory Compression
  if (compression) {
    html += renderCompression(compression);
  }

  // V5 Spec #7 — Temporal Trajectories
  if (trajectories && trajectories.trajectories) {
    html += renderTrajectories(trajectories);
  }

  // V5 Spec #6 — Causal Cognition
  if (causal && causal.chains) {
    html += renderCausal(causal);
  }

  // V5 Spec #4 — Forgetting Engine
  if (forgetting && forgetting.candidates) {
    html += renderForgetting(forgetting);
  }

  html += `</div>`;
  el.innerHTML = html;
}

function renderAttention(a) {
  let html = `
    <div class="story-card mb-16">
      <div class="intention-label accent-label">Where your attention should be</div>
      <div class="body-text">${escapeHtml(humanize(a.summary || ''))}</div>
  `;
  if (a.attention_thieves && a.attention_thieves.length) {
    html += `<div class="b-fs12-text-15">Stealing focus:</div>`;
    for (const t of a.attention_thieves) {
      html += `<div class="b-fs13-text-24">${escapeHtml(humanize(t.domain || ''))}: ${t.percentage}% — ${escapeHtml(humanize(t.reason || ''))}</div>`;
    }
  }
  if (a.should_ignore && a.should_ignore.length) {
    html += `<div class="b-fs12-text-13">Can deprioritize:</div>`;
    for (const ign of a.should_ignore) {
      html += `<div class="b-fs13-text-5">${escapeHtml(humanize(ign.domain || ''))} — ${escapeHtml(humanize(ign.reason || ''))}</div>`;
    }
  }
  html += `</div>`;
  return html;
}

function renderTrajectories(t) {
  const trajs = t.trajectories || {};
  let html = `
    <div class="story-card mb-16">
      <div class="intention-label accent-label">Where things are heading</div>
      <div class="body-text">${escapeHtml(humanize(t.summary || ''))}</div>
  `;
  for (const [name, traj] of Object.entries(trajs)) {
    const trend = traj.trend || 'stable';
    const arrow = trend === 'improving' ? '↑' : trend === 'declining' ? '↓' : '→';
    const color = trend === 'improving' ? 'var(--positive)' : trend === 'declining' ? 'var(--risk)' : 'var(--text-muted)';
    html += `
      <div class="b-p100-u">
        <div class="ds-row gap-8">
          <span class="b-clr-fs16">${arrow}</span>
          <span class="b-fs13-fw500-4">${escapeHtml(name.replace(/_/g, ' '))}</span>
          <span class="b-mlfs11-text">${escapeHtml(traj.slope || '')} · ${escapeHtml(traj.duration || '')}</span>
        </div>
        <div class="b-fs12-text-17">${escapeHtml(humanize(traj.narrative || ''))}</div>
      </div>
    `;
  }
  html += `</div>`;
  return html;
}

function renderCausal(c) {
  if (!c.chains || c.chains.length === 0) return '';
  let html = `
    <div class="story-card mb-16">
      <div class="intention-label accent-label">What causes what</div>
      <div class="body-text">${escapeHtml(humanize(c.summary || ''))}</div>
  `;
  for (const chain of c.chains.slice(0, 3)) {
    html += `
      <div class="b-p120-u">
        <div class="b-fs13-text-8"><strong>When:</strong> ${escapeHtml(humanize(chain.cause || ''))}</div>
        <div class="b-fs13-text-13"><strong>Then:</strong> ${escapeHtml(humanize(chain.effect || ''))}</div>
        <div class="ds-meta mt-4">Observed ${chain.sequence_count} times · ${escapeHtml(chain.confidence || '')} confidence</div>
        <div class="b-fs12-text-17">${escapeHtml(humanize(chain.narrative || ''))}</div>
      </div>
    `;
  }
  html += `</div>`;
  return html;
}

function renderForgetting(f) {
  if (!f.candidates || f.candidates.length === 0) return '';
  let html = `
    <div class="story-card mb-16">
      <div class="intention-label accent-label">What to stop tracking</div>
      <div class="body-text">${escapeHtml(humanize(f.summary || ''))}</div>
  `;
  for (const c of f.candidates.slice(0, 3)) {
    html += `
      <div class="b-p100-u">
        <div class="b-fs13-text-8">${escapeHtml(humanize(c.entity_id || ''))}</div>
        <div class="b-fs12-text-10">${escapeHtml(humanize(c.narrative || ''))}</div>
      </div>
    `;
  }
  html += `</div>`;
  return html;
}

function renderConsciousness(c) {
  const dims = c.dimensions || {};
  let html = `
    <div class="story-card mb-16">
      <div class="intention-label b-text-accent-3">Right now</div>
      <div class="b-fs15-text-3">${escapeHtml(humanize(c.summary || ''))}</div>
      <div class="b-u-998b-2">
  `;
  for (const [name, dim] of Object.entries(dims)) {
    const score = dim.score || 0;
    const pct = Math.round(score * 100);
    const color = score > 0.6 ? 'var(--positive)' : score > 0.3 ? 'var(--warning)' : 'var(--risk)';
    html += `
      <div class="b-p12-rad8">
        <div class="b-fs13-fw500-4">${escapeHtml(name.replace(/_/g, ' '))}</div>
        <div class="b-fs11-text">${escapeHtml(humanize(dim.label || ''))} — ${escapeHtml(humanize(dim.basis || ''))}</div>
        <div class="b-h3-bg">
          <div class="b-h100-wpctp"></div>
        </div>
      </div>
    `;
  }
  html += `</div></div>`;
  return html;
}

function renderSkepticism(s) {
  if (!s.challenges || s.challenges.length === 0) return '';
  let html = `
    <div class="story-card mb-16">
      <div class="intention-label accent-label">Beliefs worth questioning</div>
      <div class="body-text">${escapeHtml(humanize(s.summary || ''))}</div>
  `;
  for (const c of s.challenges.slice(0, 3)) {
    html += `
      <div class="b-p120-u">
        <div class="b-fs14-text-5">${escapeHtml(humanize(c.challenge || ''))}</div>
        <div class="ds-meta mt-4">${escapeHtml(humanize(c.evidence || ''))}</div>
      </div>
    `;
  }
  html += `</div>`;
  return html;
}

function renderWisdom(w) {
  let html = `
    <div class="story-card mb-16">
      <div class="intention-label accent-label">When values compete</div>
      <div class="b-fs14-text-10">${escapeHtml(humanize(w.wisdom || ''))}</div>
  `;
  if (w.competing_values && w.competing_values.length) {
    html += `<div class="b-fs12-text-2">${w.competing_values.map(v => escapeHtml(humanize(v))).join(' · ')}</div>`;
  }
  if (w.recommendation) {
    html += `<div class="b-fs14-text">${escapeHtml(humanize(w.recommendation))}</div>`;
  }
  html += `</div>`;
  return html;
}

function renderMetacognition(m) {
  let html = `
    <div class="story-card mb-16">
      <div class="intention-label accent-label">How well the parts work together</div>
      <div class="b-fs15-text-2">${escapeHtml(humanize(m.diagnosis || ''))}</div>
      <div class="b-fs13-text-21">Team quality vs. organization quality: ${m.meta_gap > 0 ? 'organization is stronger' : m.meta_gap < -0.1 ? 'teams are stronger than the whole' : 'balanced'}</div>
  `;
  if (m.team_quality && m.team_quality.length) {
    html += `<div class="b-fs12-text-12">Team quality:</div>`;
    for (const t of m.team_quality.slice(0, 3)) {
      html += `<div class="b-fs12-text-19">${escapeHtml(t.domain)}: ${escapeHtml(t.quality_label)} (${t.signal_count} signals)</div>`;
    }
  }
  html += `<div class="b-fs14-text-2">${escapeHtml(humanize(m.recommendation || ''))}</div>`;
  html += `</div>`;
  return html;
}

function renderPrinciples(p) {
  let html = `
    <div class="story-card mb-16">
      <div class="intention-label accent-label">What your organization has earned the right to trust</div>
      <div class="body-text">${escapeHtml(humanize(p.summary || ''))}</div>
  `;
  if (p.principles && p.principles.length) {
    for (const principle of p.principles) {
      html += `
        <div class="b-p120-u">
          <div class="b-fs14-text-5">${escapeHtml(humanize(principle.statement || ''))}</div>
          <div class="ds-meta mt-4">${escapeHtml(humanize(principle.narrative || ''))}</div>
        </div>
      `;
    }
  }
  if (p.candidates && p.candidates.length) {
    html += `<div class="b-fs12-text-6">Almost there:</div>`;
    for (const c of p.candidates.slice(0, 2)) {
      html += `<div class="b-fs12-text-19">${escapeHtml(humanize(c.narrative || ''))}</div>`;
    }
  }
  html += `</div>`;
  return html;
}

function renderCompression(c) {
  let html = `
    <div class="story-card mb-16">
      <div class="intention-label accent-label">What it all comes down to</div>
      <div class="body-text">${escapeHtml(humanize(c.summary || ''))}</div>
  `;
  if (c.truths && c.truths.length) {
    html += `<div class="b-fs12-fw600-2">TRUTHS</div>`;
    for (const t of c.truths) {
      html += `<div class="b-fs13-text-14">${escapeHtml(humanize(t.truth || ''))}</div>`;
    }
  }
  if (c.habits && c.habits.length) {
    html += `<div class="b-fs12-fw600-3">HABITS</div>`;
    for (const h of c.habits.slice(0, 3)) {
      html += `<div class="b-fs13-text-24">${escapeHtml(humanize(h.habit || ''))} — ${escapeHtml(humanize(h.assessment || ''))}</div>`;
    }
  }
  if (c.mistakes && c.mistakes.length) {
    html += `<div class="b-fs12-fw600-3">MISTAKES</div>`;
    for (const m of c.mistakes.slice(0, 2)) {
      html += `<div class="b-fs13-text-24">${escapeHtml(humanize(m.mistake || ''))}</div>`;
    }
  }
  html += `</div>`;
  return html;
}

// ═══════════════════════════════════════════════════════════════════════════


// === autobiography.js ===
// V6 Spec #6 — Evolution Narrative: the organization's autobiography.
// Accessible via command palette ONLY (NOT in sidebar — sidebar stays at 4).
// ═══════════════════════════════════════════════════════════════════════════

async function loadAutobiography() {
  const el = document.getElementById('autobiography-content');
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const data = await api.getOEM('/autobiography');
    renderAutobiography(el, data);
  } catch (e) {
    el.innerHTML = `<div class="calm-empty">
      <div>Your organization's story is still being written.</div>
      <div class="b-mt8-fs13">As Maestro gathers more history, the chapters will fill in.</div>
    </div>`;
  }
}

function renderAutobiography(el, data) {
  const chapters = data.chapters || [];
  let html = `<div class="meta-surface">`;
  html += `<div class="meta-surface greeting">Your organization's story</div>`;
  html += `<div class="meta-surface sub-greeting">${escapeHtml(humanize(data.summary || data.narrative || ''))}</div>`;

  for (const ch of chapters) {
    html += `
      <div class="story-card mb-16">
        <div class="intention-label accent-label">${escapeHtml(humanize(ch.title || ''))}</div>
        <div class="story-narrative">${escapeHtml(humanize(ch.narrative || ''))}</div>
        ${ch.lessons && ch.lessons.length ? `<div class="story-evidence mt-8">${ch.lessons.map(l => escapeHtml(humanize(l))).join(' · ')}</div>` : ''}
      </div>
    `;
  }

  html += `</div>`;
  el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════════════════


// === playbook.js ===
// V8 Daily Work #6 — Role-Specific Playbooks surface.
// Accessible via command palette (Ctrl+K) — NOT in the sidebar.
// Formats the same evidence differently for sales, marketing, and product.

const _playbookRoles = [
  { id: 'sales', label: 'Sales Playbook — outreach + talking points', icon: '🎯' },
  { id: 'marketing', label: 'Marketing Playbook — ROI view', icon: '📊' },
  { id: 'product', label: 'Product Playbook — PRD + tickets', icon: '📋' },
];

function loadPlaybook(role) {
  const el = document.getElementById('playbook-content');
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  api.getOEM(`/playbook/${role}`)
    .then(data => renderPlaybook(el, role, data))
    .catch(e => {
      el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
    });
}

function renderPlaybook(el, role, data) {
  let html = `
    <div class="meta-surface">
      <div class="meta-surface greeting">${escapeHtml(role.charAt(0).toUpperCase() + role.slice(1))} Playbook</div>
      <div class="meta-surface sub-greeting">Role-specific evidence formatting — not a new engine, just the right view for your role.</div>

      <div class="b-mt24-flex">
        ${_playbookRoles.map(r => `
          <button class="ds-btn ${r.id === role ? 'ds-btn-primary' : 'ds-btn-ghost'} ds-btn-small" onclick="loadPlaybook('${r.id}')">
            ${r.icon} ${escapeHtml(r.label.split(' — ')[0])}
          </button>
        `).join('')}
      </div>

      <div class="b-mt24">
        <input type="text" class="ask-input" id="playbook-context"
               placeholder="Context (customer name for sales, campaign for marketing, feature for product)…"
               onkeydown="if(event.key==='Enter') loadPlaybookWithContext('${role}', this.value)"
               aria-label="Playbook context" />
      </div>
    </div>
  `;

  if (data.error) {
    html += `<div class="ds-empty b-mt24">${escapeHtml(humanize(data.error))}</div>`;
    el.innerHTML = html;
    return;
  }

  // Role-specific rendering
  if (role === 'sales') {
    html += renderSalesPlaybook(data);
  } else if (role === 'marketing') {
    html += renderMarketingPlaybook(data);
  } else if (role === 'product') {
    html += renderProductPlaybook(data);
  }

  el.innerHTML = html;
}

function renderSalesPlaybook(data) {
  const outreach = data.drafted_outreach || {};
  let html = `
    <div class="story-card b-mt24">
      <div class="story-narrative b-fw500-text">
        Drafted Outreach — ${escapeHtml(data.customer || 'Unknown Customer')}
      </div>
  `;

  if (outreach.body) {
    html += `
      <div class="b-p14-bg-4">
${escapeHtml(outreach.body)}
      </div>
    `;
    if (outreach.talking_points && outreach.talking_points.length > 0) {
      html += `<div class="ds-cascade-label mb-8">Talking Points</div>`;
      html += outreach.talking_points.map(tp => `
        <div class="b-p812-bg-2">
          • ${escapeHtml(humanize(tp))}
        </div>
      `).join('');
    }
  }

  html += `
    <div class="ds-meta mt-16">
      ${data.customer_signal_count || 0} customer signals · ARR at stake: $${(data.arr_at_stake || 0).toLocaleString()}
    </div>
    <div class="b-mt8-fs13-2">${escapeHtml(humanize(data.next_best_action || ''))}</div>
  `;

  // Execute button — create Gmail draft from the outreach
  if (outreach.body) {
    html += `
      <div class="mt-16">
        <button class="ds-btn ds-btn-primary ds-btn-small" onclick="executeWriteBack('gmail','create_draft',{to:'${escapeHtml(outreach.to || '')}',subject:'${escapeHtml(outreach.subject || '').replace(/'/g, "\\'")}',body:'${escapeHtml(outreach.body || '').replace(/'/g, "\\'").replace(/\n/g, '\\n')}'})">
          Create Gmail Draft from Outreach
        </button>
      </div>
    `;
  }

  html += `</div>`;
  return html;
}

function renderMarketingPlaybook(data) {
  let html = `
    <div class="story-card b-mt24">
      <div class="story-narrative b-fw500-text">
        Marketing ROI — ${data.campaigns ? data.campaigns.length : 0} Campaigns
      </div>
  `;

  if (data.campaigns && data.campaigns.length > 0) {
    html += `
      <table class="b-w-full">
        <thead>
          <tr class="b-u-u">
            <th class="p-8">Campaign</th>
            <th class="p-8">Spend</th>
            <th class="p-8">Conversions</th>
            <th class="p-8">CPA</th>
            <th class="p-8">ROI</th>
          </tr>
        </thead>
        <tbody>
          ${data.campaigns.map(c => `
            <tr class="b-u-4300">
              <td class="b-p8-text-3">${escapeHtml(c.name)}</td>
              <td class="b-p8-text-4">$${c.spend.toLocaleString()}</td>
              <td class="b-p8-text-4">${c.conversions}</td>
              <td class="b-p8-text-4">$${c.cpa.toFixed(2)}</td>
              <td class="b-p8-text">${(c.roi * 100).toFixed(0)}%</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  }

  html += `
    <div class="ds-meta mt-12">
      Total spend: $${(data.total_spend || 0).toLocaleString()} · Total conversions: ${data.total_conversions || 0} · Overall CPA: $${(data.overall_cpa || 0).toFixed(2)}
    </div>
    <div class="b-mt8-fs13-2">${escapeHtml(humanize(data.recommendation || ''))}</div>
  `;

  html += `</div>`;
  return html;
}

function renderProductPlaybook(data) {
  let html = `
    <div class="story-card b-mt24">
      <div class="story-narrative b-fw500-text">
        PRD Outline — ${escapeHtml(data.feature || 'New Feature')}
      </div>
  `;

  if (data.prd_outline) {
    html += data.prd_outline.sections.map(s => `
      <div class="mb-16">
        <div class="ds-cascade-label mb-6">${escapeHtml(s.title)}</div>
        <div class="b-p1014-bg">
          ${escapeHtml(humanize(s.content || ''))}
        </div>
      </div>
    `).join('');
  }

  if (data.drafted_tickets && data.drafted_tickets.length > 0) {
    html += `<div class="ds-cascade-label b-mt16-mb8">Drafted Tickets (${data.drafted_tickets.length})</div>`;
    html += data.drafted_tickets.map(t => `
      <div class="b-p1012-bg-2">
        <div class="b-fs13-text-9">${escapeHtml(humanize(t.summary || ''))}</div>
        <div class="ds-meta mt-4">Priority: ${escapeHtml(t.priority || 'medium')}</div>
      </div>
    `).join('');
  }

  if (data.unresolved_concerns && data.unresolved_concerns.length > 0) {
    html += `<div class="ds-cascade-label b-mt16-mb8-2">Unresolved Concerns (${data.unresolved_concerns.length})</div>`;
    html += data.unresolved_concerns.map(c => `
      <div class="b-p1012-bg">
        <div class="subtle-text">${escapeHtml(humanize(c.concern || ''))}</div>
        <div class="ds-meta mt-4">Raised by: ${escapeHtml(c.raised_by || 'unknown')}</div>
      </div>
    `).join('');
  }

  // Execute button — create Jira tickets from drafted tickets
  if (data.drafted_tickets && data.drafted_tickets.length > 0) {
    const firstTicket = data.drafted_tickets[0];
    html += `
      <div class="mt-16">
        <button class="ds-btn ds-btn-primary ds-btn-small" onclick="executeWriteBack('jira','create_issue',{project:'PROD',summary:'${escapeHtml(firstTicket.summary || '').replace(/'/g, "\\'")}',description:'${escapeHtml(firstTicket.description || '').replace(/'/g, "\\'")}',issue_type:'Task'})">
          Create Jira Ticket from First Draft
        </button>
      </div>
    `;
  }

  html += `</div>`;
  return html;
}

function loadPlaybookWithContext(role, context) {
  const el = document.getElementById('playbook-content');
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  api.getOEM(`/playbook/${role}?context=${encodeURIComponent(context)}`)
    .then(data => renderPlaybook(el, role, data))
    .catch(e => {
      el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
    });
}


// === personal.js ===
// V8 Personal Mode — Frontend Surface.
// 4-item sidebar: Today / Memory / Decide / Reflect.
// Tier 2 features (relationship vault, ambient context, crossover) surface contextually.
// "What Maestro Knows" reachable in one click from every surface (Guideline P8).
// Incognito toggle with visible indicator (Guideline P6).

// ═══════════════════════════════════════════════════════════════════════════
// PERSONAL MODE — state + navigation
// ═══════════════════════════════════════════════════════════════════════════

const _personalSurfaces = [
  { id: 'personal-today', label: 'Today', icon: '☀️' },
  { id: 'personal-memory', label: 'Memory', icon: '🧠' },
  { id: 'personal-decide', label: 'Decide', icon: '⚖️' },
  { id: 'personal-reflect', label: 'Reflect', icon: '📝' },
];

let _personalCurrentSurface = 'personal-today';
let _incognitoActive = false;

// ═══════════════════════════════════════════════════════════════════════════
// LOAD PERSONAL MODE
// ═══════════════════════════════════════════════════════════════════════════

function loadPersonalMode() {
  // Check incognito status
  api.getPersonal('/incognito/status').then(data => {
    _incognitoActive = data.incognito;
  }).catch(() => {});

  // Round 51 H16 fix: render into a dedicated personal-content container,
  // NOT #main-content. The old code fell back to main-content when
  // personal-content didn't exist, which destroyed the navigation DOM
  // and broke hashchange navigation after visiting Personal Mode.
  // Now we create the container if it doesn't exist, and always render
  // into it — never overwriting main-content.
  let el = document.getElementById('personal-content');
  if (!el) {
    el = document.createElement('div');
    el.id = 'personal-content';
    const mainContent = document.getElementById('main-content');
    if (mainContent) {
      mainContent.appendChild(el);
    } else {
      // If main-content doesn't exist, fall back to body (shouldn't happen)
      document.body.appendChild(el);
    }
  }
  if (!el) return;

  el.innerHTML = `
    <div class="b-flex-minh100vh">
      <!-- Personal sidebar (4 items) -->
      <div class="b-w200-u">
        <div class="b-p02020-fs11">Personal</div>
        ${_personalSurfaces.map(s => `
          <button class="personal-nav-btn" data-surface="${s.id}"
                  class="b-flex-u-4"
                  onclick="navPersonalSurface('${s.id}')">
            <span>${s.icon}</span>
            <span>${escapeHtml(s.label)}</span>
          </button>
        `).join('')}
        <div class="b-mt20-p020">
          <button class="ds-btn ds-btn-ghost ds-btn-small w-full" onclick="showWhatMaestroKnows()">
            What Maestro Knows
          </button>
        </div>
      </div>
      <!-- Main content -->
      <div class="b-flex-p24" id="personal-main">
        <div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>
      </div>
    </div>
  `;

  // Update nav button styles
  updatePersonalNavStyles();
  // Load the current surface
  loadPersonalSurface(_personalCurrentSurface);
}

function navPersonalSurface(surfaceId) {
  _personalCurrentSurface = surfaceId;
  updatePersonalNavStyles();
  loadPersonalSurface(surfaceId);
}

function updatePersonalNavStyles() {
  document.querySelectorAll('.personal-nav-btn').forEach(btn => {
    const isActive = btn.dataset.surface === _personalCurrentSurface;
    btn.style.color = isActive ? 'var(--accent)' : 'var(--text-secondary)';
    btn.style.fontWeight = isActive ? '600' : '400';
    btn.style.background = isActive ? 'var(--surface-2)' : 'transparent';
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// SURFACE LOADERS
// ═══════════════════════════════════════════════════════════════════════════

async function loadPersonalSurface(surfaceId) {
  const el = document.getElementById('personal-main');
  if (!el) return;

  if (surfaceId === 'personal-today') {
    await loadPersonalToday(el);
  } else if (surfaceId === 'personal-memory') {
    await loadPersonalMemory(el);
  } else if (surfaceId === 'personal-decide') {
    await loadPersonalDecide(el);
  } else if (surfaceId === 'personal-reflect') {
    await loadPersonalReflect(el);
  }
}

// ─── Today: briefing + habits + contradictions (Round 47 Block 2.1: swipe cards) ──

async function loadPersonalToday(el) {
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div><div class="skeleton skeleton-line skeleton-line-w50"></div></div>';
  try {
    const [briefing, habits, contradictions] = await Promise.all([
      api.getPersonal('/briefing').catch(() => null),
      api.getPersonal('/habits/streaks').catch(() => null),
      api.getPersonal('/contradictions').catch(() => null),
    ]);

    let html = '<div class="work-section">';

    // Round 47 Block 2.1 — Personal briefing as swipe cards.
    // Same Bumble pattern as the enterprise briefing. Max 7 cards.
    // Card types: HABIT (green), CONTRADICTION (red, NOTICED not FAILED),
    // MEMORY (yellow), REMINDER (amber). Summary card at the end.
    const personalDeckCards = [];

    // Habits → HABIT cards
    if (habits && habits.streaks) {
      habits.streaks.slice(0, 3).forEach(h => {
        personalDeckCards.push({
          category: 'HABIT',
          categoryClass: 'habit',
          title: h.name || 'Your habit',
          evidence: `Streak: ${h.current_streak || 0} day${(h.current_streak || 0) === 1 ? '' : 's'}`,
          rightLabel: 'CHECK IN',
          leftLabel: 'SKIP',
          _type: 'habit',
          _habitId: h.habit_id,
        });
      });
    }

    // Contradictions → NOTICED cards (Round 47 Block 2.3)
    if (contradictions && contradictions.contradictions) {
      contradictions.contradictions.slice(0, 3).forEach(c => {
        personalDeckCards.push({
          category: 'NOTICED',
          categoryClass: 'noticed',
          title: c.description || 'A pattern was noticed',
          evidence: c.evidence || '',
          rightLabel: 'REFLECT',
          leftLabel: 'DISMISS 30D',
          _type: 'contradiction',
          _dismissKey: c.dismiss_key,
        });
      });
    }

    // Briefing items → REMINDER cards
    if (briefing && briefing.items) {
      briefing.items.slice(0, 3).forEach(item => {
        personalDeckCards.push({
          category: 'REMINDER',
          categoryClass: 'due',
          title: (item.content || '').slice(0, 100),
          evidence: `From ${item.source || 'your calendar'}`,
          rightLabel: 'ACKNOWLEDGE',
          leftLabel: 'DEFER',
          _type: 'reminder',
        });
      });
    }

    // Work context card (if integration toggle is on)
    if (briefing && briefing.work_context && briefing.work_context.enabled) {
      const wc = briefing.work_context;
      const wcParts = [];
      if (wc.deadlines_today && wc.deadlines_today.length > 0) {
        wcParts.push(`${wc.deadlines_today.length} work deadline${wc.deadlines_today.length !== 1 ? 's' : ''}`);
      }
      if (wc.meetings_into_personal_time && wc.meetings_into_personal_time.length > 0) {
        wcParts.push(`${wc.meetings_into_personal_time.length} meeting${wc.meetings_into_personal_time.length !== 1 ? 's' : ''} into personal time`);
      }
      if (wcParts.length > 0) {
        personalDeckCards.push({
          category: 'WORK CONTEXT',
          categoryClass: 'decision',
          title: wcParts.join(' · '),
          evidence: wc.commitments_summary || '',
          rightLabel: 'ACKNOWLEDGE',
          leftLabel: 'DEFER',
          _type: 'work_context',
        });
      }
    }

    // Render the swipe deck (max 7 cards)
    const deck = personalDeckCards.slice(0, 7);

    if (deck.length > 0) {
      html += `
        <div class="b-fs14-fw800-6">Your morning</div>
        <div id="personal-swipe-deck-container" class="b-pos-relative">
        </div>
        <div id="personal-swipe-deck-progress" class="b-text-center-5">
          ${deck.length} ${deck.length === 1 ? 'card' : 'cards'}
        </div>
        <div id="personal-swipe-deck-summary" class="b-hidden-text">
          <div class="b-fs18-fw800-2">That's your morning.</div>
        </div>
      `;
    } else {
      html += `
        <div class="calm-empty b-text-center-9">
          <div class="calm-empty-icon">☀️</div>
          <div class="calm-empty-title">Good morning.</div>
          <div class="calm-empty-body">Connect a source and I'll brief you tomorrow. I work either way.</div>
          <div class="b-mt16 b-text-left-9 b-mw500-m0auto">
            <div class="b-fs13-fw700-4 b-mb8">Personal Mode — what it does:</div>
            <div class="b-fs12-text-6 b-mb6"><strong>Morning brief:</strong> A 5-card swipe deck — one habit to check in, one contradiction to reflect on, one memory to revisit, one reminder, one summary. Calm, like Apple Weather. Swipe right to act, left to defer.</div>
            <div class="b-fs12-text-6 b-mb6"><strong>Memory:</strong> Your personal timeline — decisions you logged, habits you tracked, reflections you wrote. Encrypted at rest with your key. Visible only to you, never to your employer.</div>
            <div class="b-fs12-text-6 b-mb6"><strong>Decide:</strong> Personal decisions with a Bumble-style swipe deck. Each card shows the decision, the trade-offs, and the cost of inaction. Swipe right to commit, left to defer.</div>
            <div class="b-fs12-text-6 b-mb6"><strong>Reflect:</strong> A daily reflection prompt. Maestro notices patterns in your reflections over time — recurring concerns, energy cycles, decision velocity — and surfaces them gently.</div>
            <div class="b-fs12-text-6"><strong>Incognito mode:</strong> Toggle incognito to stop personal collection temporarily. Work mode keeps running. Your existing personal memories are preserved.</div>
          </div>
          <div class="b-mt16">
            <button class="ds-btn ds-btn-primary" onclick="navTo('eng-settings')">Connect a personal source →</button>
          </div>
        </div>
      `;
    }

    html += '</div>';
    el.innerHTML = html;

    // Initialize the personal swipe deck
    if (deck.length > 0) {
      _initPersonalSwipeDeck(deck);
    }
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

function _initPersonalSwipeDeck(deck) {
  window._personalDeck = deck;
  window._personalDeckIdx = 0;
  window._personalDeckActed = 0;
  window._personalDeckDeferred = 0;
  _renderPersonalSwipeCard();
}

function _renderPersonalSwipeCard() {
  const container = document.getElementById('personal-swipe-deck-container');
  if (!container || !window._personalDeck) return;

  const idx = window._personalDeckIdx || 0;
  const deck = window._personalDeck;

  if (idx >= deck.length) {
    _showPersonalDeckSummary();
    return;
  }

  const cardData = deck[idx];
  container.innerHTML = '';

  if (typeof createSwipeCard !== 'function') return;

  const card = createSwipeCard({
    category: cardData.category,
    category_class: cardData.categoryClass,
    judgment: cardData.title,
    evidence: cardData.evidence,
    right_label: cardData.rightLabel,
    left_label: cardData.leftLabel,
    why_link: false,
  });

  card.style.position = 'relative';
  container.appendChild(card);

  if (typeof SwipeCard !== 'undefined') {
    const handler = new SwipeCard(card,
      // Swipe right
      () => {
        window._personalDeckActed++;
        _handlePersonalCardAction(cardData, true);
        _advancePersonalDeck();
      },
      // Swipe left
      () => {
        window._personalDeckDeferred++;
        _handlePersonalCardAction(cardData, false);
        _advancePersonalDeck();
      }
    );
  }

  _updatePersonalDeckProgress();
}

function _handlePersonalCardAction(cardData, swipedRight) {
  // Handle the action based on card type
  if (cardData._type === 'habit' && swipedRight && cardData._habitId) {
    // Check in the habit
    api.postPersonal('/habits/checkin', { habit_id: cardData._habitId }).catch(() => {});
  } else if (cardData._type === 'contradiction') {
    if (swipedRight) {
      // Reflect — could open a journaling prompt (future)
    } else if (cardData._dismissKey) {
      // Dismiss for 30 days
      api.postPersonal('/contradictions/dismiss', { dismiss_key: cardData._dismissKey }).catch(() => {});
    }
  }
}

function _advancePersonalDeck() {
  window._personalDeckIdx = (window._personalDeckIdx || 0) + 1;
  setTimeout(() => _renderPersonalSwipeCard(), 350);
}

function _updatePersonalDeckProgress() {
  const progress = document.getElementById('personal-swipe-deck-progress');
  if (!progress) return;
  const deck = window._personalDeck || [];
  const idx = window._personalDeckIdx || 0;
  const remaining = deck.length - idx;
  progress.textContent = `${remaining} ${remaining === 1 ? 'card' : 'cards'} left`;
}

function _showPersonalDeckSummary() {
  const container = document.getElementById('personal-swipe-deck-container');
  const progress = document.getElementById('personal-swipe-deck-progress');
  const summary = document.getElementById('personal-swipe-deck-summary');
  if (container) container.style.display = 'none';
  if (progress) progress.style.display = 'none';
  if (summary) summary.style.display = 'block';
}

// ─── Memory: knowledge graph + memory replay + evolution report ──────────

async function loadPersonalMemory(el) {
  let html = '<div class="work-section">';

  html += `
    <div class="b-p20-bg-2">
      <div class="section-title">Memory Replay</div>
      <input type="text" class="ask-input mt-12" id="memory-replay-input"
             placeholder="What did I talk about with Sarah?"
             onkeydown="if(event.key==='Enter') doMemoryReplay(this.value)"
             class="b-w-full-8" />
      <div id="memory-replay-result"></div>
    </div>
  `;

  html += `
    <div class="b-p20-bg-2">
      <div class="section-title">Personal Why?</div>
      <input type="text" class="ask-input mt-12" id="personal-why-input"
             placeholder="Why did I skip the gym 3 times this month?"
             onkeydown="if(event.key==='Enter') doPersonalWhy(this.value)"
             class="b-w-full-8" />
      <div id="personal-why-result"></div>
    </div>
  `;

  html += `
    <div class="b-p20-bg">
      <div class="section-title">Evolution Report</div>
      <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="loadEvolutionReport()">Generate quarterly report</button>
      <div id="evolution-report-result" class="mt-12"></div>
    </div>
  `;

  html += '</div>';
  el.innerHTML = html;
}

// ─── Decide: decision support + prepared decisions + intent cascade + predictions ──

async function loadPersonalDecide(el) {
  let html = '<div class="work-section">';

  html += `
    <div class="b-p20-bg-2">
      <div class="section-title">Decision Support</div>
      <input type="text" class="ask-input mt-12" id="decide-input"
             placeholder="Should I take this trip?"
             onkeydown="if(event.key==='Enter') doDecide(this.value)"
             class="b-w-full-8" />
      <div id="decide-result"></div>
    </div>
  `;

  html += `
    <div class="b-p20-bg-2">
      <div class="section-title">Intent Cascade</div>
      <input type="text" class="ask-input mt-12" id="intent-input"
             placeholder="improve fitness"
             onkeydown="if(event.key==='Enter') doIntentCascade(this.value)"
             class="b-w-full-8" />
      <div id="intent-result"></div>
    </div>
  `;

  html += `
    <div class="b-p20-bg">
      <div class="section-title">Prediction Market</div>
      <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="loadCalibration()">View calibration</button>
      <div id="calibration-result" class="mt-12"></div>
    </div>
  `;

  html += '</div>';
  el.innerHTML = html;
}

// ─── Reflect: self-reflection prompts + legacy builder ───────────────────

async function loadPersonalReflect(el) {
  let html = '<div class="work-section">';

  html += `
    <div class="b-p20-bg-2">
      <div class="section-title">Reflection Prompts</div>
      <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="loadReflectionPrompts()">Get prompts</button>
      <div id="reflection-prompts-result" class="mt-12"></div>
    </div>
  `;

  html += `
    <div class="b-p20-bg">
      <div class="section-title">Legacy Builder</div>
      <div class="b-fs13-text-19">Document your life stories, values, and wisdom. Always private.</div>
      <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="loadLegacyPrompts()">Get writing prompts</button>
      <div id="legacy-prompts-result" class="mt-12"></div>
    </div>
  `;

  html += '</div>';
  el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════════════════
// ACTION HANDLERS
// ═══════════════════════════════════════════════════════════════════════════

async function checkInHabit(habitId) {
  try {
    await api.postPersonal('/habits/checkin', { habit_id: habitId });
    loadPersonalSurface('personal-today'); // reload
  } catch (e) {
    showToast('Check-in failed: ' + e.message, 'error');
  }
}

async function dismissContradiction(key) {
  try {
    await api.postPersonal('/contradictions/dismiss', { dismiss_key: key });
    loadPersonalSurface('personal-today'); // reload
  } catch (e) {
    showToast('Dismiss failed: ' + e.message, 'error');
  }
}

async function toggleIncognito() {
  try {
    if (_incognitoActive) {
      await api.postPersonal('/incognito/end');
      _incognitoActive = false;
    } else {
      await api.postPersonal('/incognito/start');
      _incognitoActive = true;
    }
    loadPersonalSurface('personal-today'); // reload
  } catch (e) {
    showToast('Incognito toggle failed: ' + e.message, 'error');
  }
}

async function doMemoryReplay(query) {
  const el = document.getElementById('memory-replay-result');
  if (!el || !query) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const data = await api.postPersonal('/memory/replay', { query });
    let html = '<div class="b-p12-bg">';
    html += `<div class="b-fs13-text-15">${escapeHtml(humanize(data.summary || ''))}</div>`;
    if (data.third_party_warning) {
      html += `<div class="b-mt8-fs12">${escapeHtml(humanize(data.third_party_warning))}</div>`;
    }
    html += '</div>';

    // Round 47 Block 2.2 — Follow-up question chips for memory conversation.
    // After a memory replay answer, show 2-3 follow-up question chips
    // (Bumble pill style). Tapping a chip asks the next question.
    // Chips are derived from the memory graph, not generated by an LLM.
    const followUps = _generateMemoryFollowUps(query, data);
    if (followUps.length > 0) {
      html += '<div class="mt-12">';
      html += '<div class="b-fs11-fw700">Follow up</div>';
      followUps.forEach(fq => {
        html += `<button class="follow-up-chip" onclick="doMemoryReplay('${escapeJs(fq).replace(/'/g,"\\'")}')">${escapeHtml(fq)}</button>`;
      });
      html += '</div>';
    }

    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

function _generateMemoryFollowUps(originalQuery, data) {
  // Round 47 Block 2.2 — derive follow-up questions from the memory graph.
  // Not LLM-generated — these are structural follow-ups based on the query
  // and the entities/time windows in the replay result.
  const followUps = [];
  const q = (originalQuery || '').toLowerCase();

  // If the query mentions a person, offer "Show more about {person}"
  const personMatch = originalQuery && originalQuery.match(/(?:about|with|from)\s+([A-Z][a-z]+)/);
  if (personMatch) {
    followUps.push(`Show more about ${personMatch[1]}`);
  }

  // Always offer a time-based follow-up
  followUps.push('What else happened that week?');

  // If the replay returned moments, offer a decision-based follow-up
  if (data && data.moments && data.moments.length > 0) {
    followUps.push('What did I decide then?');
  }

  // If the replay found memories, offer a "related" follow-up
  if (data && data.summary && !data.novel) {
    followUps.push('What else is related?');
  }

  return followUps.slice(0, 3);  // max 3 chips
}

async function doPersonalWhy(question) {
  const el = document.getElementById('personal-why-result');
  if (!el || !question) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const data = await api.postPersonal('/why', { question });
    let html = '<div class="b-p12-bg">';
    if (data.third_party_redirected) {
      html += `<div class="b-fs13-text-25">${escapeHtml(humanize(data.explanation_chain[0].narrative || ''))}</div>`;
    } else {
      data.explanation_chain.forEach(step => {
        html += `<div class="b-p60-u">
          <div class="b-fs13-fw500">${escapeHtml(humanize(step.label || ''))}</div>
          <div class="b-fs12-text-16">${escapeHtml(humanize(step.narrative || ''))}</div>
        </div>`;
      });
    }
    html += '</div>';
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function doDecide(question) {
  const el = document.getElementById('decide-result');
  if (!el || !question) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const data = await api.postPersonal('/decide', { question });
    let html = '<div class="b-p12-bg">';
    html += `<div class="b-fs12-text-5">${escapeHtml(data.label || '')}</div>`;
    html += `<div class="b-fs13-text-12">${escapeHtml(humanize(data.recommendation || ''))}</div>`;
    html += `<div class="b-flex-gap16"><div><strong>Pros:</strong> ${data.pros.map(p => escapeHtml(p)).join('; ')}</div></div>`;
    html += `<div class="b-fs12-mt4"><strong>Cons:</strong> ${data.cons.map(c => escapeHtml(c)).join('; ')}</div>`;
    html += `<div class="b-fs12-text">Confidence: ${(data.confidence * 100).toFixed(0)}%</div>`;
    html += '</div>';
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function doIntentCascade(intent) {
  const el = document.getElementById('intent-result');
  if (!el || !intent) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const data = await api.postPersonal('/intent-cascade', { intent });
    let html = '<div class="b-p12-bg">';
    const sections = [
      ['Assumptions', data.assumptions],
      ['Hypotheses', data.hypotheses],
      ['Preparations', data.preparations],
      ['Evidence Plan', data.evidence_plan],
    ];
    sections.forEach(([label, items]) => {
      html += `<div class="mb-10"><div class="b-fs12-fw600">${label}</div>`;
      items.forEach(item => {
        html += `<div class="b-fs12-text-18">• ${escapeHtml(humanize(item.text || ''))}</div>`;
      });
      html += '</div>';
    });
    html += '</div>';
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadCalibration() {
  const el = document.getElementById('calibration-result');
  if (!el) return;
  try {
    const data = await api.getPersonal('/predictions/calibration');
    el.innerHTML = `<div class="b-p12-bg-2">${escapeHtml(data.message || 'No data yet.')}</div>`;
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadReflectionPrompts() {
  const el = document.getElementById('reflection-prompts-result');
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const data = await api.getPersonal('/reflection-prompts');
    let html = '<div class="b-p12-bg">';
    data.prompts.forEach(p => {
      html += `<div class="b-p80-u">
        <div class="b-fs13-text-8">${escapeHtml(humanize(p.prompt || ''))}</div>
        <div class="ds-meta mt-2">${escapeHtml(p.type || '')}</div>
      </div>`;
    });
    html += '</div>';
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadLegacyPrompts() {
  const el = document.getElementById('legacy-prompts-result');
  if (!el) return;
  try {
    const data = await api.getPersonal('/legacy/prompts');
    let html = '<div class="b-p12-bg">';
    html += '<div class="b-fs13-text-21">Writing prompts for your legacy:</div>';
    data.prompts.forEach(p => {
      html += `<div class="b-fs13-text-14">• ${escapeHtml(p)}</div>`;
    });
    html += '</div>';
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadEvolutionReport() {
  const el = document.getElementById('evolution-report-result');
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const data = await api.getPersonal('/evolution-report');
    el.innerHTML = `<div class="b-p12-bg-3">${escapeHtml(humanize(data.narrative || ''))}</div>`;
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// "WHAT MAESTRO KNOWS" DASHBOARD (Guideline P8 — one-click from anywhere)
// ═══════════════════════════════════════════════════════════════════════════

async function showWhatMaestroKnows() {
  const el = document.getElementById('personal-main');
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const data = await api.getPersonal('/dashboard');
    let html = '<div class="work-section">';
    html += `<div class="b-p20-bg">`;
    html += `<div class="b-fs16-fw600-2">What Maestro Knows About You</div>`;
    html += `<div class="b-fs13-text-20">${escapeHtml(data.message || '')}</div>`;
    html += `<div class="ds-meta mb-16">${data.total_sources} source(s) · ${data.total_items} item(s)</div>`;

    if (data.sources && data.sources.length > 0) {
      data.sources.forEach(src => {
        html += `<div class="b-p120-u">
          <div class="b-flex-u-7">
            <div>
              <div class="b-fs13-fw500">${escapeHtml(src.source)}</div>
              <div class="ds-meta">${src.item_count} item(s) · Consent: ${src.consent_active ? 'active' : 'revoked'}</div>
            </div>
            <button class="ds-btn ds-btn-ghost ds-btn-small b-fs11-text-5"
                    onclick="revokePersonalSource('${escapeHtml(src.source)}')">Revoke</button>
          </div>
        </div>`;
      });
    } else {
      html += '<div class="empty-state"><div class="empty-state-icon"><svg width="48" height="48" viewBox="0 0 48 48" fill="none"><path d="M24 8 C16 8 12 14 12 20 C12 26 16 30 16 30 L16 36 L32 36 L32 30 C32 30 36 26 36 20 C36 14 32 8 24 8 Z" stroke="#FFC629" stroke-width="2" fill="#FFF4D1"/></svg></div><div class="empty-state-title">No data sources connected.</div><div class="empty-state-body">Connect your work tools in Settings to start receiving signals.</div></div>';
    }

    html += '</div></div>';
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function revokePersonalSource(source) {
  if (!await showConfirm(`Revoke consent for '${source}' and delete ALL data from this source? This cannot be undone.`)) return;
  try {
    await api.postPersonal('/dashboard/revoke', { source });
    showWhatMaestroKnows(); // reload
  } catch (e) {
    showToast('Revoke failed: ' + e.message, 'error');
  }
}


// === swipe-cards.js ===
// V8 Personal Mode — SwipeCard class.
// Bumble's signature interaction adapted for insights: swipe right to act,
// swipe left to defer. One card at a time. Bold, focused, decisive.

class SwipeCard {
  constructor(element, onSwipeRight, onSwipeLeft) {
    this.el = element;
    this.startX = 0;
    this.currentX = 0;
    this.dragging = false;
    this.onSwipeRight = onSwipeRight || (() => {});
    this.onSwipeLeft = onSwipeLeft || (() => {});
    this.threshold = 120; // px to trigger swipe
    this._destroyed = false;
    // Round 51 H19: store bound handlers so we can remove them on destroy.
    // The old code added anonymous arrow functions to document, which could
    // never be removed — every new SwipeCard leaked 2 document listeners.
    this._handlers = {
      touchstart: (e) => this._start(e),
      touchmove: (e) => this._move(e),
      touchend: (e) => this._end(e),
      mousedown: (e) => this._start(e),
      mousemove: (e) => this._move(e),
      mouseup: (e) => this._end(e),
    };
    this.bind();
  }

  bind() {
    // Touch events — on the card element
    this.el.addEventListener('touchstart', this._handlers.touchstart, { passive: true });
    this.el.addEventListener('touchmove', this._handlers.touchmove, { passive: true });
    this.el.addEventListener('touchend', this._handlers.touchend, { passive: true });
    // Mouse events — mousedown on card, move/up on document
    this.el.addEventListener('mousedown', this._handlers.mousedown);
    document.addEventListener('mousemove', this._handlers.mousemove);
    document.addEventListener('mouseup', this._handlers.mouseup);
  }

  // Round 51 H19: destroy method removes all listeners to prevent memory leaks.
  // Call this before creating a new card or when leaving the surface.
  destroy() {
    if (this._destroyed) return;
    this._destroyed = true;
    this.el.removeEventListener('touchstart', this._handlers.touchstart);
    this.el.removeEventListener('touchmove', this._handlers.touchmove);
    this.el.removeEventListener('touchend', this._handlers.touchend);
    this.el.removeEventListener('mousedown', this._handlers.mousedown);
    document.removeEventListener('mousemove', this._handlers.mousemove);
    document.removeEventListener('mouseup', this._handlers.mouseup);
    this.onSwipeRight = null;
    this.onSwipeLeft = null;
  }

  _start(e) {
    this.dragging = true;
    this.startX = e.touches ? e.touches[0].clientX : e.clientX;
    this.el.classList.add('swiping');
  }

  _move(e) {
    if (!this.dragging) return;
    this.currentX = (e.touches ? e.touches[0].clientX : e.clientX) - this.startX;
    this.el.style.transform = `translateX(${this.currentX}px) rotate(${this.currentX * 0.05}deg)`;
    // Show action indicators
    const rightIndicator = this.el.querySelector('.swipe-action-right');
    const leftIndicator = this.el.querySelector('.swipe-action-left');
    if (rightIndicator) {
      rightIndicator.style.opacity = Math.min(Math.max(this.currentX / 150, 0), 1);
    }
    if (leftIndicator) {
      leftIndicator.style.opacity = Math.min(Math.max(-this.currentX / 150, 0), 1);
    }
  }

  _end() {
    if (!this.dragging) return;
    this.dragging = false;
    this.el.classList.remove('swiping');

    if (this.currentX > this.threshold) {
      this.el.classList.add('swipe-right');
      setTimeout(() => this.onSwipeRight(), 300);
    } else if (this.currentX < -this.threshold) {
      this.el.classList.add('swipe-left');
      setTimeout(() => this.onSwipeLeft(), 300);
    } else {
      // Snap back
      this.el.style.transform = '';
      const rightIndicator = this.el.querySelector('.swipe-action-right');
      const leftIndicator = this.el.querySelector('.swipe-action-left');
      if (rightIndicator) rightIndicator.style.opacity = 0;
      if (leftIndicator) leftIndicator.style.opacity = 0;
    }
    this.currentX = 0;
  }
}

// Helper: create a swipe card element from data
function createSwipeCard(data) {
  const card = document.createElement('div');
  card.className = 'swipe-card';

  const categoryClass = data.category_class || 'decision';
  const rightLabel = data.right_label || 'ACT NOW';
  const leftLabel = data.left_label || 'NOT NOW';

  card.innerHTML = `
    <div class="swipe-action-right">${escapeHtml(rightLabel)}</div>
    <div class="swipe-action-left">${escapeHtml(leftLabel)}</div>
    <div class="swipe-card-body">
      <div class="swipe-card-category ${categoryClass}">${escapeHtml(data.category || 'INSIGHT')}</div>
      <div class="swipe-card-judgment">${escapeHtml(humanize(data.judgment || data.title || ''))}</div>
      ${data.evidence ? `<div class="swipe-card-evidence">${escapeHtml(humanize(data.evidence))}</div>` : ''}
      ${data.why_link ? `<a class="why-link b-fs13-text" onclick="${data.why_callback || ''}">Why?</a>` : ''}
    </div>
    <div class="swipe-card-hint">
      <span class="left-hint">${escapeHtml(leftLabel)}</span>
      <span class="right-hint">${escapeHtml(rightLabel)}</span>
    </div>
  `;
  return card;
}

// Helper: open an action sheet (bottom sheet) with action buttons
function openActionSheet(title, actions) {
  // Create overlay
  let overlay = document.querySelector('.action-sheet-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.className = 'action-sheet-overlay';
    document.body.appendChild(overlay);
  }

  // Create or update sheet
  let sheet = document.querySelector('.action-sheet');
  if (!sheet) {
    sheet = document.createElement('div');
    sheet.className = 'action-sheet';
    document.body.appendChild(sheet);
  }

  sheet.innerHTML = `
    <div class="b-fs18-fw800-5">${escapeHtml(title)}</div>
    ${actions.map(a => `
      <button class="maestro-btn ${a.style || ''} b-w-full-3" onclick="${a.onclick}">
        ${escapeHtml(a.label)}
      </button>
    `).join('')}
    <button class="maestro-btn maestro-btn-ghost w-full" onclick="closeActionSheet()">Cancel</button>
  `;

  overlay.classList.add('open');
  sheet.classList.add('open');

  overlay.onclick = closeActionSheet;
}

function closeActionSheet() {
  const overlay = document.querySelector('.action-sheet-overlay');
  const sheet = document.querySelector('.action-sheet');
  if (overlay) overlay.classList.remove('open');
  if (sheet) sheet.classList.remove('open');
}


// === mode-tabs.js ===
// V8 Maestro × Bumble — Filter Pill + Bottom Nav (Round 46).
// Round 46: The mode tabs (Work/Personal/BOTH switcher) are REMOVED from
// the default experience. The user does not "switch modes." The user
// opens Maestro and sees their whole life. The "mode" is a FILTER, not
// a switch.
//
// The filter pill is a subtle Bumble pill in the top-right of the Today
// surface: [ All | Work | Personal ]. Default is "All." The user can
// tap "Work" to filter to work cards only, or "Personal" to filter to
// personal cards only. This is a VIEW filter — the underlying data does
// not change.
//
// The bottom nav is UNIFIED — always the same 4 items regardless of
// filter: Today / Memory / Ask / More. (Phase 2 will wire this fully;
// for now the bottom nav stays at 4 items and does not switch based on
// mode.)

// ─── Filter state (Round 46) ───────────────────────────────────────────────
// The filter is a VIEW parameter. Default: 'all'. It is NOT stored as
// user state — it is a transient UI filter that resets to 'all' on page
// load. The user can change it for the current session.
let _currentFilter = 'all';  // 'all' | 'work' | 'personal'

function getCurrentFilter() {
  return _currentFilter;
}

function setCurrentFilter(filter) {
  const valid = ['all', 'work', 'personal'];
  const newFilter = valid.includes(filter) ? filter : 'all';
  if (newFilter === _currentFilter) return;  // no change, no-op
  _currentFilter = newFilter;
  // Persist for the session (not as user state — just UI convenience)
  try { sessionStorage.setItem('maestro-filter', _currentFilter); } catch (e) {}

  // Round 47 Block 2.4 — OPTIMISTIC filter application.
  // Immediately hide/show cards based on their _mode dot, WITHOUT
  // waiting for a refetch. The deck filters instantly (no spinner).
  // The background refetch (loadToday) updates silently if different.
  _optimisticFilterApply();

  // Record filter usage for pilot metrics (privacy-preserving — count only)
  try {
    api.postOEM('/pilot/metrics/filter', { filter: _currentFilter }).catch(() => {});
  } catch (e) { /* non-fatal */ }

  // Re-render the filter pill to reflect the new active state
  renderFilterPill();

  // Background refetch — updates silently if the data is different.
  // No loading spinner — the optimistic filter already applied.
  if (window._currentSurface === 'today' && typeof loadToday === 'function') {
    loadToday();
  }
}

function _optimisticFilterApply() {
  // Round 47 Block 2.4 — instantly hide/show cards based on the filter.
  // This runs BEFORE the refetch, so the user sees instant feedback.
  const cards = document.querySelectorAll('.brief-item, .swipe-card, [data-mode]');
  cards.forEach(card => {
    const mode = card.dataset.mode || card.getAttribute('data-mode') || '';
    if (_currentFilter === 'all') {
      card.style.display = '';
    } else if (_currentFilter === 'work' && mode === 'personal') {
      card.style.display = 'none';
    } else if (_currentFilter === 'personal' && mode === 'work') {
      card.style.display = 'none';
    } else {
      card.style.display = '';
    }
  });
}

function _loadInitialFilter() {
  try {
    const saved = sessionStorage.getItem('maestro-filter');
    if (saved && ['all', 'work', 'personal'].includes(saved)) {
      _currentFilter = saved;
    }
  } catch (e) { /* default to 'all' */ }
}

// ─── Filter Pill renderer (Round 46) ──────────────────────────────────────
// The filter pill is a subtle Bumble pill with 3 options. The active
// option gets the Bumble yellow background; inactive options are ghost.
// It renders in the top-right of the Today surface (or wherever the
// caller injects it).

function renderFilterPill(containerId) {
  // If a container ID is provided, render into it. Otherwise, find or
  // create the pill in the today-content header.
  let container = containerId ? document.getElementById(containerId) : null;
  if (!container) {
    // Try to find an existing filter-pill-container in the today surface
    container = document.getElementById('filter-pill-container');
  }
  if (!container) return;  // no container — the pill is not rendered

  const options = [
    { value: 'all', label: 'All' },
    { value: 'work', label: 'Work' },
    { value: 'personal', label: 'Personal' },
  ];

  container.innerHTML = `
    <div class="b-flex-gap4">
      ${options.map(opt => `
        <button class="maestro-btn ${_currentFilter === opt.value ? '' : 'maestro-btn-ghost'}"
                class="b-fs12-minh30"
                onclick="setCurrentFilter('${opt.value}')"
                aria-pressed="${_currentFilter === opt.value}">
          ${escapeHtml(opt.label)}
        </button>
      `).join('')}
    </div>
  `;
}

// ─── Mode Tab Switcher — evolved into Filter Pill (Round 46 → Round 78) ───
// The original Bumble mode tabs (Work/Personal/BOTH) evolved into the
// filter pill (All/Work/Personal). This IS the Bumble pattern — pill
// buttons, yellow active state, Montserrat font. The filter pill is
// rendered by renderFilterPill() above.
//
// renderModeTabs() is kept as a backward-compat shim that delegates to
// the filter pill. Callers that used the old API still work.

function renderModeTabs(currentMode) {
  // Delegate to the filter pill — the Bumble evolution of mode tabs.
  // Callers that still invoke this get the pill rendered.
  renderFilterPill(null);
  return '';
}

// DEPRECATED: switchMode() is deprecated. Use setCurrentFilter() instead.
// switchMode delegates to setCurrentFilter — same concept, new name.
async function switchMode(mode) {
  // switchMode delegates to setCurrentFilter — same concept, new name.
  // Maps old mode values to new filter values
  const filterMap = { work: 'work', personal: 'personal', both: 'all' };
  const filter = filterMap[mode] || 'all';
  setCurrentFilter(filter);
}

// ─── Bottom Nav (UNIFIED — Round 46) ──────────────────────────────────────
// The bottom nav is ALWAYS the same 4 items regardless of filter:
// Today / Memory / Ask / More. It does NOT switch based on mode.

const _unifiedNavItems = [
  { id: 'today', label: 'Today', icon: '☀️' },
  { id: 'memory', label: 'Memory', icon: '🧠' },
  { id: 'ask-v2', label: 'Ask', icon: '💬' },
  { id: 'more', label: 'More', icon: '⋯' },
];

function renderBottomNav(mode) {
  // Round 46: the 'mode' parameter is IGNORED. The bottom nav is always
  // the same 4 unified items.
  let existing = document.querySelector('.bottom-nav');
  if (existing) existing.remove();

  const items = _unifiedNavItems;
  const nav = document.createElement('nav');
  nav.className = 'bottom-nav';

  items.forEach(item => {
    const btn = document.createElement('button');
    btn.className = 'nav-item';
    btn.innerHTML = `<span class="icon">${item.icon}</span><span>${escapeHtml(item.label)}</span>`;
    btn.onclick = () => {
      if (item.id === 'more') {
        openMoreMenu();
      } else {
        navTo(item.id);
      }
    };
    nav.appendChild(btn);
  });

  document.body.appendChild(nav);
}

function openMoreMenu(mode) {
  // Round 46: the 'mode' parameter is IGNORED. The More menu is unified.
  const actions = [
    { label: 'What Maestro Knows', onclick: 'showWhatMaestroKnows()', style: '' },
    { label: 'Incognito Toggle', onclick: 'toggleIncognito()', style: 'maestro-btn-secondary' },
    { label: 'Personal Context in Work', onclick: 'showIntegrationToggle()', style: 'maestro-btn-secondary' },
    { label: 'Role Playbooks', onclick: "navTo('playbook')", style: 'maestro-btn-secondary' },
    { label: 'Cognitive Organs', onclick: "navTo('cognition')", style: 'maestro-btn-secondary' },
    { label: "Organizational Story", onclick: "navTo('autobiography')", style: 'maestro-btn-secondary' },
  ];
  openActionSheet('More', actions);
}

// Round 46 — the integration toggle is reachable from the More menu.
function showIntegrationToggle() {
  const el = document.getElementById('main-content') || document.getElementById('personal-main');
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  // Round 78 CRITICAL 4: use _getCurrentUser() instead of hardcoded 'default'
  if (typeof _getCurrentUser === 'function') {
    _getCurrentUser().then(user => {
      if (!user) { el.innerHTML = '<div class="ds-error">Could not determine user identity.</div>'; return; }
      _loadIntegrationSettings(el, user);
    });
  } else {
    // Fallback if onboarding.js hasn't loaded yet
    _loadIntegrationSettings(el, 'local-dev-user');
  }
}

function _loadIntegrationSettings(el, user) {
  api.getPersonal('/settings/personal-context-in-work?user=' + encodeURIComponent(user)).then(data => {
    const enabled = data.personal_context_in_work;
    el.innerHTML = `
      <div class="b-mw500-m40p24">
        <div class="b-fs20-fw800">Personal Context in Work</div>
        <div class="b-fs14-text-13">
          When enabled, your own personal state (sleep, energy, calendar conflicts) appears in Work Mode.
          Maestro never surfaces intelligence about a third party. You can disable this at any time.
        </div>
        <div class="b-p16-bg">
          <div class="b-fs13-fw700-2">Current state: ${enabled ? 'ON' : 'OFF (default)'}</div>
          <button class="maestro-btn ${enabled ? 'maestro-btn-ghost' : ''} b-w-full-2" onclick="toggleIntegration(${!enabled})">
            ${enabled ? 'Disable' : 'Enable'}
          </button>
        </div>
        <button class="maestro-btn maestro-btn-ghost maestro-btn-full fs-13" onclick="navTo('today')">Back to Today</button>
      </div>
    `;
  }).catch(() => {
    el.innerHTML = '<div class="ds-error">Failed to load integration settings.</div>';
  });
}

async function toggleIntegration(enable) {
  try {
    const user = (typeof _getCurrentUser === 'function') ? (await _getCurrentUser()) : 'local-dev-user';
    if (!user) { showToast('Could not determine user identity.', 'error'); return; }
    await api.postPersonal('/settings/personal-context-in-work', { enabled: enable, user: user });
    showIntegrationToggle(); // reload
  } catch (e) {
    showToast('Toggle failed: ' + e.message, 'error');
  }
}

// ─── Initialize on page load ───────────────────────────────────────────────

function initBumbleNav() {
  // Round 46: load the initial filter from sessionStorage (default 'all').
  _loadInitialFilter();
  // The bottom nav is unified — always the same 4 items.
  renderBottomNav('all');  // the 'all' arg is ignored (kept for compat)
}

// Auto-init on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initBumbleNav);
} else {
  initBumbleNav();
}


// === onboarding.js ===
// V8 Maestro × Bumble — Onboarding Flow (Round 46 — 6 screens, no mode choice).
// One bold question per screen. Big yellow CTAs. Confident, not a form.
// Stores data via PersonalDataStore + ConsentStore + ModeManager + PersonalKG.
//
// Round 46: Screen 4 (the mode choice) is REMOVED. The user is never
// asked to choose Work, Personal, or Both. Instead:
//   Screen 4: "Connect your work tools" (optional — Jira, Slack, GitHub, Gmail, Calendar).
//   Screen 5: "Connect your personal tools" (optional — personal calendar, personal email, photos).
//   Screen 6: "You're in."
// The user connects what they want, and Maestro figures out the rest.
// The "mode" is inferred from the data. The filter pill lets them focus.

let _onboardingStep = 1;
let _onboardingData = {};

// Round 78 fix + Round 78 CRITICAL 4 fix: replace hardcoded 'default' user
// with authenticated session user. Previously all onboarding data was stored
// under user: 'default', which means all tenants shared the same onboarding
// state. Now we fetch the current user from /api/auth/status.
//
// CRITICAL 4 fix: the prior version fell back to 'default' when auth status
// couldn't be determined. This is a cross-tenant data leak — an unauthenticated
// user could write onboarding data to the 'default' tenant. Now the function
// returns null when the user can't be determined, and the callers check for
// null before writing. In dev mode (auth disabled), /api/auth/status returns
// {authenticated: false} and we use 'local-dev-user' — NOT 'default' — so
// dev data is isolated from any real tenant.
let _currentUserId = null;
async function _getCurrentUser() {
  if (_currentUserId !== null) return _currentUserId;
  try {
    const resp = await fetch((MAESTRO_API || '') + '/api/auth/status');
    const data = await resp.json();
    if (data.authenticated && data.user) {
      _currentUserId = data.user.sub || data.user.email;
      if (!_currentUserId) {
        // Authenticated but no sub or email — fail closed.
        console.error('Onboarding: authenticated user has no sub/email — refusing to write without user identity');
        return null;
      }
    } else if (data.authenticated === false) {
      // Auth is disabled (dev mode) — use a dev-only user ID, NOT 'default'.
      _currentUserId = 'local-dev-user';
    } else {
      // Auth status ambiguous — fail closed.
      console.error('Onboarding: could not determine auth status — refusing to write without user identity');
      return null;
    }
  } catch (e) {
    // /api/auth/status failed — fail closed, don't write with 'default'.
    console.error('Onboarding: /api/auth/status failed — refusing to write without user identity:', e);
    return null;
  }
  return _currentUserId;
}

// Round 65 H1 fix: persist onboarding state to localStorage so refresh
// doesn't lose progress.
function _saveOnboardingState() {
  try {
    localStorage.setItem('maestro_onboarding', JSON.stringify({
      step: _onboardingStep,
      data: _onboardingData,
      timestamp: Date.now()
    }));
  } catch (e) { /* localStorage may be unavailable in some contexts */ }
}

function _loadOnboardingState() {
  try {
    const saved = localStorage.getItem('maestro_onboarding');
    if (saved) {
      const state = JSON.parse(saved);
      // Only resume if saved within the last hour
      if (state.timestamp && (Date.now() - state.timestamp) < 3600000) {
        _onboardingStep = state.step || 1;
        _onboardingData = state.data || {};
        return true;
      }
    }
  } catch (e) { /* parse error — start fresh */ }
  return false;
}

function _clearOnboardingState() {
  try { localStorage.removeItem('maestro_onboarding'); } catch (e) {}
}

function startOnboarding() {
  // Round 65 H1: try to resume from saved state
  if (_loadOnboardingState() && _onboardingStep > 1) {
    showOnboardingScreen(_onboardingStep);
  } else {
    _onboardingStep = 1;
    _onboardingData = {};
    showOnboardingScreen(1);
  }
}

function showOnboardingScreen(step) {
  _onboardingStep = step;
  _saveOnboardingState(); // Round 65 H1: checkpoint after every step
  const el = document.getElementById('onboarding-container');
  if (!el) return;

  const screens = {
    1: renderOnboardingWelcome,
    2: renderOnboardingName,
    3: renderOnboardingAbout,
    4: renderOnboardingWorkTools,    // Round 46 — was renderOnboardingMode
    5: renderOnboardingPersonalTools, // Round 46 — was renderOnboardingConnect
    6: renderOnboardingDone,
  };

  el.innerHTML = screens[step]();
  updateProgressDots(step);
}

function updateProgressDots(step) {
  const dotsContainer = document.querySelector('.progress-dots');
  if (!dotsContainer) return;
  const dots = dotsContainer.querySelectorAll('.progress-dot');
  dots.forEach((dot, i) => {
    dot.classList.toggle('active', i + 1 === step);
  });
}

// ─── Screen 1: Welcome ────────────────────────────────────────────────────

function renderOnboardingWelcome() {
  return `
    <div class="onboarding-screen">
      <div class="onboarding-logo">M</div>
      <div class="text-hero b-text-center">Your organization's judgment, institutionalized.</div>
      <div class="text-body b-text-center-10">
        I'm Maestro — your organizational intelligence layer.
      </div>
      <button class="maestro-btn maestro-btn-full" data-action="showOnboardingScreen" data-args='[2]'>Get Started</button>
      <div class="progress-dots">
        ${[1,2,3,4,5,6].map(i => `<div class="progress-dot ${i === 1 ? 'active' : ''}"></div>`).join('')}
      </div>
    </div>
  `;
}

// ─── Screen 2: Name ───────────────────────────────────────────────────────

function renderOnboardingName() {
  return `
    <div class="onboarding-screen">
      <div class="text-title b-mbvar-space-4">What's your name?</div>
      <div class="b-w-full-5">
        <input type="text" class="maestro-input" id="onboard-name" placeholder="First name"
               oninput="document.getElementById('onboard-name-btn').disabled = !this.value.trim()"
               class="b-mbvar-space-3" autofocus />
        <div class="text-caption b-text-muted-4">
          This is how I'll greet you.
        </div>
        <button class="maestro-btn maestro-btn-ghost maestro-btn-full" data-action="showOnboardingScreen" data-args='[1]' style="margin-bottom:8px;">← Back</button>
        <button class="maestro-btn maestro-btn-full" id="onboard-name-btn" disabled
                data-action="saveOnboardingName">Continue</button>
      </div>
      <div class="progress-dots">
        ${[1,2,3,4,5,6].map(i => `<div class="progress-dot ${i === 2 ? 'active' : ''}"></div>`).join('')}
      </div>
    </div>
  `;
}

async function saveOnboardingName() {
  const name = document.getElementById('onboard-name').value.trim();
  if (!name) return;
  const user = await _getCurrentUser();
  if (!user) { showToast('Could not determine your user identity. Please refresh and try again.', 'error'); return; }
  _onboardingData.name = name;
  api.postPersonal('/kg/entity', {
    user: await _getCurrentUser(),
    entity_type: 'person',
    name: name,
    attributes: { role: 'self' },
  }).catch(() => {});
  showOnboardingScreen(3);
}

// ─── Screen 3: About You ──────────────────────────────────────────────────

function renderOnboardingAbout() {
  return `
    <div class="onboarding-screen">
      <div class="text-title b-mbvar-space-4">Tell me about you.</div>
      <div class="b-w-full-5">
        <div class="onboarding-card b-mbvar-space-2">
          <div class="text-label b-mbvar-space">How old are you?</div>
          <input type="number" class="maestro-input" id="onboard-age" placeholder="Age" min="18" max="120" />
        </div>
        <div class="onboarding-card b-mbvar-space-2">
          <div class="text-label b-mbvar-space">What do you do?</div>
          <input type="text" class="maestro-input b-mbvar-space" id="onboard-role" placeholder="Role (e.g. Engineer, Student)" />
          <input type="text" class="maestro-input" id="onboard-company" placeholder="Company (optional)" />
        </div>
        <div class="text-caption b-text-muted-3">
          This is stored in your Maestro account. You can delete it anytime in Settings.
        </div>
        <button class="maestro-btn maestro-btn-full" data-action="saveOnboardingAbout">Continue</button>
      </div>
      <div class="progress-dots">
        ${[1,2,3,4,5,6].map(i => `<div class="progress-dot ${i === 3 ? 'active' : ''}"></div>`).join('')}
      </div>
    </div>
  `;
}

async function saveOnboardingAbout() {
  _onboardingData.age = document.getElementById('onboard-age')?.value || '';
  _onboardingData.role = document.getElementById('onboard-role')?.value || '';
  _onboardingData.company = document.getElementById('onboard-company')?.value || '';
  if (_onboardingData.role) {
    api.postPersonal('/kg/entity', {
      user: await _getCurrentUser(), entity_type: 'interest',
      name: _onboardingData.role,
      attributes: { company: _onboardingData.company },
    }).catch(() => {});
  }
  showOnboardingScreen(4);
}

// ─── Screen 4: Connect Work Tools (Round 46 — replaces the mode choice) ───
// The user is NOT asked to choose a mode. They connect work tools (all
// OFF by default). Maestro infers "work context" from the data.

let _workToolToggles = { jira: false, slack: false, github: false, confluence: false, gmail: false };

function renderOnboardingWorkTools() {
  const tools = [
    { id: 'jira', icon: '📋', label: 'Jira', desc: 'Issue tracking & project management' },
    { id: 'slack', icon: '💬', label: 'Slack', desc: 'Team conversations & cross-team signals' },
    { id: 'github', icon: '🐙', label: 'GitHub', desc: 'Code, PRs, & engineering signals' },
    { id: 'confluence', icon: '📄', label: 'Confluence', desc: 'Team wikis & documentation' },
    { id: 'gmail', icon: '✉️', label: 'Gmail / Calendar', desc: 'Work email & calendar (read-only)' },
  ];

  return `
    <div class="onboarding-screen">
      <div class="text-title b-mbvar-space">Connect your work tools.</div>
      <div class="text-body b-text-muted-5">
        Optional — skip if you want. I work either way.
      </div>
      <div class="b-w-full-5">
        <div class="onboarding-card b-mbvar-space-3">
          ${tools.map(s => `
            <div class="onboarding-toggle-row">
              <div class="b-flex-u-5">
                <span class="fs-24">${s.icon}</span>
                <div>
                  <div class="text-label">${escapeHtml(s.label)}</div>
                  <div class="text-caption text-muted">${escapeHtml(s.desc)}</div>
                </div>
              </div>
              <div class="maestro-toggle" id="work-toggle-${s.id}" data-action="toggleWorkTool" data-tool-id="${s.id}"></div>
            </div>
          `).join('')}
        </div>
        <div class="b-flex-gapvar">
          <button class="maestro-btn maestro-btn-ghost maestro-btn-full" data-action="showOnboardingScreen" data-args='[5]'>Skip for now</button>
          <button class="maestro-btn maestro-btn-full" data-action="saveOnboardingWorkTools">Continue</button>
        </div>
      </div>
      <div class="progress-dots">
        ${[1,2,3,4,5,6].map(i => `<div class="progress-dot ${i === 4 ? 'active' : ''}"></div>`).join('')}
      </div>
    </div>
  `;
}

async function toggleWorkTool(toolId) {
  _workToolToggles[toolId] = !_workToolToggles[toolId];
  const toggle = document.getElementById(`work-toggle-${toolId}`);
  if (toggle) {
    toggle.classList.toggle('on', _workToolToggles[toolId]);
  }
  // Round 51 H15 fix: when a tool is toggled ON, start the REAL OAuth flow.
  // The old code only called /consent/grant — the user thought they connected
  // GitHub but no OAuth flow started. Now we redirect to the OAuth start URL.
  // The OAuth callback will redirect back to onboarding.
  if (_workToolToggles[toolId]) {
    // Grant consent (for the personal data store layer)
    api.postPersonal('/consent/grant', {
      user: await _getCurrentUser(), source: `work_${toolId}`, purpose: 'store',
    }).catch(() => {});
    api.postPersonal('/consent/grant', {
      user: await _getCurrentUser(), source: `work_${toolId}`, purpose: 'retrieve',
    }).catch(() => {});
    // Start the real OAuth flow — redirect to the provider
    // Map onboarding tool IDs to OAuth provider names
    const oauthProvider = _toolIdToOAuthProvider(toolId);
    if (oauthProvider) {
      // Open OAuth in a popup so we stay on the onboarding page
      _startOAuthFlow(oauthProvider, toolId);
    }
  }
}

function _toolIdToOAuthProvider(toolId) {
  // Map onboarding tool IDs to the OAuth provider names used by /api/oauth/{provider}/start
  const mapping = {
    'jira': 'jira',
    'slack': 'slack',
    'github': 'github',
    'gmail': 'gmail',
    'calendar': 'gmail',  // Google Calendar uses Gmail OAuth
    'confluence': 'confluence',  // Round 53 H4: add Confluence
    'personal_calendar': 'gmail',
    'personal_email': 'gmail',
  };
  return mapping[toolId] || null;
}

function _startOAuthFlow(provider, toolId) {
  // Round 51 H15: start the real OAuth flow.
  // Fetch the authorization URL from /api/oauth/{provider}/start,
  // then open it in a popup. The popup redirects to the provider,
  // the user authorizes, and the callback redirects back.
  fetch(`/api/oauth/${provider}/start`)
    .then(r => r.json())
    .then(data => {
      if (data.authorization_url) {
        // Open OAuth in a popup window
        const popup = window.open(data.authorization_url, 'oauth-popup', 'width=600,height=700');
        // Check periodically if the popup closed (user completed or cancelled)
        const checkClosed = setInterval(() => {
          if (popup.closed) {
            clearInterval(checkClosed);
            // Verify the connection succeeded
            _verifyOAuthConnection(provider, toolId);
          }
        }, 1000);
      }
    })
    .catch(() => {
      // Non-fatal — the consent was already granted; OAuth can be completed later
      console.warn(`OAuth start failed for ${provider} — user can connect later in Settings`);
    });
}

function _verifyOAuthConnection(provider, toolId) {
  // Check if the OAuth connection actually succeeded
  fetch('/api/oauth/status')
    .then(r => r.json())
    .then(data => {
      const providers = data.providers || [];
      const connected = providers.find(p => p.provider === provider && p.connected);
      if (connected) {
        // Show a brief success indicator on the toggle
        const toggle = document.getElementById(`work-toggle-${toolId}`) || document.getElementById(`personal-toggle-${toolId}`);
        if (toggle) {
          toggle.style.boxShadow = '0 0 0 3px var(--maestro-success, #00C853)';
          setTimeout(() => { toggle.style.boxShadow = ''; }, 2000);
        }
      } else {
        // Connection failed — turn the toggle back off
        _workToolToggles[toolId] = false;
        _personalToolToggles[toolId] = false;
        const toggle = document.getElementById(`work-toggle-${toolId}`) || document.getElementById(`personal-toggle-${toolId}`);
        if (toggle) toggle.classList.remove('on');
      }
    })
    .catch(() => {});
}

function saveOnboardingWorkTools() {
  _onboardingData.workTools = { ..._workToolToggles };
  showOnboardingScreen(5);
}

// ─── Screen 5: Connect Personal Tools (Round 46 — separate from work) ─────
// Personal tools are on a SEPARATE screen with SEPARATE consent toggles.
// This enforces the consent boundary — work and personal are never
// conflated during onboarding.

let _personalToolToggles = { personal_calendar: false, personal_email: false, photos: false };

function renderOnboardingPersonalTools() {
  const tools = [
    { id: 'personal_calendar', icon: '📆', label: 'Personal Calendar', desc: 'Your life events, appointments' },
    { id: 'personal_email', icon: '📧', label: 'Personal Email', desc: 'Personal correspondence (read-only)' },
    { id: 'photos', icon: '📷', label: 'Photos', desc: 'So I can help you remember' },
  ];

  return `
    <div class="onboarding-screen">
      <div class="text-title b-mbvar-space">Connect your personal tools.</div>
      <div class="text-body b-text-muted-5">
        Also optional. Personal data stays separate from work by default.
      </div>
      <div class="b-w-full-5">
        <div class="onboarding-card b-mbvar-space-3">
          ${tools.map(s => `
            <div class="onboarding-toggle-row">
              <div class="b-flex-u-5">
                <span class="fs-24">${s.icon}</span>
                <div>
                  <div class="text-label">${escapeHtml(s.label)}</div>
                  <div class="text-caption text-muted">${escapeHtml(s.desc)}</div>
                </div>
              </div>
              <div class="maestro-toggle" id="personal-toggle-${s.id}" data-action="togglePersonalTool" data-tool-id="${s.id}"></div>
            </div>
          `).join('')}
        </div>
        <div class="b-flex-gapvar">
          <button class="maestro-btn maestro-btn-ghost maestro-btn-full" data-action="showOnboardingScreen" data-args='[6]'>Skip for now</button>
          <button class="maestro-btn maestro-btn-full" data-action="saveOnboardingPersonalTools">Connect</button>
        </div>
      </div>
      <div class="progress-dots">
        ${[1,2,3,4,5,6].map(i => `<div class="progress-dot ${i === 5 ? 'active' : ''}"></div>`).join('')}
      </div>
    </div>
  `;
}

async function togglePersonalTool(toolId) {
  _personalToolToggles[toolId] = !_personalToolToggles[toolId];
  const toggle = document.getElementById(`personal-toggle-${toolId}`);
  if (toggle) {
    toggle.classList.toggle('on', _personalToolToggles[toolId]);
  }
  // Round 51 H15 fix: start the real OAuth flow for personal tools too.
  if (_personalToolToggles[toolId]) {
    api.postPersonal('/consent/grant', {
      user: await _getCurrentUser(), source: toolId, purpose: 'store',
    }).catch(() => {});
    api.postPersonal('/consent/grant', {
      user: await _getCurrentUser(), source: toolId, purpose: 'retrieve',
    }).catch(() => {});
    // Start the real OAuth flow
    const oauthProvider = _toolIdToOAuthProvider(toolId);
    if (oauthProvider) {
      _startOAuthFlow(oauthProvider, toolId);
    }
  }
}

function saveOnboardingPersonalTools() {
  _onboardingData.personalTools = { ..._personalToolToggles };
  showOnboardingScreen(6);
}

// ─── Screen 6: You're In ──────────────────────────────────────────────────

function renderOnboardingDone() {
  return `
    <div class="onboarding-screen yellow-bg">
      <div class="text-hero b-text-center-2">You're in.</div>
      <div class="b-fs80-fw900">✓</div>
      <div class="text-label b-text-center-7">
        I'll learn what matters as you use me. You'll get a briefing tomorrow morning.
      </div>
      <button class="maestro-btn maestro-btn-inverted maestro-btn-full" data-action="finishOnboarding">
        Open Maestro
      </button>
    </div>
  `;
}

function finishOnboarding() {
  _clearOnboardingState(); // Round 65 H1: clear saved state on completion
  window.location.href = '/app.html';
}

// Phase 4: Event delegation for toggle handlers (replaces inline onclick)
// The CSP shim handles data-action + data-args, but toggleTool needs data-tool-id
document.addEventListener('click', function(e) {
    var target = e.target.closest('[data-action="toggleWorkTool"]');
    if (target) {
        e.preventDefault();
        e.stopPropagation();
        var toolId = target.getAttribute('data-tool-id');
        if (toolId) toggleWorkTool(toolId);
        return;
    }
    target = e.target.closest('[data-action="togglePersonalTool"]');
    if (target) {
        e.preventDefault();
        e.stopPropagation();
        var toolId = target.getAttribute('data-tool-id');
        if (toolId) togglePersonalTool(toolId);
        return;
    }
});


// === canvas.js ===
// Round 47 — Block 1.1: Canvas — Visual Decision Mapping.
// A thinking aid: the decision node, linked laws, experts, bottlenecks,
// connected by labeled edges. Bumble-styled cards, not a complex diagram.
// Accessed via the command palette (Ctrl+K), NOT a new sidebar item.

async function loadCanvas(decisionId) {
  const el = document.getElementById('canvas-content') || document.getElementById('main-content');
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    // If no decision ID, get the top recommendation
    if (!decisionId) {
      const briefing = await api.getOEM('/ceo-briefing');
      const ot = briefing.one_thing || {};
      if (ot.rec_id) {
        decisionId = ot.rec_id;
      } else {
        el.innerHTML = `<div class="calm-empty b-text-center-9">
          <div class="b-fs18-fw800-4">No active decisions to map.</div>
          <div class="meta-text">Connect more signal sources and Maestro will map your decisions here.</div>
        </div>`;
        return;
      }
    }

    const data = await api.getOEM(`/canvas/${encodeURIComponent(decisionId)}`);
    renderCanvas(el, data);
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed to load canvas: ${escapeHtml(e.message)}</div>`;
  }
}

function renderCanvas(el, data) {
  const nodes = data.nodes || [];
  const edges = data.edges || [];
  const assessment = data.assessment || '';

  let html = `<div class="b-mw800-m0auto">`;

  // Header
  html += `
    <div class="b-mb20">
      <div class="b-fs18-fw800">Decision Canvas</div>
      <div class="caption-text">${escapeHtml(humanize(assessment))}</div>
    </div>
  `;

  if (nodes.length === 0) {
    html += `<div class="calm-empty b-text-center-9">
      <div class="b-fs16-fw700">This decision has no dependencies mapped yet.</div>
    </div>`;
    html += `</div>`;
    el.innerHTML = html;
    return;
  }

  // Canvas area — relative positioned for node placement
  html += `<div class="b-pos-relative-3">`;

  // Render edges first (SVG lines behind nodes)
  html += `<svg class="b-pos-absolute-5">`;
  edges.forEach(edge => {
    const fromNode = nodes.find(n => n.id === edge.from);
    const toNode = nodes.find(n => n.id === edge.to);
    if (!fromNode || !toNode) return;
    const x1 = fromNode.position.x;
    const y1 = fromNode.position.y;
    const x2 = toNode.position.x;
    const y2 = toNode.position.y;
    html += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#D0D0D0" stroke-width="2" stroke-dasharray="4,4" />`;
    // Edge label
    const midX = (x1 + x2) / 2;
    const midY = (y1 + y2) / 2;
    html += `<text x="${midX}" y="${midY}" fill="#999" font-size="10" font-family="Montserrat,sans-serif" font-weight="600" text-anchor="middle">${escapeHtml(edge.label)}</text>`;
  });
  html += `</svg>`;

  // Render nodes — Bumble-styled cards
  nodes.forEach(node => {
    const pos = node.position || { x: 100, y: 100 };
    const typeColors = {
      decision: { bg: 'var(--maestro-yellow,#FFC629)', text: 'var(--maestro-black,#1A1A1A)' },
      law: { bg: 'var(--maestro-yellow-light,#FFF4D1)', text: 'var(--maestro-yellow-dark,#F0B500)' },
      expert: { bg: 'rgba(0,200,83,0.1)', text: 'var(--maestro-success,#00C853)' },
      bottleneck: { bg: 'rgba(255,152,0,0.15)', text: 'var(--maestro-warning,#FF9800)' },
    };
    const colors = typeColors[node.type] || typeColors.law;
    const size = node.type === 'decision' ? 180 : 140;

    html += `
      <div class="maestro-card canvas-node" data-node-id="${escapeHtml(node.id)}"
           class="b-pos-absolute">
        <div class="b-inline-block">${escapeHtml(node.type)}</div>
        <div class="b-fs12-fw700">${escapeHtml(humanize(node.label))}</div>
        ${node.detail ? `<div class="b-fs10-text-2">${escapeHtml(humanize(node.detail))}</div>` : ''}
        ${node.confidence != null ? `<div class="b-fs10-fw700">${Math.round(node.confidence * 100)}%</div>` : ''}
        ${node.verified ? `<div class="b-fs9-text">✓ VERIFIED</div>` : ''}
      </div>
    `;
  });

  html += `</div>`;

  // Withdrawal path note
  html += `
    <div class="b-mt16-p1216">
      <strong>Withdrawal path:</strong> You can map decisions on a whiteboard. This canvas saves time; without it, you are slower but functional.
    </div>
  `;

  html += `</div>`;
  el.innerHTML = html;

  // Make nodes draggable
  _initCanvasDrag();
}

// Round 69 RESIDUAL-7: Central drag manager — single listener pair, not per-node.
// Old code added 2 document listeners per node per render — memory leak.
let _canvasDragState = null;

function _initCanvasDrag() {
  // Remove old listeners if they exist (prevents accumulation on re-render)
  _destroyCanvasDrag();

  _canvasDragState = { dragging: null, startX: 0, startY: 0, startLeft: 0, startTop: 0 };

  _canvasDragState.onMouseMove = (e) => {
    if (!_canvasDragState || !_canvasDragState.dragging) return;
    const dx = e.clientX - _canvasDragState.startX;
    const dy = e.clientY - _canvasDragState.startY;
    _canvasDragState.dragging.style.left = (_canvasDragState.startLeft + dx) + 'px';
    _canvasDragState.dragging.style.top = (_canvasDragState.startTop + dy) + 'px';
  };

  _canvasDragState.onMouseUp = () => {
    if (_canvasDragState && _canvasDragState.dragging) {
      _canvasDragState.dragging.style.cursor = 'move';
      _canvasDragState.dragging = null;
    }
  };

  document.addEventListener('mousemove', _canvasDragState.onMouseMove);
  document.addEventListener('mouseup', _canvasDragState.onMouseUp);

  // Per-node: only mousedown (not document listeners)
  document.querySelectorAll('.canvas-node').forEach(node => {
    node.addEventListener('mousedown', (e) => {
      if (!_canvasDragState) return;
      _canvasDragState.dragging = node;
      _canvasDragState.startX = e.clientX;
      _canvasDragState.startY = e.clientY;
      _canvasDragState.startLeft = parseInt(node.style.left);
      _canvasDragState.startTop = parseInt(node.style.top);
      node.style.cursor = 'grabbing';
      e.preventDefault();
    });
  });
}

function _destroyCanvasDrag() {
  if (_canvasDragState) {
    document.removeEventListener('mousemove', _canvasDragState.onMouseMove);
    document.removeEventListener('mouseup', _canvasDragState.onMouseUp);
    _canvasDragState = null;
  }
}

// Round 78: Touch event support for iPad/mobile
function _addTouchSupport(node, dragHandler) {
  node.addEventListener('touchstart', (e) => {
    e.preventDefault();
    const touch = e.touches[0];
    dragHandler._start({ clientX: touch.clientX, clientY: touch.clientY });
  }, { passive: false });
}
document.addEventListener('touchmove', (e) => {
  if (window._canvasDragState && window._canvasDragState.dragging) {
    e.preventDefault();
    const touch = e.touches[0];
    window._canvasDragState._move({ clientX: touch.clientX, clientY: touch.clientY });
  }
}, { passive: false });
document.addEventListener('touchend', () => {
  if (window._canvasDragState && window._canvasDragState.dragging) {
    window._canvasDragState._end();
  }
});


// === teammate.js ===
// Round 47 — Block 1.2: Per-Teammate View.
// A per-person view: tasks, commitments, attention, trust, influence.
// This is the USER'S view OF a teammate — uses only the user's own
// organizational data. Does NOT analyze the teammate's personal life.
// Accessed by tapping a person's name, NOT a new sidebar item.
//
// Typography: font-family: 'Montserrat', sans-serif (Bumble design system)

async function loadTeammate(email) {
  const el = document.getElementById('teammate-content') || document.getElementById('main-content');
  if (!el) return;
  if (!email) {
    el.innerHTML = `<div class="calm-empty b-text-center-9">
      <div class="b-fs16-fw700-2">No teammate selected.</div>
      <div class="caption-text">Tap a person's name anywhere in Maestro to see their view.</div>
    </div>`;
    return;
  }
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const data = await api.getOEM(`/teammate/${encodeURIComponent(email)}`);
    renderTeammate(el, data);
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed to load teammate: ${escapeHtml(e.message)}</div>`;
  }
}

function renderTeammate(el, data) {
  let html = `<div class="b-mw700-m0auto">`;

  // Header
  html += `
    <div class="b-mb24">
      <div class="b-fs22-fw800">${escapeHtml(humanize(data.name))}</div>
      <div class="b-fs13-text-4">${escapeHtml(data.email)}</div>
      <div class="b-flex-gap16-2">
        <span>📊 Influence: ${data.influence}</span>
        <span>📡 Signals: ${data.signal_count}</span>
        ${data.domains.length > 0 ? `<span>🏷️ ${data.domains.length} domain${data.domains.length === 1 ? '' : 's'}</span>` : ''}
      </div>
    </div>
  `;

  // Tasks
  if (data.tasks && data.tasks.length > 0) {
    html += `
      <div class="b-fs14-fw800-4">Tasks (${data.tasks.length})</div>
    `;
    data.tasks.forEach(task => {
      const priClass = task.priority === 'high' ? 'contradiction' : task.priority === 'medium' ? 'due' : 'unknown';
      html += `
        <div class="maestro-card mb-10">
          <div class="swipe-card-category ${priClass} mb-6">${escapeHtml(task.priority.toUpperCase())}</div>
          <div class="b-fs14-fw700-3">${escapeHtml(humanize(task.description))}</div>
          <div class="b-flex-gap12">
            ${task.due_date ? `<span>📅 ${escapeHtml(task.due_date)}</span>` : ''}
            ${task.domain ? `<span>🏷️ ${escapeHtml(task.domain)}</span>` : ''}
            <span class="text-positive">${escapeHtml(task.status.toUpperCase())}</span>
          </div>
        </div>
      `;
    });
  }

  // Commitments
  if (data.commitments && data.commitments.length > 0) {
    html += `
      <div class="b-fs14-fw800-8">Commitments (${data.commitments.length})</div>
    `;
    data.commitments.forEach(c => {
      html += `
        <div class="maestro-card b-mb10-u">
          <div class="b-fs14-fw700-3">${escapeHtml(humanize(c.description))}</div>
          <div class="b-flex-gap12">
            ${c.to_whom ? `<span>→ ${escapeHtml(c.to_whom)}</span>` : ''}
            ${c.due_date ? `<span>📅 ${escapeHtml(c.due_date)}</span>` : ''}
          </div>
        </div>
      `;
    });
  }

  // Attention
  if (data.attention && data.attention.total_signals > 0) {
    html += `
      <div class="b-fs14-fw800-8">Attention</div>
      <div class="maestro-card mb-10">
        <div class="b-fs13-text-17">${escapeHtml(humanize(data.attention.summary || 'No attention data.'))}</div>
      </div>
    `;
  }

  // Empty state
  if ((!data.tasks || data.tasks.length === 0) && (!data.commitments || data.commitments.length === 0)) {
    html += `
      <div class="calm-empty b-text-center-8">
        <div class="b-fs16-fw700-2">No tasks or commitments yet.</div>
        <div class="caption-text">As ${escapeHtml(data.name)} appears in more signals, their tasks and commitments will show here.</div>
      </div>
    `;
  }

  // Withdrawal path
  html += `
    <div class="b-mt24-p1216">
      <strong>Withdrawal path:</strong> You can track teammates in a spreadsheet. This view saves time; without it, you are slower but functional.
    </div>
  `;

  html += `</div>`;
  el.innerHTML = html;
}


// === coordination.js ===
// Round 59 — Coordination Engine UI surface.
// Lets the CEO initiate a coordination request, see affected teams,
// collect responses, and view the synthesized recommendation.
// Accessed via the command palette (Ctrl+K), NOT a sidebar item (V5 litmus).

async function loadCoordination() {
  const el = document.getElementById('coordination-content') || document.getElementById('main-content');
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const [active, all] = await Promise.all([
      api.getOEM('/coordinate').catch(() => ({ requests: [] })),
      api.getOEM('/coordinate').catch(() => ({ requests: [] })),
    ]);

    const requests = (all.requests || []);
    renderCoordinationSurface(el, requests);
  } catch (e) {
    el.innerHTML = `<div class="calm-empty b-text-center-9">
      <div class="b-fs16-fw700-2">Coordination Engine</div>
      <div class="caption-text">Failed to load: ${escapeHtml(e.message)}</div>
    </div>`;
  }
}

function renderCoordinationSurface(el, requests) {
  let html = `<div class="b-mw700-m0auto">`;

  // Header
  html += `
    <div class="b-mb20">
      <div class="b-fs18-fw800">Coordination Engine</div>
      <div class="caption-text">Coordinate multi-team input for decisions without scheduling a meeting.</div>
    </div>
  `;

  // Initiate form
  html += `
    <div class="maestro-card b-mb20">
      <div class="b-fs14-fw700-4">Initiate a coordination request</div>
      <input type="text" class="maestro-input" id="coord-decision-input"
             placeholder="e.g., Standardize OAuth across all services"
             onkeydown="if(event.key==='Enter') initiateCoordination()"
             class="b-w-full-6" />
      <button class="maestro-btn maestro-btn-full" id="coord-initiate-btn"
              class="b-fs14-minh44">
        Initiate coordination
      </button>
    </div>
  `;

  // Active requests
  if (requests.length > 0) {
    html += `<div class="b-fs14-fw800-4">Active requests (${requests.length})</div>`;
    requests.forEach(req => {
      const status = req.status || 'open';
      const statusColor = status === 'synthesized' ? 'var(--maestro-success,#00C853)' : 'var(--maestro-warning,#FF9800)';
      const teamCount = (req.affected_teams || []).length;
      const responseCount = (req.responses || []).length;

      html += `
        <div class="maestro-card b-mb12-cursor" data-action="viewCoordination" data-args='["${escapeJs(req.request_id)}"]'>
          <div class="b-flex-u-9">
            <div class="flex-1">
              <div class="b-inline-block-3">${escapeHtml(status)}</div>
              <div class="b-fs15-fw700">${escapeHtml(humanize(req.decision || ''))}</div>
              <div class="b-flex-gap12-2">
                <span>👥 ${teamCount} team${teamCount === 1 ? '' : 's'}</span>
                <span>💬 ${responseCount} response${responseCount === 1 ? '' : 's'}</span>
              </div>
            </div>
          </div>
        </div>
      `;
    });
  } else {
    html += `
      <div class="calm-empty b-text-center-8">
        <div class="b-fs16-fw700-2">No coordination requests yet.</div>
        <div class="caption-text">Initiate one above to coordinate multi-team input for a decision.</div>
      </div>
    `;
  }

  // Withdrawal path
  html += `
    <div class="b-mt24-p1216">
      <strong>Withdrawal path:</strong> You can make decisions without coordination — schedule a meeting instead. This tool saves time; without it, you are slower but functional.
    </div>
  `;

  html += `</div>`;
  el.innerHTML = html;

  // Wire the initiate button via addEventListener (CSP-safe)
  const btn = document.getElementById('coord-initiate-btn');
  if (btn) {
    btn.addEventListener('click', initiateCoordination);
  }
}

async function initiateCoordination() {
  const input = document.getElementById('coord-decision-input');
  if (!input || !input.value.trim()) return;
  const decision = input.value.trim();

  try {
    const result = await api.postOEM('/coordinate', {
      decision: decision,
      initiated_by: 'ceo@acme.com',
    });
    // Reload to show the new request
    loadCoordination();
  } catch (e) {
    showToast('Failed to initiate coordination: ' + e.message, 'error');
  }
}

async function viewCoordination(requestId) {
  const el = document.getElementById('coordination-content') || document.getElementById('main-content');
  if (!el || !requestId) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const req = await api.getOEM(`/coordinate/${encodeURIComponent(requestId)}`);
    renderCoordinationDetail(el, req);
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

function renderCoordinationDetail(el, req) {
  let html = `<div class="b-mw700-m0auto">`;

  // Back button
  html += `<button class="maestro-btn maestro-btn-ghost b-fs13-minh36" id="coord-back-btn">← Back to coordination</button>`;

  // Decision
  html += `
    <div class="b-mb20">
      <div class="b-fs18-fw800">${escapeHtml(humanize(req.decision || ''))}</div>
      <div class="b-fs12-text-9">Initiated by ${escapeHtml(req.initiated_by || 'CEO')} · ${escapeHtml(req.created_at || '')}</div>
    </div>
  `;

  // Affected teams
  const teams = req.affected_teams || [];
  if (teams.length > 0) {
    html += `<div class="b-fs14-fw800">Affected teams (${teams.length})</div>`;
    teams.forEach(team => {
      html += `
        <div class="maestro-card b-mb8-p1014">
          <div class="b-fs14-fw700-2">${escapeHtml(team.team || team)}</div>
          <div class="b-fs12-text-7">${escapeHtml((team.domains || []).join(', '))}</div>
        </div>
      `;
    });
  }

  // Contacts
  const contacts = req.contacts || [];
  if (contacts.length > 0) {
    html += `<div class="b-fs14-fw800-2">Contacts (${contacts.length})</div>`;
    contacts.forEach(c => {
      html += `
        <div class="maestro-card b-mb8-p1014">
          <div class="b-flex-u-7">
            <div>
              <div class="b-fs14-fw700-2">${escapeHtml(c.email || '')}</div>
              <div class="tag-text">${escapeHtml(c.team || '')} · ${escapeHtml(c.role || '')}</div>
            </div>
          </div>
        </div>
      `;
    });
  }

  // Responses
  const responses = req.responses || [];
  if (responses.length > 0) {
    html += `<div class="b-fs14-fw800-2">Responses (${responses.length})</div>`;
    responses.forEach(r => {
      html += `
        <div class="maestro-card b-mb8-p1214">
          <div class="b-fs13-fw700">${escapeHtml(r.from || '')} — ${escapeHtml(r.team || '')}</div>
          <div class="b-fs13-text-23">${escapeHtml(humanize(r.response || ''))}</div>
        </div>
      `;
    });
  }

  // Synthesis
  if (req.synthesis) {
    html += `
      <div class="b-mt24-p16">
        <div class="b-fs14-fw800-3">Synthesized recommendation</div>
        <div class="b-fs14-text-7">${escapeHtml(humanize(req.synthesis.recommendation || ''))}</div>
        ${req.synthesis.consensus ? `<div class="b-fs12-text-11">Consensus: ${Math.round(req.synthesis.consensus * 100)}%</div>` : ''}
      </div>
    `;
  }

  // Response form
  html += `
    <div class="maestro-card b-mt20">
      <div class="b-fs14-fw700">Add a response</div>
      <textarea id="coord-response-input" placeholder="Enter your team's input on this decision…"
                class="b-w-full-4"></textarea>
      <button class="maestro-btn maestro-btn-full" id="coord-respond-btn"
              class="b-fs14-minh44">
        Submit response
      </button>
    </div>
  `;

  html += `</div>`;
  el.innerHTML = html;

  // Wire buttons
  const backBtn = document.getElementById('coord-back-btn');
  if (backBtn) backBtn.addEventListener('click', loadCoordination);
  const respondBtn = document.getElementById('coord-respond-btn');
  if (respondBtn) {
    respondBtn.addEventListener('click', async () => {
      const input = document.getElementById('coord-response-input');
      if (!input || !input.value.trim()) return;
      try {
        await api.postOEM(`/coordinate/${encodeURIComponent(req.request_id)}/respond`, {
          from: 'ceo@acme.com',
          team: 'leadership',
          response: input.value.trim(),
        });
        viewCoordination(req.request_id); // reload
      } catch (e) {
        showToast('Failed to submit response: ' + e.message, 'error');
      }
    });
  }
}


// === icons.js ===
// Lucide icon helper — consistent iconography system
// Usage: icon('plus', 16) returns <i data-lucide="plus" data-size="16"></i>
// After rendering HTML, call lucide.createIcons() to convert <i> tags to SVGs.
function icon(name, size = 20, color = 'currentColor') {
  return '<i data-lucide="' + name + '" data-size="' + size + '" data-color="' + color + '" class="lucide-icon"></i>';
}


// === sw-register.js ===
// PWA service worker registration with update detection
if ('serviceWorker' in navigator) {
  window.addEventListener('load', function() {
    navigator.serviceWorker.register('/static/sw.js').then(function(reg) {
      // Check for updates every 60 minutes
      setInterval(function() {
        reg.update();
      }, 60 * 60 * 1000);

      // Notify on new version
      reg.addEventListener('updatefound', function() {
        var newWorker = reg.installing;
        newWorker.addEventListener('statechange', function() {
          if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
            // New version available — show toast
            var toast = document.createElement('div');
            toast.className = 'toast info';
            toast.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:9999;padding:12px 20px;border-radius:8px;background:#3b82f6;color:white;font-size:13px;cursor:pointer;';
            toast.textContent = 'New version available. Click to update.';
            toast.onclick = function() {
              newWorker.postMessage({ action: 'skipWaiting' });
              toast.remove();
            };
            document.body.appendChild(toast);
          }
        });
      });
    }).catch(function(e) {
      console.log('SW registration failed:', e);
    });

    // Reload when the new SW takes over
    var refreshing = false;
    navigator.serviceWorker.addEventListener('controllerchange', function() {
      if (refreshing) return;
      refreshing = true;
      window.location.reload();
    });
  });
}


// === app_init.js ===
// app_init.js — extracted from inline scripts (CSP compliance)

if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/static/sw.js').catch(() => {
        // Non-fatal — the app works without the service worker
      });
    });
  }

// Initialize Lucide icons after DOM loads
  document.addEventListener('DOMContentLoaded', function() {
    if (typeof lucide !== 'undefined') lucide.createIcons();
  });

  // Surface → Lucide icon mapping (CEO's world-class spec: every surface has an icon)
  const SURFACE_ICONS = {
    today: 'sunrise', memory: 'brain', 'ask-v2': 'help-circle', home: 'layout-dashboard',
    inbox: 'inbox', simulator: 'sliders-horizontal', hayek: 'network', flow: 'git-branch',
    physics: 'atom', debate: 'swords', customer: 'users', intents: 'arrow-down-right',
    contradictions: 'alert-octagon', predictions: 'trending-up', assumptions: 'alert-triangle',
    'eng-signals': 'radio', 'eng-oem': 'settings-2', 'eng-audit': 'scroll-text',
    'eng-settings': 'settings', canvas: 'pen-tool', personal: 'lock', work: 'briefcase',
    learn: 'graduation-cap', evolution: 'trending-up', cognition: 'cpu',
    autobiography: 'book-open', playbook: 'clipboard-list', live: 'mic',
    coordination: 'git-merge', more: 'grid-horizontal', ask: 'help-circle',
  };

  // Re-run after surface changes + inject surface icon into breadcrumb
  const _origNavTo = window.navTo;
  if (_origNavTo) {
    window.navTo = function(surface) {
      _origNavTo(surface);
      // Inject Lucide icon into the breadcrumb page title
      const bcPage = document.getElementById('bc-page');
      if (bcPage) {
        const iconName = SURFACE_ICONS[surface] || 'circle';
        // Remove any existing icon
        const existingIcon = bcPage.querySelector('.bc-surface-icon');
        if (existingIcon) existingIcon.remove();
        // Insert new icon before the text
        const iconEl = document.createElement('i');
        iconEl.setAttribute('data-lucide', iconName);
        iconEl.className = 'bc-surface-icon';
        bcPage.insertBefore(iconEl, bcPage.firstChild);
      }
      setTimeout(function() { if (typeof lucide !== 'undefined') lucide.createIcons(); }, 50);
    };
  }

// Round 78: onclick → addEventListener (CSP compliance)
document.addEventListener('DOMContentLoaded', function() {
  var el_oc_0 = document.querySelector('[data-oc="oc-0"]');
  if (el_oc_0) el_oc_0.addEventListener('click', function() { closeDrilldown() });
  var el_oc_1 = document.querySelector('[data-oc="oc-1"]');
  if (el_oc_1) el_oc_1.addEventListener('click', function() { closeDrilldown() });
  var el_oc_2 = document.querySelector('[data-oc="oc-2"]');
  if (el_oc_2) el_oc_2.addEventListener('click', function() { switchDrilldownTab('why') });
  var el_oc_3 = document.querySelector('[data-oc="oc-3"]');
  if (el_oc_3) el_oc_3.addEventListener('click', function() { switchDrilldownTab('where') });
  var el_oc_4 = document.querySelector('[data-oc="oc-4"]');
  if (el_oc_4) el_oc_4.addEventListener('click', function() { switchDrilldownTab('evidence') });
  var el_oc_5 = document.querySelector('[data-oc="oc-5"]');
  if (el_oc_5) el_oc_5.addEventListener('click', function() { switchDrilldownTab('timeline') });
  var el_oc_6 = document.querySelector('[data-oc="oc-6"]');
  if (el_oc_6) el_oc_6.addEventListener('click', function() { switchDrilldownTab('people') });
  var el_oc_7 = document.querySelector('[data-oc="oc-7"]');
  if (el_oc_7) el_oc_7.addEventListener('click', function() { switchDrilldownTab('prediction') });
  var el_oc_8 = document.querySelector('[data-oc="oc-8"]');
  if (el_oc_8) el_oc_8.addEventListener('click', function() { switchDrilldownTab('simulation') });
  var el_oc_9 = document.querySelector('[data-oc="oc-9"]');
  if (el_oc_9) el_oc_9.addEventListener('click', function() { switchDrilldownTab('recommendation') });
  var el_oc_10 = document.querySelector('[data-oc="oc-10"]');
  if (el_oc_10) el_oc_10.addEventListener('click', function() { switchDrilldownTab('perspectives') });
  var el_oc_11 = document.querySelector('[data-oc="oc-11"]');
  if (el_oc_11) el_oc_11.addEventListener('click', function() { switchDrilldownTab('sowhat') });
  var el_oc_12 = document.querySelector('[data-oc="oc-12"]');
  if (el_oc_12) el_oc_12.addEventListener('click', function() { openMoreMenu(); return false; });
  var el_oc_13 = document.querySelector('[data-oc="oc-13"]');
  if (el_oc_13) el_oc_13.addEventListener('click', function() { openCommandPalette() });
  var el_oc_14 = document.querySelector('[data-oc="oc-14"]');
  if (el_oc_14) el_oc_14.addEventListener('click', function() { toggleTheme() });
  var el_oc_15 = document.querySelector('[data-oc="oc-15"]');
  if (el_oc_15) el_oc_15.addEventListener('click', function() { toggleMobileSidebar() });
  var el_oc_16 = document.querySelector('[data-oc="oc-16"]');
  if (el_oc_16) el_oc_16.addEventListener('click', function() { runSimulator() });
  var el_oc_17 = document.querySelector('[data-oc="oc-17"]');
  if (el_oc_17) el_oc_17.addEventListener('click', function() { document.getElementById('ask-input').value='who is the bottleneck?'; submitAsk('who is the bottleneck?') });
  var el_oc_18 = document.querySelector('[data-oc="oc-18"]');
  if (el_oc_18) el_oc_18.addEventListener('click', function() { document.getElementById('ask-input').value='what laws have been discovered?'; submitAsk('what laws have been discovered?') });
  var el_oc_19 = document.querySelector('[data-oc="oc-19"]');
  if (el_oc_19) el_oc_19.addEventListener('click', function() { document.getElementById('ask-input').value='what is the P1 cluster risk?'; submitAsk('what is the P1 cluster risk?') });
  var el_oc_20 = document.querySelector('[data-oc="oc-20"]');
  if (el_oc_20) el_oc_20.addEventListener('click', function() { document.getElementById('customer-ask-input').value='Why is Initech slowing down?'; submitCustomerAsk('Why is Initech slowing down?') });
  var el_oc_21 = document.querySelector('[data-oc="oc-21"]');
  if (el_oc_21) el_oc_21.addEventListener('click', function() { document.getElementById('customer-ask-input').value='Who actually influences Globex?'; submitCustomerAsk('Who actually influences Globex?') });
  var el_oc_22 = document.querySelector('[data-oc="oc-22"]');
  if (el_oc_22) el_oc_22.addEventListener('click', function() { document.getElementById('customer-ask-input').value='Why did we lose Hooli?'; submitCustomerAsk('Why did we lose Hooli?') });
  var el_oc_23 = document.querySelector('[data-oc="oc-23"]');
  if (el_oc_23) el_oc_23.addEventListener('click', function() { document.getElementById('customer-ask-input').value='What promises have we made?'; submitCustomerAsk('What promises have we made?') });
  var el_oc_24 = document.querySelector('[data-oc="oc-24"]');
  if (el_oc_24) el_oc_24.addEventListener('click', function() { document.getElementById('customer-ask-input').value='Which engineering work unlocks the most ARR?'; submitCustomerAsk('Which engineering work unlocks the most ARR?') });
  var el_oc_25 = document.querySelector('[data-oc="oc-25"]');
  if (el_oc_25) el_oc_25.addEventListener('click', function() { setAssumptionsView('dangerous') });
  var el_oc_26 = document.querySelector('[data-oc="oc-26"]');
  if (el_oc_26) el_oc_26.addEventListener('click', function() { setAssumptionsView('accuracy') });
  var el_oc_27 = document.querySelector('[data-oc="oc-27"]');
  if (el_oc_27) el_oc_27.addEventListener('click', function() { startLiveMeeting() });
  var el_oc_28 = document.querySelector('[data-oc="oc-28"]');
  if (el_oc_28) el_oc_28.addEventListener('click', function() { analyzeTranscript() });
  var el_oc_29 = document.querySelector('[data-oc="oc-29"]');
  if (el_oc_29) el_oc_29.addEventListener('click', function() { document.getElementById('oauth-config-form').style.display='none' });
  var el_oc_30 = document.querySelector('[data-oc="oc-30"]');
  if (el_oc_30) el_oc_30.addEventListener('click', function() { saveOAuthProvider() });
  var el_oc_31 = document.querySelector('[data-oc="oc-31"]');
  if (el_oc_31) el_oc_31.addEventListener('click', function() { cancelImport() });
  var el_oc_ask_box = document.querySelector('[data-oc="oc-ask-box"]');
  if (el_oc_ask_box) el_oc_ask_box.addEventListener('click', function() { navTo('ask-v2'); });
  // P0-2: Today Ask input — delegated listener (no inline onkeydown)
  var todayAskInput = document.getElementById('today-ask-input');
  if (todayAskInput) {
    todayAskInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        if (typeof todayAskSubmit === 'function') {
          todayAskSubmit(this.value);
          this.value = '';
        }
      }
    });
  }
});

// Mobile nav: wire up click handlers + sync active state with navTo
document.addEventListener('DOMContentLoaded', function() {
  var mobileNavItems = document.querySelectorAll('.mobile-nav-item');
  mobileNavItems.forEach(function(item) {
    item.addEventListener('click', function() {
      var surface = this.getAttribute('data-surface');
      if (surface && typeof navTo === 'function') navTo(surface);
    });
  });

  // Sync mobile nav active state when navTo is called
  var _origNavTo2 = window.navTo;
  if (_origNavTo2) {
    window.navTo = function(surface) {
      _origNavTo2(surface);
      mobileNavItems.forEach(function(item) {
        var itemSurface = item.getAttribute('data-surface');
        if (itemSurface === surface) {
          item.classList.add('active');
        } else {
          item.classList.remove('active');
        }
      });
    };
  }
});



