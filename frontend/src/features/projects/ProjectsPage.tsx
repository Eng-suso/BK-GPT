import React, { useEffect, useMemo, useState } from "react";
import {
  ProgressBar,
  StatusBadge,
  WorkspacePage,
  WorkspaceTable,
  WorkspaceToolbar,
} from "../../components/workspace";
import { apiProjectsSchema, toProject } from "../../contracts/workspace";
import { API_BASE } from "../../lib/api";
import { onWorkspaceChanged } from "../../lib/workspaceEvents";
import { ProjectWorkspace } from "./ProjectWorkspace";
import type { Project } from "./projectData";

export const ProjectsPage: React.FC = () => {
  const [search, setSearch] = useState("");
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const selectedProject = projects.find((project) => project.id === selectedProjectId) ?? null;

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
        const parsed = apiProjectsSchema.parse(data).map(toProject);

        if (isMounted) {
          setProjects(parsed);
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

  if (selectedProject) {
    return (
      <ProjectWorkspace
        project={selectedProject}
        onBack={() => setSelectedProjectId(null)}
      />
    );
  }

  return (
    <WorkspacePage
      eyebrow="Portfolio"
      title="Progetti"
      description="Ingresso verso lo spazio progetto e lo spazio processo."
    >
      <WorkspaceToolbar
        searchValue={search}
        searchPlaceholder="Cerca progetti..."
        onSearchChange={setSearch}
      >
        <button type="button">Stato: tutti</button>
        <button type="button">Fase: tutte</button>
        <button type="button">Cliente: tutti</button>
      </WorkspaceToolbar>

      <WorkspaceTable columns={["Progetto", "Cliente", "Fase", "Stato", "Processi", "Avanzamento", ""]}>
        {loadState === "loading" && (
          <tr>
            <td colSpan={7}>Caricamento progetti...</td>
          </tr>
        )}
        {loadState === "error" && (
          <tr>
            <td colSpan={7}>Backend workspace non disponibile.</td>
          </tr>
        )}
        {loadState === "ready" && visibleProjects.length === 0 && (
          <tr>
            <td colSpan={7}>Nessun progetto presente. Crealo dalla chat agente.</td>
          </tr>
        )}
        {visibleProjects.map((project) => (
          <tr key={project.id}>
            <td>
              <strong>{project.name}</strong>
              <span>{project.nextStep}</span>
            </td>
            <td>{project.client}</td>
            <td>{project.phase}</td>
            <td><StatusBadge tone={toneForProject(project.status)}>{project.status}</StatusBadge></td>
            <td>{project.processes}</td>
            <td><ProgressBar value={project.progress} label={`${project.progress}%`} /></td>
            <td>
              <button
                type="button"
                className="project-table-open"
                onClick={() => setSelectedProjectId(project.id)}
              >
                Apri
              </button>
            </td>
          </tr>
        ))}
      </WorkspaceTable>
    </WorkspacePage>
  );
};

function toneForProject(status: Project["status"]) {
  if (status === "In corso") return "success";
  if (status === "A rischio") return "warning";
  return "draft";
}
