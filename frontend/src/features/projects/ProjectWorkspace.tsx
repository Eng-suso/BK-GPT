import React from "react";
import {
  apiProjectDecisionsSchema,
  apiProjectSourcesSchema,
  toProjectDecision,
  toProjectSource,
} from "../../contracts/workspace";
import type { ProjectDecision, ProjectSource } from "../../contracts/workspace";
import { API_BASE } from "../../lib/api";
import { ProgressBar, StatusBadge, WorkspaceToolbar } from "../../components/workspace";
import { ChatExperience } from "../chat/ChatExperience";
import { ProcessWorkspace } from "../process/ProcessWorkspace";
import type { Project, ProjectProcess } from "./projectData";
import {
  ownerInitials,
  processArea,
  processEvidence,
  processLastUpdated,
  processOpenIssues,
  processStatusLabel,
  processType,
  projectActivities,
  projectBenefits,
  projectDecisionRequests,
  projectDueDate,
  projectEvidenceCount,
  projectIssueCount,
  projectIssues,
  projectKpis,
  projectObjectives,
  projectRisks,
  projectTabs,
  projectTeam,
} from "./projectUiData";
import type { ProjectIssue, ProjectTab } from "./projectUiData";

type ProjectWorkspaceProps = {
  project: Project;
  onBack: () => void;
};

export const ProjectWorkspace: React.FC<ProjectWorkspaceProps> = ({ project, onBack }) => {
  const [selectedProcessId, setSelectedProcessId] = React.useState<string | null>(null);
  const [selectedProcessDetailId, setSelectedProcessDetailId] = React.useState<string | null>(
    project.processItems[0]?.id ?? null,
  );
  const [activeTab, setActiveTab] = React.useState<ProjectTab>("overview");
  const [isAssistantOpen, setIsAssistantOpen] = React.useState(false);
  const [sources, setSources] = React.useState<ProjectSource[]>([]);
  const [decisions, setDecisions] = React.useState<ProjectDecision[]>([]);
  const selectedProcess =
    project.processItems.find((process) => process.id === selectedProcessId) ?? null;
  const selectedProcessDetail =
    project.processItems.find((process) => process.id === selectedProcessDetailId) ??
    project.processItems[0] ??
    null;

  React.useEffect(() => {
    let isMounted = true;

    async function loadProjectContext() {
      setSources([]);
      setDecisions([]);

      try {
        const [sourcesRes, decisionsRes] = await Promise.all([
          fetch(`${API_BASE}/v1/workspace/projects/${project.id}/sources`, { cache: "no-store" }),
          fetch(`${API_BASE}/v1/workspace/projects/${project.id}/decisions`, { cache: "no-store" }),
        ]);

        if (!sourcesRes.ok || !decisionsRes.ok) return;

        const [sourcesData, decisionsData] = await Promise.all([
          sourcesRes.json(),
          decisionsRes.json(),
        ]);

        if (isMounted) {
          setSources(apiProjectSourcesSchema.parse(sourcesData).map(toProjectSource));
          setDecisions(apiProjectDecisionsSchema.parse(decisionsData).map(toProjectDecision));
        }
      } catch (error) {
        console.error(error);
      }
    }

    void loadProjectContext();

    return () => {
      isMounted = false;
    };
  }, [project.id]);

  if (selectedProcess) {
    return (
      <ProcessWorkspace
        project={project}
        process={selectedProcess}
        onBack={() => setSelectedProcessId(null)}
      />
    );
  }

  return (
    <section className="enterprise-page project-command-center">
      <div className="enterprise-breadcrumb">
        <button type="button" onClick={onBack}>Progetti</button>
        <span>{project.name}</span>
        <span>{projectTabs.find((tab) => tab.id === activeTab)?.label}</span>
      </div>

      <header className="project-command-header">
        <div>
          <h2>{project.name}</h2>
          <p>
            {project.client}
            <span aria-hidden="true"> - </span>
            {project.processItems[0]?.owner || "Owner da assegnare"}
            <span aria-hidden="true"> - </span>
            <StatusDot status={project.status} />
            {project.status}
          </p>
        </div>
        <div className="project-command-actions">
          <button type="button" onClick={() => setIsAssistantOpen((value) => !value)}>
            DeliR
          </button>
          <button type="button">Azioni progetto v</button>
          <button type="button" className="enterprise-primary-button">
            Nuova attivita
            <span aria-hidden="true">+</span>
          </button>
        </div>
      </header>

      <nav className="project-tabs" aria-label="Sezioni progetto">
        {projectTabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={activeTab === tab.id ? "is-active" : ""}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <div className={`project-workspace-surface ${isAssistantOpen ? "with-assistant" : ""}`}>
        <main className="project-workspace-main">
          {activeTab === "overview" && (
            <OverviewTab project={project} sources={sources} decisions={decisions} />
          )}
          {activeTab === "process-map" && (
            <ProcessMapTab
              project={project}
              selectedProcess={selectedProcessDetail}
              onSelectProcess={setSelectedProcessDetailId}
              onOpenProcess={setSelectedProcessId}
            />
          )}
          {activeTab === "processes" && (
            <ProcessesTab project={project} onOpenProcess={setSelectedProcessId} />
          )}
          {activeTab === "delivery" && (
            <DeliveryTab project={project} />
          )}
          {activeTab === "analysis" && (
            <AnalysisTab project={project} />
          )}
          {activeTab === "issues" && (
            <IssuesTab project={project} />
          )}
          {activeTab === "recommendations" && (
            <RecommendationsTab project={project} />
          )}
          {activeTab === "documents" && (
            <DocumentsTab project={project} sources={sources} />
          )}
          {activeTab === "team" && (
            <TeamTab project={project} />
          )}
          {activeTab === "settings" && (
            <SettingsTab project={project} />
          )}
        </main>

        {isAssistantOpen && (
          <aside className="project-assistant-drawer" aria-label="Assistente progetto">
            <ChatExperience
              chrome="panel"
              layout="embedded"
              scope={{
                type: "project",
                projectId: project.id,
                projectName: project.name,
              }}
            />
          </aside>
        )}
      </div>
    </section>
  );
};

function OverviewTab({
  project,
  sources,
  decisions,
}: {
  project: Project;
  sources: ProjectSource[];
  decisions: ProjectDecision[];
}) {
  const kpis = projectKpis();

  return (
    <div className="project-tab-page">
      <section className="project-summary-strip">
        <div className="summary-cell summary-title">
          <button type="button" className="favorite-button" aria-label="Preferito">*</button>
          <div>
            <strong>{project.name}</strong>
            <span>{project.client}</span>
          </div>
        </div>
        <div className="summary-cell">
          <span>Owner</span>
          <strong>{project.processItems[0]?.owner || "Da assegnare"}</strong>
        </div>
        <div className="summary-cell">
          <span>Scadenza</span>
          <strong>{projectDueDate(project)}</strong>
          <ProgressBar value={project.progress} label={`${project.progress}%`} />
        </div>
        <div className="summary-cell">
          <span>Ultimo aggiornamento</span>
          <strong>15/04/2024</strong>
          <em>Aggiornato da {project.processItems[0]?.owner || "DeliR"}</em>
        </div>
      </section>

      <section className="manager-grid manager-grid-top">
        <Panel title="Obiettivi del progetto">
          <ul className="check-list">
            {projectObjectives(project).map((objective) => (
              <li key={objective}>
                <span className="check-dot">ok</span>
                <div>
                  <strong>{objective}</strong>
                  <span>Target operativo</span>
                </div>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="Avanzamento complessivo">
          <div className="donut-card">
            <div className="donut" style={{ "--value": `${project.progress}%` } as React.CSSProperties}>
              <span>{project.progress}%</span>
              <small>Completato</small>
            </div>
            <ul className="legend-list">
              <li><StatusDot status="In corso" />Completato <strong>{project.progress}%</strong></li>
              <li><StatusDot status="In corso" />In corso <strong>28%</strong></li>
              <li><StatusDot status="A rischio" />In ritardo <strong>6%</strong></li>
              <li><StatusDot status="Bozza" />Non iniziato <strong>4%</strong></li>
            </ul>
          </div>
        </Panel>

        <Panel title="Processi coinvolti">
          <div className="stacked-number-list">
            <strong>{project.processes || project.processItems.length}</strong>
            <span>Totali</span>
            <strong>{project.processItems.filter((process) => process.status === "In corso").length}</strong>
            <span>In corso</span>
            <strong>{project.processItems.filter((process) => process.readiness >= 80).length}</strong>
            <span>Completati</span>
          </div>
        </Panel>

        <Panel title="KPI essenziali">
          <table className="mini-table">
            <thead>
              <tr><th>KPI</th><th>Valore</th><th>Target</th><th>Stato</th></tr>
            </thead>
            <tbody>
              {kpis.map((kpi) => (
                <tr key={kpi.name}>
                  <td>{kpi.name}</td>
                  <td>{kpi.value}</td>
                  <td>{kpi.target}</td>
                  <td><span className={`status-dot status-dot-${kpi.status}`} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </section>

      <section className="manager-grid manager-grid-bottom">
        <Panel title="Benefici attesi">
          <KeyValueList items={projectBenefits()} />
        </Panel>
        <Panel title="Rischi principali">
          <ul className="risk-list">
            {projectRisks(project).map((risk) => (
              <li key={risk.label}>
                <span>{risk.label}</span>
                <StatusBadge tone={risk.priority === "Alta" ? "danger" : "warning"}>{risk.priority}</StatusBadge>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="Decisioni richieste">
          <ul className="compact-detail-list">
            {(decisions.length > 0 ? decisions.map((decision) => decision.title) : projectDecisionRequests(project)).slice(0, 4).map((decision, index) => (
              <li key={decision}>
                <span>{decision}</span>
                <em>Entro {index < 2 ? "30/04" : "10/05"}</em>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="Roadmap di alto livello">
          <RoadmapMini />
        </Panel>
        <Panel title="Stato delle consegne">
          <div className="delivery-status">
            <div className="donut small"><span>{project.deliverables.length || 4}</span></div>
            <ul className="legend-list">
              <li><StatusDot status="In corso" />Consegnati <strong>14</strong></li>
              <li><StatusDot status="In corso" />In corso <strong>10</strong></li>
              <li><StatusDot status="Bozza" />Previsti <strong>4</strong></li>
            </ul>
          </div>
        </Panel>
      </section>

      <section className="managerial-summary-panel">
        <div>
          <h3>Sintesi manageriale</h3>
          <p>
            Il progetto procede con avanzamento complessivo al {project.progress}%.
            Le aree con maggiore attenzione sono integrazione dati, validazione dei processi
            e decisioni operative ancora aperte. Le evidenze raccolte sono {sources.length || projectEvidenceCount(project)}
            e i processi in perimetro sono {project.processes || project.processItems.length}.
          </p>
          <div className="two-column-note">
            <div>
              <strong>Prossime priorita</strong>
              <ul>
                <li>Finalizzare i punti aperti ad alta priorita.</li>
                <li>Completare validazione dei processi core.</li>
                <li>Preparare il piano di change management.</li>
              </ul>
            </div>
            <div>
              <strong>Richieste al management</strong>
              <ul>
                <li>Approvazione milestone successiva.</li>
                <li>Decisione su soluzione operativa target.</li>
                <li>Supporto su owner e stakeholder.</li>
              </ul>
            </div>
          </div>
        </div>
        <div className="recent-activity">
          <h4>Azioni recenti</h4>
          <ActivityList project={project} />
        </div>
      </section>
    </div>
  );
}

function ProcessMapTab({
  project,
  selectedProcess,
  onSelectProcess,
  onOpenProcess,
}: {
  project: Project;
  selectedProcess: ProjectProcess | null;
  onSelectProcess: (id: string) => void;
  onOpenProcess: (id: string) => void;
}) {
  const management = project.processItems.filter((process) => processType(process) === "Management");
  const core = project.processItems.filter((process) => processType(process) === "Core");
  const support = project.processItems.filter((process) => processType(process) === "Supporto");
  type ProcessMapNode = {
    id: string;
    name: string;
    status: string;
    processId?: string;
    placeholder?: boolean;
  };
  const toNodes = (items: ProjectProcess[]): ProcessMapNode[] =>
    items.map((process) => ({
      id: process.id,
      name: process.name,
      status: process.status,
      processId: process.id,
    }));
  const rows = [
    {
      label: "Processi di management",
      className: "management",
      items: management.length ? toNodes(management) : [
        { id: "management-strategy", name: "Strategia e Pianificazione", status: "Bozza", placeholder: true },
        { id: "management-governance", name: "Governance e Performance", status: "Bozza", placeholder: true },
      ],
    },
    {
      label: "Processi core",
      className: "core",
      items: core.length ? toNodes(core) : toNodes(project.processItems),
    },
    {
      label: "Processi di supporto",
      className: "support",
      items: support.length ? toNodes(support) : [
        { id: "support-master-data", name: "Gestione Anagrafiche e Dati", status: "Bozza", placeholder: true },
        { id: "support-it", name: "IT e Sistemi Informativi", status: "Bozza", placeholder: true },
      ],
    },
  ];

  return (
    <div className="project-tab-page process-map-layout">
      <div className="process-map-main">
        <WorkspaceToolbar>
          <button type="button">Area aziendale Tutte v</button>
          <button type="button">Tipo processo Tutti v</button>
          <button type="button">Owner Tutti v</button>
          <button type="button">Stato Tutti v</button>
          <button type="button">Altri filtri</button>
          <button type="button" className="enterprise-primary-button">Salva vista v</button>
        </WorkspaceToolbar>

        <section className="process-map-board" aria-label="Mappa dei processi">
          <div className="map-tool-rail" aria-hidden="true">
            <button type="button">+</button>
            <button type="button">-</button>
            <button type="button">[]</button>
          </div>
          {rows.map((row) => (
            <div key={row.label} className={`process-map-row process-map-row-${row.className}`}>
              <div className="process-map-row-label">
                <span className="process-row-icon">{row.className[0].toUpperCase()}</span>
                <strong>{row.label}</strong>
              </div>
              <div className="process-map-nodes">
                {row.items.map((process) => {
                  const isSelected = selectedProcess?.id === process.processId;
                  return (
                    <button
                      key={`${row.className}-${process.id}`}
                      type="button"
                      className={`process-map-node ${isSelected ? "is-selected" : ""} ${process.placeholder ? "is-placeholder" : ""}`}
                      onClick={() => process.processId && onSelectProcess(process.processId)}
                    >
                      <span>{process.name}</span>
                      <StatusDot status={process.status} />
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </section>

        <section className="process-portfolio-panel">
          <header className="panel-heading-row">
            <h3>Portfolio processi</h3>
            <label className="panel-search">
              <span>S</span>
              <input type="search" placeholder="Cerca nei processi..." />
            </label>
          </header>
          <ProcessTable project={project} onOpenProcess={onOpenProcess} />
        </section>
      </div>

      <ProcessDetailDrawer process={selectedProcess} onOpenProcess={onOpenProcess} />
    </div>
  );
}

function ProcessesTab({
  project,
  onOpenProcess,
}: {
  project: Project;
  onOpenProcess: (processId: string) => void;
}) {
  return (
    <div className="project-tab-page">
      <WorkspaceToolbar searchPlaceholder="Cerca processi...">
        <button type="button">Fase v</button>
        <button type="button">Readiness v</button>
        <button type="button">Owner v</button>
      </WorkspaceToolbar>
      <ProcessTable project={project} onOpenProcess={onOpenProcess} />
    </div>
  );
}

function DeliveryTab({ project }: { project: Project }) {
  const activities = projectActivities(project);
  const team = projectTeam(project);

  return (
    <div className="project-tab-page delivery-layout">
      <section className="workplan-panel">
        <header className="panel-heading-row">
          <h3>Piano di lavoro</h3>
          <div>
            <button type="button">Tutte le attivita v</button>
            <button type="button">Fase v</button>
            <button type="button">Filtri</button>
          </div>
        </header>
        <table className="enterprise-table compact">
          <thead>
            <tr>
              <th>Attivita</th>
              <th>Fase</th>
              <th>Owner</th>
              <th>Stato</th>
              <th>Inizio</th>
              <th>Fine</th>
              <th>Avanzamento</th>
            </tr>
          </thead>
          <tbody>
            {activities.map((activity) => (
              <tr key={activity.id}>
                <td><strong>{activity.name}</strong></td>
                <td>{activity.phase}</td>
                <td><OwnerCell owner={activity.owner} /></td>
                <td><StatusPill label={activity.status} /></td>
                <td>{activity.start}</td>
                <td>{activity.end}</td>
                <td><ProgressBar value={activity.progress} label={`${activity.progress}%`} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="roadmap-panel">
        <header className="panel-heading-row">
          <h3>Roadmap del progetto</h3>
          <div><button type="button">Settimane v</button><button type="button">Oggi</button></div>
        </header>
        <div className="gantt-board">
          {activities.slice(0, 8).map((activity, index) => (
            <div key={activity.id} className="gantt-row">
              <span>{activity.name}</span>
              <i style={{ marginLeft: `${Math.min(65, index * 8)}%`, width: `${Math.max(8, activity.progress / 4)}%` }} />
            </div>
          ))}
        </div>
      </section>

      <section className="milestone-timeline">
        {(project.milestones.length ? project.milestones : ["Kick-off completato", "Design validato", "Piano approvato", "Go-live"]).map((milestone, index) => (
          <div key={milestone}>
            <span className={index < 2 ? "is-complete" : ""} />
            <strong>{milestone}</strong>
            <small>{index < 2 ? "Completato" : "Pianificato"}</small>
          </div>
        ))}
      </section>

      <section className="delivery-bottom-grid">
        <Panel title="Attivita assegnate a me">
          <CompactRows rows={activities.slice(1, 4).map((activity) => [activity.name, activity.end, activity.status])} />
        </Panel>
        <Panel title="Owner e stakeholder">
          <CompactRows rows={team.map((member) => [member.name, member.role, member.involvement])} />
        </Panel>
        <Panel title="Deliverable previsti">
          <CompactRows rows={(project.deliverables.length ? project.deliverables : ["Mappatura Processi To-Be", "KPI e Metriche", "Piano di implementazione"]).map((item) => [item, "Documento", "In corso"])} />
        </Panel>
        <Panel title="Anteprima deliverable">
          <div className="deliverable-preview">
            <div className="mini-process-diagram" />
            <div className="comment-box">
              <strong>Commenti e review</strong>
              <p>Aggiornare il flusso di validazione credito secondo nuovo policy.</p>
              <input placeholder="Aggiungi un commento..." />
            </div>
          </div>
        </Panel>
      </section>
    </div>
  );
}

function AnalysisTab({ project }: { project: Project }) {
  return (
    <div className="project-tab-page analysis-grid">
      <Panel title="Copertura dati">
        <MetricStack items={[
          ["Evidenze raccolte", String(projectEvidenceCount(project))],
          ["Fonti progetto", String(project.processItems.length * 2)],
          ["Processi validati", String(project.processItems.filter((p) => p.readiness >= 70).length)],
        ]} />
      </Panel>
      <Panel title="Qualita del perimetro">
        <MetricStack items={[
          ["Readiness media", `${averageReadiness(project)}%`],
          ["Problemi aperti", String(projectIssueCount(project))],
          ["Decisioni pendenti", String(projectDecisionRequests(project).length)],
        ]} />
      </Panel>
      <Panel title="Sintesi analitica">
        <p className="panel-copy">
          Il progetto ha una base operativa coerente, ma richiede maggiore copertura su evidenze,
          owner e KPI per chiudere la fase corrente senza ambiguita.
        </p>
      </Panel>
    </div>
  );
}

function IssuesTab({ project }: { project: Project }) {
  const issues = projectIssues(project);
  const selected = issues[0];

  return (
    <div className="project-tab-page issues-layout">
      <div className="issues-main">
        <section className="issue-kpi-grid">
          <IssueMetric title="Problemi critici" value="12" note="di cui 5 non mitigati" tone="danger" />
          <IssueMetric title="Opportunita ad alto impatto" value="8" note="di cui 4 non avviate" tone="success" />
          <IssueMetric title="Raccomandazioni in review" value="6" note="di 14 totali" tone="warning" />
        </section>
        <WorkspaceToolbar searchPlaceholder="Cerca per titolo, descrizione, tag...">
          <button type="button">Tipo: Tutti v</button>
          <button type="button">Impatto: Tutti v</button>
          <button type="button">Priorita: Tutti v</button>
          <button type="button">Stato: Tutti v</button>
          <button type="button">Processo: Tutti v</button>
        </WorkspaceToolbar>
        <table className="enterprise-table">
          <thead>
            <tr>
              <th>Titolo</th>
              <th>Tipo</th>
              <th>Impatto</th>
              <th>Priorita</th>
              <th>Processo collegato</th>
              <th>Owner</th>
              <th>Stato</th>
            </tr>
          </thead>
          <tbody>
            {issues.map((issue, index) => (
              <tr key={issue.id} className={index === 0 ? "is-selected" : ""}>
                <td><strong className="table-link">{issue.title}</strong><span>{issue.subtitle}</span></td>
                <td><IssueTypeBadge type={issue.type} /></td>
                <td><StatusDot status={issue.impact === "Elevato" ? "A rischio" : "Bozza"} /> {issue.impact}</td>
                <td><StatusBadge tone={issue.priority === "Alta" ? "danger" : "warning"}>{issue.priority}</StatusBadge></td>
                <td><span className="table-link">{issue.linkedProcess}</span></td>
                <td><OwnerCell owner={issue.owner} /></td>
                <td><StatusPill label={issue.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <IssueDetailDrawer issue={selected} />
    </div>
  );
}

function RecommendationsTab({ project }: { project: Project }) {
  const issues = projectIssues(project).filter((issue) => issue.type === "Raccomandazione" || issue.type === "Opportunita");

  return (
    <div className="project-tab-page">
      <section className="recommendation-grid">
        {issues.map((issue) => (
          <article key={issue.id} className="recommendation-card">
            <StatusBadge tone={issue.type === "Opportunita" ? "success" : "warning"}>{issue.type}</StatusBadge>
            <h3>{issue.title}</h3>
            <p>{issue.subtitle}</p>
            <footer>
              <OwnerCell owner={issue.owner} />
              <button type="button">Apri</button>
            </footer>
          </article>
        ))}
      </section>
    </div>
  );
}

function DocumentsTab({ project, sources }: { project: Project; sources: ProjectSource[] }) {
  const rows = sources.length > 0
    ? sources.map((source) => [source.name, source.type, source.meta, "Collegata"])
    : (project.deliverables.length ? project.deliverables : ["Blueprint funzionale", "Piano implementazione", "Report stato avanzamento"]).map((item) => [item, "Documento", project.name, "Bozza"]);

  return (
    <div className="project-tab-page">
      <WorkspaceToolbar searchPlaceholder="Cerca documenti...">
        <button type="button">Tipo v</button>
        <button type="button">Stato v</button>
        <button type="button">Owner v</button>
      </WorkspaceToolbar>
      <Panel title="Documenti e fonti">
        <CompactRows rows={rows} />
      </Panel>
    </div>
  );
}

function TeamTab({ project }: { project: Project }) {
  return (
    <div className="project-tab-page">
      <Panel title="Team e stakeholder">
        <CompactRows rows={projectTeam(project).map((member) => [member.name, member.role, member.company, member.involvement])} />
      </Panel>
    </div>
  );
}

function SettingsTab({ project }: { project: Project }) {
  return (
    <div className="project-tab-page settings-grid">
      <Panel title="Proprieta progetto">
        <EditableFields rows={[
          ["Nome progetto", project.name],
          ["Cliente", project.client],
          ["Fase", project.phase],
          ["Stato", project.status],
          ["Scadenza", projectDueDate(project)],
        ]} />
      </Panel>
      <Panel title="Governance">
        <EditableFields rows={[
          ["Owner", project.processItems[0]?.owner || "Da assegnare"],
          ["Processi in scope", String(project.processes || project.processItems.length)],
          ["Ultima revisione", "15/04/2024"],
        ]} />
      </Panel>
    </div>
  );
}

function ProcessTable({
  project,
  onOpenProcess,
}: {
  project: Project;
  onOpenProcess: (processId: string) => void;
}) {
  return (
    <table className="enterprise-table process-table">
      <thead>
        <tr>
          <th>Processo</th>
          <th>Tipo</th>
          <th>Area aziendale</th>
          <th>Owner</th>
          <th>Completezza</th>
          <th>Evidenze</th>
          <th>Problemi aperti</th>
          <th>Stato</th>
          <th>Ultimo aggiornamento</th>
        </tr>
      </thead>
      <tbody>
        {project.processItems.map((process, index) => (
          <tr key={process.id} onClick={() => onOpenProcess(process.id)}>
            <td><strong className="table-link">{process.name}</strong></td>
            <td><StatusBadge tone={processType(process) === "Core" ? "success" : processType(process) === "Management" ? "warning" : "draft"}>{processType(process)}</StatusBadge></td>
            <td>{processArea(process)}</td>
            <td><OwnerCell owner={process.owner} /></td>
            <td><ProgressBar value={process.readiness} label={`${process.readiness}%`} /></td>
            <td>{processEvidence(process)}</td>
            <td><span className={processOpenIssues(process) > 0 ? "danger-number" : ""}>{processOpenIssues(process)}</span></td>
            <td><StatusPill label={processStatusLabel(process)} /></td>
            <td>{processLastUpdated(index)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ProcessDetailDrawer({
  process,
  onOpenProcess,
}: {
  process: ProjectProcess | null;
  onOpenProcess: (processId: string) => void;
}) {
  if (!process) {
    return (
      <aside className="process-detail-drawer">
        <p>Seleziona un processo.</p>
      </aside>
    );
  }

  return (
    <aside className="process-detail-drawer" aria-label="Dettagli processo">
      <header className="drawer-title">
        <div>
          <p className="badge-soft">Processo {processType(process).toLowerCase()}</p>
          <h3>{process.name}</h3>
        </div>
        <button type="button" aria-label="Chiudi dettaglio">x</button>
      </header>

      <dl className="drawer-definition-list">
        <div><dt>Owner</dt><dd><OwnerCell owner={process.owner} /></dd></div>
        <div><dt>Area aziendale</dt><dd>{processArea(process)}</dd></div>
        <div><dt>Tipo processo</dt><dd>{processType(process)}</dd></div>
        <div><dt>Ultimo aggiornamento</dt><dd>30/04/2024</dd></div>
      </dl>

      <section className="drawer-section">
        <h4>Descrizione</h4>
        <p>Gestisce il ciclo operativo del processo, assicurando chiarezza su dati, responsabilita e soddisfazione degli stakeholder.</p>
      </section>

      <section className="drawer-section">
        <h4>Perimetro</h4>
        <div className="tag-cloud">
          <span>Vendite</span>
          <span>Fatturazione</span>
          <span>Logistica</span>
          <span>CRM</span>
        </div>
      </section>

      <section className="drawer-section">
        <div className="drawer-section-heading">
          <h4>Completezza processo</h4>
          <strong>{process.readiness}%</strong>
        </div>
        <ProgressBar value={process.readiness} />
      </section>

      <button type="button" className="enterprise-primary-button full-width" onClick={() => onOpenProcess(process.id)}>
        Apri workspace processo
      </button>
      <button type="button" className="secondary-full-button">Esporta mappa</button>
    </aside>
  );
}

function IssueDetailDrawer({ issue }: { issue: ProjectIssue }) {
  return (
    <aside className="issue-detail-drawer" aria-label="Dettaglio elemento">
      <header className="drawer-title">
        <div>
          <h3>{issue.title}</h3>
          <p>{issue.subtitle}</p>
        </div>
        <button type="button" aria-label="Chiudi dettaglio">x</button>
      </header>
      <dl className="drawer-definition-list">
        <div><dt>Tipo</dt><dd><IssueTypeBadge type={issue.type} /></dd></div>
        <div><dt>Priorita</dt><dd><StatusBadge tone="danger">{issue.priority}</StatusBadge></dd></div>
        <div><dt>Impatto</dt><dd>{issue.impact}</dd></div>
        <div><dt>Stato</dt><dd><StatusPill label={issue.status} /></dd></div>
        <div><dt>Processo collegato</dt><dd><span className="table-link">{issue.linkedProcess}</span></dd></div>
        <div><dt>Owner</dt><dd><OwnerCell owner={issue.owner} /></dd></div>
      </dl>
      <section className="drawer-section">
        <h4>Descrizione</h4>
        <p>Lo stato operativo non e visibile lungo tutto il ciclo. Le informazioni sono distribuite tra sistemi e aggiornamenti non real-time.</p>
      </section>
      <section className="drawer-section">
        <h4>Evidenze collegate</h4>
        <ul className="drawer-list">
          <li><span>Analisi gap sistemi</span><em>15/04/2024</em></li>
          <li><span>Mappatura flussi ordini</span><em>10/04/2024</em></li>
          <li><span>Interviste key user</span><em>08/04/2024</em></li>
        </ul>
      </section>
      <section className="drawer-section">
        <h4>Azioni suggerite</h4>
        <ul className="compact-bullet-list">
          <li>Integrare le fonti dati in una piattaforma unica.</li>
          <li>Definire KPI standard di tracking ordini.</li>
          <li>Coinvolgere IT e Operations per roadmap.</li>
        </ul>
      </section>
      <button type="button" className="enterprise-primary-button full-width">Modifica elemento</button>
    </aside>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="enterprise-panel">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function OwnerCell({ owner }: { owner: string }) {
  return (
    <span className="owner-cell">
      <span className="avatar-dot">{ownerInitials(owner)}</span>
      {owner}
    </span>
  );
}

function StatusDot({ status }: { status: string }) {
  const tone = status === "A rischio" || status === "In ritardo" ? "warning" : status === "Bozza" ? "neutral" : "success";
  return <span className={`status-dot status-dot-${tone}`} aria-hidden="true" />;
}

function StatusPill({ label }: { label: string }) {
  const tone = label.includes("review") || label.includes("Pianificato")
    ? "neutral"
    : label.includes("corso") || label.includes("Completato") || label.includes("Approvata")
      ? "success"
      : "warning";
  return <span className={`status-pill-ui status-pill-ui-${tone}`}>{label}</span>;
}

function IssueTypeBadge({ type }: { type: ProjectIssue["type"] }) {
  const tone = type === "Problema" ? "danger" : type === "Rischio" ? "warning" : type === "Opportunita" ? "success" : "draft";
  return <StatusBadge tone={tone}>{type}</StatusBadge>;
}

function IssueMetric({ title, value, note, tone }: { title: string; value: string; note: string; tone: "danger" | "success" | "warning" }) {
  return (
    <article className={`issue-metric issue-metric-${tone}`}>
      <span className="issue-metric-icon" aria-hidden="true">!</span>
      <div>
        <h3>{title}</h3>
        <strong>{value}</strong>
        <p>{note}</p>
      </div>
    </article>
  );
}

function KeyValueList({ items }: { items: Array<{ label: string; value: string }> }) {
  return (
    <ul className="key-value-list">
      {items.map((item) => (
        <li key={item.label}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </li>
      ))}
    </ul>
  );
}

function CompactRows({ rows }: { rows: string[][] }) {
  return (
    <table className="mini-table full">
      <tbody>
        {rows.map((row, index) => (
          <tr key={`${row.join("-")}-${index}`}>
            {row.map((cell) => <td key={cell}>{cell}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function EditableFields({ rows }: { rows: string[][] }) {
  return (
    <div className="editable-field-list">
      {rows.map(([label, value]) => (
        <label key={label}>
          <span>{label}</span>
          <input defaultValue={value} />
        </label>
      ))}
    </div>
  );
}

function MetricStack({ items }: { items: string[][] }) {
  return (
    <div className="metric-stack">
      {items.map(([label, value]) => (
        <div key={label}>
          <strong>{value}</strong>
          <span>{label}</span>
        </div>
      ))}
    </div>
  );
}

function RoadmapMini() {
  return (
    <div className="roadmap-mini">
      {["Analisi", "Progettazione", "Implementazione", "Go-live"].map((step, index) => (
        <div key={step} className={index < 2 ? "is-active" : ""}>
          <span />
          <strong>{step}</strong>
        </div>
      ))}
    </div>
  );
}

function ActivityList({ project }: { project: Project }) {
  return (
    <ul className="activity-list">
      {projectActivities(project).slice(0, 4).map((activity) => (
        <li key={activity.id}>
          <span>{activity.start}</span>
          <strong>{activity.name}</strong>
          <em>{activity.owner}</em>
        </li>
      ))}
    </ul>
  );
}

function averageReadiness(project: Project) {
  if (project.processItems.length === 0) return 0;
  return Math.round(project.processItems.reduce((total, process) => total + process.readiness, 0) / project.processItems.length);
}
