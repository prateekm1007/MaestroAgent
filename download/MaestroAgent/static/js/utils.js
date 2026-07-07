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
