import { test, expect, chromium } from '@playwright/test';
import { playAudit } from 'playwright-lighthouse';

test.describe('Lighthouse Performance & Quality Audits', () => {
  test('HomePage Lighthouse metrics audit', async () => {
    // Launch Chrome with remote debugging enabled for Lighthouse CDP connection
    const browser = await chromium.launch({
      args: ['--remote-debugging-port=9222'],
    });

    const page = await browser.newPage();
    await page.goto('http://127.0.0.1:3030');
    await page.waitForLoadState('domcontentloaded');

    // Perform Lighthouse audit with defined thresholds (0-100 scale)
    try {
      await playAudit({
        page,
        thresholds: {
          performance: 60,
          accessibility: 85,
          'best-practices': 80,
          seo: 75,
        },
        port: 9222,
        reports: {
          formats: {
            html: true,
          },
          name: `lighthouse-report-${Date.now()}`,
          directory: `./playwright-report/lighthouse`,
        },
      });
    } finally {
      await browser.close();
    }
  });
});
