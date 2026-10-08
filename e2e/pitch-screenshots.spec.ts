import { expect, test, type Browser, type Locator, type Page, type Route } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const API = "http://127.0.0.1:8000";
const OUT = resolve(process.cwd(), "artifacts", "pitch-screenshots");
const PROJECT = "pitch-procurement";
const PROCESS = "purchase-to-pay";
const MODEL = "p2p-model";
const RUN = 42;

const processItem = {
  id: PROCESS,
  project_id: PROJECT,
  bpmn_model_id: MODEL,
  name: "Purchase-to-Pay",
  stage: "AS-IS",
  status: "Da validare",
  owner: "Team Operations",
  readiness: 82,
  archived_at: null,
  archive_reason: null,
};

const project = {
  id: PROJECT,
  client_id: "alpina-components",
  client: "Alpina Components",
  name: "Trasformazione ciclo acquisti",
  objective:
    "Ridurre tempi e rilavorazioni del ciclo Purchase-to-Pay, mantenendo tracciabilita e controllo sulle approvazioni.",
  lead: "Giulia Ferri",
  start_date: "2026-07-01",
  end_date: "2026-10-31",
  phase: "Validazione",
  status: "In corso",
  progress: 68,
  processes: 3,
  next_step: "Validare il modello AS-IS e confrontare lo scenario TO-BE",
  milestones: [
    { title: "Interviste stakeholder", status: "done", completed_at: "2026-07-18" },
    { title: "Modello AS-IS", status: "done", completed_at: "2026-08-12" },
    { title: "Validazione con Operations", status: "planned", completed_at: null },
    { title: "Business case TO-BE", status: "planned", completed_at: null },
  ],
  open_issues: ["Definire la soglia di approvazione per gli acquisti urgenti"],
  deliverables: ["BPMN AS-IS validato", "Scenario TO-BE", "Business case operativo"],
  archived_at: null,
  archive_reason: null,
  process_items: [
    processItem,
    {
      id: "vendor-onboarding",
      project_id: PROJECT,
      bpmn_model_id: "vendor-model",
      name: "Onboarding fornitori",
      stage: "Discovery",
      status: "In corso",
      owner: "Procurement",
      readiness: 54,
      archived_at: null,
      archive_reason: null,
    },
    {
      id: "invoice-matching",
      project_id: PROJECT,
      bpmn_model_id: "invoice-model",
      name: "Riconciliazione fatture",
      stage: "TO-BE",
      status: "Bozza",
      owner: "Finance",
      readiness: 41,
      archived_at: null,
      archive_reason: null,
    },
  ],
};

const projects = [
  project,
  {
    ...project,
    id: "quality-claims",
    client_id: "nova-retail",
    client: "Nova Retail",
    name: "Gestione reclami qualita",
    phase: "Discovery",
    status: "In corso",
    progress: 34,
    processes: 2,
    next_step: "Completare le interviste di front-line",
    process_items: [],
  },
  {
    ...project,
    id: "order-to-cash",
    name: "Ottimizzazione Order-to-Cash",
    phase: "Simulazione",
    status: "A rischio",
    progress: 77,
    processes: 4,
    next_step: "Rivedere capacita del team Credit Control",
    process_items: [],
  },
];

const clients = [
  {
    id: "alpina-components",
    name: "Alpina Components",
    sector: "Manufacturing",
    status: "Attivo",
    projects: 2,
    next_activity: "Validazione AS-IS · 29 set",
    owner: "Giulia Ferri",
    contact: "",
    processes: [],
    documents: [],
    archived_at: null,
    archive_reason: null,
  },
  {
    id: "nova-retail",
    name: "Nova Retail",
    sector: "Retail",
    status: "Da seguire",
    projects: 1,
    next_activity: "Intervista Operations · 02 ott",
    owner: "Luca Moretti",
    contact: "",
    processes: [],
    documents: [],
    archived_at: null,
    archive_reason: null,
  },
];

const sources = [
  ["source-1", "Intervista Responsabile Acquisti", "Intervista · 42 min"],
  ["source-2", "Intervista Finance & Controlling", "Intervista · 36 min"],
  ["source-3", "Procedura approvazione ordini", "Policy · PDF"],
  ["source-4", "Export ERP ordini Q2", "Dati operativi · CSV"],
].map(([id, name, meta]) => ({
  id,
  project_id: PROJECT,
  process_id: PROCESS,
  name,
  type: meta.split(" · ")[0],
  meta,
  roles: ["process_evidence"],
  retention: "persistent",
  scopes: [{ type: "process", id: PROCESS }],
  status: "ready",
  byte_size: 128000,
  content_hash: `hash-${id}`,
  mime_type: "text/plain",
}));

const decisions = [
  {
    id: "decision-1",
    project_id: PROJECT,
    process_id: PROCESS,
    title: "Approvazione obbligatoria sopra 5.000 EUR",
    owner: "CFO",
    status: "Confermata",
  },
  {
    id: "decision-2",
    project_id: PROJECT,
    process_id: PROCESS,
    title: "Percorso fast-track per acquisti urgenti",
    owner: "Procurement",
    status: "Da decidere",
  },
];

const xml = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" id="Definitions_pitch" targetNamespace="https://delir.ai/pitch">
  <bpmn:process id="Process_p2p" isExecutable="false">
    <bpmn:laneSet id="P2P_Lanes">
      <bpmn:lane id="Lane_Requester" name="Richiedente">
        <bpmn:flowNodeRef>Start</bpmn:flowNodeRef><bpmn:flowNodeRef>Request</bpmn:flowNodeRef><bpmn:flowNodeRef>Rework</bpmn:flowNodeRef>
      </bpmn:lane>
      <bpmn:lane id="Lane_Procurement" name="Ufficio Acquisti">
        <bpmn:flowNodeRef>Validate</bpmn:flowNodeRef><bpmn:flowNodeRef>Complete</bpmn:flowNodeRef><bpmn:flowNodeRef>CreatePO</bpmn:flowNodeRef><bpmn:flowNodeRef>End</bpmn:flowNodeRef>
      </bpmn:lane>
    </bpmn:laneSet>
    <bpmn:startEvent id="Start" name="Fabbisogno rilevato"><bpmn:outgoing>f1</bpmn:outgoing></bpmn:startEvent>
    <bpmn:userTask id="Request" name="Compila richiesta"><bpmn:incoming>f1</bpmn:incoming><bpmn:outgoing>f2</bpmn:outgoing></bpmn:userTask>
    <bpmn:userTask id="Validate" name="Verifica richiesta"><bpmn:incoming>f2</bpmn:incoming><bpmn:incoming>f5</bpmn:incoming><bpmn:outgoing>f3</bpmn:outgoing></bpmn:userTask>
    <bpmn:exclusiveGateway id="Complete" name="Richiesta completa?" default="f4"><bpmn:incoming>f3</bpmn:incoming><bpmn:outgoing>f4</bpmn:outgoing><bpmn:outgoing>f6</bpmn:outgoing></bpmn:exclusiveGateway>
    <bpmn:userTask id="Rework" name="Integra informazioni"><bpmn:incoming>f4</bpmn:incoming><bpmn:outgoing>f5</bpmn:outgoing></bpmn:userTask>
    <bpmn:userTask id="CreatePO" name="Emetti ordine"><bpmn:incoming>f6</bpmn:incoming><bpmn:outgoing>f7</bpmn:outgoing></bpmn:userTask>
    <bpmn:endEvent id="End" name="Ordine emesso"><bpmn:incoming>f7</bpmn:incoming></bpmn:endEvent>
    <bpmn:sequenceFlow id="f1" sourceRef="Start" targetRef="Request" />
    <bpmn:sequenceFlow id="f2" sourceRef="Request" targetRef="Validate" />
    <bpmn:sequenceFlow id="f3" sourceRef="Validate" targetRef="Complete" />
    <bpmn:sequenceFlow id="f4" name="No" sourceRef="Complete" targetRef="Rework" />
    <bpmn:sequenceFlow id="f5" sourceRef="Rework" targetRef="Validate" />
    <bpmn:sequenceFlow id="f6" name="Si" sourceRef="Complete" targetRef="CreatePO"><bpmn:conditionExpression xsi:type="bpmn:tFormalExpression"><![CDATA[requestComplete = true]]></bpmn:conditionExpression></bpmn:sequenceFlow>
    <bpmn:sequenceFlow id="f7" sourceRef="CreatePO" targetRef="End" />
  </bpmn:process>
  <bpmn:collaboration id="Collaboration_p2p">
    <bpmn:participant id="Participant_Buyer" name="Alpina Components" processRef="Process_p2p" />
  </bpmn:collaboration>
  <bpmndi:BPMNDiagram id="Diagram_pitch"><bpmndi:BPMNPlane id="Plane_pitch" bpmnElement="Collaboration_p2p">
    <bpmndi:BPMNShape id="Participant_Buyer_di" bpmnElement="Participant_Buyer" isHorizontal="true"><dc:Bounds x="40" y="40" width="1260" height="360" /></bpmndi:BPMNShape>
    <bpmndi:BPMNShape id="Lane_Requester_di" bpmnElement="Lane_Requester" isHorizontal="true"><dc:Bounds x="70" y="40" width="1230" height="180" /></bpmndi:BPMNShape>
    <bpmndi:BPMNShape id="Lane_Procurement_di" bpmnElement="Lane_Procurement" isHorizontal="true"><dc:Bounds x="70" y="220" width="1230" height="180" /></bpmndi:BPMNShape>
    <bpmndi:BPMNShape id="Start_di" bpmnElement="Start"><dc:Bounds x="110" y="112" width="36" height="36" /></bpmndi:BPMNShape>
    <bpmndi:BPMNShape id="Request_di" bpmnElement="Request"><dc:Bounds x="205" y="90" width="140" height="80" /></bpmndi:BPMNShape>
    <bpmndi:BPMNShape id="Validate_di" bpmnElement="Validate"><dc:Bounds x="410" y="270" width="145" height="80" /></bpmndi:BPMNShape>
    <bpmndi:BPMNShape id="Complete_di" bpmnElement="Complete" isMarkerVisible="true"><dc:Bounds x="635" y="285" width="50" height="50" /></bpmndi:BPMNShape>
    <bpmndi:BPMNShape id="Rework_di" bpmnElement="Rework"><dc:Bounds x="590" y="90" width="140" height="80" /></bpmndi:BPMNShape>
    <bpmndi:BPMNShape id="CreatePO_di" bpmnElement="CreatePO"><dc:Bounds x="825" y="270" width="145" height="80" /></bpmndi:BPMNShape>
    <bpmndi:BPMNShape id="End_di" bpmnElement="End"><dc:Bounds x="1080" y="292" width="36" height="36" /></bpmndi:BPMNShape>
    <bpmndi:BPMNEdge id="f1_di" bpmnElement="f1"><di:waypoint x="146" y="130" /><di:waypoint x="205" y="130" /></bpmndi:BPMNEdge>
    <bpmndi:BPMNEdge id="f2_di" bpmnElement="f2"><di:waypoint x="345" y="130" /><di:waypoint x="380" y="130" /><di:waypoint x="380" y="310" /><di:waypoint x="410" y="310" /></bpmndi:BPMNEdge>
    <bpmndi:BPMNEdge id="f3_di" bpmnElement="f3"><di:waypoint x="555" y="310" /><di:waypoint x="635" y="310" /></bpmndi:BPMNEdge>
    <bpmndi:BPMNEdge id="f4_di" bpmnElement="f4"><di:waypoint x="660" y="285" /><di:waypoint x="660" y="170" /></bpmndi:BPMNEdge>
    <bpmndi:BPMNEdge id="f5_di" bpmnElement="f5"><di:waypoint x="590" y="130" /><di:waypoint x="505" y="130" /><di:waypoint x="505" y="270" /></bpmndi:BPMNEdge>
    <bpmndi:BPMNEdge id="f6_di" bpmnElement="f6"><di:waypoint x="685" y="310" /><di:waypoint x="825" y="310" /></bpmndi:BPMNEdge>
    <bpmndi:BPMNEdge id="f7_di" bpmnElement="f7"><di:waypoint x="970" y="310" /><di:waypoint x="1080" y="310" /></bpmndi:BPMNEdge>
  </bpmndi:BPMNPlane></bpmndi:BPMNDiagram>
</bpmn:definitions>`;

const review = {
  bpmn_model_id: MODEL,
  process_id: PROCESS,
  version: 3,
  source_text: "Sintesi di quattro fonti operative.",
  bpmn_brief:
    "## Purchase-to-Pay\n\nIl processo parte dal fabbisogno, verifica la completezza della richiesta e termina con l'emissione dell'ordine.",
  readiness_score: 8.2,
  missing_information: ["SLA del percorso urgente"],
  open_questions: [
    {
      question_id: "urgent-path",
      question:
        "Negli acquisti urgenti il buyer puo emettere l'ordine prima dell'approvazione formale?",
      severity: "blocking",
      options: [
        {
          label: "Si, con approvazione retroattiva entro 24 ore",
          implication: "Introduciamo un percorso fast-track controllato.",
        },
        {
          label: "No, l'approvazione deve sempre precedere l'ordine",
          implication: "Il percorso resta unico anche per le urgenze.",
        },
      ],
      answer: null,
    },
  ],
  process_understanding: {
    title: "Purchase-to-Pay",
    actors: [
      { id: "requester", label: "Richiedente", kind: "role" },
      { id: "procurement", label: "Procurement", kind: "team" },
    ],
    unknowns: [
      {
        question: "Definire la governance del percorso urgente",
        severity: "blocking",
      },
    ],
  },
  bpmn_semantic_model: {
    lanes: [
      { id: "requester", name: "Richiedente", flowNodeRefs: ["Start", "Request", "Rework"] },
      { id: "procurement", name: "Ufficio Acquisti", flowNodeRefs: ["Validate", "Complete", "CreatePO", "End"] },
    ],
    flowNodes: [
      { id: "Start", type: "startEvent", name: "Fabbisogno rilevato" },
      { id: "Request", type: "userTask", name: "Compila richiesta" },
      { id: "Validate", type: "userTask", name: "Verifica richiesta" },
      { id: "Complete", type: "exclusiveGateway", name: "Richiesta completa?" },
      { id: "Rework", type: "userTask", name: "Integra informazioni" },
      { id: "CreatePO", type: "userTask", name: "Emetti ordine" },
      { id: "End", type: "endEvent", name: "Ordine emesso" },
    ],
    sequenceFlows: [
      { id: "f1", sourceRef: "Start", targetRef: "Request" },
      { id: "f2", sourceRef: "Request", targetRef: "Validate" },
      { id: "f3", sourceRef: "Validate", targetRef: "Complete" },
      { id: "f4", sourceRef: "Complete", targetRef: "Rework", name: "No" },
      { id: "f5", sourceRef: "Rework", targetRef: "Validate" },
      { id: "f6", sourceRef: "Complete", targetRef: "CreatePO", name: "Si", conditionExpression: "requestComplete = true" },
      { id: "f7", sourceRef: "CreatePO", targetRef: "End" },
    ],
  },
  quality_report: { approval_recommendation: "needs_user_clarification" },
  status: "pending",
  created_at: "2026-09-18T09:00:00Z",
  updated_at: "2026-09-25T15:40:00Z",
};

const provenance = {
  process_id: PROCESS,
  snapshot_id: "pitch-v3",
  snapshot_label: "V3",
  has_plan: true,
  total: 5,
  verified: 4,
  paraphrased: 1,
  label_grounded: 0,
  unverified: 0,
  awaiting_confirmation: 0,
  grounded_ratio: 1,
  sources_checked: 4,
  unused_sources: [],
  elements: [
    ["Request", "Compila richiesta", "Intervista Responsabile Acquisti"],
    ["Validate", "Verifica richiesta", "Intervista Responsabile Acquisti"],
    ["Complete", "Richiesta completa?", "Procedura approvazione ordini"],
    ["Rework", "Integra informazioni", "Intervista Responsabile Acquisti"],
    ["CreatePO", "Emetti ordine", "Export ERP ordini Q2"],
  ].map(([element_id, label, source_name], index) => ({
    kind: index === 2 ? "decision" : "step",
    element_id,
    label,
    status: index === 4 ? "paraphrased" : "verified",
    mark_status: index === 4 ? "paraphrased" : "verified",
    source_ref: `steps:${element_id}`,
    source_id: `source-${Math.min(index + 1, 4)}`,
    source_name,
    quote: `Evidenza operativa per: ${label}`,
    consultant_decision: null,
    removable: true,
  })),
};

const conformance = {
  process_id: PROCESS,
  snapshot_id: "pitch-v3",
  snapshot_label: "V3",
  running: false,
  is_current: true,
  report: {
    verdict: "conformant",
    findings: [],
    sources_audited: 4,
    sources_with_text: 4,
    llm_audit: "done",
    llm_audit_note: "",
    discarded_findings: 0,
    snapshot_id: "pitch-v3",
    canvas_signature: "pitch-canvas",
    audited_at: "2026-09-25T15:45:00+02:00",
  },
};

const tasks = [
  ["Request", "Compila richiesta"],
  ["Validate", "Verifica richiesta"],
  ["Rework", "Integra informazioni"],
  ["CreatePO", "Emetti ordine"],
].map(([element_id, name]) => ({ element_id, name, type: "userTask" }));

const summary = {
  casesCompleted: 500,
  cycle: { avg: 92880, p50: 82800, p90: 133200, p95: 151200 },
  waiting: { avg: 60480, p95: 118800, share: 0.65 },
  processing: { avg: 32400, p95: 46800 },
  cost: { total: 43750, perCase: 87.5 },
  throughputPerHour: 5.4,
  byActivity: tasks.map((task, index) => ({
    el: task.element_id,
    name: task.name,
    count: 500,
    wait: { avg: 3600 + index * 2100, p95: 7200 + index * 3600 },
  })),
  byResource: [
    { id: "requester", name: "Richiedente", utilization: 0.64 },
    { id: "procurement", name: "Ufficio Acquisti", utilization: 0.91 },
  ],
  bottleneck: { el: "CreatePO", name: "Emetti ordine", score: 0.91 },
};

const run = {
  id: RUN,
  bpmn_model_id: MODEL,
  process_id: PROCESS,
  scenario_name: "AS-IS · volume Q4",
  engine: "prosimos",
  status: "completed",
  request: {},
  scenario: {},
  result: {},
  outputs: [],
  summary,
  error: null,
  created_at: "2026-09-25T16:00:00Z",
  completed_at: "2026-09-25T16:00:18Z",
};

const seriesT = [0, 14400, 28800, 43200, 57600, 72000, 86400];
const replay = {
  run_id: RUN,
  schema_version: 1,
  replay: {
    schemaVersion: 1,
    meta: {
      start: "2026-10-01T08:00:00Z",
      durationSec: 86400,
      totalCases: 500,
      sampledCases: 3,
      bucketSec: 14400,
    },
    elements: Object.fromEntries(tasks.map((task) => [task.element_id, { name: task.name }])),
    cases: [
      {
        id: "case-101",
        cycleSec: 18000,
        events: [
          { el: "Request", enable: 0, start: 0, end: 3600, res: "Richiedente" },
          { el: "Validate", enable: 3600, start: 7200, end: 9000, res: "Ufficio Acquisti" },
          { el: "CreatePO", enable: 9000, start: 14400, end: 18000, res: "Ufficio Acquisti" },
        ],
      },
      {
        id: "case-205",
        cycleSec: 23400,
        events: [
          { el: "Request", enable: 0, start: 900, end: 4500, res: "Richiedente" },
          { el: "Validate", enable: 4500, start: 9000, end: 10800, res: "Ufficio Acquisti" },
          { el: "Rework", enable: 10800, start: 12600, end: 14400, res: "Richiedente" },
          { el: "Validate", enable: 14400, start: 17100, end: 18900, res: "Ufficio Acquisti" },
          { el: "CreatePO", enable: 18900, start: 21600, end: 23400, res: "Ufficio Acquisti" },
        ],
      },
      {
        id: "case-388",
        cycleSec: 27000,
        events: [
          { el: "Request", enable: 0, start: 1800, end: 5400, res: "Richiedente" },
          { el: "Validate", enable: 5400, start: 12600, end: 14400, res: "Ufficio Acquisti" },
          { el: "CreatePO", enable: 14400, start: 23400, end: 27000, res: "Ufficio Acquisti" },
        ],
      },
    ],
    series: {
      t: seriesT,
      byElement: Object.fromEntries(
        tasks.map((task, index) => [
          task.element_id,
          {
            active: [1, 3 + index, 5 + index, 7 + index, 6 + index, 4 + index, 2],
            queued: [0, 2 + index, 4 + index * 2, 9 + index * 3, 6 + index, 3, 0],
            done: [0, 18, 74, 164, 288, 421, 500],
          },
        ]),
      ),
      byResource: {
        Richiedente: { busy: [0.12, 0.37, 0.58, 0.73, 0.64, 0.42, 0.2] },
        "Ufficio Acquisti": { busy: [0.28, 0.62, 0.88, 0.94, 0.86, 0.69, 0.34] },
      },
      global: {
        throughputPerHour: [0, 2.1, 4.2, 5.4, 6.1, 5.8, 5.4],
        wip: [3, 18, 37, 51, 44, 27, 8],
        queued: [0, 7, 19, 31, 23, 11, 1],
        costAccrued: [0, 5100, 12800, 22400, 31100, 39100, 43750],
        avgCycleSec: [0, 48600, 64800, 79200, 86400, 90720, 92880],
      },
    },
    flows: {
      f1: { count: 500, attributed: true },
      f2: { count: 500, attributed: true },
      f3: { count: 320, attributed: true },
      f4: { count: 180, attributed: true },
    },
  },
};

const experimentReport = {
  bottleneck_el: "CreatePO",
  bottleneck_name: "Emetti ordine",
  factors: {
    waitingContribution: 0.65,
    cycleContribution: 0.58,
    utilization: 0.91,
    queueGrowth: 0.74,
    casesAffected: 0.62,
    persistence: 0.83,
  },
  experiments: [
    {
      kind: "add_resource",
      pool_id: "res-1",
      pool_name: "Operatore",
      from_amount: 1,
      to_amount: 2,
      rationale:
        "Aumentare la capacità sull'emissione ordine riduce la coda nel punto che assorbe la maggior parte dell'attesa.",
      estimate: { cycle_pct: -0.28, cost_pct: 0.09 },
      target_el: "CreatePO",
    },
  ],
};

type Language = "it" | "en";

const ENGLISH_REPLACEMENTS: Array<[string, string]> = [
  ["Trasformazione ciclo acquisti", "Procurement transformation"],
  ["Ridurre tempi e rilavorazioni del ciclo Purchase-to-Pay, mantenendo tracciabilita e controllo sulle approvazioni.", "Reduce Purchase-to-Pay cycle time and rework while preserving traceability and approval control."],
  ["Validare il modello AS-IS e confrontare lo scenario TO-BE", "Validate the AS-IS model and compare the TO-BE scenario"],
  ["Interviste stakeholder", "Stakeholder interviews"],
  ["Modello AS-IS", "AS-IS model"],
  ["BPMN AS-IS validato", "Validated AS-IS BPMN"],
  ["Scenario TO-BE", "TO-BE scenario"],
  ["Validazione con Operations", "Operations validation"],
  ["Business case operativo", "Operational business case"],
  ["Definire la soglia di approvazione per gli acquisti urgenti", "Define the approval threshold for urgent purchases"],
  ["Onboarding fornitori", "Supplier onboarding"],
  ["Riconciliazione fatture", "Invoice matching"],
  ["Gestione reclami qualita", "Quality claims management"],
  ["Completare le interviste di front-line", "Complete front-line interviews"],
  ["Ottimizzazione Order-to-Cash", "Order-to-Cash optimization"],
  ["Rivedere capacita del team Credit Control", "Review Credit Control team capacity"],
  ["Validazione AS-IS · 29 set", "AS-IS validation · Sep 29"],
  ["Intervista Operations · 02 ott", "Operations interview · Oct 02"],
  ["Intervista Responsabile Acquisti", "Procurement lead interview"],
  ["Intervista Finance & Controlling", "Finance & Controlling interview"],
  ["Dati operativi", "Operational data"],
  ["Intervista", "Interview"],
  ["Procedura approvazione ordini", "Purchase order approval policy"],
  ["Export ERP ordini Q2", "Q2 purchase orders ERP export"],
  ["Approvazione obbligatoria sopra 5.000 EUR", "Mandatory approval above EUR 5,000"],
  ["Percorso fast-track per acquisti urgenti", "Fast-track path for urgent purchases"],
  ["Sintesi di quattro fonti operative.", "Synthesis of four operational sources."],
  ["Il processo parte dal fabbisogno, verifica la completezza della richiesta e termina con l'emissione dell'ordine.", "The process starts from the business need, checks request completeness, and ends with purchase order issuance."],
  ["Negli acquisti urgenti il buyer puo emettere l'ordine prima dell'approvazione formale?", "For urgent purchases, may the buyer issue the order before formal approval?"],
  ["Si, con approvazione retroattiva entro 24 ore", "Yes, with retrospective approval within 24 hours"],
  ["Introduciamo un percorso fast-track controllato.", "Introduce a controlled fast-track path."],
  ["No, l'approvazione deve sempre precedere l'ordine", "No, approval must always precede the order"],
  ["Il percorso resta unico anche per le urgenze.", "Keep one approval path, including urgent purchases."],
  ["SLA del percorso urgente", "Urgent path SLA"],
  ["Definire la governance del percorso urgente", "Define urgent-path governance"],
  ["Fabbisogno rilevato", "Need identified"],
  ["Compila richiesta", "Complete request"],
  ["Verifica richiesta", "Check request"],
  ["Richiesta completa?", "Request complete?"],
  ["Integra informazioni", "Add missing information"],
  ["Emetti ordine", "Issue purchase order"],
  ["Ordine emesso", "Purchase order issued"],
  ["Importo sopra 5.000 EUR?", "Amount above EUR 5,000?"],
  ["Approva richiesta", "Approve request"],
  ["Richiesta autorizzata", "Request authorized"],
  ["Emetti ordine fornitore", "Issue supplier PO"],
  ["Registra ricezione", "Record goods receipt"],
  ["Riconcilia fattura", "Match invoice"],
  ["Pagamento autorizzato", "Payment authorized"],
  ["Ordine di acquisto", "Purchase order"],
  ["Conferma di consegna", "Delivery confirmation"],
  ["Fornitore", "Supplier"],
  ["name=\"Si\"", "name=\"Yes\""],
  ["Responsabile di funzione", "Department manager"],
  ["Richiedente", "Requester"],
  ["Ufficio Acquisti", "Procurement Office"],
  ["Magazzino", "Warehouse"],
  ["Evidenza operativa per:", "Operational evidence for:"],
  ["AS-IS · volume Q4", "AS-IS · Q4 volume"],
  ["Emissione ordine", "Purchase order issuance"],
  ["Analisi Purchase-to-Pay", "Purchase-to-Pay analysis"],
  ["Analizza le interviste e la procedura acquisti. Evidenzia le varianti reali e prepara il processo AS-IS.", "Analyze the interviews and procurement policy. Identify real variants and prepare the AS-IS process."],
  ["Ho ricostruito il flusso end-to-end su 4 fonti. Il modello copre compilazione, verifica, integrazione delle informazioni ed emissione dell'ordine. Ho trovato una sola decisione bloccante: la governance degli acquisti urgenti. Il piano V3 e pronto per la tua review.", "I reconstructed the end-to-end flow from four sources. The model covers request completion, verification, information rework, and purchase order issuance. I found one blocking decision: governance for urgent purchases. Plan V3 is ready for your review."],
];

const WIRE_ENUMS = new Set([
  "Attivo", "Da seguire", "Prospect", "Bozza", "In corso", "A rischio",
  "In pausa", "Completato", "Discovery", "AS-IS", "Validazione", "TO-BE",
  "Simulazione", "Delivery", "Da validare", "Validato", "Confermata", "Da decidere",
]);

function localizeText(value: string, language: Language): string {
  if (language === "it" || WIRE_ENUMS.has(value)) return value;
  return ENGLISH_REPLACEMENTS.reduce(
    (result, [italian, english]) => result.replaceAll(italian, english),
    value,
  );
}

function localize<T>(value: T, language: Language): T {
  if (typeof value === "string") return localizeText(value, language) as T;
  if (Array.isArray(value)) return value.map((item) => localize(item, language)) as T;
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, localize(item, language)]),
    ) as T;
  }
  return value;
}

async function fixture(page: Page, language: Language): Promise<void> {
  await page.addInitScript(() => {
    Object.assign(window, { DELIR_API_BASE: "http://127.0.0.1:8000" });
  });
  await page.addInitScript((lng) => window.localStorage.setItem("delir-language", lng), language);

  const demo = localize(
    { projects, clients, project, sources, decisions, xml, review, provenance, conformance, tasks, run, replay, experimentReport },
    language,
  );
  const demoSources = [...demo.sources];

  await page.route(`${API}/**`, async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();

    if (path === "/v1/workspace/projects" && method === "GET") {
      return route.fulfill({ json: demo.projects, headers: { "X-DeliR-Total": "3" } });
    }
    if (path === "/v1/workspace/clients" && method === "GET") {
      return route.fulfill({ json: demo.clients, headers: { "X-DeliR-Total": "2" } });
    }
    if (path === `/v1/workspace/projects/${PROJECT}` && method === "GET") {
      return route.fulfill({ json: demo.project });
    }
    if (path === `/v1/workspace/projects/${PROJECT}/sources`) {
      return route.fulfill({ json: demoSources });
    }
    if (path === `/v1/workspace/projects/${PROJECT}/sources/upload` && method === "POST") {
      const uploaded = localize(
        {
          id: "source-uploaded",
          project_id: PROJECT,
          process_id: PROCESS,
          name: "Intervista Operations.txt",
          type: "Intervista",
          meta: "Intervista · appena analizzata",
          roles: ["process_evidence"],
          retention: "persistent",
          scopes: [{ type: "process", id: PROCESS }],
          status: "extracted",
          byte_size: 2840,
          content_hash: "hash-source-uploaded",
          mime_type: "text/plain",
        },
        language,
      );
      if (!demoSources.some((source) => source.id === uploaded.id)) demoSources.unshift(uploaded);
      return route.fulfill({ json: uploaded });
    }
    if (path === `/v1/workspace/projects/${PROJECT}/decisions`) {
      return route.fulfill({ json: demo.decisions });
    }
    if (path === `/v1/workspace/bpmn-models/${MODEL}` && method === "GET") {
      return route.fulfill({ json: { id: MODEL, process_id: PROCESS, name: "Purchase-to-Pay AS-IS", xml: demo.xml } });
    }
    if (path === `/v1/workspace/bpmn-models/${MODEL}/versions`) {
      return route.fulfill({ json: [] });
    }
    if (path === `/v1/workspace/bpmn-models/${MODEL}/review` && method === "GET") {
      return route.fulfill({ json: demo.review });
    }
    if (path === `/v1/workspace/bpmn-models/${MODEL}/review/versions`) {
      return route.fulfill({ json: [] });
    }
    if (path === `/v1/workspace/processes/${PROCESS}/provenance`) {
      return route.fulfill({ json: demo.provenance });
    }
    if (path === `/v1/workspace/processes/${PROCESS}/conformance`) {
      return route.fulfill({ json: demo.conformance });
    }
    if (path === `/v1/workspace/bpmn-models/${MODEL}/simulation-template`) {
      return route.fulfill({
        json: {
          tasks: demo.tasks,
          gateways: [
            {
              element_id: "Complete",
              name: localizeText("Richiesta completa?", language),
              type: "exclusiveGateway",
              branches: [
                { flow_id: "f6", flow_name: language === "it" ? "Si" : "Yes", target_name: localizeText("Emetti ordine", language) },
                { flow_id: "f4", flow_name: "No", target_name: localizeText("Integra informazioni", language) },
              ],
            },
          ],
        },
      });
    }
    if (path === `/v1/workspace/bpmn-models/${MODEL}/simulation-provenance`) {
      return route.fulfill({
        json: {
          has_discovery: true,
          process_confidence: "high",
          readiness_score: 8.2,
          missing_information: ["SLA percorso urgente"],
          weak_points: [],
          elements: [
            ...demo.tasks.map((task) => ({
              element_id: task.element_id,
              kind: "activity",
              name: task.name,
              parameter: "duration",
              origin: "interview",
              confidence: "high",
              evidence: ["Interviste operative", "Dati ERP Q2"],
              open_questions: 0,
            })),
            {
              element_id: "Complete",
              kind: "gateway",
              name: localizeText("Richiesta completa?", language),
              parameter: "branching",
              origin: "interview",
              confidence: "high",
              evidence: ["Procedura approvazione ordini"],
              open_questions: 0,
            },
          ],
        },
      });
    }
    if (path === `/v1/workspace/bpmn-models/${MODEL}/simulation-runs`) {
      return route.fulfill({ json: [demo.run] });
    }
    if (path === `/v1/workspace/simulation-runs/${RUN}/replay`) {
      return route.fulfill({ json: demo.replay });
    }
    if (path === `/v1/workspace/simulation-runs/${RUN}/experiments`) {
      return route.fulfill({ json: demo.experimentReport });
    }
    if (path === "/v1/consultant-chat/sessions" && method === "GET") {
      return route.fulfill({
        json: [
          {
            thread_id: "pitch-thread",
            title: localizeText("Analisi Purchase-to-Pay", language),
            scope_type: "process",
            project_id: PROJECT,
            process_id: PROCESS,
            bpmn_model_id: MODEL,
            created_at: "2026-09-25T09:00:00Z",
            updated_at: "2026-09-25T15:30:00Z",
            messages: [],
          },
        ],
      });
    }
    if (path === "/v1/consultant-chat/sessions/pitch-thread") {
      return route.fulfill({
        json: {
          thread_id: "pitch-thread",
          title: localizeText("Analisi Purchase-to-Pay", language),
          model_name: "gpt-5.6-luna",
          messages: [
            {
              id: 1,
              role: "user",
              content: localizeText(
                "Analizza le interviste e la procedura acquisti. Evidenzia le varianti reali e prepara il processo AS-IS.",
                language,
              ),
            },
            {
              id: 2,
              role: "assistant",
              content: localizeText(
                "Ho ricostruito il flusso end-to-end su 4 fonti. Il modello copre compilazione, verifica, integrazione delle informazioni ed emissione dell'ordine. Ho trovato una sola decisione bloccante: la governance degli acquisti urgenti. Il piano V3 e pronto per la tua review.",
                language,
              ),
            },
          ],
        },
      });
    }

    return route.fulfill({ status: 200, json: [] });
  });
}

async function translateWireLabels(page: Page, language: Language): Promise<void> {
  if (language === "it") return;
  await page.evaluate(() => {
    const replacements: Array<[string, string]> = [
      ["Da validare", "To validate"],
      ["In corso", "In progress"],
      ["A rischio", "At risk"],
      ["In pausa", "Paused"],
      ["Completato", "Completed"],
      ["Da seguire", "Follow up"],
      ["Attivo", "Active"],
      ["Confermata", "Confirmed"],
      ["Da decidere", "To decide"],
      ["Validazione", "Validation"],
      ["Simulazione", "Simulation"],
      ["Bozza", "Draft"],
    ];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      let text = node.textContent ?? "";
      for (const [italian, english] of replacements) {
        text = text.replaceAll(italian, english);
      }
      node.textContent = text;
      node = walker.nextNode();
    }
  });
}

async function shot(page: Page, language: Language, name: string): Promise<void> {
  await translateWireLabels(page, language);
  await page.screenshot({ path: resolve(OUT, language, name), fullPage: false });
}

async function coreShot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: resolve(OUT, "core", name), fullPage: false });
}

test.beforeAll(async () => {
  const recordingRun =
    process.env.DELIR_RECORD_PITCH === "1" ||
    process.env.DELIR_RECORD_PITCH_CLIPS === "1";
  const directories = recordingRun
    ? [resolve(OUT, "recording")]
    : [resolve(OUT, "it"), resolve(OUT, "en"), resolve(OUT, "core")];
  await Promise.all(directories.map((directory) => mkdir(directory, { recursive: true })));
});

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
});

for (const language of ["it", "en"] as const) {
test(`generate ${language} pitch-ready end-to-end screenshots`, async ({ page }) => {
  test.setTimeout(120_000);
  await fixture(page, language);

  const labels = language === "it"
    ? {
        project: "Trasformazione ciclo acquisti",
        processChat: "Chat processo",
        assistant: /Ho ricostruito il flusso end-to-end/,
        modelingRegion: "Workspace di modellazione BPMN",
        modelingAction: /^(Decidi|Apri review)$/,
        decisionTab: /Da decidere/,
        urgent: /acquisti urgenti/,
        evidence: /Revisione delle evidenze del disegno/,
        evidencePanel: "Evidenze del disegno",
        canvasChat: "Chat canvas",
        fit: "Centra",
        run: "Avvia simulazione",
        firstTask: "Compila richiesta",
        bottleneck: /Emetti ordine/,
      }
    : {
        project: "Procurement transformation",
        processChat: "Process chat",
        assistant: /I reconstructed the end-to-end flow/,
        modelingRegion: "BPMN modelling workspace",
        modelingAction: /^(Decide|Open review)$/,
        decisionTab: /To decide/,
        urgent: /urgent purchases/,
        evidence: /Review the drawing against the evidence/,
        evidencePanel: "Drawing evidence",
        canvasChat: "Canvas chat",
        fit: "Fit",
        run: "Run simulation",
        firstTask: "Complete request",
        bottleneck: /Issue purchase order/,
      };

  await page.goto("/home");
  await expect(page.getByText(labels.project)).toBeVisible();
  await shot(page, language, "01-workspace-overview.png");

  await page.goto(`/projects/${PROJECT}`);
  await expect(page.getByRole("heading", { name: labels.project })).toBeVisible();
  await shot(page, language, "02-project-control-room.png");

  await page.goto(`/projects/${PROJECT}/processes/${PROCESS}`);
  await expect(page.getByLabel(labels.processChat)).toBeVisible();
  await expect(page.getByText(labels.assistant)).toBeVisible();
  await shot(page, language, "03-ai-process-discovery.png");
  if (language === "it") await coreShot(page, "01-process-discovery.png");

  const modelingBar = page.getByRole("region", { name: labels.modelingRegion });
  await modelingBar.getByRole("button", { name: labels.modelingAction }).click();
  const reviewDialog = page.getByRole("dialog");
  await expect(reviewDialog).toBeVisible();
  await reviewDialog.getByRole("button", { name: labels.decisionTab }).click();
  await expect(reviewDialog.getByText(labels.urgent).first()).toBeVisible();
  await shot(page, language, "04-human-in-the-loop-review.png");
  await page.keyboard.press("Escape");

  await page.goto(`/projects/${PROJECT}/processes/${PROCESS}?view=canvas`);
  await expect(page.locator("[data-element-id='CreatePO']").first()).toBeVisible();
  await page.getByRole("button", { name: labels.evidence }).click();
  await expect(page.getByRole("complementary", { name: labels.evidencePanel })).toContainText("100%");
  await page.getByRole("button", { name: labels.fit, exact: true }).click();
  await shot(page, language, "05-bpmn-evidence-and-conformance.png");
  if (language === "it") await coreShot(page, "02-process-map-and-evidence.png");

  await page.goto(`/projects/${PROJECT}/processes/${PROCESS}?view=canvas`);
  await expect(page.locator("[data-element-id='CreatePO']").first()).toBeVisible();
  await page.getByRole("button", { name: labels.canvasChat, exact: true }).click();
  await expect(page.locator(".process-studio-chat")).toBeVisible();
  await page.getByRole("button", { name: labels.fit, exact: true }).click();
  await shot(page, language, "06-canvas-with-ai-chat.png");

  await page.goto(`/projects/${PROJECT}/processes/${PROCESS}/simulation/heatmap/${RUN}`);
  await expect(page.getByText(labels.bottleneck).first()).toBeVisible();
  await shot(page, language, "07-process-intelligence-heatmap.png");
  if (language === "it") await coreShot(page, "03-process-intelligence.png");

  await page.goto(`/projects/${PROJECT}/processes/${PROCESS}/simulation/replay/${RUN}`);
  const playButton = page.getByRole("button", { name: language === "it" ? "Riproduci" : "Play", exact: true });
  await expect(playButton).toBeVisible();
  await playButton.click();
  await page.waitForTimeout(900);
  await shot(page, language, "08-event-log-replay.png");
  if (language === "it") await coreShot(page, "04-process-mining-event-log-demo.png");

  await page.goto(`/projects/${PROJECT}/processes/${PROCESS}/simulation/scenario`);
  await expect(page.getByRole("button", { name: labels.run, exact: true })).toBeVisible();
  await expect(page.getByText(labels.firstTask).first()).toBeVisible();
  await shot(page, language, "09-scenario-builder.png");

  await page.goto(`/projects/${PROJECT}/processes/${PROCESS}/simulation/dashboard/${RUN}`);
  await expect(page.getByText(labels.bottleneck).first()).toBeVisible();
  await expect(page.getByText(/87[,.]50/)).toBeVisible();
  await shot(page, language, "10-simulation-business-case.png");
  if (language === "it") await coreShot(page, "05-simulation-business-case.png");
});
}

test("record Italian pitch demo", async ({ browser }) => {
  test.skip(process.env.DELIR_RECORD_PITCH !== "1", "Enable with DELIR_RECORD_PITCH=1");
  test.setTimeout(120_000);

  const context = await browser.newContext({
    viewport: { width: 1600, height: 1000 },
    recordVideo: { dir: resolve(OUT, "recording"), size: { width: 1600, height: 1000 } },
  });
  const page = await context.newPage();
  await fixture(page, "it");
  const pause = (ms = 1500) => page.waitForTimeout(ms);

  await page.goto("/home");
  await expect(page.getByText("Trasformazione ciclo acquisti")).toBeVisible();
  await pause(1800);

  await page.goto(`/projects/${PROJECT}`);
  await expect(page.getByRole("heading", { name: "Trasformazione ciclo acquisti" })).toBeVisible();
  await pause(1800);

  await page.goto(`/projects/${PROJECT}/processes/${PROCESS}`);
  await expect(page.getByText(/Ho ricostruito il flusso end-to-end/)).toBeVisible();
  await pause(2200);

  const modelingBar = page.getByRole("region", { name: "Workspace di modellazione BPMN" });
  await modelingBar.getByRole("button", { name: /^(Decidi|Apri review)$/ }).click();
  const reviewDialog = page.getByRole("dialog");
  await expect(reviewDialog).toBeVisible();
  await reviewDialog.getByRole("button", { name: /Da decidere/ }).click();
  await pause(1800);
  await page.keyboard.press("Escape");

  await page.goto(`/projects/${PROJECT}/processes/${PROCESS}?view=canvas`);
  await expect(page.locator("[data-element-id='CreatePO']").first()).toBeVisible();
  await page.getByRole("button", { name: /Revisione delle evidenze del disegno/ }).click();
  await page.getByRole("button", { name: "Centra", exact: true }).click();
  await pause(2600);

  await page.goto(`/projects/${PROJECT}/processes/${PROCESS}/simulation/heatmap/${RUN}`);
  await expect(page.getByText(/Emetti ordine/).first()).toBeVisible();
  await pause(2400);

  await page.goto(`/projects/${PROJECT}/processes/${PROCESS}/simulation/replay/${RUN}`);
  const playButton = page.getByRole("button", { name: "Riproduci", exact: true });
  await expect(playButton).toBeVisible();
  await playButton.click();
  await pause(4500);

  await page.goto(`/projects/${PROJECT}/processes/${PROCESS}/simulation/scenario`);
  await expect(page.getByRole("button", { name: "Avvia simulazione", exact: true })).toBeVisible();
  await pause(2400);

  await page.goto(`/projects/${PROJECT}/processes/${PROCESS}/simulation/dashboard/${RUN}`);
  await expect(page.getByText(/87[,.]50/)).toBeVisible();
  await pause(3500);

  const video = page.video();
  await context.close();
  if (video) await video.saveAs(resolve(OUT, "DeliR-pitch-demo-end-to-end.webm"));
});

async function recordPitchClip(
  browser: Browser,
  filename: string,
  action: (page: Page) => Promise<void>,
): Promise<void> {
  const context = await browser.newContext({
    viewport: { width: 1600, height: 900 },
    recordVideo: { dir: resolve(OUT, "recording"), size: { width: 1600, height: 900 } },
  });
  const page = await context.newPage();
  await fixture(page, "it");
  await action(page);
  const video = page.video();
  await context.close();
  if (video) await video.saveAs(resolve(OUT, filename));
}

async function spaNavigate(page: Page, path: string): Promise<void> {
  await page.evaluate((nextPath) => {
    window.history.pushState({}, "", nextPath);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, path);
}

async function installPitchCursor(page: Page): Promise<void> {
  await page.evaluate(() => {
    if (document.querySelector("#pitch-demo-cursor")) return;
    const style = document.createElement("style");
    style.textContent = `
      #pitch-demo-cursor {
        position: fixed;
        left: 120px;
        top: 110px;
        width: 16px;
        height: 16px;
        border: 3px solid white;
        border-radius: 999px;
        background: #2563eb;
        box-shadow: 0 2px 10px rgba(15, 23, 42, .35), 0 0 0 2px rgba(37, 99, 235, .28);
        pointer-events: none;
        transform: translate(-50%, -50%);
        transition: left 460ms cubic-bezier(.22, 1, .36, 1), top 460ms cubic-bezier(.22, 1, .36, 1), transform 160ms ease, box-shadow 160ms ease;
        z-index: 2147483647;
      }
      #pitch-demo-cursor.is-clicking {
        transform: translate(-50%, -50%) scale(.72);
        box-shadow: 0 2px 10px rgba(15, 23, 42, .3), 0 0 0 10px rgba(37, 99, 235, .16);
      }
    `;
    const cursor = document.createElement("div");
    cursor.id = "pitch-demo-cursor";
    document.head.appendChild(style);
    document.body.appendChild(cursor);
  });
}

async function movePitchCursor(page: Page, target: Locator, travelMs = 520): Promise<void> {
  const box = await target.boundingBox();
  if (!box) return;
  await page.evaluate(
    ({ x, y, duration }) => {
      const cursor = document.querySelector<HTMLElement>("#pitch-demo-cursor");
      if (!cursor) return;
      cursor.style.transitionDuration = `${duration}ms, ${duration}ms, 160ms, 160ms`;
      cursor.style.left = `${x}px`;
      cursor.style.top = `${y}px`;
    },
    { x: box.x + box.width / 2, y: box.y + box.height / 2, duration: travelMs },
  );
  await page.waitForTimeout(travelMs + 80);
}

async function clickWithPitchCursor(page: Page, target: Locator, travelMs = 520): Promise<void> {
  await movePitchCursor(page, target, travelMs);
  await page.evaluate(() => document.querySelector("#pitch-demo-cursor")?.classList.add("is-clicking"));
  await page.waitForTimeout(120);
  await target.click();
  await page.evaluate(() => document.querySelector("#pitch-demo-cursor")?.classList.remove("is-clicking"));
  await page.waitForTimeout(260);
}

test("record pitch clip A discovery to verified map", async ({ browser }) => {
  test.skip(process.env.DELIR_RECORD_PITCH_CLIPS !== "1", "Enable with DELIR_RECORD_PITCH_CLIPS=1");
  test.setTimeout(120_000);
  await recordPitchClip(browser, "Clip-A-discovery-to-map.webm", async (page) => {
    await page.goto(`/projects/${PROJECT}`);
    await expect(page.getByRole("heading", { name: "Trasformazione ciclo acquisti" })).toBeVisible();
    await installPitchCursor(page);
    const sourcesTab = page.getByRole("tab", { name: /Fonti/ });
    await clickWithPitchCursor(page, sourcesTab, 650);
    const addSource = page.getByRole("button", { name: /Aggiungi fonte/ });
    await expect(addSource).toBeVisible();
    await page.waitForTimeout(900);

    await clickWithPitchCursor(page, addSource, 700);
    const dialog = page.getByRole("dialog", { name: "Aggiungi una fonte" });
    await expect(dialog).toBeVisible();
    const fileInput = dialog.getByLabel("File da analizzare");
    await movePitchCursor(page, fileInput, 520);
    await fileInput.setInputFiles({
      name: "Intervista Operations.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("Intervista sintetica per la demo DeliR."),
    });
    const processKnowledge = dialog.getByLabel("Descrive come si lavora");
    await clickWithPitchCursor(page, processKnowledge, 500);
    await dialog.getByLabel("Ambito").selectOption(`process:${PROCESS}`);
    await page.waitForTimeout(650);
    await clickWithPitchCursor(page, dialog.getByRole("button", { name: "Carica e analizza" }), 650);
    await expect(dialog).toBeHidden();
    const uploadedSource = page.getByText("Intervista Operations.txt");
    await expect(uploadedSource).toBeVisible();
    await movePitchCursor(page, uploadedSource, 700);
    await page.waitForTimeout(900);

    await spaNavigate(page, `/projects/${PROJECT}/processes/${PROCESS}?view=canvas`);
    await expect(page.locator("[data-element-id='CreatePO']").first()).toBeVisible();
    const evidenceButton = page.getByRole("button", { name: /Revisione delle evidenze del disegno/ });
    await clickWithPitchCursor(page, evidenceButton, 800);
    const centerButton = page.getByRole("button", { name: "Centra", exact: true });
    await clickWithPitchCursor(page, centerButton, 700);
    await expect(page.getByRole("complementary", { name: "Evidenze del disegno" })).toContainText("100%");
    await movePitchCursor(page, page.locator("[data-element-id='CreatePO']").first(), 900);
    await page.waitForTimeout(850);
    const citedSources = page.getByText(/Citati dalle fonti \(4\)/);
    await clickWithPitchCursor(page, citedSources, 650);
    await page.waitForTimeout(5000);
  });
});

test("record pitch clip B simulation dashboard", async ({ browser }) => {
  test.skip(process.env.DELIR_RECORD_PITCH_CLIPS !== "1", "Enable with DELIR_RECORD_PITCH_CLIPS=1");
  test.setTimeout(120_000);
  await recordPitchClip(browser, "Clip-B-simulation-dashboard.webm", async (page) => {
    await page.goto(`/projects/${PROJECT}/processes/${PROCESS}/simulation/replay/${RUN}`);
    const playButton = page.getByRole("button", { name: "Riproduci", exact: true });
    await expect(playButton).toBeVisible();
    await installPitchCursor(page);
    const speed = page.getByRole("combobox", { name: "Velocità" });
    await clickWithPitchCursor(page, speed, 600);
    await page.getByRole("option", { name: /12 s/ }).click();
    await page.waitForTimeout(400);
    await clickWithPitchCursor(page, playButton, 650);
    await page.waitForTimeout(5800);

    await spaNavigate(page, `/projects/${PROJECT}/processes/${PROCESS}/simulation/dashboard/${RUN}`);
    await expect(page.getByText(/87[,.]50/)).toBeVisible();
    await movePitchCursor(page, page.getByText(/87[,.]50/).first(), 750);
    await page.waitForTimeout(4300);
  });
});

test("record pitch clip C bottleneck to recommendation", async ({ browser }) => {
  test.skip(process.env.DELIR_RECORD_PITCH_CLIPS !== "1", "Enable with DELIR_RECORD_PITCH_CLIPS=1");
  test.setTimeout(120_000);
  await recordPitchClip(browser, "Clip-C-bottleneck-to-recommendation.webm", async (page) => {
    await page.goto(`/projects/${PROJECT}/processes/${PROCESS}/simulation/heatmap/${RUN}`);
    await expect(page.getByText("Emetti ordine", { exact: true }).first()).toBeVisible();
    await page.waitForTimeout(4500);

    await spaNavigate(page, `/projects/${PROJECT}/processes/${PROCESS}/simulation/insights/${RUN}`);
    await expect(page.getByRole("heading", { name: "Cosa provare" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Crea scenario" })).toBeVisible();
    await page.waitForTimeout(5500);
  });
});
