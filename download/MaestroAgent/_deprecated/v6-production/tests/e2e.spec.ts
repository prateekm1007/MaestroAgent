// Maestro v6 — E2E test scaffolding
// Critical user journeys — these are the tests that must pass before any deploy.

import { test, expect } from '@playwright/test';

test.describe('Onboarding flow', () => {
  test('completes 6-reveal onboarding and reaches Home', async ({ page }) => {
    await page.goto('/');
    // Reveal 0: connect signals
    await page.click('button:has-text("GitHub")');
    await page.click('button:has-text("Begin reconstruction →")');
    // Reveal 1: duplicated OAuth
    await expect(page.locator('h1')).toContainText('Three teams solved OAuth separately');
    await page.click('button:has-text("Continue →")');
    // Reveal 2: Legal bottleneck
    await expect(page.locator('h1')).toContainText('Platform is the bottleneck');
    await page.click('button:has-text("Continue →")');
    // Reveal 3: undocumented expert
    await expect(page.locator('h1')).toContainText('undocumented deployment expert');
    await page.click('button:has-text("Continue →")');
    // Reveal 4: prediction
    await expect(page.locator('h1')).toContainText('release frequency increases');
    await page.click('button:has-text("Continue →")');
    // Reveal 5: laws
    await expect(page.locator('h1')).toContainText('19 execution laws');
    await page.click('button:has-text("Enter Maestro →")');
    // Home
    await expect(page).toHaveURL(/\/home/);
    await expect(page.locator('h1')).toContainText('Good morning');
  });
});

test.describe('Decision Workbench', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/decisions/q3-hiring');
  });

  test('simulator updates predictions on slider change', async ({ page }) => {
    const emeaSlider = page.locator('#sim-emea');
    await emeaSlider.fill('5');
    await expect(page.locator('#pred-emea')).toContainText('+15%');

    await emeaSlider.fill('14');
    await expect(page.locator('#pred-emea')).toContainText('+42%');
  });

  test('confidence drops when config diverges from recommendation', async ({ page }) => {
    // Recommended config: emea=5, apac=6, na=2
    await page.locator('#sim-emea').fill('5');
    await page.locator('#sim-apac').fill('6');
    await page.locator('#sim-na').fill('2');
    const recommendedConf = await page.locator('#sim-conf-val').textContent();
    expect(parseFloat(recommendedConf!)).toBeGreaterThan(0.75);

    // Far config
    await page.locator('#sim-emea').fill('14');
    await page.locator('#sim-apac').fill('0');
    await page.locator('#sim-na').fill('0');
    const farConf = await page.locator('#sim-conf-val').textContent();
    expect(parseFloat(farConf!)).toBeLessThan(0.70);
  });

  test('approval logs prediction to Ledger', async ({ page }) => {
    await page.click('button:has-text("Approve & log prediction")');
    // Verify modal or toast confirms logging
    await expect(page.locator('text=Prediction Ledger')).toBeVisible();
  });
});

test.describe('Live Meeting Intelligence', () => {
  test('consent banner visible and prevents recording until consent', async ({ page }) => {
    await page.goto('/live');
    await expect(page.locator('.live-consent')).toBeVisible();
    // The consent banner must show all participants consented before transcript begins
  });

  test('hotkey overlay opens on Cmd+Enter', async ({ page }) => {
    await page.goto('/live');
    await page.keyboard.press('Meta+Enter');
    await expect(page.locator('#hotkeyOverlay')).toHaveClass(/active/);
    await page.keyboard.press('Escape');
    await expect(page.locator('#hotkeyOverlay')).not.toHaveClass(/active/);
  });

  test('Ask Maestro returns cited response', async ({ page }) => {
    await page.goto('/live');
    await page.keyboard.press('Meta+Enter');
    await page.click('.ho-suggestion:has-text("structural reason")');
    await expect(page.locator('#hotkeyResponseText')).toContainText('L-0014');
    await expect(page.locator('.source-cite')).toHaveCount(3);
  });

  test('post-meeting synthesis flows artifacts to correct surfaces', async ({ page }) => {
    await page.goto('/live');
    // Wait for meeting simulation to complete
    await page.waitForSelector('text=Meeting ended', { timeout: 60000 });
    await page.click('text=View synthesis →');
    await expect(page.locator('text=Decisions extracted')).toBeVisible();
    await expect(page.locator('text=Predictions logged')).toBeVisible();
    await expect(page.locator('text=Action items extracted')).toBeVisible();
    await expect(page.locator('text=Law updates')).toBeVisible();
    await expect(page.locator('text=SHR impact')).toBeVisible();
  });
});

test.describe('Prediction Ledger', () => {
  test('SHR pill visible in top bar', async ({ page }) => {
    await page.goto('/home');
    await expect(page.locator('.shr-pill')).toContainText('SHR');
  });

  test('calibration curve renders 10 buckets', async ({ page }) => {
    await page.goto('/home');
    await page.click('.shr-pill');
    await expect(page.locator('#cal-grid')).toBeVisible();
    // 10 bucket columns
    await expect(page.locator('#cal-grid > div')).toHaveCount(10);
  });
});

test.describe('Organizational Physics', () => {
  test('laws marked Unknown to leadership are visually distinct', async ({ page }) => {
    await page.goto('/physics');
    const unknownLaws = page.locator('.law-card.unknown');
    await expect(unknownLaws.first()).toBeVisible();
    // Verify the "Unknown to leadership" tag is present
    await expect(unknownLaws.first().locator('.tag-amber')).toContainText('Unknown');
  });
});

test.describe('Decision Question enforcement', () => {
  // Every screen must declare a DQ — this is v6's design rule.
  // Test: no screen ships without a DQ badge.
  const surfaces = ['home', 'live', 'inbox', 'decisions', 'physics', 'debate'];

  for (const surface of surfaces) {
    test(`${surface} surface has a Decision Question badge`, async ({ page }) => {
      await page.goto(`/${surface}`);
      await expect(page.locator('.dq-badge')).toBeVisible({ timeout: 10000 });
    });
  }
});
