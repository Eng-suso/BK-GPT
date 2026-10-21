/**
 * Il caso semplice dei video della landing: una richiesta di acquisto,
 * raccontata end-to-end in italiano e in inglese.
 *
 * Un processo che si legge in un colpo d'occhio (tre corsie, cinque attivita',
 * una decisione) su cui si vede tutto il prodotto: fonti e citazioni, As-Is con
 * le evidenze, versioni che non tornano, la domanda aperta, la review con
 * DeliR, simulazione e scenari, consegna al cliente.
 *
 * - Disegno e simulazioni: `scripts/launch_media_simple_case.py` (Prosimos,
 *   stessa pipeline del prodotto) in `data/simple/`.
 * - Fonti: le due interviste e la procedura sono scritte qui, nelle due lingue.
 *   Ogni citazione deve stare alla lettera nel testo della sua fonte: il modulo
 *   si ferma se non la trova.
 *
 * Azienda e persone sono fittizie.
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

export type Lang = "it" | "en";
const DATA = resolve(__dirname, "..", "data", "simple");
const readJson = <T>(file: string): T => JSON.parse(readFileSync(resolve(DATA, file), "utf-8")) as T;

export const SIMPLE_IDS = {
  client: "vetrano-industriale",
  project: "vetrano-richieste-acquisto",
  process: "richiesta-acquisto",
  model: "richiesta-acquisto-bpmn",
  asIsRun: 301,
  toBeRun: 302,
  thread: "thread-richiesta-acquisto",
} as const;
const IDS = SIMPLE_IDS;

const archive = { archived_at: null, archive_reason: null };
const CONSULTANT = "Marco Bellini";
const OWNER = "Laura Conti";
const CLIENT = "Vetrano Industriale S.p.A.";

// --- Testi nelle due lingue -------------------------------------------------

const T = {
  it: {
    process: "Richiesta di acquisto",
    project: "Richieste di acquisto",
    objective: "Capire perché una richiesta di acquisto impiega giorni, validarlo con chi ci lavora e simulare il miglioramento prima di cambiarlo.",
    phase: "Simulazione",
    status: "In corso",
    nextStep: `Validazione del To-Be con ${OWNER}`,
    milestones: ["Interviste e procedura", "As-Is validato", "Simulazione As-Is e To-Be", "Validazione del process owner"],
    openIssue: "Soglia di importo per la firma: nessuna fonte la dichiara",
    deliverables: ["As-Is validato", "Scenario To-Be simulato", "Cruscotto per il cliente"],
    sector: "Manifattura",
    nextActivity: "Validazione To-Be · 28 ott",
    interview: "Intervista",
    document: "Documento",
    sources: {
      francesca: { name: "Intervista Francesca Neri · Ufficio Acquisti", person: "Francesca Neri", role: "Ufficio Acquisti" },
      paolo: { name: "Intervista Paolo Marchetti · Manutenzione", person: "Paolo Marchetti", role: "Capo Manutenzione" },
      procedura: { name: "Procedura acquisti v3.pdf", person: "", role: "" },
    },
    summary: (who: string, role: string) => `Intervista a ${who} (${role}) sulla richiesta di acquisto.`,
    procedureSummary: "La procedura scritta della richiesta di acquisto, revisione 3.",
    portfolio: [
      { id: "brenta-packaging", name: "Brenta Packaging S.r.l.", sector: "Imballaggi", project: "Onboarding fornitori", phase: "Discovery", progress: 28, next: "Interviste con il team qualità", activity: "Intervista qualità · 30 ott" },
      { id: "orsini-logistica", name: "Orsini Servizi Logistici S.p.A.", sector: "Logistica", project: "Gestione resi e reclami", phase: "AS-IS", progress: 46, next: "Validazione AS-IS con il magazzino", activity: "Workshop AS-IS · 4 nov" },
    ],
  },
  en: {
    process: "Purchase request",
    project: "Purchase requests",
    objective: "Understand why a purchase request takes days, validate it with the people who do the work and simulate the improvement before changing it.",
    phase: "Simulation",
    status: "In corso",
    nextStep: `To-Be validation with ${OWNER}`,
    milestones: ["Interviews and procedure", "As-Is validated", "As-Is and To-Be simulation", "Process owner validation"],
    openIssue: "Amount threshold for sign-off: no source states it",
    deliverables: ["Validated As-Is", "Simulated To-Be scenario", "Client dashboard"],
    sector: "Manufacturing",
    nextActivity: "To-Be validation · Oct 28",
    interview: "Interview",
    document: "Document",
    sources: {
      francesca: { name: "Interview Francesca Neri · Purchasing", person: "Francesca Neri", role: "Purchasing" },
      paolo: { name: "Interview Paolo Marchetti · Maintenance", person: "Paolo Marchetti", role: "Maintenance lead" },
      procedura: { name: "Purchasing procedure v3.pdf", person: "", role: "" },
    },
    summary: (who: string, role: string) => `Interview with ${who} (${role}) about the purchase request.`,
    procedureSummary: "The written purchase request procedure, revision 3.",
    portfolio: [
      { id: "brenta-packaging", name: "Brenta Packaging S.r.l.", sector: "Packaging", project: "Supplier onboarding", phase: "Discovery", progress: 28, next: "Interviews with the quality team", activity: "Quality interview · Oct 30" },
      { id: "orsini-logistica", name: "Orsini Servizi Logistici S.p.A.", sector: "Logistics", project: "Returns and complaints", phase: "AS-IS", progress: 46, next: "AS-IS validation with the warehouse", activity: "AS-IS workshop · Nov 4" },
    ],
  },
} as const;

type SourceKey = "francesca" | "paolo" | "procedura";
const SOURCE_IDS: Record<SourceKey, string> = {
  francesca: "src-francesca-neri",
  paolo: "src-paolo-marchetti",
  procedura: "src-procedura-acquisti",
};
const SOURCE_DATES: Record<SourceKey, string> = { francesca: "2026-09-08", paolo: "2026-09-09", procedura: "2025-11-20" };

const TEXTS: Record<Lang, Record<SourceKey, string>> = {
  it: {
    francesca: `# Intervista a Francesca Neri, Ufficio Acquisti

**Marco:** Come ti arriva una richiesta di acquisto?

**Francesca:** Per mail. Il reparto mi scrive cosa serve e io la prendo in carico.

**Marco:** Cosa controlli per prima cosa?

**Francesca:** Controllo che ci siano codice articolo, quantità e centro di costo. Dieci minuti, se la richiesta è completa.

**Marco:** E quando non lo è?

**Francesca:** Una richiesta su due arriva senza codice o senza quantità, e la rimando indietro. Poi aspetto che me la rimandino, mezz'ora, a volte giorni se non trovano il codice.

**Marco:** Chi autorizza la spesa?

**Francesca:** Laura, la responsabile. Laura firma il martedì e il giovedì, quando è in sede. Se è in ferie, non c'è nessuno che firmi al posto suo.

**Marco:** Sopra quale importo serve la sua firma?

**Francesca:** Sopra una certa cifra serve la firma, ma la soglia è cambiata quest'anno e non voglio dirti un numero sbagliato.

**Marco:** Poi?

**Francesca:** Con la firma emetto l'ordine nel gestionale e lo mando al fornitore. Un quarto d'ora per ordine.

**Marco:** Cosa cambieresti?

**Francesca:** Farei nascere la richiesta già completa, con i campi obbligatori: non dovrei più rimandarla indietro. E quando Laura non c'è, vorrei che qualcuno potesse firmare al posto suo.
`,
    paolo: `# Intervista a Paolo Marchetti, Manutenzione

**Marco:** Come chiedi un acquisto?

**Paolo:** Quando mi serve qualcosa mando una mail ad Acquisti con quello che mi serve. Il codice articolo spesso non lo so, scrivo la descrizione.

**Marco:** E poi?

**Paolo:** Poi aspetto. A volte torna indietro perché manca qualcosa, a volte passa una settimana e non so a che punto è.

**Marco:** Sai chi la autorizza?

**Paolo:** So che deve firmare qualcuno in Acquisti, ma non so quando.

**Marco:** Cosa ti aiuterebbe?

**Paolo:** Un modulo che mi dica cosa serve, e vedere a che punto è la mia richiesta senza dover chiamare.
`,
    procedura: `# Procedura acquisti · revisione 3

1. Il richiedente invia la richiesta di acquisto all'Ufficio Acquisti.
2. L'Ufficio Acquisti verifica che la richiesta riporti codice articolo, quantità e centro di costo.
3. Le richieste incomplete sono restituite al richiedente.
4. Il responsabile autorizza la spesa entro un giorno lavorativo.
5. L'Ufficio Acquisti emette l'ordine al fornitore.

Le soglie di autorizzazione sono riportate nella tabella allegata.
`,
  },
  en: {
    francesca: `# Interview with Francesca Neri, Purchasing

**Marco:** How does a purchase request reach you?

**Francesca:** By email. The department writes what they need and I pick it up.

**Marco:** What do you check first?

**Francesca:** I check there is an item code, a quantity and a cost centre. Ten minutes, if the request is complete.

**Marco:** And when it isn't?

**Francesca:** One request in two arrives without a code or a quantity, and I send it back. Then I wait for it to come back, half an hour, sometimes days if they can't find the code.

**Marco:** Who approves the spend?

**Francesca:** Laura, the manager. Laura signs on Tuesdays and Thursdays, when she is in the office. If she is on holiday, nobody signs in her place.

**Marco:** Above what amount does she need to sign?

**Francesca:** Above a certain amount she has to sign, but the threshold changed this year and I don't want to give you a wrong number.

**Marco:** Then?

**Francesca:** Once it is signed I issue the order in the ERP and send it to the supplier. A quarter of an hour per order.

**Marco:** What would you change?

**Francesca:** I would make the request complete from the start, with mandatory fields: I would no longer have to send it back. And when Laura is away, I would like someone to be able to sign in her place.
`,
    paolo: `# Interview with Paolo Marchetti, Maintenance

**Marco:** How do you request a purchase?

**Paolo:** When I need something I email Purchasing with what I need. I often don't know the item code, so I write a description.

**Marco:** And then?

**Paolo:** Then I wait. Sometimes it comes back because something is missing, sometimes a week goes by and I don't know where it is.

**Marco:** Do you know who approves it?

**Paolo:** I know someone in Purchasing has to sign, but I don't know when.

**Marco:** What would help you?

**Paolo:** A form that tells me what is needed, and seeing where my request is without having to call.
`,
    procedura: `# Purchasing procedure · revision 3

1. The requester sends the purchase request to Purchasing.
2. Purchasing checks that the request includes item code, quantity and cost centre.
3. Incomplete requests are returned to the requester.
4. The manager approves the spend within one working day.
5. Purchasing issues the order to the supplier.

Approval thresholds are listed in the attached table.
`,
  },
};

// --- Affermazioni: ognuna con la sua citazione, alla lettera ------------------

type ClaimDef = { key: string; source: SourceKey; it: [string, string]; en: [string, string]; element?: string };
const CLAIMS: ClaimDef[] = [
  { key: "send", source: "paolo", element: "send_request",
    it: ["La richiesta parte con una mail ad Acquisti", "Quando mi serve qualcosa mando una mail ad Acquisti con quello che mi serve."],
    en: ["The request starts with an email to Purchasing", "When I need something I email Purchasing with what I need."] },
  { key: "nocode", source: "paolo",
    it: ["Il richiedente spesso non conosce il codice articolo", "Il codice articolo spesso non lo so, scrivo la descrizione."],
    en: ["The requester often doesn't know the item code", "I often don't know the item code, so I write a description."] },
  { key: "wait", source: "paolo",
    it: ["Il richiedente non sa a che punto è la richiesta", "a volte passa una settimana e non so a che punto è."],
    en: ["The requester can't see where the request is", "sometimes a week goes by and I don't know where it is."] },
  { key: "when", source: "paolo",
    it: ["Chi firma e quando: il richiedente non lo sa", "So che deve firmare qualcuno in Acquisti, ma non so quando."],
    en: ["Who signs and when: the requester doesn't know", "I know someone in Purchasing has to sign, but I don't know when."] },
  { key: "form", source: "paolo",
    it: ["Il richiedente chiede un modulo e lo stato visibile", "Un modulo che mi dica cosa serve, e vedere a che punto è la mia richiesta senza dover chiamare."],
    en: ["The requester asks for a form and visible status", "A form that tells me what is needed, and seeing where my request is without having to call."] },
  { key: "check", source: "francesca", element: "check_request",
    it: ["Acquisti verifica codice, quantità e centro di costo", "Controllo che ci siano codice articolo, quantità e centro di costo."],
    en: ["Purchasing checks code, quantity and cost centre", "I check there is an item code, a quantity and a cost centre."] },
  { key: "half", source: "francesca", element: "gw_complete",
    it: ["Metà delle richieste torna indietro incompleta", "Una richiesta su due arriva senza codice o senza quantità, e la rimando indietro."],
    en: ["Half of the requests are sent back incomplete", "One request in two arrives without a code or a quantity, and I send it back."] },
  { key: "rework", source: "francesca", element: "complete_request",
    it: ["Completare la richiesta può richiedere giorni", "mezz'ora, a volte giorni se non trovano il codice."],
    en: ["Completing the request can take days", "half an hour, sometimes days if they can't find the code."] },
  { key: "sign", source: "francesca", element: "approve_spend",
    it: ["La responsabile firma solo il martedì e il giovedì", "Laura firma il martedì e il giovedì, quando è in sede."],
    en: ["The manager signs only on Tuesdays and Thursdays", "Laura signs on Tuesdays and Thursdays, when she is in the office."] },
  { key: "nobody", source: "francesca",
    it: ["Nessun sostituto per la firma", "Se è in ferie, non c'è nessuno che firmi al posto suo."],
    en: ["No stand-in for the sign-off", "If she is on holiday, nobody signs in her place."] },
  { key: "threshold", source: "francesca",
    it: ["Soglia di firma: non la dice a memoria", "la soglia è cambiata quest'anno e non voglio dirti un numero sbagliato."],
    en: ["Sign-off threshold: not given from memory", "the threshold changed this year and I don't want to give you a wrong number."] },
  { key: "order", source: "francesca", element: "issue_po",
    it: ["Con la firma Acquisti emette l'ordine", "Con la firma emetto l'ordine nel gestionale e lo mando al fornitore."],
    en: ["Once signed, Purchasing issues the order", "Once it is signed I issue the order in the ERP and send it to the supplier."] },
  { key: "mandatory", source: "francesca",
    it: ["Proposta: richiesta con campi obbligatori", "Farei nascere la richiesta già completa, con i campi obbligatori"],
    en: ["Proposal: request with mandatory fields", "I would make the request complete from the start, with mandatory fields"] },
  { key: "delegate", source: "francesca",
    it: ["Proposta: qualcuno firma quando Laura non c'è", "vorrei che qualcuno potesse firmare al posto suo."],
    en: ["Proposal: someone signs when Laura is away", "I would like someone to be able to sign in her place."] },
  { key: "p-check", source: "procedura",
    it: ["La procedura prevede la verifica di codice, quantità e centro di costo", "L'Ufficio Acquisti verifica che la richiesta riporti codice articolo, quantità e centro di costo."],
    en: ["The procedure requires checking code, quantity and cost centre", "Purchasing checks that the request includes item code, quantity and cost centre."] },
  { key: "p-sign", source: "procedura",
    it: ["La procedura: firma entro un giorno lavorativo", "Il responsabile autorizza la spesa entro un giorno lavorativo."],
    en: ["The procedure: sign-off within one working day", "The manager approves the spend within one working day."] },
  { key: "p-threshold", source: "procedura",
    it: ["Le soglie sono in una tabella allegata, non presente", "Le soglie di autorizzazione sono riportate nella tabella allegata."],
    en: ["Thresholds are in an attached table that is missing", "Approval thresholds are listed in the attached table."] },
];

type RelationDef = { id: number; kind: "corroboration" | "divergence"; type: string | null; a: string; b: string; it: string; en: string };
const RELATIONS: RelationDef[] = [
  { id: 1, kind: "divergence", type: "incompatible", a: "sign", b: "p-sign",
    it: "La procedura dice che la firma arriva entro un giorno lavorativo; Francesca dice che Laura firma solo il martedì e il giovedì. Le due versioni non tornano: da verificare con la process owner.",
    en: "The procedure says sign-off comes within one working day; Francesca says Laura signs only on Tuesdays and Thursdays. The two versions don't match: to check with the process owner." },
  { id: 2, kind: "divergence", type: "knowledge_gap", a: "threshold", b: "p-threshold",
    it: "Nessuna fonte dichiara la soglia di firma: la procedura rimanda a una tabella che non c'è. Resta una domanda aperta, non un numero da stimare.",
    en: "No source states the sign-off threshold: the procedure points to a table that is missing. It stays an open question, not a number to guess." },
  { id: 3, kind: "divergence", type: "knowledge_gap", a: "when", b: "sign",
    it: "Paolo non sa quando viene firmata la sua richiesta; Francesca sì. Il richiedente non vede l'attesa.",
    en: "Paolo doesn't know when his request is signed; Francesca does. The requester can't see the wait." },
  { id: 4, kind: "corroboration", type: null, a: "check", b: "p-check",
    it: "Francesca e la procedura descrivono gli stessi tre controlli.",
    en: "Francesca and the procedure describe the same three checks." },
  { id: 5, kind: "corroboration", type: null, a: "nocode", b: "half",
    it: "Paolo non conosce il codice; Francesca rimanda indietro una richiesta su due per il codice mancante.",
    en: "Paolo doesn't know the code; Francesca sends back one request in two for the missing code." },
];

// --- Il caso, in una lingua ---------------------------------------------------

type Run = {
  name: string; model: unknown; scenario: Record<string, unknown>; result: Record<string, unknown>;
  summary: Record<string, unknown>; replay: Record<string, unknown>; request: Record<string, unknown>; experiments: unknown;
};

export type ChatScript = { phases: { id: string; label: string; icon: string; detail?: string; ms?: number }[]; answer: string };

/** I nomi tradotti dentro i JSON della simulazione (calcolati sul BPMN italiano). */
const EN_NAMES: Record<string, string> = {
  "Richiesta di acquisto": "Purchase request",
  "Invia richiesta d'acquisto": "Send purchase request",
  "Completa la richiesta": "Complete the request",
  "Verifica la richiesta": "Check the request",
  "Richiesta completa?": "Request complete?",
  "Emetti l'ordine": "Issue the order",
  "Autorizza la spesa": "Approve spend",
  "Fabbisogno rilevato": "Need spotted",
  "Ordine inviato": "Order sent",
  "Ufficio Acquisti": "Purchasing",
  "Richiedente": "Requester",
  "Responsabile": "Manager",
  "Situazione attuale": "Current process",
  "Delega giornaliera": "Daily delegate",
  "Richiesta completa + delega": "Complete request + delegate",
  "As-Is · validato": "As-Is · validated",
  "To-Be · richiesta completa + delega": "To-Be · complete request + delegate",
  "Firma il martedì e il giovedì": "Signs on Tuesdays and Thursdays",
  "Autorizzazione ogni giorno (delega)": "Daily approval (delegate)",
  "Stima del consulente.": "Consultant estimate.",
  "Persone e costo orario: assunzione del consulente.": "People and hourly cost: consultant assumption.",
  "Circa 5 richieste al giorno: assunzione del consulente.": "About 5 requests a day: consultant assumption.",
  "La firma in sé richiede pochi minuti: stima del consulente.": "The signature itself takes a few minutes: consultant estimate.",
  "«Dieci minuti, se la richiesta è completa.»": "«Ten minutes, if the request is complete.»",
  "«Mezz'ora, a volte giorni se non trovano il codice.»": "«Half an hour, sometimes days if they can't find the code.»",
  "«Un quarto d'ora per ordine.»": "«A quarter of an hour per order.»",
  "«Laura firma il martedì e il giovedì, quando è in sede.»": "«Laura signs on Tuesdays and Thursdays, when she is in the office.»",
  "«Una richiesta su due arriva senza codice o senza quantità.»": "«One request in two arrives without a code or a quantity.»",
  "To-Be: un delegato firma ogni giorno: assunzione del consulente.": "To-Be: a delegate signs every day: consultant assumption.",
  "To-Be: campi obbligatori, rilavorazione stimata al 15%.": "To-Be: mandatory fields, rework estimated at 15%.",
  "Intervista Francesca Neri · Ufficio Acquisti": "Interview Francesca Neri · Purchasing",
  "Intervista Paolo Marchetti · Manutenzione": "Interview Paolo Marchetti · Maintenance",
  "Procedura acquisti v3.pdf": "Purchasing procedure v3.pdf",
  "Sì": "Yes",
};
const EN_ORDERED = Object.entries(EN_NAMES).sort((a, b) => b[0].length - a[0].length);
function toEnglish(text: string): string {
  let out = text;
  for (const [it, en] of EN_ORDERED) {
    out = out.split(it).join(en);
    if (it.includes("'")) out = out.split(it.replace(/'/g, "&apos;")).join(en).split(it.replace(/'/g, "\\u0027")).join(en);
  }
  return out;
}
function localized<T>(value: T, lang: Lang): T {
  return lang === "it" ? value : (JSON.parse(toEnglish(JSON.stringify(value))) as T);
}

export function simpleCase(lang: Lang) {
  const t = T[lang];
  const bpmnXml = readFileSync(resolve(DATA, `${lang}.bpmn`), "utf-8");
  const runs = localized(readJson<{ as_is: Run; to_be: Run }>("runs.json"), lang);
  const api = localized(readJson<Record<string, unknown>>("api.json"), lang);
  const scenarioData = localized(readJson<{ seed: number; total_cases: number; scenarios: ScenarioDef[] }>("scenarios.json"), lang);
  const labels = new Map([...bpmnXml.matchAll(/<bpmn:(?:userTask|task|exclusiveGateway) id="([^"]+)" name="([^"]+)"/g)].map((m) => [m[1], m[2].replace(/&apos;/g, "'")]));

  const processItem = {
    id: IDS.process, project_id: IDS.project, bpmn_model_id: IDS.model, name: t.process,
    stage: "AS-IS", status: "Validato", owner: OWNER, readiness: 92, ...archive,
  };
  const project = {
    id: IDS.project, client_id: IDS.client, client: CLIENT, name: t.project, objective: t.objective, lead: CONSULTANT,
    start_date: "2026-09-07", end_date: "2026-10-30", phase: t.phase, status: t.status, progress: 72, processes: 1,
    next_step: t.nextStep,
    milestones: [
      { title: t.milestones[0], status: "done", completed_at: "2026-09-09" },
      { title: t.milestones[1], status: "done", completed_at: "2026-09-18" },
      { title: t.milestones[2], status: "done", completed_at: "2026-10-14" },
      { title: t.milestones[3], status: "planned", completed_at: null },
    ],
    open_issues: [t.openIssue], deliverables: [...t.deliverables], ...archive, process_items: [processItem],
  };
  const projects = [
    project,
    ...t.portfolio.map((item, index) => ({
      id: `${item.id}-progetto`, client_id: item.id, client: item.name, name: item.project, objective: "", lead: CONSULTANT,
      start_date: "2026-09-15", end_date: null, phase: item.phase, status: t.status, progress: item.progress, processes: 1 + index,
      next_step: item.next, milestones: [], open_issues: [], deliverables: [], ...archive, process_items: [],
    })),
  ];
  const sourceKeys: SourceKey[] = ["procedura", "francesca", "paolo"];
  const clients = [
    {
      id: IDS.client, name: CLIENT, sector: t.sector, status: "Attivo", projects: 1, next_activity: t.nextActivity, owner: CONSULTANT,
      contact: OWNER, processes: [t.process], documents: sourceKeys.map((key) => t.sources[key].name), ...archive,
    },
    ...t.portfolio.map((item) => ({
      id: item.id, name: item.name, sector: item.sector, status: "Attivo", projects: 1, next_activity: item.activity, owner: CONSULTANT,
      contact: "", processes: [], documents: [], ...archive,
    })),
  ];

  const text = (key: SourceKey) => TEXTS[lang][key];
  const sources = sourceKeys.map((key) => ({
    id: SOURCE_IDS[key], project_id: IDS.project, client_id: IDS.client, process_id: IDS.process, name: t.sources[key].name,
    type: key === "procedura" ? t.document : t.interview,
    meta: `${key === "procedura" ? "PDF" : t.interview} · ${SOURCE_DATES[key].split("-").reverse().join("/")}`,
    roles: ["process_evidence"], retention: "persistent", scopes: [{ type: "process", id: IDS.process }], status: "ready",
    byte_size: Buffer.byteLength(text(key)), content_hash: `sha-${SOURCE_IDS[key]}`,
    mime_type: key === "procedura" ? "application/pdf" : "text/markdown",
    acquisition_status: "done", acquisition_error: null, claims_status: "done", claims_error: null, reconcile_status: "done",
  }));
  const keyOf = (sourceId: string) => sourceKeys.find((key) => SOURCE_IDS[key] === sourceId);

  function sourceDocument(sourceId: string) {
    const key = keyOf(sourceId);
    if (!key) return null;
    const meta = t.sources[key];
    return {
      id: sourceId, project_id: IDS.project, process_id: IDS.process, name: meta.name, type: key === "procedura" ? t.document : t.interview,
      summary: key === "procedura" ? t.procedureSummary : t.summary(meta.person, meta.role),
      participants: key === "procedura" ? [] : [meta.person, CONSULTANT], occurred_at: SOURCE_DATES[key], episode_id: null,
      content: text(key), has_content: true,
    };
  }

  const anchorOf = (key: SourceKey, quote: string) => {
    const index = text(key).split(/\n\s*\n/).findIndex((paragraph) => paragraph.includes(quote.slice(0, 30)));
    return index >= 0 ? `§${index + 1}` : "§1";
  };
  const claims = CLAIMS.map((def, index) => {
    const [statement, quote] = def[lang];
    if (!text(def.source).includes(quote)) throw new Error(`citazione non trovata in ${def.source} (${lang}): ${quote}`);
    return { id: index + 1, key: def.key, source: def.source, statement, quote, element: def.element };
  });
  const claimByKey = new Map(claims.map((claim) => [claim.key, claim]));

  function claimsOf(sourceId: string) {
    const key = keyOf(sourceId);
    return claims.filter((claim) => claim.source === key).map((claim) => ({
      id: claim.id, source_id: sourceId, statement: claim.statement, segment_ordinal: Number(anchorOf(claim.source, claim.quote).slice(1)),
      anchor_ref: anchorOf(claim.source, claim.quote), quote: claim.quote, quote_verified: true, extracted_at: "2026-09-10T09:12:00Z",
    }));
  }
  const side = (claim: (typeof claims)[number]) => ({
    claim_id: claim.id, source_id: SOURCE_IDS[claim.source], source_name: t.sources[claim.source].name, statement: claim.statement,
    anchor_ref: anchorOf(claim.source, claim.quote), quote: claim.quote, quote_verified: true,
  });
  function relationsOf(sourceId: string) {
    const key = keyOf(sourceId);
    return RELATIONS.flatMap((relation) => {
      const a = claimByKey.get(relation.a)!;
      const b = claimByKey.get(relation.b)!;
      const mine = [a, b].find((claim) => claim.source === key);
      if (!mine) return [];
      const other = mine === a ? b : a;
      return [{
        id: relation.id, kind: relation.kind, divergence_type: relation.type, divergence_label: null, declared_type: relation.type,
        reasons: [], explanation: relation[lang], claim: side(mine), other: side(other),
      }];
    });
  }

  const evidenceClaims = claims.filter((claim) => claim.element);
  const provenance = {
    process_id: IDS.process, snapshot_id: "as-is-v3", snapshot_label: "V3", has_plan: true,
    total: evidenceClaims.length, verified: evidenceClaims.length, paraphrased: 0, label_grounded: 0, unverified: 0, awaiting_confirmation: 0,
    grounded_ratio: 1, sources_checked: sources.length, unused_sources: [],
    elements: evidenceClaims.map((claim) => ({
      kind: claim.element!.startsWith("gw_") ? "decision" : "step", element_id: claim.element, label: labels.get(claim.element!) ?? claim.element,
      status: "verified", mark_status: "verified", source_ref: `steps:${claim.element}`, source_id: SOURCE_IDS[claim.source],
      source_name: t.sources[claim.source].name, quote: claim.quote, consultant_decision: null, removable: false,
    })),
  };
  const conformance = {
    process_id: IDS.process, snapshot_id: "as-is-v3", snapshot_label: "V3", running: false, is_current: true,
    report: {
      verdict: "conformant", findings: [], sources_audited: sources.length, sources_with_text: sources.length, llm_audit: "done",
      llm_audit_note: "", discarded_findings: 0, snapshot_id: "as-is-v3", canvas_signature: "as-is-v3", audited_at: "2026-09-18T15:40:00+02:00",
    },
  };

  const steps = ["send_request", "check_request", "complete_request", "approve_spend", "issue_po"];
  const actorOf: Record<string, string> = { send_request: "requester", complete_request: "requester", check_request: "purchasing", issue_po: "purchasing", approve_spend: "manager" };
  const laneName = (id: string) => [...bpmnXml.matchAll(/<bpmn:lane id="([^"]+)" name="([^"]+)">/g)].find((m) => m[1] === id)?.[2] ?? id;
  const plan = {
    title: t.process,
    actors: ["requester", "purchasing", "manager"].map((id) => ({ id, label: laneName(id) })),
    steps: steps.map((id) => ({ id, label: labels.get(id) ?? id, description: null, actor_ids: [actorOf[id]], inputs: [], outputs: [] })),
    data_objects: [], controls: [], structured_business_rules: [], consultant_findings: [],
  };
  const semanticModel = {
    lanes: [...bpmnXml.matchAll(/<bpmn:lane id="([^"]+)" name="([^"]+)">([\s\S]*?)<\/bpmn:lane>/g)].map((m) => ({
      id: m[1], name: m[2], flowNodeRefs: [...m[3].matchAll(/<bpmn:flowNodeRef>([^<]+)<\/bpmn:flowNodeRef>/g)].map((r) => r[1]),
    })),
    flowNodes: [...bpmnXml.matchAll(/<bpmn:(startEvent|endEvent|userTask|exclusiveGateway) id="([^"]+)"(?: name="([^"]*)")?/g)].map((m) => ({ id: m[2], type: m[1], name: (m[3] ?? "").replace(/&apos;/g, "'") })),
    sequenceFlows: [...bpmnXml.matchAll(/<bpmn:sequenceFlow id="([^"]+)"(?: name="([^"]*)")? sourceRef="([^"]+)" targetRef="([^"]+)"/g)].map((m) => ({ id: m[1], sourceRef: m[3], targetRef: m[4], ...(m[2] ? { name: m[2] } : {}) })),
  };

  const question = lang === "it" ? "Sopra quale importo serve la firma della responsabile?" : "Above what amount does the manager have to sign?";
  const review = {
    bpmn_model_id: IDS.model, process_id: IDS.process, version: 3,
    source_text: lang === "it" ? "Due interviste (Acquisti, Manutenzione) e la procedura scritta." : "Two interviews (Purchasing, Maintenance) and the written procedure.",
    bpmn_brief: lang === "it"
      ? "## Richiesta di acquisto\n\nIl richiedente scrive ad Acquisti, che verifica la richiesta e la rimanda indietro se incompleta. La responsabile autorizza la spesa, poi Acquisti emette l'ordine."
      : "## Purchase request\n\nThe requester emails Purchasing, which checks the request and sends it back if incomplete. The manager approves the spend, then Purchasing issues the order.",
    readiness_score: 9.2,
    missing_information: [question],
    open_questions: [{
      question_id: "soglia-firma", question, severity: "blocking",
      options: lang === "it"
        ? [
            { label: "Chiedo la tabella delle soglie a Laura", implication: "La soglia entra nel modello solo quando una fonte la dichiara." },
            { label: "La lascio aperta nell'As-Is", implication: "La firma resta per tutte le richieste, senza un importo inventato." },
          ]
        : [
            { label: "I'll ask Laura for the threshold table", implication: "The threshold enters the model only when a source states it." },
            { label: "Leave it open in the As-Is", implication: "Sign-off stays on every request, with no made-up amount." },
          ],
      answer: null,
    }],
    process_understanding: plan, bpmn_semantic_model: semanticModel,
    quality_report: { approval_recommendation: "needs_user_clarification" }, status: "pending",
    created_at: "2026-09-10T09:00:00Z", updated_at: "2026-09-18T15:30:00Z",
  };

  const versions = [
    { id: 3, bpmn_model_id: IDS.model, process_id: IDS.process, change_summary: lang === "it" ? `As-Is v3 · validato con ${OWNER}` : `As-Is v3 · validated with ${OWNER}`, source: "consultant", created_at: "2026-09-18T15:42:00Z" },
    { id: 2, bpmn_model_id: IDS.model, process_id: IDS.process, change_summary: lang === "it" ? "Firma solo martedì e giovedì, come dice Francesca" : "Sign-off only on Tuesdays and Thursdays, as Francesca says", source: "consultant", created_at: "2026-09-12T11:05:00Z" },
    { id: 1, bpmn_model_id: IDS.model, process_id: IDS.process, change_summary: lang === "it" ? "Prima bozza dalle tre fonti" : "First draft from the three sources", source: "agent", created_at: "2026-09-10T09:20:00Z" },
  ];

  const baseRevision = createHash("sha256").update(bpmnXml).digest("hex");
  const proposalXml = bpmnXml
    .replace(`name="${labels.get("approve_spend")}"`, lang === "it" ? 'name="Autorizza la spesa (responsabile o delegato, ogni giorno)"' : 'name="Approve spend (manager or delegate, every day)"')
    .replace(`name="${labels.get("send_request")?.replace(/'/g, "&apos;")}"`, lang === "it" ? 'name="Compila il modulo con i campi obbligatori"' : 'name="Fill in the form with mandatory fields"');
  const impactReview = {
    process_id: IDS.process, base_revision: baseRevision, xml: bpmnXml, plan,
    actions: [
      {
        id: "tobe-richiesta-completa", node_id: "check_request", node_name: labels.get("check_request"), base_revision: baseRevision, kind: "candidate",
        title: lang === "it" ? "La richiesta nasce completa, con i campi obbligatori" : "The request is complete from the start, with mandatory fields",
        detail: lang === "it"
          ? "Francesca: «Farei nascere la richiesta già completa, con i campi obbligatori». Paolo: «Un modulo che mi dica cosa serve». Ipotesi simulata: le richieste rimandate indietro scendono dal 50% al 15% (stima del consulente)."
          : "Francesca: «I would make the request complete from the start, with mandatory fields». Paolo: «A form that tells me what is needed». Simulated hypothesis: requests sent back drop from 50% to 15% (consultant estimate).",
        created_at: "2026-10-12T10:00:00Z", created_by: CONSULTANT, proposal_xml: proposalXml,
      },
      {
        id: "tobe-delega", node_id: "approve_spend", node_name: labels.get("approve_spend"), base_revision: baseRevision, kind: "candidate",
        title: lang === "it" ? "Un delegato firma ogni giorno quando Laura non c'è" : "A delegate signs every day when Laura is away",
        detail: lang === "it"
          ? "Francesca: «Laura firma il martedì e il giovedì, quando è in sede» e «vorrei che qualcuno potesse firmare al posto suo». Ipotesi simulata: una finestra di firma ogni giorno."
          : "Francesca: «Laura signs on Tuesdays and Thursdays, when she is in the office» and «I would like someone to be able to sign in her place». Simulated hypothesis: a sign-off window every day.",
        created_at: "2026-10-12T10:05:00Z", created_by: CONSULTANT, proposal_xml: proposalXml,
      },
    ],
  };

  const runRecord = (id: number, run: Run, at: string) => ({
    id, bpmn_model_id: IDS.model, process_id: IDS.process, scenario_name: run.name, engine: "prosimos", status: "completed",
    idempotency_key: `simple-${id}`, request: run.request, scenario: run.scenario, result: run.result, outputs: [], summary: run.summary,
    error: null, created_at: at, completed_at: at,
  });
  const simulationRuns = [runRecord(IDS.toBeRun, runs.to_be, "2026-10-14T10:14:00Z"), runRecord(IDS.asIsRun, runs.as_is, "2026-10-14T09:48:00Z")];
  const runData = (id: number): Run | null => (id === IDS.asIsRun ? runs.as_is : id === IDS.toBeRun ? runs.to_be : null);
  const runById = (id: number) => simulationRuns.find((run) => run.id === id) ?? workspaceRuns.find((run) => run.id === id) ?? null;

  const { workspace, workspaceRuns } = buildWorkspace(scenarioData, simulationRuns, lang);

  const minutes = (seconds: number) => {
    const d = Math.floor(seconds / 86400);
    const h = Math.round((seconds % 86400) / 3600);
    return lang === "it" ? `${d}g ${h}h` : `${d}d ${h}h`;
  };
  const asIs = runs.as_is.summary as { byActivity: { el: string; wait: { avg: number } }[] };
  const approveWait = minutes(asIs.byActivity.find((a) => a.el === "approve_spend")?.wait.avg ?? 0);

  const chatSession = {
    thread_id: IDS.thread, title: lang === "it" ? "Discovery richiesta di acquisto" : "Purchase request discovery", scope_type: "process",
    project_id: IDS.project, process_id: IDS.process, bpmn_model_id: IDS.model, created_at: "2026-09-10T09:00:00Z", updated_at: "2026-09-18T15:30:00Z", messages: [],
  };
  const discoveryQuestion = lang === "it"
    ? "Ho caricato le interviste a Francesca e Paolo e la procedura. Ricostruisci l'As-Is senza inventare quello che nessuno dice."
    : "I've uploaded the interviews with Francesca and Paolo and the procedure. Rebuild the As-Is without inventing what nobody says.";
  const discoveryAnswer = lang === "it"
    ? `Ho letto le tre fonti ed estratto ${claims.length} affermazioni, ognuna con la sua citazione. Il processo passa da tre ruoli e cinque attività. ` +
      "Una cosa non torna: la procedura dice che la firma arriva entro un giorno, Francesca dice che Laura firma solo il martedì e il giovedì. " +
      "E una resta aperta: nessuna fonte dichiara la soglia di firma, quindi non la metto nel modello e te la chiedo."
    : `I've read the three sources and extracted ${claims.length} statements, each with its quote. The process runs through three roles and five activities. ` +
      "One thing doesn't match: the procedure says sign-off comes within a day, Francesca says Laura signs only on Tuesdays and Thursdays. " +
      "And one stays open: no source states the sign-off threshold, so I leave it out of the model and ask you.";
  const chatMessages = [{ id: 1, role: "user", content: discoveryQuestion }, { id: 2, role: "assistant", content: discoveryAnswer }];
  const L = lang === "it"
    ? { understanding: "Leggo la richiesta", reading: "Leggo le fonti raccolte", extracting: "Estraggo fatti e punti aperti", comparing: "Confronto con le evidenze esistenti", modeling: "Costruisco il modello di processo", drafting: "Preparo la risposta" }
    : { understanding: "Reading the request", reading: "Reading the collected sources", extracting: "Extracting facts and open points", comparing: "Comparing with existing evidence", modeling: "Building the process model", drafting: "Drafting the answer" };
  const discoveryScript: ChatScript = {
    phases: [
      { id: "understanding", label: L.understanding, icon: "brain", ms: 700 },
      { id: "reading_sources", label: L.reading, icon: "document", detail: lang === "it" ? "2 interviste e la procedura acquisti" : "2 interviews and the purchasing procedure", ms: 1500 },
      { id: "extracting", label: L.extracting, icon: "extract", detail: lang === "it" ? `${claims.length} affermazioni con citazione` : `${claims.length} statements with quotes`, ms: 1300 },
      { id: "comparing", label: L.comparing, icon: "compare", ms: 1000 },
      { id: "modeling", label: L.modeling, icon: "build", detail: lang === "it" ? "3 ruoli, 5 attività" : "3 roles, 5 activities", ms: 1100 },
      { id: "drafting", label: L.drafting, icon: "pen", ms: 500 },
    ],
    answer: discoveryAnswer,
  };
  const reviewQuestion = lang === "it" ? "Come miglioreresti questa attività? Basati solo sulle fonti." : "How would you improve this activity? Use only the sources.";
  const reviewAnswer = (lang === "it"
    ? [
        "**Il problema non è la firma: è l’attesa.**",
        "",
        `Francesca: «Laura firma il martedì e il giovedì, quando è in sede.» e «Se è in ferie, non c'è nessuno che firmi al posto suo.» Nella simulazione As-Is qui le richieste aspettano in media ${approveWait}: è il collo di bottiglia del processo.`,
        "",
        "**Proposta To-Be**",
        "- un **delegato** che firma ogni giorno quando Laura non c’è;",
        "- la richiesta che nasce **completa**, con i campi obbligatori: meno richieste rimandate indietro.",
        "",
        `**Da verificare con ${OWNER}:** la soglia di importo sopra cui serve la firma. Nessuna fonte la dichiara, quindi non la metto nel modello.`,
      ]
    : [
        "**The problem isn't the signature: it's the wait.**",
        "",
        `Francesca: «Laura signs on Tuesdays and Thursdays, when she is in the office.» and «If she is on holiday, nobody signs in her place.» In the As-Is simulation requests wait here ${approveWait} on average: it is the process bottleneck.`,
        "",
        "**To-Be proposal**",
        "- a **delegate** who signs every day when Laura is away;",
        "- a request that is **complete** from the start, with mandatory fields: fewer requests sent back.",
        "",
        `**To check with ${OWNER}:** the amount threshold above which sign-off is needed. No source states it, so I leave it out of the model.`,
      ]).join("\n");
  const reviewScript: ChatScript = {
    phases: [
      { id: "understanding", label: L.understanding, icon: "brain", ms: 600 },
      { id: "reading_sources", label: L.reading, icon: "document", detail: t.sources.francesca.name, ms: 1300 },
      { id: "comparing", label: L.comparing, icon: "compare", detail: lang === "it" ? `simulazione As-Is: attesa su ${labels.get("approve_spend")}` : `As-Is simulation: waiting at ${labels.get("approve_spend")}`, ms: 1100 },
      { id: "drafting", label: L.drafting, icon: "pen", ms: 500 },
    ],
    answer: reviewAnswer,
  };

  const toBe = runs.to_be.summary as { cycle: { avg: number }; waiting: { avg: number }; cost: { perCase: number } };
  const ownerDashboard = {
    process: { name: t.process, owner: OWNER, status: processItem.status, stage: processItem.stage },
    project_name: t.project, client_name: CLIENT, consultant_name: CONSULTANT, xml: bpmnXml,
    changes: impactReview.actions.map(({ id, node_id, node_name, title, detail, created_at }) => ({ id, node_id, node_name: node_name ?? "", title, detail, created_at })),
    open_points: [],
    versions: versions.map((version) => ({ id: version.id, change_summary: version.change_summary, created_at: version.created_at })),
    results: { scenario_name: runs.to_be.name, completed_at: "2026-10-14T10:14:00Z", cycle_avg_seconds: toBe.cycle.avg, waiting_avg_seconds: toBe.waiting.avg, cost_per_case: toBe.cost.perCase },
    generated_at: "2026-10-15T11:00:00Z",
  };

  const simulationLayoutKey = `delir:simulation:dashboard:${IDS.project}:${IDS.process}`;
  const kpi = (id: string, kind: string, metric: string, title: string, color: string, canvas: Record<string, number>) => ({
    id, title, kind, metric, width: "half", text: "**${metric}**", metricExpression: "", target: 100, followFilter: false, activityId: "", showLabels: true, color, canvas,
  });
  const k = lang === "it"
    ? { queued: "Richieste in coda", cycle: "Tempo medio di attraversamento" }
    : { queued: "Queued requests", cycle: "Average cycle time" };
  // Il processo e' il protagonista: grande a sinistra, due grafici compatti a destra.
  const simulationLayout = {
    version: 1,
    process: { canvas: { x: 0, y: 0, width: 1300, height: 520 }, groupId: "simple", beforeId: "__first__", width: "full", height: 520 },
    groups: [{
      id: "simple", title: "",
      widgets: [
        kpi("simple-queued", "area", "queued", k.queued, "amber", { x: 1324, y: 0, width: 300, height: 248 }),
        kpi("simple-cycle", "line", "cycle", k.cycle, "violet", { x: 1324, y: 272, width: 300, height: 248 }),
      ],
    }],
  };

  return {
    lang, IDS, labels, bpmnXml, proposalXml, api, runs, projects, project, processItem, clients, sources, sourceDocument, claimsOf, relationsOf,
    claimCount: claims.length, provenance, conformance, review, versions, impactReview, simulationRuns, runData, runById, workspace, workspaceRuns,
    chatSession, chatMessages, discoveryQuestion, discoveryScript, reviewQuestion, reviewScript, asIsReviewScript: reviewScript,
    ownerDashboard, simulationLayout, simulationLayoutKey, eventLog: null as null | { log: Record<string, unknown>; preview: unknown; analysis: unknown },
    owner: OWNER, client: CLIENT, consultant: CONSULTANT, openQuestion: question,
  };
}

export type SimpleCase = ReturnType<typeof simpleCase>;

// --- Workspace degli scenari: AS-IS, A, B con le loro ripetizioni ------------

type ModelResource = { id: string; name: string; cost_per_hour: number; amount: number; calendar_id?: string };
type Model = {
  calendars: { id: string; name: string; periods: { from_day: string; to_day: string; begin: string; end: string }[] }[];
  pools: { resources: ModelResource[] }[];
  activities: { element_id: string; assignments: { resource_id: string; duration: { mean: number } }[] }[];
  gateways: { element_id: string; branches: { flow_id: string; probability: number }[] }[];
};
type ScenarioDef = { label: "AS-IS" | "A" | "B"; name: string; model: Model; runs: { seed: number; summary: Record<string, unknown> }[] };

function buildWorkspace(
  data: { seed: number; total_cases: number; scenarios: ScenarioDef[] },
  simulationRuns: { id: number; request: Record<string, unknown> }[],
  lang: Lang,
) {
  const hhmm = (value: string) => value.slice(0, 5);
  const draftOf = (model: Model, name: string) => {
    const resources = model.pools.flatMap((pool) => pool.resources);
    return {
      scenarioName: name, totalCases: data.total_cases, arrivalIntervalMinutes: 96, defaultTaskMinutes: 10,
      resources: resources.map((r) => ({
        id: r.id, name: r.name, costPerHour: r.cost_per_hour, amount: r.amount, parametersConfirmed: true,
        ...(r.calendar_id && r.calendar_id !== "delir-calendar-standard" ? { calendarId: r.calendar_id } : {}),
      })),
      tasks: Object.fromEntries(model.activities.map((a) => [a.element_id, {
        meanMinutes: Math.round(a.assignments[0].duration.mean / 60), distribution: "norm", resourceId: a.assignments[0].resource_id, assignmentSource: "bpmn",
      }])),
      gateways: Object.fromEntries(model.gateways.map((g) => [g.element_id, Object.fromEntries(g.branches.map((b) => [b.flow_id, Math.round(b.probability * 100)]))])),
      calendars: model.calendars.filter((c) => c.id !== "delir-calendar-standard")
        .map((c) => ({ id: c.id, name: c.name, periods: c.periods.map((p) => ({ ...p, begin: hhmm(p.begin), end: hhmm(p.end) })) })),
    };
  };
  type Draft = ReturnType<typeof draftOf>;
  const patchOf = (base: Draft, scenario: Draft) => {
    const ops: { op: "set"; path: unknown[]; value: unknown }[] = [];
    const known = new Set(base.calendars.map((c) => c.id));
    scenario.calendars.filter((c) => !known.has(c.id)).forEach((c) => ops.push({ op: "set", path: ["calendars", { id: c.id }], value: c }));
    for (const r of scenario.resources) {
      const before = base.resources.find((x) => x.id === r.id);
      if (before && before.calendarId !== r.calendarId) ops.push({ op: "set", path: ["resources", { id: r.id }, "calendarId"], value: r.calendarId });
    }
    for (const [id, task] of Object.entries(scenario.tasks)) {
      if (base.tasks[id] && base.tasks[id].meanMinutes !== task.meanMinutes) ops.push({ op: "set", path: ["tasks", id, "meanMinutes"], value: task.meanMinutes });
    }
    for (const [id, branches] of Object.entries(scenario.gateways)) {
      for (const [flow, value] of Object.entries(branches)) {
        if (base.gateways[id]?.[flow] !== value) ops.push({ op: "set", path: ["gateways", id, flow], value });
      }
    }
    return ops;
  };
  const drafts = data.scenarios.map((s) => draftOf(s.model, s.name));
  const ids = { "AS-IS": 1, A: 2, B: 3 } as const;
  const workspace = {
    bpmn_model_id: IDS.model, seed: data.seed,
    baseline: { id: 1, kind: "baseline", label: "AS-IS", name: data.scenarios[0].name, revision: 1, draft: drafts[0], patch: [], conflicts: [], created_at: "2026-10-13T09:00:00Z", updated_at: "2026-10-13T09:00:00Z" },
    alternatives: data.scenarios.slice(1).map((s, i) => ({
      id: ids[s.label], kind: "alternative", label: s.label, name: s.name, revision: 1, draft: drafts[i + 1], patch: patchOf(drafts[0], drafts[i + 1]), conflicts: [],
      created_at: "2026-10-13T09:10:00Z", updated_at: "2026-10-13T09:10:00Z",
    })),
  };
  // Il primo run di AS-IS e B sono i run del replay (stesso modello, stesso seed).
  const firstRun: Record<string, number> = { "AS-IS": IDS.asIsRun, B: IDS.toBeRun };
  let next = 401;
  const workspaceRuns = data.scenarios.flatMap((scenario) => scenario.runs.map((run, index) => {
    const reused = index === 0 ? firstRun[scenario.label] : undefined;
    const base = (reused ? simulationRuns.find((r) => r.id === reused) : simulationRuns[0])!;
    const id = reused ?? next++;
    return {
      ...base, id,
      scenario_name: scenario.label === "AS-IS" ? "AS-IS" : `${scenario.label} · ${scenario.name}`,
      request: {
        ...base.request, seed: run.seed,
        workspace_scenario: { id: ids[scenario.label], revision: 1, baseline_revision: 1 },
        replication_group: `simple-${scenario.label}`, replication_index: index + 1,
      },
      summary: run.summary,
      created_at: `2026-10-13T09:${String(20 + (id % 40)).padStart(2, "0")}:00Z`,
      completed_at: `2026-10-13T09:${String(21 + (id % 40)).padStart(2, "0")}:00Z`,
    };
  }));
  void lang;
  return { workspace, workspaceRuns };
}
