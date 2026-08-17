import React, { useMemo, useState } from "react";
import { StatusBadge, WorkspacePage, WorkspaceToolbar } from "../../components/workspace";

type ModelType = "Intervista" | "Processo" | "Deliverable" | "Report" | "Checklist" | "Workshop";

type ModelItem = {
  id: string;
  name: string;
  type: ModelType;
  description: string;
  updated: string;
  usage: number;
  status: "Attivo" | "Bozza" | "Da rivedere";
};

const tabs: Array<ModelType | "Tutti"> = [
  "Tutti",
  "Intervista",
  "Processo",
  "Deliverable",
  "Report",
  "Checklist",
  "Workshop",
];

const models: ModelItem[] = [
  {
    id: "interview-discovery",
    name: "Discovery intervista stakeholder",
    type: "Intervista",
    description: "Traccia per raccogliere contesto, pain point e vincoli.",
    updated: "9 giu 2025",
    usage: 18,
    status: "Attivo",
  },
  {
    id: "process-p2p",
    name: "Procure-to-Pay",
    type: "Processo",
    description: "Schema operativo per analisi AS-IS e disegno TO-BE.",
    updated: "8 giu 2025",
    usage: 12,
    status: "Attivo",
  },
  {
    id: "project-plan",
    name: "Piano di progetto",
    type: "Deliverable",
    description: "Struttura iniziale per milestones, rischi e responsabilita.",
    updated: "7 giu 2025",
    usage: 9,
    status: "Da rivedere",
  },
  {
    id: "kpi-report",
    name: "Report stato avanzamento",
    type: "Report",
    description: "Sintesi periodica per avanzamento, rischi e decisioni.",
    updated: "6 giu 2025",
    usage: 14,
    status: "Attivo",
  },
  {
    id: "validation-checklist",
    name: "Validazione processo",
    type: "Checklist",
    description: "Controlli per completezza, evidenze, ruoli e varianti.",
    updated: "5 giu 2025",
    usage: 21,
    status: "Attivo",
  },
  {
    id: "workshop-tobe",
    name: "Workshop TO-BE",
    type: "Workshop",
    description: "Agenda per co-design del processo futuro.",
    updated: "3 giu 2025",
    usage: 7,
    status: "Bozza",
  },
];

export const ModelsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]>("Tutti");
  const [search, setSearch] = useState("");

  const visibleModels = useMemo(() => {
    const query = search.trim().toLowerCase();
    return models.filter((model) => {
      const matchesTab = activeTab === "Tutti" || model.type === activeTab;
      const matchesSearch =
        !query ||
        [model.name, model.type, model.description].some((value) =>
          value.toLowerCase().includes(query)
        );
      return matchesTab && matchesSearch;
    });
  }, [activeTab, search]);

  return (
    <WorkspacePage
      eyebrow="Libreria"
      title="Modelli"
      description="Template riutilizzabili per interviste, processi e deliverable."
      split
      sidePanel={<ModelsSidePanel />}
    >
      <WorkspaceToolbar
        searchValue={search}
        searchPlaceholder="Cerca modelli..."
        onSearchChange={setSearch}
      >
        <div className="workspace-tabs" role="tablist" aria-label="Categorie modelli">
          {tabs.map((tab) => (
            <button
              key={tab}
              type="button"
              className={activeTab === tab ? "is-active" : ""}
              onClick={() => setActiveTab(tab)}
            >
              {tab}
            </button>
          ))}
        </div>
      </WorkspaceToolbar>

      <div className="model-card-grid">
        {visibleModels.map((model) => (
          <article key={model.id} className="workspace-card model-card">
            <div>
              <StatusBadge tone={toneForModel(model.status)}>{model.type}</StatusBadge>
              <h3>{model.name}</h3>
              <p>{model.description}</p>
            </div>
            <footer>
              <span>{model.updated}</span>
              <strong>{model.usage} utilizzi</strong>
            </footer>
          </article>
        ))}
      </div>
    </WorkspacePage>
  );
};

function ModelsSidePanel() {
  const categoryCounts = tabs
    .filter((tab): tab is ModelType => tab !== "Tutti")
    .map((type) => ({
      type,
      count: models.filter((model) => model.type === type).length,
    }));
  const recent = [...models].sort((a, b) => b.usage - a.usage).slice(0, 3);

  return (
    <aside className="workspace-side-panel">
      <p className="product-eyebrow">Panoramica</p>
      <h3>Categorie</h3>
      <ul className="side-panel-list">
        {categoryCounts.map((category) => (
          <li key={category.type}>
            <span>{category.type}</span>
            <strong>{category.count}</strong>
          </li>
        ))}
      </ul>

      <section className="side-panel-section">
        <h4>Ultimi usati</h4>
        <ul>
          {recent.map((model) => (
            <li key={model.id}>{model.name}</li>
          ))}
        </ul>
      </section>
    </aside>
  );
}

function toneForModel(status: ModelItem["status"]) {
  if (status === "Attivo") return "success";
  if (status === "Da rivedere") return "warning";
  return "draft";
}
