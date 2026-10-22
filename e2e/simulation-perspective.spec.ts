import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const studio = "/projects/ops-project/processes/ops-process/simulation";
const xml = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_rules" targetNamespace="https://example.test/rules">
<bpmn:process id="Process_rules" isExecutable="false"><bpmn:startEvent id="Start" /><bpmn:task id="T_receive" name="Ricevi ordine" /><bpmn:exclusiveGateway id="G_split" name="Importo alto?" /><bpmn:task id="T_approve" name="Approva" /><bpmn:task id="T_pay" name="Paga" /><bpmn:endEvent id="End" />
<bpmn:sequenceFlow id="F0" sourceRef="Start" targetRef="T_receive" /><bpmn:sequenceFlow id="F1" sourceRef="T_receive" targetRef="G_split" /><bpmn:sequenceFlow id="F_high" sourceRef="G_split" targetRef="T_approve" /><bpmn:sequenceFlow id="F_low" sourceRef="G_split" targetRef="T_pay" /><bpmn:sequenceFlow id="F2" sourceRef="T_approve" targetRef="T_pay" /><bpmn:sequenceFlow id="F3" sourceRef="T_pay" targetRef="End" /></bpmn:process>
<bpmndi:BPMNDiagram id="Diagram_rules"><bpmndi:BPMNPlane id="Plane_rules" bpmnElement="Process_rules">
<bpmndi:BPMNShape id="Start_di" bpmnElement="Start"><dc:Bounds x="60" y="120" width="36" height="36" /></bpmndi:BPMNShape><bpmndi:BPMNShape id="T_receive_di" bpmnElement="T_receive"><dc:Bounds x="140" y="98" width="120" height="80" /></bpmndi:BPMNShape><bpmndi:BPMNShape id="G_split_di" bpmnElement="G_split" isMarkerVisible="true"><dc:Bounds x="300" y="113" width="50" height="50" /></bpmndi:BPMNShape><bpmndi:BPMNShape id="T_approve_di" bpmnElement="T_approve"><dc:Bounds x="400" y="20" width="120" height="80" /></bpmndi:BPMNShape><bpmndi:BPMNShape id="T_pay_di" bpmnElement="T_pay"><dc:Bounds x="560" y="98" width="120" height="80" /></bpmndi:BPMNShape><bpmndi:BPMNShape id="End_di" bpmnElement="End"><dc:Bounds x="720" y="120" width="36" height="36" /></bpmndi:BPMNShape>
<bpmndi:BPMNEdge id="F0_di" bpmnElement="F0"><di:waypoint x="96" y="138" /><di:waypoint x="140" y="138" /></bpmndi:BPMNEdge><bpmndi:BPMNEdge id="F1_di" bpmnElement="F1"><di:waypoint x="260" y="138" /><di:waypoint x="300" y="138" /></bpmndi:BPMNEdge><bpmndi:BPMNEdge id="F_high_di" bpmnElement="F_high"><di:waypoint x="325" y="113" /><di:waypoint x="325" y="60" /><di:waypoint x="400" y="60" /></bpmndi:BPMNEdge><bpmndi:BPMNEdge id="F_low_di" bpmnElement="F_low"><di:waypoint x="350" y="138" /><di:waypoint x="560" y="138" /></bpmndi:BPMNEdge><bpmndi:BPMNEdge id="F2_di" bpmnElement="F2"><di:waypoint x="520" y="60" /><di:waypoint x="620" y="60" /><di:waypoint x="620" y="98" /></bpmndi:BPMNEdge><bpmndi:BPMNEdge id="F3_di" bpmnElement="F3"><di:waypoint x="680" y="138" /><di:waypoint x="720" y="138" /></bpmndi:BPMNEdge>
</bpmndi:BPMNPlane></bpmndi:BPMNDiagram></bpmn:definitions>`;

const tasks = [
  { element_id: "T_receive", name: "Ricevi ordine", type: "task" },
  { element_id: "T_approve", name: "Approva", type: "task" },
  { element_id: "T_pay", name: "Paga", type: "task" },
];
const template = {
  tasks,
  resources: [],
  standard_calendar: { id: "delir-calendar-standard", name: "Standard", periods: [{ from_day: "MONDAY", to_day: "FRIDAY", begin: "09:00", end: "17:00" }] },
  gateways: [{ element_id: "G_split", name: "Importo alto?", type: "exclusiveGateway", branches: [
    { flow_id: "F_high", flow_name: "", target_name: "Approva" },
    { flow_id: "F_low", flow_name: "", target_name: "Paga" },
  ] }],
};
// Bozza pronta: ruolo confermato e assegnato, cosi' il test parte dalle regole.
const draft = {
  scenarioName: "Venti giorni", totalCases: 50, arrivalIntervalMinutes: 30, defaultTaskMinutes: 15,
  resources: [{ id: "r1", name: "Ufficio acquisti", costPerHour: 40, amount: 2, parametersConfirmed: true }],
  tasks: Object.fromEntries(tasks.map((t) => [t.element_id, { meanMinutes: 20, distribution: "norm", resourceId: "r1", assignmentSource: "manual" }])),
  gateways: { G_split: { F_high: 50, F_low: 50 } },
};

const run = {
  id: 42, bpmn_model_id: "ops-model", process_id: "ops-process", scenario_name: "Venti giorni",
  engine: "prosimos", status: "completed", request: {}, scenario: {}, result: {}, outputs: [], error: null,
  created_at: "2026-10-08T09:00:00Z", completed_at: "2026-10-08T09:01:00Z",
  summary: { casesCompleted: 50, cycle: { avg: 3600, p50: 3400, p90: 5200, p95: 5600 }, waiting: { avg: 900, p95: 1500, share: 0.25 },
    processing: { avg: 2700 }, cost: { total: 3000, perCase: 60 }, throughputPerHour: 2,
    byActivity: [{ el: "T_approve", name: "Approva", count: 25, wait: { avg: 600 }, queue: { avg: 1.6, max: 4 } }, { el: "T_pay", name: "Paga", count: 50, wait: { avg: 100 } }, { el: "T_receive", name: "Ricevi ordine", count: 50, wait: { avg: 0 } }],
    byResource: [], bottleneck: { el: "T_approve", name: "Approva" },
    horizon: { days: 20, arrivedCases: 330, completedCases: 318, openCases: 12, covered: true } },
};
const replay = {
  schemaVersion: 1, meta: { start: "2026-10-08T09:00:00Z", durationSec: 300, totalCases: 1, sampledCases: 1, bucketSec: 100 },
  elements: { T_receive: { name: "Ricevi ordine" }, T_approve: { name: "Approva" }, T_pay: { name: "Paga" } },
  cases: [{ id: "0", cycleSec: 300, events: [{ el: "T_receive", enable: 0, start: 0, end: 100, res: "Ufficio" }, { el: "T_pay", enable: 100, start: 150, end: 300, res: "Ufficio" }] }],
  series: { t: [0, 100, 200], byElement: {}, byResource: {}, global: { wip: [1, 1, 0], queued: [0, 0, 0], done: [0, 0, 1], throughputPerHour: [0, 0, 12], costAccrued: [0, 5, 10], avgCycleSec: [0, 0, 300] } },
  flows: {},
};
const rule = (op: string) => ({ any_of: [[{ attribute: "importo", operator: op, value: 5000 }]] });
const model = {
  schema_version: 1,
  arrival: { interarrival: { kind: "exponential", mean: 1800, minimum: 0, maximum: 18000 }, calendar_id: "delir-calendar-standard" },
  calendars: [{ id: "delir-calendar-standard", name: "Standard", periods: [{ from_day: "MONDAY", to_day: "FRIDAY", begin: "09:00:00", end: "17:00:00" }] }],
  pools: [{ id: "p", name: "Ufficio", resources: [{ id: "r1", name: "Ufficio acquisti", cost_per_hour: 40, amount: 2, calendar_id: "delir-calendar-standard" }] }],
  activities: tasks.map((t) => ({ element_id: t.element_id, name: t.name, assignments: [{ resource_id: "r1", duration: { kind: "normal", mean: 1200, std: 120, minimum: 840, maximum: 1560 }, provenance: { origin: "manual" } }] })),
  gateways: [{ element_id: "G_split", branches: [
    { flow_id: "F_high", probability: 0.5, condition: rule(">"), provenance: { origin: "manual" } },
    { flow_id: "F_low", probability: 0.5, condition: rule("<="), provenance: { origin: "manual" } },
  ] }],
  case_attributes: [{ name: "importo", distribution: { kind: "uniform", minimum: 100, maximum: 12000 }, provenance: { origin: "manual" } }],
};

const started: string[] = [];
const experiments = { bottleneck_el: "T_approve", bottleneck_name: "Approva", factors: { waitingContribution: 0.6 }, experiments: [
  { kind: "add_resource", pool_id: "p", pool_name: "Ufficio acquisti", from_amount: 2, to_amount: 3, target_el: "T_approve", target_name: "Approva", rationale: "Approva aspetta l'ufficio acquisti.", estimate: { cycle_pct: -0.2, cost_pct: 0.05 } },
] };

async function fixture(page: Page, runs: unknown[] = [], stored: object = draft) {
  await page.addInitScript((stored) => {
    Object.assign(window, { DELIR_API_BASE: "http://127.0.0.1:8000" });
    localStorage.setItem("delir-language", "it");
    if (!sessionStorage.getItem("seeded")) {
      localStorage.setItem("delir-sim-scenario:ops-model", stored);
      sessionStorage.setItem("seeded", "1");
    }
  }, JSON.stringify(stored));
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let data: unknown = [];
    if (path === "/v1/workspace/projects/ops-project") data = {
      id: "ops-project", client_id: "demo", client: "Azienda Demo", name: "Acquisti", phase: "AS-IS", status: "In corso", progress: 40, processes: 1,
      next_step: "Simulare la soglia", milestones: [], open_issues: [], deliverables: [],
      process_items: [{ id: "ops-process", project_id: "ops-project", bpmn_model_id: "ops-model", name: "Ciclo passivo", stage: "AS-IS", status: "Da validare", owner: "Acquisti", readiness: 80 }],
    };
    else if (path.endsWith("/simulation-template")) data = template;
    else if (path.endsWith("/simulation-provenance")) data = { has_discovery: false, elements: [] };
    // Solo cio' che avvia un run: le affermazioni del cliente si leggono in POST.
    else if (request.method() === "POST" && /\/simulation-(runs|sensitivity|replications)$/.test(path)) { started.push(path); data = { ...run, status: "pending" }; }
    else if (path.endsWith("/simulation-runs")) data = runs;
    else if (path.endsWith("/replay")) data = { run_id: 42, schema_version: 1, replay };
    else if (path.endsWith("/simulation-runs/42/model")) data = { run_id: 42, model };
    else if (path.endsWith("/experiments")) data = experiments;
    else if (path.endsWith("/ops-model")) data = { id: "ops-model", process_id: "ops-process", name: "Ciclo passivo", xml };
    await route.fulfill({ json: data });
  });
}

test("switching to Operations keeps the scenario and shows health, queues and what to try", async ({ page }) => {
  started.length = 0;
  await fixture(page, [run]);
  await page.goto(`${studio}/overview`);
  const tools = page.getByRole("group", { name: "Strumenti della simulazione" });
  await expect(tools.getByRole("button", { name: "Scenario", exact: true })).toBeVisible();
  const draftBefore = await page.evaluate(() => localStorage.getItem("delir-sim-scenario:ops-model"));

  const perspective = page.getByRole("group", { name: "Prospettiva" });
  await perspective.getByRole("button", { name: "Operations" }).click();
  await expect(perspective.getByRole("button", { name: "Operations" })).toHaveAttribute("aria-pressed", "true");
  await expect(page).toHaveURL(/perspective=operations/);

  // Niente strumenti che configurano modello o dati.
  for (const name of ["Scenario", "Workspace", "Event log"]) await expect(tools.getByRole("button", { name, exact: true })).toHaveCount(0);
  await expect(tools.getByRole("button", { name: "Risultati", exact: true })).toBeVisible();

  const brief = page.locator("[data-sim-operations-brief]");
  await expect(brief.getByRole("heading", { name: "Dove si accumula il lavoro" })).toBeVisible();
  const rows = brief.getByRole("listitem");
  await expect(rows).toHaveCount(2);
  await expect(rows.first()).toContainText("Approva");
  await expect(rows.first()).toContainText("75% del totale");
  await expect(rows.first()).toContainText("In media 1,6 casi in coda");
  // Ipotesi e intervalli restano al consulente.
  await expect(page.locator("[data-sim-sensitivity]")).toHaveCount(0);

  const axe = await new AxeBuilder({ page }).include("[data-sim-operations-brief]").include("[data-sim-perspective]").withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(axe.violations).toEqual([]);

  await brief.getByRole("button", { name: "Cosa provare" }).click();
  await expect(page.getByRole("button", { name: "Prepara lo scenario con il consulente" })).toBeVisible();

  // Il cambio prospettiva non ha avviato run e non ha toccato la bozza.
  expect(started).toEqual([]);
  expect(await page.evaluate(() => localStorage.getItem("delir-sim-scenario:ops-model"))).toBe(draftBefore);

  await perspective.getByRole("button", { name: "Consulente" }).click();
  await expect(page).not.toHaveURL(/perspective=/);
  await expect(tools.getByRole("button", { name: "Scenario", exact: true })).toBeVisible();
});

test("an experiment from Operations opens the scenario in the consultant view", async ({ page }) => {
  started.length = 0;
  await fixture(page, [run]);
  await page.goto(`${studio}/workspace/42?perspective=operations&panel=insights&view=final`);
  await page.getByRole("button", { name: "Prepara lo scenario con il consulente" }).click();
  await expect(page).not.toHaveURL(/perspective=/);
  await expect(page).toHaveURL(/panel=scenario/);
  await expect(page.getByRole("group", { name: "Prospettiva" }).getByRole("button", { name: "Consulente" })).toHaveAttribute("aria-pressed", "true");
  expect(started).toEqual([]);
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test("the perspective switch keeps named buttons", async ({ page }) => {
    await fixture(page, [run]);
    await page.goto(`${studio}/overview`);
    const perspective = page.getByRole("group", { name: "Prospettiva" });
    await expect(perspective.getByRole("button", { name: "Operations" })).toBeVisible();
    const box = await perspective.boundingBox();
    expect(box && box.x + box.width).toBeLessThanOrEqual(390);
    const axe = await new AxeBuilder({ page }).include("[data-sim-perspective]").withTags(["wcag2a", "wcag2aa"]).analyze();
    expect(axe.violations).toEqual([]);
  });
});
