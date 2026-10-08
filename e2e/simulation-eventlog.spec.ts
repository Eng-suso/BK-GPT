import { test, expect, type Page, type Request } from "@playwright/test";
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
    byActivity: [activity("A", "Verifica documentazione", 800, 1150), activity("B", "Approva richiesta", 600, 900), activity(null, "Archivia", 0, 60)],
  },
};

type Fixture = { mappingRequests: Request[] };

async function fixture(page: Page, logs: unknown[]): Promise<Fixture> {
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
    else if (path.endsWith("/simulation-runs")) data = [run];
    else if (path.endsWith("/replay")) data = { run_id: 42, schema_version: 1, replay };
    else if (path.endsWith("/model")) data = { run_id: 42, model: null };
    else if (path.endsWith("/simulation-template")) data = { tasks: [{ element_id: "A", name: "Verifica documentazione", type: "task" }, { element_id: "B", name: "Approva richiesta", type: "task" }], resources: [], gateways: [] };
    else if (path.endsWith("/experiments")) data = { bottleneck_el: "A", bottleneck_name: "Verifica documentazione", factors: {}, experiments: [] };
    else if (path.endsWith("/simulation-provenance")) data = { has_discovery: false, elements: [] };
    else if (path.endsWith("/eventlog-model")) data = { id: "eventlog-model", process_id: "eventlog-process", name: "Modello demo", xml };
    else if (path === "/v1/workspace/processes/eventlog-process/event-logs") data = logs;
    else if (path === "/v1/workspace/event-logs/elog_e2e/preview") data = { format: "csv", delimiter: ";", columns: COLUMNS, row_count: 9, sample_rows: [["P-1", "Verifica documentazione", "2026-01-05T09:00", "2026-01-05T09:10", "2026-01-05T09:30", "anna"]] };
    else if (path === "/v1/workspace/event-logs/elog_e2e/analysis") data = ANALYSIS;
    else if (path === "/v1/workspace/event-logs/elog_e2e/mapping") { state.mappingRequests.push(request); data = ANALYSIS; }
    await route.fulfill({ json: data });
  });
  return state;
}

function dock(page: Page) {
  return page.locator(".sim-studio-dock");
}

test("the wizard maps the enablement column of an exported log", async ({ page }) => {
  const state = await fixture(page, [LOG]);
  await page.goto(`${studio}/dashboard/42?panel=eventLog`);
  await dock(page).getByRole("button", { name: /^sap-export\.csv/ }).click();

  const caseId = dock(page).getByRole("group", { name: "Identificativo del caso" });
  await caseId.getByRole("combobox").selectOption("Pratica");
  await dock(page).getByRole("group", { name: "Attività", exact: true }).getByRole("combobox").selectOption("Attivita");
  await dock(page).getByLabel("Fine (o completamento)").selectOption("Fine");
  await dock(page).getByLabel(/^Inizio/).selectOption("Inizio");
  const enable = dock(page).getByLabel("Abilitazione");
  await expect(enable).toHaveAccessibleDescription(/enable_time/);
  await enable.selectOption("Pronta");
  await dock(page).getByLabel(/^Risorsa/).selectOption("Utente");
  await expect(dock(page).getByRole("region", { name: "Anteprima delle prime righe" }).locator("th[data-used]")).toHaveCount(6);
  await dock(page).getByRole("button", { name: "Avanti" }).click();
  await dock(page).getByRole("button", { name: "Applica il mapping" }).click();

  await expect.poll(() => state.mappingRequests.length).toBe(1);
  expect(state.mappingRequests[0].postDataJSON().mapping).toEqual(MAPPING);
  await expect(dock(page).getByRole("region", { name: "Qualità e KPI" })).toBeVisible();
});

test("real against simulated: verdict, KPIs by activity and gaps on the process", async ({ page }) => {
  await fixture(page, [ANALYSIS.event_log]);
  await page.goto(`${studio}/dashboard/42?panel=eventLog`);
  await dock(page).getByRole("button", { name: /^sap-export\.csv/ }).click();
  await dock(page).getByRole("button", { name: /Reale contro simulato$/ }).click();

  const step = dock(page).getByRole("region", { name: "Reale contro simulato" });
  await expect(step.getByLabel("Run simulato")).toHaveValue("42");
  // Cycle medio +5%, P90 +10%: vicino al reale.
  await expect(step.getByRole("status").filter({ hasText: "Il simulato è vicino al reale" })).toContainText("+5%");
  await expect(step.getByText("Il log ha 3 casi, il run 300", { exact: false })).toBeVisible();
  const processTable = step.getByRole("table").first();
  await expect(processTable.getByRole("row", { name: /Cycle time medio/ })).toContainText("+5%");
  await expect(processTable.getByRole("row", { name: /Costo per caso/ })).toContainText("il log non ha costi");

  const activities = step.getByRole("table", { name: /Lavorazione e attesa medie per attività/ });
  await expect(activities.getByRole("row")).toHaveCount(3);
  await expect(activities.getByRole("row", { name: /Approva richiesta/ })).toContainText("+67%");
  await expect(activities.getByRole("row", { name: /Verifica documentazione/ })).toContainText("+4%");
  await expect(step.getByText(/1 attività del log senza elemento del modello/)).toBeVisible();

  const show = step.getByRole("button", { name: "Mostra sul processo" });
  await show.click();
  await expect(show).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator('.djs-element[data-element-id="B"]')).toHaveClass(/sim-fidelity-far/);
  await expect(page.locator('.djs-element[data-element-id="A"]')).toHaveClass(/sim-fidelity-close/);
  await expect(page.locator(".sim-process-legend")).toContainText("Scarto reale contro simulato");
  await expect(page.locator(".sim-process-legend")).toContainText("oltre ±25%");

  const axe = await new AxeBuilder({ page }).include(".sim-studio-dock").withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(axe.violations).toEqual([]);

  await show.click();
  await expect(page.locator('.djs-element[data-element-id="B"]')).not.toHaveClass(/sim-fidelity-far/);
  await show.click();
  await page.getByRole("button", { name: "Chiudi pannello", exact: true }).click();
  await expect(page.locator('.djs-element[data-element-id="B"]')).not.toHaveClass(/sim-fidelity-far/);
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
