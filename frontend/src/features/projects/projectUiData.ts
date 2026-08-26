import type { Project, ProjectProcess } from "./projectData";

export type ProjectTab =
  | "overview"
  | "process-map"
  | "processes"
  | "delivery"
  | "analysis"
  | "issues"
  | "recommendations"
  | "documents"
  | "team"
  | "settings";

export const projectTabs: Array<{ id: ProjectTab; label: string }> = [
  { id: "overview", label: "Panoramica" },
  { id: "process-map", label: "Mappa dei processi" },
  { id: "processes", label: "Processi" },
  { id: "delivery", label: "Piano e consegna" },
  { id: "analysis", label: "Analisi" },
  { id: "issues", label: "Problemi e opportunita" },
  { id: "recommendations", label: "Raccomandazioni" },
  { id: "documents", label: "Documenti" },
  { id: "team", label: "Team" },
  { id: "settings", label: "Impostazioni" },
];

export type ProjectIssue = {
  id: string;
  title: string;
  subtitle: string;
  type: "Problema" | "Rischio" | "Opportunita" | "Raccomandazione";
  impact: "Elevato" | "Medio" | "Basso";
  priority: "Alta" | "Media" | "Bassa";
  linkedProcess: string;
  owner: string;
  status: "In corso" | "In analisi" | "In review" | "Non avviata" | "Approvata";
};

export type ProjectActivity = {
  id: string;
  name: string;
  phase: string;
  owner: string;
  status: "Completato" | "In corso" | "Pianificato";
  start: string;
  end: string;
  progress: number;
};

export function ownerInitials(owner: string) {
  const parts = owner.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return owner.slice(0, 2).toUpperCase() || "DL";
}

export function projectDueDate(project: Project) {
  return project.status === "Bozza" ? "Da pianificare" : "30/09/2024";
}

export function projectIssueCount(project: Project) {
  return Math.max(project.openIssues.length, Math.ceil((100 - project.progress) / 18));
}

export function projectEvidenceCount(project: Project) {
  return project.processItems.reduce((total, process) => total + Math.max(4, Math.round(process.readiness / 8)), 0);
}

export function projectPhaseDetail(project: Project) {
  if (project.phase.toLowerCase().includes("implement")) return "Esecuzione";
  if (project.phase.toLowerCase().includes("design")) return "Soluzione TO-BE";
  if (project.phase.toLowerCase().includes("anal")) return "Assessment";
  return "Kick-off";
}

export function processArea(process: ProjectProcess) {
  const name = process.name.toLowerCase();
  if (name.includes("pay") || name.includes("acquist")) return "Acquisti";
  if (name.includes("customer") || name.includes("order") || name.includes("client")) return "Commerciale";
  if (name.includes("demand") || name.includes("supply")) return "Operations";
  if (name.includes("it") || name.includes("sistemi") || name.includes("dati")) return "IT";
  return "Aziendale";
}

export function processType(process: ProjectProcess) {
  const area = processArea(process);
  if (area === "Aziendale") return "Management";
  if (area === "IT") return "Supporto";
  return "Core";
}

export function processStatusLabel(process: ProjectProcess) {
  if (process.status === "Da validare") return "In review";
  if (process.status === "Bozza") return "Bozza";
  return "In corso";
}

export function processLastUpdated(index: number) {
  const dates = ["30/04/2024", "15/04/2024", "20/04/2024", "18/04/2024", "10/04/2024", "22/04/2024"];
  return dates[index % dates.length];
}

export function processEvidence(process: ProjectProcess) {
  return Math.max(5, Math.round(process.readiness / 5));
}

export function processOpenIssues(process: ProjectProcess) {
  return Math.max(0, Math.round((100 - process.readiness) / 24));
}

export function projectObjectives(project: Project) {
  const base = [
    "Ridurre i costi operativi della catena end-to-end",
    "Migliorare livelli di servizio e puntualita",
    "Ottimizzare tempi di ciclo e passaggi manuali",
    "Aumentare visibilita su responsabilita e avanzamento",
    "Digitalizzare i processi chiave del perimetro",
  ];
  return base.slice(0, Math.max(3, Math.min(5, project.processItems.length || 3)));
}

export function projectKpis() {
  return [
    { name: "OTIF", value: "88%", target: "95%", status: "warning" },
    { name: "Order Cycle Time", value: "6,2 gg", target: "<= 5,0", status: "warning" },
    { name: "Process Coverage", value: "72%", target: ">= 80%", status: "danger" },
    { name: "Forecast Accuracy", value: "76%", target: ">= 85%", status: "success" },
  ];
}

export function projectBenefits() {
  return [
    { label: "Risparmio costi operativi", value: "2,1M / anno" },
    { label: "Riduzione scorte", value: "1,3M / anno" },
    { label: "Miglioramento servizio", value: "+7 p.p." },
    { label: "Riduzione tempi ciclo", value: "-20%" },
  ];
}

export function projectRisks(project: Project) {
  const risks = project.openIssues.length > 0 ? project.openIssues : [
    "Ritardi integrazione sistemi",
    "Qualita dati anagrafici",
    "Adozione utenti",
  ];

  return risks.slice(0, 4).map((risk, index) => ({
    label: risk,
    priority: index < 2 ? "Alta" : "Media",
  }));
}

export function projectDecisionRequests(project: Project) {
  return [
    `Conferma milestone ${project.milestones[0] || "analisi AS-IS"}`,
    "Scelta soluzione operativa target",
    "Approvazione piano di implementazione",
    "Definizione policy di governance",
  ];
}

export function projectActivities(project: Project): ProjectActivity[] {
  const names = [
    "Kick-off progetto",
    "Analisi As-Is",
    "Mappatura processi To-Be",
    "Definizione KPI e metriche",
    "Progettazione soluzione",
    "Validazione design",
    "Piano di implementazione",
    "Go-live",
    "Monitoraggio post go-live",
  ];

  return names.map((name, index) => ({
    id: `${project.id}-activity-${index}`,
    name,
    phase: ["Pianificazione", "Analisi", "Design", "Design", "Design", "Validazione", "Implementazione", "Implementazione", "Monitoraggio"][index],
    owner: project.processItems[index % Math.max(project.processItems.length, 1)]?.owner || "Da assegnare",
    status: index === 0 ? "Completato" : index < 6 ? "In corso" : "Pianificato",
    start: ["01/05/2024", "06/05/2024", "20/05/2024", "20/05/2024", "27/05/2024", "24/06/2024", "01/07/2024", "30/09/2024", "01/10/2024"][index],
    end: ["03/05/2024", "24/05/2024", "14/06/2024", "11/06/2024", "21/06/2024", "28/06/2024", "12/07/2024", "30/09/2024", "30/10/2024"][index],
    progress: [100, 65, 50, 40, 30, 20, 10, 0, 0][index],
  }));
}

export function projectIssues(project: Project): ProjectIssue[] {
  const linkedProcesses = project.processItems.length > 0 ? project.processItems : [
    {
      id: "fallback-process",
      bpmnModelId: "fallback",
      name: "Order-to-Cash",
      stage: "AS-IS",
      status: "In corso",
      owner: "Sara Bellini",
      readiness: 72,
    } as ProjectProcess,
  ];

  const titles = [
    "Visibilita limitata dello stato ordini",
    "Affidabilita delle previsioni di domanda",
    "Automazione del processo di riordino",
    "Implementare dashboard operativa end-to-end",
    "Scarsa integrazione tra sistemi",
    "Rischio ritardi fornitori strategici",
    "Ottimizzazione network distributivo",
    "Standardizzare codifica materiali",
  ];

  return titles.map((title, index) => {
    const process = linkedProcesses[index % linkedProcesses.length];
    const typeCycle: ProjectIssue["type"][] = ["Problema", "Rischio", "Opportunita", "Raccomandazione"];
    const statusCycle: ProjectIssue["status"][] = ["In corso", "In corso", "In analisi", "In review", "In corso", "In analisi", "Non avviata", "Approvata"];

    return {
      id: `${project.id}-issue-${index}`,
      title,
      subtitle: index % 2 === 0 ? "Dati frammentati tra sistemi e aggiornamenti non real-time" : "Accuratezza inferiore al target operativo",
      type: typeCycle[index % typeCycle.length],
      impact: index < 4 ? "Elevato" : "Medio",
      priority: index < 3 ? "Alta" : "Media",
      linkedProcess: process.name,
      owner: process.owner,
      status: statusCycle[index],
    };
  });
}

export function projectTeam(project: Project) {
  const owners = Array.from(new Set(project.processItems.map((process) => process.owner))).filter(Boolean);
  const fallback = owners.length > 0 ? owners : ["Sara Bellini", "Fabio Moretti", "Luca Conti"];

  return fallback.slice(0, 5).map((name, index) => ({
    name,
    role: index === 0 ? "Owner" : index === 1 ? "Project Manager" : "Process Lead",
    company: index < 2 ? project.client : "DeliR",
    involvement: index === 0 ? "Responsabile" : "Attivo",
  }));
}
