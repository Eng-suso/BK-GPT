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
    else if (path.endsWith("/experiments")) data = { bottleneck_el: "A", bottleneck_name: "Verifica documentazione", factors: {}, experiments: [] };
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

async function jump(page: Page, id: string): Promise<void> {
  await page.getByLabel("Vai a un elemento…", { exact: true }).selectOption(id);
}

test.beforeEach(async ({ page }) => { await fixture(page); });

test("dashboard and process share the clock and never label final KPIs as current", async ({ page }) => {
  await page.goto(`${studio}/dashboard/42`);
  await expect(page.getByRole("heading", { name: "Processo", exact: true })).toBeVisible();
  const cycle = page.locator(".sim-kpi").filter({ hasText: "Attraversamento medio" });
  await expect(cycle).toContainText("—");
  await seek(page, 200);
  await expect(page.locator(".sim-kpi").filter({ hasText: "Costo accumulato" })).toContainText("20");
  const costWidget = page.locator('[data-widget-id="default-4"]');
  await jump(page, "default-4");
  await costWidget.getByText("Visualizza dati", { exact: true }).click();
  await expect(costWidget.locator("tbody tr")).toHaveCount(3);
  await expect(costWidget.locator("tbody")).not.toContainText("999");
  await page.locator(".sim-studio-tools").getByRole("button", { name: "Scenario", exact: true }).click();
  await expect(page.locator('input[type="range"]')).toHaveValue("200");
  await page.getByRole("button", { name: "Chiudi pannello", exact: true }).click();
  await expect(page.locator('input[type="range"]')).toHaveValue("200");
  await page.locator(".sim-final-results > summary").click();
  await expect(page.locator(".sim-final-results")).toContainText("333");
  await page.getByRole("combobox", { name: "Scegli una run" }).click();
  await page.getByRole("option", { name: /TO-BE/ }).click();
  await expect(page.locator('input[type="range"]')).toHaveValue("0");
});

test("widget edits, duplication, keyboard reordering and sections persist after reload", async ({ page }) => {
  await page.goto(`${studio}/dashboard/42`);
  await page.getByRole("button", { name: "Modifica canvas", exact: true }).click();
  await jump(page, "default-4");
  await page.getByRole("button", { name: "Configura Costo accumulato", exact: true }).click();
  const inspector = page.getByRole("complementary", { name: "Impostazioni widget" });
  await expect(inspector.getByLabel("Titolo", { exact: true })).toBeFocused();
  await inspector.getByLabel("Titolo", { exact: true }).fill("Costi del run");
  await inspector.getByLabel("Larghezza").selectOption("full");
  await expect(page.locator('[data-widget-id="default-4"]')).toHaveClass(/is-full/);
  await inspector.getByRole("button", { name: "Duplica widget", exact: true }).click();
  await inspector.getByLabel("Titolo", { exact: true }).fill("Costi confronto");
  await inspector.getByRole("button", { name: "Sposta widget prima" }).click();
  await page.getByRole("button", { name: "Aggiungi sezione", exact: true }).click();
  await inspector.getByLabel("Sezione", { exact: true }).selectOption({ label: "Sezione 2" });
  await page.getByRole("button", { name: "Salva layout", exact: true }).click();
  await expect(page.getByRole("button", { name: "Modifica canvas", exact: true })).toBeVisible();
  await page.reload();
  await page.getByLabel("Vai a un elemento…", { exact: true }).selectOption({ label: "Costi del run" });
  await expect(page.getByRole("heading", { name: "Costi del run", exact: true })).toBeVisible();
  await page.getByLabel("Vai a un elemento…", { exact: true }).selectOption({ label: "Costi confronto" });
  await expect(page.getByRole("heading", { name: "Costi confronto", exact: true })).toBeVisible();
  await expect(page.locator(".sim-widget-section")).toHaveCount(2);
  await expect(page.locator(".sim-widget").filter({ hasText: "Costi del run" })).toHaveClass(/is-full/);
});

test("Markdown formulas follow the playhead and invalid input remains editable", async ({ page }) => {
  await page.goto(`${studio}/dashboard/42`);
  await page.getByRole("button", { name: "Aggiungi widget", exact: true }).click();
  const palette = page.getByRole("complementary", { name: "Aggiungi un elemento", exact: true });
  await palette.getByRole("button", { name: "Testo", exact: true }).click();
  await palette.getByRole("button", { name: /Testo e Markdown/ }).click();
  await palette.getByRole("button", { name: "Chiudi raccolta elementi", exact: true }).click();
  await page.getByRole("button", { name: "Configura Casi conclusi", exact: true }).click();
  await page.getByLabel("Testo Markdown", { exact: true }).fill("Casi conclusi: **${metric}**");
  await page.getByLabel("Vai a un elemento…", { exact: true }).selectOption({ label: "Casi conclusi" });
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
  await page.getByLabel("Testo Markdown", { exact: true }).fill("**Nota operativa** ![Immagine](https://example.invalid/pixel.svg)");
  await expect(page.getByLabel("Testo Markdown", { exact: true })).toHaveAttribute("aria-invalid", "false");
  await expect(page.locator(".sim-note img")).toHaveCount(0);
  await expect(page.locator(".sim-note strong")).toHaveText("Nota operativa");
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
  await page.getByRole("button", { name: "Modifica canvas", exact: true }).click();
  await jump(page, "default-4");
  await page.getByRole("button", { name: "Configura Costo accumulato", exact: true }).click();
  await page.getByLabel("Titolo", { exact: true }).fill("Bozza da conservare");
  await page.evaluate(() => { Storage.prototype.setItem = () => { throw new DOMException("Blocked", "QuotaExceededError"); }; });
  await page.getByRole("button", { name: "Salva layout", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("non è stato salvato");
  await expect(page.getByLabel("Titolo", { exact: true })).toHaveValue("Bozza da conservare");
});

test("dashboard is accessible and visually stable at desktop and mobile widths", async ({ page, isMobile }, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  await page.goto(`${studio}/dashboard/42`);
  await seek(page, 300);
  await expect(page.getByRole("heading", { name: "Processo", exact: true })).toBeVisible();
  await expect(page.locator(".sim-workspace-nav")).toHaveCount(0);
  await expect(page.locator("[data-process-tile]")).toBeVisible();
  if (isMobile) expect((await page.locator(".sim-scene-viewport").boundingBox())!.height).toBeGreaterThan(220);
  await expect(page.locator('[data-widget-id="default-0"]')).toBeVisible();
  const scan = await new AxeBuilder({ page }).include("main").withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
  expect(scan.violations).toEqual([]);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
  expect(overflow).toBe(false);
  await page.screenshot({ path: testInfo.outputPath("dashboard.png"), animations: "disabled" });
  await page.getByRole("button", { name: "Modifica canvas", exact: true }).click();
  await jump(page, "default-4");
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
  const widget = page.locator("[data-canvas-widget]");
  await expect(widget).toHaveCount(1);
  await expect(widget.locator(".sim-widget-kpi strong")).toHaveText("2");
  await seek(page, 300);
  await expect(widget.locator(".sim-widget-kpi strong")).toHaveText("0");
  await widget.getByRole("button", { name: /^Configura/ }).click();
  const inspector = page.locator(".sim-studio-widget-host");
  await inspector.getByLabel("Metrica", { exact: true }).selectOption("activityDone");
  await expect(widget.locator(".sim-widget-kpi strong")).toHaveText("2");
  await inspector.getByLabel("Titolo", { exact: true }).fill("Verifiche concluse");
  await page.getByRole("button", { name: "Chiudi pannello", exact: true }).click();
  const handle = widget.getByRole("button", { name: "Sposta analisi sulla tela" });
  await handle.focus();
  await handle.press("ArrowLeft");
  if (!isMobile) {
    await handle.scrollIntoViewIfNeeded();
    const box = (await handle.boundingBox())!;
    const scale = await widget.evaluate(el => { const scene = el.closest(".sim-scene-object") as HTMLElement; return scene.getBoundingClientRect().width / scene.offsetWidth; });
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 30, box.y + box.height / 2 - 40, { steps: 5 });
    await page.mouse.up();
    const moved = await widget.evaluate(el => new DOMMatrix(getComputedStyle(el).transform).toFloat64Array().slice(12, 14));
    expect(moved[0]).toBeCloseTo(-10 + 30 / scale, 1);
    expect(moved[1]).toBeCloseTo(110 - 40 / scale, 1);
  }
  const position = await widget.evaluate(element => { const m = new DOMMatrix(getComputedStyle(element).transform); return { x: m.e, y: m.f }; });
  await expect(handle).toBeFocused();
  await seek(page, 200);
  const storedPosition = await widget.evaluate(element => { const m = new DOMMatrix(getComputedStyle(element).transform); return { x: m.e, y: m.f }; });
  expect(storedPosition.x).toBeCloseTo(position.x, 1);
  expect(storedPosition.y).toBeCloseTo(position.y, 1);
  await page.getByRole("button", { name: "Grafici", exact: true }).click();
  await expect(widget).toHaveCount(0);
  await page.getByRole("button", { name: "Grafici", exact: true }).click();
  await expect(widget).toContainText("Verifiche concluse");
  await page.reload();
  await expect(widget).toContainText("Verifiche concluse");
  const restoredPosition = await widget.evaluate(element => { const m = new DOMMatrix(getComputedStyle(element).transform); return { x: m.e, y: m.f }; });
  expect(restoredPosition.x).toBeCloseTo(position.x, 1);
  expect(restoredPosition.y).toBeCloseTo(position.y, 1);
  await seek(page, 300);
  await expect(widget.locator(".sim-widget-kpi strong")).toHaveText("2");
  const scan = await new AxeBuilder({ page }).include("main").withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
  expect(scan.violations).toEqual([]);
  await widget.scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath("canvas-analytics.png"), animations: "disabled" });
});

test("all chart types render and circular charts expose categories without hover", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  // A zero-valued first category must retain its color in the legend.
  await page.route("http://127.0.0.1:8000/**/replay", async (route) => route.fulfill({ json: {
    run_id: 42, schema_version: 1, replay: { ...payload, series: { ...payload.series, byResource: {
      Approvatori: payload.series.byResource.Approvatori, Analisti: payload.series.byResource.Analisti,
    } } },
  } }));
  await page.goto(`${studio}/dashboard/42`);
  await seek(page, 300);
  await page.getByRole("button", { name: "Modifica canvas", exact: true }).click();
  await jump(page, "default-3");
  await page.getByRole("button", { name: "Configura Occupazione delle risorse", exact: true }).click();
  const inspector = page.getByRole("complementary", { name: "Impostazioni widget" });
  const widget = page.locator('[data-widget-id="default-3"]');
  for (const kind of ["line", "area", "bar", "column", "pie", "donut", "gauge", "radial", "kpi", "table", "text"]) {
    await inspector.getByLabel("Tipo di grafico", { exact: true }).selectOption(kind);
    await expect(widget).toBeVisible();
    await expect(widget.locator(".sim-widget-empty")).toHaveCount(0);
    if (["pie", "donut", "radial"].includes(kind)) {
      await expect(widget.locator(".sim-widget-legend li")).toHaveCount(2);
      await expect(widget.locator(".sim-widget-legend")).toContainText("Analisti");
      await expect(widget.locator(".sim-widget-legend")).toContainText("50%");
      if (kind !== "radial") {
        const slice = await widget.locator(".recharts-pie-sector path").first().evaluate((element) => getComputedStyle(element).fill);
        const swatch = await widget.locator(".sim-widget-legend li").filter({ hasText: "Analisti" }).locator("span").first().evaluate((element) => getComputedStyle(element).backgroundColor);
        expect(slice).toBe(swatch);
      }
    }
    if (kind === "table") await expect(widget.locator("tbody")).toContainText("Approvatori");
  }
  await inspector.getByLabel("Tipo di grafico", { exact: true }).selectOption("donut");
  await inspector.getByText("Etichette e stile", { exact: true }).click();
  await inspector.getByLabel("Mostra etichette e categorie", { exact: true }).uncheck();
  await expect(widget.locator(".sim-widget-legend")).toHaveCount(0);
  await inspector.getByLabel("Mostra etichette e categorie", { exact: true }).check();
  await expect(widget.locator(".sim-widget-legend li")).toHaveCount(2);
  expect(errors).toEqual([]);
});


test("consultant investigates an activity through contextual tools without losing the canvas", async ({ page, isMobile }, testInfo) => {
  test.setTimeout(120_000);
  await page.goto(`${studio}/workspace/42`);
  await seek(page, 100);
  await page.getByLabel("Attività", { exact: true }).selectOption("A");
  const process = page.locator("[data-process-tile]");
  const viewer = process.locator(".djs-container");
  await expect(viewer).toBeVisible();
  await viewer.evaluate((element) => element.setAttribute("data-session-marker", "same-viewer"));
  const tools = page.locator(".sim-studio-tools");
  for (const name of ["Scenario", "Risultati", "Heatmap", "Confronto", "Insight"]) {
    await tools.getByRole("button", { name, exact: true }).click();
    if (name === "Confronto") await expect(page.locator(".sim-comparison-bar")).toBeVisible();
    else await expect(page.getByRole("complementary", { name: "Dettagli e impostazioni", exact: true })).toBeVisible();
    await expect(viewer).toHaveAttribute("data-session-marker", "same-viewer");
    if (name === "Scenario") await expect(page.locator('input[type="range"]')).toHaveValue("100");
    else await expect(page.locator(".sim-final-transport")).toBeVisible();
    await expect(page.getByLabel("Attività", { exact: true })).toHaveValue("A");
    await expect(page.locator("[data-process-tile]")).toHaveCount(1);
    await expect(page.locator(".sim-kpi")).toHaveCount(6);
    if (name === "Insight") {
      await page.locator(".sim-current-insights > summary").click();
      await expect(page.locator(".sim-current-insights")).toContainText("Verifica documentazione");
    }
    if (name !== "Confronto") {
      await page.getByRole("button", { name: "Chiudi pannello", exact: true }).click();
      await expect(page.locator(".sim-studio-dock")).toBeHidden();
      await expect(tools.getByRole("button", { name, exact: true })).toBeFocused();
    }
    await tools.getByRole("button", { name: "Osserva", exact: true }).click();
    await expect(page.locator('input[type="range"]')).toHaveValue("100");
  }
  await expect(process.locator(".sim-token")).not.toHaveCount(0);
  if (!isMobile) await page.setViewportSize({ width: 1600, height: 1000 });
  await page.locator(".sim-dashboard-workspace").evaluate((element) => { element.scrollTop = 0; });
  await page.screenshot({ path: testInfo.outputPath("unified-workspace.png"), animations: "disabled" });
  await tools.getByRole("button", { name: "Heatmap", exact: true }).click();
  await expect(page.locator(".sim-studio-dock")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("unified-heatmap.png"), animations: "disabled" });
});

test("process placement, sizing and undo are saved with the analytical layout", async ({ page }) => {
  await page.goto(`${studio}/workspace/42`);
  await page.getByRole("button", { name: "Modifica canvas", exact: true }).click();
  const object = page.locator('[data-scene-object="__process__"]');
  const viewer = object.locator(".djs-container");
  await viewer.evaluate(el => el.setAttribute("data-session-marker", "same-viewer"));
  const handle = page.getByRole("button", { name: "Sposta Processo sulla tela", exact: true });
  await handle.press("ArrowRight");
  await expect(object).toHaveCSS("left", "20px");
  await page.getByRole("button", { name: "Annulla modifica al layout", exact: true }).click();
  await expect(object).toHaveCSS("left", "0px");
  await page.getByRole("button", { name: "Ripristina modifica al layout", exact: true }).click();
  await expect(object).toHaveCSS("left", "20px");
  await page.getByRole("button", { name: "Ridimensiona Processo sulla tela", exact: true }).press("ArrowRight");
  await expect(object).toHaveCSS("width", "920px");
  await expect(viewer).toHaveAttribute("data-session-marker", "same-viewer");
  await page.getByRole("button", { name: "Salva layout", exact: true }).click();
  await expect(page.getByRole("button", { name: "Modifica canvas", exact: true })).toBeVisible();
  await page.reload();
  await expect(object).toHaveCSS("left", "20px");
  await expect(object).toHaveCSS("width", "920px");
});



test("changing run retains the tool while resetting clock and activity scope", async ({ page }) => {
  await page.goto(`${studio}/workspace/42`);
  await seek(page, 200);
  await page.getByLabel("Attivit\u00e0", { exact: true }).selectOption("A");
  await page.locator(".sim-studio-tools").getByRole("button", { name: "Risultati", exact: true }).click();
  await expect(page).toHaveURL(/panel=overview/);
  await page.getByRole("combobox", { name: "Scegli una run" }).click();
  await page.getByRole("option", { name: /TO-BE/ }).click();
  await expect(page).toHaveURL(/workspace\/43.*panel=overview/);
  await expect(page.locator(".sim-final-transport")).toBeVisible();
  await expect(page.getByLabel("Attivit\u00e0", { exact: true })).toHaveValue("all");
  await expect(page.locator(".sim-studio-dock")).toContainText("TO-BE");
  await expect(page.locator("[data-process-tile]")).toHaveCount(1);
  await page.getByRole("button", { name: "Riprendi osservazione", exact: true }).click();
  await expect(page.locator('input[type="range"]')).toHaveValue("0");
});

for (const state of ["pending", "failed", "no-artifact"] as const) {
  test(`${state} run keeps the process and scenario controls reachable`, async ({ page }) => {
    if (state === "no-artifact") await page.route("http://127.0.0.1:8000/**/replay", (route) => route.fulfill({ status: 404, json: { detail: "No artifact" } }));
    else await page.route("http://127.0.0.1:8000/**/simulation-runs", (route) => route.fulfill({ json: [{ ...run, status: state, error: state === "failed" ? "Simulation failed" : null }] }));
    await page.goto(`${studio}/workspace/42`);
    await expect(page.locator(".simulation-bpmn-view .djs-container")).toHaveCount(1);
    await page.locator(".sim-studio-tools").getByRole("button", { name: "Scenario", exact: true }).click();
    await expect(page.getByRole("complementary", { name: "Dettagli e impostazioni", exact: true })).toBeVisible();
    await expect(page.locator(".sim-config-body")).toBeVisible();
    await expect(page.locator(".simulation-bpmn-view .djs-container")).toHaveCount(1);
  });
}


const complexXml = (() => {
  const nodes = ["Start", "A", "Gateway", "C", "B", "D", "E", "End"];
  const names = ["Ricevi richiesta", "Verifica documentazione", "Completa?", "Richiedi integrazione", "Approva richiesta", "Controlla disponibilità", "Emetti ordine", "Ordine emesso"];
  const positions = [[80, 130], [180, 108], [380, 125], [490, 108], [180, 320], [380, 320], [580, 320], [790, 342]];
  const tags = nodes.map((id, i) => `<bpmn:${i === 0 ? "startEvent" : i === 7 ? "endEvent" : i === 2 ? "exclusiveGateway" : "task"} id="${id}" name="${names[i]}"/>`).join("");
  const flows = [[0,1],[1,2],[2,3],[3,1],[2,4],[4,5],[5,6],[6,7]].map(([from,to], i) => `<bpmn:sequenceFlow id="Flow_${i}" sourceRef="${nodes[from]}" targetRef="${nodes[to]}"/>`).join("");
  const shapes = nodes.map((id, i) => `<bpmndi:BPMNShape id="${id}_di" bpmnElement="${id}"><dc:Bounds x="${positions[i][0]}" y="${positions[i][1]}" width="${i === 0 || i === 7 ? 36 : i === 2 ? 50 : 140}" height="${i === 0 || i === 7 ? 36 : i === 2 ? 50 : 80}"/></bpmndi:BPMNShape>`).join("");
  return `<?xml version="1.0" encoding="UTF-8"?><bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definition_complex" targetNamespace="https://example.test/simulation"><bpmn:process id="Process_complex" isExecutable="false"><bpmn:laneSet id="Lanes"><bpmn:lane id="Operations" name="Operations"><bpmn:flowNodeRef>Start</bpmn:flowNodeRef><bpmn:flowNodeRef>A</bpmn:flowNodeRef><bpmn:flowNodeRef>Gateway</bpmn:flowNodeRef><bpmn:flowNodeRef>C</bpmn:flowNodeRef></bpmn:lane><bpmn:lane id="Finance" name="Finance"><bpmn:flowNodeRef>B</bpmn:flowNodeRef><bpmn:flowNodeRef>D</bpmn:flowNodeRef><bpmn:flowNodeRef>E</bpmn:flowNodeRef><bpmn:flowNodeRef>End</bpmn:flowNodeRef></bpmn:lane></bpmn:laneSet>${tags}${flows}</bpmn:process><bpmndi:BPMNDiagram id="Diagram_complex"><bpmndi:BPMNPlane id="Plane_complex" bpmnElement="Process_complex"><bpmndi:BPMNShape id="Operations_di" bpmnElement="Operations" isHorizontal="true"><dc:Bounds x="30" y="70" width="860" height="210"/></bpmndi:BPMNShape><bpmndi:BPMNShape id="Finance_di" bpmnElement="Finance" isHorizontal="true"><dc:Bounds x="30" y="280" width="860" height="210"/></bpmndi:BPMNShape>${shapes}${[[0,1],[1,2],[2,3],[3,1],[2,4],[4,5],[5,6],[6,7]].map(([from,to],i) => `<bpmndi:BPMNEdge id="Flow_${i}_di" bpmnElement="Flow_${i}"><di:waypoint x="${positions[from][0] + 36}" y="${positions[from][1]+40}"/><di:waypoint x="${positions[to][0]}" y="${positions[to][1]+40}"/></bpmndi:BPMNEdge>`).join("")}</bpmndi:BPMNPlane></bpmndi:BPMNDiagram></bpmn:definitions>`;
})();

test("a consultant observes a lane-based process and opens details without reflowing it", async ({ page, isMobile }, testInfo) => {
  await page.route("http://127.0.0.1:8000/**/simulation-ui-model", route => route.fulfill({ json: { id: "simulation-ui-model", process_id: "simulation-ui-process", name: "Acquisti", xml: complexXml } }));
  if (!isMobile) await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto(`${studio}/workspace/42`);
  await seek(page, 100);
  const process = page.locator('[data-scene-object="__process__"]');
  const viewer = process.locator(".djs-container");
  await expect(viewer.locator('[data-element-id="Operations"]')).toBeVisible();
  await expect(viewer.locator('[data-element-id="Gateway"]')).toBeVisible();
  await expect(process.locator(".sim-token")).not.toHaveCount(0);
  await viewer.evaluate(el => el.setAttribute("data-session-marker", "same-lanes"));
  const size = await process.boundingBox();
  await page.locator(".sim-studio-tools").getByRole("button", { name: "Scenario", exact: true }).click();
  await expect(viewer).toHaveAttribute("data-session-marker", "same-lanes");
  expect((await process.boundingBox())!.width).toBeCloseTo(size!.width, 1);
  expect((await process.boundingBox())!.height).toBeCloseTo(size!.height, 1);
  await page.getByRole("button", { name: "Chiudi pannello", exact: true }).click();
  await expect(page.locator(".sim-studio-dock")).toBeHidden();
  await expect(page.locator('input[type="range"]')).toHaveValue("100");
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
  await page.screenshot({ path: testInfo.outputPath("analytical-canvas-lanes.png"), animations: "disabled" });
});

for (const missingReplay of [false, true]) test(`comparison uses the selected B summary and preserves observation clock (missing replay: ${missingReplay})`, async ({ page, isMobile }, testInfo) => {
  const variant = { ...run, id: 43, scenario_name: "TO-BE · Capacità aggiuntiva", summary: { ...run.summary, casesCompleted: 8, cycle: { avg: 120, p50: 110, p90: 150, p95: 160 }, cost: { total: 400, perCase: 50 }, throughputPerHour: 0.0032 } };
  await page.route("http://127.0.0.1:8000/**/simulation-runs", route => route.fulfill({ json: [run, variant] }));
  await page.route("http://127.0.0.1:8000/**/43/replay", route => missingReplay ? route.fulfill({ status: 404, json: { detail: "No replay" } }) : route.fulfill({ json: { run_id: 43, schema_version: 1, replay: { ...payload, series: { ...payload.series, global: { ...payload.series.global, done: [0,2,4,6,8], costAccrued: [0,100,200,300,400] } } } } }));
  await page.goto(`${studio}/workspace/42`);
  await seek(page, 200);
  const viewer = page.locator("[data-process-tile] .djs-container");
  await viewer.evaluate(el => el.setAttribute("data-session-marker", "same-comparison"));
  await page.locator(".sim-studio-tools").getByRole("button", { name: "Confronto", exact: true }).click();
  await page.locator(".sim-comparison-bar").getByRole("combobox").last().click();
  await page.getByRole("option", { name: /TO-BE/ }).click();
  await expect(page.locator(".sim-kpi").filter({ hasText: "Attraversamento medio" })).toContainText("2 min");
  await expect(page.locator(".sim-kpi").filter({ hasText: "Costo accumulato" })).toContainText("400");
  await expect(page.locator(".sim-kpi").filter({ hasText: "Throughput" })).toContainText("0,0032/h");
  await expect(page.locator(".sim-scope-badge")).toContainText("#43");
  await expect(viewer).toHaveAttribute("data-session-marker", "same-comparison");
  if (!isMobile) {
    expect((await page.locator(".sim-scene-viewport").boundingBox())!.height).toBeGreaterThan(260);
    await expect(viewer.locator('[data-element-id="A"]')).toBeInViewport();
  }
  await expect(page.locator(".sim-studio-dock")).toBeHidden();
  await expect(page.locator(".sim-token")).toHaveCount(0);
  if (missingReplay) await expect(page.locator(".sim-widget-empty").first()).toContainText("Replay non disponibile");
  await page.locator(".sim-comparison-details > summary").click();
  await expect(page.locator(".sim-comparison-details")).toContainText("0,0032/h");
  await page.locator(".sim-comparison-details > summary").click();
  await page.screenshot({ path: testInfo.outputPath("analytical-canvas-comparison.png"), animations: "disabled" });
  await page.getByRole("button", { name: "Riprendi osservazione", exact: true }).click();
  await expect(page.locator('input[type="range"]')).toHaveValue("200");
  await expect(page.locator(".sim-kpi").filter({ hasText: "Costo accumulato" })).toContainText("20");
  await expect(viewer).toHaveAttribute("data-session-marker", "same-comparison");
});


test("pointer placement commits one scene edit in world coordinates at a non-default zoom", async ({ page, isMobile }) => {
  test.skip(isMobile, "Keyboard and touch targets are covered by the mobile journeys.");
  await page.goto(`${studio}/workspace/42`);
  await page.getByRole("button", { name: "Modifica canvas", exact: true }).click();
  const object = page.locator('[data-scene-object="__process__"]');
  const handle = page.getByRole("button", { name: "Sposta Processo sulla tela", exact: true });
  await page.locator(".sim-scene-controls").getByRole("button", { name: "Zoom indietro", exact: true }).click();
  const scale = await object.evaluate(el => el.getBoundingClientRect().width / (el as HTMLElement).offsetWidth);
  const box = (await handle.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 48, box.y + box.height / 2 + 32, { steps: 4 });
  await page.mouse.up();
  const moved = await object.evaluate(el => ({ x: parseFloat((el as HTMLElement).style.left), y: parseFloat((el as HTMLElement).style.top) }));
  expect(moved.x).toBeCloseTo(48 / scale, 1);
  expect(moved.y).toBeCloseTo(32 / scale, 1);
  await page.getByRole("button", { name: "Annulla modifica al layout", exact: true }).click();
  await expect(object).toHaveCSS("left", "0px");
  await expect(object).toHaveCSS("top", "0px");
  await expect(page.getByRole("button", { name: "Annulla modifica al layout", exact: true })).toBeDisabled();
});


test("headers move process and charts directly at nondefault zoom with one undoable edit", async ({ page, isMobile }) => {
  test.skip(isMobile, "Mouse header dragging is covered on desktop; touch and keyboard placement have separate journeys.");
  await page.goto(`${studio}/workspace/42`);
  const process = page.locator('[data-scene-object="__process__"]');
  const header = process.locator(".sim-process-tile-header");
  await header.click();
  await expect(page.getByRole("button", { name: "Salva layout", exact: true })).toHaveCount(0);
  const moveHeader = async (selector: string) => {
    const object = page.locator(selector);
    const heading = object.locator(".sim-widget-heading,.sim-process-tile-header");
    const box = (await heading.boundingBox())!;
    const scale = await object.evaluate(el => el.getBoundingClientRect().width / (el as HTMLElement).offsetWidth);
    const before = await object.evaluate(el => ({ x: parseFloat((el as HTMLElement).style.left), y: parseFloat((el as HTMLElement).style.top) }));
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 48, box.y + box.height / 2 + 36, { steps: 5 });
    await page.mouse.up();
    const after = await object.evaluate(el => ({ x: parseFloat((el as HTMLElement).style.left), y: parseFloat((el as HTMLElement).style.top) }));
    expect(after.x - before.x).toBeCloseTo(48 / scale, 1);
    expect(after.y - before.y).toBeCloseTo(36 / scale, 1);
    return { before, after };
  };
  await moveHeader('[data-scene-object="__process__"]');
  await expect(page.getByRole("button", { name: "Salva layout", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Annulla modifica al layout", exact: true }).click();
  await expect(process).toHaveCSS("left", "0px");
  await expect(page.getByRole("button", { name: "Annulla modifica al layout", exact: true })).toBeDisabled();
  await jump(page, "default-0");
  await page.getByRole("button", { name: "Zoom indietro", exact: true }).click();
  const chart = await moveHeader('[data-scene-object="default-0"]');
  await page.getByRole("button", { name: "Salva layout", exact: true }).click();
  await expect(page.getByRole("button", { name: "Modifica canvas", exact: true })).toBeVisible();
  await page.reload();
  const restored = await page.locator('[data-scene-object="default-0"]').evaluate(el => parseFloat((el as HTMLElement).style.left));
  expect(restored).toBeCloseTo(chart.after.x, 1);
});

test("palette adds consecutive visible KPIs and notes with keyboard configuration and cancel", async ({ page }, testInfo) => {
  await page.goto(`${studio}/workspace/42`);
  await page.getByRole("button", { name: "Aggiungi widget", exact: true }).click();
  const palette = page.getByRole("complementary", { name: "Aggiungi un elemento", exact: true });
  await palette.getByRole("button", { name: /^KPI · Costo accumulato/ }).press("Enter");
  const added = page.locator('[data-scene-object]:not(.is-process)').filter({ has: page.locator('[data-widget-id]:not([data-widget-id^="default-"])') });
  await expect(added).toHaveCount(1);
  await expect(added.first()).toBeInViewport({ ratio: 0.9 });
  await palette.getByRole("button", { name: /^KPI · Casi in coda/ }).click();
  await expect(added).toHaveCount(2);
  await expect(added.last()).toBeInViewport({ ratio: 0.9 });
  const rects = await added.evaluateAll(elements => elements.map(el => ({ x: parseFloat((el as HTMLElement).style.left), y: parseFloat((el as HTMLElement).style.top) })));
  expect(rects[0]).not.toEqual(rects[1]);
  await palette.getByRole("button", { name: "Testo", exact: true }).click();
  await palette.getByRole("button", { name: /^Nota di analisi/ }).click();
  await expect(added).toHaveCount(3);
  await expect(added.last()).toBeInViewport({ ratio: 0.9 });
  await expect(added.last()).toContainText("Prossima azione");
  await palette.getByRole("button", { name: "Chiudi raccolta elementi", exact: true }).press("Escape");
  await expect(page.getByRole("button", { name: "Aggiungi widget", exact: true })).toBeFocused();
  await page.getByRole("button", { name: "Configura Nota di analisi", exact: true }).click();
  await expect(page.getByLabel("Titolo", { exact: true })).toBeFocused();
  await page.getByLabel("Titolo", { exact: true }).fill("Ipotesi di miglioramento");
  await page.getByRole("button", { name: "Chiudi pannello", exact: true }).click();
  const violations = await new AxeBuilder({ page }).include(".sim-studio").withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(violations.violations).toEqual([]);
  await page.getByRole("button", { name: "Aggiungi widget", exact: true }).click();
  await page.screenshot({ path: testInfo.outputPath("canvas-authoring.png"), animations: "disabled" });
  const paletteScan = await new AxeBuilder({ page }).include(".sim-studio").withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(paletteScan.violations).toEqual([]);
  await page.getByRole("button", { name: "Annulla", exact: true }).click();
  await expect(page.locator(".sim-widget")).toHaveCount(6);
  await expect(palette).toHaveCount(0);
});

test("dragging a palette preset places it at the drop point in scene coordinates", async ({ page, isMobile }) => {
  test.skip(isMobile, "Native HTML drag/drop uses a mouse; click-to-add covers touch devices.");
  await page.goto(`${studio}/workspace/42`);
  await page.getByRole("button", { name: "Zoom indietro", exact: true }).click();
  await page.getByRole("button", { name: "Aggiungi widget", exact: true }).click();
  const viewport = page.getByRole("region", { name: "Tela di processo e analisi", exact: true });
  const camera = await page.locator(".sim-scene-world").evaluate(el => { const matrix = new DOMMatrix(getComputedStyle(el).transform); return { x: matrix.e, y: matrix.f, scale: matrix.a }; });
  const box = (await viewport.boundingBox())!;
  const point = { x: Math.min(480, box.width - 40), y: Math.min(160, box.height - 40) };
  await page.getByRole("complementary", { name: "Aggiungi un elemento", exact: true }).getByRole("button", { name: /^KPI · Costo accumulato/ }).dragTo(viewport, { targetPosition: point });
  const widget = page.locator('[data-widget-id]:not([data-widget-id^="default-"])');
  await expect(widget).toHaveCount(1);
  const rect = await widget.evaluate(el => { const scene = el.closest("[data-scene-object]") as HTMLElement; return { x: parseFloat(scene.style.left), y: parseFloat(scene.style.top) }; });
  expect(Math.abs(rect.x - (point.x - camera.x) / camera.scale)).toBeLessThan(2 / camera.scale);
  expect(Math.abs(rect.y - (point.y - camera.y) / camera.scale)).toBeLessThan(2 / camera.scale);
  await expect(widget).toBeInViewport({ ratio: 0.9 });
  await page.getByRole("button", { name: "Salva layout", exact: true }).click();
  await expect(page.getByRole("button", { name: "Modifica canvas", exact: true })).toBeVisible();
  await page.reload();
  await expect(widget).toHaveCount(1);
});


test("results panels have dedicated space and readable metrics on desktop and phone", async ({ page, isMobile }, testInfo) => {
  await page.route("http://127.0.0.1:8000/**/simulation-runs", route => route.fulfill({ json: [{ ...run, result: {
    OverallScenarioStatistics: [{ KPI: "cycle_time", Average: 267, "Trace Ocurrences": 3 }, { KPI: "waiting_time", Average: 90 }, { KPI: "processing_time", Average: 177 }],
    ResourceUtilization: [{ "Resource ID": "Analisti", "Resource name": "Analisti", "Utilization": 0.8 }],
    IndividualTaskStatistics: [{ Name: "Verifica documentazione", Count: 3, "Waiting Time": 90, "Processing Time": 177, "Cycle Time": 267 }],
  } }, { ...run, id: 43, scenario_name: "TO-BE · Capacità aggiuntiva" }] }));
  if (!isMobile) await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto(`${studio}/workspace/42`);
  await page.locator(".sim-studio-tools").getByRole("button", { name: "Risultati", exact: true }).click();
  const dock = page.locator(".sim-studio-dock");
  const board = page.locator(".sim-studio-board");
  const metrics = dock.locator(".sim-snapshot-kpis");
  await expect(metrics.locator("strong")).toHaveCount(6);
  const positions = await page.evaluate(() => {
    const box = (selector: string) => { const r = document.querySelector(selector)!.getBoundingClientRect(); return { left: r.left, right: r.right, top: r.top, bottom: r.bottom }; };
    return { board: box(".sim-studio-board"), dock: box(".sim-studio-dock") };
  });
  if (isMobile) expect(positions.dock.top).toBeGreaterThanOrEqual(positions.board.bottom);
  else expect(positions.dock.left).toBeGreaterThanOrEqual(positions.board.right);
  expect(await metrics.locator("strong").evaluateAll(elements => elements.every(element => element.scrollWidth <= element.clientWidth))).toBe(true);
  expect(await metrics.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
  await expect(board.getByRole("button", { name: "Aggiungi widget", exact: true })).toBeVisible();
  await metrics.scrollIntoViewIfNeeded();
  const scan = await new AxeBuilder({ page }).include(".sim-studio").withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(scan.violations).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("satin-results.png"), animations: "disabled" });
});

test("multiple alternatives compare against one reference and preserve the replay session", async ({ page, isMobile }, testInfo) => {
  const names = ["TO-BE · Capacità", "TO-BE · Automazione", "TO-BE · Turni", "TO-BE · Priorità", "TO-BE · Calendario"];
  await page.route("http://127.0.0.1:8000/**/simulation-runs", route => route.fulfill({ json: [run, ...names.map((name, index) => ({ ...run, id: 43 + index, scenario_name: name, summary: { ...run.summary, cycle: { ...run.summary.cycle, avg: 200 - index * 10 }, cost: { total: 1200 + index * 100, perCase: 400 + index * 10 } } }))] }));
  if (!isMobile) await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto(`${studio}/workspace/42`);
  await seek(page, 200);
  await page.locator(".sim-studio-tools").getByRole("button", { name: "Confronto", exact: true }).click();
  await page.getByRole("combobox", { name: "Scenario A", exact: true }).click();
  await page.getByRole("option", { name: /AS-IS/ }).click();
  await expect(page.getByRole("combobox", { name: "Scenario A", exact: true })).toContainText("AS-IS");
  await page.getByRole("combobox", { name: "Scenario B", exact: true }).click();
  await page.getByRole("option", { name: /TO-BE · Capacità/ }).click();
  await expect(page.getByRole("combobox", { name: "Scenario B", exact: true })).toContainText("TO-BE · Capacità");
  await page.locator(".sim-multi-comparison > summary").click();
  const matrix = page.getByRole("region", { name: "Matrice di confronto degli scenari", exact: true });
  await page.getByRole("checkbox", { name: "TO-BE · Automazione · #44", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: "TO-BE · Automazione · #44", exact: true })).toBeChecked();
  await page.getByRole("checkbox", { name: "TO-BE · Turni · #45", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: "TO-BE · Turni · #45", exact: true })).toBeChecked();
  await expect(matrix.locator("thead th")).toHaveCount(5);
  const cycle = matrix.locator("tbody tr").filter({ hasText: "Attraversamento medio" });
  await expect(cycle.locator("td").nth(0)).toContainText("4 min");
  await expect(cycle.locator("td").nth(1)).toContainText("3 min");
  await expect(cycle.locator("td").nth(2)).toContainText("Migliora");
  await expect(matrix.locator("tbody tr").filter({ hasText: "Costo per caso" })).toContainText("Peggiora");
  await page.getByRole("checkbox", { name: "TO-BE · Priorità · #46", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: "TO-BE · Priorità · #46", exact: true })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: "TO-BE · Calendario · #47", exact: true })).toBeDisabled();
  await matrix.locator("thead th").filter({ hasText: "TO-BE · Turni" }).getByRole("button", { name: "Osserva nel canvas", exact: true }).click();
  await expect(page).toHaveURL(/b=45/);
  await expect(page).toHaveURL(/compareMode=b/);
  await expect(matrix.locator("thead th")).toHaveCount(6);
  const scan = await new AxeBuilder({ page }).include(".sim-studio").withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(scan.violations).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("scenario-matrix.png"), animations: "disabled" });
  await page.locator(".sim-studio-tools").getByRole("button", { name: "Osserva", exact: true }).click();
  await expect(page.locator('input[type="range"]')).toHaveValue("200");
});

test("different model versions do not paint unmatched activities as comparable", async ({ page }) => {
  await page.route("http://127.0.0.1:8000/**/simulation-runs", route => route.fulfill({ json: [run, { ...run, id: 43, bpmn_model_id: "different-model", scenario_name: "TO-BE · Modello diverso" }] }));
  await page.goto(`${studio}/workspace/42?view=compare&a=42&b=43`);
  await expect(page.locator(".sim-comparison-bar > .sim-comparison-compatibility")).toContainText("mappatura");
  await expect(page.locator(".sim-delta-better,.sim-delta-worse,.sim-heat-1,.sim-heat-2,.sim-heat-3,.sim-heat-4,.sim-heat-5")).toHaveCount(0);
});
