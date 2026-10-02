import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test('una procedura caricata diventa una fonte leggibile', async ({ page }) => {
  await page.goto('/projects/riorganizzazione-ciclo-passivo');
  await page.getByRole('tab', { name: 'Fonti' }).click();

  await page.getByRole('button', { name: 'Aggiungi fonte' }).click();
  await page.getByLabel('File da analizzare').setInputFiles({
    name: 'procedura-acquisti.md',
    mimeType: 'text/markdown',
    buffer: Buffer.from('# Procedura acquisti\nIl CFO approva gli ordini sopra EUR 30.000.'),
  });
  await page.getByLabel('Descrive come si lavora').check();
  await page.getByLabel('Contiene regole da rispettare').check();
  await page.getByLabel('Ambito').selectOption({ label: 'Ciclo passivo' });
  const [uploadResponse] = await Promise.all([
    page.waitForResponse((response) => response.url().endsWith('/sources/upload')),
    page.getByRole('button', { name: 'Carica e analizza' }).click(),
  ]);
  expect([200, 201]).toContain(uploadResponse.status());

  await expect(page.getByRole('dialog', { name: 'Aggiungi una fonte' })).toBeHidden();
  await expect(page.getByText('procedura-acquisti.md')).toBeVisible();
  await page.getByRole('button', { name: /Apri fonte: procedura-acquisti\.md/ }).click();
  await expect(page.getByText('Come si lavora, Regole da rispettare', { exact: true })).toBeVisible();
  await expect(page.getByText(/Il CFO approva gli ordini sopra EUR 30\.000/)).toBeVisible();
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Scarica originale' }).click();
  const download = await downloadPromise;
  const savedPath = await download.path();
  expect(savedPath).not.toBeNull();
  expect((await readFile(savedPath!)).toString('utf8')).toContain('Il CFO approva');
});
