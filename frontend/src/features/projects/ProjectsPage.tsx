import React, { useEffect, useMemo, useState } from "react";
import {
  ProgressBar,
  StatusBadge,
  WorkspaceTable,
  WorkspaceToolbar,
} from "../../components/workspace";
import { apiProjectsSchema, toProject } from "../../contracts/workspace";
import { API_BASE } from "../../lib/api";
import { onWorkspaceChanged } from "../../lib/workspaceEvents";
import { ProjectWorkspace } from "./ProjectWorkspace";
import type { Project } from "./projectData";
import {
  ownerInitials,
  projectDueDate,
  projectIssueCount,
  projectPhaseDetail,
} from "./projectUiData";

export const ProjectsPage: React.FC = () => {
  const [search, setSearch] = useState("");
  const [workspaceProjectId, setWorkspaceProjectId] = useState<string | null>(null);
  const [detailProjectId, setDetailProjectId] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const workspaceProject = projects.find((project) => project.id === workspaceProjectId) ?? null;
  const detailProject = projects.find((project) => project.id === detailProjectId) ?? projects[0] ?? null;

  useEffect(() => {
    let isMounted = true;

    async function loadProjects() {
      try {
        const res = await fetch(`${API_BASE}/v1/workspace/projects`, { cache: "no-store" });

        if (!res.ok) {
          if (isMounted) {
            setLoadState("error");
          }
          return;
        }

        const data = await res.json();

        let parsed: Project[];
        try {
          parsed = apiProjectsSchema.parse(data).map(toProject);
        } catch (parseError) {
          console.error("[ProjectsPage] Zod parsing failed:", parseError);
          console.error("[ProjectsPage] Raw API response:", JSON.stringify(data, null, 2));
          if (isMounted) {
            setLoadState("error");
          }
          return;
        }

        if (isMounted) {
          setProjects(parsed);
          setDetailProjectId((current) => current || parsed[0]?.id || null);
          setLoadState("ready");
        }
      } catch (error) {
        console.error(error);
        if (isMounted) {
          setLoadState("error");
        }
      }
    }

    void loadProjects();
    const unsubscribe = onWorkspaceChanged(loadProjects);

    return () => {
      isMounted = false;
      unsubscribe();
    };
  }, []);

  const visibleProjects = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return projects;
    return projects.filter((project) =>
      [project.name, project.client, project.phase, project.status].some((value) =>
        value.toLowerCase().includes(query)
      )
    );
  }, [projects, search]);

  if (workspaceProject) {
    return (
      <ProjectWorkspace
        project={workspaceProject}
        onBack={() => setWorkspaceProjectId(null)}
      />
    );
  }

  return (
    <section className="enterprise-page enterprise-page-with-drawer">
      <main className="enterprise-main">
        <div className="enterprise-breadcrumb">
          <span>Progetti</span>
          <span>Portafoglio progetti</span>
        </div>

        <header className="enterprise-page-header">
          <div>
            <h2>Progetti</h2>
            <p>Monitora lo stato del portafoglio progetti di consulenza e avanza con decisioni informate.</p>
          </div>
          <button type="button" className="enterprise-primary-button">
            Nuovo progetto
            <span aria-hidden="true">+</span>
          </button>
        </header>

        <WorkspaceToolbar
          searchValue={search}
          searchPlaceholder="Cerca progetti..."
          onSearchChange={setSearch}
        >
          <button type="button">Cliente v</button>
          <button type="button">Stato v</button>
          <button type="button">Fase v</button>
          <button type="button">Owner v</button>
          <button type="button">Altri filtri v</button>
          <button type="button" className="enterprise-reset-button">Ripristina filtri</button>
        </WorkspaceToolbar>

        <WorkspaceTable columns={["", "Progetto", "Cliente", "Fase corrente", "Owner", "Scadenza", "Stato", "Processi", "Avanzamento", ""]}>
          {loadState === "loading" && (
            <tr>
              <td colSpan={10}>Caricamento progetti...</td>
            </tr>
          )}
          {loadState === "error" && (
            <tr>
              <td colSpan={10}>Backend workspace non disponibile.</td>
            </tr>
          )}
          {loadState === "ready" && visibleProjects.length === 0 && (
            <tr>
              <td colSpan={10}>Nessun progetto presente. Crealo dalla chat agente.</td>
            </tr>
          )}
          {visibleProjects.map((project, index) => {
            const isSelected = project.id === detailProject?.id;

            return (
              <tr
                key={project.id}
                className={isSelected ? "is-selected" : ""}
                onClick={() => setDetailProjectId(project.id)}
              >
                <td><button type="button" className="favorite-button" aria-label="Preferito">*</button></td>
                <td>
                  <strong className="table-link">{project.name}</strong>
                  <span>{project.nextStep}</span>
                </td>
                <td>{project.client}</td>
                <td>
                  <strong>{project.phase}</strong>
                  <span>{projectPhaseDetail(project)}</span>
                </td>
                <td>
                  <span className="owner-cell">
                    <span className="avatar-dot">{ownerInitials(project.processItems[0]?.owner || "Marco Bianchi")}</span>
                    {project.processItems[0]?.owner || "Marco Bianchi"}
                  </span>
                </td>
                <td>{projectDueDate(project)}</td>
                <td><StatusBadge tone={toneForProject(project.status)}>{project.status}</StatusBadge></td>
                <td>{project.processes || project.processItems.length}</td>
                <td><ProgressBar value={project.progress} label={`${project.progress}%`} /></td>
                <td>
                  <button
                    type="button"
                    className="row-more-button"
                    aria-label={`Apri ${project.name}`}
                    onClick={(event) => {
                      event.stopPropagation();
                      setWorkspaceProjectId(project.id);
                    }}
                  >
                    {index === 0 ? "Apri" : "..."}
                  </button>
                </td>
              </tr>
            );
          })}
        </WorkspaceTable>

        <footer className="enterprise-table-footer">
          <span>Vista 1-10 di {Math.max(visibleProjects.length, projects.length)} progetti</span>
          <div className="pagination">
            <button type="button">{"<"}</button>
            <button type="button" className="is-active">1</button>
            <button type="button">2</button>
            <button type="button">{">"}</button>
            <button type="button">10 per pagina v</button>
          </div>
        </footer>
      </main>

      <ProjectPortfolioDrawer
        project={detailProject}
        onOpenProject={(projectId) => setWorkspaceProjectId(projectId)}
      />
    </section>
  );
};

function ProjectPortfolioDrawer({
  project,
  onOpenProject,
}: {
  project: Project | null;
  onOpenProject: (projectId: string) => void;
}) {
  if (!project) {
    return (
      <aside className="enterprise-drawer">
        <p className="drawer-empty">Seleziona un progetto per vedere il dettaglio.</p>
      </aside>
    );
  }

  const owner = project.processItems[0]?.owner || "Marco Bianchi";
  const issues = project.openIssues.length > 0 ? project.openIssues : [
    "Definizione requisiti integrazione",
    "Allineamento KPI di servizio",
    "Dati anagrafici incompleti",
  ];
  const deliverables = project.deliverables.length > 0 ? project.deliverables : [
    "Processo TO-BE",
    "Blueprint funzionale",
    "Piano di implementazione",
  ];

  return (
    <aside className="enterprise-drawer" aria-label="Riepilogo progetto">
      <header className="drawer-title">
        <div>
          <h3>{project.name}</h3>
          <p>{project.client}</p>
        </div>
        <button type="button" aria-label="Chiudi dettaglio">x</button>
      </header>

      <section className="drawer-section">
        <h4>Riepilogo progetto</h4>
        <dl className="drawer-definition-list">
          <div><dt>Fase corrente</dt><dd>{project.phase}</dd></div>
          <div><dt>Stato</dt><dd><StatusBadge tone={toneForProject(project.status)}>{project.status}</StatusBadge></dd></div>
          <div><dt>Owner</dt><dd>{owner}</dd></div>
          <div><dt>Scadenza</dt><dd>{projectDueDate(project)}</dd></div>
          <div><dt>Avanzamento</dt><dd><ProgressBar value={project.progress} label={`${project.progress}%`} /></dd></div>
          <div><dt>Processi in scope</dt><dd>{project.processes || project.processItems.length}</dd></div>
        </dl>
      </section>

      <DrawerList title="Milestone principali" items={project.milestones.slice(0, 5)} empty="Nessuna milestone definita." />
      <DrawerList title="Punti aperti" items={issues.slice(0, 4)} empty="Nessun punto aperto." dangerCount={projectIssueCount(project)} />
      <DrawerList title="Deliverable previsti" items={deliverables.slice(0, 4)} empty="Nessun deliverable previsto." />

      <section className="drawer-section">
        <h4>Azioni rapide</h4>
        <div className="quick-action-grid">
          <button type="button" onClick={() => onOpenProject(project.id)}>Apri roadmap</button>
          <button type="button">Aggiorna stato</button>
          <button type="button" onClick={() => onOpenProject(project.id)}>Apri processi</button>
          <button type="button">Nuovo punto aperto</button>
          <button type="button">Apri documenti</button>
          <button type="button">Registra decisione</button>
        </div>
      </section>
    </aside>
  );
}

function DrawerList({
  title,
  items,
  empty,
  dangerCount,
}: {
  title: string;
  items: string[];
  empty: string;
  dangerCount?: number;
}) {
  return (
    <section className="drawer-section">
      <div className="drawer-section-heading">
        <h4>{title}</h4>
        {typeof dangerCount === "number" ? <strong>{dangerCount}</strong> : <button type="button">...</button>}
      </div>
      {items.length === 0 ? (
        <p className="drawer-muted">{empty}</p>
      ) : (
        <ul className="drawer-list">
          {items.map((item, index) => (
            <li key={`${title}-${item}`}>
              <span>{item}</span>
              <em>{index < 2 ? "ok" : "open"}</em>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function toneForProject(status: Project["status"]) {
  if (status === "In corso") return "success";
  if (status === "A rischio") return "warning";
  return "draft";
}
