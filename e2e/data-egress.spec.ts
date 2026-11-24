import { expect, test } from '@playwright/test';

/**
 * Impostazioni -> "Dati inviati all'esterno" (SEC-06).
 *
 * Il backend non gira in questo job: la rotta dell'inventario si simula con la
 * forma che `GET /v1/observability/egress` restituisce davvero. Si verifica
 * che il consulente veda chi riceve i dati, cosa riceve e cosa e' bloccato.
 */

const inventory = {
  environment: 'prod',
  enforced: true,
  localTracePayload: false,
  routes: [
    {
      destination: 'llm_chat',
      purpose: 'Modello linguistico: chat, estrazione dei processi, revisione, simulazione assistita',
      host: 'api.openai.com',
      internal: false,
      active: true,
      allowed: true,
      data: ['customer_content'],
      tasks: ['chat_turn', 'plan_extraction'],
    },
    {
      destination: 'transcription',
      purpose: 'Trascrizione dei file audio delle interviste',
      host: 'api.openai.com',
      internal: false,
      active: true,
      allowed: true,
      data: ['audio', 'customer_content'],
      tasks: ['transcription'],
    },
    {
      destination: 'tracing',
      purpose: 'Tracing delle chiamate al modello (LangSmith)',
      host: 'api.smith.langchain.com',
      internal: false,
      active: true,
      allowed: false,
      data: ['prompt_trace', 'customer_content'],
      tasks: [],
    },
    {
      destination: 'web_search',
      purpose: "Ricerca web dell'agente (Tavily)",
      host: 'api.tavily.com',
      internal: false,
      active: false,
      allowed: true,
      data: ['search_query'],
      tasks: [],
    },
    {
      destination: 'document_reader',
      purpose: 'Lettura di PDF, DOCX e PPTX (docling-serve)',
      host: 'docling',
      internal: true,
      active: true,
      allowed: true,
      data: ['customer_content'],
      tasks: [],
    },
  ],
};

test.describe("Dati inviati all'esterno", () => {
  test('the settings page says who receives customer data and what is blocked', async ({ page }) => {
    await page.route('**/v1/observability/egress', (route) => route.fulfill({ json: inventory }));

    await page.goto('/settings', { waitUntil: 'domcontentloaded' });

    const section = page.getByRole('region', { name: "Dati inviati all'esterno" });
    await section.scrollIntoViewIfNeeded();
    await expect(section.getByText('3 fornitori esterni ricevono dati.', { exact: false })).toBeVisible();
    await expect(section.getByText(/Solo gli host autorizzati/)).toBeVisible();

    const transcription = section.getByRole('listitem').filter({ hasText: 'Trascrizione dei file audio' });
    await expect(transcription.getByText('Audio', { exact: true })).toBeVisible();
    await expect(transcription.getByText('api.openai.com')).toBeVisible();

    const tracing = section.getByRole('listitem').filter({ hasText: 'LangSmith' });
    await expect(tracing.getByText(/Non autorizzato/)).toBeVisible();

    await expect(section.getByText(/Servizio interno/)).toBeVisible();
    // Spenta: non riceve niente, quindi non compare.
    await expect(section.getByText('Tavily')).toHaveCount(0);
  });

  test('an unreadable inventory says so and offers a retry', async ({ page }) => {
    await page.route('**/v1/observability/egress', (route) => route.fulfill({ status: 503, json: {} }));

    await page.goto('/settings', { waitUntil: 'domcontentloaded' });

    const section = page.getByRole('region', { name: "Dati inviati all'esterno" });
    await expect(section.getByRole('alert')).toContainText('Elenco dei destinatari non leggibile.');
    await expect(section.getByRole('button', { name: 'Aggiorna' })).toBeVisible();
  });
});
