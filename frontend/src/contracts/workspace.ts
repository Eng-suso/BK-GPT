import { z } from "zod";
import type { Project, ProjectProcess } from "../features/projects/projectData";

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

const apiClientSchema = z.object({
  id: z.string(),
  name: z.string(),
  sector: z.string(),
  status: z.enum(["Attivo", "Da seguire", "Prospect"]),
  projects: z.number(),
  next_activity: z.string(),
  owner: z.string(),
  contact: z.string(),
  processes: z.array(z.string()),
  documents: z.array(z.string()),
});

const apiProcessSchema = z.object({
  id: z.string(),
  project_id: z.string(),
  bpmn_model_id: z.string(),
  name: z.string(),
  stage: z.enum(["Discovery", "AS-IS", "TO-BE", "Validazione"]),
  status: z.enum(["In corso", "Da validare", "Bozza"]),
  owner: z.string(),
  readiness: z.number(),
});

const apiProjectSchema = z.object({
  id: z.string(),
  client_id: z.string(),
  client: z.string(),
  name: z.string(),
  phase: z.string(),
  status: z.enum(["In corso", "A rischio", "Bozza"]),
  progress: z.number(),
  processes: z.number(),
  next_step: z.string(),
  milestones: z.array(z.string()),
  open_issues: z.array(z.string()),
  deliverables: z.array(z.string()),
  process_items: z.array(apiProcessSchema),
});

const apiProjectSourceSchema = z.object({
  id: z.string(),
  project_id: z.string(),
  process_id: z.string().nullable(),
  name: z.string(),
  type: z.string(),
  meta: z.string(),
});

const apiProjectDecisionSchema = z.object({
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
    status: client.status,
    projects: client.projects,
    nextActivity: client.next_activity,
    owner: client.owner,
    contact: client.contact,
    processes: client.processes,
    documents: client.documents,
  };
}

function toProcess(process: z.infer<typeof apiProcessSchema>): ProjectProcess {
  return {
    id: process.id,
    bpmnModelId: process.bpmn_model_id,
    name: process.name,
    stage: process.stage,
    status: process.status,
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
    status: project.status,
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
