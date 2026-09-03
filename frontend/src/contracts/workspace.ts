import { z } from "zod";

export type ProjectProcess = {
  id: string;
  bpmnModelId: string;
  name: string;
  stage: "Discovery" | "AS-IS" | "TO-BE" | "Validazione";
  status: "In corso" | "Da validare" | "Bozza";
  owner: string;
  readiness: number;
};

export type Project = {
  id: string;
  name: string;
  client: string;
  phase: string;
  status: "In corso" | "A rischio" | "Bozza";
  progress: number;
  processes: number;
  nextStep: string;
  milestones: string[];
  openIssues: string[];
  deliverables: string[];
  processItems: ProjectProcess[];
};

export type Client = {
  id: string;
  name: string;
  sector: string;
  status: "Attivo" | "Da seguire" | "Prospect";
  projects: number;
  nextActivity: string;
  owner: string;
  contact: string;
  processes: string[];
  documents: string[];
};

export type ProjectSource = {
  id: string;
  projectId: string;
  processId: string | null;
  name: string;
  type: string;
  meta: string;
};

export type ProjectDecision = {
  id: string;
  projectId: string;
  processId: string | null;
  title: string;
  owner: string;
  status: string;
};

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
});

const CLIENT_STATUS: Record<string, Client["status"]> = {
  attivo: "Attivo",
  cliente: "Attivo",
  active: "Attivo",
  "da seguire": "Da seguire",
  "follow up": "Da seguire",
  prospect: "Prospect",
};

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
});

export const apiProjectSchema = z.object({
  id: z.string(),
  client_id: z.string(),
  client: z.string(),
  name: z.string(),
  phase: z.string(),
  status: z.string(),
  progress: z.number(),
  processes: z.number(),
  next_step: z.string(),
  milestones: z.array(z.string()),
  open_issues: z.array(z.string()),
  deliverables: z.array(z.string()),
  process_items: z.array(apiProcessSchema),
});

export const apiProjectSourceSchema = z.object({
  id: z.string(),
  project_id: z.string(),
  process_id: z.string().nullable(),
  name: z.string(),
  type: z.string(),
  meta: z.string(),
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
  };
}

const VALID_PROCESS_STAGES = new Set(["Discovery", "AS-IS", "TO-BE", "Validazione"]);
const VALID_PROCESS_STATUSES = new Set(["In corso", "Da validare", "Bozza"]);
const VALID_PROJECT_STATUSES = new Set(["In corso", "A rischio", "Bozza"]);

function toProcess(process: z.infer<typeof apiProcessSchema>): ProjectProcess {
  return {
    id: process.id,
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
  };
}

export function toProject(project: z.infer<typeof apiProjectSchema>): Project {
  return {
    id: project.id,
    name: project.name,
    client: project.client,
    phase: project.phase,
    status: (VALID_PROJECT_STATUSES.has(project.status)
      ? project.status
      : "Bozza") as Project["status"],
    progress: project.progress,
    processes: project.processes,
    nextStep: project.next_step,
    milestones: project.milestones,
    openIssues: project.open_issues,
    deliverables: project.deliverables,
    processItems: project.process_items.map(toProcess),
  };
}

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
