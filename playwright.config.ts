import { defineConfig, devices } from '@playwright/test';

/**
 * See https://playwright.dev/docs/test-configuration.
 */
export default defineConfig({
  testDir: './e2e',
  /* Run tests in files in parallel */
  fullyParallel: true,
  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,
  /* Retry on CI only */
  retries: process.env.CI ? 2 : 0,
  /* Opt out of parallel tests on CI. */
  workers: process.env.CI ? 1 : undefined,
  /* Dev-mode Vite compiles the module graph on first navigation; the default
   * 30s is tight for the first spec on a cold CI runner. */
  timeout: 45 * 1000,
  /* Reporter to use. See https://playwright.dev/docs/test-reporters */
  reporter: [['html', { open: 'never' }], ['list']],
  
  /* Shared settings for all visual regression snapshots */
  expect: {
    /* Dev-mode Vite compiles a route's module graph on first navigation, and a
     * loaded machine makes that cost visible: i cinque secondi di default
     * scadevano mentre la pagina stava ancora arrivando, e il rosso diceva
     * "schermata vuota" su un'app che funzionava. */
    timeout: 15 * 1000,
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.05,
      threshold: 0.2,
      animations: 'disabled',
    },
  },

  /* Shared settings for all the projects below. See https://playwright.dev/docs/api/class-testoptions. */
  use: {
    /* Base URL to use in actions like `await page.goto('/')`. */
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:3030',

    /* Collect trace when retrying the failed test. See https://playwright.dev/docs/trace-viewer */
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  /* Configure projects for major browsers. I media di lancio (e2e/launch-media)
   * hanno la loro config, playwright.launch.config.ts. */
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
      testIgnore: ['**/performance-lighthouse.spec.ts', '**/launch-media/**'],
    },
    // Firefox is intentionally excluded from the default local matrix because the
    // current Windows runner fails before navigation at browser.newPage().
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
      testIgnore: ['**/performance-lighthouse.spec.ts', '**/launch-media/**'],
    },

    /* Test against mobile viewports. */
    {
      name: 'mobile-chrome',
      use: { ...devices['Pixel 7'] },
      testIgnore: ['**/performance-lighthouse.spec.ts', '**/launch-media/**'],
    },
    {
      name: 'mobile-safari',
      use: { ...devices['iPhone 14'] },
      testIgnore: ['**/performance-lighthouse.spec.ts', '**/launch-media/**'],
    },

    /* Lighthouse performance audits — Chromium/CDP only */
    {
      name: 'lighthouse',
      use: { ...devices['Desktop Chrome'] },
      testMatch: ['**/performance-lighthouse.spec.ts'],
    },
  ],

  /* Run your local dev server before starting the tests */
  webServer: {
    command: 'npm run dev:frontend',
    url: 'http://127.0.0.1:3030',
    reuseExistingServer: !process.env.CI,
    timeout: 120 * 1000,
  },
});
