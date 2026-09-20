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
    // With or without a backend the panel must reach a verdict, never stay on
    // "checking": the dev server compiles on first navigation, so the window is
    // generous on purpose.
    await expect(
      page.getByText(/Backend non raggiungibile|Il backend risponde/).first(),
    ).toBeVisible({ timeout: 20000 });
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

  test('the top bar search opens the workspace search, by click and by keyboard', async ({
    page,
  }) => {
    await page.goto('/projects', { waitUntil: 'domcontentloaded' });

    await page.getByRole('banner').getByRole('button', { name: /Cerca/ }).first().click();
    const search = page.getByRole('dialog', { name: 'Cerca nel workspace' });
    await expect(search).toBeVisible();
    await expect(search.getByRole('combobox')).toBeFocused();

    await page.keyboard.press('Escape');
    await expect(search).toBeHidden();

    await page.keyboard.press('Control+k');
    await expect(page.getByRole('dialog', { name: 'Cerca nel workspace' })).toBeVisible();
  });

  test('the bell shows what happened, or says it cannot load it', async ({ page }) => {
    await page.goto('/projects', { waitUntil: 'domcontentloaded' });

    const bell = page.getByRole('banner').getByRole('button', { name: /Avvisi/ });
    await expect(bell).toBeVisible({ timeout: 20000 });
    // The badge is the unread count or nothing at all — never the hardcoded 3
    // this control used to show.
    await expect(bell).toHaveText(/^(|[1-9]|9\+)$/);

    await bell.click();
    // One of the three honest answers: a list, "nothing happened", or "could
    // not load" — never a spinner that never resolves.
    await expect(
      page.getByText(/Impossibile caricare gli avvisi|Nessun avviso|da rivedere|Simulazione|Piano/).first(),
    ).toBeVisible({ timeout: 20000 });
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
