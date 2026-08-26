import { test, chromium } from '@playwright/test';
import { playAudit } from 'playwright-lighthouse';
import { createServer } from 'node:net';

const getAvailablePort = async () =>
  await new Promise<number>((resolve, reject) => {
    const server = createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      if (!address || typeof address === 'string') {
        server.close(() => reject(new Error('Unable to allocate a Lighthouse port')));
        return;
      }
      const { port } = address;
      server.close(() => resolve(port));
    });
  });

test.describe('Lighthouse Performance & Quality Audits', () => {
  test('HomePage Lighthouse metrics audit', async () => {
    test.setTimeout(90_000);
    const port = await getAvailablePort();

    // Launch Chrome with remote debugging enabled for Lighthouse CDP connection
    const browser = await chromium.launch({
      args: [`--remote-debugging-port=${port}`],
    });

    const page = await browser.newPage();
    await page.goto('http://127.0.0.1:3030');
    await page.waitForLoadState('domcontentloaded');

    // Perform Lighthouse audit with defined thresholds (0-100 scale)
    try {
      await playAudit({
        page,
        thresholds: {
          performance: 50,
          accessibility: 85,
          'best-practices': 80,
          seo: 75,
        },
        port,
        reports: {
          formats: {
            html: true,
          },
          name: 'lighthouse-report',
          directory: `./playwright-report/lighthouse`,
        },
        disableLogs: true,
      });
    } finally {
      await browser.close();
    }
  });
});
