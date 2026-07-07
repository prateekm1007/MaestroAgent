import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

describe('PWA', () => {
  it('manifest.json has correct structure', () => {
    const manifest = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'static/manifest.json'), 'utf8'));
    expect(manifest.name).toContain('Maestro');
    expect(manifest.short_name).toBe('Maestro');
    expect(manifest.display).toBe('standalone');
    expect(manifest.start_url).toBe('/');
    expect(manifest.theme_color).toMatch(/^#/);
    expect(manifest.icons).toBeInstanceOf(Array);
    expect(manifest.icons.length).toBeGreaterThan(0);
  });

  it('sw.js has stale-while-revalidate', () => {
    const sw = fs.readFileSync(path.join(process.cwd(), 'static/sw.js'), 'utf8');
    expect(sw).toContain('stale-while-revalidate');
    expect(sw).toContain('API_CACHE');
    expect(sw).toContain('CACHE_NAME');
  });

  it('sw.js caches app shell', () => {
    const sw = fs.readFileSync(path.join(process.cwd(), 'static/sw.js'), 'utf8');
    expect(sw).toContain('/app.html');
    expect(sw).toContain('bundle.min.js');
  });

  it('sw.js has offline fallback', () => {
    const sw = fs.readFileSync(path.join(process.cwd(), 'static/sw.js'), 'utf8');
    expect(sw).toContain('503');
    expect(sw).toContain('offline');
  });

  it('sw-register.js has update detection', () => {
    const reg = fs.readFileSync(path.join(process.cwd(), 'static/js/sw-register.js'), 'utf8');
    expect(reg).toContain('updatefound');
    expect(reg).toContain('controllerchange');
  });

  it('app.html has offline banner', () => {
    const html = fs.readFileSync(path.join(process.cwd(), 'app.html'), 'utf8');
    expect(html).toContain('offline-banner');
    expect(html).toContain('role="alert"');
  });
});
