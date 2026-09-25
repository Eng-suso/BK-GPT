import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

/**
 * Chi non usa il mouse deve poter lavorare.
 *
 * Axe girava su una schermata sola, la Home, che e' anche la piu' semplice:
 * studio, canvas, simulazione, elenchi e impostazioni - cioe' il prodotto -
 * non erano mai stati scansionati. Qui ci sono le superfici principali.
 *
 * Il backend non c'e' in questo job, quindi molte schermate mostrano il loro
 * stato di errore o di vuoto: va bene, sono schermate anche quelle, e sono
 * quelle che un consulente vede quando il servizio non risponde.
 */

const SURFACES: { name: string; path: string }[] = [
  { name: 'Home', path: '/home' },
  { name: 'Chat consulente', path: '/consultant' },
  { name: 'Clienti', path: '/clients' },
  { name: 'Incarichi', path: '/projects' },
  { name: 'Modelli', path: '/models' },
  { name: 'Archivio', path: '/archive' },
  { name: 'Impostazioni', path: '/settings' },
  { name: 'Indirizzo inesistente', path: '/questa-non-esiste' },
];

async function seriousViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();

  for (const violation of results.violations) {
    console.log(`- [${violation.impact?.toUpperCase()}] ${violation.id}: ${violation.help}`);
    console.log(`  Target: ${violation.nodes.map((n) => n.target).join(', ')}`);
    console.log(`  Help: ${violation.helpUrl}`);
  }

  return results.violations.filter(
    (v) => v.impact === 'critical' || v.impact === 'serious',
  );
}

test.describe('Accessibilita (WCAG 2.1 AA)', () => {
  for (const surface of SURFACES) {
    test(`${surface.name} non ha barriere gravi`, async ({ page }) => {
      await page.goto(surface.path);
      // Le schermate arrivano a richiesta: si aspetta il contenuto, non il
      // solo `domcontentloaded`, altrimenti axe scansiona lo scheletro.
      await page.waitForLoadState('networkidle');
      await expect(page.locator('main')).toBeVisible();

      expect(await seriousViolations(page)).toEqual([]);
    });
  }

  test('i dialoghi della shell restano raggiungibili da tastiera', async ({ page }) => {
    await page.goto('/projects');
    await page.waitForLoadState('networkidle');

    const sidebar = page.getByRole('complementary', { name: 'Navigazione principale' });
    await sidebar.getByRole('button', { name: 'Aiuto' }).click();
    await expect(page.getByRole('dialog')).toBeVisible();

    // Un dialogo e' il posto dove una barriera costa di piu': se il focus non
    // ci entra, chi naviga da tastiera resta fuori dal prodotto.
    expect(await seriousViolations(page)).toEqual([]);
  });
});
