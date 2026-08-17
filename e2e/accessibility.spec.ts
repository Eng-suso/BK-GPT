import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('Accessibility (a11y) Audits with Axe', () => {
  test('HomePage WCAG 2.1 AA Compliance Check', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    // Run Axe accessibility analysis
    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    // Log violations to console for actionable debugging
    if (accessibilityScanResults.violations.length > 0) {
      console.log('Accessibility Violations Found:');
      accessibilityScanResults.violations.forEach((violation) => {
        console.log(`- [${violation.impact?.toUpperCase()}] ${violation.id}: ${violation.help}`);
        console.log(`  Target: ${violation.nodes.map((n) => n.target).join(', ')}`);
        console.log(`  Help URL: ${violation.helpUrl}`);
      });
    }

    // Assert zero critical/serious accessibility violations
    const criticalOrSeriousViolations = accessibilityScanResults.violations.filter(
      (v) => v.impact === 'critical' || v.impact === 'serious'
    );
    expect(criticalOrSeriousViolations).toEqual([]);
  });
});
