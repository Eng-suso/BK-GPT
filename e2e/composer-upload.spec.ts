import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * Caricare un file dal + della chat del consulente.
 *
 * La chat del consulente non ha un progetto: prima del file si sceglie dove
 * metterlo. Il backend qui e' finto e risponde con la forma vera delle fonti.
 */

const API = "http://127.0.0.1:8000";

const PROJECT = {
  id: "p-acquisti",
  client_id: "c-esaote",
  client: "Esaote",
  name: "Riorganizzazione acquisti",
  objective: "",
  lead: null,
  start_date: null,
  end_date: null,
  phase: "Discovery",
  status: "In corso",
  progress: 40,
  processes: 1,
  next_step: "",
  milestones: [],
  open_issues: [],
  deliverables: [],
  archived_at: null,
  archive_reason: null,
  process_items: [
    {
      id: "proc-p2p",
      project_id: "p-acquisti",
      bpmn_model_id: "m-p2p",
      name: "Procure to pay",
      stage: "As-Is",
      status: "In corso",
      owner: "",
      readiness: 30,
      archived_at: null,
      archive_reason: null,
    },
  ],
};

function source(created: boolean) {
  return {
    id: "src-procedura",
    project_id: "p-acquisti",
    process_id: "proc-p2p",
    name: "procedura.md",
    type: "Documento",
    meta: "",
    roles: ["process_evidence"],
    retention: "persistent",
    scopes: [{ type: "process", id: "proc-p2p" }],
    status: "extracted",
    byte_size: 42,
    content_hash: "abc",
    mime_type: "text/markdown",
    acquisition_status: "done",
    acquisition_error: null,
    created,
    suggested_roles: ["process_evidence", "policy"],
  };
}

/** Un file per tutto il cliente (P1.16): nessun progetto, compare nelle Fonti di ognuno. */
function clientSource() {
  return {
    ...source(false),
    id: "src-policy",
    project_id: null,
    client_id: "c-esaote",
    process_id: null,
    name: "policy-acquisti.pdf",
    mime_type: "application/pdf",
    roles: ["context"],
    scopes: [{ type: "client", id: "c-esaote" }],
  };
}

async function fixture(
  page: Page,
  uploads: { path: string; body: string }[],
  patches: unknown[] = [],
) {
  await page.addInitScript(() => Object.assign(window, { DELIR_API_BASE: "http://127.0.0.1:8000" }));
  await page.route(`${API}/**`, async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/v1/consultant-chat/sessions" && request.method() === "GET") {
      return route.fulfill({ json: [] });
    }
    if (path === "/v1/workspace/projects" && request.method() === "GET") {
      return route.fulfill({ json: [PROJECT], headers: { "X-DeliR-Total": "1" } });
    }
    if (path === "/v1/workspace/projects/p-acquisti/sources/upload") {
      uploads.push({ path, body: request.postData() ?? "" });
      return route.fulfill({ status: 201, json: source(true) });
    }
    if (path === "/v1/workspace/sources/src-procedura" && request.method() === "PATCH") {
      const body = request.postDataJSON() as { roles: string[] };
      patches.push(body);
      return route.fulfill({ json: { ...source(false), roles: body.roles } });
    }
    if (path === "/v1/workspace/clients/c-esaote/sources/upload") {
      uploads.push({ path, body: request.postData() ?? "" });
      return route.fulfill({ status: 201, json: { ...clientSource(), created: true, suggested_roles: ["policy"] } });
    }
    if (path === "/v1/workspace/projects/p-acquisti/sources") {
      return route.fulfill({ json: [source(false), clientSource()] });
    }
    return route.fulfill({ status: 200, json: null });
  });
}

test("dalla chat del consulente un file va dove il consulente sceglie", async ({ page }) => {
  const uploads: { path: string; body: string }[] = [];
  const patches: unknown[] = [];
  await fixture(page, uploads, patches);
  await page.goto("/consultant");

  await page.getByRole("button", { name: /aggiungi/i }).first().click();
  await page.getByRole("menuitem", { name: "Carica un file" }).click();

  const dialog = page.getByRole("dialog", { name: "Dove va questo file?" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Progetto").selectOption("p-acquisti");
  await dialog.getByLabel("Ambito").selectOption("proc-p2p");

  const chooser = page.waitForEvent("filechooser");
  await dialog.getByRole("button", { name: "Scegli il file" }).click();
  await (await chooser).setFiles({
    name: "procedura.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# Procedura\nIl CFO approva sopra i 30.000 EUR."),
  });

  const chips = page.getByRole("list", { name: /allegati/i });
  await expect(chips.getByText("procedura.md")).toBeVisible();
  await expect(chips.getByText("Pronta")).toBeVisible();
  expect(uploads).toHaveLength(1);
  // Messo nel processo: evidenza di quel processo.
  expect(uploads[0].body).toContain("process_evidence");
  expect(uploads[0].body).toContain("proc-p2p");

  // DeliR propone a cosa serve il file; il consulente accetta con un clic.
  const role = chips.getByRole("button", { name: /procedura\.md, a cosa serve/ });
  await expect(role).toHaveText(/Sembra: Come si lavora, Regole da rispettare/);
  await role.click();
  await page.getByRole("menuitem", { name: /Usa la proposta/ }).click();
  await expect(role).toHaveText(/^Come si lavora, Regole da rispettare/);
  expect(patches).toEqual([{ roles: ["process_evidence", "policy"] }]);

  // La destinazione resta, e si legge nel menu.
  await page.getByRole("button", { name: /aggiungi/i }).first().click();
  await expect(
    page.getByRole("menuitem", { name: /Carica un file · In: Riorganizzazione acquisti · Procure to pay/ }),
  ).toBeVisible();
  // Con un file gia' allegato la destinazione non cambia.
  await expect(page.getByRole("menuitem", { name: "Cambia destinazione" })).toBeDisabled();
});

for (const mobile of [false, true]) {
  test(`dalla chat del consulente un file va a tutto il cliente (${mobile ? "mobile" : "desktop"})`, async ({ page }, testInfo) => {
    const uploads: { path: string; body: string }[] = [];
    await fixture(page, uploads);
    await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 });
    await page.goto("/consultant");

    await page.getByRole("button", { name: /aggiungi/i }).first().click();
    await page.getByRole("menuitem", { name: "Carica un file" }).click();
    const dialog = page.getByRole("dialog", { name: "Dove va questo file?" });
    await dialog.getByLabel("Progetto").selectOption("p-acquisti");
    await dialog.getByLabel("Ambito").selectOption({ label: "Tutto il cliente «Esaote»" });
    await expect(dialog).toContainText("Vale per tutti i progetti del cliente");
    const box = await dialog.boundingBox();
    const select = await dialog.getByLabel("Ambito").boundingBox();
    // La voce lunga non allarga il menu oltre la finestra.
    expect(select && box && select.x + select.width <= box.x + box.width).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`destinazione-cliente-${mobile ? "mobile" : "desktop"}.png`) });

    const chooser = page.waitForEvent("filechooser");
    await dialog.getByRole("button", { name: "Scegli il file" }).click();
    await (await chooser).setFiles({
      name: "policy-acquisti.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4 policy"),
    });

    const chips = page.getByRole("list", { name: /allegati/i });
    await expect(chips.getByText("policy-acquisti.pdf")).toBeVisible();
    await expect(chips.getByText("Pronta")).toBeVisible();
    expect(uploads.map((upload) => upload.path)).toEqual(["/v1/workspace/clients/c-esaote/sources/upload"]);
    expect(uploads[0].body).toContain("context");
    await page.screenshot({ path: testInfo.outputPath(`allegato-cliente-${mobile ? "mobile" : "desktop"}.png`) });
  });
}
