import { expect, test } from '@playwright/test';

test.describe('Enterprise project workspace UI', () => {
  test('renders the project portfolio shell and detail drawer', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await expect(page.getByRole('heading', { name: 'Progetti' })).toBeVisible();
    await expect(page.locator('.product-sidebar')).toBeVisible();
    await expect(page.locator('.product-topbar')).toBeVisible();
    await expect(page.locator('.workspace-table-card')).toBeVisible();
    await expect(page.locator('.enterprise-drawer')).toBeVisible();
    await expect(page.getByText('Riepilogo progetto')).toBeVisible();

    const viewport = page.viewportSize();
    if (viewport && viewport.width > 1366) {
      const tableBox = await page.locator('.workspace-table-card').boundingBox();
      const drawerBox = await page.locator('.enterprise-drawer').boundingBox();

      expect(tableBox).not.toBeNull();
      expect(drawerBox).not.toBeNull();
      expect(drawerBox!.x).toBeGreaterThan(tableBox!.x + tableBox!.width - 8);
    }
  });

  test('opens a project workspace with enterprise tabs', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.getByRole('button', { name: /Apri/i }).first().click();

    await expect(page.locator('.project-command-header')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Panoramica' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Mappa dei processi' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Piano e consegna' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Problemi e opportunita' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'DeliR' })).toBeVisible();
    await expect(page.locator('.manager-grid-top')).toBeVisible();
  });

  test('renders process map and issue workspaces without layout collapse', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.getByRole('button', { name: /Apri/i }).first().click();
    await page.getByRole('button', { name: 'Mappa dei processi' }).click();

    await expect(page.locator('.process-map-board')).toBeVisible();
    await expect(page.locator('.process-detail-drawer')).toBeVisible();
    await expect(page.locator('.process-table')).toBeVisible();

    await page.getByRole('button', { name: 'Problemi e opportunita' }).click();

    await expect(page.locator('.issue-kpi-grid')).toBeVisible();
    await expect(page.locator('.issue-detail-drawer')).toBeVisible();
    await expect(page.locator('.enterprise-table')).toBeVisible();
  });
});
