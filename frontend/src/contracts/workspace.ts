import { z } from "zod";

/**
 * Quando un record e' stato chiuso, e perche'.
 *
 * `archivedAt` vuoto = lavoro corrente. Un incarico chiuso esce dagli elenchi
 * operativi e resta leggibile in Archivio: chiudere e cancellare sono due
 * decisioni diverse, e prima esisteva solo la seconda.
 */
export type ArchiveState = {
  archivedAt: string | null;
  archiveReason: string | null;
};

/** Cosa si porta dietro chiudere o eliminare un record. */
export type ArchiveImpact = {
  id: string;
  name: string;
  projects: number;
  processes: number;
  sources: number;
  decisions: number;
};

export type ProjectProcess = ArchiveState & {
  id: string;
  projectId: string;
  bpmnModelId: string;
  name: string;
  stage: ProcessStage;
  status: ProcessStatus;
  owner: string;
  readiness: number;
};

/* ── Vocabolari condivisi col backend ──────────────────────────────
 * Le stesse voci di `backend/workspace_defaults.py`, nello stesso ordine: la
 * fase e' il ciclo di vita dell'incarico, dallo scoping alla consegna. Il
 * campo resta free-form sul filo (un record vecchio puo' portare altro), ma
 * questi sono i valori che la UI propone e che l'agente sceglie.
 */

export const PROJECT_PHASES = [
  "Discovery",
  "AS-IS",
  "Validazione",
  "TO-BE",
  "Simulazione",
  "Delivery",
] as const;
export type ProjectPhase = (typeof PROJECT_PHASES)[number];

export const PROJECT_STATUSES = [
  "Bozza",
  "In corso",
  "A rischio",
  "In pausa",
  "Completato",
] as const;
export type ProjectStatus = (typeof PROJECT_STATUSES)[number];

export const CLIENT_STATUSES = ["Attivo", "Da seguire", "Prospect"] as const;
export type ClientStatus = (typeof CLIENT_STATUSES)[number];

// Lo stadio dice *quale* processo si sta descrivendo, lo stato a che punto e'
// quella descrizione: due domande diverse, due vocabolari.
export const PROCESS_STAGES = [
  "Discovery",
  "AS-IS",
  "TO-BE",
  "Validazione",
] as const;
export type ProcessStage = (typeof PROCESS_STAGES)[number];

export const PROCESS_STATUSES = [
  "Bozza",
  "In corso",
  "Da validare",
  "Validato",
] as const;
export type ProcessStatus = (typeof PROCESS_STATUSES)[number];

/**
 * Un traguardo del progetto, e se e' stato raggiunto.
 *
 * Prima era una riga di testo, e il pannello di riepilogo disegnava lo stato
 * dall'ordine della lista: la prima voce spuntata, la seconda in corso. Adesso
 * lo stato arriva dal record, e nessuno lo inventa.
 */
export type Milestone = {
  title: string;
  status: MilestoneStatus;
  /** ISO 8601, valorizzata dal backend solo quando la milestone e' raggiunta. */
  completedAt: string | null;
};

export const MILESTONE_STATUSES = ["planned", "done"] as const;
export type MilestoneStatus = (typeof MILESTONE_STATUSES)[number];

export type Project = ArchiveState & {
  id: string;
  clientId: string;
  name: string;
  client: string;
  /** Perche' l'incarico esiste e cosa lo chiude. Vuoto = mai dichiarato. */
  objective: string;
  /** Chi segue l'incarico. `null` = mai dichiarato. */
  lead: string | null;
  /** Finestra dell'incarico, in ISO `YYYY-MM-DD`. `null` = mai dichiarata. */
  startDate: string | null;
  endDate: string | null;
  phase: string;
  status: ProjectStatus;
  progress: number;
  processes: number;
  nextStep: string;
  milestones: Milestone[];
  openIssues: string[];
  deliverables: string[];
  processItems: ProjectProcess[];
};

export type Client = ArchiveState & {
  id: string;
  name: string;
  sector: string;
  status: ClientStatus;
  projects: number;
  nextActivity: string;
  owner: string;
  contact: string;
  processes: string[];
  documents: string[];
};

/** Campi modificabili a mano dal consulente, o dall'agente per suo conto. */
export type ClientDraft = {
  name: string;
  sector: string;
  status: ClientStatus;
  owner: string;
  contact: string;
};

export type ProcessDraft = {
  name: string;
  stage: ProcessStage;
  status: ProcessStatus;
  owner: string;
  readiness: number;
};

export type ProjectDraft = {
  clientId: string;
  name: string;
  objective: string;
  /** Chi segue l'incarico. Vuoto significa "non l'ho ancora detto". */
  lead: string;
  /** Date in ISO `YYYY-MM-DD`, come le scrive un `<input type="date">`. */
  startDate: string;
  endDate: string;
  phase: string;
  status: ProjectStatus;
  progress: number;
  nextStep: string;
  /**
   * Il form modifica i titoli; lo stato di ogni milestone lo conserva il
   * backend, che riconosce le voci rimaste per titolo. Marcarne una come
   * raggiunta passa da `toApiMilestonePayload`.
   */
  milestones: string[];
  openIssues: string[];
  deliverables: string[];
};

export type ProjectSource = {
  id: string;
  projectId: string;
  processId: string | null;
  name: string;
  type: string;
  meta: string;
};

/**
 * A source with what it actually says, not just how it is labelled.
 *
 * The sources panel used to show a truncated note. Reading a claim back to its
 * evidence needs the original words, so a source carries its summary and its
 * full text. `hasContent` is false for evidence that never had a transcript.
 */
export type SourceDocument = {
  id: string;
  projectId: string;
  processId: string | null;
  name: string;
  type: string;
  summary: string;
  participants: string[];
  occurredAt: string | null;
  episodeId: string | null;
  content: string;
  hasContent: boolean;
};

export type ProjectDecision = {
  id: string;
  projectId: string;
  processId: string | null;
  title: string;
  owner: string;
  status: string;
};

// Un record salvato prima dell'archivio non porta questi campi: assenti vuol
// dire attivo, non "risposta malformata".
const archiveFields = {
  archived_at: z.string().nullable().default(null),
  archive_reason: z.string().nullable().default(null),
};

/** Legge lo stato di archiviazione da una risposta del backend. */
export function toArchiveState(record: {
  archived_at?: string | null;
  archive_reason?: string | null;
}): ArchiveState {
  return {
    archivedAt: record.archived_at ?? null,
    archiveReason: record.archive_reason ?? null,
  };
}

export const apiArchiveImpactSchema = z.object({
  id: z.string(),
  name: z.string(),
  projects: z.number(),
  processes: z.number(),
  sources: z.number(),
  decisions: z.number(),
});

export const apiClientSchema = z.object({
  id: z.string(),
  name: z.string(),
  sector: z.string(),
  // Backend status is free-form; normalised in `toClient`.
  status: z.string(),
  projects: z.number(),
  next_activity: z.string(),
  owner: z.string(),
  contact: z.string(),
  processes: z.array(z.string()),
  documents: z.array(z.string()),
  ...archiveFields,
});

const CLIENT_STATUS: Record<string, Client["status"]> = {
  attivo: "Attivo",
  cliente: "Attivo",
  active: "Attivo",
  "da seguire": "Da seguire",
  "follow up": "Da seguire",
  prospect: "Prospect",
};

/**
 * Converts a raw client status into a supported client status.
 *
 * @param raw - The raw client status value.
 * @returns The corresponding supported client status, or `"Prospect"` for unrecognized values.
 */
function normalizeClientStatus(raw: string): Client["status"] {
  return CLIENT_STATUS[raw.trim().toLowerCase()] ?? "Prospect";
}

export const apiProcessSchema = z.object({
  id: z.string(),
  project_id: z.string(),
  bpmn_model_id: z.string(),
  name: z.string(),
  stage: z.string(),
  status: z.string(),
  owner: z.string(),
  readiness: z.number(),
  ...archiveFields,
});

export const apiMilestoneSchema = z.object({
  title: z.string(),
  // Vocabolario del backend, non enum: uno stato sconosciuto non deve far
  // fallire il parse dell'intero progetto. Lo normalizza `toMilestone`.
  status: z.string().default("planned"),
  completed_at: z.string().nullable().default(null),
});

export const apiProjectSchema = z.object({
  id: z.string(),
  client_id: z.string(),
  client: z.string(),
  name: z.string(),
  // Aggiunto con PROJECT-01: un record creato prima non lo porta.
  objective: z.string().default(""),
  // Aggiunti con WS-04, e per la stessa ragione facoltativi: chi segue
  // l'incarico e fra quali date sta. Date in ISO `YYYY-MM-DD`.
  lead: z.string().nullable().default(null),
  start_date: z.string().nullable().default(null),
  end_date: z.string().nullable().default(null),
  phase: z.string(),
  status: z.string(),
  progress: z.number(),
  processes: z.number(),
  next_step: z.string(),
  // Un record salvato prima di MILESTONE-01 porta ancora una lista di stringhe.
  milestones: z.array(z.union([apiMilestoneSchema, z.string()])),
  open_issues: z.array(z.string()),
  deliverables: z.array(z.string()),
  ...archiveFields,
  process_items: z.array(apiProcessSchema),
});

export const apiArchiveSchema = z.object({
  clients: z.array(apiClientSchema),
  projects: z.array(apiProjectSchema),
  processes: z.array(apiProcessSchema),
});

export const apiProjectSourceSchema = z.object({
  id: z.string(),
  project_id: z.string(),
  process_id: z.string().nullable(),
  name: z.string(),
  type: z.string(),
  meta: z.string(),
});

export const apiSourceDocumentSchema = z.object({
  id: z.string(),
  project_id: z.string(),
  process_id: z.string().nullable(),
  name: z.string(),
  type: z.string(),
  summary: z.string(),
  participants: z.array(z.string()),
  occurred_at: z.string().nullable(),
  episode_id: z.string().nullable(),
  content: z.string(),
  has_content: z.boolean(),
});

export const apiProjectDecisionSchema = z.object({
  id: z.string(),
  project_id: z.string(),
  process_id: z.string().nullable(),
  title: z.string(),
  owner: z.string(),
  status: z.string(),
});

export const apiClientsSchema = z.array(apiClientSchema);
export const apiProjectsSchema = z.array(apiProjectSchema);
export const apiProjectSourcesSchema = z.array(apiProjectSourceSchema);
export const apiProjectDecisionsSchema = z.array(apiProjectDecisionSchema);

/**
 * Converts an API source document into the client-side model.
 *
 * @param document - The validated API source document
 * @returns The source document with client-side field names
 */
export function toSourceDocument(
  document: z.infer<typeof apiSourceDocumentSchema>,
): SourceDocument {
  return {
    id: document.id,
    projectId: document.project_id,
    processId: document.process_id,
    name: document.name,
    type: document.type,
    summary: document.summary,
    participants: document.participants,
    occurredAt: document.occurred_at,
    episodeId: document.episode_id,
    content: document.content,
    hasContent: document.has_content,
  };
}

/**
 * Converts an API client record into the client-side model.
 *
 * @param client - The validated API client record
 * @returns The normalized client model
 */
export function toClient(client: z.infer<typeof apiClientSchema>): Client {
  return {
    id: client.id,
    name: client.name,
    sector: client.sector,
    status: normalizeClientStatus(client.status),
    projects: client.projects,
    nextActivity: client.next_activity,
    owner: client.owner,
    contact: client.contact,
    processes: client.processes,
    documents: client.documents,
    ...toArchiveState(client),
  };
}

const VALID_PROCESS_STAGES = new Set<string>(PROCESS_STAGES);
const VALID_PROCESS_STATUSES = new Set<string>(PROCESS_STATUSES);
const VALID_PROJECT_STATUSES = new Set<string>(PROJECT_STATUSES);

/**
 * Determines whether a project phase belongs to the current phase vocabulary.
 *
 * @param phase - The project phase to validate
 * @returns `true` if the phase is recognized, `false` otherwise.
 */
export function isKnownProjectPhase(phase: string): phase is ProjectPhase {
  return (PROJECT_PHASES as readonly string[]).includes(phase);
}

/**
 * Converts an API process record into a project process.
 *
 * Unknown stages default to `"Discovery"` and unknown statuses default to `"Bozza"`.
 *
 * @param process - The API process record to convert
 * @returns The normalized project process
 */
export function toProcess(process: z.infer<typeof apiProcessSchema>): ProjectProcess {
  return {
    id: process.id,
    projectId: process.project_id,
    bpmnModelId: process.bpmn_model_id,
    name: process.name,
    stage: (VALID_PROCESS_STAGES.has(process.stage)
      ? process.stage
      : "Discovery") as ProjectProcess["stage"],
    status: (VALID_PROCESS_STATUSES.has(process.status)
      ? process.status
      : "Bozza") as ProjectProcess["status"],
    owner: process.owner,
    readiness: process.readiness,
    ...toArchiveState(process),
  };
}

/**
 * Converts one API milestone entry into the client-side milestone.
 *
 * @param milestone - A structured milestone, or the bare title stored before
 *   milestones carried their own state
 * @returns The normalized milestone
 */
export function toMilestone(
  milestone: z.infer<typeof apiMilestoneSchema> | string,
): Milestone {
  if (typeof milestone === "string") {
    return { title: milestone, status: "planned", completedAt: null };
  }

  const status: MilestoneStatus = milestone.status === "done" ? "done" : "planned";
  return {
    title: milestone.title,
    status,
    completedAt: status === "done" ? milestone.completed_at : null,
  };
}

/**
 * Builds the backend payload for a milestone list whose state must be preserved.
 *
 * @param milestones - The milestones as the UI holds them
 * @returns The milestone entries in backend field names
 */
export function toApiMilestonePayload(
  milestones: Milestone[],
): Record<string, unknown>[] {
  return milestones.map((milestone) => ({
    title: milestone.title,
    status: milestone.status,
    completed_at: milestone.completedAt,
  }));
}

/**
 * Converts an API project record into the client-side project structure.
 *
 * @param project - The validated API project record
 * @returns The normalized project
 */
export function toProject(project: z.infer<typeof apiProjectSchema>): Project {
  return {
    id: project.id,
    clientId: project.client_id,
    name: project.name,
    client: project.client,
    objective: project.objective,
    lead: project.lead,
    startDate: project.start_date,
    endDate: project.end_date,
    phase: project.phase,
    status: (VALID_PROJECT_STATUSES.has(project.status)
      ? project.status
      : "Bozza") as Project["status"],
    progress: project.progress,
    processes: project.processes,
    nextStep: project.next_step,
    milestones: project.milestones.map(toMilestone),
    openIssues: project.open_issues,
    deliverables: project.deliverables,
    ...toArchiveState(project),
    processItems: project.process_items.map(toProcess),
  };
}

/**
 * Builds a backend-compatible payload from a client draft, trimming editable text fields.
 *
 * @param draft - The client draft to serialize
 * @returns An object containing the client fields expected by the backend
 */

export function toApiClientPayload(draft: ClientDraft): Record<string, unknown> {
  return {
    name: draft.name.trim(),
    sector: draft.sector.trim(),
    status: draft.status,
    owner: draft.owner.trim(),
    contact: draft.contact.trim(),
  };
}

/**
 * Converts a process draft into the backend request payload format.
 *
 * @param draft - The process data to serialize
 * @returns A backend-compatible process payload with editable text fields trimmed
 */
export function toApiProcessPayload(draft: ProcessDraft): Record<string, unknown> {
  return {
    name: draft.name.trim(),
    stage: draft.stage,
    status: draft.status,
    owner: draft.owner.trim(),
    readiness: draft.readiness,
  };
}

/**
 * Converts a project draft into the backend request payload format.
 *
 * @param draft - The project data to serialize
 * @returns A backend-compatible project payload with editable text fields trimmed
 */
export function toApiProjectPayload(draft: ProjectDraft): Record<string, unknown> {
  return {
    client_id: draft.clientId,
    name: draft.name.trim(),
    objective: draft.objective.trim(),
    // Campo svuotato nel form = campo tolto dal record: il backend legge la
    // stringa vuota come "dimenticalo", non come "non l'ho detto".
    lead: draft.lead.trim(),
    start_date: draft.startDate,
    end_date: draft.endDate,
    phase: draft.phase,
    status: draft.status,
    progress: draft.progress,
    next_step: draft.nextStep.trim(),
    milestones: draft.milestones,
    open_issues: draft.openIssues,
    deliverables: draft.deliverables,
  };
}

/**
 * Converts an API project source record to the client-side project source model.
 *
 * @param source - The validated API project source record
 * @returns The project source with client-side field names
 */
export function toProjectSource(source: z.infer<typeof apiProjectSourceSchema>): ProjectSource {
  return {
    id: source.id,
    projectId: source.project_id,
    processId: source.process_id,
    name: source.name,
    type: source.type,
    meta: source.meta,
  };
}

export function toProjectDecision(
  decision: z.infer<typeof apiProjectDecisionSchema>,
): ProjectDecision {
  return {
    id: decision.id,
    projectId: decision.project_id,
    processId: decision.process_id,
    title: decision.title,
    owner: decision.owner,
    status: decision.status,
  };
}

/* ── BPMN model + versions ─────────────────────────────────────────
 * Backend: /v1/workspace/bpmn-models/*  (see docs/frontend-audit.md).
 * Consumed by features/process/api.ts.
 */

export type BpmnModel = {
  id: string;
  processId: string;
  name: string;
  xml: string | null;
};

export type BpmnVersion = {
  id: number;
  bpmnModelId: string;
  processId: string;
  changeSummary: string;
  source: string;
  createdAt: string;
};

export const apiBpmnModelSchema = z.object({
  id: z.string(),
  process_id: z.string(),
  name: z.string(),
  xml: z.string().nullable(),
});

// `xml` is present on the wire but intentionally not carried into the client
// cache — the version list never renders it.
export const apiBpmnVersionSchema = z.object({
  id: z.number(),
  bpmn_model_id: z.string(),
  process_id: z.string(),
  change_summary: z.string(),
  source: z.string(),
  created_at: z.string(),
});

export const apiBpmnVersionsSchema = z.array(apiBpmnVersionSchema);

export const apiRestoreBpmnVersionSchema = z.object({
  bpmn_model: apiBpmnModelSchema,
  restored_from: apiBpmnVersionSchema,
  created_version: apiBpmnVersionSchema,
});

export function toBpmnModel(model: z.infer<typeof apiBpmnModelSchema>): BpmnModel {
  return {
    id: model.id,
    processId: model.process_id,
    name: model.name,
    xml: model.xml,
  };
}

export function toBpmnVersion(
  version: z.infer<typeof apiBpmnVersionSchema>,
): BpmnVersion {
  return {
    id: version.id,
    bpmnModelId: version.bpmn_model_id,
    processId: version.process_id,
    changeSummary: version.change_summary,
    source: version.source,
    createdAt: version.created_at,
  };
}
