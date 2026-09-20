import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { setupUser } from "@/test/user";

import { i18n } from "@/lib/i18n";

// Il confine e' la risposta HTTP: il test passa anche dal contratto e dalla
// mappatura, non solo dal componente.
const http = vi.fn<(path: string) => Promise<unknown>>();

vi.mock("@/lib/http", () => ({ http: (path: string) => http(path) }));

const { GlobalSearchDialog } = await import("./GlobalSearchDialog");
const { hitHref } = await import("./api");

type ApiHit = {
  kind: "client" | "project" | "process" | "source";
  id: string;
  title: string;
  context: string;
  client_id: string | null;
  client_name: string | null;
  project_id: string | null;
  project_name: string | null;
  process_id: string | null;
  source_type: string | null;
};

function hit(overrides: Partial<ApiHit> = {}): ApiHit {
  return {
    kind: "process",
    id: "proc-1",
    title: "Ciclo passivo",
    context: "Esaote · Riorganizzazione acquisti · As-is",
    client_id: "cli-1",
    client_name: "Esaote",
    project_id: "proj-1",
    project_name: "Riorganizzazione acquisti",
    process_id: "proc-1",
    source_type: null,
    ...overrides,
  };
}

const backendReturns = (rows: ApiHit[]) =>
  http.mockImplementation(async (path) => {
    expect(path).toContain("/v1/workspace/search?");
    return rows;
  });

function renderDialog() {
  const onNavigate = vi.fn();
  const onOpenChange = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </I18nextProvider>
  );
  render(<GlobalSearchDialog open onOpenChange={onOpenChange} onNavigate={onNavigate} />, {
    wrapper,
  });
  return { onNavigate, onOpenChange };
}

beforeAll(async () => {
  await i18n.changeLanguage("it");
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("GlobalSearchDialog", () => {
  it("groups what it found, because one word can name three different things", async () => {
    const user = setupUser();
    backendReturns([
      hit({ kind: "client", id: "cli-1", title: "Esaote", context: "Biomedicale" }),
      hit({
        kind: "project",
        id: "proj-1",
        title: "Riorganizzazione acquisti",
        context: "Esaote · Discovery",
      }),
      hit(),
      hit({
        kind: "source",
        id: "src-1",
        title: "Intervista Neri",
        context: "Esaote · Riorganizzazione acquisti",
        source_type: "Intervista",
      }),
    ]);
    renderDialog();

    await user.type(screen.getByRole("combobox"), "esaote");

    const clients = await screen.findByRole("group", { name: "Clienti" }, { timeout: 5000 });
    expect(within(clients).getByRole("option", { name: /Esaote/ })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Processi" })).toBeInTheDocument();
    // Il tipo della fonte sta accanto al percorso: "Intervista" dice cos'e'
    // meglio del nome del file.
    expect(screen.getByText(/Intervista · Esaote/)).toBeInTheDocument();
  });

  it("opens the highlighted result with the keyboard and closes itself", async () => {
    const user = setupUser();
    backendReturns([
      hit({ kind: "client", id: "cli-1", title: "Esaote", context: "Biomedicale" }),
      hit(),
    ]);
    const { onNavigate, onOpenChange } = renderDialog();

    await user.type(screen.getByRole("combobox"), "esaote");
    await screen.findByRole("option", { name: /Ciclo passivo/ }, { timeout: 5000 });

    await user.keyboard("{ArrowDown}{Enter}");

    expect(onNavigate).toHaveBeenCalledWith("/projects/proj-1/processes/proc-1");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("does not ask the backend for one letter", async () => {
    const user = setupUser();
    backendReturns([]);
    renderDialog();

    await user.type(screen.getByRole("combobox"), "e");

    expect(await screen.findByText(/almeno 2 caratteri/i)).toBeInTheDocument();
    expect(http).not.toHaveBeenCalled();
  });

  it("separates 'nothing found' from 'the search failed'", async () => {
    const user = setupUser();
    http.mockRejectedValue(new Error("backend giu'"));
    renderDialog();

    await user.type(screen.getByRole("combobox"), "esaote");

    // Un guasto mostrato come lista vuota fa concludere che il cliente non
    // esiste, e il consulente lo ricrea.
    expect(await screen.findByText(/Ricerca non riuscita/, {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Riprova/ })).toBeInTheDocument();
  });
});

describe("hitHref", () => {
  const base = {
    id: "x",
    title: "Esaote",
    context: "",
    clientName: "Esaote",
    projectId: "proj-1",
    processId: "proc-1",
    sourceType: null,
  };

  it("takes a client to its projects, already filtered", () => {
    // Il cliente non ha una pagina propria: mandare all'elenco completo
    // sarebbe come non aver cercato.
    expect(hitHref({ ...base, kind: "client" })).toBe("/projects?f_client=Esaote");
  });

  it("opens a source on the tab where sources are read", () => {
    expect(hitHref({ ...base, kind: "source", title: "Intervista Neri" })).toBe(
      "/projects/proj-1?tab=sources",
    );
  });

  it("opens a project and a process where they live", () => {
    expect(hitHref({ ...base, kind: "project" })).toBe("/projects/proj-1");
    expect(hitHref({ ...base, kind: "process" })).toBe("/projects/proj-1/processes/proc-1");
  });
});
