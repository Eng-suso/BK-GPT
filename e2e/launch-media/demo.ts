/**
 * Il caso della demo di lancio, costruito dai file veri del repo.
 *
 * - Interviste, claim ed evidenze: golden set `tests/golden/esaote_ciclo_passivo`
 *   (citazioni alla lettera, nessuna riscritta).
 * - BPMN: `data/as-is.bpmn`, l'As-Is v3: le attivita' del compilatore del
 *   prodotto (`data/as-is.compiled.bpmn`), corrette secondo le regole di stile
 *   BPMN da `scripts/launch_media_asis.py`.
 * - Simulazioni: `data/runs.json` e `data/api.json`, scritti da
 *   `scripts/launch_media_simulate.py` con Prosimos e le funzioni del backend.
 *
 * A schermo il cliente e' Vetrano Industriale S.p.A. (fittizio): il nome del
 * caso nel golden set non deve comparire negli asset pubblici.
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const ROOT = resolve(__dirname, "..", "..");
const GOLDEN = resolve(ROOT, "tests", "golden", "esaote_ciclo_passivo");
const DATA = resolve(__dirname, "data");

const readJson = <T>(path: string): T => JSON.parse(readFileSync(path, "utf-8")) as T;

export const IDS = {
  client: "vetrano-industriale",
  project: "vetrano-acquisti-indiretti",
  process: "acquisti-indiretti",
  model: "acquisti-indiretti-bpmn",
  asIsRun: 301,
  toBeRun: 302,
  thread: "thread-acquisti-indiretti",
} as const;

export const CLIENT_NAME = "Vetrano Industriale S.p.A.";
export const PROJECT_NAME = "Acquisti indiretti e servizi";
export const PROCESS_NAME = "Gestione acquisto materiali indiretti e servizi";
export const PROCESS_OWNER = "Laura Conti";

type Expected = {
  expected_claims: { id: string; text: string; evidence: { source: string; quote: string }[] }[];
  expected_evidence_bindings: { element: string; source: string; quote: string }[];
  open_gaps: { question: string }[];
};
const expected = readJson<Expected>(resolve(GOLDEN, "expected.json"));
const idealPlan = readJson<Record<string, unknown>>(resolve(GOLDEN, "ideal_plan.json"));

type Interview = { file: string; id: string; person: string; role: string; date: string };
const INTERVIEWS: Interview[] = [
  { file: "a1_laura_conti_ufficio_tecnico.md", id: "src-laura-conti", person: "Laura Conti", role: "Responsabile Ufficio Tecnico", date: "2026-09-02" },
  { file: "a2_paolo_marchetti_manutenzione.md", id: "src-paolo-marchetti", person: "Paolo Marchetti", role: "Capo Manutenzione", date: "2026-09-03" },
  { file: "a3_francesca_neri_acquisti.md", id: "src-francesca-neri", person: "Francesca Neri", role: "Ufficio Acquisti", date: "2026-09-04" },
];
const interviewByFile = new Map(INTERVIEWS.map((item) => [item.file, item]));
const interviewText = (file: string) => readFileSync(resolve(GOLDEN, "sources", file), "utf-8");
const sourceName = (item: Interview) => `Intervista ${item.person} · ${item.role}`;

// Gli elementi dei percorsi alternativi il compilatore li prefissa col percorso.
const COMPILED_ID: Record<string, string> = {
  richiedi_integrazione: "percorso_integrazione_richiedi_integrazione",
  richiedi_autorizzazione: "percorso_autorizzazione_richiedi_autorizzazione",
  autorizza_spesa: "percorso_autorizzazione_autorizza_spesa",
  chiama_fornitore_diretto: "percorso_urgente_chiama_fornitore_diretto",
  invia_riferimento_ordine_urgente: "percorso_urgente_invia_riferimento_ordine_urgente",
  regolarizza_ordine: "percorso_urgente_regolarizza_ordine",
  gestione_contabile_fattura: "percorso_urgente_gestione_contabile_fattura",
  richiesta_lavorabile: "gw_richiesta_completa",
  serve_autorizzazione: "gw_serve_autorizzazione",
  urgenza_linea_ferma: "urgenza",
};

export const bpmnXml = readFileSync(resolve(DATA, "as-is.bpmn"), "utf-8");
const labels = new Map(
  [...bpmnXml.matchAll(/<bpmn:(?:userTask|task|exclusiveGateway) id="([^"]+)" name="([^"]+)"/g)].map((m) => [m[1], m[2]]),
);

type Run = {
  name: string;
  model: unknown;
  scenario: Record<string, unknown>;
  result: Record<string, unknown>;
  summary: Record<string, unknown>;
  replay: Record<string, unknown>;
  request: Record<string, unknown>;
  experiments: unknown;
};
export const runs = readJson<{ as_is: Run; to_be: Run }>(resolve(DATA, "runs.json"));
export const api = readJson<Record<string, unknown>>(resolve(DATA, "api.json"));

const archive = { archived_at: null, archive_reason: null };

export const processItem = {
  id: IDS.process,
  project_id: IDS.project,
  bpmn_model_id: IDS.model,
  name: PROCESS_NAME,
  stage: "AS-IS",
  status: "Validato",
  owner: PROCESS_OWNER,
  readiness: 86,
  ...archive,
};

export const project = {
  id: IDS.project,
  client_id: IDS.client,
  client: CLIENT_NAME,
  name: PROJECT_NAME,
  objective:
    "Ricostruire come funziona davvero l'acquisto di materiali indiretti e servizi, validarlo con chi ci lavora e simulare il miglioramento prima di cambiarlo.",
  lead: "Marco Bellini",
  start_date: "2026-09-01",
  end_date: "2026-10-30",
  phase: "Simulazione",
  status: "In corso",
  progress: 64,
  processes: 1,
  next_step: "Validazione del To-Be con Laura Conti",
  milestones: [
    { title: "Interviste stakeholder", status: "done", completed_at: "2026-09-04" },
    { title: "As-Is validato", status: "done", completed_at: "2026-09-18" },
    { title: "Simulazione As-Is e To-Be", status: "done", completed_at: "2026-10-02" },
    { title: "Validazione del process owner", status: "planned", completed_at: null },
  ],
  open_issues: ["Soglia di autorizzazione non dichiarata da nessuna fonte"],
  deliverables: ["As-Is validato", "Scenario To-Be simulato", "Confronto KPI"],
  ...archive,
  process_items: [processItem],
};

// Gli altri incarichi del consulente: servono alla scena della memoria.
const portfolio = [
  { id: "brenta-packaging", name: "Brenta Packaging S.r.l.", sector: "Imballaggi", project: "Onboarding fornitori", phase: "Discovery", status: "In corso", progress: 28 },
  { id: "orsini-logistica", name: "Orsini Servizi Logistici S.p.A.", sector: "Logistica", project: "Gestione resi e reclami", phase: "AS-IS", status: "In corso", progress: 46 },
];

export const projects = [
  project,
  ...portfolio.map((item, index) => ({
    id: `${item.id}-progetto`,
    client_id: item.id,
    client: item.name,
    name: item.project,
    objective: "",
    lead: "Marco Bellini",
    start_date: "2026-09-15",
    end_date: null,
    phase: item.phase,
    status: item.status,
    progress: item.progress,
    processes: 1 + index,
    next_step: index === 0 ? "Interviste con il team qualita'" : "Validazione AS-IS con il magazzino",
    milestones: [],
    open_issues: [],
    deliverables: [],
    ...archive,
    process_items: [],
  })),
];

export const clients = [
  {
    id: IDS.client,
    name: CLIENT_NAME,
    sector: "Manifattura",
    status: "Attivo",
    projects: 1,
    next_activity: "Validazione To-Be · 14 ott",
    owner: "Marco Bellini",
    contact: PROCESS_OWNER,
    processes: [PROCESS_NAME],
    documents: INTERVIEWS.map(sourceName),
    ...archive,
  },
  ...portfolio.map((item) => ({
    id: item.id,
    name: item.name,
    sector: item.sector,
    status: "Attivo",
    projects: 1,
    next_activity: item.phase === "Discovery" ? "Intervista qualita' · 16 ott" : "Workshop AS-IS · 21 ott",
    owner: "Marco Bellini",
    contact: "",
    processes: [],
    documents: [],
    ...archive,
  })),
];

export const sources = INTERVIEWS.map((item) => ({
  id: item.id,
  project_id: IDS.project,
  client_id: IDS.client,
  process_id: IDS.process,
  name: sourceName(item),
  type: "Intervista",
  meta: `Intervista · ${item.date.split("-").reverse().join("/")}`,
  roles: ["process_evidence"],
  retention: "persistent",
  scopes: [{ type: "process", id: IDS.process }],
  status: "ready",
  byte_size: Buffer.byteLength(interviewText(item.file)),
  content_hash: `sha-${item.id}`,
  mime_type: "text/markdown",
  acquisition_status: "done",
  acquisition_error: null,
  claims_status: "done",
  claims_error: null,
  reconcile_status: "done",
}));

export function sourceDocument(sourceId: string) {
  const item = INTERVIEWS.find((entry) => entry.id === sourceId);
  if (!item) return null;
  return {
    id: item.id,
    project_id: IDS.project,
    process_id: IDS.process,
    name: sourceName(item),
    type: "Intervista",
    summary: `Intervista a ${item.person} (${item.role}) sul processo di acquisto dei materiali indiretti.`,
    participants: [item.person, "Marco Bellini"],
    occurred_at: item.date,
    episode_id: null,
    content: interviewText(item.file),
    has_content: true,
  };
}

/** Il paragrafo dell'intervista che contiene la citazione: e' l'ancora mostrata. */
function anchorOf(file: string, quote: string): string {
  const paragraphs = interviewText(file).split(/\n\s*\n/);
  const index = paragraphs.findIndex((paragraph) => paragraph.includes(quote.slice(0, 40)));
  return index >= 0 ? `§${index + 1}` : "§1";
}

type Claim = { id: number; file: string; statement: string; quote: string };
const claims: Claim[] = [];
let nextClaimId = 1;
function claim(file: string, statement: string, quote: string): Claim {
  if (!interviewText(file).includes(quote)) throw new Error(`citazione non trovata in ${file}: ${quote}`);
  const existing = claims.find((item) => item.file === file && item.quote === quote);
  if (existing) return existing;
  const created = { id: nextClaimId++, file, statement, quote };
  claims.push(created);
  return created;
}

for (const expectedClaim of expected.expected_claims) {
  for (const evidence of expectedClaim.evidence) claim(evidence.source, expectedClaim.text, evidence.quote);
}
for (const binding of expected.expected_evidence_bindings) {
  const elementId = COMPILED_ID[binding.element] ?? binding.element;
  const label = labels.get(elementId) ?? binding.element;
  const what = elementId.startsWith("gw_") || elementId === "urgenza" ? "la decisione" : "il passo";
  claim(binding.source, `Descrive ${what} «${label}»`, binding.quote);
}

const LAURA = "a1_laura_conti_ufficio_tecnico.md";
const PAOLO = "a2_paolo_marchetti_manutenzione.md";
const FRANCESCA = "a3_francesca_neri_acquisti.md";

// Il passaggio nascosto: due fonti non sanno chi regolarizza l'urgenza, la terza si'.
const lauraUnknown = claim(LAURA, "Chi regolarizza un acquisto urgente: non lo sa", "So che poi la parte di carta viene messa a posto dopo, ma non so da chi.");
const paoloUnknown = claim(PAOLO, "Chi regolarizza un acquisto urgente: non lo sa", "Se mi chiedi chi materialmente lo fa, non lo so, e non voglio dirti un nome a caso.");
const francescaKnows = claim(FRANCESCA, "La regolarizzazione dell'ordine urgente la fa Acquisti", "La parte di ordine si', la faccio io.");
const francescaUnsaid = claim(FRANCESCA, "Chi chiede l'urgenza non sa chi la regolarizza", "Non credo, e onestamente non e' mai stato detto.");
const lauraThreshold = claim(LAURA, "Soglia di autorizzazione: non la conosce", "So che sopra una certa cifra serve un passaggio in piu', ma quale sia la cifra e chi firmi non te lo so dire.");
const francescaThreshold = claim(FRANCESCA, "Soglia di autorizzazione: non la dice a memoria", "Preferisco non dartela a memoria perche' e' una cosa che e' cambiata e non voglio dirti un numero sbagliato.");

export function claimsOf(sourceId: string) {
  const item = INTERVIEWS.find((entry) => entry.id === sourceId);
  if (!item) return [];
  return claims
    .filter((entry) => entry.file === item.file)
    .map((entry) => ({
      id: entry.id,
      source_id: sourceId,
      statement: entry.statement,
      segment_ordinal: Number(anchorOf(entry.file, entry.quote).slice(1)),
      anchor_ref: anchorOf(entry.file, entry.quote),
      quote: entry.quote,
      quote_verified: true,
      extracted_at: "2026-09-05T09:12:00Z",
    }));
}

const side = (entry: Claim) => {
  const item = interviewByFile.get(entry.file)!;
  return {
    claim_id: entry.id,
    source_id: item.id,
    source_name: sourceName(item),
    statement: entry.statement,
    anchor_ref: anchorOf(entry.file, entry.quote),
    quote: entry.quote,
    quote_verified: true,
  };
};

type Relation = {
  id: number;
  kind: "corroboration" | "divergence";
  divergence_type: string | null;
  explanation: string;
  a: Claim;
  b: Claim;
};
const canale = claims.filter((entry) => entry.statement.startsWith("Gli Acquisti accettano"));
const codice = claims.filter((entry) => entry.statement.startsWith("I materiali indiretti"));
const relations: Relation[] = [
  {
    id: 1,
    kind: "divergence",
    divergence_type: "knowledge_gap",
    explanation:
      "Laura non sa chi regolarizza un acquisto urgente; Francesca dice che la parte d'ordine la fa lei. Non e' un conflitto: e' un passaggio che una fonte conosce e l'altra no.",
    a: lauraUnknown,
    b: francescaKnows,
  },
  {
    id: 2,
    kind: "divergence",
    divergence_type: "knowledge_gap",
    explanation:
      "Paolo ordina d'urgenza ma non sa chi sistema la pratica; Francesca la ricostruisce a posteriori e conferma che a Paolo non e' mai stato detto.",
    a: paoloUnknown,
    b: francescaUnsaid,
  },
  {
    id: 3,
    kind: "divergence",
    divergence_type: "knowledge_gap",
    explanation: "Nessuna delle due fonti dichiara la soglia di autorizzazione: resta una domanda aperta, non un numero da stimare.",
    a: lauraThreshold,
    b: francescaThreshold,
  },
  { id: 4, kind: "corroboration", divergence_type: null, explanation: "Paolo e Francesca descrivono lo stesso canale unico verso Acquisti.", a: canale[1] ?? canale[0], b: canale[0] },
  { id: 5, kind: "corroboration", divergence_type: null, explanation: "Laura e Francesca confermano che gli indiretti non hanno un codice interno.", a: codice[0], b: codice[1] ?? codice[0] },
];

export function relationsOf(sourceId: string) {
  const item = INTERVIEWS.find((entry) => entry.id === sourceId);
  if (!item) return [];
  return relations.flatMap((relation) => {
    const mine = [relation.a, relation.b].find((entry) => entry.file === item.file);
    if (!mine) return [];
    const other = mine === relation.a ? relation.b : relation.a;
    return [{
      id: relation.id,
      kind: relation.kind,
      divergence_type: relation.divergence_type,
      divergence_label: null,
      declared_type: relation.divergence_type,
      reasons: [],
      explanation: relation.explanation,
      claim: side(mine),
      other: side(other),
    }];
  });
}

export const claimCount = claims.length;

/** Le evidenze del disegno: ogni elemento con la sua citazione, dal golden set. */
export const provenance = (() => {
  const seen = new Set<string>();
  const elements = expected.expected_evidence_bindings.flatMap((binding) => {
    const elementId = COMPILED_ID[binding.element] ?? binding.element;
    if (seen.has(elementId)) return [];
    seen.add(elementId);
    const item = interviewByFile.get(binding.source)!;
    const label = labels.get(elementId) ?? binding.element;
    return [{
      kind: elementId.startsWith("gw_") || elementId === "urgenza" ? "decision" : "step",
      element_id: elementId,
      label,
      status: "verified",
      mark_status: "verified",
      source_ref: `steps:${binding.element}`,
      source_id: item.id,
      source_name: sourceName(item),
      quote: binding.quote,
      consultant_decision: null,
      removable: false,
    }];
  });
  return {
    process_id: IDS.process,
    snapshot_id: "as-is-v3",
    snapshot_label: "V3",
    has_plan: true,
    total: elements.length,
    verified: elements.length,
    paraphrased: 0,
    label_grounded: 0,
    unverified: 0,
    awaiting_confirmation: 0,
    grounded_ratio: 1,
    sources_checked: INTERVIEWS.length,
    unused_sources: [],
    elements,
  };
})();

export const conformance = {
  process_id: IDS.process,
  snapshot_id: "as-is-v3",
  snapshot_label: "V3",
  running: false,
  is_current: true,
  report: {
    verdict: "conformant",
    findings: [],
    sources_audited: INTERVIEWS.length,
    sources_with_text: INTERVIEWS.length,
    llm_audit: "done",
    llm_audit_note: "",
    discarded_findings: 0,
    snapshot_id: "as-is-v3",
    canvas_signature: "as-is-v3",
    audited_at: "2026-09-18T15:40:00+02:00",
  },
};

/** Corsie, nodi e flussi dell'As-Is v3, nella forma che la review mostra. */
const semanticModel = (() => {
  const lanes = [...bpmnXml.matchAll(/<bpmn:lane id="([^"]+)" name="([^"]+)">([\s\S]*?)<\/bpmn:lane>/g)].map((m) => ({
    id: m[1],
    name: m[2],
    flowNodeRefs: [...m[3].matchAll(/<bpmn:flowNodeRef>([^<]+)<\/bpmn:flowNodeRef>/g)].map((r) => r[1]),
  }));
  const flowNodes = [...bpmnXml.matchAll(/<bpmn:(startEvent|endEvent|userTask|exclusiveGateway) id="([^"]+)"(?: name="([^"]*)")?/g)].map(
    (m) => ({ id: m[2], type: m[1], name: m[3] ?? "" }),
  );
  const sequenceFlows = [...bpmnXml.matchAll(/<bpmn:sequenceFlow id="([^"]+)"(?: name="([^"]*)")? sourceRef="([^"]+)" targetRef="([^"]+)"/g)].map(
    (m) => ({ id: m[1], sourceRef: m[3], targetRef: m[4], ...(m[2] ? { name: m[2] } : {}) }),
  );
  return { lanes, flowNodes, sequenceFlows };
})();

export const review = {
  bpmn_model_id: IDS.model,
  process_id: IDS.process,
  version: 3,
  source_text: "Sintesi di tre interviste: Ufficio Tecnico, Manutenzione, Acquisti.",
  bpmn_brief:
    "## Acquisto materiali indiretti e servizi\n\nIl fabbisogno nasce in reparto, passa dall'Ufficio Tecnico che ricostruisce la richiesta e arriva ad Acquisti. Le urgenze saltano il giro e vengono regolarizzate dopo.",
  readiness_score: 8.6,
  missing_information: [expected.open_gaps[0].question],
  open_questions: [
    {
      question_id: "soglia-autorizzazione",
      question: expected.open_gaps[0].question,
      severity: "blocking",
      options: [
        { label: "Chiedo la procedura scritta a Francesca", implication: "La soglia entra nel modello solo quando una fonte la dichiara." },
        { label: "La lascio aperta nell'As-Is", implication: "Il ramo di autorizzazione resta, senza un importo inventato." },
      ],
      answer: null,
    },
  ],
  process_understanding: idealPlan,
  bpmn_semantic_model: semanticModel,
  quality_report: { approval_recommendation: "needs_user_clarification" },
  status: "pending",
  created_at: "2026-09-05T09:00:00Z",
  updated_at: "2026-09-18T15:30:00Z",
};

export const versions = [
  { id: 3, bpmn_model_id: IDS.model, process_id: IDS.process, change_summary: "As-Is v3 · validato con Laura Conti", source: "consultant", created_at: "2026-09-18T15:42:00Z" },
  { id: 2, bpmn_model_id: IDS.model, process_id: IDS.process, change_summary: "Percorso urgente collegato alla regolarizzazione", source: "consultant", created_at: "2026-09-12T11:05:00Z" },
  { id: 1, bpmn_model_id: IDS.model, process_id: IDS.process, change_summary: "Prima bozza dalle tre interviste", source: "agent", created_at: "2026-09-05T09:20:00Z" },
];

function runRecord(id: number, run: Run, createdAt: string) {
  return {
    id,
    bpmn_model_id: IDS.model,
    process_id: IDS.process,
    scenario_name: run.name,
    engine: "prosimos",
    status: "completed",
    idempotency_key: `launch-${id}`,
    request: run.request,
    scenario: run.scenario,
    result: run.result,
    outputs: [],
    summary: run.summary,
    error: null,
    created_at: createdAt,
    completed_at: createdAt,
  };
}

export const simulationRuns = [
  runRecord(IDS.toBeRun, runs.to_be, "2026-10-02T10:14:00Z"),
  runRecord(IDS.asIsRun, runs.as_is, "2026-10-02T09:48:00Z"),
];

export function runById(id: number) {
  return simulationRuns.find((run) => run.id === id) ?? null;
}

export function runData(id: number): Run | null {
  if (id === IDS.asIsRun) return runs.as_is;
  if (id === IDS.toBeRun) return runs.to_be;
  return null;
}

export const chatSession = {
  thread_id: IDS.thread,
  title: "Discovery acquisti indiretti",
  scope_type: "process",
  project_id: IDS.project,
  process_id: IDS.process,
  bpmn_model_id: IDS.model,
  created_at: "2026-09-05T09:00:00Z",
  updated_at: "2026-09-18T15:30:00Z",
  messages: [],
};

export const chatMessages = [
  {
    id: 1,
    role: "user",
    content: "Ho caricato le interviste a Laura, Paolo e Francesca. Ricostruisci l'As-Is senza inventare quello che nessuno dice.",
  },
  {
    id: 2,
    role: "assistant",
    content:
      `Ho letto le tre interviste ed estratto ${claims.length} affermazioni, ognuna con la sua citazione. ` +
      "Il processo passa da sei funzioni. Nessuna persona lo conosce per intero: chi regolarizza un acquisto urgente non lo sanno ne' Laura ne' Paolo, lo dice Francesca. " +
      "Una cosa resta aperta: nessuna fonte dichiara la soglia di autorizzazione, quindi non la metto nel modello e te la chiedo.",
  },
];

/**
 * Il layout della tela di simulazione per il video: processo grande, tre KPI
 * a destra. E' il JSON che "Modifica canvas → Salva layout" scrive su questo
 * dispositivo (`layoutSchema` in dashboardModel.ts).
 */
export const simulationLayoutKey = `delir:simulation:dashboard:${IDS.project}:${IDS.process}`;
const widget = (id: string, kind: string, metric: string, title: string, color: string, canvas: Record<string, number>) => ({
  id, title, kind, metric, width: "half", text: "**${metric}**", metricExpression: "", target: 100,
  followFilter: false, activityId: "", showLabels: true, color, canvas,
});
// Proporzioni dello schermo (16:9 meno la barra di riproduzione): processo con
// coda e tempo medio a destra, sotto quattro grafici in riga. Sei andamenti che si
// muovono mentre i casi attraversano il processo.
const ROW_Y = 624;
const ROW_W = (1924 - 3 * 24) / 4;
const rowRect = (index: number) => ({ x: index * (ROW_W + 24), y: ROW_Y, width: ROW_W, height: 260 });
export const simulationLayout = {
  version: 1,
  process: { canvas: { x: 0, y: 0, width: 1500, height: 600 }, groupId: "video", beforeId: "__first__", width: "full", height: 600 },
  groups: [{
    id: "video",
    title: "",
    widgets: [
      widget("video-queued", "area", "queued", "Richieste in coda", "amber", { x: 1524, y: 0, width: 400, height: 294 }),
      widget("video-cycle", "line", "cycle", "Tempo medio di attraversamento", "violet", { x: 1524, y: 306, width: 400, height: 294 }),
      widget("video-completed", "line", "completed", "Richieste concluse", "teal", rowRect(0)),
      widget("video-throughput", "line", "throughput", "Throughput", "blue", rowRect(1)),
      widget("video-cost", "area", "cost", "Costo accumulato", "violet", rowRect(2)),
      widget("video-busy", "column", "resourceBusy", "Occupazione delle risorse", "amber", rowRect(3)),
    ],
  }],
};

/** "Ipotesi To-Be": le due modifiche che il To-Be simula, con chi le ha chieste. */
// La revisione di base e' l'impronta sha256 del disegno, come la calcola il backend.
const BASE_REVISION = createHash("sha256").update(bpmnXml).digest("hex");
export const impactReview = {
  process_id: IDS.process,
  base_revision: BASE_REVISION,
  xml: bpmnXml,
  plan: {
    title: PROCESS_NAME,
    actors: (idealPlan.actors as { id: string; label: string }[]).map(({ id, label }) => ({ id, label })),
    steps: (idealPlan.steps as { id: string; label: string; actor_ids: string[] }[]).map((step) => ({
      id: step.id, label: step.label, description: null, actor_ids: step.actor_ids, inputs: [], outputs: [],
    })),
    data_objects: [],
    controls: [],
    structured_business_rules: [],
    consultant_findings: [],
  },
  actions: [
    {
      id: "tobe-richiesta-completa",
      node_id: "ricostruisci_richiesta",
      node_name: labels.get("ricostruisci_richiesta") ?? "Ricostruisci richiesta",
      base_revision: BASE_REVISION,
      kind: "candidate",
      title: "La richiesta nasce completa, con i campi obbligatori",
      detail:
        "Laura: «Un posto unico dove la richiesta arriva scritta come si deve, con dentro tutto quello che serve.» " +
        "Francesca: «Farei in modo che la richiesta nasca gia' completa, con i campi obbligatori.» " +
        "Ipotesi simulata: i rimbalzi scendono dal 55% al 25% (stima del consulente).",
      created_at: "2026-10-01T10:00:00Z",
      created_by: "Marco Bellini",
      proposal_xml: null,
    },
    {
      id: "tobe-autorizzazione-visibile",
      node_id: "percorso_autorizzazione_autorizza_spesa",
      node_name: labels.get("percorso_autorizzazione_autorizza_spesa") ?? "Autorizza spesa",
      base_revision: BASE_REVISION,
      kind: "candidate",
      title: "Autorizzazione visibile, con una delega quando il responsabile e' fuori",
      detail:
        "Francesca: «…vorrei che l'autorizzazione fosse una cosa che si vede, non una mail che aspetto.» " +
        "Oggi «non c'e' un sostituto formale». Ipotesi simulata: una finestra di autorizzazione ogni giorno.",
      created_at: "2026-10-01T10:05:00Z",
      created_by: "Marco Bellini",
      proposal_xml: null,
    },
  ],
};

/**
 * Review mode su "Autorizza spesa": la domanda del consulente e la risposta di
 * DeliR. Le citazioni sono di Francesca, alla lettera; l'attesa e' quella della
 * simulazione As-Is (heatmap); la soglia resta una domanda aperta.
 */
export const REVIEW_NODE = "percorso_autorizzazione_autorizza_spesa";
export const reviewQuestion = "Come miglioreresti questa attività? Basati solo sulle fonti.";
export const reviewAnswer = [
  "**Il problema non è la firma: è l’attesa.**",
  "",
  "Francesca: «Se e' fuori, possono essere giorni.» e «Non c'e' un sostituto formale». Nella simulazione As-Is qui le richieste aspettano in media 2g 22h: è il collo di bottiglia del processo.",
  "",
  "**Proposta To-Be**",
  "- una finestra di autorizzazione ogni giorno, con una **delega** quando il responsabile è fuori;",
  "- l’autorizzazione **visibile** a chi l’ha chiesta, non una mail che si aspetta.",
  "",
  "**Da verificare con Laura Conti:** la soglia di importo sopra cui serve l’autorizzazione. Nessuna fonte la dichiara, quindi non la metto nel modello.",
].join("\n");

/** La proposta come diagramma separato dall'As-Is: le due attivita' che cambiano. */
export const proposalXml = bpmnXml
  .replace('name="Autorizza spesa"', 'name="Autorizza spesa (responsabile o delegato, ogni giorno)"')
  .replace('name="Invia richiesta all\'Ufficio Tecnico"', 'name="Compila richiesta con campi obbligatori"');

for (const action of impactReview.actions as Record<string, unknown>[]) {
  action.proposal_xml = proposalXml;
}

/** Un turno dell'agente come lo recita `streamServer.mjs`: fasi di lavoro, poi il testo. */
export type ChatScript = { phases: { id: string; label: string; icon: string; detail?: string; ms?: number }[]; answer: string };

// Etichette e icone delle fasi: backend/services/agent_progress.py.
export const discoveryQuestion = chatMessages[0].content;
export const discoveryScript: ChatScript = {
  phases: [
    { id: "understanding", label: "Leggo la richiesta", icon: "brain", ms: 700 },
    { id: "reading_sources", label: "Leggo le fonti raccolte", icon: "document", detail: "3 interviste: Laura Conti, Paolo Marchetti, Francesca Neri", ms: 1500 },
    { id: "extracting", label: "Estraggo fatti e punti aperti", icon: "extract", detail: `${claimCount} affermazioni con citazione`, ms: 1300 },
    { id: "comparing", label: "Confronto con le evidenze esistenti", icon: "compare", ms: 1000 },
    { id: "modeling", label: "Costruisco il modello di processo", icon: "build", detail: "6 funzioni, percorso urgente", ms: 1100 },
    { id: "drafting", label: "Preparo la risposta", icon: "pen", ms: 500 },
  ],
  answer: chatMessages[1].content,
};

export const reviewScript: ChatScript = {
  phases: [
    { id: "understanding", label: "Leggo la richiesta", icon: "brain", ms: 600 },
    { id: "reading_sources", label: "Leggo le fonti raccolte", icon: "document", detail: "Intervista Francesca Neri · Ufficio Acquisti", ms: 1300 },
    { id: "comparing", label: "Confronto con le evidenze esistenti", icon: "compare", detail: "simulazione As-Is: attesa su Autorizza spesa", ms: 1100 },
    { id: "drafting", label: "Preparo la risposta", icon: "pen", ms: 500 },
  ],
  answer: reviewAnswer,
};

/** L'export del gestionale e l'analisi del backend (scripts/launch_media_eventlog.py). */
export const eventLog = readJson<{ log: Record<string, unknown>; preview: unknown; analysis: unknown }>(resolve(DATA, "eventlog.json"));

/** Review dell'As-Is su "Regolarizza ordine a posteriori": chi lo fa davvero, cosa manca. */
export const AS_IS_REVIEW_NODE = "percorso_urgente_regolarizza_ordine";
export const asIsReviewQuestion = "È corretto così? Chi lo fa davvero, e cosa manca?";
export const asIsReviewScript: ChatScript = {
  phases: [
    { id: "understanding", label: "Leggo la richiesta", icon: "brain", ms: 600 },
    { id: "reading_sources", label: "Leggo le fonti raccolte", icon: "document", detail: "3 interviste sul percorso urgente", ms: 1300 },
    { id: "comparing", label: "Confronto con le evidenze esistenti", icon: "compare", ms: 900 },
    { id: "drafting", label: "Preparo la risposta", icon: "pen", ms: 500 },
  ],
  answer: [
    "**Sì: la regolarizzazione la fa Acquisti.**",
    "",
    "Francesca: «La parte di ordine si', la faccio io.» Laura e Paolo non lo sanno: «non so da chi», «non voglio dirti un nome a caso».",
    "",
    "**Cosa manca nel modello**",
    "- la registrazione contabile è di Amministrazione, ma solo dopo l’ordine: «per farla loro hanno bisogno che io abbia aperto l'ordine»;",
    "- Paolo non sa che è Acquisti; Francesca: «Non credo, e onestamente non e' mai stato detto.»",
    "",
    "**Da confermare con Laura Conti** prima di validare l’As-Is.",
  ].join("\n"),
};
