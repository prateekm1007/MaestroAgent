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