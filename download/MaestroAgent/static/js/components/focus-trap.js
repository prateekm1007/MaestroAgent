// focus-trap.js — traps focus within a modal/dialog when active.
// Prevents Tab from escaping to background content.
// Depends on: nothing (vanilla JS)

function createFocusTrap(container) {
  var focusableSelector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
  var previouslyFocused = null;

  function trap(e) {
    if (e.key !== 'Tab') return;
    var focusable = container.querySelectorAll(focusableSelector);
    if (focusable.length === 0) return;
    var first = focusable[0];
    var last = focusable[focusable.length - 1];

    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  return {
    activate: function() {
      previouslyFocused = document.activeElement;
      container.addEventListener('keydown', trap);
      var first = container.querySelector(focusableSelector);
      if (first) first.focus();
    },
    deactivate: function() {
      container.removeEventListener('keydown', trap);
      if (previouslyFocused && previouslyFocused.focus) {
        previouslyFocused.focus();
      }
    }
  };
}
