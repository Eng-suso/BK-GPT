import { expect, test, type Page } from '@playwright/test';

/**
 * Il gate al salvataggio, visto dal consulente.
 *
 * `scripts/seed_e2e.py` scrive il processo "Approvazione fatture" con un piano
 * pendente il cui flusso va in deadlock: una scelta esclusiva che finisce in un
 * gateway parallelo. Il piano supera la prontezza; e' il gate L3 del disegno
 * (analisi a token, `backend/bpmn/xml_behavior.py`) a rifiutarlo quando il
 * consulente approva. Qui si verifica che il rifiuto arrivi a schermo come una
 * frase di consulenza - il nome del passaggio, nessun ID o path XML - e che
 * niente sia stato salvato.
 */

const PROCESS_URL = '/projects/riorganizzazione-ciclo-passivo/processes/approvazione-fatture';

function modelingBar(page: Page) {
  return page.getByRole('region', { name: 'Workspace di modellazione BPMN' });
}

async function openReview(page: Page) {
  await page.goto(PROCESS_URL);
  const open = modelingBar(page).getByRole('button', { name: /^(Decidi|Apri review)$/ });
  await expect(open).toBeVisible();
  await open.click();
  const sheet = page.getByRole('dialog');
  await expect(sheet).toBeVisible();
  return sheet;
}

test.describe('Gate BPMN al salvataggio', () => {
  test('un piano in deadlock non si approva e il consulente legge perche', async ({ page }) => {
    const sheet = await openReview(page);

    await sheet.getByRole('button', { name: 'Approva e genera BPMN' }).click();

    const notice = page.getByText("Il diagramma non è stato salvato", { exact: false });
    await expect(notice).toBeVisible();
    await expect(notice).toContainText('«Entrambe le verifiche concluse»');
    await expect(notice).toContainText("Il canvas resta com'era.");
    // Niente di tecnico: ne' l'ID del gateway, ne' il livello del gate, ne'
    // diagnostica XSD.
    await expect(notice).not.toContainText('Sync');
    await expect(notice).not.toContainText('BPMN L3');
    await expect(notice).not.toContainText('XSD');
    await expect(page.getByText('BPMN generato e salvato.')).toHaveCount(0);

    // Il piano resta pendente: ricaricando, la review e' ancora da approvare.
    await page.reload();
    await expect(
      modelingBar(page).getByRole('button', { name: /^(Decidi|Apri review)$/ }),
    ).toBeVisible();
  });
});
