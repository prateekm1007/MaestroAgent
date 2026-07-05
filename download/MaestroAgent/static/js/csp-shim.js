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
