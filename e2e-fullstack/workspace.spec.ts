import { expect, test } from '@playwright/test';

/**
 * Il percorso di chi lavora: cliente, incarico, processo.
 *
 * I dati sono quelli scritti da `scripts/seed_e2e.py` e arrivano da Postgres
 * passando dal backend. Le spec di `e2e/` disegnano le stesse schermate con
 * risposte finte: qui si verifica che il prodotto le sappia produrre, che e'
 * un'altra domanda.
 */

const CLIENTE = 'Esaote S.p.A.';
const INCARICO = 'Riorganizzazione ciclo passivo';
const PROCESSO = 'Ciclo passivo';

test.describe('Workspace', () => {
  test('il cliente seminato compare nel suo elenco', async ({ page }) => {
    await page.goto('/clients');

    await expect(page.getByRole('heading', { name: 'Clienti', level: 1 })).toBeVisible();
    // Il nome compare due volte: nella tabella e nella scheda di sintesi.
    await expect(page.getByText(CLIENTE).first()).toBeVisible();
    await expect(page.getByText('Medicale').first()).toBeVisible();
  });

  test('dall elenco incarichi si arriva al processo', async ({ page }) => {
    await page.goto('/projects');

    await expect(page.getByRole('heading', { name: 'Progetti', level: 1 })).toBeVisible();
    await page.getByText(INCARICO).first().click();

    // La scheda dell'incarico: da qui si entra nel processo, ed e' il passaggio
    // che porta dentro lo studio.
    await expect(page).toHaveURL(/\/projects\/riorganizzazione-ciclo-passivo$/);
    await expect(page.getByText(PROCESSO).first()).toBeVisible();
  });

  test('lo studio di processo apre il suo indirizzo profondo', async ({ page }) => {
    // Gli id del seed sono slug stabili: un indirizzo profondo non e' un caso
    // fortunato, e' quello che un consulente si manda per email.
    await page.goto('/projects/riorganizzazione-ciclo-passivo/processes/ciclo-passivo');

    await expect(page.getByText(PROCESSO).first()).toBeVisible();
    // La schermata pesante arriva a richiesta (U2): non deve restare uno
    // scheletro.
    await expect(page.locator('main [aria-busy="true"]')).toHaveCount(0);
  });

  test('un indirizzo inventato lo dice, invece di rimandare in silenzio', async ({ page }) => {
    // X3 con il backend acceso. Una rotta che non esiste e un incarico che non
    // esiste sono due cose diverse, e prima il prodotto le confondeva: il
    // secondo caso mostrava "errore di caricamento" con un tasto Riprova che
    // non avrebbe funzionato mai.
    await page.goto('/questa-rotta-non-esiste');
    await expect(page.getByText('Questa pagina non esiste')).toBeVisible();

    await page.goto('/projects/questo-incarico-non-esiste-affatto');
    await expect(page.getByText('Questo incarico non esiste')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Riprova' })).toHaveCount(0);
  });
});
