import { defineConfig, devices } from '@playwright/test';

/**
 * L'e2e che attraversa il prodotto.
 *
 * `playwright.config.ts` avvia solo il frontend e ogni spec sostituisce il
 * backend con `page.route`: quelle prove dicono che l'interfaccia sa disegnare
 * una risposta, non che il prodotto la produca. Qui girano invece frontend,
 * backend e Postgres insieme, su un workspace scritto da
 * `scripts/seed_e2e.py`, e nessuna spec intercetta la rete.
 *
 * Il modello non viene mai chiamato: `DELIR_FAKE_LLM=1` sostituisce la runtime
 * dell'agente con uno stub deterministico (`backend/services/agent_runtime.py`),
 * quindi la suite non spende e non dipende da cosa risponde un modello oggi.
 *
 *     npm run test:e2e:fullstack
 *
 * Serve `WORKSPACE_DATABASE_URL` che punti a un database dedicato: le spec
 * scrivono davvero.
 */

const BACKEND_PORT = Number(process.env.DELIR_E2E_BACKEND_PORT ?? 8010);
const FRONTEND_PORT = Number(process.env.DELIR_E2E_FRONTEND_PORT ?? 3031);
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;

export default defineConfig({
  testDir: './e2e-fullstack',
  fullyParallel: false,
  // Le spec scrivono sullo stesso workspace: in parallelo si guarderebbero le
  // scritture a vicenda, e un rosso non direbbe quale delle due ha sbagliato.
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // Un turno di chat vero passa dal grafo dell'agente: piu' lento di una
  // risposta finta servita da `page.route`, anche con il modello stubbato.
  timeout: 90 * 1000,
  expect: { timeout: 20 * 1000 },
  reporter: [['html', { open: 'never', outputFolder: 'playwright-report-fullstack' }], ['list']],

  use: {
    baseURL: `http://127.0.0.1:${FRONTEND_PORT}`,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],

  webServer: [
    {
      command: `uv run uvicorn backend.app:app --host 127.0.0.1 --port ${BACKEND_PORT}`,
      url: `${BACKEND_URL}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 180 * 1000,
      env: {
        // Nessuna chiamata al modello, in nessun ramo.
        DELIR_FAKE_LLM: '1',
        OPENAI_API_KEY: '',
        TAVILY_API_KEY: '',
        MEM0_API_KEY: '',
        LANGSMITH_TRACING: 'false',
        // I worker in-process drenano code che qui non servono e che
        // rallenterebbero l'avvio.
        WORKERS_IN_PROCESS: 'false',
      },
    },
    {
      command: `npm --prefix frontend run dev -- --host 127.0.0.1 --port ${FRONTEND_PORT}`,
      url: `http://127.0.0.1:${FRONTEND_PORT}`,
      reuseExistingServer: !process.env.CI,
      timeout: 180 * 1000,
      env: {
        // Il nome che legge `frontend/src/lib/api.ts`: senza, il frontend
        // parlerebbe con la porta 8000, cioe' con il backend di sviluppo di chi
        // sta lavorando, e i test scriverebbero nel suo workspace.
        VITE_API_BASE_URL: BACKEND_URL,
      },
    },
  ],
});
