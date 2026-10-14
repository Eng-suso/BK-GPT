/**
 * Il caso dei nuovi video del prodotto (piano video, ottobre 2026): "Gestione
 * richiesta di acquisto" di Vetrano Industriale S.p.A., in italiano e in
 * inglese come il sito.
 *
 * Tutto viene dai file del repo, niente scritto a mano qui:
 * - processo: `data/demo.marked.bpmn` / `demo.en.marked.bpmn`, dal compilatore
 *   del prodotto (`scripts/launch_media_demo_process.py`) con l'esito delle
 *   fonti scritto da `mark_provenance` (`scripts/launch_media_demo_evidence.py`);
 * - evidenze: `data/demo-evidence(.en).json`, citazioni alla lettera dalle
 *   interviste (in inglese dalla traduzione in `data/en/sources`);
 * - simulazioni: `data/demo-runs.json` e `data/demo-api.json`, Prosimos
 *   (`scripts/launch_media_demo_simulate.py`).
 *
 * Azienda e persone sono fittizie: il caso e' dimostrativo e i valori simulati.
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

export type Lang = "it" | "en";

const DATA = resolve(__dirname, "data");
const GOLDEN = resolve(__dirname, "..", "..", "tests", "golden", "esaote_ciclo_passivo");
const read = (path: string) => readFileSync(path, "utf-8");
const readJson = <T>(path: string): T => JSON.parse(read(path)) as T;

export const IDS = {
  client: "vetrano-industriale",
  project: "vetrano-acquisti-indiretti",
  process: "richiesta-acquisto",
  model: "richiesta-acquisto-bpmn",
  asIsRun: 401,
  toBeRun: 402,
  thread: "thread-richiesta-acquisto",
} as const;

export const CLIENT_NAME = "Vetrano Industriale S.p.A.";
export const PROCESS_OWNER = "Laura Conti";
export const CONSULTANT = "Marco Bellini";

const TEXT = {
  it: {
    project: "Acquisti indiretti",
    sector: "Manifattura",
    objective: "Ricostruire come nasce e si autorizza una richiesta di acquisto, validarla con chi ci lavora e simulare il miglioramento prima di cambiarlo.",
    phase: "Simulazione",
    status: "In corso",
    nextStep: "Validazione del To-Be con Laura Conti",
    milestones: ["Interviste", "As-Is validato", "Simulazione As-Is e To-Be", "Validazione del process owner"],
    openIssue: "Soglia di autorizzazione non dichiarata da nessuna fonte",
    deliverables: ["As-Is validato", "Scenario To-Be simulato", "Confronto KPI"],
    interview: "Intervista",
    roles: { "Laura Conti": "Responsabile Ufficio Tecnico", "Paolo Marchetti": "Capo Manutenzione", "Francesca Neri": "Ufficio Acquisti" },
    sourceSummary: (person: string, role: string) => `Intervista a ${person} (${role}) su come nasce e si autorizza una richiesta di acquisto.`,
    question: "Qual è la soglia di importo sopra cui serve l'autorizzazione del responsabile, e chi firma?",
    affects: "Autorizzazione necessaria?",
    groundedIn: "Francesca la conosce ma non la dice a memoria; Laura sa che esiste ma non quale sia. Nessuna fonte scritta.",
    options: [
      { label: "Chiedo la procedura scritta a Francesca", implication: "La soglia entra nel modello solo quando una fonte la dichiara." },
      { label: "La lascio aperta nell'As-Is", implication: "Il ramo di autorizzazione resta, senza un importo inventato." },
    ],
    brief: "## Gestione richiesta di acquisto\n\nLa richiesta nasce nel reparto, Acquisti ne verifica la completezza e, sopra una soglia che nessuno dichiara, la porta al responsabile prima di emettere l'ordine.",
    sourceText: "Sintesi di tre interviste: Ufficio Tecnico, Manutenzione, Acquisti.",
    versions: ["As-Is · validato con Laura Conti", "Ramo di rifiuto e richiesta di integrazione", "Prima bozza dalle tre interviste"],
    scenarios: { as_is: "As-Is", to_be: "To-Be · richiesta completa + delega" },
    changes: [
      { node: "Task_Compila", title: "La richiesta nasce completa, con i campi obbligatori", detail: "Francesca: «Farei in modo che la richiesta nasca gia' completa, con i campi obbligatori.» Nello scenario: rimbalzi dal 55% al 25% (stima del consulente)." },
      { node: "Task_Valuta", title: "Una delega quando il responsabile non c'è", detail: "Francesca: «Non c'e' un sostituto formale». Ipotesi del consulente, da validare: un'ora di delega ogni giorno lavorativo." },
    ],
  },
  en: {
    project: "Indirect purchasing",
    sector: "Manufacturing",
    objective: "Reconstruct how a purchase request is raised and authorized, validate it with the people who do the work, and simulate the improvement before changing it.",
    phase: "Simulation",
    status: "In progress",
    nextStep: "To-Be validation with Laura Conti",
    milestones: ["Interviews", "As-Is validated", "As-Is and To-Be simulation", "Process owner validation"],
    openIssue: "Authorization threshold not stated by any source",
    deliverables: ["Validated As-Is", "Simulated To-Be scenario", "KPI comparison"],
    interview: "Interview",
    roles: { "Laura Conti": "Technical Office Manager", "Paolo Marchetti": "Maintenance Lead", "Francesca Neri": "Purchasing Office" },
    sourceSummary: (person: string, role: string) => `Interview with ${person} (${role}) on how a purchase request is raised and authorized.`,
    question: "What is the amount above which the manager's authorization is required, and who signs?",
    affects: "Authorization required?",
    groundedIn: "Francesca knows it but won't state it from memory; Laura knows it exists but not what it is. No written source.",
    options: [
      { label: "I'll ask Francesca for the written procedure", implication: "The threshold enters the model only when a source states it." },
      { label: "I'll leave it open in the As-Is", implication: "The authorization branch stays, with no invented amount." },
    ],
    brief: "## Purchase request handling\n\nThe request starts in the department; Purchasing checks it is complete and, above a threshold nobody states, takes it to the manager before issuing the order.",
    sourceText: "Summary of three interviews: Technical Office, Maintenance, Purchasing.",
    versions: ["As-Is · validated with Laura Conti", "Rejection branch and request for missing information", "First draft from the three interviews"],
    scenarios: { as_is: "As-Is", to_be: "To-Be · complete request + delegate" },
    changes: [
      { node: "Task_Compila", title: "The request starts complete, with mandatory fields", detail: "Francesca: «__Q1__» In the scenario: send-backs from 55% to 25% (consultant estimate)." },
      { node: "Task_Valuta", title: "A delegate when the manager is away", detail: "Francesca: «__Q2__». Consultant hypothesis, to be validated: one hour of delegation every working day." },
    ],
  },
} as const;

const INTERVIEWS = [
  { file: "a1_laura_conti_ufficio_tecnico.md", id: "src-laura-conti", person: "Laura Conti", date: "2026-09-02" },
  { file: "a2_paolo_marchetti_manutenzione.md", id: "src-paolo-marchetti", person: "Paolo Marchetti", date: "2026-09-03" },
  { file: "a3_francesca_neri_acquisti.md", id: "src-francesca-neri", person: "Francesca Neri", date: "2026-09-04" },
] as const;

// Le citazioni inglesi sono quelle verificate alla lettera (data/en/quotes.json).
const QUOTES_EN = readJson<Record<string, string>>(resolve(DATA, "en", "quotes.json"));
const quoteEn = (it: string) => {
  const en = QUOTES_EN[it];
  if (!en) throw new Error(`citazione senza traduzione verificata: ${it}`);
  return en;
};
const fillQuotes = (text: string) =>
  text
    .replace("__Q1__", quoteEn("Farei in modo che la richiesta nasca gia' completa, con i campi obbligatori."))
    .replace("__Q2__", quoteEn("Non c'e' un sostituto formale"));

const interviewText = (lang: Lang, file: string) =>
  read(lang === "it" ? resolve(GOLDEN, "sources", file) : resolve(DATA, "en", "sources", file));

type Evidence = { source_id: string; person: string; role: string; quote: string };
type EvidenceElement = { element_id: string; source_ref: string; label: string; status: string; note?: string; evidence: Evidence[] };

/** Nomi italiani -> inglesi dei nodi, dai due BPMN (stessi id). */
function namesById(xml: string): Map<string, string> {
  return new Map([...xml.matchAll(/<bpmn:\w+ id="([^"]+)" name="([^"]+)"/g)].map((m) => [m[1], m[2].replace(/&apos;/g, "'")]));
}

/** I dati di simulazione sono scritti in italiano: in inglese si traducono i valori esatti. */
function englishNames(): [string, string][] {
  const it = namesById(read(resolve(DATA, "demo.bpmn")));
  const en = namesById(read(resolve(DATA, "demo.en.bpmn")));
  const pairs: [string, string][] = [...it].flatMap(([id, name]) => (en.has(id) && en.get(id) !== name ? [[name, en.get(id)!] as [string, string]] : []));
  const lanes = pairs.filter(([name]) => ["Reparto richiedente", "Ufficio Acquisti", "Responsabile Acquisti"].includes(name));
  for (const [itName, enName] of lanes) for (let i = 0; i < 8; i++) pairs.push([`${itName}_${i}`, `${enName}_${i}`]);
  pairs.push(
    ["Sì", "Yes"],
    [TEXT.it.scenarios.to_be, TEXT.en.scenarios.to_be],
    ["Responsabile presente a tratti", "Manager available at times"],
    ["Autorizzazione ogni giorno (delega)", "Daily authorization (delegate)"],
  );
  return pairs;
}

let englishPairs: [string, string][] | null = null;
function localizeJson<T>(body: T, lang: Lang): T {
  if (lang === "it") return body;
  englishPairs ??= englishNames();
  let text = JSON.stringify(body);
  for (const [itName, enName] of englishPairs) text = text.split(JSON.stringify(itName)).join(JSON.stringify(enName));
  return JSON.parse(text) as T;
}

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

/**
 * La tela di simulazione del video: il processo grande e i KPI, nessun bianco
 * intorno ("Modifica canvas -> Salva layout" scrive lo stesso JSON,
 * `layoutSchema` in dashboard/dashboardModel.ts). Le pagine hanno aree diverse:
 * - `wide`: Osserva e replay, tela a tutta larghezza (circa 2,3:1): il processo
 *   e due KPI in colonna a destra;
 * - `panel`: Confronto e pagine col pannello laterale (circa 4:3): il processo
 *   a tutta larghezza (e' largo, circa 1,9:1) e quattro KPI in riga sotto.
 */
export const simulationLayoutKey = `delir:simulation:dashboard:${IDS.project}:${IDS.process}`;
export type SimulationLayoutKind = "wide" | "panel";
const KPI_TITLES = {
  it: { cycle: "Tempo medio di attraversamento", queued: "Richieste in coda", cost: "Costo accumulato", resourceBusy: "Occupazione delle risorse" },
  en: { cycle: "Average cycle time", queued: "Queued requests", cost: "Accrued cost", resourceBusy: "Resource utilization" },
} as const;

export function simulationLayout(lang: Lang, kind: SimulationLayoutKind = "wide") {
  const titles = KPI_TITLES[lang];
  type Rect = { x: number; y: number; width: number; height: number };
  const widget = (metric: keyof typeof titles, chart: string, color: string, canvas: Rect) => ({
    id: `video-${metric}`, title: titles[metric], kind: chart, metric, width: "half", text: "**${metric}**", metricExpression: "", target: 100,
    followFilter: false, activityId: "", showLabels: true, color, canvas,
  });
  const GAP = 24;
  const PROCESS = kind === "wide" ? { width: 1180, height: 720 } : { width: 1500, height: 720 };
  let cells: Rect[];
  if (kind === "wide") {
    const column = { x: PROCESS.width + GAP, width: 520, height: (PROCESS.height - GAP) / 2 };
    cells = [0, 1].map((index) => ({ x: column.x, y: index * (column.height + GAP), width: column.width, height: column.height }));
  } else {
    const row = { y: PROCESS.height + GAP, height: 380, width: (PROCESS.width - 3 * GAP) / 4 };
    cells = [0, 1, 2, 3].map((index) => ({ x: index * (row.width + GAP), y: row.y, width: row.width, height: row.height }));
  }
  const widgets = [
    widget("cycle", "line", "blue", cells[0]),
    widget("queued", "area", "amber", cells[1]),
    ...(cells.length > 2 ? [widget("cost", "area", "blue", cells[2]), widget("resourceBusy", "column", "teal", cells[3])] : []),
  ];
  return {
    version: 1,
    process: { canvas: { x: 0, y: 0, ...PROCESS }, groupId: "video", beforeId: "__first__", width: "full", height: PROCESS.height },
    groups: [{ id: "video", title: "", widgets }],
  };
}

/** Tutto quello che il mock serve, in una lingua. */
export function demoCase(lang: Lang) {
  const t = TEXT[lang];
  const suffix = lang === "it" ? "" : ".en";
  const bpmnXml = read(resolve(DATA, `demo${suffix}.marked.bpmn`));
  const processName = namesById(bpmnXml).get("Process_richiesta_acquisto")!;
  const archive = { archived_at: null, archive_reason: null };
  const sourceName = (person: string) => `${t.interview} ${person} · ${t.roles[person as keyof typeof t.roles]}`;

  const processItem = {
    id: IDS.process,
    project_id: IDS.project,
    bpmn_model_id: IDS.model,
    name: processName,
    stage: "AS-IS",
    // Vocabolario del backend (uguale nelle due lingue): il processo non e'
    // ancora stato inviato al cliente, la consegna parte da qui.
    status: "In corso",
    owner: PROCESS_OWNER,
    readiness: 86,
    ...archive,
  };
  const project = {
    id: IDS.project,
    client_id: IDS.client,
    client: CLIENT_NAME,
    name: t.project,
    objective: t.objective,
    lead: CONSULTANT,
    start_date: "2026-09-01",
    end_date: "2026-10-30",
    phase: t.phase,
    status: t.status,
    progress: 64,
    processes: 1,
    next_step: t.nextStep,
    milestones: t.milestones.map((title, index) => ({
      title,
      status: index < 3 ? "done" : "planned",
      completed_at: ["2026-09-04", "2026-09-18", "2026-10-02", null][index],
    })),
    open_issues: [t.openIssue],
    deliverables: [...t.deliverables],
    ...archive,
    process_items: [processItem],
  };
  const client = {
    id: IDS.client,
    name: CLIENT_NAME,
    sector: t.sector,
    status: lang === "it" ? "Attivo" : "Active",
    projects: 1,
    next_activity: lang === "it" ? "Validazione To-Be · 14 ott" : "To-Be validation · Oct 14",
    owner: CONSULTANT,
    contact: PROCESS_OWNER,
    processes: [processName],
    documents: INTERVIEWS.map((item) => sourceName(item.person)),
    ...archive,
  };

  const sources = INTERVIEWS.map((item) => ({
    id: item.id,
    project_id: IDS.project,
    client_id: IDS.client,
    process_id: IDS.process,
    name: sourceName(item.person),
    type: t.interview,
    meta: `${t.interview} · ${item.date.split("-").reverse().join("/")}`,
    roles: ["process_evidence"],
    retention: "persistent",
    scopes: [{ type: "process", id: IDS.process }],
    status: "ready",
    byte_size: Buffer.byteLength(interviewText(lang, item.file)),
    content_hash: `sha-${item.id}`,
    mime_type: "text/markdown",
    acquisition_status: "done",
    acquisition_error: null,
    claims_status: "done",
    claims_error: null,
    reconcile_status: "done",
  }));
  const sourceDocument = (sourceId: string) => {
    const item = INTERVIEWS.find((entry) => entry.id === sourceId);
    if (!item) return null;
    const role = t.roles[item.person as keyof typeof t.roles];
    return {
      id: item.id,
      project_id: IDS.project,
      process_id: IDS.process,
      name: sourceName(item.person),
      type: t.interview,
      summary: t.sourceSummary(item.person, role),
      participants: [item.person, CONSULTANT],
      occurred_at: item.date,
      episode_id: null,
      content: interviewText(lang, item.file),
      has_content: true,
    };
  };

  // Le evidenze del disegno: una riga per elemento, con la prima citazione.
  const evidence = readJson<{ elements: EvidenceElement[] }>(resolve(DATA, `demo-evidence${suffix}.json`)).elements;
  const kindOf = (id: string) => (id.startsWith("Decision_") ? "decision" : /Event/.test(id) ? "event" : "step");
  const provenanceElements = evidence.map((item) => {
    const first = item.evidence[0];
    const status = first ? "verified" : "unverified";
    return {
      kind: kindOf(item.element_id),
      element_id: item.element_id,
      label: item.label,
      status,
      mark_status: status,
      source_ref: item.source_ref,
      source_id: first?.source_id ?? "",
      source_name: first ? sourceName(first.person) : "",
      quote: first?.quote ?? "",
      consultant_decision: null,
      removable: !first,
    };
  });
  const verified = provenanceElements.filter((item) => item.status === "verified").length;
  const provenance = {
    process_id: IDS.process,
    snapshot_id: "as-is-v3",
    snapshot_label: "V3",
    has_plan: true,
    total: provenanceElements.length,
    verified,
    paraphrased: 0,
    label_grounded: 0,
    unverified: provenanceElements.length - verified,
    awaiting_confirmation: provenanceElements.length - verified,
    grounded_ratio: verified / provenanceElements.length,
    sources_checked: INTERVIEWS.length,
    unused_sources: [],
    elements: provenanceElements,
  };

  // Il confronto disegno-fonti cerca contraddizioni: qui nessuna. Le tre ipotesi
  // del consulente restano "da confermare" nel rapporto di provenance.
  const conformance = {
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

  const semanticModel = {
    lanes: [...bpmnXml.matchAll(/<bpmn:lane id="([^"]+)" name="([^"]+)">([\s\S]*?)<\/bpmn:lane>/g)].map((m) => ({
      id: m[1],
      name: m[2],
      flowNodeRefs: [...m[3].matchAll(/<bpmn:flowNodeRef>([^<]+)<\/bpmn:flowNodeRef>/g)].map((r) => r[1]),
    })),
    flowNodes: [...bpmnXml.matchAll(/<bpmn:(startEvent|endEvent|userTask|exclusiveGateway) id="([^"]+)"(?: name="([^"]*)")?/g)].map((m) => ({
      id: m[2],
      type: m[1],
      name: (m[3] ?? "").replace(/&apos;/g, "'"),
    })),
    sequenceFlows: [...bpmnXml.matchAll(/<bpmn:sequenceFlow id="([^"]+)"(?: name="([^"]*)")? sourceRef="([^"]+)" targetRef="([^"]+)"/g)].map((m) => ({
      id: m[1],
      sourceRef: m[3],
      targetRef: m[4],
      ...(m[2] ? { name: m[2] } : {}),
    })),
  };
  const review = {
    bpmn_model_id: IDS.model,
    process_id: IDS.process,
    version: 3,
    source_text: t.sourceText,
    bpmn_brief: t.brief,
    readiness_score: 8.6,
    missing_information: [t.question],
    open_questions: [
      {
        question_id: "soglia-autorizzazione",
        question: t.question,
        affects: t.affects,
        severity: "blocking",
        grounded_in: t.groundedIn,
        options: t.options.map((option) => ({ ...option })),
        answer: null,
      },
    ],
    process_understanding: {},
    bpmn_semantic_model: semanticModel,
    quality_report: { approval_recommendation: "needs_user_clarification" },
    status: "pending",
    created_at: "2026-09-05T09:00:00Z",
    updated_at: "2026-09-18T15:30:00Z",
  };
  const versions = t.versions.map((change_summary, index) => ({
    id: 3 - index,
    bpmn_model_id: IDS.model,
    process_id: IDS.process,
    change_summary,
    source: index === 2 ? "agent" : "consultant",
    created_at: ["2026-09-18T15:42:00Z", "2026-09-12T11:05:00Z", "2026-09-05T09:20:00Z"][index],
  }));

  // Simulazioni: stessi numeri nelle due lingue, cambiano solo i nomi.
  const runs = localizeJson(readJson<{ as_is: Run; to_be: Run }>(resolve(DATA, "demo-runs.json")), lang);
  runs.as_is.name = t.scenarios.as_is;
  runs.to_be.name = t.scenarios.to_be;
  const api = localizeJson(readJson<Record<string, unknown>>(resolve(DATA, "demo-api.json")), lang);
  const runRecord = (id: number, run: Run, createdAt: string) => ({
    id,
    bpmn_model_id: IDS.model,
    process_id: IDS.process,
    scenario_name: run.name,
    engine: "prosimos",
    status: "completed",
    idempotency_key: `demo-${id}`,
    request: run.request,
    scenario: run.scenario,
    result: run.result,
    outputs: [],
    summary: run.summary,
    error: null,
    created_at: createdAt,
    completed_at: createdAt,
  });
  const simulationRuns = [
    runRecord(IDS.toBeRun, runs.to_be, "2026-10-02T10:14:00Z"),
    runRecord(IDS.asIsRun, runs.as_is, "2026-10-02T09:48:00Z"),
  ];
  const runData = (id: number): Run | null => (id === IDS.asIsRun ? runs.as_is : id === IDS.toBeRun ? runs.to_be : null);

  // Consegna: la proposta To-Be (le due modifiche), il cruscotto del responsabile.
  const baseRevision = createHash("sha256").update(bpmnXml).digest("hex");
  const nodeName = (id: string) => namesById(bpmnXml).get(id) ?? id;
  const actions = t.changes.map((change, index) => ({
    id: `tobe-${index + 1}`,
    node_id: change.node,
    node_name: nodeName(change.node),
    base_revision: baseRevision,
    kind: "candidate",
    title: change.title,
    detail: fillQuotes(change.detail),
    created_at: `2026-10-01T10:0${index}:00Z`,
    created_by: CONSULTANT,
    proposal_xml: null,
  }));
  const impactReview = {
    process_id: IDS.process,
    base_revision: baseRevision,
    xml: bpmnXml,
    plan: { title: processName, actors: [], steps: [], data_objects: [], controls: [], structured_business_rules: [], consultant_findings: [] },
    actions,
  };
  const toBe = runs.to_be.summary as { cycle: { avg: number }; waiting: { avg: number }; cost: { perCase: number } };
  const ownerDashboard = {
    process: { name: processName, owner: PROCESS_OWNER, status: processItem.status, stage: processItem.stage },
    project_name: t.project,
    client_name: CLIENT_NAME,
    consultant_name: CONSULTANT,
    xml: bpmnXml,
    changes: actions.map(({ id, node_id, node_name, title, detail, created_at }) => ({ id, node_id, node_name, title, detail, created_at })),
    open_points: [{ id: "soglia-autorizzazione", node_id: "Decision_Necessaria", node_name: nodeName("Decision_Necessaria"), title: t.question, kind: "clarification", created_at: "2026-09-18T15:30:00Z" }],
    versions: versions.map(({ id, change_summary, created_at }) => ({ id, change_summary, created_at })),
    results: { scenario_name: runs.to_be.name, completed_at: "2026-10-02T10:14:00Z", cycle_avg_seconds: toBe.cycle.avg, waiting_avg_seconds: toBe.waiting.avg, cost_per_case: toBe.cost.perCase },
    generated_at: "2026-10-13T09:00:00Z",
  };

  return {
    lang,
    processName,
    bpmnXml,
    processItem,
    project,
    projects: [project],
    clients: [client],
    sources,
    sourceDocument,
    provenance,
    conformance,
    impactReview,
    ownerDashboard,
    review,
    versions,
    api,
    runs,
    simulationRuns,
    runData,
    runById: (id: number) => simulationRuns.find((run) => run.id === id) ?? null,
  };
}

export type DemoCase = ReturnType<typeof demoCase>;
