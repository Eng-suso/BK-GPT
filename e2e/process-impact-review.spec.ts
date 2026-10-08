import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";

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

async function fixture(page: Page, options: { failEvidence?: boolean; conflict?: boolean; failChatOnce?: boolean; holdChat?: boolean; engineDiagram?: boolean; enterpriseDiagram?: boolean } = {}) {
  // These artifacts are generated and compared byte-canonically in the real
  // LangGraph → tool → Postgres test, rather than authored by this API mock.
  const baseline = options.engineDiagram ? readFileSync("e2e/fixtures/review-agent/baseline.bpmn", "utf8") : XML;
  const proposal = options.enterpriseDiagram ? readFileSync("e2e/fixtures/canvas-layout/purchase.bpmn", "utf8") : options.engineDiagram ? readFileSync("e2e/fixtures/review-agent/proposal.bpmn", "utf8") : XML.replace('name="Verificare dati"', 'name="Verificare completezza dati"');
  const actions: Array<Record<string, unknown>> = [];
  const mutations: string[] = [];
  const turns: Array<Record<string, unknown>> = [];
  const sessions: Array<{ thread_id: string; scope_key: string; messages: Array<{ role: string; content: string }>; title: string }> = [];
  let release: (() => void) | undefined;
  const held = options.holdChat ? new Promise<void>(resolve => { release = resolve; }) : null;
  await page.addInitScript(() => Object.assign(window, { DELIR_API_BASE: "http://127.0.0.1:8000" }));
  await page.route(`${API}/**`, async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.startsWith("/v1/consultant-chat/sessions")) {
      if (path.endsWith("/messages/stream")) {
        const body = request.postDataJSON() as Record<string, unknown>; turns.push(body);
        if (options.failChatOnce && turns.length === 1) return route.fulfill({ status: 503, json: { detail: "Review temporarily unavailable" } });
        const session = sessions.find(item => path.includes(item.thread_id))!;
        if (held && turns.length === 1) await held;
        const answer = session.scope_key.endsWith(":verify") ? "**Il controllo è utile, ma l’input non è documentato.**\n\nL’owner è Acquisti; l’intervista collega la verifica al passaggio verso Amministrazione. Suggerisco di esplicitare i campi obbligatori e l’esito del controllo, mantenendo l’autorizzazione della spesa.\n\n**Da verificare:** gestione delle richieste incomplete e responsabilità del rinvio. Non abbiamo dati sufficienti per stimare un risparmio di tempo." : "Questo task emette l’ordine dopo l’approvazione. Nessuna modifica effettuata.";
        session.messages.push({ role: "user", content: String(body.message) }, { role: "assistant", content: answer });
        if (String(body.message).includes("Disegna")) actions.push({ id: "separate-diagram", node_id: "verify", node_name: "Verificare dati", base_revision: BASE, kind: "as_is_proposal", title: "Esplicitare il controllo di completezza", detail: "Proposta As-Is: rendere esplicito il controllo descritto dall’owner. Da confermare i campi obbligatori.", proposal_xml: proposal, created_at: "2026-10-07T10:00:00Z", created_by: "DeliR Review" });
        return route.fulfill({ contentType: "application/x-ndjson", body: `${JSON.stringify({ type: "delta", content: answer })}\n${JSON.stringify({ type: "done", message: answer })}\n` });
      }
      if (request.method() === "POST") {
        const scope = request.postDataJSON().scope;
        const session = { thread_id: `review-thread-${sessions.length}`, scope_key: `canvas:${scope.project_id}:${scope.process_id}:${scope.bpmn_model_id}:review:${scope.review_node_id}`, messages: [], title: "Task review" };
        sessions.push(session); return route.fulfill({ json: session });
      }
      return route.fulfill({ json: sessions.find(item => path.endsWith(item.thread_id)) ?? sessions.filter(item => item.scope_key === new URL(request.url()).searchParams.get("scope_key")) });
    }
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
      process_id: "review-process", base_revision: BASE, xml: baseline, actions,
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
  return { actions, mutations, turns, release: () => release?.() };
}

async function open(page: Page) {
  await page.goto("/projects/review-project/processes/review-process?view=review");
  await expect(page.locator(".review-canvas [data-element-id='verify']").first()).toBeVisible();
}
async function selectTask(page: Page, name = "Verificare dati") {
  await page.getByRole("button", { name: "Task 4", exact: true }).click();
  await page.getByRole("button", { name, exact: true }).click();
}
async function openAgent(page: Page) {
  await page.getByRole("button", { name: "Apri agente DeliR", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Agente di Review" })).toBeVisible();
}
async function send(page: Page, message: string) {
  await page.getByLabel("Scrivi all’agente di Review").fill(message);
  await page.getByRole("button", { name: "Invia messaggio", exact: true }).click();
}

test("floating agent, contextual conversation, knowledge and product screenshots", async ({ page }, info) => {
  if (info.project.name === "chromium") await page.setViewportSize({ width: 1600, height: 1000 });
  const state = await fixture(page);
  await open(page);
  await expect(page.locator(".review-task-ribbon")).toHaveCount(0);
  await selectTask(page);
  const inspector = page.getByRole("complementary", { name: "Analisi del task" });
  await expect(inspector).toBeHidden();
  const launcher = (await page.getByRole("button", { name: "Apri agente DeliR", exact: true }).boundingBox())!;
  expect(launcher.height).toBeLessThanOrEqual(80);
  expect(launcher.width).toBeLessThanOrEqual(196);
  await page.screenshot({ path: info.outputPath("review-canvas.png") });
  const camera = await page.locator(".review-canvas .viewport").getAttribute("transform");
  await openAgent(page);
  await expect(page.getByLabel("Scrivi all’agente di Review")).toBeFocused();
  await send(page, "Leggi le fonti e dimmi cosa ne pensi, senza modificare il processo.");
  const chat = page.getByRole("dialog", { name: "Agente di Review" });
  await expect(chat).toContainText("Il controllo è utile");
  await expect(page.getByRole("button", { name: "Salva come ipotesi" })).toBeVisible();
  expect(state.turns[0]).toMatchObject({ autonomy: "manual", posture: "review", scope: { review_node_id: "verify", review_base_revision: BASE } });
  expect(await page.locator(".review-canvas .viewport").getAttribute("transform")).toBe(camera);
  const chatBounds = (await chat.boundingBox())!;
  const attributionBounds = (await page.locator(".review-canvas .bjs-powered-by").boundingBox())!;
  expect(chatBounds.y + chatBounds.height).toBeLessThan(attributionBounds.y);
  expect((await new AxeBuilder({ page }).include(".process-review-workspace").analyze()).violations).toEqual([]);
  await page.screenshot({ path: info.outputPath("review-agent-chat.png") });
  if (info.project.name === "chromium") await chat.screenshot({ path: info.outputPath("review-agent-detail.png") });
  await chat.getByRole("button", { name: "Apri conoscenza e proposte del task" }).click();
  await expect(inspector).toBeVisible();
  for (const name of ["Owner", "Input", "Output", "Problemi rilevati", "Impatti", "Suggerimento"]) await expect(inspector.locator("dt").filter({ hasText: name })).toBeVisible();
  await page.screenshot({ path: info.outputPath("review-overview.png") });
  await inspector.getByRole("tab", { name: "Impatti", exact: true }).click();
  await expect(inspector).toContainText("Controllo di completezza");
  await page.screenshot({ path: info.outputPath("review-impacts.png") });
  await inspector.getByRole("tab", { name: "Evidenze", exact: true }).click();
  await expect(inspector).toContainText("Intervista owner Acquisti · esempio");
  await page.screenshot({ path: info.outputPath("review-evidence.png") });
  await expect(inspector.getByRole("button", { name: "Lavora con DeliR" })).toBeInViewport();
  await expect(inspector.getByRole("button", { name: "Proposta As-Is", exact: true })).toBeInViewport();
  expect((await new AxeBuilder({ page }).include(".process-review-workspace").analyze()).violations).toEqual([]);
  await page.getByRole("button", { name: "Chiudi analisi del task" }).click();
  await expect(chat).toBeVisible();
  await chat.getByRole("button", { name: "Chiudi chat DeliR" }).click();
  await expect(chat).toBeHidden();
  await expect(page.getByRole("button", { name: "Apri agente DeliR" })).toBeFocused();
  expect(state.mutations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});

test("editable hypotheses survive reload without changing As-Is", async ({ page }, info) => {
  if (info.project.name === "chromium") await page.setViewportSize({ width: 1600, height: 1000 });
  const state = await fixture(page);
  await open(page); await selectTask(page); await openAgent(page);
  await send(page, "Quale modifica consiglieresti?");
  await page.getByRole("button", { name: "Salva come ipotesi" }).click();
  await page.getByRole("menuitem", { name: "Proposta To-Be", exact: true }).click();
  const dialog = page.getByRole("dialog").filter({ has: page.getByRole("heading", { name: "Proponi modifica", exact: true }) });
  await expect(dialog).toBeVisible();
  await expect(page.getByLabel("Modifica proposta e impatti da verificare")).toHaveValue(/Il controllo è utile/);
  await page.getByLabel("Titolo", { exact: true }).fill("Validare la completezza prima del passaggio");
  await page.getByLabel("Modifica proposta e impatti da verificare").fill("Verificare campi obbligatori e responsabilità con l’owner prima del passaggio ad Amministrazione.");
  await page.getByRole("button", { name: "Registra azione" }).click();
  await expect(dialog).toBeHidden();
  await page.goto("/projects/review-project/processes/review-process?view=tobe");
  await expect(page.getByRole("heading", { name: "Validare la completezza prima del passaggio" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Validare la completezza prima del passaggio" })).toBeVisible();
  await page.screenshot({ path: info.outputPath("review-tobe.png") });
  expect((await new AxeBuilder({ page }).include(".review-hypotheses").analyze()).violations).toEqual([]);
  expect(state.actions).toHaveLength(1);
  expect(state.mutations).toEqual(["/v1/workspace/processes/review-process/impact-review/actions"]);
  await page.getByRole("button", { name: "Rivedi il task", exact: true }).click();
  await expect(page.getByRole("tab", { name: "Proposte", exact: true })).toHaveAttribute("aria-selected", "true");
});

test("separate As-Is diagram is available for presentation and export", async ({ page }, info) => {
  if (info.project.name === "chromium") await page.setViewportSize({ width: 1600, height: 1000 });
  const state = await fixture(page);
  await open(page); await selectTask(page); await openAgent(page);
  await send(page, "Disegna una proposta As-Is separata: rinomina il task in Verificare completezza dati.");
  await expect(page.getByRole("button", { name: "Salva come ipotesi" })).toBeVisible();
  await page.getByRole("dialog", { name: "Agente di Review" }).getByRole("button", { name: "Apri conoscenza e proposte del task" }).click();
  await page.getByRole("tab", { name: "Proposte", exact: true }).click();
  await page.getByRole("button", { name: "Apri diagramma", exact: true }).click();
  const preview = page.getByRole("dialog", { name: "Esplicitare il controllo di completezza" });
  await expect(preview.locator(".djs-label").filter({ hasText: "Verificare completezza" })).toBeVisible();
  await page.screenshot({ path: info.outputPath("review-as-is-proposal.png") });
  await preview.getByRole("tab", { name: "As-Is originale", exact: true }).click();
  await expect(preview.locator(".djs-label").filter({ hasText: "Verificare dati" })).toBeVisible();
  const download = page.waitForEvent("download");
  await preview.getByRole("button", { name: "Scarica BPMN" }).click();
  expect((await download).suggestedFilename()).toBe("review-separate-diagram.bpmn");
  expect(state.actions).toHaveLength(1);
  expect(state.mutations).toEqual([]);
  expect((await new AxeBuilder({ page }).include(".review-proposal-viewer").analyze()).violations).toEqual([]);
});

test("agent engine output renders the new task, owner and reconnected flows", async ({ page }, info) => {
  if (info.project.name === "chromium") await page.setViewportSize({ width: 1600, height: 1000 });
  await fixture(page, { engineDiagram: true });
  await open(page);
  await page.getByRole("button", { name: "Task 1", exact: true }).click();
  await page.getByRole("button", { name: "Verificare dati", exact: true }).click();
  await openAgent(page);
  await send(page, "Disegna nella proposta un task per registrare l’esito dopo la verifica, con owner Acquisti.");
  await expect(page.getByRole("button", { name: "Salva come ipotesi" })).toBeVisible();
  await page.getByRole("dialog", { name: "Agente di Review" }).getByRole("button", { name: "Apri conoscenza e proposte del task" }).click();
  await page.getByRole("tab", { name: "Proposte", exact: true }).click();
  await page.getByRole("button", { name: "Apri diagramma", exact: true }).click();
  const preview = page.getByRole("dialog", { name: "Esplicitare il controllo di completezza" });
  for (const id of ["verify", "record", "buying"]) await expect(preview.locator(`.djs-element[data-element-id='${id}']`)).toBeVisible();
  await expect(preview.locator(".djs-label").filter({ hasText: "Registrare esito verifica" })).toBeVisible();
  await expect(preview.locator(".djs-label").filter({ hasText: "Acquisti" })).toBeVisible();
  await expect(preview.locator(".djs-connection")).toHaveCount(3);
  for (const id of ["begin", "handoff", "finish"]) {
    const line = preview.locator(`.djs-connection[data-element-id='${id}'] .djs-visual > path`);
    // Horizontal SVG lines have zero bounding-box height: Playwright's
    // visibility predicate cannot distinguish them from a hidden element.
    expect(await line.evaluate(element => {
      const style = getComputedStyle(element);
      return (element as SVGPathElement).getTotalLength() > 0 && style.stroke !== "none" && Number.parseFloat(style.strokeWidth) > 0 && style.visibility === "visible";
    })).toBeTruthy();
  }
  await page.screenshot({ path: info.outputPath("review-engine-proposal.png") });
  const download = page.waitForEvent("download");
  await preview.getByRole("button", { name: "Scarica BPMN" }).click();
  expect(readFileSync((await (await download).path())!, "utf8")).toBe(readFileSync("e2e/fixtures/review-agent/proposal.bpmn", "utf8"));
  await preview.getByRole("tab", { name: "As-Is originale", exact: true }).click();
  await expect(preview.locator(".djs-element[data-element-id='record']")).toHaveCount(0);
  await expect(preview.locator(".djs-connection")).toHaveCount(2);
});

test("node histories and drafts stay isolated while an earlier reply finishes", async ({ page }) => {
  const state = await fixture(page, { holdChat: true });
  await open(page); await selectTask(page); await openAgent(page);
  await send(page, "Cosa sappiamo della verifica?");
  await expect(page.getByRole("button", { name: "Interrompi risposta" })).toBeVisible();
  await page.getByLabel("Scrivi all’agente di Review").fill("Bozza per verifica");
  await selectTask(page, "Emettere ordine");
  await expect(page.getByLabel("Scrivi all’agente di Review")).toHaveValue("");
  await page.getByLabel("Scrivi all’agente di Review").fill("Bozza per ordine");
  state.release();
  await expect(page.getByRole("dialog", { name: "Agente di Review" })).not.toContainText("Il controllo è utile");
  await selectTask(page);
  await expect(page.getByLabel("Scrivi all’agente di Review")).toHaveValue("Bozza per verifica");
  await expect(page.getByRole("dialog", { name: "Agente di Review" })).toContainText("Il controllo è utile");
  await selectTask(page, "Emettere ordine");
  await expect(page.getByLabel("Scrivi all’agente di Review")).toHaveValue("Bozza per ordine");
  expect(state.turns).toHaveLength(1);
});

test("retry and stale proposal errors retain editable text", async ({ page }) => {
  await fixture(page, { failChatOnce: true, conflict: true });
  await open(page); await selectTask(page); await openAgent(page);
  await send(page, "Valuta il controllo");
  const chat = page.getByRole("dialog", { name: "Agente di Review" });
  await expect(chat.getByRole("alert")).toContainText("La risposta non è stata completata");
  await chat.getByRole("button", { name: "Riprova", exact: true }).click();
  await expect(chat).toContainText("Il controllo è utile");
  await page.getByRole("button", { name: "Salva come ipotesi" }).click();
  await page.getByRole("menuitem", { name: "Proposta As-Is", exact: true }).click();
  await page.getByLabel("Titolo", { exact: true }).fill("Proposta conservata");
  await page.getByRole("button", { name: "Registra azione" }).click();
  await expect(page.getByRole("alert")).toContainText("La base della review è cambiata");
  await expect(page.getByLabel("Titolo", { exact: true })).toHaveValue("Proposta conservata");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Salva come ipotesi" })).toBeFocused();
});


test("avatar opens on demand and chat resizing persists across tasks", async ({ page }, info) => {
  if (info.project.name === "chromium") await page.setViewportSize({ width: 1600, height: 1000 });
  await fixture(page); await open(page); await selectTask(page);
  const chat = page.locator(".review-agent-chat");
  await expect(chat).toBeHidden();
  await selectTask(page, "Emettere ordine"); await expect(chat).toBeHidden();
  await openAgent(page);
  const before = (await chat.boundingBox())!;
  const handle = page.getByRole("button", { name: "Ridimensiona chat DeliR" });
  await handle.focus();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await expect(chat).toHaveCSS("height", `${Math.round(before.height - 40)}px`);
  if (info.project.name === "chromium") {
    await page.keyboard.press("ArrowLeft");
    await expect(chat).toHaveCSS("width", `${Math.round(before.width + 20)}px`);
    const grip = (await handle.boundingBox())!;
    await page.mouse.move(grip.x + grip.width / 2, grip.y + grip.height / 2); await page.mouse.down();
    await page.mouse.move(grip.x + grip.width / 2 - 80, grip.y + grip.height / 2 - 60); await page.mouse.up();
    await expect(chat).toHaveCSS("width", `${Math.round(before.width + 100)}px`);
    await expect(chat).toHaveCSS("height", `${Math.round(before.height + 20)}px`);
  }
  const resized = (await chat.boundingBox())!;
  await page.getByRole("button", { name: "Chiudi chat DeliR" }).click();
  await expect(chat).toBeHidden(); await selectTask(page); await openAgent(page);
  const retained = (await chat.boundingBox())!;
  expect(retained.width).toBe(resized.width); expect(retained.height).toBe(resized.height);
  await handle.focus(); await page.keyboard.press("Home");
  // WebKit retains fractional CSS pixels in viewport-derived dimensions.
  // Reset must restore the original measured size, rather than an integer.
  await expect.poll(() => chat.evaluate(element => element.getBoundingClientRect().height)).toBeCloseTo(before.height, 1);
  expect((await new AxeBuilder({ page }).include(".process-review-workspace").analyze()).violations).toEqual([]);
});


test("enterprise policy diagram renders real-owner lanes, process pool and branch labels", async ({ page }, info) => {
  if (!info.project.name.startsWith("mobile-")) await page.setViewportSize({ width: 1600, height: 1000 });
  await fixture(page, { enterpriseDiagram: true });
  await open(page); await selectTask(page); await openAgent(page);
  await send(page, "Disegna la proposta di acquisto con owner e condizioni espliciti.");
  await expect(page.getByRole("button", { name: "Salva come ipotesi" })).toBeVisible();
  await page.getByRole("dialog", { name: "Agente di Review" }).getByRole("button", { name: "Apri conoscenza e proposte del task" }).click();
  await page.getByRole("tab", { name: "Proposte", exact: true }).click();
  await page.getByRole("button", { name: "Apri diagramma", exact: true }).click();
  const preview = page.getByRole("dialog", { name: "Esplicitare il controllo di completezza" });
  for (const id of ["Company", "Supplier", "Technical", "Purchasing", "Maintenance", "Director_Sign", "Request_Document"])
    await expect(preview.locator(`.djs-element[data-element-id='${id}']`)).toBeVisible();
  for (const text of ["Ufficio tecnico", "Acquisti", "Manutenzione", "Sopra soglia", "Sotto soglia"])
    await expect(preview.locator(".djs-label").filter({ hasText: text }).first()).toBeVisible();
  await expect(preview.locator(".djs-connection")).toHaveCount(11);
  await expect(preview.locator(".delir-canvas-identity")).toHaveText("DeliR");
  await expect(preview.locator(".delir-canvas-identity svg")).toBeVisible();
  await expect(preview.locator(".delir-role-band")).toHaveCount(5);
  const task = preview.locator(".djs-element[data-element-id='Verify'] .djs-visual > rect").first();
  const gateway = preview.locator(".djs-element[data-element-id='Decision'] .djs-visual > polygon").first();
  expect(await task.evaluate(el => getComputedStyle(el).fill)).not.toBe(await gateway.evaluate(el => getComputedStyle(el).fill));
  // The branded presentation must keep the actual activity label inside its shape.
  for (const id of ["Open_Request", "Verify", "Director_Sign", "Create_Order", "Urgent_Call"]) {
    const visual = preview.locator(`.djs-element[data-element-id='${id}'] .djs-visual`);
    const box = (await visual.locator("rect").first().boundingBox())!;
    const text = (await visual.locator("text").boundingBox())!;
    expect(text.x).toBeGreaterThanOrEqual(box.x - 2);
    expect(text.y).toBeGreaterThanOrEqual(box.y - 2);
    expect(text.x + text.width).toBeLessThanOrEqual(box.x + box.width + 2);
    expect(text.y + text.height).toBeLessThanOrEqual(box.y + box.height + 2);
  }
  const geometry = await preview.locator(".djs-element[data-element-id='Start'], .djs-element[data-element-id='Open_Request'], .djs-element[data-element-id='Verify'], .djs-element[data-element-id='Decision'], .djs-element[data-element-id='Create_Order'], .djs-element[data-element-id='End']").evaluateAll(elements => Object.fromEntries(elements.map(element => [element.getAttribute("data-element-id"), element.getBoundingClientRect().x])));
  expect(geometry.Start).toBeLessThan(geometry.Open_Request);
  expect(geometry.Open_Request).toBeLessThan(geometry.Verify);
  expect(geometry.Verify).toBeLessThan(geometry.Decision);
  expect(geometry.Decision).toBeLessThan(geometry.Create_Order);
  expect(geometry.Create_Order).toBeLessThan(geometry.End);
  await page.screenshot({ path: info.outputPath("enterprise-layout-proposal.png") });
});
