import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const studio = "/projects/imp-project/processes/imp-process/simulation";
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
  gateways: [{ element_id: "G_split", name: "Oltre 48 ore", type: "exclusiveGateway", branches: [
    { flow_id: "F_high", flow_name: "", target_name: "Approva" },
    { flow_id: "F_low", flow_name: "", target_name: "Paga" },
  ], escalation: { activity_id: "T_receive", after_seconds: 172800, normal_flow_id: "F_high" } }],
};
// Bozza pronta: ruolo confermato e assegnato, cosi' il test parte da salto e rilavorazione.
const draft = {
  scenarioName: "Escalation a 48 ore", totalCases: 50, arrivalIntervalMinutes: 30, defaultTaskMinutes: 15,
  resources: [{ id: "r1", name: "Ufficio acquisti", costPerHour: 40, amount: 2, parametersConfirmed: true }],
  tasks: Object.fromEntries(tasks.map((t) => [t.element_id, { meanMinutes: 20, distribution: "norm", resourceId: "r1", assignmentSource: "manual" }])),
  gateways: { G_split: { F_high: 50, F_low: 50 } },
  caseAttributes: [{ id: "attr-1", name: "tipo", kind: "category", categories: [{ value: "premium", percent: 30 }, { value: "standard", percent: 70 }] }],
};

const run = {
  id: 42, bpmn_model_id: "imp-model", process_id: "imp-process", scenario_name: "Escalation a 48 ore",
  engine: "prosimos", status: "completed", request: {}, scenario: {}, result: {}, outputs: [], error: null,
  created_at: "2026-10-08T09:00:00Z", completed_at: "2026-10-08T09:01:00Z",
  summary: { casesCompleted: 50, cycle: { avg: 3600, p50: 3400, p90: 5200, p95: 5600 }, waiting: { avg: 900, p95: 1500, share: 0.25 },
    processing: { avg: 2700 }, cost: { total: 3000, perCase: 60 }, throughputPerHour: 2,
    byActivity: [{ el: "T_approve", name: "Approva", wait: { avg: 600 } }, { el: "T_pay", name: "Paga", wait: { avg: 300 } }],
    byResource: [], bottleneck: { el: "T_approve", name: "Approva" } },
};
const replay = {
  schemaVersion: 1, meta: { start: "2026-10-08T09:00:00Z", durationSec: 300, totalCases: 1, sampledCases: 1, bucketSec: 100 },
  elements: { T_receive: { name: "Ricevi ordine" }, T_approve: { name: "Approva" }, T_pay: { name: "Paga" } },
  cases: [{ id: "0", cycleSec: 300, events: [{ el: "T_receive", enable: 0, start: 0, end: 100, res: "Ufficio" }, { el: "T_pay", enable: 100, start: 150, end: 300, res: "Ufficio" }] }],
  series: { t: [0, 100, 200], byElement: {}, byResource: {}, global: { wip: [1, 1, 0], queued: [0, 0, 0], done: [0, 0, 1], throughputPerHour: [0, 0, 12], costAccrued: [0, 5, 10], avgCycleSec: [0, 0, 300] } },
  flows: {},
};

/** Uno scenario scoperto da SIMOD: l'editor non rappresenta i suoi metadati, il server si'. */
const simodScenario = {
  process_model: "/tmp/simod/best_result/model.bpmn", model_type: "CRISP", granule_size: 60,
  resource_profiles: [{ id: "p", name: "Ufficio", resource_list: [{ id: "r1", name: "Ufficio acquisti", cost_per_hour: "40", amount: 2, calendar: "cal", assignedTasks: ["T_receive", "T_approve", "T_pay"] }] }],
  arrival_time_distribution: { distribution_name: "expon", distribution_params: [{ value: 1800 }, { value: 0 }, { value: 18000 }] },
  arrival_time_calendar: [{ from: "MONDAY", to: "FRIDAY", beginTime: "09:00:00", endTime: "17:00:00" }],
  gateway_branching_probabilities: [{ gateway_id: "G_split", probabilities: [{ path_id: "F_high", value: "0.3" }, { path_id: "F_low", value: "0.7" }] }],
  task_resource_distribution: tasks.map((t) => ({ task_id: t.element_id, resources: [{ resource_id: "r1", distribution_name: "fix", distribution_params: [{ value: t.element_id === "T_pay" ? 0 : 600 }] }] })),
  resource_calendars: [{ id: "cal", name: "Ufficio", time_periods: [{ from: "MONDAY", to: "FRIDAY", beginTime: "09:00:00", endTime: "17:00:00" }] }],
};

const imported = {
  bpmn_model_id: "imp-model",
  model: {
    schema_version: 1,
    arrival: { interarrival: { kind: "exponential", mean: 1800, minimum: 0, maximum: 18000 }, calendar_id: "arrival" },
    calendars: [{ id: "cal", name: "Ufficio", periods: [{ from_day: "MONDAY", to_day: "FRIDAY", begin: "09:00:00", end: "17:00:00" }] }],
    pools: [{ id: "p", name: "Ufficio", resources: [{ id: "r1", name: "Ufficio acquisti", cost_per_hour: 40, amount: 2, calendar_id: "cal" }] }],
    activities: tasks.map((t) => ({ element_id: t.element_id, name: t.name, assignments: [{ resource_id: "r1", duration: { kind: "fixed", value: 600 } }] })),
    gateways: [{ element_id: "G_split", branches: [{ flow_id: "F_high", probability: 0.3 }, { flow_id: "F_low", probability: 0.7 }] }],
    waits: [],
  },
  notes: [
    { kind: "info", topic: "instant_activity", message: "«Paga»: 1 risorsa su 1 la svolge in 0 secondi (attività istantanea nei dati).", element_id: "T_pay" },
    { kind: "approximated", topic: "missing_branch", message: "1 percorso senza probabilità nello scenario: vale 0, nessun caso lo prende.", element_id: "G_split" },
  ],
  simod: { process_model: simodScenario.process_model, model_type: "CRISP", granule_size: 60 },
};

type State = { modelRuns: unknown[]; importRequests: unknown[] };

/** CAL-01: SIMOD ha stimato la probabilita' di trovare libere le persone, fascia per fascia. */
const importedFuzzy = {
  ...imported,
  notes: [
    ...imported.notes,
    { kind: "info", topic: "probabilistic_calendars", message: "Probabilità di trovare libere le risorse stimata dai dati per 1 calendario, a fasce di 60 minuti.", element_id: null },
  ],
  simod: { ...imported.simod, model_type: "FUZZY", granule_size: { value: 60, time_unit: "MINUTES" } },
};

async function fixture(page: Page, { refuse = false, broken = false, fuzzy = false, delayMs = 0 } = {}): Promise<State> {
  const state: State = { modelRuns: [], importRequests: [] };
  await page.addInitScript((stored) => {
    Object.assign(window, { DELIR_API_BASE: "http://127.0.0.1:8000" });
    localStorage.setItem("delir-language", "it");
    if (!sessionStorage.getItem("seeded")) {
      localStorage.setItem("delir-sim-scenario:imp-model", stored);
      sessionStorage.setItem("seeded", "1");
    }
  }, JSON.stringify(draft));
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let data: unknown = [];
    if (path === "/v1/workspace/projects/imp-project") data = {
      id: "imp-project", client_id: "demo", client: "Azienda Demo", name: "Acquisti", phase: "AS-IS", status: "In corso", progress: 40, processes: 1,
      next_step: "Simulare lo scenario scoperto", milestones: [], open_issues: [], deliverables: [],
      process_items: [{ id: "imp-process", project_id: "imp-project", bpmn_model_id: "imp-model", name: "Ciclo passivo", stage: "AS-IS", status: "Da validare", owner: "Acquisti", readiness: 80 }],
    };
    else if (path.endsWith("/prosimos-import")) {
      state.importRequests.push(request.postDataJSON());
      if (delayMs) await new Promise((resolve) => setTimeout(resolve, delayMs));
      if (broken) {
        await route.fulfill({ status: 500, json: { ok: false, data: null, error: { code: "internal", message: "Internal Server Error", request_id: "r", origin: "server", retryable: false }, meta: { request_id: "r", duration_ms: 1 } } });
        return;
      }
      if (refuse) {
        await route.fulfill({ status: 400, json: { ok: false, data: null, error: { code: "bad_request", message: "Lo scenario usa l'elaborazione a lotti (batch_processing), che DeliR non simula ancora.", request_id: "r", origin: "server", retryable: false }, meta: { request_id: "r", duration_ms: 1 } } });
        return;
      }
      data = fuzzy ? importedFuzzy : imported;
    }
    else if (path.endsWith("/simulation-model-runs")) { state.modelRuns.push(request.postDataJSON()); data = { ...run, id: 77, status: "pending", scenario_name: "simod-scenario.json" }; }
    else if (path.endsWith("/simulation-template")) data = template;
    else if (path.endsWith("/simulation-provenance")) data = { has_discovery: false, elements: [] };
    else if (path.endsWith("/simulation-runs")) data = [];
    else if (path.endsWith("/imp-model")) data = { id: "imp-model", process_id: "imp-process", name: "Ciclo passivo", xml };
    await route.fulfill({ json: data });
  });
  return state;
}

async function upload(page: Page) {
  await page.goto(`${studio}/scenario`);
  await page.getByRole("button", { name: "Origine parametri" }).click();
  await page.getByRole("button", { name: /Importa una configurazione/ }).click();
  const dialog = page.getByRole("dialog", { name: "Importa una configurazione" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Seleziona configurazione").setInputFiles({
    name: "simod-scenario.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(simodScenario)),
  });
  return dialog;
}

test("a SIMOD scenario the editor cannot hold is read by the server and simulated as it is", async ({ page }) => {
  const state = await fixture(page);
  const dialog = await upload(page);

  const panel = dialog.getByRole("region", { name: "DeliR può simulare questo scenario così com'è" });
  await expect(panel).toBeVisible();
  await expect(panel).toContainText("Attività: 3 · Risorse: 1 · Decisioni: 1 · Attese: 0");
  await expect(panel).toContainText("ricavato da un event log con SIMOD");
  // C'e' una nota da verificare: il pannello non promette "senza modifiche".
  await expect(panel).toContainText("con gli adattamenti elencati sotto");
  // Prima cio' che va verificato, in parole semplici; il dettaglio tecnico su richiesta.
  await expect(panel.getByText("Da verificare")).toBeVisible();
  await expect(panel).toContainText("1 decisione con percorsi senza probabilità");
  await expect(panel).toContainText("1 attività che nei dati alcune persone svolgono in 0 secondi");
  expect(state.importRequests[0]).toMatchObject({ scenario: { model_type: "CRISP" } });

  const axe = await new AxeBuilder({ page }).include('[role="dialog"]').withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(axe.violations).toEqual([]);

  await panel.getByRole("button", { name: "Simula così com'è" }).click();
  await expect.poll(() => state.modelRuns.length).toBe(1);
  expect(state.modelRuns[0]).toMatchObject({ model: imported.model, scenario_name: "simod-scenario.json" });
  await expect(dialog).toBeHidden();
  await expect(page.getByText("Simulazione avviata")).toBeVisible();
});

test("a scenario the server cannot import explains why and changes nothing", async ({ page }) => {
  const state = await fixture(page, { refuse: true });
  const dialog = await upload(page);

  const alert = dialog.getByRole("alert");
  await expect(alert).toContainText("Il file non è stato applicato");
  await alert.getByText("Mostra il motivo tecnico").click();
  await expect(alert).toContainText("batch_processing");
  await expect(dialog.getByRole("button", { name: "Simula così com'è" })).toHaveCount(0);
  expect(state.modelRuns).toEqual([]);
});

test("a SIMOD scenario with probabilistic availability is explained and simulated as it is", async ({ page }) => {
  const state = await fixture(page, { fuzzy: true });
  const dialog = await upload(page);

  const panel = dialog.getByRole("region", { name: "DeliR può simulare questo scenario così com'è" });
  await expect(panel).toBeVisible();
  // Prima la frase per il consulente, il dettaglio tecnico solo su richiesta.
  await expect(panel).toContainText("Le persone non sono sempre libere nei loro orari");
  await expect(panel).not.toContainText("FUZZY");
  await expect(panel).not.toContainText("altra nota");

  await panel.getByRole("button", { name: "Simula così com'è" }).click();
  await expect.poll(() => state.modelRuns.length).toBe(1);
});

test("a technical failure of the server keeps the editor's own reason", async ({ page }) => {
  const state = await fixture(page, { broken: true });
  const dialog = await upload(page);

  const alert = dialog.getByRole("alert");
  await expect(alert).toContainText("Il file non è stato applicato");
  await alert.getByText("Mostra il motivo tecnico").click();
  await expect(alert).not.toContainText("Internal Server Error");
  await expect(alert.locator("details p")).not.toBeEmpty();
  expect(state.modelRuns).toEqual([]);
});

test("a slow answer for a file the consultant left behind never comes back", async ({ page }) => {
  const state = await fixture(page, { delayMs: 1500 });
  const dialog = await upload(page);
  await expect(dialog.getByRole("status").filter({ hasText: "Verifico lo scenario con DeliR" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect.poll(() => state.importRequests.length).toBe(1);
  await page.waitForTimeout(2000);

  await page.getByRole("button", { name: "Origine parametri" }).click();
  await page.getByRole("button", { name: /Importa una configurazione/ }).click();
  const reopened = page.getByRole("dialog", { name: "Importa una configurazione" });
  await expect(reopened).toBeVisible();
  await expect(reopened.getByRole("region", { name: "DeliR può simulare questo scenario così com'è" })).toHaveCount(0);
  expect(state.modelRuns).toEqual([]);
});
