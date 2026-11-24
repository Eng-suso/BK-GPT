import { expect, test, type Page } from '@playwright/test';

import { BACKEND_PORT, CONSULTANT, SHARED_TOKEN, TENANT } from './supabase';

/**
 * Il login per persona, da cima a fondo: nessuna `page.route`, il token che il
 * backend verifica e' quello che Supabase ha firmato.
 */

const CLIENTE = 'Esaote S.p.A.';

async function signIn(page: Page, tenant: string, email: string, password: string) {
  await page.getByLabel('Tenant').fill(tenant);
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Entra' }).click();
}

function supabaseSession(page: Page) {
  return page.evaluate(() => sessionStorage.getItem('delir:supabase-session'));
}

test.describe('Login Supabase', () => {
  test('senza sessione il workspace non viene nemmeno chiesto', async ({ page }) => {
    const workspaceCalls: string[] = [];
    page.on('request', (request) => {
      if (request.url().includes('/v1/workspace')) workspaceCalls.push(request.url());
    });

    await page.goto('/clients');

    await expect(page.getByLabel('Email')).toBeVisible();
    await expect(page.getByLabel('Token API')).toHaveCount(0);
    expect(workspaceCalls).toEqual([]);
  });

  test('una password sbagliata non apre niente', async ({ page }) => {
    await page.goto('/clients');
    await signIn(page, TENANT, CONSULTANT.email, 'password-sbagliata-000');

    await expect(page.getByRole('alert')).toHaveText('Email o password non validi.');
    await expect(page.getByLabel('Email')).toBeVisible();
  });

  test('con le credenziali giuste il backend riconosce la persona', async ({ page }) => {
    const authorizations: string[] = [];
    page.on('request', (request) => {
      const value = request.headers().authorization;
      if (request.url().includes('/v1/workspace') && value) authorizations.push(value);
    });

    await page.goto('/clients');
    await signIn(page, TENANT, CONSULTANT.email, CONSULTANT.password);

    await expect(page.getByRole('heading', { name: 'Clienti', level: 1 })).toBeVisible();
    await expect(page.getByText(CLIENTE).first()).toBeVisible();
    // Al backend arriva il JWT firmato da Supabase, non un token condiviso.
    expect(authorizations.length).toBeGreaterThan(0);
    expect(authorizations.every((value) => /^Bearer [\w-]+\.[\w-]+\.[\w-]+$/.test(value))).toBe(true);

    await page.getByRole('button', { name: /Spazio di lavoro/ }).click();
    await expect(page.getByRole('menuitem', { name: 'Esci' })).toBeVisible();
    await expect(page.getByText('Accesso personale').first()).toBeVisible();

    // Niente in localStorage: la sessione vive solo in questa scheda.
    const local = await page.evaluate(() => JSON.stringify({ ...localStorage }));
    expect(local).not.toContain('access_token');
    expect(await supabaseSession(page)).not.toBeNull();
  });

  test('la sessione resta al reload e finisce con Esci', async ({ page }) => {
    await page.goto('/clients');
    await signIn(page, TENANT, CONSULTANT.email, CONSULTANT.password);
    await expect(page.getByText(CLIENTE).first()).toBeVisible();

    await page.reload();
    await expect(page.getByText(CLIENTE).first()).toBeVisible();
    await expect(page.getByLabel('Email')).toHaveCount(0);

    await page.getByRole('button', { name: /Spazio di lavoro/ }).click();
    await page.getByRole('menuitem', { name: 'Esci' }).click();
    await expect(page.getByLabel('Email')).toBeVisible();
    expect(await supabaseSession(page)).toBeNull();
  });

  test('uno spazio di lavoro fuori dalla allowlist chiude la sessione appena aperta', async ({ page }) => {
    await page.goto('/clients');
    await signIn(page, 'altro-spazio', CONSULTANT.email, CONSULTANT.password);

    await expect(page.getByRole('alert')).toContainText('non è autorizzato');
    await expect(page.getByLabel('Email')).toBeVisible();
    expect(await supabaseSession(page)).toBeNull();
  });

  test('il token condiviso del pilota non apre piu il backend', async ({ request }) => {
    const response = await request.get(`http://127.0.0.1:${BACKEND_PORT}/v1/auth/me`, {
      headers: { Authorization: `Bearer ${SHARED_TOKEN}`, 'X-DeliR-Tenant-ID': TENANT },
    });

    expect(response.status()).toBe(401);
  });
});
