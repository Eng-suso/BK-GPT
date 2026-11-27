import { test, expect, type Locator, type Page, type Request, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const studio = "/projects/eventlog-project/processes/eventlog-process/simulation";
const xml = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_log" targetNamespace="https://example.test/eventlog">
<bpmn:process id="Process_log" isExecutable="false"><bpmn:startEvent id="Start" /><bpmn:task id="A" name="Verifica documentazione" /><bpmn:task id="B" name="Approva richiesta" /><bpmn:endEvent id="End" /><bpmn:sequenceFlow id="F1" sourceRef="Start" targetRef="A" /><bpmn:sequenceFlow id="F2" sourceRef="A" targetRef="B" /><bpmn:sequenceFlow id="F3" sourceRef="B" targetRef="End" /></bpmn:process>
<bpmndi:BPMNDiagram id="Diagram_log"><bpmndi:BPMNPlane id="Plane_log" bpmnElement="Process_log"><bpmndi:BPMNShape id="Start_di" bpmnElement="Start"><dc:Bounds x="80" y="120" width="36" height="36" /></bpmndi:BPMNShape><bpmndi:BPMNShape id="A_di" bpmnElement="A"><dc:Bounds x="180" y="98" width="140" height="80" /></bpmndi:BPMNShape><bpmndi:BPMNShape id="B_di" bpmnElement="B"><dc:Bounds x="400" y="98" width="140" height="80" /></bpmndi:BPMNShape><bpmndi:BPMNShape id="End_di" bpmnElement="End"><dc:Bounds x="610" y="120" width="36" height="36" /></bpmndi:BPMNShape><bpmndi:BPMNEdge id="F1_di" bpmnElement="F1"><di:waypoint x="116" y="138" /><di:waypoint x="180" y="138" /></bpmndi:BPMNEdge><bpmndi:BPMNEdge id="F2_di" bpmnElement="F2"><di:waypoint x="320" y="138" /><di:waypoint x="400" y="138" /></bpmndi:BPMNEdge><bpmndi:BPMNEdge id="F3_di" bpmnElement="F3"><di:waypoint x="540" y="138" /><di:waypoint x="610" y="138" /></bpmndi:BPMNEdge></bpmndi:BPMNPlane></bpmndi:BPMNDiagram></bpmn:definitions>`;

const activity = (el: string | null, name: string, wait: number, processing: number) => ({
  el, name, count: 3, wait: { avg: wait, p95: wait }, processing: { avg: processing, p95: processing },
  queue: { avg: 0, max: 0 }, utilizationPct: 0, avgCost: 0, cycleContributionPct: 0.5, casesAffectedPct: 0.5,
});

const run = {
  id: 42, bpmn_model_id: "eventlog-model", process_id: "eventlog-process", scenario_name: "AS-IS · Gestione richieste",
  engine: "prosimos", status: "completed", request: {}, scenario: {}, result: {}, outputs: [], error: null,
  created_at: "2026-01-05T09:00:00Z", completed_at: "2026-01-05T09:01:00Z",
  summary: { casesCompleted: 300, cycle: { avg: 4200, p50: 4000, p90: 6600, p95: 7000 }, waiting: { avg: 1500, p95: 2000, share: 0.36 },
    processing: { avg: 2700 }, cost: { total: 9000, perCase: 30 }, throughputPerHour: 2.2,
    byActivity: [activity("A", "Verifica documentazione", 900, 1200), activity("B", "Approva richiesta", 600, 1500)],
    byResource: [], bottleneck: { el: "A", name: "Verifica documentazione" } },
};

const replay = {
  schemaVersion: 1, meta: { start: "2026-01-05T09:00:00Z", durationSec: 400, totalCases: 1, sampledCases: 1, bucketSec: 100 },
  elements: { A: { name: "Verifica documentazione" }, B: { name: "Approva richiesta" } },
  cases: [{ id: "0", cycleSec: 150, events: [{ el: "A", enable: 0, start: 0, end: 50, res: "Analisti" }, { el: "B", enable: 50, start: 100, end: 150, res: "Approvatori" }] }],
  series: { t: [0, 100, 200], byElement: { A: { active: [1, 0, 0], queued: [0, 0, 0], done: [0, 1, 1] }, B: { active: [0, 1, 0], queued: [0, 0, 0], done: [0, 0, 1] } },
    byResource: {}, global: { wip: [1, 1, 0], queued: [0, 0, 0], done: [0, 0, 1], throughputPerHour: [0, 0, 24], costAccrued: [0, 5, 10], avgCycleSec: [0, 0, 150] } },
  flows: {},
};

const COLUMNS = ["Pratica", "Attivita", "Pronta", "Inizio", "Fine", "Utente"];
const MAPPING = {
  case_id: ["Pratica"], activity: ["Attivita"], start: "Inizio", end: "Fine", enable: "Pronta", timestamp: null, lifecycle: null,
  resource: "Utente", role: null, cost: null, case_attributes: [], event_attributes: [],
  timestamps: { pattern: null, timezone: "Europe/Rome" }, numbers: { decimal: ".", thousands: "" },
};
const LOG = {
  id: "elog_e2e", process_id: "eventlog-process", name: "sap-export.csv", format: "csv", delimiter: ";", byte_size: 512, row_count: 9,
  columns: COLUMNS, status: "uploaded", mapping: null, template: null, created_at: "2026-10-07T10:00:00Z", mapped_at: null,
};
const ANALYSIS = {
  event_log: { ...LOG, status: "mapped", mapping: MAPPING, mapped_at: "2026-10-07T10:01:00Z" },
  quality: { rows_read: 9, rows_excluded: 0, events: 9, cases: 3, activities: 3, resources: 2, period_start: "2026-01-05T09:00:00+01:00", period_end: "2026-01-09T18:00:00+01:00", events_without_start: 0, issues: [] },
  activities: {
    bpmn_version_id: 1, confirmed: true,
    matches: [
      { activity: "Verifica documentazione", events: 3, element_id: "A", reason: "same_name" },
      { activity: "Approva richiesta", events: 3, element_id: "B", reason: "same_name" },
      { activity: "Archivia", events: 3, element_id: null, reason: "none" },
    ],
    unmatched_activities: ["Archivia"], unobserved_elements: [],
  },
  resources: { confirmed: false, matches: [], unmatched_resources: [], unobserved_model_resources: [], events_without_resource: 0 },
  summary: {
    casesCompleted: 3, cycle: { avg: 4000, p50: 3900, p90: 6000, p95: 6200 }, waiting: { avg: 1400, p95: 1800, share: 0.35 },
    processing: { avg: 2600, p95: 3000 }, throughputPerHour: 2, cost: null, timing: "start_and_end", source: "real",
    byActivity: [activity("A", "Verifica documentazione", 800, 1150), activity("B", "Approva richiesta", 600, 900), activity(null, "Archivia", 0, 60), activity("End", "Chiusura pratica", 0, 30)],
    // B3.2: le cause delle attese che calcola il server (secondi totali per attivita').
    waitingCauses: {
      activities: [
        { name: "Approva richiesta", el: "B", executions: 3, waiting: 2, seconds: { contention: 9720, unavailability: 4320, extraneous: 3600, batching: 360 } },
      ],
    },
  },
};

/** Il report del server: stesse definizioni osservabili sui due lati (SIM-19). */
const kpi = (real: number, mean: number) => ({ real, mean, ci95Half: null, min: mean, max: mean, bias: mean - real, mae: Math.abs(mean - real) });
const VALIDATION = {
  referenceCases: 3, simulatedCases: [300], replications: 1, runIds: [42],
  kpis: {
    cycle: kpi(4000, 4200), p50: kpi(3900, 4000), p90: kpi(6000, 6600),
    between: kpi(1400, 1500), processing: kpi(2600, 2700), throughput: kpi(2, 2.2),
  },
  distances: { cycleW1: { mean: 300, ci95Half: null, min: 300, max: 300 }, ngd: { mean: 0.05, ci95Half: null, min: 0.05, max: 0.05 } },
  pooledCycle: { p50: 4000, p90: 6600 },
  firstWaitSimulated: null,
  quality: { rowsExcluded: 0, eventsWithoutStart: 0 },
  provenance: { eventLogId: "elog_e2e", runs: [{ runId: 42, seed: 7, engine: "prosimos", engineVersion: "2.1.0", startDate: "2026-01-05T00:00:00Z", warmupCases: 0 }] },
  initialActivities: [],
  basis: "observable",
};

/** Due simulazioni dello stesso gruppo: il report mostra la media, la seconda è quella scelta. */
const GROUP_A = { ...run, id: 41, request: { replication_group: "batch-e2e", replication_index: 1 } };
const GROUP_B = { ...run, request: { replication_group: "batch-e2e", replication_index: 2 } };
const GROUP_VALIDATION = { ...VALIDATION, replications: 2, simulatedCases: [280, 320], runIds: [41, 42],
  provenance: { eventLogId: "elog_e2e", runs: [41, 42].map((runId) => ({ runId, seed: runId, engine: "prosimos", engineVersion: "2.1.0", startDate: "2026-01-05T00:00:00Z", warmupCases: 0 })) } };

/** Token replay del server (CONF-01): un caso su tre salta l'approvazione. */
const CONFORMANCE = {
  event_log: ANALYSIS.event_log, bpmn_version_id: 1, mapping_bpmn_version_id: 1,
  fitness: 0.94, cases: 3, fitting_cases: 2, fitting_share: 2 / 3,
  deviations: [{ element_id: "B", name: "Approva richiesta", executed_out_of_order: 0, left_waiting: 1, cases_affected: 1 }],
  variants: [
    { activities: ["Verifica documentazione", "Approva richiesta", "Archivia"], cases: 2, fitness: 1, fits: false, out_of_order: [], waiting: [], unmodeled: ["Archivia"] },
    { activities: ["Verifica documentazione", "Archivia"], cases: 1, fitness: 0.8, fits: false, out_of_order: [], waiting: ["B"], unmodeled: ["Archivia"] },
  ],
  unmodeled_activities: { Archivia: 3 }, unobserved_elements: [], excluded_variants: 0, excluded_cases: 0, warnings: [],
};

type Fixture = { mappingRequests: Request[] };

async function fixture(page: Page, logs: unknown[], options: { runs?: unknown[]; validation?: unknown } = {}): Promise<Fixture> {
  const state: Fixture = { mappingRequests: [] };
  await page.addInitScript(() => { Object.assign(window, { DELIR_API_BASE: "http://127.0.0.1:8000" }); localStorage.setItem("delir-language", "it"); });
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let data: unknown = [];
    if (path === "/v1/workspace/projects/eventlog-project") data = {
      id: "eventlog-project", client_id: "demo", client: "Azienda Demo", name: "Efficienza operativa", phase: "AS-IS", status: "In corso", progress: 50, processes: 1,
      next_step: "Validare il modello sul log", milestones: [], open_issues: [], deliverables: [],
      process_items: [{ id: "eventlog-process", project_id: "eventlog-project", bpmn_model_id: "eventlog-model", name: "Gestione richieste", stage: "AS-IS", status: "Da validare", owner: "Team Operations", readiness: 85 }],
    };
    else if (path.endsWith("/simulation-runs")) data = options.runs ?? [run];
    else if (path.endsWith("/replay")) data = { run_id: 42, schema_version: 1, replay };
    else if (path.endsWith("/model")) data = { run_id: 42, model: null };
    else if (path.endsWith("/simulation-template")) data = { tasks: [{ element_id: "A", name: "Verifica documentazione", type: "task" }, { element_id: "B", name: "Approva richiesta", type: "task" }], resources: [], gateways: [] };
    else if (path.endsWith("/experiments")) data = { bottleneck_el: "A", bottleneck_name: "Verifica documentazione", factors: {}, experiments: [] };
    else if (path.endsWith("/simulation-provenance")) data = { has_discovery: false, elements: [] };
    else if (path.endsWith("/eventlog-model")) data = { id: "eventlog-model", process_id: "eventlog-process", name: "Modello demo", xml };
    else if (path === "/v1/workspace/processes/eventlog-process/event-logs") data = logs;
    else if (path === "/v1/workspace/event-logs/elog_e2e/preview") data = { format: "csv", delimiter: ";", columns: COLUMNS, row_count: 9, sample_rows: [["P-1", "Verifica documentazione", "2026-01-05T09:00", "2026-01-05T09:10", "2026-01-05T09:30", "anna"]] };
    else if (path === "/v1/workspace/event-logs/elog_e2e/analysis") data = ANALYSIS;
    else if (path === "/v1/workspace/event-logs/elog_e2e/validation") data = options.validation ?? VALIDATION;
    else if (path === "/v1/workspace/event-logs/elog_e2e/conformance") data = CONFORMANCE;
    else if (path === "/v1/workspace/event-logs/elog_e2e/mapping") { state.mappingRequests.push(request); data = ANALYSIS; }
    await route.fulfill({ json: data });
  });
  return state;
}

/** UX-01: nel percorso ordinario nessun termine da statistico; la precisione resta nei dettagli. */
async function expectPlainLanguage(step: Locator) {
  expect(await step.innerText()).not.toMatch(/IC 95%|P50|P90|2-grammi|warm-up|Errore assoluto medio|repliche|replica\b|\bKPI\b/i);
}

/** Apre il passo "Reale contro simulato" del log mappato. */
async function openCompare(page: Page): Promise<Locator> {
  await page.goto(`${studio}/dashboard/42?panel=eventLog`);
  await dock(page).getByRole("button", { name: /^sap-export\.csv/ }).click();
  await dock(page).getByRole("button", { name: /Reale contro simulato$/ }).click();
  return dock(page).getByRole("region", { name: "Reale contro simulato" });
}

/** Gate UX (DELIR_UX_SHOTS): la schermata com'è (desktop 1440 × 900), poi il pannello intero per leggerne ogni riga. */
async function shoot(page: Page, testInfo: TestInfo, name: string) {
  if (!process.env.DELIR_UX_SHOTS) return;
  const path = `${process.env.DELIR_UX_SHOTS}/${name}-${testInfo.project.name}`;
  const viewport = page.viewportSize()!;
  const desktop = viewport.width > 1199;
  if (desktop) await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({ path: `${path}.png` });
  const body = dock(page).locator(".sim-studio-dock-body");
  const height = await body.evaluate((element) => element.scrollHeight);
  // Il pannello si allunga con la finestra: su telefono resta largo come il telefono.
  await page.setViewportSize({ width: desktop ? 1440 : viewport.width, height: height + (desktop ? 400 : 1200) });
  await body.evaluate((element) => { (element as HTMLElement).style.maxHeight = "none"; (element as HTMLElement).style.overflow = "visible"; });
  await body.screenshot({ path: `${path}-panel.png` });
  await body.evaluate((element) => { (element as HTMLElement).style.maxHeight = ""; (element as HTMLElement).style.overflow = ""; });
  await page.setViewportSize(viewport);
}

function dock(page: Page) {
  return page.locator(".sim-studio-dock");
}

test("the wizard maps the enablement column of an exported log", async ({ page }) => {
  const state = await fixture(page, [LOG]);
  await page.goto(`${studio}/dashboard/42?panel=eventLog`);
  await dock(page).getByRole("button", { name: /^sap-export\.csv/ }).click();

  // Il wizard propone le colonne riconoscibili: il consulente controlla, non compila.
  await expect(dock(page).getByRole("group", { name: "Identificativo del caso" }).getByRole("listitem")).toContainText(["Pratica"]);
  await expect(dock(page).getByRole("group", { name: "Attività", exact: true }).getByRole("listitem")).toContainText(["Attivita"]);
  await expect(dock(page).getByLabel("Fine (o completamento)")).toHaveValue("Fine");
  await expect(dock(page).getByLabel(/^Inizio/)).toHaveValue("Inizio");
  await expect(dock(page).getByLabel(/^Risorsa/)).toHaveValue("Utente");
  const enable = dock(page).getByLabel("Abilitazione");
  await expect(enable).toHaveAccessibleDescription(/enable_time/);
  await enable.selectOption("Pronta");
  await expect(dock(page).getByRole("region", { name: "Righe dell'event log" }).locator("th[data-used]")).toHaveCount(6);
  await dock(page).getByRole("button", { name: "Avanti" }).click();
  await dock(page).getByRole("button", { name: "Applica il mapping" }).click();

  await expect.poll(() => state.mappingRequests.length).toBe(1);
  expect(state.mappingRequests[0].postDataJSON().mapping).toEqual(MAPPING);
  await expect(dock(page).getByRole("region", { name: "Qualità e KPI" })).toBeVisible();
});

test("real against simulated: verdict, KPIs by activity and gaps on the process", async ({ page }, testInfo) => {
  await fixture(page, [ANALYSIS.event_log]);
  const step = await openCompare(page);
  await expect(step.getByLabel("Simulazione da confrontare")).toHaveValue("42");
  // Prima la risposta: cycle medio +5%, P90 +10%, la simulazione è vicina al log.
  await expect(step.getByRole("status").filter({ hasText: "Questa simulazione è vicina al log reale" })).toContainText("+5%");
  // Il report del server dice su cosa si basa, al singolare quando la simulazione è una.
  const report = step.getByRole("region", { name: "Confronto con il log reale" });
  await expect(report).toContainText("1 simulazione a confronto con 3 casi reali.");
  await expect(report).toContainText("Il log ha 3 casi, la simulazione 300 casi.");
  // Con una sola simulazione non si ripete la stessa tabella due volte.
  await expect(report.getByRole("table")).toHaveCount(0);
  const processTable = step.getByRole("table").filter({ has: page.getByRole("row", { name: /Durata media di un caso/ }) });
  await expect(processTable.getByRole("row", { name: /Durata media di un caso/ })).toContainText("+5%");
  await expect(processTable.getByRole("row", { name: /9 casi su 10 si chiudono entro/ })).toContainText("+10%");
  await expect(processTable.getByRole("row", { name: /Costo per caso/ })).toContainText("il log non ha costi");

  const activities = step.getByRole("table", { name: /Tempo di lavoro e attesa medi per attività/ });
  await expect(activities.getByRole("row")).toHaveCount(3);
  await expect(activities.getByRole("row", { name: /Approva richiesta/ })).toContainText("+67%");
  await expect(activities.getByRole("row", { name: /Verifica documentazione/ })).toContainText("+4%");
  await expect(step.getByText("1 attività del log non è nel modello: resta fuori dal confronto")).toBeVisible();
  await expect(step.getByText("1 attività del log non è mai stata eseguita nella simulazione")).toBeVisible();

  // UX-01: nel percorso ordinario nessun termine da statistico; la precisione resta nei dettagli.
  await expectPlainLanguage(step);
  await shoot(page, testInfo, "real-vs-simulated");
  await report.getByText("Dettagli per specialisti").click();
  const specialist = report.getByRole("table", { name: /intervallo di confidenza al 95%/ });
  await expect(specialist.getByRole("row", { name: /9 casi su 10 si chiudono entro/ })).toContainText("+10 min");
  await expect(report).toContainText("2-grammi");
  await expect(report).toContainText("warm-up 0");
  await shoot(page, testInfo, "real-vs-simulated-details");

  const show = step.getByRole("button", { name: "Mostra sul processo" });
  await show.click();
  await expect(show).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator('.djs-element[data-element-id="B"]')).toHaveClass(/sim-fidelity-far/);
  await expect(page.locator('.djs-element[data-element-id="A"]')).toHaveClass(/sim-fidelity-close/);
  await expect(page.locator(".sim-process-legend")).toContainText("Differenza fra simulato e reale");
  await expect(page.locator(".sim-process-legend")).toContainText("oltre ±25%");

  const axe = await new AxeBuilder({ page }).include(".sim-studio-dock").withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(axe.violations).toEqual([]);

  await show.click();
  await expect(page.locator('.djs-element[data-element-id="B"]')).not.toHaveClass(/sim-fidelity-far/);
  await show.click();
  await page.getByRole("button", { name: "Chiudi pannello", exact: true }).click();
  await expect(page.locator('.djs-element[data-element-id="B"]')).not.toHaveClass(/sim-fidelity-far/);
});

test("real against simulated with a group of simulations: averages first, plural wording", async ({ page }, testInfo) => {
  await fixture(page, [ANALYSIS.event_log], { runs: [GROUP_A, GROUP_B], validation: GROUP_VALIDATION });
  const step = await openCompare(page);
  const report = step.getByRole("region", { name: "Confronto con il log reale" });
  await expect(report).toContainText("2 simulazioni a confronto con 3 casi reali.");
  await expect(report).toContainText("Il log ha 3 casi, ogni simulazione da 280 a 320 casi.");
  const averages = report.getByRole("table").first();
  await expect(averages.getByRole("columnheader")).toHaveText(["Indicatore", "Reale", "Simulato (media)", "Differenza"]);
  await expect(averages.getByRole("row", { name: /9 casi su 10 si chiudono entro/ })).toContainText("+10 min");
  await expect(step.getByText("Sopra, la media di tutte le simulazioni del gruppo.", { exact: false })).toBeVisible();
  await expectPlainLanguage(step);

  const axe = await new AxeBuilder({ page }).include(".sim-studio-dock").withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(axe.violations).toEqual([]);
  await shoot(page, testInfo, "real-vs-simulated-group");
});

test("process conformance: verdict, skipped steps and overlay on the design", async ({ page }, testInfo) => {
  await fixture(page, [{ ...ANALYSIS.event_log }]);
  await page.goto(`${studio}/dashboard/42?panel=eventLog`);
  await dock(page).getByRole("button", { name: /^sap-export\.csv/ }).click();
  await dock(page).getByRole("button", { name: /Aderenza al processo$/ }).click();

  const step = dock(page).getByRole("region", { name: "Aderenza al processo" });
  const verdict = step.getByRole("status").filter({ hasText: "Una parte dei casi esce dal processo disegnato" });
  await expect(verdict).toContainText("2 casi su 3 seguono il disegno (67%).");
  await expect(step.getByRole("row", { name: /Approva richiesta/ })).toContainText("1 caso");
  await expect(step.getByText("Manca: Approva richiesta")).toBeVisible();
  await expect(step.getByText("Archivia · 3 casi")).toBeVisible();

  await step.getByRole("button", { name: "Mostra sul disegno" }).click();
  await expect(page.locator('.djs-element[data-element-id="B"].sim-fidelity-calibrate')).toHaveCount(1);
  await expect(page.locator(".sim-process-legend")).toContainText("Casi che escono dal disegno");
  await expect(step.getByRole("button", { name: "Avanti" })).toBeVisible();

  const results = await new AxeBuilder({ page }).include(".sim-studio-dock").withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(results.violations).toEqual([]);
  if (process.env.DELIR_UX_SHOTS) {
    await page.screenshot({ path: `${process.env.DELIR_UX_SHOTS}/conformance-${testInfo.project.name}.png`, fullPage: false });
  }
});

test("the activity inspector shows the same activity in the real log", async ({ page }) => {
  await fixture(page, [ANALYSIS.event_log]);
  await page.goto(`${studio}/workspace/42?panel=activity`);
  await page.getByLabel("Attività", { exact: true }).selectOption("B");
  const real = page.getByRole("region", { name: "Dal log reale", exact: true });
  await expect(real).toContainText("sap-export.csv");
  await expect(real).toContainText("15 min → 25 min");
  await expect(real.locator(".sim-gap")).toHaveText("+67%");
  await expect(real).toContainText("10 min → 10 min");
  const axe = await new AxeBuilder({ page }).include(".sim-real-activity").withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(axe.violations).toEqual([]);
});

test("the activity inspector says why the real activity waits, in plain words", async ({ page }, testInfo) => {
  await fixture(page, [ANALYSIS.event_log]);
  await page.goto(`${studio}/workspace/42?panel=activity`);
  await page.getByLabel("Attività", { exact: true }).selectOption("B");
  const why = page.getByRole("region", { name: "Perché si aspetta", exact: true });
  await expect(why.locator("dt")).toHaveText([
    "Le persone sono occupate in altro lavoro",
    "Fuori dall'orario di lavoro",
    "Si aspetta qualcosa da fuori: clienti, fornitori, altri uffici",
    "Il lavoro si raccoglie e si fa a lotti",
  ]);
  await expect(why.locator("dd")).toHaveText(["54%", "24%", "20%", "2%"]);
  await expect(why).toContainText("Su 2 attese delle 3 esecuzioni osservate");
  await expectPlainLanguage(why);
  const axe = await new AxeBuilder({ page }).include(".sim-real-activity").withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(axe.violations).toEqual([]);
  await shoot(page, testInfo, "why-it-waits");

  // Senza righe per l'elemento il log non lo dice: mai "non si aspetta" sotto un'attesa media.
  await page.getByLabel("Attività", { exact: true }).selectOption("A");
  await expect(why).toContainText("servono l'ora d'inizio e la persona");
});

test("without a mapped log the inspector leads to the import", async ({ page }) => {
  await fixture(page, [LOG]);
  await page.goto(`${studio}/workspace/42?panel=activity`);
  await page.getByLabel("Attività", { exact: true }).selectOption("A");
  const real = page.getByRole("region", { name: "Dal log reale", exact: true });
  await expect(real).toContainText("Nessun event log mappato");
  await real.getByRole("button", { name: "Importa un event log" }).click();
  await expect(page).toHaveURL(/panel=eventLog/);
  await expect(dock(page).getByRole("button", { name: /^sap-export\.csv/ })).toBeVisible();
});

test("a log with completions only is never compared on processing, and merged activities show once", async ({ page }, testInfo) => {
  const completions = {
    ...ANALYSIS,
    summary: {
      ...ANALYSIS.summary,
      timing: "complete_only",
      byActivity: [activity("A", "Verifica documentazione", 0, 2000), activity("A", "Verifica integrazioni", 0, 1000), activity("B", "Approva richiesta", 0, 1500)],
    },
  };
  await fixture(page, [ANALYSIS.event_log]);
  await page.route("http://127.0.0.1:8000/v1/workspace/event-logs/elog_e2e/analysis", (route) => route.fulfill({ json: completions }));
  const step = await openCompare(page);
  // Il report aggregato spiega perché non confronta i tempi, senza errori.
  const report = step.getByRole("region", { name: "Confronto con il log reale" });
  await expect(report).toContainText("Il log registra solo i completamenti");
  await expect(report.getByRole("table")).toHaveCount(0);
  await expect(step.getByText("Calcolo il confronto con il log")).toHaveCount(0);
  const activities = step.getByRole("table", { name: /Tempo di lavoro e attesa medi per attività/ });
  await expect(activities.getByRole("row")).toHaveCount(3);
  await expect(activities.getByRole("row", { name: /Verifica documentazione/ })).toContainText("dal log: Verifica documentazione, Verifica integrazioni");
  await expect(activities.getByRole("row", { name: /Approva richiesta/ })).toContainText("il log non registra l'inizio");
  await expect(step.getByRole("button", { name: "Mostra sul processo" })).toHaveCount(0);
  await expect(step.getByText("Il log ha 3 casi, la simulazione 300 casi", { exact: false })).toBeVisible();
  await expectPlainLanguage(step);
  await shoot(page, testInfo, "complete-only");

  await page.goto(`${studio}/workspace/42?panel=activity`);
  await page.getByLabel("Attività", { exact: true }).selectOption("B");
  const real = page.getByRole("region", { name: "Dal log reale", exact: true });
  await expect(real).toContainText("registra solo i completamenti");
  await expect(real.locator(".sim-gap")).toHaveCount(0);
});
