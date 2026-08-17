import React, { useMemo, useState } from "react";
import { StatusBadge, WorkspacePage, WorkspaceTable, WorkspaceToolbar } from "../../components/workspace";

type DocumentItem = {
  id: string;
  name: string;
  type: string;
  project: string;
  version: string;
  updated: string;
  status: "Pubblicato" | "Bozza" | "Da validare" | "Consegnato";
};

const documents: DocumentItem[] = [];
const exports: string[] = [];
const versions: string[] = [];
const shared: string[] = [];

export const ArchivePage: React.FC = () => {
  const [search, setSearch] = useState("");

  const visibleDocuments = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return documents;
    return documents.filter((document) =>
      [document.name, document.type, document.project, document.status].some((value) =>
        value.toLowerCase().includes(query)
      )
    );
  }, [search]);

  return (
    <WorkspacePage
      eyebrow="Archivio"
      title="Archivio"
      description="Documenti, versioni, esportazioni e deliverable di progetto."
      split
      sidePanel={<ArchiveSidePanel />}
    >
      <WorkspaceToolbar
        searchValue={search}
        searchPlaceholder="Cerca archivio..."
        onSearchChange={setSearch}
      >
        <button type="button">Tipo: tutti</button>
        <button type="button">Stato: tutti</button>
        <button type="button">Periodo: tutti</button>
      </WorkspaceToolbar>

      <WorkspaceTable columns={["Nome", "Tipo", "Cliente / progetto", "Versione", "Aggiornato", "Stato"]}>
        {visibleDocuments.length === 0 && (
          <tr>
            <td colSpan={6}>Nessun documento presente. Aggiungilo dalla chat agente.</td>
          </tr>
        )}
        {visibleDocuments.map((document) => (
          <tr key={document.id}>
            <td><strong>{document.name}</strong></td>
            <td>{document.type}</td>
            <td>{document.project}</td>
            <td>{document.version}</td>
            <td>{document.updated}</td>
            <td><StatusBadge tone={toneForDocument(document.status)}>{document.status}</StatusBadge></td>
          </tr>
        ))}
      </WorkspaceTable>
    </WorkspacePage>
  );
};

function ArchiveSidePanel() {
  return (
    <aside className="workspace-side-panel">
      <p className="product-eyebrow">Archivio</p>
      <h3>Attivita recenti</h3>

      <section className="side-panel-section">
        <h4>Esportazioni</h4>
        {exports.length === 0 ? <p>Nessuna esportazione.</p> : <ul>{exports.map((item) => <li key={item}>{item}</li>)}</ul>}
      </section>

      <section className="side-panel-section">
        <h4>Versioni</h4>
        {versions.length === 0 ? <p>Nessuna versione.</p> : <ul>{versions.map((item) => <li key={item}>{item}</li>)}</ul>}
      </section>

      <section className="side-panel-section">
        <h4>Condivisi</h4>
        {shared.length === 0 ? <p>Nessun documento condiviso.</p> : <ul>{shared.map((item) => <li key={item}>{item}</li>)}</ul>}
      </section>
    </aside>
  );
}

function toneForDocument(status: DocumentItem["status"]) {
  if (status === "Pubblicato" || status === "Consegnato") return "success";
  if (status === "Da validare") return "warning";
  return "draft";
}
