import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import "@/lib/i18n";

const http = vi.fn();
const httpList = vi.fn();

vi.mock("@/lib/http", async () => {
  const actual = await vi.importActual<typeof import("@/lib/http")>("@/lib/http");
  return {
    ...actual,
    http: (path: string, options?: unknown) => http(path, options),
    httpList: (path: string, options?: unknown) => httpList(path, options),
  };
});

const { ClientDetailPage } = await import("./ClientDetailPage");

const ESAOTE = {
  id: "esaote",
  name: "Esaote",
  sector: "Medicale",
  status: "Attivo",
  projects: 2,
  next_activity: "",
  owner: "Sohayb",
  contact: "",
  processes: [],
  documents: [],
  archived_at: null,
  archive_reason: null,
};

const POLICY = {
  id: "src-policy",
  project_id: null,
  client_id: "esaote",
  process_id: null,
  name: "policy-acquisti-gruppo.pdf",
  type: "File",
  meta: "",
  roles: ["policy"],
  retention: "persistent",
  scopes: [],
  status: "approved",
  byte_size: 1800,
  content_hash: "h",
  mime_type: "application/pdf",
  acquisition_status: "done",
  acquisition_error: null,
};

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/clients/:clientId" element={<ClientDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  http.mockReset();
  httpList.mockReset();
});

describe("ClientDetailPage", () => {
  it("mostra il cliente e le fonti che valgono per tutti i suoi progetti", async () => {
    httpList.mockResolvedValue({ rows: [ESAOTE], total: 1 });
    http.mockImplementation((path: string) =>
      path === "/v1/workspace/clients/esaote/sources" ? Promise.resolve([POLICY]) : Promise.resolve(null),
    );

    renderAt("/clients/esaote");

    expect(await screen.findByRole("heading", { name: "Esaote", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Fonti del cliente" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /policy-acquisti-gruppo\.pdf/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /progetti del cliente/i })).toBeInTheDocument();
  });

  it("un cliente che non c'e' lo dice, senza offrire di riprovare", async () => {
    httpList.mockResolvedValue({ rows: [ESAOTE], total: 1 });
    http.mockResolvedValue([]);

    renderAt("/clients/sparito");

    expect(await screen.findByText("Cliente non trovato")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /riprova/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Torna ai clienti" })).toBeInTheDocument();
  });
});
