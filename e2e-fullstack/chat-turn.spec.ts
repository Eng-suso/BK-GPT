import { expect, test, type Page } from '@playwright/test';

/**
 * Un turno di chat, dall'interfaccia fino al database e ritorno.
 *
 * Nessun `page.route`: quello che si legge a schermo lo ha scritto il backend,
 * e quello che resta dopo un ricaricamento lo ha salvato Postgres. E' il
 * percorso che nessuna spec di `e2e/` attraversa, e quindi il percorso dove i
 * difetti B7 e B9 sono vissuti senza che nessun test li vedesse.
 *
 * Il modello non viene chiamato: `DELIR_FAKE_LLM=1` risponde con uno stub che
 * riporta il testo ricevuto, quindi si puo' asserire su cosa e' arrivato.
 */

/** Il compositore, non la ricerca in alto: due caselle di testo sulla pagina. */
function composer(page: Page) {
  return page.getByRole('textbox', { name: 'Scrivi un messaggio…' });
}

/** L'ultima risposta dell'assistente. Ce ne sono tante quante i turni. */
function lastAnswer(page: Page) {
  return page.getByText('[fake-llm]').last();
}

/**
 * Un testo diverso a ogni passata.
 *
 * Il workspace di prova e' vero e resta: due esecuzioni della stessa spec
 * lascerebbero due conversazioni con lo stesso titolo, e il selettore che ne
 * cerca una le troverebbe entrambe. Non si azzera il database fra una passata e
 * l'altra di proposito - un e2e che pretende un database vergine nasconde
 * proprio i difetti che compaiono su dati gia' esistenti.
 */
function unico(testo: string): string {
  return `${testo} ${Date.now().toString(36)}`;
}

async function ask(page: Page, question: string) {
  await composer(page).fill(question);
  await composer(page).press('Enter');
}

/**
 * Le spec scrivono su un workspace vero e condiviso: ogni prova parte da una
 * conversazione sua, altrimenti la seconda erediterebbe i turni della prima e
 * un rosso non direbbe quale delle due ha sbagliato.
 */
test.beforeEach(async ({ page }) => {
  await page.goto('/consultant');
  // `exact` perche' la stessa pagina ha anche "Cerca nella cronologia" e
  // "Svuota cronologia": senza, il selettore ne trova tre.
  await page.getByRole('button', { name: 'Cronologia', exact: true }).click();
  await page.getByRole('button', { name: 'Nuova chat' }).click();
  await expect(composer(page)).toBeVisible();
});

test.describe('Chat consulente', () => {
  test('una risposta arriva dal backend e sopravvive al ricaricamento', async ({ page }) => {
    const asked = unico('ricostruiamo il ciclo passivo');
    await ask(page, asked);

    // Lo stub riporta cosa gli e' stato chiesto: se questo testo compare, ha
    // risposto il backend e non un finto di Playwright.
    await expect(lastAnswer(page)).toContainText(asked);

    // Il turno vive nella memoria del browser finche' non lo salva il backend:
    // ricaricare e' il modo di chiedere chi dei due lo aveva davvero.
    await page.reload();

    await expect(lastAnswer(page)).toContainText(asked);
  });

  test('una conversazione eliminata non torna indietro', async ({ page }) => {
    const asked = unico('questa conversazione va cancellata');
    await ask(page, asked);
    await expect(lastAnswer(page)).toContainText(asked);

    // Si cancella dalla riga nella cronologia, che e' il gesto vero: il menu
    // "Altre azioni" mostra la voce solo quando il thread e' gia' selezionato.
    // L'elenco e' gia' aperto da `beforeEach`, e la conversazione appena
    // aperta e' la prima. Non si cerca per nome: l'elenco tronca i titoli
    // lunghi, quindi il nome a schermo non e' quello che si e' scritto.
    const corrente = page.getByRole('listitem').first();
    await corrente.getByRole('button', { name: /^Elimina thread/ }).click();

    // X1: cancellare passa da una domanda, e la domanda dice cosa si perde.
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText('Non si torna indietro.')).toBeVisible();
    await dialog.getByRole('button', { name: 'Elimina la conversazione' }).click();

    await expect(dialog).toBeHidden();
    await page.reload();

    await expect(page.getByText(asked, { exact: false })).toHaveCount(0);
  });
});
