import { expect, test, type Page } from "@playwright/test";
import { join } from "node:path";
import { readFileSync } from "node:fs";
import AxeBuilder from "@axe-core/playwright";

const studio = "/projects/layout-project/processes/layout-process";
const tasks = Array.from({ length: 18 }, (_, index) => ({
  element_id: `Task_${index + 1}`,
  name: `Attività ${index + 1}: verifica della documentazione e approvazione della richiesta`,
  type: "userTask",
}));
const xml = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_layout" targetNamespace="https://example.test/layout">
<bpmn:process id="Process_layout" isExecutable="false">${tasks.map((task) => `<bpmn:userTask id="${task.element_id}" name="${task.name}" />`).join("")}${tasks.slice(1).map((task, i) => `<bpmn:sequenceFlow id="Flow_${i}" sourceRef="${tasks[i].element_id}" targetRef="${task.element_id}" />`).join("")}</bpmn:process>
<bpmndi:BPMNDiagram id="Diagram_layout"><bpmndi:BPMNPlane id="Plane_layout" bpmnElement="Process_layout">${tasks.map((task, i) => `<bpmndi:BPMNShape id="${task.element_id}_di" bpmnElement="${task.element_id}"><dc:Bounds x="${80 + (i % 6) * 210}" y="${80 + Math.floor(i / 6) * 180}" width="160" height="90" /></bpmndi:BPMNShape>`).join("")}${tasks.slice(1).map((task, i) => `<bpmndi:BPMNEdge id="Flow_${i}_di" bpmnElement="Flow_${i}"><di:waypoint x="${240 + (i % 6) * 210}" y="${125 + Math.floor(i / 6) * 180}" /><di:waypoint x="${80 + ((i + 1) % 6) * 210}" y="${125 + Math.floor((i + 1) / 6) * 180}" /></bpmndi:BPMNEdge>`).join("")}</bpmndi:BPMNPlane></bpmndi:BPMNDiagram></bpmn:definitions>`;

async function fixture(page: Page) {
  await page.addInitScript(() => Object.assign(window, { DELIR_API_BASE: "http://127.0.0.1:8000" }));
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let data: unknown = null;
    if (path === "/v1/workspace/projects/layout-project") data = {
      id: "layout-project", client_id: "demo", client: "Azienda Demo", name: "Progetto dimostrativo", phase: "AS-IS", status: "In corso", progress: 50, processes: 1,
      next_step: "Validare il modello", milestones: [], open_issues: [], deliverables: [],
      process_items: [{ id: "layout-process", project_id: "layout-project", bpmn_model_id: "layout-model", name: "Gestione richieste e approvazioni", stage: "AS-IS", status: "Da validare", owner: "Team Operations", readiness: 65 }],
    };
    else if (path.endsWith("/simulation-template")) data = { tasks, gateways: [] };
    else if (path.endsWith("/simulation-provenance")) data = { has_discovery: false, elements: [] };
    else if (path.endsWith("/simulation-runs") && request.method() === "POST") data = {
      id: 1, bpmn_model_id: "layout-model", process_id: "layout-process", scenario_name: "Scenario demo", engine: "prosimos", status: "completed", request: request.postDataJSON(), scenario: {}, result: {}, outputs: [], error: null, created_at: "2026-09-06T10:00:00Z", completed_at: "2026-09-06T10:00:01Z",
    };
    else if (path.endsWith("/versions") || path.endsWith("/sessions") || path.endsWith("/simulation-runs")) data = [];
    else if (path.endsWith("/layout-model")) data = { id: "layout-model", process_id: "layout-process", name: "Modello demo", xml };
    else if (!path.endsWith("/review")) return route.fulfill({ status: 503, json: { detail: "Synthetic fixture: endpoint unavailable" } });
    await route.fulfill({ json: data });
  });
}

test.beforeEach(async ({ page }) => { await fixture(page); });

// Aprire un processo porta alla discussione: il canvas si chiede, con `?view=canvas`.
const canvasView = `${studio}?view=canvas`;

for (const mobile of [false, true]) test(`enterprise library and properties round-trip on ${mobile ? "mobile" : "desktop"}`, async ({ page }, info) => {
  test.setTimeout(90_000);
  await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1600, height: 1000 });
  const errors: string[] = []; page.on("pageerror", error => errors.push(error.message));
  let savedXml = xml;
  const cors = { "access-control-allow-origin": "*", "access-control-allow-methods": "GET, PUT, OPTIONS", "access-control-allow-headers": "Content-Type" };
  await page.route("**/v1/workspace/bpmn-models/layout-model/versions", route => route.fulfill({ headers: cors, json: [] }));
  await page.route("**/v1/workspace/bpmn-models/layout-model", async route => {
    if (route.request().method() === "PUT") savedXml = route.request().postDataJSON().xml;
    await route.fulfill({ headers: cors, json: { id: "layout-model", process_id: "layout-process", name: "Model", xml: savedXml, version_id: 1 } });
  });
  await page.goto(canvasView);
  const canvas = page.locator(".process-bpmn-canvas");
  await expect(canvas.locator('[data-element-id="Task_1"]').first()).toBeVisible();
  await page.getByRole("button", { name: "Apri libreria BPMN", exact: true }).click();
  const library = page.getByRole("navigation", { name: "Strumenti BPMN" });
  await library.getByRole("textbox", { name: "Cerca elementi BPMN" }).fill("servizio");
  await expect(library.getByRole("button", { name: "Attività di servizio", exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath(`enterprise-library-${mobile}.png`) });
  await library.getByRole("textbox", { name: "Cerca elementi BPMN" }).fill("no-matching-element");
  await expect(library).toContainText("Nessun elemento trovato");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Apri libreria BPMN", exact: true })).toBeFocused();
  await canvas.locator('[data-element-id="Task_1"]').first().click();
  const inspector = page.locator(".process-enterprise-properties");
  if (mobile) { await page.getByRole("button", { name: "Proprietà", exact: true }).click(); await expect(canvas).toBeHidden(); }
  await inspector.getByRole("textbox", { name: "Responsabile attività", exact: true }).fill("Operations");
  await inspector.getByRole("textbox", { name: "Ufficio competente", exact: true }).fill("Acquisti");
  await inspector.getByRole("checkbox").check();
  await inspector.getByRole("combobox", { name: "Sezione proprietà" }).click();
  await page.keyboard.press("Escape");
  await expect(inspector.getByRole("combobox", { name: "Sezione proprietà" })).toBeFocused();
  if (mobile) await expect(canvas).toBeHidden();
  await inspector.getByRole("combobox", { name: "Sezione proprietà" }).click();
  await page.getByRole("option", { name: "Regole", exact: true }).click();
  await inspector.getByRole("textbox", { name: "Note sulle regole", exact: true }).fill("Approvazione sopra soglia");
  await inspector.getByRole("textbox", { name: "Rischi e mitigazioni", exact: true }).fill("Dati incompleti: controllo preventivo");
  await inspector.getByRole("textbox", { name: "Riferimenti SOP", exact: true }).fill("SOP-ACQ-01");
  await inspector.getByRole("combobox", { name: "Sezione proprietà" }).click();
  await page.getByRole("option", { name: "Dati", exact: true }).click();
  await inspector.getByRole("textbox", { name: "Input", exact: true }).fill("Richiesta");
  await inspector.getByRole("combobox", { name: "Sezione proprietà" }).click();
  await page.getByRole("option", { name: "File", exact: true }).click();
  await inspector.getByRole("textbox", { name: "Riferimenti documentali", exact: true }).fill("Procedura acquisti");
  await inspector.getByRole("combobox", { name: "Sezione proprietà" }).click();
  await page.getByRole("option", { name: "Cronologia", exact: true }).click();
  await expect(inspector).toContainText("Nessuna versione salvata disponibile");
  await inspector.getByRole("combobox", { name: "Sezione proprietà" }).click();
  await page.getByRole("option", { name: "AI", exact: true }).click();
  await expect(inspector.getByRole("button", { name: "Chiedi a DeliR" })).toBeVisible();
  await inspector.getByRole("combobox", { name: "Sezione proprietà" }).click();
  await page.getByRole("option", { name: "Dettagli", exact: true }).click();
  await page.screenshot({ path: info.outputPath(`enterprise-properties-${mobile}.png`) });
  expect((await new AxeBuilder({ page }).include(".process-workspace").analyze()).violations).toEqual([]);
  if (mobile) await page.getByRole("button", { name: "Chiudi i pannelli", exact: true }).click();
  await expect(page.getByRole("button", { name: "Salva", exact: true })).toBeEnabled();
  const historyReload = page.waitForResponse(response => response.url().endsWith("/layout-model/versions"));
  await page.getByRole("button", { name: "Salva", exact: true }).click();
  await (await historyReload).finished();
  await expect.poll(() => savedXml).toContain('delir:owner="Operations"');
  expect(savedXml).toContain('xmlns:delir="https://delir.app/schema/bpmn/1.0"');
  expect(savedXml).toContain('delir:rules="Approvazione sopra soglia"');
  expect(savedXml).toContain('delir:required="true"');
  await page.reload();
  await canvas.locator('[data-element-id="Task_1"]').first().click();
  if (mobile) { await page.getByRole("button", { name: "Proprietà", exact: true }).click(); await expect(canvas).toBeHidden(); }
  await expect(inspector.getByRole("textbox", { name: "Responsabile attività", exact: true })).toHaveValue("Operations");
  await expect(inspector.getByRole("checkbox")).toBeChecked();
  await inspector.getByRole("button", { name: "Elimina elemento", exact: true }).click();
  await expect(canvas.locator('[data-element-id="Task_1"]')).toHaveCount(0);
  if (mobile) await page.getByRole("button", { name: "Chiudi i pannelli", exact: true }).click();
  await page.getByRole("button", { name: "Annulla modifica", exact: true }).click();
  await expect(canvas.locator('[data-element-id="Task_1"]').first()).toBeVisible();
  expect(errors).toEqual([]);
});

test("enterprise library places service tasks and timer event definitions", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto(canvasView);
  const canvas = page.locator(".process-bpmn-canvas");
  await expect(canvas.locator('[data-element-id="Task_1"]').first()).toBeVisible();
  await page.getByRole("button", { name: "Apri libreria BPMN", exact: true }).click();
  const search = page.getByRole("textbox", { name: "Cerca elementi BPMN" });
  await search.fill("servizio");
  await page.getByRole("button", { name: "Attività di servizio", exact: true }).click();
  await canvas.click({ position: { x: 180, y: 30 } });
  await expect(canvas.locator(".delir-type-automation")).toHaveCount(1);
  await search.fill("iniziale · timer");
  await page.getByRole("button", { name: "Evento iniziale · timer", exact: true }).click();
  await canvas.click({ position: { x: 400, y: 30 } });
  await expect(canvas.locator(".delir-type-start")).toHaveCount(1);
  const saveRequest = page.waitForRequest(request => request.method() === "PUT" && request.url().endsWith("/layout-model"));
  await expect(page.getByRole("button", { name: "Salva", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Salva", exact: true }).click();
  const saved = (await saveRequest).postDataJSON().xml;
  expect(saved).toContain("bpmn:serviceTask"); expect(saved).toContain("bpmn:timerEventDefinition");
});

test("product-generated diagram keeps the DeliR identity in the editable canvas", async ({ page }, info) => {
  if (!info.project.name.startsWith("mobile-")) await page.setViewportSize({ width: 1600, height: 1000 });
  const generated = readFileSync("e2e/fixtures/canvas-layout/purchase.bpmn", "utf8");
  await page.route("http://127.0.0.1:8000/v1/workspace/bpmn-models/layout-model", route => route.fulfill({ json: { id: "layout-model", process_id: "layout-process", name: "Acquisti indiretti", xml: generated } }));
  await page.goto(canvasView);
  const canvas = page.locator(".process-bpmn-canvas");
  await expect(canvas.locator('[data-element-id="Verify"]')).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Strumenti BPMN" })).toBeVisible();
  await expect(canvas.locator(".bjs-powered-by")).toHaveCount(0);
  await expect(canvas.locator(".delir-role-band")).toHaveCount(5);
  await expect(canvas.locator(".djs-connection")).toHaveCount(11);
  await expect(canvas.locator('[data-element-id="Request_Document"]')).toBeVisible();
  const scan = await new AxeBuilder({ page }).include(".process-bpmn-shell").withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
  expect(scan.violations).toEqual([]);
  await page.screenshot({ path: info.outputPath("delir-generated-editor.png") });
});

test("laptop tools preserve canvas space and unsaved model edits", async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto(canvasView);
  const canvas = page.locator(".process-bpmn-canvas");
  await page.locator('[data-element-id="Task_1"]').first().click();
  await page.getByRole("textbox", { name: "Nome" }).fill("Modifica da conservare");
  await page.getByRole("button", { name: "Chat canvas", exact: true }).focus();
  await page.getByRole("button", { name: "Chat canvas", exact: true }).click();
  await expect(page.locator(".process-studio-chat")).toBeVisible();
  await expect.poll(async () => (await canvas.boundingBox())?.width ?? 0).toBeGreaterThan(720);
  await page.getByRole("button", { name: "Proprietà", exact: true }).click();
  await expect(page.locator(".process-studio-chat")).toBeHidden();
  await expect(page.locator(".process-studio-properties")).toBeVisible();
  await expect.poll(async () => (await canvas.boundingBox())?.width ?? 0).toBeGreaterThan(720);
  const before = (await canvas.boundingBox())!.width;
  await page.getByRole("button", { name: "Importa, esporta, cronologia" }).click();
  await page.getByRole("menuitem", { name: "Cronologia versioni" }).click();
  await expect(page.getByRole("dialog", { name: "Cronologia versioni" })).toBeVisible();
  expect((await canvas.boundingBox())!.width).toBeCloseTo(before, 0);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Importa, esporta, cronologia" })).toBeFocused();
  await page.getByRole("button", { name: "Chiudi i pannelli", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Nome" })).toHaveValue("Modifica da conservare");
  const saved = page.waitForRequest((req) => req.method() === "PUT" && req.url().endsWith("/layout-model"));
  await page.getByRole("button", { name: "Salva", exact: true }).click();
  expect((await saved).postDataJSON().xml).toContain("Modifica da conservare");
});

test("scenario supports long activity lists, model reference and execution", async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto(`${studio}/simulation/scenario`);
  const row = page.locator('[data-sim-el="Task_18"]');
  await row.scrollIntoViewIfNeeded();
  await expect(row).toBeVisible();
  const run = page.getByRole("button", { name: "Avvia simulazione", exact: true });
  await expect(run).toBeInViewport();
  await row.getByRole("spinbutton", { name: /^Durata, min/ }).fill("37");
  expect((await row.getByRole("spinbutton", { name: /^Durata, min/ }).boundingBox())!.width).toBeGreaterThanOrEqual(100);
  await expect(page.locator(".sim-studio-empty-process .djs-container")).toBeVisible();
  await page.locator('.sim-studio-empty-process [data-element-id="Task_18"]').first().click();
  await expect(row.getByRole("spinbutton", { name: /^Durata, min/ })).toHaveValue("37");
  await expect(run).toBeDisabled();
  await page.getByRole("button", { name: "Aggiungi ruolo", exact: true }).click();
  const resource = page.locator("[data-resource-id]");
  await resource.getByRole("textbox", { name: "Ruolo", exact: true }).fill("Team Operations");
  await resource.getByRole("spinbutton", { name: "Costo ora (€/h)", exact: true }).fill("40");
  await resource.getByRole("spinbutton", { name: "Unità disponibili", exact: true }).fill("2");
  await resource.getByRole("button", { name: "Conferma capacità e costo", exact: true }).click();
  await expect(run).toBeDisabled();
  await resource.getByRole("button", { name: /Assegna alle attività senza risorsa/ }).click();
  await expect(run).toBeEnabled();
  const request = page.waitForRequest((req) => req.method() === "POST" && req.url().endsWith("/simulation-runs"));
  await run.click();
  const body = (await request).postDataJSON();
  expect(body.tasks.find((task: { element_id: string }) => task.element_id === "Task_18").mean_seconds).toBe(2220);
});

test("mobile tools are reachable and scenario controls stay inside the viewport", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(canvasView);
  await page.getByRole("button", { name: "Chat canvas", exact: true }).focus();
  await page.getByRole("button", { name: "Chat canvas", exact: true }).click();
  await expect(page.locator(".process-studio-chat")).toBeVisible();
  await expect(page.getByRole("button", { name: "Chiudi i pannelli", exact: true })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Chat canvas", exact: true })).toBeFocused();
  await page.getByRole("button", { name: "Proprietà", exact: true }).click();
  await page.getByRole("button", { name: "Chiudi i pannelli", exact: true }).click();
  await page.goto(`${studio}/simulation/scenario`);
  await page.locator('[data-sim-el="Task_18"]').scrollIntoViewIfNeeded();
  await expect(page.getByRole("button", { name: "Avvia simulazione", exact: true })).toBeInViewport();
  const overflow = await page.locator("main input, main [role=combobox]").evaluateAll((elements) => elements.filter((element) => {
    const box = element.getBoundingClientRect();
    return box.width > 0 && (box.right > innerWidth + 1 || box.left < 0);
  }).length);
  expect(overflow).toBe(0);
  const scan = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
  expect(scan.violations).toEqual([]);
  expect(errors).toEqual([]);
});

for (const [surface, path] of [
  ["consultant", "/consultant"],
  ["project", "/projects/layout-project?tab=chat"],
  ["process", `${studio}?view=chat`],
  ["canvas", canvasView],
] as const) {
  test(`${surface} chat keeps long conversations and composer usable on laptop and mobile`, async ({ page }, testInfo) => {
    // La scansione axe completa della pagina, su due viewport e in WebKit,
    // sfiora i 45 secondi gia' su main (44,7 s sul canvas): stesso margine
    // dei test di questo file che fanno scansioni complete.
    test.setTimeout(Math.max(testInfo.timeout, 90_000));
    const session = {
      thread_id: "layout-chat", title: "Analisi del processo dimostrativo con un titolo esteso",
      created_at: "2026-09-06T10:00:00Z", updated_at: "2026-09-06T10:00:00Z",
      messages: Array.from({ length: 12 }, (_, i) => ({
        id: i, role: i % 2 ? "assistant" : "user",
        content: i % 2 ? "Ogni passaggio ha un responsabile e un esito esplicito. ".repeat(24) : `Analizziamo il passaggio ${i + 1}.`,
      })),
    };
    await page.route("**/v1/consultant-chat/sessions**", (route) => route.fulfill({
      json: new URL(route.request().url()).pathname.endsWith("/sessions") ? [session] : session,
    }));
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto(path);
    if (surface === "canvas") await page.getByRole("button", { name: "Chat canvas", exact: true }).click();
    const composer = page.locator(".composer-wrap");
    const input = composer.getByRole("textbox");
    await expect(input).toBeVisible();
    await expect(page.locator(".message-list")).toContainText("Analizziamo il passaggio 11.");

    for (const size of [{ width: 1366, height: 768 }, { width: 390, height: 844 }]) {
      await page.setViewportSize(size);
      await input.fill("Bozza da conservare\n".repeat(20));
      await expect(composer.getByRole("button", { name: "Invia", exact: true })).toBeInViewport();
      await expect.poll(() => composer.locator("button").evaluateAll((buttons) => buttons.filter((button) => {
        const rect = button.getBoundingClientRect();
        return rect.width > 0 && (rect.right > innerWidth + 1 || rect.left < 0 || rect.bottom > innerHeight + 1);
      }).length)).toBe(0);
      // Postura, ragionamento e autonomia stanno dietro tre menu: la barra dice
      // cosa e' scelto e le alternative stanno a un click. Tutti e tre devono
      // restare dentro il viewport anche a 390px.
      const triggers = composer.locator(".chat-mode-trigger");
      await expect(triggers).toHaveCount(3);
      for (const trigger of await triggers.all()) {
        await expect(trigger).toBeInViewport();
      }
      // Il menu si apre in un portal fuori da `.composer-wrap`, e i suoi item
      // sono `menuitemradio`. Qui conta che si apra dentro il viewport e che
      // la scelta arrivi al trigger.
      const autonomyTrigger = composer.getByRole("button", { name: /Autonomia/ });
      await autonomyTrigger.click();
      const modeMenu = page.getByRole("menu");
      await expect(modeMenu).toBeVisible();
      expect(await modeMenu.evaluate((element) => {
        const rect = element.getBoundingClientRect();
        return rect.right > innerWidth + 1 || rect.left < -1
          || rect.bottom > innerHeight + 1 || rect.top < -1;
      })).toBe(false);
      await modeMenu.getByRole("menuitemradio", { name: /Chiedi approvazione/ }).click();
      await expect(modeMenu).toBeHidden();
      await expect(autonomyTrigger).toContainText("Chiedi approvazione");
      // Riaperto, il menu ricorda la scelta invece di ripartire dal default.
      await autonomyTrigger.click();
      await expect(page.getByRole("menuitemradio", { name: /Chiedi approvazione/ })).toBeChecked();
      await page.keyboard.press("Escape");
      await expect(page.getByRole("menu")).toBeHidden();
      const messages = page.locator(".messages, .embedded-chat-body");
      expect(await messages.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true);
      await messages.evaluate((element) => element.scrollTo(0, 0));
      await expect(input).toHaveValue("Bozza da conservare\n".repeat(20));
      await expect(composer.getByRole("button", { name: "Invia", exact: true })).toBeInViewport();
    }
    if (surface === "consultant") {
      const history = page.getByRole("button", { name: "Cronologia", exact: true });
      await history.click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(history).toBeFocused();
    }
    await page.route("**/v1/audio/transcriptions", (route) => route.fulfill({ json: { text: "Trascrizione dimostrativa del processo." } }));
    await composer.locator('input[type="file"][accept^="audio"]').setInputFiles({ name: "synthetic-audio.wav", mimeType: "audio/wav", buffer: Buffer.from("synthetic fixture") });
    await expect(input).toHaveValue(/Trascrizione dimostrativa del processo\./);
    await expect(composer.getByRole("button", { name: "Invia", exact: true })).toBeInViewport();
    const transcript = page.getByRole("button", { name: "Apri trascrizione", exact: true });
    await transcript.click();
    await expect(page.getByRole("dialog", { name: "Trascrizione audio" })).toContainText("Trascrizione dimostrativa del processo.");
    await page.keyboard.press("Escape");
    await expect(transcript).toBeFocused();
    const scan = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
    expect(scan.violations).toEqual([]);
  });
}

test("mobile heatmap preserves a readable diagram above populated metrics", async ({ page }) => {
  const summary = {
    casesCompleted: 100, cycle: { avg: 7200, p50: 6600, p90: 10000, p95: 12000 },
    waiting: { avg: 4200, p95: 9000, share: 0.58 }, processing: { avg: 3000 },
    cost: { total: 3000, perCase: 30 }, throughputPerHour: 12,
    byActivity: tasks.map((task) => ({ el: task.element_id, name: task.name, count: 100, wait: { avg: 2000, p95: 4200 } })),
    byResource: [], bottleneck: { el: "Task_1", score: 0.8 },
  };
  await page.route("**/simulation-runs", (route) => route.fulfill({ json: [{
    id: 1, bpmn_model_id: "layout-model", process_id: "layout-process", scenario_name: "Scenario demo", engine: "prosimos", status: "completed", request: {}, scenario: {}, result: {}, outputs: [], summary, error: null, created_at: "2026-09-06T10:00:00Z", completed_at: "2026-09-06T10:00:01Z",
  }] }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${studio}/simulation/heatmap/1`);
  await expect(page.locator(".djs-container")).toBeVisible();
  // This legacy run has no replay artifact: keep the static process usable alongside final metrics.
  expect((await page.locator(".djs-container").boundingBox())!.height).toBeGreaterThan(240);
  await expect(page.locator(".sim-studio-board")).toBeVisible();
  await page.getByRole("button", { name: /Attività 18:/ }).scrollIntoViewIfNeeded();
  await expect(page.getByRole("button", { name: /Attività 18:/ })).toBeInViewport();
  const scan = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
  expect(scan.violations).toEqual([]);
});


test("process elements follow imports, selection and properties without rewriting BPMN colours", async ({ page }, testInfo) => {
  // This complete import/edit/export journey mounts two modelers and both docks;
  // keep its budget separate from the shorter interaction tests on mobile WebKit.
  test.setTimeout(Math.max(testInfo.timeout, 90_000));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(canvasView);
  await expect(page.locator('[data-element-id="Task_1"]').first()).toBeVisible();
  await page.getByRole("button", { name: "Elementi", exact: true }).click();
  const navigator = page.getByRole("complementary", { name: "Elementi", exact: true });
  await expect(navigator.locator("li")).toHaveCount(18);
  await navigator.getByRole("textbox", { name: "Cerca nel processo" }).fill("Attività 18:");
  await navigator.getByRole("button", { name: /Attività 18:/ }).click();
  await expect(page.getByRole("textbox", { name: "Nome" })).toHaveValue(tasks[17].name);
  await page.getByRole("button", { name: "Chiudi elenco elementi" }).click();

  const imported = xml.replaceAll("Task_", "Imported_").replace('bpmn:userTask id="Imported_2"', 'bpmn:serviceTask id="Imported_2"').replace('bpmn:userTask id="Imported_3"', 'bpmn:exclusiveGateway id="Imported_3"');
  await page.locator('.process-bpmn-file-input').setInputFiles({ name: "synthetic-import.bpmn", mimeType: "application/xml", buffer: Buffer.from(imported) });
  await page.getByRole("button", { name: "Elementi", exact: true }).click();
  await navigator.getByRole("textbox", { name: "Cerca nel processo" }).fill("Imported_2");
  await navigator.getByRole("button", { name: /ServiceTask/ }).click();
  await expect(navigator.locator("li")).toHaveCount(1);
  await page.getByRole("button", { name: "Proprietà", exact: true }).click();
  await page.getByText("Proprietà tecniche BPMN", { exact: true }).click();
  const properties = page.locator(".process-bpmn-properties-host");
  const nameInput = properties.getByRole("textbox", { name: "Nome", exact: true });
  if (!await nameInput.isVisible()) await properties.locator('[data-group-id="group-general"]').getByRole("button", { name: "Toggle section" }).click();
  await expect(properties.getByRole("textbox", { name: "Nome", exact: true })).toHaveValue(tasks[1].name);
  await properties.getByRole("textbox", { name: "Nome", exact: true }).fill("Automazione importata");
  await expect(navigator).toContainText("Automazione importata");
  await page.getByRole("button", { name: "Chiudi i pannelli", exact: true }).click();
  await expect(page.getByRole("button", { name: "Proprietà", exact: true })).toBeFocused();
  await expect(page.getByRole("textbox", { name: "Nome" })).toHaveValue("Automazione importata");
  const search = navigator.getByRole("textbox", { name: "Cerca nel processo" });
  await search.press("ControlOrMeta+A");
  await search.press("Backspace");
  await expect(search).toHaveValue("");
  await expect(navigator.locator("li")).toHaveCount(18);
  await expect(page.locator('[data-element-id="Task_1"]')).toHaveCount(0);
  await testInfo.attach("Process desktop", { body: await page.screenshot({ path: process.env.DELIR_UI_PROOF_DIR ? join(process.env.DELIR_UI_PROOF_DIR, "process-desktop.png") : undefined }), contentType: "image/png" });
  const shape = page.locator('.delir-type-automation .djs-visual > rect').first();
  const tint = await shape.evaluate((el) => getComputedStyle(el).fill);
  await page.getByRole("button", { name: "Importa, esporta, cronologia" }).click();
  await page.getByRole("menuitemcheckbox", { name: "Colori per tipo" }).click();
  await expect.poll(() => shape.evaluate((el) => getComputedStyle(el).fill)).not.toBe(tint);
  const saved = page.waitForRequest((req) => req.method() === "PUT" && req.url().endsWith("/layout-model"));
  await page.getByRole("button", { name: "Salva", exact: true }).click();
  const savedXml = (await saved).postDataJSON().xml as string;
  expect(savedXml).toContain("Automazione importata");
  expect(savedXml).not.toContain("bioc:fill");
  expect(savedXml).not.toContain("delir-type");
});

test("process loading failures are recoverable and never look like a new empty model", async ({ page }) => {
  let failed = true;
  await page.route("**/v1/workspace/bpmn-models/layout-model", (route) => route.fulfill(failed ? { status: 503, json: { detail: "Synthetic model unavailable" } } : { json: { id: "layout-model", process_id: "layout-process", name: "Modello demo", xml } }));
  await page.goto(canvasView);
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByText("Il modello è ancora vuoto", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Salva", exact: true })).toBeDisabled();
  failed = false;
  await page.getByRole("button", { name: "Riprova caricamento" }).click();
  await expect(page.locator('[data-element-id="Task_1"]').first()).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("process chrome and element navigation remain accessible without overlap on mobile", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(canvasView);
  await expect(page.locator('[data-element-id="Task_1"]').first()).toBeVisible();
  await page.getByRole("button", { name: "Elementi", exact: true }).click();
  await expect(page.getByRole("complementary", { name: "Elementi" })).toBeVisible();
  await expect(page.locator(".process-bpmn-canvas")).toBeHidden();
  await page.getByRole("textbox", { name: "Cerca nel processo" }).fill("Attività 18:");
  await page.getByRole("button", { name: /Attività 18:/ }).click();
  await expect(page.locator(".process-bpmn-canvas")).toBeVisible();
  await expect(page.getByRole("button", { name: "Elementi", exact: true })).toBeFocused();
  await page.getByRole("button", { name: "Proprietà", exact: true }).click();
  await expect(page.locator(".process-bpmn-canvas")).toBeHidden();
  await expect(page.getByRole("textbox", { name: "Nome" })).toHaveValue(tasks[17].name);
  await testInfo.attach("Process mobile", { body: await page.screenshot({ path: process.env.DELIR_UI_PROOF_DIR ? join(process.env.DELIR_UI_PROOF_DIR, "process-mobile.png") : undefined }), contentType: "image/png" });
  await page.getByRole("button", { name: "Chiudi i pannelli", exact: true }).click();
  await expect(page.locator(".process-bpmn-canvas")).toBeVisible();
  await expect(page.getByRole("button", { name: "Proprietà", exact: true })).toBeFocused();
  const controls = page.locator(".process-bpmn-toolbar button, .process-studio-header button");
  const overflow = await controls.evaluateAll((els) => els.filter((el) => { const box = el.getBoundingClientRect(); return box.width && (box.right > innerWidth + 1 || box.left < 0); }).length);
  expect(overflow).toBe(0);
  const scan = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
  expect(scan.violations).toEqual([]);
});


test("reserved BPMN tools create elements through the modeler without covering its viewport", async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto(canvasView);
  const canvas = page.locator(".process-bpmn-canvas");
  await expect(canvas.locator('[data-element-id="Task_7"]').first()).toBeVisible();
  await page.getByRole("button", { name: "Centra e adatta diagramma", exact: true }).click();
  const first = (await canvas.locator('[data-element-id="Task_1"]').first().boundingBox())!;
  const nextRow = (await canvas.locator('[data-element-id="Task_7"]').first().boundingBox())!;
  const surface = (await canvas.boundingBox())!;
  await page.getByRole("button", { name: "Crea attività", exact: true }).click();
  // Derive the blank gap from the rendered rows, independent of overview scale.
  await canvas.click({ position: { x: first.x + first.width / 2 - surface.x, y: (first.y + first.height + nextRow.y) / 2 - surface.y } });
  await expect(page.locator('.delir-type-task')).toHaveCount(19);
  const toolsBox = (await page.getByRole("navigation", { name: "Strumenti BPMN" }).boundingBox())!;
  const modelBox = (await canvas.boundingBox())!;
  expect(toolsBox.x + toolsBox.width).toBeLessThanOrEqual(modelBox.x + 1);
  await page.getByRole("button", { name: "Elementi", exact: true }).click();
  await expect(page.getByRole("complementary", { name: "Elementi" }).locator("li")).toHaveCount(19);
});


for (const mobile of [false, true]) {
 test(`unpooled resources require explicit assignment and remain empty after removal and reload on ${mobile ? "mobile" : "desktop"}`, async ({ page }, testInfo) => {
  test.setTimeout(Math.max(testInfo.timeout, 90_000));
  await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1366, height: 900 });
  await page.goto(`${studio}/simulation/workspace?panel=scenario`);
  const run = page.getByRole("button", { name: "Avvia simulazione", exact: true });
  await expect(page.getByText("Nessuna risorsa configurata", { exact: true })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Ruolo", exact: true })).toHaveCount(0);
  await expect(run).toBeDisabled();
  await page.getByRole("button", { name: "Aggiungi ruolo", exact: true }).click();
  const resource = page.locator("[data-resource-id]");
  await resource.getByRole("textbox", { name: "Ruolo", exact: true }).fill("Support");
  await resource.getByRole("button", { name: "Conferma capacità e costo", exact: true }).click();
  await expect(run).toBeDisabled();
  const assign = resource.getByRole("button", { name: /Assegna alle attività senza risorsa/ });
  await assign.scrollIntoViewIfNeeded();
  const assignBounds = (await assign.boundingBox())!;
  expect(assignBounds.x).toBeGreaterThanOrEqual(0);
  expect(assignBounds.x + assignBounds.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  await assign.click();
  await expect(run).toBeEnabled();
  await resource.getByRole("button", { name: "Rimuovi ruolo Support", exact: true }).click();
  await expect(run).toBeDisabled();
  await expect(page.locator("[data-resource-id]")).toHaveCount(0);
  await page.reload();
  await expect(page.getByText("Nessuna risorsa configurata", { exact: true })).toBeVisible();
  await expect(run).toBeDisabled();
 });
}

for (const mobile of [false, true]) {
  test(`BPMN lane resource origin, capacity review and stable layout on ${mobile ? "mobile" : "desktop"}`, async ({ page }, testInfo) => {
    test.setTimeout(Math.max(testInfo.timeout, 90_000));
    await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1366, height: 900 });
    const resources = [
      { id: "bpmn-front", bpmn_id: "Lane_front", kind: "lane", name: "Operations", pool_name: "Company", parent_name: "Service delivery", task_ids: tasks.slice(0, 9).map((task) => task.element_id) },
      { id: "bpmn-back", bpmn_id: "Lane_back", kind: "lane", name: "Finance", pool_name: "Company", parent_name: null, task_ids: tasks.slice(9).map((task) => task.element_id) },
    ];
    await page.route("http://127.0.0.1:8000/**/simulation-template", (route) => route.fulfill({ json: { tasks, gateways: [], resources } }));
    await page.goto(`${studio}/simulation/workspace?panel=scenario`);
    const run = page.getByRole("button", { name: "Avvia simulazione", exact: true });
    await expect(page.locator("[data-resource-id]")).toHaveCount(2);
    const front = page.locator('[data-resource-id="bpmn-front"]');
    const back = page.locator('[data-resource-id="bpmn-back"]');
    await expect(front.getByText("Company / Service delivery", { exact: true })).toBeVisible();
    await expect(front.getByText("Attività assegnate: 9", { exact: true })).toBeVisible();
    await expect(back.getByText("Attività assegnate: 9", { exact: true })).toBeVisible();
    await expect(run).toBeDisabled();
    await front.getByRole("spinbutton", { name: "Unità disponibili", exact: true }).fill("2");
    await front.getByRole("button", { name: "Conferma capacità e costo", exact: true }).click();
    await expect(run).toBeDisabled();
    await back.getByRole("button", { name: "Conferma capacità e costo", exact: true }).click();
    await expect(run).toBeEnabled();
    const task1 = page.locator('[data-sim-el="Task_1"]');
    await expect(task1.getByRole("combobox").last()).toHaveText("Company / Operations");
    const task18 = page.locator('[data-sim-el="Task_18"]');
    await expect(task18.getByRole("combobox").last()).toHaveText("Company / Finance");
    await back.getByRole("spinbutton", { name: "Unità disponibili", exact: true }).fill("1.5");
    await expect(back.getByRole("button", { name: "Conferma capacità e costo", exact: true })).toBeDisabled();
    await expect(run).toBeDisabled();
    await back.getByRole("spinbutton", { name: "Unità disponibili", exact: true }).fill("3");
    await back.getByRole("button", { name: "Conferma capacità e costo", exact: true }).click();
    await front.scrollIntoViewIfNeeded();
    const overflow = await page.locator("[data-resource-id] input, [data-resource-id] button").evaluateAll((nodes) => nodes.filter((node) => {
      const r = node.getBoundingClientRect(); return r.width > 0 && (r.right > innerWidth + 1 || r.left < 0);
    }).length);
    expect(overflow).toBe(0);
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze()).violations).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath(`resources-${mobile ? "mobile" : "desktop"}.png`) });
    const request = page.waitForRequest((req) => req.method() === "POST" && req.url().endsWith("/simulation-runs"));
    await run.click();
    const body = (await request).postDataJSON();
    expect(body.resources.map((r: { name: string }) => r.name)).toEqual(["Operations", "Finance"]);
    expect(body.tasks.find((t: { element_id: string }) => t.element_id === "Task_1").resource_id).toBe("bpmn-front");
    expect(body.tasks.find((t: { element_id: string }) => t.element_id === "Task_18").resource_id).toBe("bpmn-back");
    await page.reload();
    await expect(page.locator('[data-resource-id="bpmn-front"]').getByText("Capacità e costo confermati", { exact: true })).toBeVisible();
  });
}


test("resource configuration waits for the BPMN before claiming the model is empty", async ({ page }, testInfo) => {
  test.setTimeout(Math.max(testInfo.timeout, 90_000));
  let releaseModel!: () => void;
  let signalRequest!: () => void;
  const requestSeen = new Promise<void>((resolve) => { signalRequest = resolve; });
  const modelReady = new Promise<void>((resolve) => { releaseModel = resolve; });
  await page.route("http://127.0.0.1:8000/**/layout-model", async (route) => {
    signalRequest();
    await modelReady;
    await route.fulfill({ json: { id: "layout-model", process_id: "layout-process", name: "Modello demo", xml } });
  });
  await page.goto(`${studio}/simulation/workspace?panel=scenario`);
  await requestSeen;
  const dock = page.locator(".sim-studio-dock");
  await expect(dock.getByRole("heading", { name: "Configura scenario", exact: true })).toBeVisible();
  await expect(dock.getByText("Nessun BPMN da simulare. Genera o salva un modello nel canvas.", { exact: true })).toHaveCount(0);
  await expect(dock.getByText("Nessuna risorsa configurata", { exact: true })).toHaveCount(0);
  releaseModel();
  await expect(dock.getByText("Nessuna risorsa configurata", { exact: true })).toBeVisible();
});

for (const width of [1440, 1920]) {
  test(`process canvas hierarchy preserves camera, edits and one inspector at ${width}`, async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.startsWith("mobile"), "Desktop composition");
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(canvasView);
    const canvas = page.locator(".process-bpmn-canvas");
    const viewport = canvas.locator(".viewport");
    await expect(page.getByRole("button", { name: "Elementi", exact: true })).toBeEnabled();
    const header = await page.locator(".process-studio-header").boundingBox();
    // One context row accommodates 44 px controls and shared vertical padding.
    expect(header!.height).toBeLessThanOrEqual(72);
    await expect.poll(async () => (await canvas.boundingBox())!.height).toBeGreaterThan(760);
    await page.getByRole("button", { name: "Dettagli", exact: true }).click();
    await expect(page.getByText("Team Operations", { exact: true })).toBeVisible();
    await page.keyboard.press("Escape");
    // The initial overview includes the entire process, even with eighteen tasks.
    await expect.poll(async () => canvas.locator(".djs-shape").evaluateAll(nodes => nodes.filter(node => {
      const rect = node.getBoundingClientRect(), bounds = node.closest(".process-bpmn-canvas")!.getBoundingClientRect();
      return rect.width > 0 && (rect.left < bounds.left - 1 || rect.right > bounds.right + 1 || rect.top < bounds.top - 1 || rect.bottom > bounds.bottom + 1);
    }).length)).toBe(0);
    const originalCamera = await viewport.getAttribute("transform");
    const diagramBox = (await canvas.boundingBox())!;
    await page.getByRole("button", { name: "Sposta la tela", exact: true }).click();
    await page.mouse.move(diagramBox.x + 20, diagramBox.y + 20);
    await page.mouse.down();
    await page.mouse.move(diagramBox.x + 60, diagramBox.y + 50, { steps: 5 });
    await page.mouse.up();
    await expect(viewport).not.toHaveAttribute("transform", originalCamera!);
    await page.getByRole("button", { name: "Seleziona", exact: true }).click();
    await canvas.locator('[data-element-id="Task_1"]').first().click();
    await page.getByRole("textbox", { name: "Nome" }).fill("Bozza da conservare");
    const inspector = page.locator(".process-studio-properties");
    await expect(inspector).toBeVisible();
    await expect(page.getByRole("button", { name: "Chiudi ispettore", exact: true })).toHaveCount(1);
    const camera = await viewport.getAttribute("transform");
    const initialWidth = (await inspector.boundingBox())!.width;
    const resize = page.getByRole("separator", { name: "Ridimensiona ispettore", exact: true });
    await resize.press("ArrowLeft");
    await expect.poll(async () => (await inspector.boundingBox())!.width).toBeGreaterThan(initialWidth);
    await expect(viewport).toHaveAttribute("transform", camera!);
    expect((await canvas.boundingBox())!.width).toBeGreaterThanOrEqual(720);
    await page.getByRole("button", { name: "Proprietà", exact: true }).click();
    await expect(inspector.locator(".process-enterprise-host")).toBeVisible();
    await expect(inspector.locator(".process-detail-host")).toBeHidden();
    await expect(viewport).toHaveAttribute("transform", camera!);
    await page.getByRole("button", { name: "Chiudi i pannelli", exact: true }).click();
    await expect(page.getByRole("textbox", { name: "Nome" })).toHaveValue("Bozza da conservare");
    await page.getByRole("button", { name: "Chat canvas", exact: true }).click();
    await expect(page.locator(".process-studio-chat")).toBeVisible();
    expect((await canvas.boundingBox())!.width).toBeGreaterThanOrEqual(720);
    await expect(viewport).toHaveAttribute("transform", camera!);
    // Explicit centering uses the current stage bounds after the inspector resize.
    await page.getByRole("button", { name: "Centra e adatta diagramma", exact: true }).click();
    await expect.poll(async () => canvas.locator(".djs-shape").evaluateAll(nodes => nodes.filter(node => {
      const rect = node.getBoundingClientRect(), bounds = node.closest(".process-bpmn-canvas")!.getBoundingClientRect();
      return rect.width > 0 && (rect.left < bounds.left - 1 || rect.right > bounds.right + 1 || rect.top < bounds.top - 1 || rect.bottom > bounds.bottom + 1);
    }).length)).toBe(0);
    const scan = await new AxeBuilder({ page }).include(".process-workspace").include(".process-studio-header").withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(scan.violations).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath(`process-canvas-hierarchy-${width}.png`) });
  });
}


for (const mobile of [false, true]) test(`DeliR canvas controls keep XML and the edit-save-reopen workflow on ${mobile ? "mobile" : "desktop"}`, async ({ page }, info) => {
  test.setTimeout(120_000);
  await page.setViewportSize(mobile ? { width:390, height:844 } : { width:1600, height:1000 });
  let savedXml = xml;
  const writes: string[] = [];
  await page.route("**/v1/workspace/bpmn-models/layout-model", async route => {
    if (route.request().method() === "PUT") { savedXml = route.request().postDataJSON().xml; writes.push(savedXml); }
    await route.fulfill({json:{id:"layout-model",process_id:"layout-process",name:"Model",xml:savedXml,version_id:1}});
  });
  await page.goto(canvasView);
  const canvas = page.locator(".process-bpmn-canvas");
  await expect(canvas.locator('[data-element-id="Task_1"]').first()).toBeVisible();
  const before = xml;
  await page.getByRole("button", {name:/^Zoom [0-9]+%$/}).click();
  await page.getByRole("menuitem", {name:"100%",exact:true}).click();
  await expect(page.getByRole("button", {name:"Zoom 100%"})).toBeVisible();
  await page.getByRole("button", {name:"Sposta la tela",exact:true}).click();
  await expect(page.getByRole("button", {name:"Sposta la tela",exact:true})).toHaveAttribute("aria-pressed","true");
  await page.getByRole("button", {name:"Seleziona",exact:true}).click();
  await expect(page.getByRole("button", {name:"Seleziona",exact:true})).toHaveAttribute("aria-pressed","true");
  await page.getByRole("button", {name:"Centra e adatta diagramma",exact:true}).click();
  expect(writes).toEqual([]); expect(savedXml).toBe(before);
  await canvas.locator('[data-element-id="Task_1"]').first().click();
  const selection = page.getByRole("group", {name:"Azioni della selezione"});
  await expect(selection).toBeVisible();
  await expect(canvas.locator(".djs-context-pad.open")).toBeHidden();
  if (mobile) await page.getByRole("button", {name:"Proprietà",exact:true}).click();
  const inspector = page.locator(".process-enterprise-properties");
  const name = inspector.getByRole("textbox", {name:"Nome",exact:true});
  await expect(name).toHaveValue(tasks[0].name);
  await name.fill("Verifica documenti");
  if (mobile) await page.getByRole("button", {name:"Chiudi i pannelli",exact:true}).click();
  await page.getByRole("button", {name:"Annulla modifica",exact:true}).click();
  await expect(canvas.locator('[data-element-id="Task_1"]')).toContainText(tasks[0].name);
  await page.getByRole("button", {name:"Ripeti modifica",exact:true}).click();
  await expect(canvas.locator('[data-element-id="Task_1"]')).toContainText("Verifica documenti");
  await page.getByRole("button", {name:"Salva",exact:true}).click();
  await expect.poll(()=>writes.length).toBe(1);
  const summary = await page.evaluate(source=>{const doc=new DOMParser().parseFromString(source,"application/xml");return {error:doc.querySelector("parsererror")?.textContent,tasks:doc.getElementsByTagNameNS("http://www.omg.org/spec/BPMN/20100524/MODEL","userTask").length,flows:Array.from(doc.getElementsByTagNameNS("http://www.omg.org/spec/BPMN/20100524/MODEL","sequenceFlow")).map(el=>({id:el.id,from:el.getAttribute("sourceRef"),to:el.getAttribute("targetRef")})),name:doc.querySelector('[id="Task_1"]')?.getAttribute("name")}},savedXml);
  expect(summary.error).toBeUndefined();expect(summary.tasks).toBe(18);expect(summary.flows).toHaveLength(17);expect(summary.flows[0]).toEqual({id:"Flow_0",from:"Task_1",to:"Task_2"});expect(summary.name).toBe("Verifica documenti");
  await page.reload();
  await expect(canvas.locator('[data-element-id="Task_1"]')).toContainText("Verifica documenti");
  expect(savedXml).toContain('targetNamespace="https://example.test/layout"');
  expect((await new AxeBuilder({page}).include(".process-workspace").withTags(["wcag2a","wcag2aa","wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
  await page.screenshot({path:info.outputPath("canvas-ui.png"),animations:"disabled"});
});

for (const mobile of [false, true]) test(`selection actions use the existing BPMN commands on ${mobile ? "mobile" : "desktop"}`, async ({page}, info) => {
  test.setTimeout(90_000);
  await page.setViewportSize(mobile ? {width:390,height:844} : {width:1600,height:1000});
  await page.goto(canvasView);
  const canvas=page.locator('.process-bpmn-canvas');
  const task=canvas.locator('[data-element-id="Task_1"]').first();
  await task.click();
  const actions=page.getByRole('group',{name:'Azioni della selezione'});
  await expect(actions).toBeVisible();
  await actions.getByRole('button',{name:'Aggiungi passaggio',exact:true}).click();
  // Escape closes the child menu and returns focus without discarding selection.
  await page.keyboard.press('Escape');
  await expect(actions.getByRole('button',{name:'Aggiungi passaggio',exact:true})).toBeFocused();
  await expect(task).toHaveClass(/selected/);
  await actions.getByRole('button',{name:'Aggiungi passaggio',exact:true}).click();
  await page.getByRole('menuitem',{name:'Aggiungi attività',exact:true}).click();
  await expect(canvas.locator('.delir-type-task')).toHaveCount(19);
  await page.getByRole('button',{name:'Annulla modifica',exact:true}).click();
  await expect(canvas.locator('.delir-type-task')).toHaveCount(18);
  await task.click();
  await page.getByRole('button',{name:'Collega elemento',exact:true}).click();
  await canvas.locator('[data-element-id="Task_3"]').first().click();
  await expect(canvas.locator('.djs-connection')).toHaveCount(18);
  await page.getByRole('button',{name:'Annulla modifica',exact:true}).click();
  await expect(canvas.locator('.djs-connection')).toHaveCount(17);
  await task.click();
  await page.getByRole('button',{name:'Collega elemento',exact:true}).click();
  await page.keyboard.press('Escape');
  await expect(canvas.locator('.djs-connection')).toHaveCount(17);
  await expect(task).toHaveClass(/selected/);
  await actions.getByRole('button',{name:'Altre azioni',exact:true}).click();
  await page.getByRole('menuitem',{name:'Elimina elemento',exact:true}).click();
  await expect(task).toHaveCount(0);
  await page.getByRole('button',{name:'Annulla modifica',exact:true}).click();
  await expect(task).toBeVisible();
  await expect(canvas.locator('.djs-connection')).toHaveCount(17);
  if (!mobile) {
    if (!await task.evaluate(el=>el.classList.contains('selected'))) await task.click();
    await actions.getByRole('button',{name:'Altre azioni',exact:true}).click();await page.getByRole('menuitem',{name:'Cambia tipo',exact:true}).hover();
    await expect(page.getByRole('menuitem',{name:'Attività di servizio',exact:true})).toBeVisible();
    await page.keyboard.press('Escape');
  }
  await page.screenshot({path:info.outputPath('selection-actions.png'),animations:'disabled'});
  expect((await new AxeBuilder({page}).include('.process-workspace').withTags(['wcag2a','wcag2aa','wcag22aa']).analyze()).violations).toEqual([]);
});


test('mouse tools keep selection, pan and node movement separate', async ({page}) => {
  test.setTimeout(90_000);
  await page.setViewportSize({width:1600,height:1000}); await page.goto(canvasView);
  const canvas=page.locator('.process-bpmn-canvas'), viewport=canvas.locator('.viewport');
  const task=canvas.locator('[data-element-id="Task_1"]').first();
  const pan=page.getByRole('button',{name:'Sposta la tela',exact:true});
  const select=page.getByRole('button',{name:'Seleziona',exact:true});
  const drag=async(from:{x:number;y:number},to:{x:number;y:number},button:'left'|'middle'|'right'='left')=>{await page.mouse.move(from.x,from.y);await page.mouse.down({button});await page.mouse.move(to.x,to.y,{steps:12});await page.mouse.up({button});};
  const moveNode=async(button:'left'|'middle'|'right'='left')=>{const b=(await task.boundingBox())!;await drag({x:b.x+b.width/2,y:b.y+b.height/2},{x:b.x+b.width/2+60,y:b.y+b.height/2+30},button);};
  await task.click(); const initialNode=await task.getAttribute('transform');
  await task.click(); await expect(task).toHaveClass(/selected/);
  await pan.click(); let camera=await viewport.getAttribute('transform'); await moveNode();
  await expect(viewport).not.toHaveAttribute('transform',camera!); await expect(task).toHaveAttribute('transform',initialNode!);await expect(pan).toHaveAttribute('aria-pressed','true');
  camera=await viewport.getAttribute('transform');await moveNode(); await expect(viewport).not.toHaveAttribute('transform',camera!);await expect(task).toHaveAttribute('transform',initialNode!);
  await page.keyboard.press('v');await expect(select).toHaveAttribute('aria-pressed','true');
  camera=await viewport.getAttribute('transform'); await page.keyboard.down('Space');await moveNode();await page.keyboard.up('Space');
  await expect(viewport).not.toHaveAttribute('transform',camera!);await expect(task).toHaveAttribute('transform',initialNode!);await expect(select).toHaveAttribute('aria-pressed','true');
  for (const button of ['middle','right'] as const) { camera=await viewport.getAttribute('transform');await moveNode(button);await expect(viewport).not.toHaveAttribute('transform',camera!);await expect(task).toHaveAttribute('transform',initialNode!); }
  camera=await viewport.getAttribute('transform');await moveNode();await expect(task).not.toHaveAttribute('transform',initialNode!);await expect(viewport).toHaveAttribute('transform',camera!);
  await page.getByRole('button',{name:'Annulla modifica',exact:true}).click();await expect(task).toHaveAttribute('transform',initialNode!);
  await select.click();await page.keyboard.press('h');await expect(pan).toHaveAttribute('aria-pressed','true');await page.keyboard.press('Escape');await expect(select).toHaveAttribute('aria-pressed','true');
});

test('selection rectangle selects objects without moving the camera', async ({page})=>{
  await page.setViewportSize({width:1600,height:1000});await page.goto(canvasView);
  const canvas=page.locator('.process-bpmn-canvas'), viewport=canvas.locator('.viewport');
  await page.getByRole('button',{name:'Centra e adatta diagramma',exact:true}).click();
  const first=canvas.locator('[data-element-id="Task_1"]').first(),second=canvas.locator('[data-element-id="Task_2"]').first();
  const a=(await first.boundingBox())!,b=(await second.boundingBox())!;const camera=await viewport.getAttribute('transform');
  await page.mouse.move(a.x-15,a.y-15);await page.mouse.down();await page.mouse.move(b.x+b.width+15,b.y+b.height+15,{steps:15});await page.mouse.up();
  await expect(first).toHaveClass(/selected/);await expect(second).toHaveClass(/selected/);await expect(viewport).toHaveAttribute('transform',camera!);
  await expect(page.locator('.process-enterprise-properties')).toHaveCount(0);
  await expect(page.locator('.ui-workspace-inspector')).toBeHidden();
  const selected = page.getByRole('button',{name:/elementi selezionati/});
  await expect(selected).toBeVisible();
  await expect(page.getByRole('button',{name:'Elimina selezione',exact:true})).toBeVisible();
  await selected.click();
  await expect(page.getByText('Scegli un elemento per aprirne le proprietà.',{exact:true})).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(first).toHaveClass(/selected/);
  await page.getByRole('button',{name:'Elimina selezione',exact:true}).click();
  await expect(first).toHaveCount(0);await expect(second).toHaveCount(0);
  await page.getByRole('button',{name:'Annulla modifica',exact:true}).click();
  await expect(first).toBeVisible();await expect(second).toBeVisible();
});

test('selection list opens one element and clearing returns keyboard focus to the canvas', async ({page}) => {
  await page.setViewportSize({width:1600,height:1000}); await page.goto(canvasView);
  const canvas = page.locator('.process-bpmn-canvas'), svg = canvas.locator('.djs-container > svg');
  await canvas.locator('[data-element-id="Task_1"]').first().waitFor();
  await svg.focus(); await page.keyboard.press('Control+a');
  await page.getByRole('button',{name:'35 elementi selezionati',exact:true}).click();
  const list = page.getByRole('dialog',{name:'35 elementi selezionati',exact:true});
  await expect(list.getByRole('button')).toHaveCount(35);
  await list.getByRole('button',{name:/^Attività 1:.*Attività utente$/}).click();
  await expect(page.getByRole('textbox',{name:'Nome',exact:true})).toBeVisible();
  await expect(canvas.locator('[data-element-id="Task_2"]').first()).not.toHaveClass(/selected/);
  await page.getByRole('button',{name:'Chiudi ispettore',exact:true}).click();
  await svg.focus(); await page.keyboard.press('Control+a');
  await page.getByRole('button',{name:'Deseleziona tutto',exact:true}).click();
  await expect(canvas.locator('.djs-element.selected')).toHaveCount(0);
  await expect(svg).toBeFocused();
});

test('mouse and trackpad wheel modes preserve the pointer anchor and model',async({page})=>{
  test.setTimeout(90_000);await page.setViewportSize({width:1600,height:1000});await page.goto(canvasView);
  const canvas=page.locator('.process-bpmn-canvas'), viewport=canvas.locator('.viewport'), task=canvas.locator('[data-element-id="Task_1"]').first();
  await expect(task).toBeVisible();const node=await task.getAttribute('transform');const box=(await canvas.boundingBox())!;const point={x:box.x+box.width*.6,y:box.y+box.height*.65};
  const world=()=>page.evaluate(p=>{const matrix=document.querySelector<SVGGElement>('.process-bpmn-canvas .viewport')!.getScreenCTM()!;const local=new DOMPoint(p.x,p.y).matrixTransform(matrix.inverse());return {x:local.x,y:local.y,scale:matrix.a};},point);
  const before=await world();await page.mouse.move(point.x,point.y);await page.mouse.wheel(0,-100);await expect.poll(async()=>(await world()).scale).toBeGreaterThan(before.scale);
  const after=await world();expect(Math.abs(after.x-before.x)).toBeLessThan(1);expect(Math.abs(after.y-before.y)).toBeLessThan(1);await expect(task).toHaveAttribute('transform',node!);
  await page.getByRole('button',{name:'Importa, esporta, cronologia',exact:true}).click();await page.getByRole('menuitemradio',{name:'Trackpad · scorri per spostare',exact:true}).click();
  const panBefore=await world(),camera=await viewport.getAttribute('transform');await page.mouse.move(point.x,point.y);await page.mouse.wheel(35,80);await expect(viewport).not.toHaveAttribute('transform',camera!);expect((await world()).scale).toBeCloseTo(panBefore.scale,5);
  const pinchBefore=await world();await page.keyboard.down('Control');await page.mouse.wheel(0,-60);await page.keyboard.up('Control');await expect.poll(async()=>(await world()).scale).toBeGreaterThan(pinchBefore.scale);
  await expect(task).toHaveAttribute('transform',node!);await page.reload();await page.getByRole('button',{name:'Importa, esporta, cronologia',exact:true}).click();await expect(page.getByRole('menuitemradio',{name:'Trackpad · scorri per spostare',exact:true})).toHaveAttribute('aria-checked','true');
});


test("inline rename commits, cancels, undoes and saves the BPMN name",async({page})=>{
 await page.setViewportSize({width:1600,height:1000});const writes:string[]=[];
 await page.route("**/v1/workspace/bpmn-models/layout-model",async route=>{if(route.request().method()==="PUT")writes.push(route.request().postDataJSON().xml);await route.fulfill({json:{id:"layout-model",process_id:"layout-process",name:"Model",xml:writes.at(-1)??xml,version_id:1}});});
 await page.goto(canvasView);const canvas=page.locator(".process-bpmn-canvas"),task=canvas.locator('[data-element-id="Task_1"]').first();
 await expect(task).toBeVisible();await task.dblclick();const form=page.getByRole("form",{name:"Rinomina elemento"}),input=form.getByRole("textbox",{name:"Nome",exact:true});
 await input.fill("Cancelled");await input.press("Escape");await expect(form).toBeHidden();await expect(task).toContainText(tasks[0].name);
 await task.dblclick();await input.fill("Rinominato nel canvas");await input.press("Enter");await expect(task).toContainText("Rinominato nel canvas");
 await page.getByRole("button",{name:"Annulla modifica",exact:true}).click();await expect(task).toContainText(tasks[0].name);
 await task.dblclick();await input.fill("Salvataggio da tastiera");await input.press("Control+s");await expect.poll(()=>writes.length).toBe(1);
 expect(await page.evaluate(source=>new DOMParser().parseFromString(source,"application/xml").getElementById("Task_1")!.getAttribute("name"),writes[0])).toBe("Salvataggio da tastiera");
});

test("clipboard keeps copied tasks independent with new IDs and valid BPMN references",async({page})=>{
 const pageErrors:string[]=[];page.on("pageerror",error=>pageErrors.push(error.message));
 await page.setViewportSize({width:1600,height:1000});let savedXml=xml;
 await page.route("**/v1/workspace/bpmn-models/layout-model",async route=>{if(route.request().method()==="PUT")savedXml=route.request().postDataJSON().xml;await route.fulfill({json:{id:"layout-model",process_id:"layout-process",name:"Model",xml:savedXml,version_id:1}});});
 await page.goto(canvasView);const canvas=page.locator(".process-bpmn-canvas"),svg=canvas.locator(".djs-container > svg");
 await canvas.locator('[data-element-id="Task_1"]').first().click();await page.keyboard.down("Shift");await canvas.locator('[data-element-id="Task_2"]').first().click();await page.keyboard.up("Shift");
 await expect(canvas.locator(".djs-shape.selected")).toHaveCount(2);
 await svg.focus();await page.keyboard.press("Control+c");const bounds=(await canvas.boundingBox())!,point={x:bounds.x+bounds.width*.65,y:bounds.y+bounds.height*.82};
 await page.mouse.move(point.x,point.y);await page.keyboard.press("Control+v");await page.mouse.click(point.x,point.y);
 expect(pageErrors).toEqual([]);
 await expect(canvas.locator(".delir-type-task")).toHaveCount(20);await expect(canvas.locator(".djs-connection")).toHaveCount(18);
 await page.getByRole("button",{name:"Annulla modifica",exact:true}).click();await expect(canvas.locator(".delir-type-task")).toHaveCount(18);
 await page.getByRole("button",{name:"Ripeti modifica",exact:true}).click();await expect(canvas.locator(".delir-type-task")).toHaveCount(20);
 await page.getByRole("button",{name:"Salva",exact:true}).click();
 await expect.poll(()=>savedXml!==xml).toBe(true);
 const result=await page.evaluate(source=>{const doc=new DOMParser().parseFromString(source,"application/xml"),nodes=Array.from(doc.getElementsByTagNameNS("http://www.omg.org/spec/BPMN/20100524/MODEL","userTask")),flows=Array.from(doc.getElementsByTagNameNS("http://www.omg.org/spec/BPMN/20100524/MODEL","sequenceFlow"));return{error:!!doc.querySelector("parsererror"),ids:nodes.map(n=>n.id),flows:flows.map(f=>({id:f.id,source:f.getAttribute("sourceRef"),target:f.getAttribute("targetRef")})),original:doc.getElementById("Task_1")!.getAttribute("name")};},savedXml);
 expect(result.error).toBe(false);expect(result.ids).toHaveLength(20);expect(new Set(result.ids).size).toBe(20);expect(result.original).toBe(tasks[0].name);
 for(const flow of result.flows){expect(result.ids).toContain(flow.source);expect(result.ids).toContain(flow.target);}
 await expect(canvas.locator(".bjs-powered-by")).toHaveCount(0);
});

test("semantic selection keeps symbols clear and edits event labels below their shape", async ({page}) => {
  await page.setViewportSize({width:1600,height:1000});
  const symbols = [
    {id:"Start",type:"startEvent",x:80,y:160,width:36,height:36},
    {id:"Gateway",type:"exclusiveGateway",x:280,y:150,width:50,height:50},
    {id:"End",type:"endEvent",x:480,y:160,width:36,height:36},
    {id:"Task",type:"userTask",x:650,y:140,width:160,height:88}
  ];
  const source = '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" targetNamespace="urn:test"><bpmn:process id="Process">'+symbols.map(n=>'<bpmn:'+n.type+' id="'+n.id+'"/>').join('')+'</bpmn:process><bpmndi:BPMNDiagram id="diagram"><bpmndi:BPMNPlane id="plane" bpmnElement="Process">'+symbols.map(n=>'<bpmndi:BPMNShape id="'+n.id+'_di" bpmnElement="'+n.id+'"><dc:Bounds x="'+n.x+'" y="'+n.y+'" width="'+n.width+'" height="'+n.height+'"/></bpmndi:BPMNShape>').join('')+'</bpmndi:BPMNPlane></bpmndi:BPMNDiagram></bpmn:definitions>';
  let saved=source;const errors:string[]=[];page.on("pageerror",e=>errors.push(e.message));
  await page.route("**/v1/workspace/bpmn-models/layout-model",async route=>{if(route.request().method()==="PUT")saved=route.request().postDataJSON().xml;await route.fulfill({json:{id:"layout-model",process_id:"layout-process",name:"Synthetic model",xml:saved,version_id:1}});});
  await page.goto(canvasView);const canvas=page.locator(".process-bpmn-canvas");
  for(const [id,kind] of [["Start","start"],["Gateway","gateway"],["End","end"],["Task","task"]]){
    const node=canvas.locator('.djs-element[data-element-id="'+id+'"]').first();
    await page.getByRole("button",{name:"Centra e adatta diagramma",exact:true}).click();
    await node.click();await expect(node.locator(".djs-outline")).toHaveAttribute("data-selection-kind",kind);
    await expect(canvas.locator(".djs-resizer")).toHaveCount(0);
  }
  await page.getByRole("button",{name:"Centra e adatta diagramma",exact:true}).click();
  const start=canvas.locator('.djs-element[data-element-id="Start"]').first();await start.dblclick();
  const editor=page.getByRole("form",{name:"Rinomina elemento"}).getByRole("textbox",{name:"Nome",exact:true});
  const shape=await start.locator(".djs-visual > circle").first().boundingBox(), editing=await editor.boundingBox();
  expect(editing!.y).toBeGreaterThan(shape!.y+shape!.height-1);
  await editor.fill("Richiesta ricevuta");await editor.press("Enter");
  await expect(canvas.locator('[data-delir-label-for="Start"]')).toContainText("Richiesta ricevuta");
  await page.getByRole("button",{name:"Annulla modifica",exact:true}).click();
  await expect(canvas.locator('[data-delir-label-for="Start"]')).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Salva",exact:true})).toBeDisabled();
  expect(saved).toBe(source);expect(errors).toEqual([]);
});

test("canvas chat reserves readable space for conversation, actions and composer",async({page})=>{
  await page.setViewportSize({width:1600,height:1000});await page.goto(canvasView);
  await page.getByRole("button",{name:"Chat canvas",exact:true}).click();
  const chat=page.locator(".process-studio-chat");await expect(chat).toBeVisible();
  expect((await chat.boundingBox())!.width).toBeGreaterThanOrEqual(360);
  const copy=chat.locator(".ui-action-prompt-copy");
  if(await copy.count())expect((await copy.boundingBox())!.width).toBeGreaterThan(240);
  const input=chat.getByRole("textbox",{name:"Scrivi un messaggio…",exact:true});
  await expect(input).toBeVisible();
  const controls=chat.locator(".composer-bottom-bar button");
  const boxes=await controls.evaluateAll(nodes=>nodes.map(n=>{const r=n.getBoundingClientRect();return{x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width};}));
  const bounds=(await chat.boundingBox())!;
  for(const box of boxes){expect(box.x).toBeGreaterThanOrEqual(bounds.x);expect(box.right).toBeLessThanOrEqual(bounds.x+bounds.width+1);expect(box.width).toBeGreaterThanOrEqual(24);}
  const scan=await new AxeBuilder({page}).include(".process-studio-chat").analyze();expect(scan.violations).toEqual([]);
});

test("connections follow BPMN pool and lane boundaries and lane removal preserves work",async({page},info)=>{
  await page.setViewportSize({width:1600,height:1000});
  const shapes=[
    ["PoolA",100,100,800,400],["LaneA",130,100,770,200],["LaneB",130,300,770,200],
    ["TaskA",260,150,160,88],["TaskB",550,350,160,88],
    ["PoolB",100,650,800,220],["TaskC",260,710,160,88]
  ];
  let saved='<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" targetNamespace="urn:collaboration"><bpmn:process id="ProcessA"><bpmn:laneSet id="Roles"><bpmn:lane id="LaneA" name="Operations"><bpmn:flowNodeRef>TaskA</bpmn:flowNodeRef></bpmn:lane><bpmn:lane id="LaneB" name="Finance"><bpmn:flowNodeRef>TaskB</bpmn:flowNodeRef></bpmn:lane></bpmn:laneSet><bpmn:task id="TaskA" name="Prepare"/><bpmn:task id="TaskB" name="Approve"/></bpmn:process><bpmn:process id="ProcessB"><bpmn:task id="TaskC" name="Receive"/></bpmn:process><bpmn:collaboration id="Collaboration"><bpmn:participant id="PoolA" name="Company" processRef="ProcessA"/><bpmn:participant id="PoolB" name="Partner" processRef="ProcessB"/></bpmn:collaboration><bpmndi:BPMNDiagram id="Diagram"><bpmndi:BPMNPlane id="Plane" bpmnElement="Collaboration">'+shapes.map(([id,x,y,w,h])=>'<bpmndi:BPMNShape id="'+id+'_di" bpmnElement="'+id+'" isHorizontal="true"><dc:Bounds x="'+x+'" y="'+y+'" width="'+w+'" height="'+h+'"/></bpmndi:BPMNShape>').join('')+'</bpmndi:BPMNPlane></bpmndi:BPMNDiagram></bpmn:definitions>';
  const errors:string[]=[];page.on("pageerror",e=>errors.push(e.message));
  await page.route("**/v1/workspace/bpmn-models/layout-model",async route=>{if(route.request().method()==="PUT")saved=route.request().postDataJSON().xml;await route.fulfill({json:{id:"layout-model",process_id:"layout-process",name:"Collaboration",xml:saved,version_id:1}});});
  await page.goto(canvasView);const canvas=page.locator(".process-bpmn-canvas");
  const node=(id:string)=>canvas.locator('.djs-element[data-element-id="'+id+'"]').first();
  await expect(node("TaskA")).toBeVisible();
  const connect=async(from:string,to:string)=>{
    await node(from).click();await page.getByRole("button",{name:"Collega elemento",exact:true}).click();
    const box=(await node(to).boundingBox())!;await page.mouse.move(box.x+box.width/2,box.y+box.height/2,{steps:12});await page.mouse.click(box.x+box.width/2,box.y+box.height/2);
  };
  await node("TaskA").click();await page.getByRole("button",{name:"Collega elemento",exact:true}).click();
  const laneBox=(await node("LaneB").boundingBox())!;await page.mouse.move(laneBox.x+8,laneBox.y+40,{steps:8});await expect(node("LaneB")).toHaveClass(/connect-not-ok/);
  await page.mouse.click(laneBox.x+8,laneBox.y+40);await expect(canvas.locator(".djs-connection")).toHaveCount(0);
  await connect("TaskA","TaskB");await expect(canvas.locator(".djs-connection")).toHaveCount(1);
  await connect("TaskB","TaskC");await expect(canvas.locator(".djs-connection")).toHaveCount(2);
  await page.getByRole("button",{name:"Salva",exact:true}).click();
  const graph=await page.evaluate(source=>{
    const doc=new DOMParser().parseFromString(source,"application/xml");
    return Array.from(doc.getElementsByTagNameNS("*","sequenceFlow")).map(n=>({type:n.localName,parent:n.parentElement?.id,source:n.getAttribute("sourceRef"),target:n.getAttribute("targetRef")})).concat(Array.from(doc.getElementsByTagNameNS("*","messageFlow")).map(n=>({type:n.localName,parent:n.parentElement?.id,source:n.getAttribute("sourceRef"),target:n.getAttribute("targetRef")})));
  },saved);
  expect(graph).toEqual(expect.arrayContaining([{type:"sequenceFlow",parent:"ProcessA",source:"TaskA",target:"TaskB"},{type:"messageFlow",parent:"Collaboration",source:"TaskB",target:"TaskC"}]));
  await node("LaneB").click({position:{x:8,y:40}});
  await page.getByRole("button",{name:"Aggiungi lane sotto",exact:true}).click();
  await expect(canvas.locator('.djs-element[data-delir-type="bpmn:Lane"]')).toHaveCount(3);
  await node("LaneB").click({position:{x:8,y:40}});await page.getByRole("button",{name:"Altre azioni",exact:true}).click();
  await page.getByRole("menuitem",{name:"Rimuovi lane, mantieni le attività",exact:true}).click();
  await expect(node("LaneB")).toHaveCount(0);await expect(node("TaskB")).toBeVisible();await expect(canvas.locator(".djs-connection")).toHaveCount(2);
  await page.getByRole("button",{name:"Annulla modifica",exact:true}).click();await expect(node("LaneB")).toBeVisible();await expect(canvas.locator(".djs-connection")).toHaveCount(2);
  await page.getByRole("button",{name:"Salva",exact:true}).click();
  await info.attach("collaboration.xml",{body:Buffer.from(saved),contentType:"application/xml"});
  expect(errors).toEqual([]);
});

for (const width of [1440,1920]) test("local connection control previews, clicks, drags and cancels at "+width,async({page})=>{
  await page.setViewportSize({width,height:1000});const errors:string[]=[];page.on("pageerror",error=>errors.push(error.message));
  await page.goto(canvasView);const canvas=page.locator(".process-bpmn-canvas"),shell=page.locator(".process-bpmn-shell"),task=(id:string)=>canvas.locator('.djs-element[data-element-id="'+id+'"]').first();
  await expect(task("Task_1")).toBeVisible();await task("Task_1").click();await page.getByRole("button",{name:"Centra e adatta diagramma",exact:true}).click();
  const control=page.getByRole("button",{name:"Collega elemento",exact:true});await expect(control).toBeVisible();
  await expect.poll(async()=>{const a=(await control.boundingBox())!,b=(await task("Task_1").locator(".djs-visual > rect").first().boundingBox())!;return Math.abs(a.x-b.x-b.width);},{timeout:3000}).toBeLessThan(40);
  for(const label of ["Ingrandisci","Riduci"]) {
    await page.getByRole("button",{name:label,exact:true}).click();
    await expect.poll(async()=>{const a=(await control.boundingBox())!,b=(await task("Task_1").locator(".djs-visual > rect").first().boundingBox())!;return Math.abs(a.x-b.x-b.width);}).toBeLessThan(40);
  }
  await page.getByRole("button",{name:"Chiudi ispettore",exact:true}).click();
  await expect(control).toHaveCount(0);await task("Task_1").click();
  await expect.poll(async()=>{const a=(await control.boundingBox())!,b=(await task("Task_1").locator(".djs-visual > rect").first().boundingBox())!;return Math.abs(a.x-b.x-b.width);}).toBeLessThan(40);
  await control.click();await expect(shell).toHaveAttribute("data-connecting","true");
  const target=(await task("Task_2").boundingBox())!;await page.mouse.move(target.x+target.width/2,target.y+target.height/2,{steps:10});
  await expect(canvas.locator(".djs-dragger")).toBeVisible();await expect(task("Task_2")).toHaveClass(/connect-ok/);
  await page.keyboard.press("Escape");await expect(canvas.locator(".djs-dragger")).toHaveCount(0);await expect(canvas.locator(".djs-connection")).toHaveCount(17);await expect(task("Task_1")).toHaveClass(/selected/);
  await control.click();await page.mouse.move(target.x+target.width/2,target.y+target.height/2,{steps:10});await page.mouse.click(target.x+target.width/2,target.y+target.height/2);
  await expect(canvas.locator(".djs-connection")).toHaveCount(18);
  await page.getByRole("button",{name:"Annulla modifica",exact:true}).click();await expect(canvas.locator(".djs-connection")).toHaveCount(17);
  await task("Task_1").click();const from=(await control.boundingBox())!,destination=(await task("Task_3").boundingBox())!;
  await page.mouse.move(from.x+from.width/2,from.y+from.height/2);await page.mouse.down();await page.mouse.move(destination.x+destination.width/2,destination.y+destination.height/2,{steps:15});
  await expect(canvas.locator(".djs-dragger")).toBeVisible();await page.mouse.up();await expect(canvas.locator(".djs-connection")).toHaveCount(18);
  const connection=canvas.locator('.djs-connection[data-element-id^="SequenceFlow_"] .djs-visual > path').first();
  const end=await connection.evaluate(path=>{const p=path as SVGPathElement,point=p.getPointAtLength(p.getTotalLength()),matrix=p.getScreenCTM()!;return{x:point.x*matrix.a+point.y*matrix.c+matrix.e,y:point.x*matrix.b+point.y*matrix.d+matrix.f};});
  const bounds=(await task("Task_3").locator(".djs-visual > rect").first().boundingBox())!;
  expect(Math.min(Math.abs(end.x-bounds.x),Math.abs(end.x-bounds.x-bounds.width),Math.abs(end.y-bounds.y),Math.abs(end.y-bounds.y-bounds.height))).toBeLessThan(2);
  expect(errors).toEqual([]);
});

test.describe("touch connection gestures",()=>{
  test.use({hasTouch:true,isMobile:true,viewport:{width:390,height:844}});
  test("tap connects two elements and the cancel action restores selection",async({page})=>{
    await page.goto(canvasView);const canvas=page.locator(".process-bpmn-canvas"),task=canvas.locator('[data-element-id="Task_1"]').first();
    await expect(task).toBeVisible();await task.tap();const control=page.getByRole("button",{name:"Collega elemento",exact:true});await expect(control).toBeVisible();await control.tap();
    await expect(page.locator(".process-bpmn-shell")).toHaveAttribute("data-connecting","true");
    await page.getByRole("button",{name:"Annulla collegamento",exact:true}).tap();await expect(task).toHaveClass(/selected/);await expect(canvas.locator(".djs-connection")).toHaveCount(17);
    await control.tap();await canvas.locator('[data-element-id="Task_3"]').first().tap();await expect(canvas.locator(".djs-connection")).toHaveCount(18);
  });
});

test("editing an endpoint keeps the arrow on the target boundary and undo restores the attachment",async({page})=>{
  await page.setViewportSize({width:1600,height:1000});let saved=xml;
  const source=xml.replace('<di:waypoint x="240" y="125" /><di:waypoint x="290" y="125" />','<di:waypoint x="160" y="125"/><di:waypoint x="270" y="125"/><di:waypoint x="270" y="260"/><di:waypoint x="370" y="260"/><di:waypoint x="370" y="125"/>');
  saved=source;const errors:string[]=[];page.on("pageerror",e=>errors.push(e.message));
  await page.route("**/v1/workspace/bpmn-models/layout-model",async route=>{if(route.request().method()==="PUT")saved=route.request().postDataJSON().xml;await route.fulfill({headers:{"access-control-allow-origin":"*","access-control-allow-methods":"GET, PUT, OPTIONS","access-control-allow-headers":"Content-Type"},json:{id:"layout-model",name:"Connections",process_id:"layout-process",xml:saved,version_id:1}});});
  await page.goto(canvasView);const canvas=page.locator(".process-bpmn-canvas"),path=canvas.locator('.djs-connection[data-element-id="Flow_0"] .djs-visual > path').first();
  await expect(path).toBeVisible();await expect(page.getByRole("button",{name:"Salva",exact:true})).toBeDisabled();
  const point=async(fraction:number)=>path.evaluate((node,f)=>{const p=node as SVGPathElement,at=p.getPointAtLength(p.getTotalLength()*f),m=p.getScreenCTM()!;return{x:at.x*m.a+at.y*m.c+m.e,y:at.x*m.b+at.y*m.d+m.f};},fraction);
  const originalPath=await path.getAttribute("d"),unrelated=canvas.locator('.djs-shape[data-element-id="Task_18"]').first(),unrelatedBox=(await unrelated.boundingBox())!;
  await page.mouse.move(unrelatedBox.x+40,unrelatedBox.y+35);await page.mouse.down();await page.mouse.move(unrelatedBox.x+60,unrelatedBox.y+70,{steps:10});await page.mouse.up();
  await expect(path).toHaveAttribute("d",originalPath!);await page.getByRole("button",{name:"Annulla modifica",exact:true}).click();await expect(page.getByRole("button",{name:"Salva",exact:true})).toBeDisabled();
  const p=await point(.5);await page.mouse.click(p.x,p.y);
  await page.getByRole("button",{name:"Centra e adatta diagramma",exact:true}).click();
  await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));
  const start=await point(1),task=canvas.locator('.djs-shape[data-element-id="Task_3"]').first(),box=(await task.boundingBox())!;
  await page.mouse.move(start.x,start.y);await page.mouse.down();await page.mouse.move(box.x+box.width/2,box.y+box.height/2,{steps:15});await page.mouse.up();
  await expect(page.getByRole("button",{name:"Salva",exact:true})).toBeEnabled({timeout:5000});await page.getByRole("button",{name:"Salva",exact:true}).click();
  expect(await page.evaluate(s=>new DOMParser().parseFromString(s,"application/xml").querySelector('[id="Flow_0"]')!.getAttribute("targetRef"),saved)).toBe("Task_3");
  const end=await point(1),bounds=(await task.locator(".djs-visual > rect").first().boundingBox())!;
  expect(Math.min(Math.abs(end.x-bounds.x),Math.abs(end.x-bounds.x-bounds.width),Math.abs(end.y-bounds.y),Math.abs(end.y-bounds.y-bounds.height))).toBeLessThan(2);
  await page.getByRole("button",{name:"Annulla modifica",exact:true}).click();await page.getByRole("button",{name:"Salva",exact:true}).click();
  expect(await page.evaluate(s=>new DOMParser().parseFromString(s,"application/xml").querySelector('[id="Flow_0"]')!.getAttribute("targetRef"),saved)).toBe("Task_2");
  await expect(path).toHaveAttribute("d",originalPath!);
  expect(errors).toEqual([]);
});


test("large diagrams keep connection gestures reversible across 500 activities",async({page},info)=>{
  await page.setViewportSize({width:1600,height:1000});
  const nodes=Array.from({length:500},(_,i)=>({id:"Scale_"+i,x:80+(i%25)*180,y:80+Math.floor(i/25)*110}));
  const source='<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" targetNamespace="urn:scale"><bpmn:process id="Scale">'+nodes.map(n=>'<bpmn:task id="'+n.id+'" name="Attività '+n.id+'"/>').join('')+'</bpmn:process><bpmndi:BPMNDiagram id="diagram"><bpmndi:BPMNPlane id="plane" bpmnElement="Scale">'+nodes.map(n=>'<bpmndi:BPMNShape id="'+n.id+'_di" bpmnElement="'+n.id+'"><dc:Bounds x="'+n.x+'" y="'+n.y+'" width="120" height="64"/></bpmndi:BPMNShape>').join('')+'</bpmndi:BPMNPlane></bpmndi:BPMNDiagram></bpmn:definitions>';
  const errors:string[]=[];page.on("pageerror",error=>errors.push(error.message));
  await page.route("**/v1/workspace/bpmn-models/layout-model",route=>route.fulfill({json:{id:"layout-model",process_id:"layout-process",name:"Synthetic scale",xml:source,version_id:1}}));
  await page.goto(canvasView);const canvas=page.locator(".process-bpmn-canvas"),node=(id:string)=>canvas.locator('.djs-shape[data-element-id="'+id+'"]').first();
  await expect(canvas.locator('.djs-shape[data-delir-type="bpmn:Task"]')).toHaveCount(500);
  await node("Scale_0").click();await page.getByRole("button",{name:"Centra e adatta diagramma",exact:true}).click();
  const before=Date.now();await page.getByRole("button",{name:"Collega elemento",exact:true}).click();const target=(await node("Scale_2").boundingBox())!;
  await page.mouse.move(target.x+target.width/2,target.y+target.height/2,{steps:20});await expect(node("Scale_2")).toHaveClass(/connect-ok/);await expect(canvas.locator(".djs-dragger")).toBeVisible();
  await info.attach("gesture-timing.json",{body:Buffer.from(JSON.stringify({activities:500,previewGestureWallMs:Date.now()-before,note:"Includes Playwright transport; observation, not a frame-rate benchmark."})),contentType:"application/json"});
  await page.mouse.click(target.x+target.width/2,target.y+target.height/2);await expect(canvas.locator(".djs-connection")).toHaveCount(1);await page.getByRole("button",{name:"Annulla modifica",exact:true}).click();await expect(canvas.locator(".djs-connection")).toHaveCount(0);await expect(page.getByRole("button",{name:"Salva",exact:true})).toBeDisabled();expect(errors).toEqual([]);
});


for (const touch of [false,true]) test.describe("container resize grips "+(touch?"touch":"mouse"),()=>{
  test.use({hasTouch:touch,isMobile:touch,viewport:{width:1600,height:1000}});
  test("stay discreet at every zoom and preserve resize undo",async({page},info)=>{
    const source=readFileSync(join(process.cwd(),"docs/design/proofs/canvas-connection-2026-11-04/collaboration.xml"),"utf8");let saved=source;
    const errors:string[]=[];page.on("pageerror",error=>errors.push(error.message));
    await page.route("**/v1/workspace/bpmn-models/layout-model",async route=>{if(route.request().method()==="PUT")saved=route.request().postDataJSON().xml;await route.fulfill({headers:{"access-control-allow-origin":"*","access-control-allow-methods":"GET, PUT, OPTIONS","access-control-allow-headers":"Content-Type"},json:{id:"layout-model",process_id:"layout-process",name:"Container resize",xml:saved,version_id:1}});});
    await page.goto(canvasView);const canvas=page.locator(".process-bpmn-canvas"),lane=canvas.locator('.djs-shape[data-element-id="LaneB"]').first();
    await expect(lane).toBeVisible();await lane.click({position:{x:8,y:40}});
    const handles=canvas.locator('.delir-resizer[data-resize-element="LaneB"]');await expect(handles).toHaveCount(8);
    await expect(handles.locator("circle.djs-resizer-visual")).toHaveCount(4);
    const hitStyle=await handles.first().locator(".djs-resizer-hit").evaluate(node=>({fill:getComputedStyle(node).fill,stroke:getComputedStyle(node).stroke}));expect(hitStyle).toEqual({fill:"none",stroke:"none"});
    await page.screenshot({path:info.outputPath("lane-selected.png")});
    const gripPixels=Math.round((await handles.locator("circle.djs-resizer-visual").first().boundingBox())!.width);expect(gripPixels).toBeGreaterThanOrEqual(7);expect(gripPixels).toBeLessThanOrEqual(9);
    for(const zoom of [50,100,200]) {
      await page.getByRole("button",{name:/^Zoom \d+%$/}).click();await page.getByRole("menuitem",{name:zoom+"%",exact:true}).click();
      await expect.poll(async()=>Math.round((await handles.locator("circle.djs-resizer-visual").first().boundingBox())!.width)).toBe(gripPixels);
      expect(Math.round(await handles.first().locator(".djs-resizer-hit").evaluate(node=>{const el=node as SVGGraphicsElement,matrix=el.getScreenCTM()!;return el.getBBox().width*Math.hypot(matrix.a,matrix.b);}))).toBe(touch?44:24);
    }
    await page.getByRole("button",{name:"Centra e adatta diagramma",exact:true}).click();
    await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));
    const body=lane.locator(".djs-visual > rect").first(),before=(await body.boundingBox())!,grip=(await handles.filter({has:page.locator("rect.djs-resizer-visual")}).filter({hasNot:page.locator("circle")}).count());expect(grip).toBe(4);
    const handle=canvas.locator('.delir-resizer.djs-resizer-se[data-resize-element="LaneB"] .djs-resizer-hit'),start=(await handle.boundingBox())!;
    await page.mouse.move(start.x+start.width/2,start.y+start.height/2);await page.mouse.down();await page.mouse.move(start.x+start.width/2+50,start.y+start.height/2+35,{steps:15});await page.mouse.up();
    await expect.poll(async()=>(await body.boundingBox())!.width).toBeGreaterThan(before.width+20);
    await page.getByRole("button",{name:"Annulla modifica",exact:true}).click();await expect.poll(async()=>Math.round((await body.boundingBox())!.width)).toBe(Math.round(before.width));await expect(page.getByRole("button",{name:"Salva",exact:true})).toBeDisabled();expect(saved).toBe(source);expect(errors).toEqual([]);
  });
});


test("lanes without a participant support direct insertion, removal and exact undo",async({page},info)=>{
  await page.setViewportSize({width:1600,height:1000});
  const source='<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" targetNamespace="urn:lane-process"><bpmn:process id="Process"><bpmn:laneSet id="Roles"><bpmn:lane id="Role" name="Operations"><bpmn:flowNodeRef>Work</bpmn:flowNodeRef></bpmn:lane></bpmn:laneSet><bpmn:task id="Work" name="Verifica richiesta"/></bpmn:process><bpmndi:BPMNDiagram id="Diagram"><bpmndi:BPMNPlane id="Plane" bpmnElement="Process"><bpmndi:BPMNShape id="Role_di" bpmnElement="Role"><dc:Bounds x="100" y="100" width="700" height="300"/></bpmndi:BPMNShape><bpmndi:BPMNShape id="Work_di" bpmnElement="Work"><dc:Bounds x="230" y="170" width="160" height="88"/></bpmndi:BPMNShape></bpmndi:BPMNPlane></bpmndi:BPMNDiagram></bpmn:definitions>';
  let saved=source;const errors:string[]=[];page.on("pageerror",error=>errors.push(error.message));
  await page.route("**/v1/workspace/bpmn-models/layout-model",async route=>{if(route.request().method()==="PUT")saved=route.request().postDataJSON().xml;await route.fulfill({headers:{"access-control-allow-origin":"*","access-control-allow-methods":"GET, PUT, OPTIONS","access-control-allow-headers":"Content-Type"},json:{id:"layout-model",process_id:"layout-process",name:"Unpooled lanes",xml:saved,version_id:1}});});
  await page.goto(canvasView);const canvas=page.locator(".process-bpmn-canvas"),lane=canvas.locator('.djs-shape[data-element-id="Role"]').first();await expect(lane).toBeVisible();await lane.click({position:{x:8,y:40}});
  const actions=page.getByRole("group",{name:"Azioni della selezione"});await expect(page.getByRole("button",{name:"Gestisci lane",exact:true})).toHaveCount(0);expect((await actions.boundingBox())!.width).toBeLessThan(180);await expect(actions.locator(".process-selection-label")).toHaveCount(0);
  await page.screenshot({path:info.outputPath("unpooled-lane-selected.png")});
  for(const label of ["Aggiungi lane sotto","Aggiungi lane sopra"]) {
    if(label === "Aggiungi lane sotto"){await lane.click({button:"right",position:{x:8,y:40}});await page.getByRole("menu",{name:"Azioni della selezione"}).getByRole("menuitem",{name:label,exact:true}).click();}else await page.getByRole("button",{name:label,exact:true}).click();await expect(canvas.locator('.djs-shape[data-delir-type="bpmn:Lane"]')).toHaveCount(2);
    await page.getByRole("button",{name:"Salva",exact:true}).click();
    const graph=await page.evaluate(xml=>{const doc=new DOMParser().parseFromString(xml,"application/xml");return{lanes:doc.getElementsByTagNameNS("*","lane").length,pools:doc.getElementsByTagNameNS("*","participant").length,reference:doc.getElementsByTagNameNS("*","flowNodeRef")[0]?.textContent};},saved);expect(graph).toEqual({lanes:2,pools:0,reference:"Work"});if(label === "Aggiungi lane sotto")await info.attach("unpooled-lanes.xml",{body:Buffer.from(saved),contentType:"application/xml"});
    await page.getByRole("button",{name:"Annulla modifica",exact:true}).click();await page.getByRole("button",{name:"Salva",exact:true}).click();expect(saved).toBe(source);
  }
  for(const [label,count] of [["Dividi in due lane",2],["Dividi in tre lane",3]] as const) {
    await lane.click({position:{x:8,y:40}});await page.getByRole("button",{name:"Altre azioni",exact:true}).click();await page.getByRole("menuitem",{name:label,exact:true}).click();await expect(canvas.locator('.djs-shape[data-delir-type="bpmn:Lane"]')).toHaveCount(count);
    const placement=await canvas.locator('.djs-shape[data-element-id="Work"]').evaluate(el=>{const parent=el.closest('.djs-children')!.parentElement!.querySelector(':scope > .djs-element > .djs-visual > rect')!,child=el.querySelector('.djs-visual > rect')!;const a=child.getBoundingClientRect(),b=parent.getBoundingClientRect();return{top:a.top,bottom:a.bottom,parentTop:b.top,parentBottom:b.bottom};});expect(placement.top).toBeGreaterThan(placement.parentTop);expect(placement.bottom).toBeLessThan(placement.parentBottom);
    await page.getByRole("button",{name:"Salva",exact:true}).click();await info.attach("split-"+count+".xml",{body:Buffer.from(saved),contentType:"application/xml"});await page.getByRole("button",{name:"Annulla modifica",exact:true}).click();await page.getByRole("button",{name:"Salva",exact:true}).click();expect(saved).toBe(source);
  }
  await lane.click({position:{x:8,y:40}});await page.getByRole("button",{name:"Altre azioni",exact:true}).click();await page.getByRole("menuitem",{name:"Rimuovi lane, mantieni le attività",exact:true}).click();await expect(lane).toHaveCount(0);await expect(canvas.locator('.djs-shape[data-element-id="Work"]')).toBeVisible();await page.getByRole("button",{name:"Annulla modifica",exact:true}).click();await expect(lane).toBeVisible();await expect(page.getByRole("button",{name:"Salva",exact:true})).toBeDisabled();expect(errors).toEqual([]);
});


test("right click opens working object actions while right drag only pans",async({page},info)=>{
  await page.setViewportSize({width:1600,height:1000});await page.goto(canvasView);const canvas=page.locator(".process-bpmn-canvas"),task=canvas.locator('.djs-shape[data-element-id="Task_1"]').first(),viewport=canvas.locator("g.viewport").first();await expect(task).toBeVisible();
  await task.click({button:"right"});const menu=page.getByRole("menu",{name:"Azioni della selezione"});await expect(menu).toBeVisible();await expect(task).toHaveClass(/selected/);await page.screenshot({path:info.outputPath("right-click-object.png")});
  await menu.getByRole("menuitem",{name:"Collega elemento",exact:true}).click();await expect(page.locator(".process-bpmn-shell")).toHaveAttribute("data-connecting","true");await canvas.locator('.djs-shape[data-element-id="Task_3"]').first().click();await expect(canvas.locator(".djs-connection")).toHaveCount(18);await page.getByRole("button",{name:"Annulla modifica",exact:true}).click();await expect(canvas.locator(".djs-connection")).toHaveCount(17);
  await task.click({button:"right"});await menu.getByRole("menuitem",{name:"Cambia tipo",exact:true}).hover();await page.getByRole("menuitem",{name:"Attività di servizio",exact:true}).click();await expect(task).toHaveAttribute("data-delir-type","bpmn:ServiceTask");await page.getByRole("button",{name:"Annulla modifica",exact:true}).click();await expect(task).toHaveAttribute("data-delir-type","bpmn:UserTask");
  await task.click({button:"right"});await page.keyboard.press("Escape");await expect(menu).toHaveCount(0);
  await canvas.locator(".djs-container > svg").focus();await page.keyboard.press("Shift+F10");await expect(menu).toBeVisible();await expect(task).toHaveClass(/selected/);await page.keyboard.press("Escape");
  const box=(await canvas.boundingBox())!,x=box.x+box.width/2,y=box.y+90,before=await viewport.getAttribute("transform");await page.mouse.move(x,y);await page.mouse.down({button:"right"});await page.mouse.move(x+80,y+45,{steps:12});await page.mouse.up({button:"right"});await expect(viewport).not.toHaveAttribute("transform",before!);await expect(menu).toHaveCount(0);
  await page.mouse.click(x,y,{button:"right"});await expect(menu).toBeVisible();await menu.getByRole("menuitem",{name:"Seleziona tutto",exact:true}).click();await expect(page.getByRole("button",{name:"35 elementi selezionati",exact:true})).toBeVisible();await expect(page.getByRole("button",{name:"Salva",exact:true})).toBeDisabled();
});
