import { test, expect } from '@playwright/test';

test.describe('Visual Regression Tests', () => {
  // Opt-in: committed baselines are per-platform and only regenerated on the
  // runner that owns them. Running everywhere by default produced guaranteed
  // failures (no Linux baseline in the repo). Set RUN_VISUAL=1 to enable, and
  // refresh baselines with `npm run test:visual:update`.
  test.skip(!process.env.RUN_VISUAL, 'set RUN_VISUAL=1 to run visual regression');

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

    // Snapshot the global sidebar — a stable, bounded element on every route.
    const sidebar = page.getByRole('complementary', {
      name: 'Navigazione principale',
    });
    await expect(sidebar).toBeVisible();
    await expect(sidebar).toHaveScreenshot('global-sidebar.png');
  });
});
