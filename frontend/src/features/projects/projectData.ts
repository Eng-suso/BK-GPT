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

export type ProjectProcess = {
  id: string;
  bpmnModelId: string;
  name: string;
  stage: "Discovery" | "AS-IS" | "TO-BE" | "Validazione";
  status: "In corso" | "Da validare" | "Bozza";
  owner: string;
  readiness: number;
};
