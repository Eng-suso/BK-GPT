import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { i18n } from "@/lib/i18n";
import { PeriodProvider } from "@/features/period/PeriodContext";

const http = vi.fn<(path: string) => Promise<unknown>>();

// Gli elenchi passano da `httpList` (B12: pagina con totale), il resto da `http`.
vi.mock("@/lib/http", () => ({
  http: (path: string) => http(path),
  httpList: async (path: string) => ({ rows: await http(path), total: null }),
}));

const { HomePage } = await import("./HomePage");

function project(overrides: Record<string, unknown> = {}) {
  return {
    id: "proj-1",
    client_id: "cli-1",
    client: "Esaote",
    name: "Riorganizzazione acquisti",
    objective: "",
    lead: null,
    start_date: "2026-01-10",
    end_date: "2026-09-30",
    phase: "Discovery",
    status: "In corso",
    progress: 40,
    processes: 2,
    process_items: [],
    next_step: "",
    milestones: [],
    open_issues: [],
    deliverables: [],
    archived_at: null,
    archive_reason: null,
    ...overrides,
  };
}

function backendReturns(projects: Record<string, unknown>[]) {
  http.mockImplementation(async (path) =>
    path.includes("/clients") ? [] : projects,
  );
}

function renderHome() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>
        <PeriodProvider>
          <MemoryRouter>{children}</MemoryRouter>
        </PeriodProvider>
      </QueryClientProvider>
    </I18nextProvider>
  );
  render(<HomePage />, { wrapper });
}

beforeAll(async () => {
  await i18n.changeLanguage("it");
  // "Quest'anno" dipende da quando gira il test: senza orologio fisso questo
  // file diventerebbe rosso il primo gennaio.
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(new Date(2026, 4, 20));
});

afterEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
});

afterAll(() => {
  vi.useRealTimers();
});

describe("HomePage", () => {
  it("counts every engagement when no period is chosen", async () => {
    backendReturns([
      project(),
      project({ id: "proj-2", name: "Chiuso nel 2020", start_date: "2020-01-01", end_date: "2020-06-30" }),
    ]);
    renderHome();

    // "Tutto il lavoro" e' il default: la home mostra quello che c'e'.
    expect(
      await screen.findByText("Riorganizzazione acquisti", {}, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(screen.getByText("Chiuso nel 2020")).toBeInTheDocument();
  });

  it("counts only the engagements the chosen period touches", async () => {
    window.localStorage.setItem("delir-period", "year");
    backendReturns([
      project(),
      project({ id: "proj-2", name: "Chiuso nel 2020", start_date: "2020-01-01", end_date: "2020-06-30" }),
    ]);
    renderHome();

    // Un numero accanto a un periodo deve essere di quel periodo: l'incarico
    // chiuso nel 2020 non entra in "quest'anno".
    expect(
      await screen.findByText("Riorganizzazione acquisti", {}, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Chiuso nel 2020")).not.toBeInTheDocument();
  });
});
