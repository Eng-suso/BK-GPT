import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const studio = "/projects/simulation-ui-project/processes/simulation-ui-process/simulation";
const xml = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_ui" targetNamespace="https://example.test/simulation">
<bpmn:process id="Process_ui" isExecutable="false"><bpmn:startEvent id="Start" /><bpmn:task id="A" name="Verifica documentazione" /><bpmn:task id="B" name="Approva richiesta" /><bpmn:endEvent id="End" /><bpmn:sequenceFlow id="F1" sourceRef="Start" targetRef="A" /><bpmn:sequenceFlow id="F2" sourceRef="A" targetRef="B" /><bpmn:sequenceFlow id="F3" sourceRef="B" targetRef="End" /></bpmn:process>
<bpmndi:BPMNDiagram id="Diagram_ui"><bpmndi:BPMNPlane id="Plane_ui" bpmnElement="Process_ui"><bpmndi:BPMNShape id="Start_di" bpmnElement="Start"><dc:Bounds x="80" y="120" width="36" height="36" /></bpmndi:BPMNShape><bpmndi:BPMNShape id="A_di" bpmnElement="A"><dc:Bounds x="180" y="98" width="140" height="80" /></bpmndi:BPMNShape><bpmndi:BPMNShape id="B_di" bpmnElement="B"><dc:Bounds x="400" y="98" width="140" height="80" /></bpmndi:BPMNShape><bpmndi:BPMNShape id="End_di" bpmnElement="End"><dc:Bounds x="610" y="120" width="36" height="36" /></bpmndi:BPMNShape><bpmndi:BPMNEdge id="F1_di" bpmnElement="F1"><di:waypoint x="116" y="138" /><di:waypoint x="180" y="138" /></bpmndi:BPMNEdge><bpmndi:BPMNEdge id="F2_di" bpmnElement="F2"><di:waypoint x="320" y="138" /><di:waypoint x="400" y="138" /></bpmndi:BPMNEdge><bpmndi:BPMNEdge id="F3_di" bpmnElement="F3"><di:waypoint x="540" y="138" /><di:waypoint x="610" y="138" /></bpmndi:BPMNEdge></bpmndi:BPMNPlane></bpmndi:BPMNDiagram></bpmn:definitions>`;

const run = {
  id: 42, bpmn_model_id: "simulation-ui-model", process_id: "simulation-ui-process", scenario_name: "AS-IS · Gestione richieste",
  engine: "prosimos", status: "completed", request: {}, scenario: {}, result: {}, outputs: [], error: null,
  created_at: "2026-01-05T09:00:00Z", completed_at: "2026-01-05T09:01:00Z",
  summary: { casesCompleted: 3, cycle: { avg: 267, p50: 250, p90: 380, p95: 390 }, waiting: { avg: 90, p95: 140, share: 0.4 },
    processing: { avg: 177 }, cost: { total: 999, perCase: 333 }, throughputPerHour: 27,
    byActivity: [{ el: "A", name: "Verifica documentazione", wait: { avg: 90 } }, { el: "B", name: "Approva richiesta", wait: { avg: 40 } }],
    byResource: [], bottleneck: { el: "A", name: "Verifica documentazione" } },
};

const payload = {
  schemaVersion: 1, meta: { start: "2026-01-05T09:00:00Z", durationSec: 400, totalCases: 3, sampledCases: 3, bucketSec: 100 },
  elements: { A: { name: "Verifica documentazione" }, B: { name: "Approva richiesta" } },
  cases: [
    { id: "0", cycleSec: 150, events: [{ el: "A", enable: 0, start: 0, end: 50, res: "Analisti" }, { el: "B", enable: 50, start: 100, end: 150, res: "Approvatori" }] },
    { id: "1", cycleSec: 250, events: [{ el: "A", enable: 0, start: 50, end: 120, res: "Analisti" }, { el: "B", enable: 120, start: 200, end: 250, res: "Approvatori" }] },
    { id: "2", cycleSec: 400, events: [{ el: "A", enable: 0, start: 200, end: 400, res: "Analisti" }] },
  ],
  series: { t: [0, 100, 200, 300, 400], byElement: {
    A: { active: [1, 1, 1, 1, 0], queued: [2, 1, 0, 0, 0], done: [0, 1, 2, 2, 3] },
    B: { active: [0, 1, 1, 0, 0], queued: [0, 0, 0, 0, 0], done: [0, 0, 1, 2, 2] },
  }, byResource: { Analisti: { busy: [1, 1, 0.5, 0.5, 0] }, Approvatori: { busy: [0, 1, 1, 0, 0] } },
    global: { wip: [3, 2, 2, 1, 0], queued: [2, 1, 0, 0, 0], done: [0, 1, 1, 2, 3], throughputPerHour: [0, 36, 0, 36, 36], costAccrued: [0, 10, 20, 30, 999], avgCycleSec: [0, 150, 150, 200, 267] } },
  flows: { F2: { count: 2, attributed: true } },
};

async function fixture(page: Page): Promise<void> {
  await page.addInitScript(() => { Object.assign(window, { DELIR_API_BASE: "http://127.0.0.1:8000" }); localStorage.setItem("delir-language", "it"); });
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown = [];
    if (path === "/v1/workspace/projects/simulation-ui-project") data = {
      id: "simulation-ui-project", client_id: "demo", client: "Azienda Demo", name: "Efficienza operativa", phase: "AS-IS", status: "In corso", progress: 50, processes: 1,
      next_step: "Confrontare gli scenari", milestones: [], open_issues: [], deliverables: [],
      process_items: [{ id: "simulation-ui-process", project_id: "simulation-ui-project", bpmn_model_id: "simulation-ui-model", name: "Gestione richieste e approvazioni", stage: "AS-IS", status: "Da validare", owner: "Team Operations", readiness: 85 }],
    };
    else if (path.endsWith("/simulation-runs")) data = [run, { ...run, id: 43, scenario_name: "TO-BE · Capacità aggiuntiva" }];
    else if (path.endsWith("/replay")) data = { run_id: Number(path.split("/").at(-2)), schema_version: 1, replay: payload };
    else if (path.endsWith("/simulation-template")) data = { tasks: [{ element_id: "A", name: "Verifica documentazione", type: "task" }, { element_id: "B", name: "Approva richiesta", type: "task" }], gateways: [] };
    else if (path.endsWith("/simulation-provenance")) data = { has_discovery: false, elements: [] };
    else if (path.endsWith("/simulation-ui-model")) data = { id: "simulation-ui-model", process_id: "simulation-ui-process", name: "Modello demo", xml };
    await route.fulfill({ json: data });
  });
}

async function seek(page: Page, value: number): Promise<void> {
  await page.locator('input[type="range"]').evaluate((element, value) => {
    const input = element as HTMLInputElement;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, String(value));
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }, value);
  await expect(page.locator('input[type="range"]')).toHaveValue(String(value));
}

test.beforeEach(async ({ page }) => { await fixture(page); });

test("dashboard and process share the clock and never label final KPIs as current", async ({ page }) => {
  await page.goto(`${studio}/dashboard/42`);
  await expect(page.getByRole("heading", { name: "Dashboard del processo" })).toBeVisible();
  const cycle = page.locator(".sim-kpi").filter({ hasText: "Attraversamento medio" });
  await expect(cycle).toContainText("—");
  await seek(page, 200);
  await expect(page.locator(".sim-kpi").filter({ hasText: "Costo accumulato" })).toContainText("20");
  const costWidget = page.locator('[data-widget-id="default-4"]');
  await costWidget.getByText("Visualizza dati", { exact: true }).click();
  await expect(costWidget.locator("tbody tr")).toHaveCount(3);
  await expect(costWidget.locator("tbody")).not.toContainText("999");
  await page.locator(".sim-workspace-nav").getByRole("button", { name: "Processo", exact: true }).click();
  await expect(page.locator('input[type="range"]')).toHaveValue("200");
  await page.locator(".sim-workspace-nav").getByRole("button", { name: "Dashboard", exact: true }).click();
  await expect(page.locator('input[type="range"]')).toHaveValue("200");
  await page.locator(".sim-final-results > summary").click();
  await expect(page.locator(".sim-final-results")).toContainText("333");
  await page.getByRole("combobox", { name: "Scegli una run" }).click();
  await page.getByRole("option", { name: /TO-BE/ }).click();
  await expect(page.locator('input[type="range"]')).toHaveValue("0");
});

test("widget edits, duplication, keyboard reordering and sections persist after reload", async ({ page }) => {
  await page.goto(`${studio}/dashboard/42`);
  await page.getByRole("button", { name: "Modifica dashboard", exact: true }).click();
  await page.getByRole("button", { name: "Configura Costo accumulato", exact: true }).click();
  const inspector = page.getByRole("complementary", { name: "Impostazioni widget" });
  await expect(inspector.getByLabel("Titolo", { exact: true })).toBeFocused();
  await inspector.getByLabel("Titolo", { exact: true }).fill("Costi del run");
  await inspector.getByLabel("Larghezza").selectOption("full");
  await inspector.getByRole("button", { name: "Duplica widget", exact: true }).click();
  await inspector.getByLabel("Titolo", { exact: true }).fill("Costi confronto");
  await inspector.getByRole("button", { name: "Sposta widget prima" }).click();
  await page.getByRole("button", { name: "Aggiungi sezione", exact: true }).click();
  await inspector.getByLabel("Sezione", { exact: true }).selectOption({ label: "Sezione 2" });
  await page.getByRole("button", { name: "Salva layout", exact: true }).click();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Costi del run", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Costi confronto", exact: true })).toBeVisible();
  await expect(page.locator(".sim-widget-section")).toHaveCount(2);
  await expect(page.locator(".sim-widget").filter({ hasText: "Costi del run" })).toHaveClass(/is-full/);
});

test("Markdown formulas follow the playhead and invalid input remains editable", async ({ page }) => {
  await page.goto(`${studio}/dashboard/42`);
  await page.getByRole("button", { name: "Aggiungi widget", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: /Testo e Markdown/ }).click();
  await page.getByLabel("Testo Markdown", { exact: true }).fill("Casi conclusi: **${metric}**");
  await seek(page, 300);
  await expect(page.locator(".sim-note strong")).toHaveText("2");
  await page.getByLabel("Espressione metrica", { exact: true }).fill("metric * 2");
  await expect(page.locator(".sim-note strong")).toHaveText("4");
  await page.getByLabel("Espressione metrica", { exact: true }).fill("metric / 0");
  await expect(page.getByLabel("Espressione metrica", { exact: true })).toHaveAttribute("aria-invalid", "true");
  await page.getByLabel("Espressione metrica", { exact: true }).fill("");
  await page.getByLabel("Testo Markdown", { exact: true }).fill("${metric / 0}");
  await expect(page.getByLabel("Testo Markdown", { exact: true })).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByLabel("Testo Markdown", { exact: true })).toHaveValue("${metric / 0}");
  await page.getByLabel("Testo Markdown", { exact: true }).fill("**Nota operativa**");
  await expect(page.getByLabel("Testo Markdown", { exact: true })).toHaveAttribute("aria-invalid", "false");
  await page.getByRole("button", { name: "Annulla", exact: true }).click();
  await expect(page.locator(".sim-widget")).toHaveCount(6);
});

test("activity filters have explicit scope and can be cleared", async ({ page }) => {
  await page.goto(`${studio}/dashboard/42`);
  await page.getByLabel("Attività", { exact: true }).selectOption("B");
  await expect(page.locator('[data-widget-id="default-2"]')).toContainText("Attività selezionata");
  await expect(page.locator(".sim-kpi").first()).toContainText("Tutto il processo");
  await page.getByRole("button", { name: "Rimuovi filtro", exact: true }).click();
  await expect(page.getByLabel("Attività", { exact: true })).toHaveValue("all");
});

test("corrupt saved layouts and blocked storage fail visibly without losing drafts", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("delir:simulation:dashboard:simulation-ui-project:simulation-ui-process", '{"version":99}'));
  await page.goto(`${studio}/dashboard/42`);
  await expect(page.getByRole("alert")).toContainText("layout salvato");
  await page.getByRole("button", { name: "Modifica dashboard", exact: true }).click();
  await page.getByRole("button", { name: "Configura Costo accumulato", exact: true }).click();
  await page.getByLabel("Titolo", { exact: true }).fill("Bozza da conservare");
  await page.evaluate(() => { Storage.prototype.setItem = () => { throw new DOMException("Blocked", "QuotaExceededError"); }; });
  await page.getByRole("button", { name: "Salva layout", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("non è stato salvato");
  await expect(page.getByLabel("Titolo", { exact: true })).toHaveValue("Bozza da conservare");
});

test("dashboard is accessible and visually stable at desktop and mobile widths", async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  await page.goto(`${studio}/dashboard/42`);
  await seek(page, 300);
  await expect(page.getByRole("heading", { name: "Dashboard del processo" })).toBeVisible();
  const activeTab = page.locator('.sim-workspace-nav [aria-current="page"]');
  const activeBox = (await activeTab.boundingBox())!;
  expect(activeBox.x).toBeGreaterThanOrEqual(0);
  expect(activeBox.x + activeBox.width).toBeLessThanOrEqual(page.viewportSize()!.width + 1);
  const scan = await new AxeBuilder({ page }).include("main").withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
  expect(scan.violations).toEqual([]);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
  expect(overflow).toBe(false);
  await page.screenshot({ path: testInfo.outputPath("dashboard.png"), animations: "disabled" });
  await page.getByRole("button", { name: "Modifica dashboard", exact: true }).click();
  await page.getByRole("button", { name: "Configura Costo accumulato", exact: true }).click();
  const editScan = await new AxeBuilder({ page }).include("main").withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
  expect(editScan.violations).toEqual([]);
  await expect(page.getByLabel("Titolo", { exact: true })).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
  await page.screenshot({ path: testInfo.outputPath("dashboard-editor.png"), animations: "disabled" });
  expect(errors).toEqual([]);
});

test("canvas analytics follow the shared clock, move with the keyboard and survive replay updates", async ({ page, isMobile }, testInfo) => {
  await page.goto(`${studio}/replay/42`);
  await page.getByLabel("Attività", { exact: true }).selectOption("A");
  await page.getByRole("button", { name: "Aggiungi analisi alla tela", exact: true }).click();
  await page.getByRole("button", { name: "Chiudi dettaglio" }).click();
  const widget = page.locator("[data-canvas-widget]");
  await expect(widget).toHaveCount(1);
  await expect(widget.locator(".sim-widget-kpi strong")).toHaveText("2");
  await seek(page, 300);
  await expect(widget.locator(".sim-widget-kpi strong")).toHaveText("0");
  await widget.getByText("Elemento selezionato", { exact: true }).click();
  await widget.getByLabel("Metrica", { exact: true }).selectOption("activityDone");
  await expect(widget.locator(".sim-widget-kpi strong")).toHaveText("2");
  await widget.getByLabel("Titolo", { exact: true }).fill("Verifiche concluse");
  await widget.getByText("Elemento selezionato", { exact: true }).click();
  const handle = widget.getByRole("button", { name: "Sposta analisi sulla tela" });
  await handle.focus();
  await handle.press("ArrowLeft");
  if (!isMobile) {
    await handle.scrollIntoViewIfNeeded();
    const box = (await handle.boundingBox())!;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 30, box.y + box.height / 2 - 40, { steps: 5 });
    await page.mouse.up();
    await expect(widget).toHaveCSS("transform", "matrix(1, 0, 0, 1, 20, 70)");
  }
  const position = await widget.evaluate((element) => (element as HTMLElement).style.transform);
  await expect(handle).toBeFocused();
  await seek(page, 200);
  expect(await widget.evaluate((element) => (element as HTMLElement).style.transform)).toBe(position);
  await page.getByRole("button", { name: "Grafici", exact: true }).click();
  await expect(widget).toHaveCount(0);
  await page.getByRole("button", { name: "Grafici", exact: true }).click();
  await expect(widget).toContainText("Verifiche concluse");
  await page.reload();
  await expect(widget).toContainText("Verifiche concluse");
  expect(await widget.evaluate((element) => (element as HTMLElement).style.transform)).toBe(position);
  await seek(page, 300);
  await expect(widget.locator(".sim-widget-kpi strong")).toHaveText("2");
  const scan = await new AxeBuilder({ page }).include("main").withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
  expect(scan.violations).toEqual([]);
  await widget.scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath("canvas-analytics.png"), animations: "disabled" });
});
