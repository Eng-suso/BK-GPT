import { defineConfig, devices } from '@playwright/test';

import { BACKEND_PORT, CONSULTANT, FRONTEND_PORT, SHARED_TOKEN, TENANT, localSupabase } from './e2e-auth/supabase';

/**
 * Il login per persona, attraverso il prodotto: browser, Supabase Auth locale
 * (ES256, sign-up chiusi), backend FastAPI che verifica i token, Postgres.
 * Nessuna spec intercetta la rete.
 *
 *     npm run supabase:start
 *     npm run test:e2e:auth
 *
 * Serve `WORKSPACE_DATABASE_URL` verso un database dedicato e seminato con
 * `npm run seed:e2e`, come per `playwright.fullstack.config.ts`.
 */

const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;
const FRONTEND_URL = `http://127.0.0.1:${FRONTEND_PORT}`;
const supabase = localSupabase();

export default defineConfig({
  testDir: './e2e-auth',
  globalSetup: './e2e-auth/global-setup.ts',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  timeout: 90 * 1000,
  expect: { timeout: 20 * 1000 },
  reporter: [['html', { open: 'never', outputFolder: 'playwright-report-auth' }], ['list']],
  use: {
    baseURL: FRONTEND_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `uv run uvicorn backend.app:app --host 127.0.0.1 --port ${BACKEND_PORT}`,
      url: `${BACKEND_URL}/health`,
      // Mai un server gia' acceso: deve girare con questa configurazione.
      reuseExistingServer: false,
      timeout: 180 * 1000,
      env: {
        DELIR_ENVIRONMENT: 'dev',
        DELIR_AUTH_ENABLED: 'true',
        DELIR_AUTH_PROVIDER: 'supabase',
        SUPABASE_URL: supabase.apiUrl,
        SUPABASE_PUBLISHABLE_KEY: supabase.publishableKey,
        DELIR_API_TOKEN: SHARED_TOKEN,
        DELIR_ADMIN_TOKEN: 'chiave-admin-e2e-distinta-dal-token-api-000',
        DELIR_ALLOWED_TENANT_IDS: TENANT,
        // Le persone ammesse: chi ha un account Supabase ma non e' qui riceve 403.
        DELIR_ALLOWED_EMAILS: CONSULTANT.email,
        DELIR_DEFAULT_TENANT_ID: TENANT,
        DELIR_CORS_ORIGINS: FRONTEND_URL,
        DELIR_FAKE_LLM: '1',
        OPENAI_API_KEY: '',
        TAVILY_API_KEY: '',
        MEM0_API_KEY: '',
        LANGSMITH_TRACING: 'false',
        WORKERS_IN_PROCESS: 'false',
      },
    },
    {
      command: `npm --prefix frontend run dev -- --host 127.0.0.1 --port ${FRONTEND_PORT} --strictPort`,
      url: FRONTEND_URL,
      reuseExistingServer: false,
      timeout: 180 * 1000,
      env: { VITE_API_BASE_URL: BACKEND_URL },
    },
  ],
});
