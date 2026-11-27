import { expect, test, type Page } from '@playwright/test';

/**
 * Il contatore d'uso della prova nella barra in alto.
 *
 * Solo frontend: la risposta di `/v1/usage/me` si finge qui, nei tre stati che
 * il consulente incontra (ritmo da tenere d'occhio, quasi al limite, fermo).
 * Gli screenshot finiscono in `docs/usage-limits/ux/` per la verifica visiva.
 */

const inHours = (hours: number) => new Date(Date.now() + hours * 3_600_000).toISOString();

function windowState(share: number, resetsInHours: number | null, exhausted = false) {
  return {
    used_share: share,
    limited: true,
    exhausted,
    started_at: inHours(-1),
    resets_at: resetsInHours === null ? null : inHours(resetsInHours),
  };
}

function audio(weekUsed: number, trialUsed: number, blocking: 'week' | 'trial' | null = null) {
  return {
    week: { used_seconds: weekUsed, limit_seconds: 6 * 3600, exhausted: weekUsed >= 6 * 3600, resets_at: inHours(50) },
    trial: { used_seconds: trialUsed, limit_seconds: 10 * 3600, exhausted: trialUsed >= 10 * 3600, resets_at: inHours(24 * 8) },
    blocking,
  };
}

const STATES = {
  forecast: {
    enabled: true,
    session_hours: 5,
    session: windowState(0.64, 3),
    week: windowState(0.42, 96),
    trial: { ...windowState(0.18, 24 * 10), over: false },
    blocking: null,
    forecast: { window: 'session', exhausts_at: inHours(1.5), resets_at: inHours(3) },
    audio: audio(2 * 3600 + 600, 3 * 3600),
  },
  nearLimit: {
    enabled: true,
    session_hours: 5,
    session: windowState(0.35, 4),
    week: windowState(0.91, 30),
    trial: { ...windowState(0.6, 24 * 6), over: false },
    blocking: null,
    forecast: null,
    audio: audio(5 * 3600 + 1800, 7 * 3600),
  },
  audioUsedUp: {
    enabled: true,
    session_hours: 5,
    session: windowState(0.3, 4),
    week: windowState(0.5, 50),
    trial: { ...windowState(0.35, 24 * 8), over: false },
    blocking: null,
    forecast: null,
    audio: audio(6 * 3600, 8 * 3600, 'week'),
  },
  blocked: {
    enabled: true,
    session_hours: 5,
    session: windowState(1, 2, true),
    week: windowState(0.7, 50),
    trial: { ...windowState(0.4, 24 * 8), over: false },
    blocking: 'session',
    forecast: null,
    audio: audio(3600, 4 * 3600),
  },
} as const;

async function mockUsage(page: Page, body: unknown) {
  await page.route('**/v1/usage/me', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  );
}

for (const [name, body] of Object.entries(STATES)) {
  test(`usage meter: ${name}`, async ({ page }, testInfo) => {
    await mockUsage(page, body);
    await page.goto('/projects', { waitUntil: 'domcontentloaded' });
    // Il cassetto del telefono si apre da solo su alcune viste: chiuso, la barra e' raggiungibile.
    await page.keyboard.press('Escape');

    const ring = page.getByRole('button', { name: /^Utilizzo: \d+% del limite più vicino$/ });
    await expect(ring).toBeVisible();
    await ring.click();

    await expect(page.getByRole('progressbar', { name: 'Sessione corrente' })).toBeVisible();
    await expect(page.getByRole('progressbar', { name: 'Limite settimanale' })).toBeVisible();
    if (name === 'blocked') await expect(page.getByRole('alert')).toContainText('Sessione esaurita');
    if (name === 'forecast') await expect(page.getByText('Attenzione al ritmo')).toBeVisible();
    if (name === 'audioUsedUp') await expect(page.getByText('Ore di registrazione finite')).toBeVisible();
    await expect(page.getByRole('progressbar', { name: 'Ore di registrazione questa settimana' })).toBeVisible();

    await page.screenshot({
      path: `docs/usage-limits/ux/${testInfo.project.name}-${name}.png`,
      fullPage: false,
    });
  });
}

test('usage meter: hidden when limits are off', async ({ page }) => {
  await mockUsage(page, { ...STATES.forecast, enabled: false });
  await page.goto('/projects', { waitUntil: 'domcontentloaded' });
  await page.keyboard.press('Escape');

  await expect(page.getByRole('banner')).toBeVisible();
  await expect(page.getByRole('button', { name: /^Utilizzo:/ })).toHaveCount(0);
});
