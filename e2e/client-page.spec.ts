import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * La pagina del cliente (P1.16): i file che valgono per tutti i suoi progetti.
 *
 * Ci si arriva dalla ricerca globale, che trova anche le fonti del cliente, e
 * da li' si carica un file per tutto il cliente. Il backend e' finto ma
 * risponde con la forma vera. Le schermate finiscono negli output del test
 * per la verifica visiva desktop e mobile.
 */

const API = "http://127.0.0.1:8000";

const CLIENT = {
  id: "c-esaote",
  name: "Esaote",
  sector: "Medicale",
  status: "Attivo",
  projects: 2,
  next_activity: "Comitato acquisti",
  owner: "Sohayb Raqaq",
  contact: "",
  processes: [],
  documents: [],
  archived_at: null,
  archive_reason: null,
};

function clientSource(id: string, name: string) {
  return {
    id,
    project_id: null,
    client_id: CLIENT.id,
    process_id: null,
    name,
    type: "File",
    meta: "",
    roles: ["policy"],
    retention: "persistent",
    scopes: [],
    status: "approved",
    byte_size: 1800,
    content_hash: id,
    mime_type: "application/pdf",
    acquisition_status: "done",
    acquisition_error: null,
  };
}

async function fixture(page: Page, uploads: string[]) {
  const sources = [clientSource("src-policy", "policy-acquisti-gruppo.pdf")];
  await page.addInitScript(() => Object.assign(window, { DELIR_API_BASE: "http://127.0.0.1:8000" }));
  await page.route(`${API}/**`, async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/v1/workspace/clients" && request.method() === "GET") {
      return route.fulfill({ json: [CLIENT], headers: { "X-DeliR-Total": "1" } });
    }
    if (path === "/v1/workspace/search") {
      return route.fulfill({
        json: [
          {
            kind: "source",
            id: "src-policy",
            title: "policy-acquisti-gruppo.pdf",
            context: "Esaote",
            client_id: CLIENT.id,
            client_name: CLIENT.name,
            project_id: null,
            project_name: null,
            process_id: null,
            source_type: "File",
          },
        ],
      });
    }
    if (path === `/v1/workspace/clients/${CLIENT.id}/sources`) {
      return route.fulfill({ json: sources });
    }
    if (path === `/v1/workspace/clients/${CLIENT.id}/sources/upload`) {
      uploads.push(request.postData() ?? "");
      const created = clientSource("src-codice", "codice-etico.pdf");
      sources.push(created);
      return route.fulfill({ status: 201, json: { ...created, created: true, suggested_roles: null } });
    }
    return route.fulfill({ status: 200, json: null });
  });
}

for (const mobile of [false, true]) {
  test(`dalla ricerca alla pagina del cliente, e un file per tutto il cliente (${mobile ? "mobile" : "desktop"})`, async ({ page }, testInfo) => {
    const uploads: string[] = [];
    await fixture(page, uploads);
    await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 });
    await page.goto("/home");

    await page.getByRole("banner").getByRole("button", { name: /Cerca/ }).first().click();
    const search = page.getByRole("dialog", { name: "Cerca nel workspace" });
    await search.getByRole("combobox").fill("policy");
    await search.getByRole("option", { name: /policy-acquisti-gruppo\.pdf/ }).click();

    await expect(page).toHaveURL(/\/clients\/c-esaote$/);
    await expect(page.getByRole("heading", { name: "Esaote", level: 1 })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Fonti del cliente" })).toBeVisible();
    await expect(page.getByRole("button", { name: /policy-acquisti-gruppo\.pdf/ })).toBeVisible();
    // Niente scorrimento orizzontale: la pagina sta nella larghezza.
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    await page.screenshot({ path: testInfo.outputPath(`cliente-${mobile ? "mobile" : "desktop"}.png`), fullPage: true });

    await page.getByRole("button", { name: /aggiungi fonte/i }).click();
    const dialog = page.getByRole("dialog", { name: /aggiungi una fonte/i });
    await expect(dialog).toContainText("Ambito: Tutto il cliente «Esaote»");
    await dialog.getByLabel(/file da analizzare/i).setInputFiles({
      name: "codice-etico.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4 codice"),
    });
    await dialog.getByLabel(/regole da rispettare/i).check();
    await page.screenshot({ path: testInfo.outputPath(`carica-cliente-${mobile ? "mobile" : "desktop"}.png`) });
    await dialog.getByRole("button", { name: /^carica e analizza$/i }).click();

    await expect(dialog).toBeHidden();
    await expect(page.getByRole("button", { name: /codice-etico\.pdf/ })).toBeVisible();
    expect(uploads).toHaveLength(1);
    expect(uploads[0]).toContain("policy");
  });
}
