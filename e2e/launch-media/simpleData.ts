/**
 * Il caso semplice dei video della landing (docs/launch/landing-videos.md):
 * lo stesso processo compatto dell'hero (3 corsie, 5 attivita'), in italiano e
 * in BPMN 2.0.2 rigoroso (`data/simple.bpmn`: eventi con nome, split e merge
 * esclusivi espliciti, flussi in uscita etichettati).
 *
 * Simulazioni: i due run Prosimos dell'hero (`data/hero-runs.json`, stessi id
 * degli elementi), con i nomi riportati in italiano. Le evidenze sono citazioni
 * alla lettera del golden set: `claimQuote` si ferma se una non si trova.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { IDS } from "./demo";

const GOLDEN = resolve(__dirname, "..", "..", "tests", "golden", "esaote_ciclo_passivo", "sources");

export const simpleXml = readFileSync(resolve(__dirname, "data", "simple.bpmn"), "utf-8");

/** I nomi dei run dell'hero (in inglese) come stanno nel processo semplice. */
const ITALIAN: Record<string, string> = {
  "Send purchase request": "Invia richiesta di acquisto",
  "Check request": "Verifica richiesta",
  "Complete the request": "Completa la richiesta",
  "Approve spend": "Autorizza spesa",
  "Issue purchase order": "Emetti ordine",
  "Request complete?": "Richiesta completa?",
  "Need spotted": "Fabbisogno rilevato",
  "Order sent": "Ordine inviato",
  "Purchase request": "Richiesta di acquisto",
  "Manager approvals": "Presenza del responsabile",
  "Standard office calendar": "Calendario d'ufficio",
  "To-Be · complete request + daily delegate": "To-Be · richiesta completa + delega giornaliera",
  Requester: "Richiedente",
  Purchasing: "Ufficio Acquisti",
  Manager: "Responsabile",
};
const ordered = Object.entries(ITALIAN).sort((a, b) => b[0].length - a[0].length);

export function toItalian<T>(body: T): T {
  let text = JSON.stringify(body);
  for (const [en, it] of ordered) text = text.split(`"${en}`).join(`"${it}`);
  text = text.split('"Yes"').join('"Sì"');
  return JSON.parse(text) as T;
}

type Run = Record<string, unknown> & { summary: unknown; request: unknown; scenario: unknown; result: unknown; name: string };
const sim = toItalian(JSON.parse(readFileSync(resolve(__dirname, "data", "hero-runs.json"), "utf-8")) as Record<"as_is" | "to_be", Run>);
export const simpleApi = toItalian(JSON.parse(readFileSync(resolve(__dirname, "data", "hero-api.json"), "utf-8")) as { simulation_template: unknown; simulation_provenance: unknown });

export function simpleRunData(id: number) {
  if (id === IDS.asIsRun) return sim.as_is;
  if (id === IDS.toBeRun) return sim.to_be;
  return null;
}

export const simpleRunRecords = ([[IDS.toBeRun, sim.to_be, "To-Be · richiesta completa + delega", "2026-10-03T10:14:00Z"], [IDS.asIsRun, sim.as_is, "As-Is", "2026-10-03T09:48:00Z"]] as const).map(([id, run, name, at]) => ({
  id, bpmn_model_id: IDS.model, process_id: IDS.process, scenario_name: name, engine: "prosimos", status: "completed",
  idempotency_key: `simple-${id}`, request: run.request, scenario: run.scenario, result: run.result, outputs: [], summary: run.summary,
  error: null, created_at: at, completed_at: at,
}));

// --- Evidenze: ogni elemento del disegno con la frase che lo sostiene.

const FILES = {
  laura: { file: "a1_laura_conti_ufficio_tecnico.md", id: "src-laura-conti", name: "Intervista Laura Conti · Responsabile Ufficio Tecnico" },
  paolo: { file: "a2_paolo_marchetti_manutenzione.md", id: "src-paolo-marchetti", name: "Intervista Paolo Marchetti · Capo Manutenzione" },
  francesca: { file: "a3_francesca_neri_acquisti.md", id: "src-francesca-neri", name: "Intervista Francesca Neri · Ufficio Acquisti" },
} as const;

function claimQuote(who: keyof typeof FILES, quote: string) {
  const text = readFileSync(resolve(GOLDEN, FILES[who].file), "utf-8");
  if (!text.includes(quote)) throw new Error(`citazione non trovata in ${FILES[who].file}: ${quote}`);
  return { source_id: FILES[who].id, source_name: FILES[who].name, quote };
}

const BINDINGS: [string, string, "step" | "decision", keyof typeof FILES, string][] = [
  ["start", "Fabbisogno rilevato", "step", "paolo", "Se durante il giro vedo che manca qualcosa, o che un componente e' da sostituire prima che diventi un problema, me lo segno."],
  ["send_request", "Invia richiesta di acquisto", "step", "paolo", "Io mando la mail e poi c'e' il buio."],
  ["check_request", "Verifica richiesta", "step", "francesca", "Leggo e verifico se e' lavorabile."],
  ["gw_complete", "Richiesta completa?", "decision", "francesca", "Lavorabile vuol dire che capisco cosa devo comprare e da chi posso comprarlo."],
  ["complete_request", "Completa la richiesta", "step", "paolo", "Ogni richiesta si porta dietro due o tre scambi che non dovrebbero esserci."],
  ["approve_spend", "Autorizza spesa", "step", "francesca", "Sopra una certa cifra devo chiedere una autorizzazione al mio responsabile"],
  ["issue_po", "Emetti ordine", "step", "francesca", "Per le cose piccole e ricorrenti ho margine per procedere da sola: emetto l'ordine e via."],
];

const elements = BINDINGS.map(([element_id, label, kind, who, quote]) => ({
  kind, element_id, label, status: "verified", mark_status: "verified", source_ref: `steps:${element_id}`,
  ...claimQuote(who, quote), consultant_decision: null, removable: false,
}));

export const simpleProvenance = {
  process_id: IDS.process, snapshot_id: "as-is-v3", snapshot_label: "V3", has_plan: true,
  total: elements.length, verified: elements.length, paraphrased: 0, label_grounded: 0, unverified: 0, awaiting_confirmation: 0,
  grounded_ratio: 1, sources_checked: 3, unused_sources: [], elements,
};

// --- La tela di simulazione: il processo intero e sei KPI intorno, senza vuoti
// (misure minime del layout: 280x240, dashboardModel.ts). Sotto il processo
// quattro grafici, a destra due piu' alti: l'insieme ha le proporzioni della tela.

const kpi = (id: string, kind: string, metric: string, title: string, color: string, canvas: { x: number; y: number; width: number; height: number }) => ({
  id, title, kind, metric, width: "half", text: "**${metric}**", metricExpression: "", target: 100,
  followFilter: false, activityId: "", showLabels: true, color, canvas,
});
const below = (index: number) => ({ x: index * 298, y: 412, width: 286, height: 248 });
const right = (index: number) => ({ x: 1200, y: index * 336, width: 300, height: 324 });
export const simpleSimulationLayout = {
  version: 1,
  process: { canvas: { x: 0, y: 0, width: 1188, height: 400 }, groupId: "landing", beforeId: "__first__", width: "full", height: 400 },
  groups: [{
    id: "landing",
    title: "",
    widgets: [
      kpi("landing-queued", "area", "queued", "Richieste in coda", "amber", right(0)),
      kpi("landing-cycle", "line", "cycle", "Tempo medio di attraversamento", "violet", right(1)),
      kpi("landing-completed", "line", "completed", "Richieste concluse", "teal", below(0)),
      kpi("landing-throughput", "line", "throughput", "Throughput", "blue", below(1)),
      kpi("landing-cost", "area", "cost", "Costo accumulato", "violet", below(2)),
      kpi("landing-busy", "column", "resourceBusy", "Occupazione delle risorse", "amber", below(3)),
    ],
  }],
};

// --- La discussione del processo: la risposta di DeliR sul caso semplice.

export const simpleDiscoveryQuestion = "Ho caricato le interviste a Laura, Paolo e Francesca. Ricostruisci il processo senza inventare nulla.";
export const simpleDiscoveryScript = {
  phases: [
    { id: "understanding", label: "Leggo la richiesta", icon: "brain", ms: 900 },
    { id: "reading_sources", label: "Leggo le fonti raccolte", icon: "document", detail: "3 interviste: Laura Conti, Paolo Marchetti, Francesca Neri", ms: 1800 },
    { id: "extracting", label: "Estraggo fatti e punti aperti", icon: "extract", detail: "ogni affermazione con la sua citazione", ms: 1500 },
    { id: "modeling", label: "Costruisco il modello di processo", icon: "build", detail: "2 corsie, 5 attività, 1 decisione", ms: 1300 },
    { id: "drafting", label: "Preparo la risposta", icon: "pen", ms: 700 },
  ],
  answer: [
    "Ho letto le tre interviste. Il processo passa da **due ruoli**: chi chiede e l'Ufficio Acquisti, dove il responsabile autorizza la spesa.",
    "",
    "- La richiesta arriva spesso incompleta: Paolo, «due o tre scambi che non dovrebbero esserci».",
    "- Acquisti la verifica e, se è completa, chiede l'autorizzazione.",
    "",
    "**Da chiarire:** nessuna fonte dichiara la soglia di autorizzazione. Non la metto nel modello: te la chiedo.",
  ].join("\n"),
};

// --- Le altre letture del processo, sul disegno semplice.

const PROPOSAL_XML = simpleXml
  .replace('name="Autorizza spesa"', 'name="Autorizza spesa (responsabile o delegato, ogni giorno)"')
  .replace('name="Invia richiesta di acquisto"', 'name="Invia richiesta con campi obbligatori"');

export function simpleImpactReview(base: Record<string, unknown>) {
  const actions = (base.actions as Record<string, unknown>[]).map((action, index) => ({
    ...action,
    node_id: index === 0 ? "send_request" : "approve_spend",
    node_name: index === 0 ? "Invia richiesta di acquisto" : "Autorizza spesa",
    proposal_xml: PROPOSAL_XML,
  }));
  return { ...base, xml: simpleXml, actions };
}

export const simpleVersionNotes: Record<number, string> = {
  1: "Prima bozza dalle tre interviste",
  2: "Ciclo di integrazione della richiesta incompleta",
  3: "As-Is v3 · validato con Laura Conti",
};

/**
 * Le affermazioni di una fonte: i fatti del golden set (non legati al disegno
 * grande) piu' quelle che sostengono il disegno semplice.
 */
export function simpleClaims(sourceId: string, original: { statement: string; quote: string; id: number }[]) {
  const who = Object.entries(FILES).find(([, item]) => item.id === sourceId)?.[0] as keyof typeof FILES | undefined;
  if (!who) return [];
  const text = readFileSync(resolve(GOLDEN, FILES[who].file), "utf-8");
  const paragraphs = text.split(/\n\s*\n/);
  const anchor = (quote: string) => {
    const index = paragraphs.findIndex((paragraph) => paragraph.includes(quote.slice(0, 40)));
    return index >= 0 ? index + 1 : 1;
  };
  const facts = original.filter((item) => !item.statement.startsWith("Descrive "));
  const steps = BINDINGS.filter(([, , , owner]) => owner === who).map(([, label, kind, , quote], index) => ({
    id: 900 + index + Object.keys(FILES).indexOf(who) * 20,
    statement: `Descrive ${kind === "decision" ? "la decisione" : "il passo"} «${label}»`,
    quote,
  }));
  return [...steps, ...facts].map((item) => ({
    id: item.id, source_id: sourceId, statement: item.statement, segment_ordinal: anchor(item.quote), anchor_ref: `§${anchor(item.quote)}`,
    quote: item.quote, quote_verified: true, extracted_at: "2026-09-05T09:12:00Z",
  }));
}

/** Il cruscotto che il process owner apre dal link: lo stesso per l'anteprima. */
export function simpleOwnerDashboard() {
  const toBe = sim.to_be.summary as { cycle: { avg: number }; waiting: { avg: number }; cost: { perCase: number } };
  return {
    process: { name: "Richiesta di acquisto", owner: "Laura Conti", status: "Validato", stage: "approved" },
    project_name: "Acquisti indiretti e servizi",
    client_name: "Vetrano Industriale S.p.A.",
    consultant_name: "Marco Bellini",
    xml: PROPOSAL_XML,
    changes: [
      { id: "c1", node_id: "send_request", node_name: "Invia richiesta di acquisto", title: "La richiesta nasce completa, con i campi obbligatori", detail: "Lo chiedono Laura e Francesca.", created_at: "2026-10-01T10:00:00Z" },
      { id: "c2", node_id: "approve_spend", node_name: "Autorizza spesa", title: "Autorizzazione ogni giorno, con una delega", detail: "Oggi non c'e' un sostituto formale.", created_at: "2026-10-01T10:05:00Z" },
    ],
    open_points: [],
    versions: Object.entries(simpleVersionNotes).map(([id, change_summary]) => ({ id: Number(id), change_summary, created_at: `2026-09-${10 + Number(id) * 3}T10:00:00Z` })),
    results: { scenario_name: "To-Be · richiesta completa + delega", completed_at: "2026-10-03T10:14:00Z", cycle_avg_seconds: toBe.cycle.avg, waiting_avg_seconds: toBe.waiting.avg, cost_per_case: toBe.cost.perCase },
    generated_at: "2026-10-20T09:00:00Z",
  };
}
