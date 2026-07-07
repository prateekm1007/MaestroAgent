import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

describe('accessibility', () => {
  const appHtml = fs.readFileSync(path.join(process.cwd(), 'app.html'), 'utf8');

  it('has ARIA live region for screen readers', () => {
    expect(appHtml).toContain('aria-live');
    expect(appHtml).toContain('sr-announcer');
  });

  it('has skip-to-content link', () => {
    expect(appHtml).toContain('skip-link');
  });

  it('has role attributes', () => {
    expect(appHtml).toContain('role=');
  });

  it('has aria-label attributes', () => {
    expect(appHtml).toContain('aria-label');
  });

  it('has tabindex for keyboard navigation', () => {
    expect(appHtml).toContain('tabindex');
  });

  it('has .sr-only CSS class', () => {
    expect(appHtml).toContain('sr-only');
  });

  it('has focus-trap.js loaded', () => {
    expect(appHtml).toContain('focus-trap.js');
  });

  it('has CSP shim (either separate or in bundle)', () => {
    // CSP shim is bundled into bundle.min.js
    const bundleSrc = fs.readFileSync(path.join(process.cwd(), 'static/js/bundle.min.js'), 'utf8');
    const hasCspInBundle = bundleSrc.includes('data-action') && bundleSrc.includes('_executeAction');
    const hasCspInHtml = appHtml.includes('csp-shim.js');
    expect(hasCspInBundle || hasCspInHtml).toBe(true);
  });
});

describe('focus-trap', () => {
  const src = fs.readFileSync(path.join(process.cwd(), 'static/js/components/focus-trap.js'), 'utf8');

  it('defines createFocusTrap function', () => {
    expect(src).toContain('function createFocusTrap');
  });

  it('has activate method', () => {
    expect(src).toContain('activate');
  });

  it('has deactivate method', () => {
    expect(src).toContain('deactivate');
  });

  it('handles Tab key', () => {
    expect(src).toContain('Tab');
  });

  it('handles Shift+Tab', () => {
    expect(src).toContain('shiftKey');
  });
});
