import { readFileSync } from "node:fs";

import { test, expect, type Locator, type Page, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * IMP-01: un file con arrivi esponenziali e massimo vicino alla media. Prosimos 2.1
 * scarta gli intervalli oltre il massimo: i casi arrivano piu' fitti di quanto scritto.
 * Il consulente lo legge all'import, in parole sue, con cosa fare; lo scenario resta com'era.
 */
const studio = "/projects/imp-project/processes/imp-process/simulation";
const DATASET = "datasets/extraneous-delays/inputs/synthetic/Procure_to_Pay";
const procureXml = readFileSync(`${DATASET}.bpmn`, "utf8");
const procureFile = readFileSync(`${DATASET}.json`, "utf8");
// Risposte del backend vero (e2e/fixtures/imp-01/generate.py).
const procureTemplate = JSON.parse(readFileSync("e2e/fixtures/imp-01/procure-to-pay.template.json", "utf8"));
const procureImport = JSON.parse(readFileSync("e2e/fixtures/imp-01/procure-to-pay.import.json", "utf8"));

const JARGON = /expon|esponenzial|distribuzion|prosimos|troncat|node-/i;

/** Un processo piccolo che l'editor rappresenta: il file passa dall'editor, non dal server. */
const smallXml = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="D" targetNamespace="https://example.test/imp01">
<bpmn:process id="P" isExecutable="false"><bpmn:startEvent id="Start" /><bpmn:task id="T_order" name="Registra ordine" /><bpmn:task id="T_pay" name="Paga fattura" /><bpmn:endEvent id="End" />
<bpmn:sequenceFlow id="F0" sourceRef="Start" targetRef="T_order" /><bpmn:sequenceFlow id="F1" sourceRef="T_order" targetRef="T_pay" /><bpmn:sequenceFlow id="F2" sourceRef="T_pay" targetRef="End" /></bpmn:process>
<bpmndi:BPMNDiagram id="DD"><bpmndi:BPMNPlane id="PL" bpmnElement="P">
<bpmndi:BPMNShape id="Start_di" bpmnElement="Start"><dc:Bounds x="60" y="120" width="36" height="36" /></bpmndi:BPMNShape><bpmndi:BPMNShape id="T_order_di" bpmnElement="T_order"><dc:Bounds x="140" y="98" width="120" height="80" /></bpmndi:BPMNShape><bpmndi:BPMNShape id="T_pay_di" bpmnElement="T_pay"><dc:Bounds x="320" y="98" width="120" height="80" /></bpmndi:BPMNShape><bpmndi:BPMNShape id="End_di" bpmnElement="End"><dc:Bounds x="500" y="120" width="36" height="36" /></bpmndi:BPMNShape>
<bpmndi:BPMNEdge id="F0_di" bpmnElement="F0"><di:waypoint x="96" y="138" /><di:waypoint x="140" y="138" /></bpmndi:BPMNEdge><bpmndi:BPMNEdge id="F1_di" bpmnElement="F1"><di:waypoint x="260" y="138" /><di:waypoint x="320" y="138" /></bpmndi:BPMNEdge><bpmndi:BPMNEdge id="F2_di" bpmnElement="F2"><di:waypoint x="440" y="138" /><di:waypoint x="500" y="138" /></bpmndi:BPMNEdge>
</bpmndi:BPMNPlane></bpmndi:BPMNDiagram></bpmn:definitions>`;
const smallTasks = [{ element_id: "T_order", name: "Registra ordine", type: "task" }, { element_id: "T_pay", name: "Paga fattura", type: "task" }];
const smallTemplate = {
  tasks: smallTasks, resources: [], gateways: [], waits: [],
  standard_calendar: { id: "delir-calendar-standard", name: "Standard", periods: [{ from_day: "MONDAY", to_day: "FRIDAY", begin: "09:00", end: "17:00" }] },
};
const week = [{ from: "MONDAY", to: "SUNDAY", beginTime: "00:00:00", endTime: "23:59:59.999" }];
/** Gli stessi arrivi di Procure_to_Pay, in un file scritto a mano che l'editor sa leggere. */
const smallFile = {
  resource_profiles: [{ id: "p", name: "Acquisti", resource_list: [{ id: "r1", name: "Ufficio acquisti", cost_per_hour: 40, amount: 2, calendar: "cal", assignedTasks: ["T_order", "T_pay"] }] }],
  arrival_time_distribution: { distribution_name: "expon", distribution_params: [{ value: 1805 }, { value: 5 }, { value: 3600 }] },
  arrival_time_calendar: week,
  gateway_branching_probabilities: [],
  task_resource_distribution: smallTasks.map((t) => ({ task_id: t.element_id, resources: [{ resource_id: "r1", distribution_name: "fix", distribution_params: [{ value: 600 }] }] })),
  resource_calendars: [{ id: "cal", name: "Sempre", time_periods: week }],
};

const draft = { scenarioName: "Ciclo passivo", totalCases: 50, arrivalIntervalMinutes: 30, defaultTaskMinutes: 15, resources: [], tasks: {}, gateways: {} };
const queued = {
  id: 77, bpmn_model_id: "imp-model", process_id: "imp-process", scenario_name: "Procure_to_Pay.json", engine: "prosimos", status: "pending",
  request: {}, scenario: {}, result: {}, outputs: [], error: null, created_at: "2026-11-24T09:00:00Z", completed_at: null,
};

type State = { importRequests: Array<{ scenario: Record<string, unknown> }>; modelRuns: Array<{ model: typeof procureImport.model }> };

async function fixture(page: Page, kind: "procure" | "small"): Promise<State> {
  const state: State = { importRequests: [], modelRuns: [] };
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
      next_step: "Simulare il ciclo passivo", milestones: [], open_issues: [], deliverables: [],
      process_items: [{ id: "imp-process", project_id: "imp-project", bpmn_model_id: "imp-model", name: "Ciclo passivo", stage: "AS-IS", status: "Da validare", owner: "Acquisti", readiness: 80 }],
    };
    else if (path.endsWith("/prosimos-import")) { state.importRequests.push(request.postDataJSON()); data = procureImport; }
    else if (path.endsWith("/simulation-model-runs")) { state.modelRuns.push(request.postDataJSON()); data = queued; }
    else if (path.endsWith("/simulation-template")) data = kind === "procure" ? procureTemplate : smallTemplate;
    else if (path.endsWith("/simulation-provenance")) data = { has_discovery: false, elements: [] };
    else if (path.endsWith("/simulation-runs")) data = [];
    else if (path.endsWith("/imp-model")) data = { id: "imp-model", process_id: "imp-process", name: "Ciclo passivo", xml: kind === "procure" ? procureXml : smallXml };
    await route.fulfill({ json: data });
  });
  return state;
}

async function upload(page: Page, name: string, content: string): Promise<Locator> {
  await page.goto(`${studio}/scenario`);
  await page.getByRole("button", { name: "Origine parametri" }).click();
  await page.getByRole("button", { name: /Importa una configurazione/ }).click();
  const dialog = page.getByRole("dialog", { name: "Importa una configurazione" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Seleziona configurazione").setInputFiles({ name, mimeType: "application/json", buffer: Buffer.from(content) });
  return dialog;
}

/** Gate UX (DELIR_UX_SHOTS): la schermata com'e', poi l'elemento intero per leggerne ogni riga. */
async function shoot(page: Page, testInfo: TestInfo, name: string, element: Locator) {
  if (!process.env.DELIR_UX_SHOTS) return;
  const path = `${process.env.DELIR_UX_SHOTS}/${name}-${testInfo.project.name}`;
  if (page.viewportSize()!.width > 1199) await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({ path: `${path}.png` });
  await element.screenshot({ path: `${path}-panel.png` });
}

test("Procure_to_Pay warns that cases will arrive more often and is simulated as it is", async ({ page }, testInfo) => {
  const state = await fixture(page, "procure");
  const dialog = await upload(page, "Procure_to_Pay.json", procureFile);

  // Nessuna domanda sugli identificativi: i punti di ricongiungimento non hanno scelte.
  await expect(dialog.getByText("Associa gli elementi del file al BPMN corrente")).toHaveCount(0);
  const panel = dialog.getByRole("region", { name: "DeliR può simulare questo scenario così com'è" });
  await expect(panel).toBeVisible();
  // DeliR non ha adattato nulla: dice "senza modifiche" e chiede di leggere il punto da verificare.
  await expect(panel).toContainText("può simularlo senza modifiche: prima di usare i risultati, leggi il punto da verificare");
  await expect(panel).not.toContainText("adattamenti");

  const check = panel.getByRole("status").filter({ hasText: "Da verificare" });
  await expect(check).toContainText("Nella simulazione i casi arriveranno più spesso di quanto indica il file");
  await expect(check).toContainText("code e attese risulteranno più lunghe di quelle reali");
  await expect(check).toContainText("correggi gli arrivi nel file e importalo di nuovo");
  await check.getByText("Dettagli (1)").click();
  await expect(check).toContainText("in media arriva un caso ogni 21 minuti, circa il 45% di casi in più");
  await expect(check).toContainText("usa un intervallo fisso di 30 minuti");
  await expect(check).toContainText("porta il massimo ad almeno 2,5 ore");
  expect(await check.innerText()).not.toMatch(JARGON);
  await shoot(page, testInfo, "procure-to-pay-import", panel);

  const axe = await new AxeBuilder({ page }).include('[role="dialog"]').withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(axe.violations).toEqual([]);

  // Lo scenario resta com'era: il file va al server cosi' com'e' e torna al run identico.
  expect(state.importRequests[0].scenario.arrival_time_distribution).toEqual(JSON.parse(procureFile).arrival_time_distribution);
  await panel.getByRole("button", { name: "Simula così com'è" }).click();
  await expect.poll(() => state.modelRuns.length).toBe(1);
  expect(state.modelRuns[0].model.arrival.interarrival).toEqual({ kind: "exponential", mean: 1805, minimum: 5, maximum: 3600 });
});

test("a file the editor can hold warns in Arrivals and offers a maximum that removes the effect", async ({ page }, testInfo) => {
  await fixture(page, "small");
  const dialog = await upload(page, "ciclo-passivo.json", JSON.stringify(smallFile));
  await expect(dialog).toBeHidden();
  await expect(page.getByText("Configurazione applicata")).toBeVisible();
  await expect(page.getByText("Gli arrivi del file renderanno i casi più frequenti del previsto")).toBeVisible();

  const arrivals = page.locator("[data-sim-arrivals]");
  const notice = arrivals.getByRole("status").filter({ hasText: "I casi arriveranno più spesso del previsto" });
  await notice.scrollIntoViewIfNeeded();
  await expect(notice).toContainText("Con un massimo di 1h fra due arrivi");
  await expect(notice).toContainText("in media arriva un caso ogni 21 min invece che ogni 30 min, circa il 45% di casi in più");
  expect(await notice.innerText()).not.toMatch(JARGON);
  await shoot(page, testInfo, "editor-arrivals", arrivals);

  const axe = await new AxeBuilder({ page }).include("[data-sim-arrivals]").withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(axe.violations).toEqual([]);

  // Il file resta com'era finche' il consulente non sceglie la correzione proposta.
  await notice.getByRole("button", { name: "Porta il massimo a 2h 30 min" }).click();
  await expect(notice).toHaveCount(0);
  await arrivals.getByText("Dettagli tecnici e limiti").click();
  await expect(arrivals.getByLabel("Massimo, min · Arrivi dei casi")).toHaveValue(/^150\.4/);
});
