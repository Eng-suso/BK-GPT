import React, { useCallback, useEffect, useMemo, useState } from "react";
import { WorkspacePage } from "../../components/workspace";
import { apiClientsSchema, apiProjectsSchema, toClient, toProject } from "../../contracts/workspace";
import type { Client } from "../../contracts/workspace";
import type { Project } from "../projects/projectData";
import { API_BASE } from "../../lib/api";
import { onWorkspaceChanged } from "../../lib/workspaceEvents";

const workspaces = [
  {
    title: "Consulente",
    focus: "Chat generale",
    note: "Conversazioni trasversali e contesto di lavoro.",
  },
  {
    title: "Progetti",
    focus: "Chat progetto",
    note: "Fonti, decisioni, milestone e deliverable.",
  },
  {
    title: "Processi",
    focus: "Chat processo + canvas",
    note: "Riepilogo, BPMN e proprieta operative.",
  },
];

export const HomePage: React.FC = () => {
  const [clients, setClients] = useState<Client[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");

  const loadWorkspace = useCallback(async () => {
    try {
      const [clientsRes, projectsRes] = await Promise.all([
        fetch(`${API_BASE}/v1/workspace/clients`, { cache: "no-store" }),
        fetch(`${API_BASE}/v1/workspace/projects`, { cache: "no-store" }),
      ]);

      if (!clientsRes.ok || !projectsRes.ok) {
        setLoadState("error");
        return;
      }

      const [clientsJson, projectsJson] = await Promise.all([
        clientsRes.json(),
        projectsRes.json(),
      ]);

      setClients(apiClientsSchema.parse(clientsJson).map(toClient));
      setProjects(apiProjectsSchema.parse(projectsJson).map(toProject));
      setLoadState("ready");
    } catch (error) {
      console.error(error);
      setLoadState("error");
    }
  }, []);

  useEffect(() => {
    let isMounted = true;

    async function init() {
      await Promise.resolve();
      if (isMounted) {
        void loadWorkspace();
      }
    }

    void init();
    const unsubscribe = onWorkspaceChanged(() => {
      void loadWorkspace();
    });

    return () => {
      isMounted = false;
      unsubscribe();
    };
  }, [loadWorkspace]);

  const processCount = useMemo(
    () => projects.reduce((total, project) => total + project.processes, 0),
    [projects],
  );

  const metrics = [
    { label: "Clienti", value: String(clients.length), note: "Creati dall'agente" },
    { label: "Progetti", value: String(projects.length), note: "Collegati al workspace" },
    { label: "Processi", value: String(processCount), note: "Da modellare nel canvas" },
  ];

  return (
    <WorkspacePage
      eyebrow="Panoramica"
      title="Home"
      description="Panoramica operativa di clienti, progetti e processi presenti nel workspace."
    >
      <div className="metric-grid">
        {metrics.map((metric) => (
          <article key={metric.label} className="workspace-card metric-card">
            <span>{metric.label}</span>
            <strong>{loadState === "loading" ? "-" : metric.value}</strong>
            <p>{loadState === "error" ? "Backend workspace non disponibile" : metric.note}</p>
          </article>
        ))}
      </div>

      <div className="metric-grid">
        {workspaces.map((workspace) => (
          <article key={workspace.title} className="workspace-card metric-card">
            <span>{workspace.title}</span>
            <strong>{workspace.focus}</strong>
            <p>{workspace.note}</p>
          </article>
        ))}
      </div>

      <div className="workspace-two-column">
        <section className="workspace-card">
          <div className="section-heading">
            <h3>Progetti</h3>
          </div>
          <WorkspaceList
            emptyLabel="Nessun progetto presente."
            items={projects.map((project) => ({
              title: project.name,
              meta: `${project.client} - ${project.phase}`,
              status: project.status,
            }))}
          />
        </section>

        <section className="workspace-card">
          <div className="section-heading">
            <h3>Clienti</h3>
          </div>
          <WorkspaceList
            emptyLabel="Nessun cliente presente."
            items={clients.map((client) => ({
              title: client.name,
              meta: client.nextActivity,
              status: client.status,
            }))}
          />
        </section>
      </div>
    </WorkspacePage>
  );
};

function WorkspaceList({
  emptyLabel,
  items,
}: {
  emptyLabel: string;
  items: Array<{ title: string; meta: string; status: string }>;
}) {
  if (items.length === 0) {
    return <p className="side-note">{emptyLabel}</p>;
  }

  return (
    <ul className="compact-list">
      {items.map((item) => (
        <li key={`${item.title}-${item.status}`}>
          <div>
            <strong>{item.title}</strong>
            <span>{item.meta}</span>
          </div>
          <em>{item.status}</em>
        </li>
      ))}
    </ul>
  );
}
