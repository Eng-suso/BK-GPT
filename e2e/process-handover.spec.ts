import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// Consegna al responsabile, con dati sintetici: nessun dato di clienti reali.
const API = "http://127.0.0.1:8000";
const BASE = "b".repeat(64);
const trace = (id: string) => `<b:documentation>DeliR traceability: {"source_refs":["steps:${id}"]}</b:documentation>`;
const flow = (id: string, source: string, target: string, name = "") => `<b:sequenceFlow id="${id}" sourceRef="${source}" targetRef="${target}"${name ? ` name="${name}"` : ""}/>`;
const XML = `<?xml version="1.0" encoding="UTF-8"?>
<b:definitions xmlns:b="http://www.omg.org/spec/BPMN/20100524/MODEL"><b:process id="P">
<b:laneSet id="Lanes">
<b:lane id="L1" name="Richiedente"><b:flowNodeRef>start</b:flowNodeRef><b:flowNodeRef>request</b:flowNodeRef></b:lane>
<b:lane id="L2" name="Ufficio acquisti"><b:flowNodeRef>verify</b:flowNodeRef><b:flowNodeRef>order</b:flowNodeRef><b:flowNodeRef>end</b:flowNodeRef></b:lane>
<b:lane id="L3" name="Amministrazione"><b:flowNodeRef>amount</b:flowNodeRef><b:flowNodeRef>approve</b:flowNodeRef><b:flowNodeRef>join</b:flowNodeRef></b:lane>
</b:laneSet>
<b:startEvent id="start" name="Serve un acquisto"/>
<b:userTask id="request" name="Compilare la richiesta"/>
<b:userTask id="verify" name="Verificare dati">${trace("verify")}</b:userTask>
<b:exclusiveGateway id="amount" name="Importo sopra 5.000 €?"/>
<b:userTask id="approve" name="Approvare richiesta">${trace("approve")}</b:userTask>
<b:exclusiveGateway id="join"/>
<b:userTask id="order" name="Emettere l'ordine"/>
<b:endEvent id="end" name="Ordine inviato al fornitore"/>
${flow("f1", "start", "request")}${flow("f2", "request", "verify")}${flow("f3", "verify", "amount")}
${flow("f4", "amount", "approve", "Sì")}${flow("f5", "amount", "join", "No")}${flow("f6", "approve", "join")}
${flow("f7", "join", "order")}${flow("f8", "order", "end")}
</b:process></b:definitions>`;

type Options = { owner?: string; status?: string; blocking?: boolean; simulated?: boolean };

const RUN = {
  id: 42, bpmn_model_id: "handover-model", process_id: "handover-process", scenario_name: "To-Be · Una sola firma sotto 5.000 €", engine: "prosimos", status: "completed",
  request: {}, scenario: {}, result: {}, outputs: [], error: null, created_at: "2026-10-06T10:00:00Z", completed_at: "2026-10-06T10:05:00Z",
  summary: { casesCompleted: 480, cycle: { avg: 2.5 * 86400, p50: 2 * 86400, p90: 4 * 86400, p95: 5 * 86400 }, waiting: { avg: 1.5 * 86400, p95: 3 * 86400, share: 0.6 },
    processing: { avg: 3600 }, cost: { total: 21600, perCase: 45 }, throughputPerHour: 2, byActivity: [], byResource: [], bottleneck: null },
};

async function fixture(page: Page, options: Options = {}) {
  let status = options.status ?? "In corso";
  const patches: Array<Record<string, unknown>> = [];
  const actions: Array<Record<string, unknown>> = [
    { id: "change-1", node_id: "approve", node_name: "Approvare richiesta", base_revision: BASE, kind: "candidate", title: "Togliere la seconda firma sotto 5.000 €", detail: "L'approvazione richiede troppo tempo: due firme anche per importi bassi.", created_at: "2026-10-05T10:00:00Z", created_by: "consulente" },
  ];
  const processItem = () => ({ id: "handover-process", project_id: "handover-project", bpmn_model_id: "handover-model", name: "Acquisti indiretti", stage: "TO-BE", status, owner: options.owner ?? "Amministrazione", readiness: 80, archived_at: null, archive_reason: null });
  // La chiave dello studio e' configurata: la pagina del cliente non deve mai usarla.
  await page.context().addInitScript(() => Object.assign(window, { DELIR_API_BASE: "http://127.0.0.1:8000", DELIR_API_TOKEN: "studio-secret" }));
  // Gli appunti si intercettano: Safari non ha un permesso da concedere ai test.
  await page.context().addInitScript(() => {
    const copied: string[] = [];
    Object.defineProperty(window, "__copied", { value: copied });
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: async (text: string) => { copied.push(text); } } });
  });
  const link: { token: string | null; views: number; lastViewed: string | null } = { token: null, views: 0, lastViewed: null };
  const sharedRequests: Array<Record<string, string>> = [];
  const dashboard = () => ({
    process: { name: "Acquisti indiretti", owner: options.owner ?? "Amministrazione", status, stage: "TO-BE" },
    project_name: "Acquisti", client_name: "Azienda demo", consultant_name: "Giulia Bianchi", xml: XML,
    changes: actions.filter((item) => item.kind === "candidate").map(({ id, node_id, node_name, title, detail, created_at }) => ({ id, node_id, node_name, title, detail, created_at })),
    open_points: actions.filter((item) => item.kind === "clarification" || item.kind === "deferred").map(({ id, node_id, node_name, title, kind, created_at }) => ({ id, node_id, node_name, title, kind, created_at })),
    versions: [{ id: 7, change_summary: "Nuova approvazione degli acquisti", created_at: "2026-10-06T09:00:00Z" }],
    results: options.simulated ? { scenario_name: RUN.scenario_name, completed_at: RUN.completed_at, cycle_avg_seconds: RUN.summary.cycle.avg, waiting_avg_seconds: RUN.summary.waiting.avg, cost_per_case: RUN.summary.cost.perCase } : null,
    generated_at: "2026-10-11T08:00:00Z",
  });
  await page.context().route(`${API}/**`, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/v1/shared/process-dashboard") {
      sharedRequests.push(await request.allHeaders());
      if (!link.token || request.headers()["x-delir-share-token"] !== link.token) return route.fulfill({ status: 404, json: { ok: false, error: { message: "Link non valido o scaduto." } } });
      link.views += 1;
      link.lastViewed = "2026-10-11T09:30:00Z";
      return route.fulfill({ json: dashboard(), headers: { "cache-control": "no-store" } });
    }
    if (path.endsWith("/owner-dashboard")) return route.fulfill({ json: dashboard() });
    if (path.endsWith("/owner-link")) {
      if (request.method() === "POST") {
        link.token = `tok_${"x".repeat(40)}${Date.now()}`;
        link.views = 0;
        link.lastViewed = null;
        return route.fulfill({ status: 201, json: { token: link.token, created_at: "2026-10-11T08:00:00Z", expires_at: "2027-04-09T08:00:00Z" } });
      }
      if (request.method() === "DELETE") { link.token = null; return route.fulfill({ status: 204, body: "" }); }
      return route.fulfill({ json: link.token
        ? { active: true, created_at: "2026-10-11T08:00:00Z", expires_at: "2027-04-09T08:00:00Z", last_viewed_at: link.lastViewed, view_count: link.views }
        : { active: false, view_count: 0 } });
    }
    if (path === "/v1/workspace/projects/handover-project") return route.fulfill({ json: {
      id: "handover-project", client_id: "example", client: "Azienda demo", name: "Acquisti", objective: "Ridisegno", lead: "Consulente", start_date: null, end_date: null,
      phase: "TO-BE", status: "In corso", progress: 70, processes: 1, next_step: "Consegna", milestones: [], open_issues: [], deliverables: [], archived_at: null, archive_reason: null,
      process_items: [processItem()],
    } });
    if (path === "/v1/workspace/processes/handover-process" && request.method() === "PATCH") {
      const body = request.postDataJSON() as Record<string, unknown>;
      patches.push(body);
      status = String(body.status);
      return route.fulfill({ json: processItem() });
    }
    if (path.endsWith("/impact-review/actions") && request.method() === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      const action = { ...body, node_name: "Verificare dati", created_at: "2026-10-07T10:00:00Z", created_by: "consulente" };
      actions.push(action);
      return route.fulfill({ status: 201, json: action });
    }
    if (path.endsWith("/impact-review")) return route.fulfill({ json: {
      process_id: "handover-process", base_revision: BASE, xml: XML, actions,
      plan: { title: "Acquisti", actors: [], steps: [], data_objects: [], controls: [], structured_business_rules: [],
        consultant_findings: [{ id: "f1", finding: "L'approvazione richiede troppo tempo.", severity: "warning", recommendation: null }] },
    } });
    if (path.endsWith("/provenance")) return route.fulfill({ json: {
      process_id: "handover-process", snapshot_id: "s", snapshot_label: "V2", has_plan: true, total: 2, verified: 2, paraphrased: 0, label_grounded: 0, unverified: 0, awaiting_confirmation: 0, grounded_ratio: 0.94, sources_checked: 1, unused_sources: [],
      elements: [{ kind: "step", element_id: "approve", label: "Approvare richiesta", source_ref: "steps:approve", status: "verified", mark_status: "verified", source_id: "proc", source_name: "Procedura PROC-14 · esempio", quote: "Ogni richiesta è firmata dal responsabile e dall'Amministrazione.", consultant_decision: null, removable: false }],
    } });
    if (path.endsWith("/conformance")) return route.fulfill({ json: {
      process_id: "handover-process", running: false, is_current: true,
      report: { verdict: options.blocking ? "not_conformant" : "conformant", findings: options.blocking ? [{ layer: "source_contradiction", severity: "blocking", message: "Contrasto", source_name: "PROC-14" }] : [], sources_audited: 1, sources_with_text: 1, llm_audit_note: "", audited_at: "2026-10-06T10:00:00Z" },
    } });
    if (path.endsWith("/simulation-runs")) return route.fulfill({ json: options.simulated ? [RUN] : [] });
    if (path.endsWith("/versions")) return route.fulfill({ json: [{ id: 7, bpmn_model_id: "handover-model", process_id: "handover-process", change_summary: "To-Be", source: "canvas", created_at: "2026-10-06T09:00:00Z" }] });
    return route.fulfill({ json: [] });
  });
  return { patches, actions, link, sharedRequests };
}

/** Quanto il contenuto supera la larghezza visibile, nel documento o in un contenitore che scorre. */
async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(() => {
    const scrollers = [document.documentElement, ...document.querySelectorAll<HTMLElement>(".handover, .owner-dashboard")];
    const contentEdge = Math.max(...[...document.querySelectorAll<HTMLElement>(".handover-body *, .owner-dashboard-page *")]
      .filter((element) => !element.parentElement?.closest("[data-slot='table-container']"))
      .map((element) => element.getBoundingClientRect().right));
    return Math.max(...scrollers.map((element) => element.scrollWidth - element.clientWidth), contentEdge - window.innerWidth);
  });
}

const URL_HANDOVER = "/projects/handover-project/processes/handover-process/handover";

test("the consultant sends the process to the client in one step and records the client approval", async ({ page }) => {
  const api = await fixture(page);
  await page.goto(URL_HANDOVER);
  await expect(page.getByRole("heading", { name: "Disegno completato · Pronto per la consegna" })).toBeVisible();
  await expect(page.getByText("Togliere la seconda firma sotto 5.000 €")).toBeVisible();
  await expect(page.getByText("Procedura PROC-14 · esempio")).toBeVisible();

  const stepper = page.getByRole("list", { name: "Fase del processo" });
  await expect(stepper.locator('[aria-current="step"]')).toContainText("Preparazione");
  // I problemi in cima, poi il resto: qui manca solo la simulazione.
  await expect(page.getByText("5 di 6 controlli superati")).toBeVisible();
  await expect(page.locator(".handover-check").first()).toContainText("Simulazione eseguita");

  // Inviare e' un gesto solo: il link si prepara, si copia, si conferma l'invio.
  await page.getByRole("button", { name: "Invia al cliente" }).click();
  const dialog = page.getByRole("dialog", { name: "Invia il processo al cliente" });
  const confirm = dialog.getByRole("button", { name: "Ho inviato il link" });
  await expect(dialog.getByLabel("Link del cruscotto")).toHaveValue(/\/share\.html#tok_/);
  expect(api.patches).toHaveLength(0);
  await dialog.getByRole("button", { name: "Copia il link" }).click();
  expect(await page.evaluate(() => (window as unknown as { __copied: string[] }).__copied.at(-1))).toMatch(/\/share\.html#tok_/);
  await confirm.click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("heading", { name: "Inviato a Amministrazione · In attesa della risposta del cliente" })).toBeVisible();
  expect(api.patches.at(-1)).toMatchObject({ status: "Da validare", owner: "Amministrazione" });
  await expect(stepper.locator('[aria-current="step"]')).toContainText("Con il cliente");
  await expect(page.getByText("Amministrazione non ha ancora aperto il cruscotto")).toBeVisible();

  await page.getByRole("button", { name: "Il cliente ha approvato" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Il cliente ha approvato" }).click();
  await expect(page.getByRole("heading", { name: "Approvato dal cliente · Da ora si misurano i risultati" })).toBeVisible();
  expect(api.patches.at(-1)).toMatchObject({ status: "Validato" });
});

test("the consultant records a client change request without editing the diagram", async ({ page }) => {
  const api = await fixture(page, { status: "Da validare" });
  await page.goto(URL_HANDOVER);
  await page.getByRole("button", { name: "Il cliente chiede modifiche" }).click();
  const dialog = page.getByRole("dialog", { name: "Il cliente chiede modifiche" });
  await dialog.getByRole("combobox").click();
  await page.getByRole("option", { name: "Verificare dati" }).click();
  await dialog.getByLabel("In breve").fill("La responsabilità deve restare all'Amministrazione");
  await dialog.getByLabel("Cosa ha chiesto il cliente e perché").fill("Il controllo dei dati è oggi in carico all'Amministrazione.");
  await dialog.getByRole("button", { name: "Registra la richiesta" }).click();
  await expect(dialog).toBeHidden();
  expect(api.actions.at(-1)).toMatchObject({ kind: "clarification", node_id: "verify", base_revision: BASE });
  expect(api.patches.at(-1)).toMatchObject({ status: "In corso" });
  await expect(page.getByText("La responsabilità deve restare all'Amministrazione")).toBeVisible();
});

test("a process without owner or with conflicting documents cannot be sent", async ({ page }) => {
  await fixture(page, { owner: "", blocking: true });
  await page.goto(URL_HANDOVER);
  await expect(page.getByRole("heading", { name: "Non ancora pronto per la consegna" })).toBeVisible();
  await expect(page.getByText("2 controlli importanti non sono superati.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Invia al cliente" })).toBeDisabled();
});

for (const viewport of [{ name: "desktop", width: 1440, height: 1000 }, { name: "mobile", width: 390, height: 844 }]) {
  test(`hand over page is accessible and does not overflow on ${viewport.name}`, async ({ page }, info) => {
    await page.setViewportSize(viewport);
    await fixture(page);
    await page.goto(URL_HANDOVER);
    await expect(page.getByRole("heading", { name: "Pronto per la consegna?" })).toBeVisible();
    // Le pagine scorrono in un contenitore loro: e' li' che il contenuto non deve uscire.
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
    const results = await new AxeBuilder({ page }).include(".handover").analyze();
    expect(results.violations.map((violation) => violation.id)).toEqual([]);
    await page.screenshot({ path: info.outputPath(`handover-${viewport.name}.png`), fullPage: true });
  });
}

const URL_DASHBOARD = "/projects/handover-project/processes/handover-process/handover/dashboard";

test("the owner dashboard opens from the hand over, without DeliR navigation, and prints to PDF", async ({ page, browserName }, info) => {
  await fixture(page, { status: "Validato", simulated: true });
  await page.goto(URL_HANDOVER);
  await page.getByRole("button", { name: "Anteprima per il cliente" }).click();
  await expect(page).toHaveURL(new RegExp(`${URL_DASHBOARD}$`));
  await expect(page.getByRole("heading", { level: 1, name: "Acquisti indiretti" })).toBeVisible();
  await expect(page.getByText("Approvato · In uso")).toBeVisible();
  await expect(page.getByRole("navigation", { name: /principale|main/i })).toHaveCount(0);
  await expect(page.getByText("Il tuo consulente: Giulia Bianchi")).toBeVisible();
  await expect(page.getByText("Per rispondere o fare domande scrivi a Giulia Bianchi.")).toBeVisible();
  await expect(page.locator(".owner-dashboard-glance")).toContainText("Passi del processo4");
  await expect(page.locator(".owner-dashboard-glance")).toContainText("Persone coinvolte3");
  await expect(page.locator(".owner-dashboard-results")).toContainText("Costo per ogni pratica45,00 €");
  await expect(page.getByRole("heading", { level: 3, name: "Togliere la seconda firma sotto 5.000 €" })).toBeVisible();
  // Il processo raccontato a chi non conosce il BPMN: passi in ordine, chi li fa, decisioni come domande.
  const steps = page.getByRole("region", { name: "Come funziona il processo" }).getByRole("listitem");
  await expect(page.getByText("Serve un acquisto")).toBeVisible();
  await expect(steps.filter({ hasText: "Passo 3" }).filter({ hasText: "Importo sopra 5.000 €?" })).toContainText("Se «Sì» → passo 4");
  await expect(steps.filter({ hasText: "Passo 3" }).filter({ hasText: "Importo sopra 5.000 €?" })).toContainText("Se «No» → passo 5");
  await expect(steps.filter({ hasText: "Passo 4" }).filter({ hasText: "Approvare richiesta" }).first()).toContainText("Cambia");
  await expect(steps.filter({ hasText: "Passo 4" }).filter({ hasText: "Approvare richiesta" }).first()).toContainText("Amministrazione");
  await expect(page.getByText("Ordine inviato al fornitore")).toBeVisible();
  await expect(page.getByText(/gateway|BPMN|lane|corsia/i)).toHaveCount(0);
  await expect(page.getByText("Nuova versione del processo")).toBeVisible();
  // "Passo 4" nelle modifiche porta al passo.
  await page.getByRole("link", { name: "Vai al passo 4" }).click();
  await expect(page).toHaveURL(/#plain-step-4$/);
  await expect(page.locator("#plain-step-4")).toBeInViewport();

  await page.emulateMedia({ media: "print" });
  await expect(page.getByRole("button", { name: "Scarica PDF" })).toBeHidden();
  if (browserName === "chromium") await page.pdf({ path: info.outputPath("cruscotto.pdf"), format: "A4", printBackground: true });
  await page.emulateMedia({ media: "screen" });
  await page.getByRole("button", { name: "Torna alla consegna" }).click();
  await expect(page).toHaveURL(new RegExp(`${URL_HANDOVER}$`));
});

for (const viewport of [{ name: "desktop", width: 1440, height: 1000 }, { name: "mobile", width: 390, height: 844 }]) {
  test(`owner dashboard is accessible and does not overflow on ${viewport.name}`, async ({ page }, info) => {
    await page.setViewportSize(viewport);
    await fixture(page, { status: "Da validare", simulated: true });
    await page.goto(URL_DASHBOARD);
    await expect(page.getByText("In attesa della tua approvazione")).toBeVisible();
    // Le pagine scorrono in un contenitore loro: e' li' che il contenuto non deve uscire.
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
    const results = await new AxeBuilder({ page }).include(".owner-dashboard").analyze();
    expect(results.violations.map((violation) => violation.id)).toEqual([]);
    await page.screenshot({ path: info.outputPath(`owner-dashboard-${viewport.name}.png`), fullPage: true });
  });
}

test("the consultant creates the client link, the client opens it without studio credentials, the consultant sees the visit", async ({ page, context }, info) => {
  const api = await fixture(page, { status: "Da validare", simulated: true });
  await page.goto(URL_HANDOVER);
  const panel = page.getByRole("region", { name: "Link per il cliente" });
  await expect(panel.getByText("Il link si crea quando invii il processo al cliente.")).toBeVisible();
  await panel.getByRole("button", { name: "Crea solo il link" }).click();
  const url = await panel.getByLabel("Link del cruscotto").inputValue();
  expect(url).toMatch(/\/share\.html#tok_/);
  expect(url.split("#")[1]).toBe(api.link.token);
  await panel.getByRole("button", { name: "Copia il link" }).click();
  expect(await page.evaluate(() => (window as unknown as { __copied: string[] }).__copied.at(-1))).toBe(url);
  await expect(page.getByText("Link copiato")).toBeVisible();
  await expect(panel.getByText("Il cliente non l'ha ancora aperto.")).toBeVisible();

  // Il cliente apre il link in una pagina nuova.
  const client = await context.newPage();
  await client.goto(url.replace(/^https?:\/\/[^/]+/, ""));
  await expect(client.getByRole("heading", { level: 1, name: "Acquisti indiretti" })).toBeVisible();
  await expect(client.getByText("In attesa della tua approvazione")).toBeVisible();
  await expect(client.getByRole("region", { name: "Come funziona il processo" })).toContainText("Importo sopra 5.000 €?");
  await expect(client.getByText("Link personale: non inoltrarlo ad altre persone.")).toBeVisible();
  await expect(client.getByRole("button", { name: "Torna alla consegna" })).toHaveCount(0);
  const shared = api.sharedRequests.at(-1)!;
  expect(shared["x-delir-share-token"]).toBe(api.link.token);
  expect(shared.authorization).toBeUndefined();
  expect(shared["x-delir-tenant-id"]).toBeUndefined();
  const results = await new AxeBuilder({ page: client }).include(".owner-dashboard").analyze();
  expect(results.violations.map((violation) => violation.id)).toEqual([]);
  await client.screenshot({ path: info.outputPath("share-page.png"), fullPage: true });

  // Il consulente vede la visita, poi disattiva il link.
  await page.reload();
  await expect(panel.getByText("Aperto dal cliente 1 volta, il 11 ott 2026")).toBeVisible();
  // L'informazione piu' utile dopo l'invio sta anche in cima, nello stato.
  await expect(page.getByText("Amministrazione ha aperto il cruscotto 1 volta, il 11 ott 2026")).toBeVisible();
  await panel.getByRole("button", { name: "Disattiva il link" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Disattiva il link" }).click();
  await expect(panel.getByText("Il link si crea quando invii il processo al cliente.")).toBeVisible();
  await client.reload();
  await expect(client.getByRole("heading", { name: "Questo link non funziona" })).toBeVisible();
});

test("a share page without a code or with a wrong code says the link does not work", async ({ page }) => {
  await fixture(page);
  await page.goto("/share.html");
  await expect(page.getByRole("heading", { name: "Questo link non funziona" })).toBeVisible();
  await page.goto("/share.html#codice-sbagliato-0123456789012345678901234567890");
  await page.reload();
  await expect(page.getByRole("heading", { name: "Questo link non funziona" })).toBeVisible();
});
