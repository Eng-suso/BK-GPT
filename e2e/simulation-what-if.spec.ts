import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const studio = "/projects/whatif-project/processes/whatif-process/simulation";
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
const draft = {
  scenarioName: "Prova con una frase", totalCases: 50, arrivalIntervalMinutes: 30, defaultTaskMinutes: 15,
  resources: [{ id: "r1", name: "Ufficio acquisti", costPerHour: 40, amount: 2, parametersConfirmed: true }],
  tasks: Object.fromEntries(tasks.map((t) => [t.element_id, { meanMinutes: 20, distribution: "norm", resourceId: "r1", assignmentSource: "manual" }])),
  gateways: { G_split: { F_high: 50, F_low: 50 } },
};
const translation = {
  changes: [
    { kind: "resource_units", resource_id: "r1", units: 3 },
    { kind: "activity_duration", element_id: "T_approve", factor: 0.5, mean_minutes: null },
  ],
  not_understood: "anche il sabato",
  rejected: 0,
};

async function fixture(page: Page, whatIf: { status: number; json: unknown } = { status: 200, json: translation }) {
  const sent: unknown[] = [];
  await page.addInitScript((stored) => {
    Object.assign(window, { DELIR_API_BASE: "http://127.0.0.1:8000" });
    localStorage.setItem("delir-language", "it");
    if (!sessionStorage.getItem("seeded")) {
      localStorage.setItem("delir-sim-scenario:whatif-model", stored);
      sessionStorage.setItem("seeded", "1");
    }
  }, JSON.stringify(draft));
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let data: unknown = [];
    if (path === "/v1/workspace/projects/whatif-project") data = {
      id: "whatif-project", client_id: "demo", client: "Azienda Demo", name: "Acquisti", phase: "AS-IS", status: "In corso", progress: 40, processes: 1,
      next_step: "Provare un approvatore in più", milestones: [], open_issues: [], deliverables: [],
      process_items: [{ id: "whatif-process", project_id: "whatif-project", bpmn_model_id: "whatif-model", name: "Ciclo passivo", stage: "AS-IS", status: "Da validare", owner: "Acquisti", readiness: 80 }],
    };
    else if (path.endsWith("/simulation-what-if")) {
      sent.push(request.postDataJSON());
      await route.fulfill({ status: whatIf.status, json: whatIf.json });
      return;
    }
    else if (path.endsWith("/simulation-template")) data = template;
    else if (path.endsWith("/simulation-provenance")) data = { has_discovery: false, elements: [] };
    else if (path.endsWith("/simulation-claims")) data = { sources: 0, activities: [] };
    else if (path.endsWith("/simulation-runs") && request.method() === "POST") data = {
      id: 42, bpmn_model_id: "whatif-model", process_id: "whatif-process", scenario_name: "Prova", engine: "prosimos", status: "pending",
      request: request.postDataJSON(), scenario: {}, result: {}, outputs: [], error: null, summary: null, created_at: "2026-10-25T09:00:00Z", completed_at: null,
    };
    else if (path.endsWith("/simulation-runs")) data = [];
    else if (path.endsWith("/whatif-model")) data = { id: "whatif-model", process_id: "whatif-process", name: "Ciclo passivo", xml };
    await route.fulfill({ json: data });
  });
  return sent;
}

test("a sentence becomes a preview, and only applying changes the draft (SIM-23)", async ({ page }, testInfo) => {
  const sent = await fixture(page);
  const runs: string[] = [];
  page.on("request", (req) => { if (req.method() === "POST" && req.url().endsWith("/simulation-runs")) runs.push(req.url()); });
  await page.goto(`${studio}/scenario`);

  const box = page.getByTestId("sim-what-if");
  await box.getByRole("textbox", { name: "Cosa vuoi provare" }).fill("Un approvatore in più, Approva dura la metà e lavoriamo anche il sabato");
  await box.getByRole("button", { name: "Traduci" }).click();

  await expect(box).toContainText("Modifiche proposte");
  await expect(box).toContainText("Ufficio acquisti");
  await expect(box).toContainText("2 → 3");
  await expect(box).toContainText("Approva");
  await expect(box).toContainText("20 → 10");
  await expect(box).toContainText("Non tradotto: «anche il sabato»");
  await expect(box).toContainText("I ruoli cambiati vanno riconfermati");
  await expect(box).not.toContainText("sì → no");
  expect(sent[0]).toMatchObject({
    sentence: "Un approvatore in più, Approva dura la metà e lavoriamo anche il sabato",
    activities: expect.arrayContaining([{ id: "T_approve", name: "Approva" }]),
    resources: [{ id: "r1", name: "Ufficio acquisti", units: 2 }],
  });
  await box.scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath("what-if-preview.png"), animations: "disabled" });
  const axe = await new AxeBuilder({ page }).include('[data-testid="sim-what-if"]').withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(axe.violations).toEqual([]);

  await box.getByRole("button", { name: "Applica alla bozza" }).click();
  await expect(box.getByRole("status")).toContainText("Modifiche applicate alla bozza");
  expect(runs).toEqual([]);
  await expect(page.getByLabel("Unità disponibili").first()).toHaveValue("3");

  // Una capacità cambiata si riconferma, come dopo un esperimento dell'advisor; da tastiera,
  // perché l'intestazione fissa della sezione copre il bottone nel pannello stretto.
  await page.getByRole("button", { name: "Conferma capacità e costo" }).first().focus();
  await page.keyboard.press("Enter");
  const request = page.waitForRequest((req) => req.method() === "POST" && req.url().endsWith("/simulation-runs"));
  await page.getByRole("button", { name: "Avvia simulazione", exact: true }).click();
  const body = (await request).postDataJSON();
  expect(body.resources[0].amount).toBe(3);
  expect(body.tasks.find((t: { element_id: string }) => t.element_id === "T_approve").mean_seconds).toBe(600);
});

test("without the model key the panel says so and the draft stays as it is", async ({ page }) => {
  await fixture(page, { status: 503, json: { ok: false, data: null, error: { code: "service_unavailable", message: "Il what-if in linguaggio naturale richiede la chiave del modello." } } });
  await page.goto(`${studio}/scenario`);

  const box = page.getByTestId("sim-what-if");
  await box.getByRole("textbox", { name: "Cosa vuoi provare" }).fill("Un approvatore in più");
  await box.getByRole("textbox", { name: "Cosa vuoi provare" }).press("Enter");
  await expect(box.getByRole("alert")).toContainText("richiede la chiave del modello");
  await expect(box).not.toContainText("Modifiche proposte");
});
