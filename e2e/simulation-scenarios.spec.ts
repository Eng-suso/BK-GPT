import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

import { applyScenarioPatch, type ScenarioPatchOp } from "../frontend/src/features/process/simulation/scenarioPatch";

/** SIM-14: il workspace degli scenari AS-IS | A | B, dal pannello allo studio. */

const studio = "/projects/ws-project/processes/ws-process/simulation";
const xml = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_ws" targetNamespace="https://example.test/ws">
<bpmn:process id="Process_ws" isExecutable="false"><bpmn:startEvent id="Start" /><bpmn:task id="T_receive" name="Ricevi ordine" /><bpmn:task id="T_approve" name="Approva" /><bpmn:endEvent id="End" />
<bpmn:sequenceFlow id="F0" sourceRef="Start" targetRef="T_receive" /><bpmn:sequenceFlow id="F1" sourceRef="T_receive" targetRef="T_approve" /><bpmn:sequenceFlow id="F2" sourceRef="T_approve" targetRef="End" /></bpmn:process>
<bpmndi:BPMNDiagram id="Diagram_ws"><bpmndi:BPMNPlane id="Plane_ws" bpmnElement="Process_ws">
<bpmndi:BPMNShape id="Start_di" bpmnElement="Start"><dc:Bounds x="60" y="120" width="36" height="36" /></bpmndi:BPMNShape><bpmndi:BPMNShape id="T_receive_di" bpmnElement="T_receive"><dc:Bounds x="140" y="98" width="120" height="80" /></bpmndi:BPMNShape><bpmndi:BPMNShape id="T_approve_di" bpmnElement="T_approve"><dc:Bounds x="320" y="98" width="120" height="80" /></bpmndi:BPMNShape><bpmndi:BPMNShape id="End_di" bpmnElement="End"><dc:Bounds x="500" y="120" width="36" height="36" /></bpmndi:BPMNShape>
<bpmndi:BPMNEdge id="F0_di" bpmnElement="F0"><di:waypoint x="96" y="138" /><di:waypoint x="140" y="138" /></bpmndi:BPMNEdge><bpmndi:BPMNEdge id="F1_di" bpmnElement="F1"><di:waypoint x="260" y="138" /><di:waypoint x="320" y="138" /></bpmndi:BPMNEdge><bpmndi:BPMNEdge id="F2_di" bpmnElement="F2"><di:waypoint x="440" y="138" /><di:waypoint x="500" y="138" /></bpmndi:BPMNEdge>
</bpmndi:BPMNPlane></bpmndi:BPMNDiagram></bpmn:definitions>`;

const tasks = [
  { element_id: "T_receive", name: "Ricevi ordine", type: "task" },
  { element_id: "T_approve", name: "Approva", type: "task" },
];
const template = {
  tasks,
  resources: [],
  standard_calendar: { id: "delir-calendar-standard", name: "Standard", periods: [{ from_day: "MONDAY", to_day: "FRIDAY", begin: "09:00", end: "17:00" }] },
  gateways: [],
};
const draft = {
  scenarioName: "Situazione attuale", totalCases: 50, arrivalIntervalMinutes: 30, defaultTaskMinutes: 15,
  resources: [{ id: "r1", name: "Ufficio acquisti", costPerHour: 40, amount: 2, parametersConfirmed: true }],
  tasks: Object.fromEntries(tasks.map((t) => [t.element_id, { meanMinutes: 20, distribution: "norm", resourceId: "r1", assignmentSource: "manual" }])),
  gateways: {},
};

type Scenario = { id: number; kind: "baseline" | "alternative"; label: string; name: string; revision: number; draft?: object; patch: ScenarioPatchOp[] };

/** Un workspace finto con le stesse regole del backend: revisioni, lettere, patch risolte. */
class Workspace {
  seed = 4242;
  baseline: Scenario | null = null;
  alternatives: Scenario[] = [];
  private nextId = 1;
  requests: { method: string; path: string; body: unknown }[] = [];
  failNext: number | null = null;

  json() {
    const base = this.baseline?.draft ?? {};
    const view = (s: Scenario) => {
      const { draft: resolved, conflicts } = s.kind === "baseline" ? { draft: base, conflicts: [] } : applyScenarioPatch(base, s.patch);
      return { id: s.id, kind: s.kind, label: s.label, name: s.name, revision: s.revision, draft: resolved, patch: s.patch, conflicts, created_at: "", updated_at: "" };
    };
    return { bpmn_model_id: "ws-model", seed: this.baseline ? this.seed : null, baseline: this.baseline && view(this.baseline), alternatives: this.alternatives.map(view) };
  }

  seedWith(baseline: object, ...alternatives: { name: string; patch: ScenarioPatchOp[]; revision?: number }[]) {
    this.baseline = { id: this.nextId++, kind: "baseline", label: "AS-IS", name: "Situazione attuale", revision: 1, draft: baseline, patch: [] };
    alternatives.forEach((alt, index) => this.alternatives.push({ id: this.nextId++, kind: "alternative", label: "ABCDE"[index], name: alt.name, revision: alt.revision ?? 1, patch: alt.patch }));
    return this;
  }

  handle(method: string, path: string, body: Record<string, unknown> | null): { status: number; json: unknown } {
    this.requests.push({ method, path, body });
    if (this.failNext !== null && method !== "GET") {
      const status = this.failNext;
      this.failNext = null;
      return { status, json: { error: { message: "conflitto" } } };
    }
    const id = Number(path.split("/").pop());
    if (method === "PUT") {
      if (!this.baseline) this.baseline = { id: this.nextId++, kind: "baseline", label: "AS-IS", name: String(body!.name), revision: 1, draft: body!.draft as object, patch: [] };
      else {
        if (body!.revision !== this.baseline.revision) return { status: 409, json: {} };
        Object.assign(this.baseline, { name: body!.name, draft: body!.draft, revision: this.baseline.revision + 1 });
        if (typeof body!.seed === "number") this.seed = body!.seed;
      }
    } else if (method === "POST") {
      const label = "ABCDE".split("").find((l) => !this.alternatives.some((s) => s.label === l))!;
      this.alternatives.push({ id: this.nextId++, kind: "alternative", label, name: String(body!.name), revision: 1, patch: (body!.patch as ScenarioPatchOp[]) ?? [] });
    } else if (method === "PATCH") {
      const scenario = this.alternatives.find((s) => s.id === id)!;
      if (body!.revision !== scenario.revision) return { status: 409, json: {} };
      if (body!.name) scenario.name = String(body!.name);
      if (body!.patch) scenario.patch = body!.patch as ScenarioPatchOp[];
      scenario.revision += 1;
    } else if (method === "DELETE") {
      this.alternatives = this.alternatives.filter((s) => s.id !== id);
    }
    return { status: 200, json: this.json() };
  }
}

const summary = (cycle: number) => ({
  casesCompleted: 50, cycle: { avg: cycle, p50: cycle, p90: cycle * 1.4, p95: cycle * 1.5 }, waiting: { avg: cycle / 4, p95: cycle / 2, share: 0.25 },
  processing: { avg: cycle * 0.75 }, cost: { total: 3000, perCase: 60 }, throughputPerHour: 2,
  byActivity: [{ el: "T_approve", name: "Approva", wait: { avg: 600 } }], byResource: [], bottleneck: { el: "T_approve", name: "Approva" },
});
const run = (id: number, scenarioId: number, cycle: number, extra: Record<string, unknown> = {}) => ({
  id, bpmn_model_id: "ws-model", process_id: "ws-process", scenario_name: `Run ${id}`, engine: "prosimos", status: "completed",
  request: { workspace_scenario: { id: scenarioId, revision: 1, baseline_revision: 1 }, ...extra }, scenario: {}, result: {}, outputs: [], error: null,
  created_at: "2026-10-10T09:00:00Z", completed_at: "2026-10-10T09:01:00Z", summary: summary(cycle),
});
const group = (firstId: number, scenarioId: number, name: string, cycles: number[]) => cycles.map((cycle, i) =>
  run(firstId + i, scenarioId, cycle, { replication_group: name, replication_index: i + 1, seed: 4242 + i }));

const replay = {
  schemaVersion: 1, meta: { start: "2026-10-10T09:00:00Z", durationSec: 300, totalCases: 1, sampledCases: 1, bucketSec: 100 },
  elements: { T_receive: { name: "Ricevi ordine" }, T_approve: { name: "Approva" } },
  cases: [{ id: "0", cycleSec: 300, events: [{ el: "T_receive", enable: 0, start: 0, end: 100, res: "Ufficio" }, { el: "T_approve", enable: 100, start: 150, end: 300, res: "Ufficio" }] }],
  series: { t: [0, 100, 200], byElement: {}, byResource: {}, global: { wip: [1, 1, 0], queued: [0, 0, 0], done: [0, 0, 1], throughputPerHour: [0, 0, 12], costAccrued: [0, 5, 10], avgCycleSec: [0, 0, 300] } },
  flows: {},
};

async function fixture(page: Page, workspace: Workspace, runs: unknown[] = []) {
  await page.addInitScript((stored) => {
    Object.assign(window, { DELIR_API_BASE: "http://127.0.0.1:8000" });
    localStorage.setItem("delir-language", "it");
    if (!sessionStorage.getItem("seeded")) {
      localStorage.setItem("delir-sim-scenario:ws-model", stored);
      sessionStorage.setItem("seeded", "1");
    }
  }, JSON.stringify(draft));
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.includes("/simulation-scenarios")) {
      const result = workspace.handle(request.method(), path, request.method() === "GET" || request.method() === "DELETE" ? null : request.postDataJSON());
      await route.fulfill({ status: result.status, json: result.json });
      return;
    }
    let data: unknown = [];
    if (path === "/v1/workspace/projects/ws-project") data = {
      id: "ws-project", client_id: "demo", client: "Azienda Demo", name: "Acquisti", phase: "AS-IS", status: "In corso", progress: 40, processes: 1,
      next_step: "Confrontare gli scenari", milestones: [], open_issues: [], deliverables: [],
      process_items: [{ id: "ws-process", project_id: "ws-project", bpmn_model_id: "ws-model", name: "Ciclo passivo", stage: "AS-IS", status: "Da validare", owner: "Acquisti", readiness: 80 }],
    };
    else if (path.endsWith("/simulation-template")) data = template;
    else if (path.endsWith("/simulation-provenance")) data = { has_discovery: false, elements: [] };
    else if (path.endsWith("/simulation-runs") && request.method() === "POST") data = { ...run(99, 0, 3600), status: "pending", summary: null, request: request.postDataJSON() };
    else if (path.endsWith("/simulation-runs")) data = runs;
    else if (path.endsWith("/replay")) data = { run_id: 41, schema_version: 1, replay };
    else if (path.endsWith("/experiments")) data = { bottleneck_el: null, bottleneck_name: null, factors: {}, experiments: [] };
    else if (path.endsWith("/ws-model")) data = { id: "ws-model", process_id: "ws-process", name: "Ciclo passivo", xml };
    await route.fulfill({ json: data });
  });
}

const tabs = (page: Page) => page.locator("[data-sim-scenario-tabs]");

test("the AS-IS comes from the draft and a new scenario keeps only its changes", async ({ page }, testInfo) => {
  const workspace = new Workspace();
  await fixture(page, workspace);
  await page.goto(`${studio}/scenario`);

  // L'AS-IS nasce dalla bozza che il browser aveva gia'.
  await expect(tabs(page).getByRole("button", { name: "AS-IS", exact: true })).toHaveAttribute("aria-pressed", "true");
  const created = workspace.requests.find((r) => r.method === "PUT");
  expect((created?.body as { draft: { totalCases: number } }).draft.totalCases).toBe(50);
  await expect(tabs(page)).toContainText("Stai modificando l'AS-IS");

  await tabs(page).getByRole("button", { name: "Nuovo scenario", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Nuovo scenario" });
  await dialog.getByLabel("Nome dello scenario").fill("+1 approvatore");
  await dialog.getByRole("button", { name: "Crea scenario", exact: true }).click();
  await expect(tabs(page).getByRole("button", { name: "A · +1 approvatore", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page).toHaveURL(/scenario=2/);
  await expect(tabs(page)).toContainText("Ancora uguale all'AS-IS");

  // +1 approvatore: una sola differenza, sulla risorsa per id.
  await page.getByLabel("Unità disponibili").first().fill("3");
  // Da tastiera: l'intestazione fissa della sezione copre il bottone nel pannello stretto.
  await page.getByRole("button", { name: "Conferma capacità e costo" }).first().focus();
  await page.keyboard.press("Enter");
  await expect(tabs(page)).toContainText("Ufficio acquisti · Unità: 2 → 3");
  await expect.poll(() => (workspace.alternatives[0]?.patch ?? [])).toEqual([{ op: "set", path: ["resources", { id: "r1" }, "amount"], value: 3 }]);

  await tabs(page).scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath("scenario-tabs.png"), animations: "disabled" });
  const axe = await new AxeBuilder({ page }).include("[data-sim-scenario-tabs]").withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(axe.violations).toEqual([]);

  // Il run porta lo scenario, le revisioni e il seed comune.
  const request = page.waitForRequest((req) => req.method() === "POST" && req.url().endsWith("/simulation-runs"));
  await page.getByRole("button", { name: "Avvia simulazione", exact: true }).click();
  const body = (await request).postDataJSON();
  expect(body.workspace_scenario).toEqual({ id: 2, revision: workspace.alternatives[0].revision, baseline_revision: 1 });
  expect(body.seed).toBe(4242);
  expect(body.scenario_name).toBe("A · +1 approvatore");
  expect(body.resources[0].amount).toBe(3);

  // Ripristina: lo scenario torna uguale all'AS-IS.
  await tabs(page).getByRole("button", { name: /Riporta Ufficio acquisti · Unità/ }).click();
  await expect(tabs(page)).toContainText("Ancora uguale all'AS-IS");
  expect(workspace.alternatives[0].patch).toEqual([]);

  // L'AS-IS resta com'era.
  await tabs(page).getByRole("button", { name: "AS-IS", exact: true }).click();
  await expect(page.getByLabel("Unità disponibili").first()).toHaveValue("2");
});

test("duplicating and deleting a scenario, and a change made elsewhere", async ({ page }) => {
  const workspace = new Workspace().seedWith(draft, { name: "+1 approvatore", patch: [{ op: "set", path: ["resources", { id: "r1" }, "amount"], value: 3 }] });
  await fixture(page, workspace);
  await page.goto(`${studio}/scenario?scenario=2`);
  await expect(tabs(page)).toContainText("1 modifica rispetto all'AS-IS");

  await tabs(page).getByRole("button", { name: "Azioni su A · +1 approvatore", exact: true }).click();
  await page.getByRole("menuitem", { name: "Duplica" }).click();
  const dialog = page.getByRole("dialog", { name: "Nuovo scenario" });
  await expect(dialog.getByLabel("Nome dello scenario")).toHaveValue("+1 approvatore (copia)");
  await dialog.getByRole("button", { name: "Crea scenario", exact: true }).click();
  await expect(tabs(page).getByRole("button", { name: "B · +1 approvatore (copia)", exact: true })).toHaveAttribute("aria-pressed", "true");
  expect(workspace.alternatives[1].patch).toEqual(workspace.alternatives[0].patch);

  await tabs(page).getByRole("button", { name: "Azioni su B · +1 approvatore (copia)", exact: true }).click();
  await page.getByRole("menuitem", { name: "Elimina scenario" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Elimina", exact: true }).click();
  await expect(tabs(page).getByRole("button", { name: /^B ·/ })).toHaveCount(0);
  await expect(tabs(page).getByRole("button", { name: "AS-IS", exact: true })).toHaveAttribute("aria-pressed", "true");

  // Un'altra scheda ha salvato prima: il pannello ricarica e lo dice.
  workspace.failNext = 409;
  await page.getByLabel("Casi", { exact: true }).fill("80");
  await expect(page.getByRole("alert").filter({ hasText: "cambiato altrove" })).toBeVisible();
});

test("the Workspace tool compares every scenario with the AS-IS, with the interval", async ({ page }, testInfo) => {
  const workspace = new Workspace().seedWith(draft,
    { name: "+1 approvatore", patch: [{ op: "set", path: ["resources", { id: "r1" }, "amount"], value: 3 }] },
    { name: "Turni", patch: [{ op: "set", path: ["totalCases"], value: 60 }], revision: 2 });
  const runs = [
    ...group(41, 1, "g-asis", [3600, 3720, 3660]),
    ...group(51, 2, "g-a", [3000, 3130, 3070]),
    run(61, 3, 3500),
  ];
  await fixture(page, workspace, runs);
  await page.goto(`${studio}/workspace/41?panel=scenarios`);
  const panel = page.locator("[data-sim-scenario-workspace]");
  await expect(panel).toContainText("Seed comune: 4242");

  const asIs = panel.locator('[data-sim-workspace-row="AS-IS"]');
  const a = panel.locator('[data-sim-workspace-row="A"]');
  const b = panel.locator('[data-sim-workspace-row="B"]');
  await expect(asIs).toContainText("Aggiornato");
  await expect(asIs).toContainText("3 ripetizioni");
  await expect(a).toContainText("Aggiornato");
  await expect(a).toContainText("±");
  await expect(a).toContainText("Migliore");
  await expect(panel.locator('[data-sim-workspace-method="paired"]')).toBeVisible();
  // Turni e' cambiato dopo il suo run: da rifare.
  await expect(b).toContainText("Da rifare");

  await panel.scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath("scenario-workspace.png"), animations: "disabled" });
  const axe = await new AxeBuilder({ page }).include("[data-sim-scenario-workspace]").withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(axe.violations).toEqual([]);

  // Esegui solo cio' che serve: Turni, con il seed comune.
  const request = page.waitForRequest((req) => req.method() === "POST" && req.url().endsWith("/simulation-runs"));
  await panel.getByRole("button", { name: "Esegui gli scenari da aggiornare", exact: true }).click();
  const body = (await request).postDataJSON();
  expect(body.workspace_scenario).toEqual({ id: 3, revision: 2, baseline_revision: 1 });
  expect(body.total_cases).toBe(60);
  expect(body.seed).toBe(4242);

  await panel.getByRole("button", { name: "Mostra A · +1 approvatore contro l'AS-IS sul processo", exact: true }).click();
  await expect(page).toHaveURL(/a=41/);
  await expect(page).toHaveURL(/b=51/);
  await expect(page).toHaveURL(/panel=compare/);
});

test("the process and the task inspector show what a scenario changes", async ({ page }, testInfo) => {
  const workspace = new Workspace().seedWith(draft, { name: "Approvazione veloce", patch: [{ op: "set", path: ["tasks", "T_approve", "meanMinutes"], value: 10 }] });
  await fixture(page, workspace, group(41, 1, "g-asis", [3600, 3720]));
  await page.goto(`${studio}/workspace/41?panel=scenario&scenario=2`);
  await expect(page.locator('.djs-element[data-element-id="T_approve"].sim-scenario-changed').first()).toBeAttached();
  await expect(page.locator(".sim-process-legend")).toContainText("Modificato nello scenario A");
  await page.screenshot({ path: testInfo.outputPath("scenario-overlay.png"), animations: "disabled" });

  await page.goto(`${studio}/workspace/41?panel=activity`);
  await page.locator('.djs-element[data-element-id="T_approve"]').first().click();
  const inspector = page.getByRole("region", { name: "Negli scenari", exact: true });
  await expect(inspector).toContainText("A · Approvazione veloce: Approva · Durata media, min: 20 → 10");
  const axe = await new AxeBuilder({ page }).include("[data-sim-scenario-activity]").withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(axe.violations).toEqual([]);
  await inspector.getByRole("button", { name: "Modifica A · Approvazione veloce nel pannello Scenario", exact: true }).click();
  await expect(page).toHaveURL(/panel=scenario/);
  await expect(page).toHaveURL(/scenario=2/);
});
