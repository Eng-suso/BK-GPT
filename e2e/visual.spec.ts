import { test, expect } from '@playwright/test';

test.describe('Visual Regression Tests', () => {
  test('Full page visual baseline snapshot', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle').catch(() => page.waitForLoadState('domcontentloaded'));

    // Capture visual snapshot of the page
    await expect(page).toHaveScreenshot('homepage-layout.png', {
      fullPage: true,
      // Mask dynamic elements if present (e.g. timestamps, live tickers)
      mask: [page.locator('.dynamic-timestamp, [data-testid="live-timer"]')],
    });
  });

  test('Component-level visual baseline snapshot', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    // Snapshot specific header / navigation container if available
    const header = page.locator('header, nav, #root > div').first();
    if (await header.isVisible()) {
      await expect(header).toHaveScreenshot('header-component.png');
    }
  });
});
