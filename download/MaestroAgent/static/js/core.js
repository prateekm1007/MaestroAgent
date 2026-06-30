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