import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

describe('error-boundary', () => {
  const src = fs.readFileSync(path.join(process.cwd(), 'static/js/error-boundary.js'), 'utf8');

  it('has global error handler', () => {
    expect(src).toContain("window.addEventListener('error'");
  });

  it('has unhandled promise rejection handler', () => {
    expect(src).toContain('unhandledrejection');
  });

  it('has reportError function', () => {
    expect(src).toContain('function reportError');
  });

  it('stores errors in appStore', () => {
    expect(src).toContain('appStore');
    expect(src).toContain('errors');
  });

  it('has withErrorBoundary wrapper', () => {
    expect(src).toContain('withErrorBoundary');
  });

  it('has retry action', () => {
    expect(src).toContain('retrySurface');
  });

  it('has escapeHtml for error messages', () => {
    expect(src).toContain('escapeHtml');
  });

  it('limits stored errors to 50', () => {
    expect(src).toContain('50');
  });
});

describe('perf-monitor', () => {
  const src = fs.readFileSync(path.join(process.cwd(), 'static/js/perf-monitor.js'), 'utf8');

  it('has LCP observer', () => {
    expect(src).toContain('largest-contentful-paint');
  });

  it('has FID observer', () => {
    expect(src).toContain('first-input');
  });

  it('has CLS observer', () => {
    expect(src).toContain('layout-shift');
  });

  it('has long task detection', () => {
    expect(src).toContain('longtask');
  });

  it('stores metrics in appStore', () => {
    expect(src).toContain('appStore');
  });
});
