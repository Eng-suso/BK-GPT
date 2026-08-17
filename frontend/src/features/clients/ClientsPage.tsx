import React, { useEffect, useMemo, useState } from "react";
import { StatusBadge, WorkspacePage, WorkspaceTable, WorkspaceToolbar } from "../../components/workspace";
import { apiClientsSchema, toClient } from "../../contracts/workspace";
import type { Client } from "../../contracts/workspace";
import { API_BASE } from "../../lib/api";
import { onWorkspaceChanged } from "../../lib/workspaceEvents";

export const ClientsPage: React.FC = () => {
  const [search, setSearch] = useState("");
  const [clients, setClients] = useState<Client[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    let isMounted = true;

    async function loadClients() {
      try {
        const res = await fetch(`${API_BASE}/v1/workspace/clients`, { cache: "no-store" });

        if (!res.ok) {
          if (isMounted) setLoadState("error");
          return;
        }

        const data = await res.json();
        const parsed = apiClientsSchema.parse(data).map(toClient);

        if (isMounted) {
          setClients(parsed);
          setSelectedId((current) => current || parsed[0]?.id || "");
          setLoadState("ready");
        }
      } catch (error) {
        console.error(error);
        if (isMounted) setLoadState("error");
      }
    }

    void loadClients();
    const unsubscribe = onWorkspaceChanged(loadClients);

    return () => {
      isMounted = false;
      unsubscribe();
    };
  }, []);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return clients;
    return clients.filter((client) =>
      [client.name, client.sector, client.owner, client.contact].some((value) =>
        value.toLowerCase().includes(query)
      )
    );
  }, [clients, search]);

  const selected = clients.find((client) => client.id === selectedId) ?? filtered[0];

  return (
    <WorkspacePage
      eyebrow="Anagrafiche"
      title="Clienti"
      description="Clienti, referenti, processi collegati e prossime attivita operative."
      split
      sidePanel={<ClientDetailPanel client={selected} />}
    >
      <WorkspaceToolbar
        searchValue={search}
        searchPlaceholder="Cerca clienti..."
        onSearchChange={setSearch}
      >
        <button type="button">Stato: tutti</button>
        <button type="button">Owner: tutti</button>
        <button type="button">Settore: tutti</button>
      </WorkspaceToolbar>

      <WorkspaceTable columns={["Cliente", "Stato", "Progetti", "Prossima attivita", "Owner"]}>
        {loadState === "loading" && (
          <tr>
            <td colSpan={5}>Caricamento clienti...</td>
          </tr>
        )}
        {loadState === "error" && (
          <tr>
            <td colSpan={5}>Backend workspace non disponibile.</td>
          </tr>
        )}
        {loadState === "ready" && filtered.length === 0 && (
          <tr>
            <td colSpan={5}>Nessun cliente presente. Crealo dalla chat agente.</td>
          </tr>
        )}
        {filtered.map((client) => (
          <tr
            key={client.id}
            className={selected?.id === client.id ? "is-selected" : ""}
            onClick={() => setSelectedId(client.id)}
          >
            <td>
              <strong>{client.name}</strong>
              <span>{client.sector}</span>
            </td>
            <td><StatusBadge tone={toneForClient(client.status)}>{client.status}</StatusBadge></td>
            <td>{client.projects}</td>
            <td>{client.nextActivity}</td>
            <td>{client.owner}</td>
          </tr>
        ))}
      </WorkspaceTable>
    </WorkspacePage>
  );
};

function ClientDetailPanel({ client }: { client?: Client }) {
  if (!client) return null;

  return (
    <aside className="workspace-side-panel">
      <p className="product-eyebrow">Dettaglio</p>
      <h3>{client.name}</h3>
      <dl>
        <div><dt>Settore</dt><dd>{client.sector}</dd></div>
        <div><dt>Stato</dt><dd>{client.status}</dd></div>
        <div><dt>Progetti attivi</dt><dd>{client.projects}</dd></div>
        <div><dt>Responsabile</dt><dd>{client.owner}</dd></div>
      </dl>

      <section className="side-panel-section">
        <h4>Referente</h4>
        <p>{client.contact}</p>
      </section>

      <section className="side-panel-section">
        <h4>Processi attivi</h4>
        <ul>
          {client.processes.map((process) => <li key={process}>{process}</li>)}
        </ul>
      </section>

      <section className="side-panel-section">
        <h4>Documenti recenti</h4>
        <ul>
          {client.documents.map((document) => <li key={document}>{document}</li>)}
        </ul>
      </section>

      <p className="side-note">{client.nextActivity}</p>
    </aside>
  );
}

function toneForClient(status: Client["status"]) {
  if (status === "Attivo") return "success";
  if (status === "Da seguire") return "warning";
  return "draft";
}
