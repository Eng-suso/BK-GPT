import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// Multiple full Axe scans and reloads need more than the single-page default
// on mobile emulation in a CPU-constrained runner.
test.setTimeout(90_000);

// Product UI with synthetic API data. Screenshots never contain customer data.
const API = "http://127.0.0.1:8000";
const BASE = "a".repeat(64);
const trace = (id: string) => `<b:documentation>DeliR traceability: {"source_refs":["steps:${id}"]}</b:documentation>`;
const TASKS = [
  { id: "request", name: "Richiedere materiale", x: 180, y: 80 },
  { id: "verify", name: "Verificare dati", x: 385, y: 180 },
  { id: "approve", name: "Approvare richiesta", x: 590, y: 280 },
  { id: "order", name: "Emettere ordine", x: 795, y: 180 },
];
const XML = `<?xml version="1.0" encoding="UTF-8"?>
<b:definitions xmlns:b="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="D" targetNamespace="https://delir.app/review">
<b:collaboration id="Collab"><b:participant id="Pool" name="Acquisti indiretti" processRef="P"/></b:collaboration>
<b:process id="P" isExecutable="false"><b:laneSet id="Lanes">
<b:lane id="Operations" name="Operations"><b:flowNodeRef>Start</b:flowNodeRef><b:flowNodeRef>request</b:flowNodeRef></b:lane>
<b:lane id="Buying" name="Acquisti"><b:flowNodeRef>verify</b:flowNodeRef><b:flowNodeRef>order</b:flowNodeRef><b:flowNodeRef>End</b:flowNodeRef></b:lane>
<b:lane id="Finance" name="Amministrazione"><b:flowNodeRef>approve</b:flowNodeRef></b:lane></b:laneSet>
<b:startEvent id="Start" name="Fabbisogno"/><b:endEvent id="End" name="Ordine inviato"/>
${TASKS.map(task => `<b:userTask id="${task.id}" name="${task.name}">${trace(task.id)}</b:userTask>`).join("")}
<b:sequenceFlow id="f1" sourceRef="Start" targetRef="request"/><b:sequenceFlow id="f2" sourceRef="request" targetRef="verify"/><b:sequenceFlow id="f3" sourceRef="verify" targetRef="approve"/><b:sequenceFlow id="f4" sourceRef="approve" targetRef="order"/><b:sequenceFlow id="f5" sourceRef="order" targetRef="End"/>
</b:process><bpmndi:BPMNDiagram id="Diagram"><bpmndi:BPMNPlane id="Plane" bpmnElement="Collab">
<bpmndi:BPMNShape id="Pool_di" bpmnElement="Pool" isHorizontal="true"><dc:Bounds x="40" y="50" width="1020" height="350"/></bpmndi:BPMNShape>
${[{ id: "Operations", y: 50, height: 120 }, { id: "Buying", y: 170, height: 100 }, { id: "Finance", y: 270, height: 130 }].map(lane => `<bpmndi:BPMNShape id="${lane.id}_di" bpmnElement="${lane.id}" isHorizontal="true"><dc:Bounds x="70" y="${lane.y}" width="990" height="${lane.height}"/></bpmndi:BPMNShape>`).join("")}
${TASKS.map(task => `<bpmndi:BPMNShape id="${task.id}_di" bpmnElement="${task.id}"><dc:Bounds x="${task.x}" y="${task.y}" width="140" height="70"/></bpmndi:BPMNShape>`).join("")}
<bpmndi:BPMNShape id="Start_di" bpmnElement="Start"><dc:Bounds x="110" y="97" width="36" height="36"/></bpmndi:BPMNShape>
<bpmndi:BPMNShape id="End_di" bpmnElement="End"><dc:Bounds x="980" y="197" width="36" height="36"/></bpmndi:BPMNShape>
${[
  '<di:waypoint x="146" y="115"/><di:waypoint x="180" y="115"/>',
  '<di:waypoint x="320" y="115"/><di:waypoint x="350" y="115"/><di:waypoint x="350" y="215"/><di:waypoint x="385" y="215"/>',
  '<di:waypoint x="525" y="215"/><di:waypoint x="555" y="215"/><di:waypoint x="555" y="315"/><di:waypoint x="590" y="315"/>',
  '<di:waypoint x="730" y="315"/><di:waypoint x="765" y="315"/><di:waypoint x="765" y="215"/><di:waypoint x="795" y="215"/>',
  '<di:waypoint x="935" y="215"/><di:waypoint x="980" y="215"/>',
].map((points, index) => `<bpmndi:BPMNEdge id="f${index + 1}_di" bpmnElement="f${index + 1}">${points}</bpmndi:BPMNEdge>`).join("")}
</bpmndi:BPMNPlane></bpmndi:BPMNDiagram></b:definitions>`;

async function fixture(page: Page, options: { failEvidence?: boolean; conflict?: boolean } = {}) {
  const actions: Array<Record<string, unknown>> = [];
  const mutations: string[] = [];
  await page.addInitScript(() => Object.assign(window, { DELIR_API_BASE: "http://127.0.0.1:8000" }));
  await page.route(`${API}/**`, async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() !== "GET") mutations.push(path);
    if (path === "/v1/workspace/projects/review-project") return route.fulfill({ json: {
      id: "review-project", client_id: "example", client: "Azienda demo", name: "Revisione acquisti indiretti", objective: "Review", lead: "Consulente", start_date: null, end_date: null,
      phase: "Discovery", status: "In corso", progress: 40, processes: 1, next_step: "Review", milestones: [], open_issues: [], deliverables: [], archived_at: null, archive_reason: null,
      process_items: [{ id: "review-process", project_id: "review-project", bpmn_model_id: "review-model", name: "Acquisti indiretti", stage: "AS-IS", status: "Da validare", owner: "Acquisti", readiness: 65, archived_at: null, archive_reason: null }],
    } });
    if (path.endsWith("/impact-review/actions") && request.method() === "POST") {
      if (options.conflict) return route.fulfill({ status: 409, json: { detail: "Baseline changed" } });
      const body = request.postDataJSON() as Record<string, unknown>;
      const action = { ...body, node_name: "Verificare dati", created_at: "2026-10-07T10:00:00Z", created_by: "consulente" };
      actions.push(action);
      return route.fulfill({ status: 201, json: action });
    }
    if (path.endsWith("/impact-review")) return route.fulfill({ json: {
      process_id: "review-process", base_revision: BASE, xml: XML, actions,
      plan: {
        title: "Acquisti indiretti", actors: [{ id: "buy", label: "Acquisti" }, { id: "ops", label: "Operations" }, { id: "fin", label: "Amministrazione" }],
        steps: TASKS.map(task => ({ id: task.id, label: task.name, actor_ids: [task.id === "request" ? "ops" : task.id === "approve" ? "fin" : "buy"], inputs: task.id === "verify" ? [] : ["request-form"], outputs: [task.id === "verify" ? "validated-request" : "request-form"] })),
        data_objects: [{ id: "request-form", label: "Richiesta di acquisto" }, { id: "validated-request", label: "Richiesta verificata" }],
        controls: [{ id: "check", label: "Controllo di completezza della richiesta", subject_ids: ["verify"] }],
        structured_business_rules: [{ id: "rule", label: "Autorizzazione della spesa", applies_to_ids: ["verify"], consequence: "La richiesta deve essere approvata prima dell’ordine." }],
        consultant_findings: [{ id: "finding", finding: "La modalità di gestione delle richieste incomplete resta da chiarire.", severity: "warning", recommendation: "Confrontare la procedura con l’owner del processo." }],
      },
    } });
    if (path.endsWith("/provenance")) {
      if (options.failEvidence) return route.fulfill({ status: 503, json: { detail: "Unavailable" } });
      return route.fulfill({ json: {
        process_id: "review-process", snapshot_id: "synthetic", snapshot_label: "V3", has_plan: true, total: 4, verified: 3, paraphrased: 1, label_grounded: 0, unverified: 0, awaiting_confirmation: 0, grounded_ratio: 1, sources_checked: 2, unused_sources: [],
        elements: TASKS.map(task => ({ kind: "step", element_id: task.id, label: task.name, source_ref: `steps:${task.id}`, status: "verified", mark_status: "verified", source_id: "example-interview", source_name: "Intervista owner Acquisti · esempio", quote: task.id === "verify" ? "Verifichiamo i dati della richiesta prima di passarla all’Amministrazione per l’approvazione." : "Il processo segue la richiesta fino all’emissione dell’ordine.", consultant_decision: null, removable: true })),
      } });
    }
    return route.fulfill({ json: [] });
  });
  return { actions, mutations };
}

async function open(page: Page) {
  await page.goto("/projects/review-project/processes/review-process?view=review");
  await expect(page.locator(".review-canvas [data-element-id='verify']").first()).toBeVisible();
}
async function selectTask(page: Page) {
  await page.getByRole("button", { name: "Task 4", exact: true }).click();
  await page.getByRole("button", { name: "Verificare dati", exact: true }).click();
  await expect(page.getByRole("complementary", { name: "Analisi del task" })).toBeVisible();
}

test("Review exposes six fields, dependency focus, evidence and responsive product screenshots", async ({ page }, info) => {
  if (info.project.name === "chromium") await page.setViewportSize({ width: 1600, height: 1000 });
  const state = await fixture(page);
  await open(page);
  if (info.project.name === "mobile-chrome") await expect(page.locator(".review-commands-compact")).toBeVisible();
  await page.screenshot({ path: info.outputPath("review-canvas.png") });
  await selectTask(page);
  if (info.project.name === "chromium") await page.getByRole("button", { name: "Centra", exact: true }).click();
  const inspector = page.getByRole("complementary", { name: "Analisi del task" });
  if (info.project.name === "mobile-chrome") await expect(page.locator(".review-inspector-compact")).toBeVisible();
  if (info.project.name === "chromium") {
    expect(await page.locator(".review-mascot-orbit").evaluate(element => getComputedStyle(element).animationIterationCount)).toBe("1");
    await page.emulateMedia({ reducedMotion: "reduce" });
    expect(await page.locator(".review-mascot-orbit").evaluate(element => getComputedStyle(element).animationName)).toBe("none");
    await page.emulateMedia({ reducedMotion: "no-preference" });
  }
  for (const name of ["Owner", "Input", "Output", "Problemi rilevati", "Impatti", "Suggerimento"]) await expect(inspector.locator("dt").filter({ hasText: name })).toBeVisible();
  await expect(inspector).toContainText("Input non documentato");
  expect((await new AxeBuilder({ page }).include(".process-review-workspace").analyze()).violations).toEqual([]);
  await expect(page.locator(".review-canvas [data-element-id='request']").first()).toHaveClass(/review-upstream/);
  await expect(page.locator(".review-canvas [data-element-id='order']").first()).toHaveClass(/review-downstream/);
  await page.screenshot({ path: info.outputPath("review-overview.png") });
  if (info.project.name === "chromium") await page.locator(".review-agent-card").screenshot({ path: info.outputPath("review-mascot-detail.png") });
  await inspector.getByRole("tab", { name: "Impatti", exact: true }).click();
  await expect(inspector).toContainText("Controllo di completezza");
  await expect(inspector).toContainText("Nessuna variazione di tempo è stata calcolata");
  await page.screenshot({ path: info.outputPath("review-impacts.png") });
  await inspector.getByRole("tab", { name: "Evidenze", exact: true }).click();
  await expect(inspector).toContainText("Intervista owner Acquisti · esempio");
  await page.screenshot({ path: info.outputPath("review-evidence.png") });
  const camera = await page.locator(".review-canvas .viewport").getAttribute("transform");
  await page.getByRole("button", { name: "Zona di impatto", exact: true }).click();
  await expect(page.locator(".review-canvas [data-element-id='order']").first()).not.toHaveClass(/review-downstream/);
  expect(await page.locator(".review-canvas .viewport").getAttribute("transform")).toBe(camera);
  await inspector.getByRole("tab", { name: "Overview", exact: true }).click();
  expect(await page.locator(".review-canvas .viewport").getAttribute("transform")).toBe(camera);
  const violations = (await new AxeBuilder({ page }).include(".process-review-workspace").analyze()).violations;
  expect(violations).toEqual([]);
  expect(state.mutations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  if (info.project.name === "mobile-chrome") {
    await page.getByRole("button", { name: "Chiudi analisi del task", exact: true }).click();
    await expect(inspector).toBeHidden();
    await expect(page.getByRole("button", { name: "Task 4", exact: true })).toBeFocused();
    await expect(page.locator(".review-canvas")).toBeVisible();
    await page.screenshot({ path: info.outputPath("review-mascot-canvas.png") });
  } else {
    await page.getByRole("button", { name: "Chiudi analisi del task", exact: true }).click();
  }
  await page.getByRole("button", { name: "Attività 4: Emettere ordine", exact: true }).click();
  await expect(inspector.getByRole("heading", { name: "Emettere ordine", exact: true })).toBeVisible();
  await expect(inspector.getByRole("button", { name: "Task successivo", exact: true })).toBeDisabled();
  await inspector.getByRole("button", { name: "Task precedente", exact: true }).click();
  await expect(inspector.getByRole("heading", { name: "Approvare richiesta", exact: true })).toBeVisible();
  await expect(inspector.getByRole("button", { name: "Proponi modifica", exact: true })).toBeInViewport();
  await page.getByRole("button", { name: "Chiudi analisi del task", exact: true }).click();
  await expect(page.getByRole("button", { name: "Attività 3: Approvare richiesta", exact: true })).toBeFocused();
});

test("candidate survives reload in To-Be hypotheses without editing As-Is", async ({ page }, info) => {
  if (info.project.name === "chromium") await page.setViewportSize({ width: 1600, height: 1000 });
  const state = await fixture(page);
  await open(page); await selectTask(page);
  await page.getByRole("button", { name: "Proponi modifica", exact: true }).click();
  expect((await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations).toEqual([]);
  await page.getByLabel("Titolo", { exact: true }).fill("Validare la completezza prima del passaggio");
  await page.getByLabel("Modifica proposta e impatti da verificare").fill("Introdurre un controllo condiviso sulla richiesta prima dell’invio ad Amministrazione. Verificare con l’owner i campi obbligatori, i documenti in output e il tempo di lavorazione nello scenario To-Be.");
  await page.getByRole("button", { name: "Registra azione" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(page.getByRole("status").filter({ hasText: "Azione registrata" })).toBeVisible();
  await page.goto("/projects/review-project/processes/review-process?view=tobe");
  await expect(page.getByRole("heading", { name: "Validare la completezza prima del passaggio" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Validare la completezza prima del passaggio" })).toBeVisible();
  await page.screenshot({ path: info.outputPath("review-tobe.png") });
  expect((await new AxeBuilder({ page }).include(".review-hypotheses").analyze()).violations).toEqual([]);
  expect(state.actions).toHaveLength(1);
  expect(state.mutations).toEqual(["/v1/workspace/processes/review-process/impact-review/actions"]);
  await page.getByRole("button", { name: "Rivedi il task", exact: true }).click();
  await expect(page.getByRole("complementary", { name: "Analisi del task" }).getByRole("heading", { name: "Verificare dati", exact: true })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Azioni", exact: true })).toHaveAttribute("aria-selected", "true");
});

test("conflict keeps proposal text and evidence failure stays explicit", async ({ page }) => {
  await fixture(page, { conflict: true, failEvidence: true });
  await open(page); await selectTask(page);
  const inspector = page.getByRole("complementary", { name: "Analisi del task" });
  await inspector.getByRole("tab", { name: "Evidenze" }).click();
  await expect(inspector.getByRole("alert")).toContainText("Impossibile caricare le evidenze");
  await inspector.getByRole("tab", { name: "Azioni" }).click();
  await inspector.getByRole("button", { name: "Proponi modifica" }).click();
  await page.getByLabel("Titolo", { exact: true }).fill("Proposta conservata");
  await page.getByLabel("Modifica proposta e impatti da verificare").fill("Dettaglio conservato dopo conflitto.");
  await page.getByRole("button", { name: "Registra azione" }).click();
  await expect(page.getByRole("dialog")).toContainText("La base della review è cambiata");
  await expect(page.getByLabel("Titolo", { exact: true })).toHaveValue("Proposta conservata");
  await page.keyboard.press("Escape");
  await expect(inspector.getByRole("button", { name: "Proponi modifica" })).toBeFocused();
});
