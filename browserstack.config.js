/**
 * BrowserStack Playwright Cloud Integration Helper
 * 
 * Instructions:
 * 1. Set environment variables:
 *    export BROWSERSTACK_USERNAME="your_username"
 *    export BROWSERSTACK_ACCESS_KEY="your_access_key"
 * 2. Run: node browserstack.config.js
 */

const { chromium } = require('@playwright/test');

const caps = {
  'browser': 'chrome',
  'browser_version': 'latest',
  'os': 'Windows',
  'os_version': '11',
  'name': 'Playwright DeliR-MVP E2E Test',
  'build': 'playwright-build-1',
  'browserstack.username': process.env.BROWSERSTACK_USERNAME || 'YOUR_USERNAME',
  'browserstack.accessKey': process.env.BROWSERSTACK_ACCESS_KEY || 'YOUR_ACCESS_KEY',
};

async function runBrowserStackTest() {
  console.log('Connecting to BrowserStack Playwright Grid...');
  const browser = await chromium.connect({
    wsEndpoint: `wss://cdp.browserstack.com/playwright?caps=${encodeURIComponent(JSON.stringify(caps))}`,
  });

  const page = await browser.newPage();
  await page.goto('http://localhost:3030');
  const title = await page.title();
  console.log(`Page title on BrowserStack Windows 11 Chrome: ${title}`);

  await browser.close();
}

if (require.main === module) {
  runBrowserStackTest().catch(console.error);
}

module.exports = { caps, runBrowserStackTest };
