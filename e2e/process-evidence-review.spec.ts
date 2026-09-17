import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * La revisione delle evidenze, dal punto di vista del consulente.
 *
 * Il disegno arriva con i segni di provenance scritti dal backend; il pannello
 * "Evidenze" mette prima cio' che nessuna fonte regge. Il backend e' finto ma
 * tiene lo stato come quello vero: una conferma aggiorna il rapporto e il
 * segno sul canvas salvato, e il canvas si ricarica.
 *
 * Le schermate finiscono in `test-results/evidence-*.png` per la verifica
 * visiva desktop e mobile; non sono snapshot confrontati, quindi il test non
 * dipende dal font del runner.
 */

const API = "http://127.0.0.1:8000";
const PROJECT = "p1";
const PROCESS = "pr1";
const MODEL = "bpmn-1";

const doc = (ref: string) =>
  `<bpmn:documentation>DeliR traceability:\n{"source_refs": ["${ref}"]}</bpmn:documentation>`;

function canvasXml(auditMark: "unverified" | "confirmed") {
  return `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" xmlns:delir="https://delir.app/schema/bpmn/provenance" id="D" targetNamespace="https://workspace.local/bpmn">
  <bpmn:process id="P" isExecutable="false">
    <bpmn:startEvent id="Start" name="Fabbisogno rilevato"><bpmn:outgoing>f1</bpmn:outgoing></bpmn:startEvent>
    <bpmn:userTask id="apri" name="Apri richiesta di acquisto" delir:provenance="verified">${doc("steps:apri")}<bpmn:incoming>f1</bpmn:incoming><bpmn:outgoing>f2</bpmn:outgoing></bpmn:userTask>
    <bpmn:userTask id="audit" name="Audit trimestrale fornitori" delir:provenance="${auditMark}">${doc("steps:audit")}<bpmn:incoming>f2</bpmn:incoming><bpmn:outgoing>f3</bpmn:outgoing></bpmn:userTask>
    <bpmn:userTask id="ordine" name="Emetti ordine" delir:provenance="label_grounded">${doc("steps:ordine")}<bpmn:incoming>f3</bpmn:incoming><bpmn:outgoing>f4</bpmn:outgoing></bpmn:userTask>
    <bpmn:endEvent id="End" name="Ordine inviato"><bpmn:incoming>f4</bpmn:incoming></bpmn:endEvent>
    <bpmn:sequenceFlow id="f1" sourceRef="Start" targetRef="apri" />
    <bpmn:sequenceFlow id="f2" sourceRef="apri" targetRef="audit" />
    <bpmn:sequenceFlow id="f3" sourceRef="audit" targetRef="ordine" />
    <bpmn:sequenceFlow id="f4" sourceRef="ordine" targetRef="End" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="Dia"><bpmndi:BPMNPlane id="Plane" bpmnElement="P">
    <bpmndi:BPMNShape id="Start_di" bpmnElement="Start"><dc:Bounds x="100" y="122" width="36" height="36" /></bpmndi:BPMNShape>
    <bpmndi:BPMNShape id="apri_di" bpmnElement="apri"><dc:Bounds x="200" y="100" width="120" height="80" /></bpmndi:BPMNShape>
    <bpmndi:BPMNShape id="audit_di" bpmnElement="audit"><dc:Bounds x="380" y="100" width="120" height="80" /></bpmndi:BPMNShape>
    <bpmndi:BPMNShape id="ordine_di" bpmnElement="ordine"><dc:Bounds x="560" y="100" width="120" height="80" /></bpmndi:BPMNShape>
    <bpmndi:BPMNShape id="End_di" bpmnElement="End"><dc:Bounds x="740" y="122" width="36" height="36" /></bpmndi:BPMNShape>
    <bpmndi:BPMNEdge id="f1_di" bpmnElement="f1"><di:waypoint x="136" y="140" /><di:waypoint x="200" y="140" /></bpmndi:BPMNEdge>
    <bpmndi:BPMNEdge id="f2_di" bpmnElement="f2"><di:waypoint x="320" y="140" /><di:waypoint x="380" y="140" /></bpmndi:BPMNEdge>
    <bpmndi:BPMNEdge id="f3_di" bpmnElement="f3"><di:waypoint x="500" y="140" /><di:waypoint x="560" y="140" /></bpmndi:BPMNEdge>
    <bpmndi:BPMNEdge id="f4_di" bpmnElement="f4"><di:waypoint x="680" y="140" /><di:waypoint x="740" y="140" /></bpmndi:BPMNEdge>
  </bpmndi:BPMNPlane></bpmndi:BPMNDiagram>
</bpmn:definitions>`;
}

type Element = Record<string, unknown>;

function provenance(auditConfirmed: boolean) {
  const elements: Element[] = [
    {
      kind: "step", element_id: "apri", label: "Apri richiesta di acquisto",
      status: "verified", mark_status: "verified", source_ref: "steps:apri",
      source_id: "a1", source_name: "Intervista Laura Conti",
      quote: "apro una richiesta di acquisto e la mando ad Acquisti per mail",
      consultant_decision: null, removable: true,
    },
    {
      kind: "step", element_id: "audit", label: "Audit trimestrale fornitori",
      status: "unverified", mark_status: auditConfirmed ? "confirmed" : "unverified",
      source_ref: "steps:audit", source_id: "", source_name: "", quote: "",
      consultant_decision: auditConfirmed ? "confirmed" : null, removable: true,
    },
    {
      kind: "step", element_id: "ordine", label: "Emetti ordine",
      status: "label_grounded", mark_status: "label_grounded", source_ref: "steps:ordine",
      source_id: "a3", source_name: "Intervista Francesca Neri",
      quote: "Per le cose piccole e ricorrenti ho margine per procedere da sola: emetto l'ordine e via.",
      consultant_decision: null, removable: true,
    },
    {
      kind: "decision", element_id: "soglia", label: "Serve autorizzazione?",
      status: "unverified", mark_status: "unverified", source_ref: "decisions:soglia",
      source_id: "", source_name: "", quote: "", consultant_decision: null, removable: false,
    },
  ];
  return {
    process_id: PROCESS, snapshot_id: "s1", snapshot_label: "V4", has_plan: true,
    total: 4, verified: 1, paraphrased: 0, label_grounded: 1, unverified: 2,
    awaiting_confirmation: auditConfirmed ? 1 : 2, grounded_ratio: 0.5, sources_checked: 3,
    unused_sources: ["Intervista Paolo Marchetti"], elements,
  };
}

async function fixture(page: Page) {
  const state = { auditConfirmed: false, decisions: [] as unknown[] };

  await page.addInitScript(() =>
    Object.assign(window, { DELIR_API_BASE: "http://127.0.0.1:8000" }),
  );

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
      return route.fulfill({
        json: {
          id: MODEL, process_id: PROCESS, name: "Ciclo passivo",
          xml: canvasXml(state.auditConfirmed ? "confirmed" : "unverified"),
        },
      });
    }
    if (path === `/v1/workspace/bpmn-models/${MODEL}/versions`) {
      return route.fulfill({ json: [] });
    }
    if (path === `/v1/workspace/processes/${PROCESS}/provenance` && method === "GET") {
      return route.fulfill({ json: provenance(state.auditConfirmed) });
    }
    if (path === `/v1/workspace/processes/${PROCESS}/provenance/decisions` && method === "POST") {
      const body = request.postDataJSON() as { source_ref: string; decision: string };
      state.decisions.push(body);
      if (body.source_ref === "steps:audit" && body.decision === "confirmed") {
        state.auditConfirmed = true;
      }
      return route.fulfill({
        json: {
          ok: true, reason_code: "reviewed", reason: "«Audit trimestrale fornitori» confermato.",
          provenance: provenance(state.auditConfirmed), draft_status: null,
          pending_verification: [],
        },
      });
    }
    return route.fulfill({ status: 200, json: [] });
  });

  return state;
}

async function openCanvas(page: Page) {
  await page.goto(`/projects/${PROJECT}/processes/${PROCESS}?view=canvas`);
  await expect(page.locator(".process-bpmn-canvas [data-element-id='audit']")).toBeVisible();
}

test("il disegno segna cio' che nessuna fonte regge, e il pannello lo mette per primo", async ({
  page,
}, testInfo) => {
  await fixture(page);
  await openCanvas(page);

  const audit = page.locator(".process-bpmn-canvas [data-element-id='audit']");
  await expect(audit).toHaveClass(/delir-provenance-unverified/);
  // I nodi che le fonti citano non hanno segno: sono la norma.
  await expect(page.locator(".process-bpmn-canvas [data-element-id='apri']")).not.toHaveClass(
    /delir-provenance/,
  );

  const toggle = page.getByRole("button", { name: /Revisione delle evidenze del disegno \(2\)/ });
  await toggle.click();

  const panel = page.getByRole("complementary", { name: "Evidenze del disegno" });
  await expect(panel).toBeVisible();
  const awaiting = panel.locator("section").filter({ hasText: "Da confermare" }).first();
  await expect(awaiting).toContainText("Audit trimestrale fornitori");
  await expect(panel).toContainText("Intervista Paolo Marchetti");

  await page.screenshot({
    path: testInfo.outputPath(`evidence-${testInfo.project.name}-open.png`),
    fullPage: false,
  });
});

test("confermare un'inferenza la toglie da quelle da rivedere e cambia il segno sul disegno", async ({
  page,
}, testInfo) => {
  const state = await fixture(page);
  await openCanvas(page);
  await page.getByRole("button", { name: /Revisione delle evidenze del disegno/ }).click();

  const panel = page.getByRole("complementary", { name: "Evidenze del disegno" });
  await panel.getByRole("button", { name: /Conferma «Audit trimestrale fornitori»/ }).click();

  await expect(panel.getByRole("heading", { name: /Confermati da te/ })).toBeVisible();
  expect(state.decisions).toEqual([{ source_ref: "steps:audit", decision: "confirmed", note: "" }]);
  await expect(page.locator(".process-bpmn-canvas [data-element-id='audit']")).toHaveClass(
    /delir-provenance-confirmed/,
  );
  // La decisione non si rifiuta da qui: la riga lo dice invece di nascondere l'azione.
  await expect(panel).toContainText("Attori e decisioni si correggono sul piano");

  await page.screenshot({
    path: testInfo.outputPath(`evidence-${testInfo.project.name}-confirmed.png`),
    fullPage: false,
  });
});

test("il rifiuto chiede conferma e il pannello si usa da tastiera", async ({ page }) => {
  await fixture(page);
  await openCanvas(page);
  await page.getByRole("button", { name: /Revisione delle evidenze del disegno/ }).click();

  const panel = page.getByRole("complementary", { name: "Evidenze del disegno" });
  const reject = panel.getByRole("button", { name: /Rifiuta «Audit trimestrale fornitori»/ });
  await reject.focus();
  await page.keyboard.press("Enter");
  await expect(
    panel.getByRole("button", { name: /togli «Audit trimestrale fornitori» dal piano e ridisegna/ }),
  ).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(panel.getByRole("button", { name: "Annulla" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(panel.getByRole("button", { name: /dal piano e ridisegna/ })).toHaveCount(0);
});
