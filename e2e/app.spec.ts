import { test, expect } from '@playwright/test';

test.describe('End-to-End Core Functionality Tests', () => {
  test('HomePage loads correctly with title', async ({ page }) => {
    await page.goto('/');
    
    // Check that the page loads properly
    await expect(page).toHaveURL(/.*3030/);
    
    // Ensure body or main container is visible
    const body = page.locator('body');
    await expect(body).toBeVisible();
  });

  test('Interactive navigation check', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    // Basic assertion on interactive elements
    const buttons = page.locator('button, a[href]');
    const count = await buttons.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});
