import { expect, test } from '@playwright/test';

/**
 * Frontend-only smoke of the current app shell.
 *
 * The Playwright `webServer` starts only the Vite frontend — there is no
 * backend in this job — so these tests assert what renders without data:
 * the shell chrome, routing, and graceful degradation when the API is down.
 * Full data-flow e2e (projects → process → canvas → simulation) lands with
 * the `e2e-fullstack` job once the backend + seed are wired.
 */

const projectsHeading = { name: 'Progetti', level: 1 as const };

test.describe('App shell', () => {
  test('/ redirects to the projects portfolio', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await expect(page).toHaveURL(/\/projects$/);
    await expect(page.getByRole('heading', projectsHeading)).toBeVisible();
  });

  test('renders the global sidebar and top bar', async ({ page }) => {
    await page.goto('/projects', { waitUntil: 'domcontentloaded' });

    const sidebar = page.getByRole('complementary', {
      name: 'Navigazione principale',
    });
    await expect(sidebar).toBeVisible();
    // Label collapses to an icon below the `lg` breakpoint, but `title` keeps
    // the accessible name on every viewport.
    await expect(sidebar.getByRole('button', { name: 'Progetti' })).toBeVisible();
    await expect(page.getByRole('banner')).toBeVisible();
  });

  test('primary navigation switches sections', async ({ page }) => {
    await page.goto('/projects', { waitUntil: 'domcontentloaded' });
    const sidebar = page.getByRole('complementary', {
      name: 'Navigazione principale',
    });

    await sidebar.getByRole('button', { name: 'Clienti' }).click();
    await expect(page).toHaveURL(/\/clients$/);

    await sidebar.getByRole('button', { name: 'Home' }).click();
    await expect(page).toHaveURL(/\/home$/);
  });

  test('projects list degrades gracefully with no backend', async ({ page }) => {
    await page.goto('/projects', { waitUntil: 'domcontentloaded' });

    // Either the data table renders (backend reachable) or the explicit
    // "backend down" alert does — never a blank screen or an unhandled crash.
    const table = page.getByRole('table');
    const errorAlert = page.getByRole('alert');
    await expect(table.or(errorAlert).first()).toBeVisible();

    // The shell must survive whichever branch rendered.
    await expect(page.getByRole('heading', projectsHeading)).toBeVisible();
  });

  test('settings opens a real page from the sidebar footer', async ({ page }) => {
    await page.goto('/projects', { waitUntil: 'domcontentloaded' });
    const sidebar = page.getByRole('complementary', {
      name: 'Navigazione principale',
    });

    await sidebar.getByRole('button', { name: 'Impostazioni' }).click();

    await expect(page).toHaveURL(/\/settings$/);
    await expect(page.getByRole('heading', { name: 'Impostazioni', level: 1 })).toBeVisible();
    await expect(sidebar.getByRole('button', { name: 'Impostazioni' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    // Without a backend the status panel must say so, not render empty.
    await expect(
      page.getByText(/Backend non raggiungibile|Il backend risponde/).first(),
    ).toBeVisible();
  });

  test('models is a real library, not a "coming soon"', async ({ page }) => {
    await page.goto('/models', { waitUntil: 'domcontentloaded' });

    await expect(page.getByRole('heading', { name: 'Modelli', level: 1 })).toBeVisible();
    await expect(page.getByText('In arrivo')).toHaveCount(0);
    // No backend in this job: the library must say it could not load, with a
    // way to retry — or render the table when a backend is there.
    await expect(
      page.getByRole('table').or(page.getByRole('button', { name: /Riprova/ })).first(),
    ).toBeVisible({ timeout: 15000 });
  });

  test('help opens and leads to the service status', async ({ page }) => {
    await page.goto('/projects', { waitUntil: 'domcontentloaded' });
    const sidebar = page.getByRole('complementary', {
      name: 'Navigazione principale',
    });

    await sidebar.getByRole('button', { name: 'Aiuto' }).click();
    const help = page.getByRole('dialog', { name: 'Aiuto' });
    await expect(help).toBeVisible();

    await help.getByRole('button', { name: /stato del servizio/ }).click();
    await expect(page.getByRole('dialog', { name: 'Stato del servizio' })).toBeVisible();
  });
});
