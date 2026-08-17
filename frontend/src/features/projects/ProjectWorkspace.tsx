import React from "react";
import {
  apiProjectDecisionsSchema,
  apiProjectSourcesSchema,
  toProjectDecision,
  toProjectSource,
} from "../../contracts/workspace";
import type { ProjectDecision, ProjectSource } from "../../contracts/workspace";
import { API_BASE } from "../../lib/api";
import { ChatExperience } from "../chat/ChatExperience";
import { ProcessWorkspace } from "../process/ProcessWorkspace";
import type { Project } from "./projectData";

type ProjectWorkspaceProps = {
  project: Project;
  onBack: () => void;
};

type ProjectPanelTab = "overview" | "processes" | "sources" | "decisions";

const panelTabs: Array<{ id: ProjectPanelTab; label: string }> = [
  { id: "overview", label: "Sintesi" },
  { id: "processes", label: "Processi" },
  { id: "sources", label: "Fonti" },
  { id: "decisions", label: "Decisioni" },
];

export const ProjectWorkspace: React.FC<ProjectWorkspaceProps> = ({ project, onBack }) => {
  const [selectedProcessId, setSelectedProcessId] = React.useState<string | null>(null);
  const [activePanelTab, setActivePanelTab] = React.useState<ProjectPanelTab>("overview");
  const [sources, setSources] = React.useState<ProjectSource[]>([]);
  const [decisions, setDecisions] = React.useState<ProjectDecision[]>([]);
  const selectedProcess =
    project.processItems.find((process) => process.id === selectedProcessId) ?? null;

  React.useEffect(() => {
    let isMounted = true;

    async function loadProjectContext() {
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
        if (isMounted) {
          setSources([]);
          setDecisions([]);
        }
      }
    }

    setSources([]);
    setDecisions([]);
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
    <section className="project-workspace">
      <header className="project-workspace-header">
        <div className="project-title-group">
          <button type="button" className="project-back-button" onClick={onBack}>
            Indietro
          </button>
          <div>
            <p className="product-eyebrow">{project.client}</p>
            <h2>{project.name}</h2>
          </div>
        </div>
        <span className={`project-status project-status-${statusClass(project.status)}`}>
          {project.status}
        </span>
      </header>

      <div className="project-workspace-grid">
        <section className="project-chat-panel" aria-label="Chat progetto">
          <ChatExperience
            chrome="panel"
            layout="embedded"
            scope={{
              type: "project",
              projectId: project.id,
              projectName: project.name,
            }}
          />
        </section>

        <aside className="project-context-panel" aria-label="Contesto progetto">
          <div className="project-context-header">
            <div>
              <p className="product-eyebrow">Contesto</p>
              <h3>Progetto</h3>
            </div>
            <span>{project.progress}%</span>
          </div>

          <div className="project-context-tabs" role="tablist" aria-label="Viste progetto">
            {panelTabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={activePanelTab === tab.id ? "is-active" : ""}
                onClick={() => setActivePanelTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="project-context-body">
            {activePanelTab === "overview" && <OverviewTab project={project} />}
            {activePanelTab === "processes" && (
              <ProcessesTab project={project} onSelectProcess={setSelectedProcessId} />
            )}
            {activePanelTab === "sources" && <SourcesTab project={project} sources={sources} />}
            {activePanelTab === "decisions" && (
              <DecisionsTab project={project} decisions={decisions} />
            )}
          </div>
        </aside>
      </div>
    </section>
  );
};

function OverviewTab({ project }: { project: Project }) {
  return (
    <div className="project-tab-content">
      <section className="project-panel">
        <h3>Stato</h3>
        <div className="project-progress project-progress-large">
          <span style={{ width: `${project.progress}%` }} />
        </div>
        <p className="project-muted">{project.progress}% completato</p>
      </section>

      <section className="project-panel">
        <h3>Prossimo step</h3>
        <p>{project.nextStep}</p>
      </section>

      <section className="project-panel">
        <h3>Focus operativo</h3>
        <p>
          Usare la chat progetto per allineare fonti, ipotesi e decisioni prima di
          entrare nel singolo processo.
        </p>
      </section>

      <section className="project-panel">
        <h3>Milestone</h3>
        <ul className="project-detail-list">
          {project.milestones.map((milestone) => (
            <li key={milestone}>
              <strong>{milestone}</strong>
              <span>Stato progetto</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function ProcessesTab({
  project,
  onSelectProcess,
}: {
  project: Project;
  onSelectProcess: (processId: string) => void;
}) {
  return (
    <div className="project-tab-content">
      <section className="project-panel">
        <h3>Processi</h3>
        <p>{project.processes} processi nel perimetro iniziale.</p>
        <ul className="process-preview-list">
          {project.processItems.map((process) => (
            <li key={process.id}>
              <button type="button" onClick={() => onSelectProcess(process.id)}>
                <span>
                  <strong>{process.name}</strong>
                  <small>{process.stage} - {process.status}</small>
                </span>
                <em>{process.readiness}%</em>
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function SourcesTab({ project, sources }: { project: Project; sources: ProjectSource[] }) {
  return (
    <div className="project-tab-content">
      <section className="project-panel">
        <h3>Fonti progetto</h3>
        <ul className="project-detail-list">
          {sources.length === 0 && (
            <li>
              <strong>Nessuna fonte presente</strong>
              <span>Le fonti saranno create dall'agente o caricate dal consulente.</span>
            </li>
          )}
          {sources.map((source) => (
            <li key={source.id}>
              <strong>{source.name}</strong>
              <span>{source.type} - {source.meta}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="project-panel">
        <h3>Deliverable</h3>
        <ul className="project-detail-list">
          {project.deliverables.map((deliverable) => (
            <li key={deliverable}>
              <strong>{deliverable}</strong>
              <span>Previsto nel progetto</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function DecisionsTab({
  project,
  decisions,
}: {
  project: Project;
  decisions: ProjectDecision[];
}) {
  return (
    <div className="project-tab-content">
      <section className="project-panel">
        <h3>Decisioni aperte</h3>
        <ul className="project-detail-list">
          {decisions.length === 0 && (
            <li>
              <strong>Nessuna decisione presente</strong>
              <span>Le decisioni saranno create dall'agente durante il lavoro.</span>
            </li>
          )}
          {decisions.map((decision) => (
            <li key={decision.id}>
              <strong>{decision.title}</strong>
              <span>{decision.owner} - {decision.status}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="project-panel">
        <h3>Punti aperti</h3>
        <ul className="project-detail-list">
          {project.openIssues.map((issue) => (
            <li key={issue}>
              <strong>{issue}</strong>
              <span>Da chiarire</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function statusClass(status: Project["status"]) {
  if (status === "A rischio") return "risk";
  if (status === "Bozza") return "draft";
  return "active";
}
