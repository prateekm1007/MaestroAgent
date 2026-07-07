// error-boundary.js — catches unhandled errors and shows recovery UI.
// Loaded after utils.js, before bundle.
// Depends on: escapeHtml, showToast (from utils.js + core.js)

(function() {
  'use strict';

  // Global error handler
  window.addEventListener('error', function(event) {
    reportError({
      type: 'uncaught',
      message: event.message,
      filename: event.filename,
      lineno: event.lineno,
      colno: event.colno,
      stack: event.error ? event.error.stack : null,
    });
  });

  // Unhandled promise rejection handler
  window.addEventListener('unhandledrejection', function(event) {
    reportError({
      type: 'unhandled-promise',
      message: (event.reason && event.reason.message) || String(event.reason),
      stack: event.reason ? event.reason.stack : null,
    });
  });

  function reportError(error) {
    // 1. Log to console (dev)
    console.error('[Maestro Error]', error);

    // 2. Store in appStore for debugging
    if (window.appStore) {
      var errors = window.appStore.get('errors') || [];
      errors.push({
        ...error,
        url: window.location.href,
        surface: window._currentSurface,
        timestamp: new Date().toISOString(),
      });
      // Keep last 50 errors
      if (errors.length > 50) errors = errors.slice(-50);
      window.appStore.set('errors', errors);
    }

    // 3. Show non-intrusive toast (don't spam — dedupe by message)
    if (typeof B === 'function' && error.message) {
      B('Something went wrong: ' + error.message.substring(0, 80), 'error');
    }
  }

  // Per-surface error recovery wrapper
  // Usage: var safeLoad = withErrorBoundary('today', loadTodayData);
  //        safeLoad(); // if loadTodayData throws, shows error UI + retry
  window.withErrorBoundary = function(surfaceId, loadFn) {
    return async function() {
      var el = document.getElementById(surfaceId + '-content') ||
               document.getElementById('surface-' + surfaceId);
      try {
        await loadFn();
      } catch (e) {
        reportError({
          type: 'surface-error',
          surface: surfaceId,
          message: e.message,
          stack: e.stack,
        });
        if (el) {
          el.innerHTML =
            '<div class="error-boundary" role="alert" style="padding:24px;text-align:center;">' +
            '<div class="text-sm font-semibold" style="color:#ef4444;">This surface failed to load.</div>' +
            '<div class="text-xs" style="color:#525252;margin-top:4px;">' + escapeHtml(e.message) + '</div>' +
            '<button data-action="retrySurface" data-surface="' + escapeHtml(surfaceId) + '" ' +
            'class="maestro-btn maestro-btn-secondary" style="margin-top:12px;">Retry</button>' +
            '</div>';
        }
      }
    };
  };

  // Register retry action with CSP shim
  if (window._registerAction) {
    window._registerAction('retrySurface', function(el) {
      var surface = el.getAttribute('data-surface');
      if (surface && typeof loadSurfaceData === 'function') {
        loadSurfaceData(surface);
      }
    });
  }
})();
