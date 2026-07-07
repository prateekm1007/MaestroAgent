import { test, expect } from '@playwright/test';

test('home page loads with correct title', async ({ page }) => {
  await page.goto('http://127.0.0.1:8765/');
  await expect(page).toHaveTitle(/Maestro/);
});

test('sidebar has 4 primary navigation items', async ({ page }) => {
  await page.goto('http://127.0.0.1:8765/');
  await page.waitForLoadState('networkidle');
  const sidebarLinks = page.locator('.sidebar-v2-primary [data-surface]');
  await expect(sidebarLinks).toHaveCount(4);
});

test('today surface renders content', async ({ page }) => {
  await page.goto('http://127.0.0.1:8765/');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);
  // The main content area should have substantial content
  const content = await page.locator('#main-content').innerHTML();
  expect(content.length).toBeGreaterThan(1000);
});

test('all JS functions are defined in browser', async ({ page }) => {
  await page.goto('http://127.0.0.1:8765/');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);
  const funcs = await page.evaluate(() => ({
    loadDashboard: typeof loadDashboard,
    openMoreMenu: typeof openMoreMenu,
    escapeHtml: typeof escapeHtml,
    navTo: typeof navTo,
    humanize: typeof humanize,
  }));
  expect(funcs.loadDashboard).toBe('function');
  expect(funcs.openMoreMenu).toBe('function');
  expect(funcs.escapeHtml).toBe('function');
  expect(funcs.navTo).toBe('function');
  expect(funcs.humanize).toBe('function');
});

test('no console errors on page load', async ({ page }) => {
  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  await page.goto('http://127.0.0.1:8765/');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);
  // Filter out CSP inline handler errors (known, Phase 4 will fix)
  const realErrors = errors.filter(e => !e.includes('Content Security Policy'));
  expect(realErrors).toHaveLength(0);
});
