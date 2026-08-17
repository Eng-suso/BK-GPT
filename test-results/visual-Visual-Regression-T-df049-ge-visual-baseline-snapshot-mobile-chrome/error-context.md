# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: visual.spec.ts >> Visual Regression Tests >> Full page visual baseline snapshot
- Location: e2e\visual.spec.ts:4:7

# Error details

```
Error: expect(page).toHaveScreenshot(expected) failed

  316237 pixels (ratio 0.92 of all image pixels) are different.

  Snapshot: homepage-layout.png

Call log:
  - Expect "toHaveScreenshot(homepage-layout.png)" with timeout 5000ms
    - verifying given screenshot expectation
  - taking page screenshot
    - disabled all CSS animations
  - waiting for fonts to load...
  - fonts loaded
  - 316237 pixels (ratio 0.92 of all image pixels) are different.
  - waiting 100ms before taking screenshot
  - taking page screenshot
    - disabled all CSS animations
  - waiting for fonts to load...
  - fonts loaded
  - captured a stable screenshot
  - 316237 pixels (ratio 0.92 of all image pixels) are different.

```

# Page snapshot

```yaml
- generic [ref=e4]:
  - generic [ref=e5]: "[plugin:vite:import-analysis] Failed to resolve import \"@bpmn-io/properties-panel/dist/assets/properties-panel.css\" from \"src/features/process/ProcessBpmnCanvas.tsx\". Does the file exist?"
  - generic [ref=e6]: C:/Users/sohay/Desktop/DeliR-MVP/frontend/src/features/process/ProcessBpmnCanvas.tsx:6:7
  - generic [ref=e7]: "3 | import \"bpmn-js/dist/assets/bpmn-js.css\"; 4 | import \"bpmn-js/dist/assets/bpmn-font/css/bpmn.css\"; 5 | import \"@bpmn-io/properties-panel/dist/assets/properties-panel.css\"; | ^ 6 | import \"bpmn-js-token-simulation/assets/css/bpmn-js-token-simulation.css\"; 7 | import { API_BASE } from \"../../lib/api\";"
  - generic [ref=e8]: at TransformPluginContext._formatLog (file:///C:/Users/sohay/Desktop/DeliR-MVP/frontend/node_modules/vite/dist/node/chunks/node.js:30416:39) at TransformPluginContext.error (file:///C:/Users/sohay/Desktop/DeliR-MVP/frontend/node_modules/vite/dist/node/chunks/node.js:30413:14) at normalizeUrl (file:///C:/Users/sohay/Desktop/DeliR-MVP/frontend/node_modules/vite/dist/node/chunks/node.js:27438:18) at async file:///C:/Users/sohay/Desktop/DeliR-MVP/frontend/node_modules/vite/dist/node/chunks/node.js:27506:30 at async Promise.all (index 4) at async TransformPluginContext.transform (file:///C:/Users/sohay/Desktop/DeliR-MVP/frontend/node_modules/vite/dist/node/chunks/node.js:27474:4) at async EnvironmentPluginContainer.transform (file:///C:/Users/sohay/Desktop/DeliR-MVP/frontend/node_modules/vite/dist/node/chunks/node.js:30201:14) at async loadAndTransform (file:///C:/Users/sohay/Desktop/DeliR-MVP/frontend/node_modules/vite/dist/node/chunks/node.js:20124:26) at async viteTransformMiddleware (file:///C:/Users/sohay/Desktop/DeliR-MVP/frontend/node_modules/vite/dist/node/chunks/node.js:24604:20)
  - generic [ref=e9]:
    - text: Click outside, press Esc key, or fix the code to dismiss.You can also disable this overlay by setting
    - code [ref=e10]: server.hmr.overlay
    - text: to
    - code [ref=e11]: "false"
    - text: in
    - code [ref=e12]: vite.config.ts
    - text: .
```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test';
  2  | 
  3  | test.describe('Visual Regression Tests', () => {
  4  |   test('Full page visual baseline snapshot', async ({ page }) => {
  5  |     await page.goto('/');
  6  |     await page.waitForLoadState('networkidle').catch(() => page.waitForLoadState('domcontentloaded'));
  7  | 
  8  |     // Capture visual snapshot of the page
> 9  |     await expect(page).toHaveScreenshot('homepage-layout.png', {
     |                        ^ Error: expect(page).toHaveScreenshot(expected) failed
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
  20 |     // Snapshot specific header / navigation container if available
  21 |     const header = page.locator('header, nav, #root > div').first();
  22 |     if (await header.isVisible()) {
  23 |       await expect(header).toHaveScreenshot('header-component.png');
  24 |     }
  25 |   });
  26 | });
  27 | 
```