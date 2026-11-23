import { expect, test } from "@playwright/test";
import { IDS } from "./launch-media/demo";
import { installDemoApi } from "./launch-media/mockApi";

test("consultant can inspect all event log rows without choosing a separator", async ({ page }) => {
  await installDemoApi(page, "it");
  await page.route(`**/v1/workspace/event-logs/*/preview*`, async (route) => {
    const url = new URL(route.request().url());
    const offset = Number(url.searchParams.get("offset") ?? 0);
    const limit = Number(url.searchParams.get("limit") ?? 20);
    const rows = Array.from({ length: 120 }, (_, index) => [`PO-${index + 1}`, "Ricevi richiesta", "2026-01-05T09:10:00", "anna"]);
    await route.fulfill({ json: { format: "csv", delimiter: ";", columns: ["Ordine", "Attivita", "Fine", "Utente"], row_count: 120, sample_rows: rows.slice(offset, offset + limit) } });
  });
  await page.goto(`/projects/${IDS.project}/processes/${IDS.process}/simulation`);
  await page.getByRole("button", { name: "Analisi", exact: true }).click();
  await page.getByRole("menuitem", { name: "Event log", exact: true }).click();
  await page.getByRole("button", { name: /^export-workflow-acquisti\.csv/ }).first().click();
  await page.getByRole("button", { name: "Colonne", exact: true }).click();
  await expect(page.getByRole("region", { name: "Righe dell'event log" })).toBeVisible();
  await expect(page.getByText("120 righe nel file")).toBeVisible();
  await page.getByRole("button", { name: "Esplora tutto il file" }).click();
  await expect(page.getByText("Righe 1–50 di 120")).toBeVisible();
  await page.getByRole("button", { name: "Righe successive" }).click();
  await expect(page.getByText("Righe 51–100 di 120")).toBeVisible();
  await expect(page.getByRole("region", { name: "Righe dell'event log" })).toContainText("PO-51");
});
