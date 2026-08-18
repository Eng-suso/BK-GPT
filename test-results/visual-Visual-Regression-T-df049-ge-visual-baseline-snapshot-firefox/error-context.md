# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: visual.spec.ts >> Visual Regression Tests >> Full page visual baseline snapshot
- Location: e2e\visual.spec.ts:4:7

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: page.goto: Test timeout of 30000ms exceeded.
Call log:
  - navigating to "http://127.0.0.1:3030/", waiting until "load"

```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test';
  2  | 
  3  | test.describe('Visual Regression Tests', () => {
  4  |   test('Full page visual baseline snapshot', async ({ page }) => {
> 5  |     await page.goto('/');
     |                ^ Error: page.goto: Test timeout of 30000ms exceeded.
  6  |     await page.waitForLoadState('networkidle').catch(() => page.waitForLoadState('domcontentloaded'));
  7  | 
  8  |     // Capture visual snapshot of the page
  9  |     await expect(page).toHaveScreenshot('homepage-layout.png', {
  10 |       fullPage: true,
  11 |       // Mask dynamic elements if present (e.g. timestamps, live tickers)
  12 |       mask: [page.locator('.dynamic-timestamp, [data-testid="live-timer"]')],
  13 |     });
  14 |   });
  15 | 
  16 |   test('Component-level visual baseline snapshot', async ({ page }) => {
  17 |     await page.goto('/');
  18 |     await page.waitForLoadState('domcontentloaded');
  19 | 
  20 |     // Snapshot the top bar — a stable, bounded element present on all sections
  21 |     const header = page.locator('.product-topbar');
  22 |     if (await header.isVisible()) {
  23 |       await expect(header).toHaveScreenshot('header-component.png');
  24 |     }
  25 |   });
  26 | });
  27 | 
```