import { test, expect } from "@playwright/test";

/**
 * `process.json` non sta piu' nel pacchetto d'ingresso: arriva a richiesta
 * (`frontend/src/lib/i18n`). I test unitari lo precaricano nel setup, quindi
 * non lo vedrebbero mai mancare; qui lo si guarda dal browser vero.
 *
 * La pagina del cliente ha un ingresso suo e parla solo con `process.json`, e
 * senza token nell'indirizzo risponde senza chiamare l'API: e' il punto piu'
 * piccolo in cui un namespace che non arriva si leggerebbe come chiave nuda.
 */
const cases = [
  { language: "it", title: "Questo link non funziona" },
  { language: "en", title: "This link does not work" },
] as const;

for (const { language, title } of cases) {
  test(`the client page reads process translations loaded on demand (${language})`, async ({ page }) => {
    await page.addInitScript((lng) => localStorage.setItem("delir-language", lng), language);
    await page.goto("/share.html");

    await expect(page.getByRole("heading", { level: 1 })).toHaveText(title);
    await expect(page.locator("body")).not.toContainText("handover.dashboard");
  });
}
