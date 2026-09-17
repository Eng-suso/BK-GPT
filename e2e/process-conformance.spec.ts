import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * Il confronto con le fonti, dal punto di vista del consulente.
 *
 * Il disegno esce subito e la verifica gira dietro: il pannello deve dire
 * quale dei tre stati e' vero - in corso, un esito, nessun esito - senza mai
 * spacciare per attuale un confronto che descrive il disegno di prima. I punti
 * che una rilettura delle fonti puo' chiudere si integrano con un bottone; i
 * disaccordi fra due voci no, e infatti non compaiono nel conteggio.
 *
 * Il backend e' finto ma tiene lo stato come quello vero. Le schermate finiscono
 * in `test-results/conformance-*.png` per la verifica visiva desktop e mobile.
 */

const API = "http://127.0.0.1:8000";
const PROJECT = "p1";
const PROCESS = "pr1";
const MODEL = "bpmn-1";

const CANVAS = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="D" targetNamespace="https://workspace.local/bpmn">
  <bpmn:process id="P" isExecutable="false">
    <bpmn:startEvent id="Start" name="Fabbisogno rilevato"><bpmn:outgoing>f1</bpmn:outgoing></bpmn:startEvent>
    <bpmn:userTask id="apri" name="Apri richiesta di acquisto"><bpmn:incoming>f1</bpmn:incoming><bpmn:outgoing>f2</bpmn:outgoing></bpmn:userTask>
    <bpmn:endEvent id="End" name="Ordine inviato"><bpmn:incoming>f2</bpmn:incoming></bpmn:endEvent>
    <bpmn:sequenceFlow id="f1" sourceRef="Start" targetRef="apri" />
    <bpmn:sequenceFlow id="f2" sourceRef="apri" targetRef="End" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="Dia"><bpmndi:BPMNPlane id="Plane" bpmnElement="P">
    <bpmndi:BPMNShape id="Start_di" bpmnElement="Start"><dc:Bounds x="100" y="122" width="36" height="36" /></bpmndi:BPMNShape>
    <bpmndi:BPMNShape id="apri_di" bpmnElement="apri"><dc:Bounds x="200" y="100" width="120" height="80" /></bpmndi:BPMNShape>
    <bpmndi:BPMNShape id="End_di" bpmnElement="End"><dc:Bounds x="400" y="122" width="36" height="36" /></bpmndi:BPMNShape>
    <bpmndi:BPMNEdge id="f1_di" bpmnElement="f1"><di:waypoint x="136" y="140" /><di:waypoint x="200" y="140" /></bpmndi:BPMNEdge>
    <bpmndi:BPMNEdge id="f2_di" bpmnElement="f2"><di:waypoint x="320" y="140" /><di:waypoint x="400" y="140" /></bpmndi:BPMNEdge>
  </bpmndi:BPMNPlane></bpmndi:BPMNDiagram>
</bpmn:definitions>`;

const PROVENANCE = {
  process_id: PROCESS,
  snapshot_id: "s1",
  snapshot_label: "V3",
  has_plan: true,
  total: 1,
  verified: 1,
  paraphrased: 0,
  label_grounded: 0,
  unverified: 0,
  awaiting_confirmation: 0,
  grounded_ratio: 1,
  sources_checked: 3,
  unused_sources: [],
  elements: [
    {
      kind: "step",
      element_id: "apri",
      label: "Apri richiesta di acquisto",
      status: "verified",
      mark_status: "verified",
      source_ref: "steps:apri",
      source_id: "a1",
      source_name: "Intervista Laura Conti",
      quote: "apro una richiesta di acquisto e la mando ad Acquisti per mail",
      consultant_decision: null,
      removable: true,
    },
  ],
};

function report(verdict: string, findings: Record<string, unknown>[]) {
  return {
    verdict,
    findings,
    sources_audited: 3,
    sources_with_text: 3,
    llm_audit: "done",
    llm_audit_note: "",
    discarded_findings: 0,
    snapshot_id: "s1",
    canvas_signature: "abc123",
    audited_at: "2026-09-17T21:05:00+00:00",
  };
}

const MISSING = {
  layer: "source_coverage",
  severity: "gap",
  code: "missing_activity",
  message:
    "«Intervista Paolo Marchetti» dice «chiamo direttamente il fornitore e faccio consegnare», e il disegno non lo rappresenta (nelle urgenze Manutenzione chiama il fornitore).",
  element_ref: "",
  source_name: "Intervista Paolo Marchetti",
};

const DIVERGENCE = {
  layer: "source_divergence",
  severity: "gap",
  code: "sources_disagree",
  message:
    "«Verifica autorizzazione»: «Intervista Francesca Neri» e «Intervista Paolo Marchetti» lo raccontano in modo diverso. Il disegno segue «Intervista Francesca Neri»: serve una tua conferma su come funziona davvero.",
  element_ref: "steps:verifica",
  source_name: "Intervista Paolo Marchetti",
};

type Scenario = "running" | "points" | "conformant";

async function fixture(page: Page, scenario: Scenario) {
  const state = { repaired: false, audits: 0 };

  await page.route(`${API}/**`, async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();

    if (path === `/v1/workspace/projects/${PROJECT}` && method === "GET") {
      return route.fulfill({
        json: {
          id: PROJECT, client_id: "esaote", client: "Esaote", name: "Mappatura ciclo passivo",
          objective: "Mappare l'AS-IS", lead: "Marco Bianchi", start_date: null, end_date: null,
          phase: "Discovery", status: "In corso", progress: 40, processes: 1,
          next_step: "Rivedere il disegno", milestones: [], open_issues: [], deliverables: [],
          archived_at: null, archive_reason: null,
          process_items: [{
            id: PROCESS, project_id: PROJECT, bpmn_model_id: MODEL, name: "Ciclo passivo",
            stage: "AS-IS", status: "In corso", owner: "Francesca Neri", readiness: 6,
            archived_at: null, archive_reason: null,
          }],
        },
      });
    }
    if (path === `/v1/workspace/bpmn-models/${MODEL}` && method === "GET") {
      return route.fulfill({ json: { id: MODEL, process_id: PROCESS, name: "Ciclo passivo", xml: CANVAS } });
    }
    if (path === `/v1/workspace/bpmn-models/${MODEL}/versions`) {
      return route.fulfill({ json: [] });
    }
    if (path === `/v1/workspace/processes/${PROCESS}/provenance` && method === "GET") {
      return route.fulfill({ json: PROVENANCE });
    }
    if (path === `/v1/workspace/processes/${PROCESS}/conformance/repair` && method === "POST") {
      state.repaired = true;
      return route.fulfill({ json: { status: "drafted", reason_code: "drafted", process_id: PROCESS, bpmn_model_id: MODEL } });
    }
    if (path === `/v1/workspace/processes/${PROCESS}/conformance` && method === "GET") {
      if (scenario === "running") {
        return route.fulfill({
          json: { process_id: PROCESS, snapshot_id: "s1", snapshot_label: "V3", running: true, is_current: false, report: null },
        });
      }
      if (scenario === "conformant" || state.repaired) {
        return route.fulfill({
          json: { process_id: PROCESS, snapshot_id: "s1", snapshot_label: "V3", running: false, is_current: true, report: report("conformant", []) },
        });
      }
      return route.fulfill({
        json: {
          process_id: PROCESS, snapshot_id: "s1", snapshot_label: "V3", running: false, is_current: true,
          report: report("not_conformant", [MISSING, DIVERGENCE]),
        },
      });
    }
    return route.fulfill({ status: 200, json: [] });
  });

  return state;
}

async function openPanel(page: Page) {
  await page.goto(`/projects/${PROJECT}/processes/${PROCESS}?view=canvas`);
  await expect(page.locator(".process-bpmn-canvas [data-element-id='apri']")).toBeVisible();
  await page.getByRole("button", { name: /Revisione delle evidenze del disegno/ }).click();
  const panel = page.getByRole("complementary", { name: "Evidenze del disegno" });
  await expect(panel).toBeVisible();
  return panel;
}

test("mentre la verifica gira, il pannello lo dice invece di dichiarare un esito", async ({ page }, testInfo) => {
  await fixture(page, "running");
  const panel = await openPanel(page);

  await expect(panel).toContainText("Confronto in corso");
  await expect(panel).toContainText("Puoi continuare a lavorare");
  await expect(panel).not.toContainText("coincide con le fonti");

  await page.screenshot({
    path: testInfo.outputPath(`conformance-${testInfo.project.name}-running.png`),
    fullPage: false,
  });
});

test("i punti da rivedere sono raggruppati, e solo quelli integrabili si integrano", async ({ page }, testInfo) => {
  await fixture(page, "points");
  const panel = await openPanel(page);

  await expect(panel).toContainText("2 punti da rivedere");
  await expect(panel).toContainText("Detto nelle fonti, assente nel disegno");
  await expect(panel).toContainText("Le fonti si contraddicono fra loro");
  // Il disaccordo fra due voci non si integra riscrivendo il piano: si chiede.
  const repair = panel.getByRole("button", { name: "Integra nel disegno 1 punto" });
  await expect(repair).toBeVisible();

  await page.screenshot({
    path: testInfo.outputPath(`conformance-${testInfo.project.name}-points.png`),
    fullPage: false,
  });

  await repair.click();
  await expect(panel).toContainText("Il disegno coincide con le fonti");
});

test("quando coincide, lo dice con quante fonti e quando", async ({ page }, testInfo) => {
  await fixture(page, "conformant");
  const panel = await openPanel(page);

  await expect(panel).toContainText("Il disegno coincide con le fonti");
  await expect(panel).toContainText("Confrontato con 3 fonti");
  // Niente linguaggio da sviluppatore sotto gli occhi del consulente.
  await expect(panel).not.toContainText("snapshot");
  await expect(panel).not.toContainText("steps:");

  await page.screenshot({
    path: testInfo.outputPath(`conformance-${testInfo.project.name}-conformant.png`),
    fullPage: false,
  });
});
