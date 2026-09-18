import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { setupUser } from "@/test/user";

import { i18n } from "@/lib/i18n";
import type { ApiModel } from "./api";

// Il confine e' la risposta HTTP, non la funzione di fetch: cosi' il test passa
// anche dal parsing del contratto e dalla mappatura verso la riga della lista.
const http = vi.fn<(path: string) => Promise<unknown>>();

vi.mock("@/lib/http", () => ({ http: (path: string) => http(path) }));

const { ModelsPage } = await import("./ModelsPage");
const { modelStage } = await import("./api");

const backendReturns = {
  mockResolvedValue: (rows: ApiModel[]) =>
    http.mockImplementation(async (path) => {
      expect(path).toBe("/v1/workspace/models");
      return rows;
    }),
  mockRejectedValue: (error: Error) => http.mockRejectedValue(error),
};

function model(overrides: Partial<ApiModel> = {}): ApiModel {
  return {
    bpmn_model_id: "bpmn-1",
    name: "Ciclo passivo",
    has_diagram: true,
    version_count: 3,
    last_saved_at: "2026-09-17T10:00:00Z",
    process_id: "proc-1",
    process_name: "Ciclo passivo",
    process_stage: "As-is",
    project_id: "proj-1",
    project_name: "Riorganizzazione acquisti",
    client_id: "cli-1",
    client_name: "Esaote",
    review_status: "pending",
    review_version: 2,
    readiness_score: 72,
    review_updated_at: "2026-09-16T10:00:00Z",
    conformance_verdict: "not_conformant",
    conformance_findings: 2,
    conformance_pending: false,
    ...overrides,
  };
}

/**
 * La prima riga della tabella, aspettata piu' del secondo di default.
 *
 * Il dato passa da query, parsing e tabella: da solo arriva in poche decine di
 * millisecondi, ma con la suite in parallelo (un jsdom per file) supera il
 * secondo e il rosso diceva "riga assente" mentre la riga arrivava. Cio' che si
 * verifica e' quale riga compare, non quanto in fretta.
 */
function findRow(name: RegExp): Promise<HTMLElement> {
  return screen.findByRole("row", { name }, { timeout: 5000 });
}

function Location(): React.JSX.Element {
  const location = useLocation();
  return <p data-testid="location">{`${location.pathname}${location.search}`}</p>;
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/models"]}>
          <Routes>
            <Route path="/models" element={children} />
            <Route path="*" element={<Location />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>
  );
  render(<ModelsPage />, { wrapper });
}

beforeAll(async () => {
  await i18n.changeLanguage("it");
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("ModelsPage", () => {
  it("lists the models that exist instead of a 'coming soon'", async () => {
    backendReturns.mockResolvedValue([
      model(),
      model({
        bpmn_model_id: "bpmn-2",
        process_id: "proc-2",
        process_name: "Accettazione merce",
        has_diagram: false,
        version_count: 0,
        last_saved_at: null,
        review_status: null,
        review_version: null,
        readiness_score: null,
        review_updated_at: null,
        conformance_verdict: null,
        conformance_findings: 0,
      }),
    ]);
    renderPage();

    const passive = await findRow(/Ciclo passivo/);
    expect(within(passive).getByText("Da correggere")).toBeInTheDocument();
    expect(within(passive).getByText("3 versioni")).toBeInTheDocument();
    expect(within(passive).getByText("2 punti da rivedere")).toBeInTheDocument();

    const goods = screen.getByRole("row", { name: /Accettazione merce/ });
    expect(within(goods).getByText("Nessun disegno")).toBeInTheDocument();
    expect(within(goods).getByText("Piano non preparato")).toBeInTheDocument();
    expect(screen.queryByText("In arrivo")).not.toBeInTheDocument();
  });

  it("opens the diagram when there is one", async () => {
    const user = setupUser();
    backendReturns.mockResolvedValue([model()]);
    renderPage();

    await user.click(await findRow(/Ciclo passivo/));

    expect(screen.getByTestId("location")).toHaveTextContent(
      "/projects/proj-1/processes/proc-1?view=canvas",
    );
  });

  it("opens the process, where drawing starts, when there is no diagram yet", async () => {
    const user = setupUser();
    backendReturns.mockResolvedValue([model({ has_diagram: false })]);
    renderPage();

    await user.click(await findRow(/Ciclo passivo/));

    // Aprire un canvas vuoto farebbe credere che il processo sia sparito.
    expect(screen.getByTestId("location")).toHaveTextContent("/projects/proj-1/processes/proc-1");
    expect(screen.getByTestId("location")).not.toHaveTextContent("view=canvas");
  });

  it("finds a model by client name", async () => {
    const user = setupUser();
    backendReturns.mockResolvedValue([
      model(),
      model({
        bpmn_model_id: "bpmn-2",
        process_id: "proc-2",
        process_name: "Fatturazione",
        client_name: "Frascheri",
      }),
    ]);
    renderPage();
    await findRow(/Ciclo passivo/);

    await user.type(screen.getByRole("textbox"), "frascheri");

    expect(screen.getByRole("row", { name: /Fatturazione/ })).toBeInTheDocument();
    expect(screen.queryByRole("row", { name: /Ciclo passivo/ })).not.toBeInTheDocument();
  });

  it("says the workspace has no models yet, and where to start", async () => {
    backendReturns.mockResolvedValue([]);
    renderPage();

    expect(
      await screen.findByText("Ancora nessun modello", {}, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Vai ai progetti" })).toBeInTheDocument();
  });

  it("offers a retry when the library cannot be loaded", async () => {
    backendReturns.mockRejectedValue(new Error("backend giu'"));
    renderPage();

    expect(
      await screen.findByRole("button", { name: /Riprova/ }, { timeout: 5000 }),
    ).toBeInTheDocument();
  });
});

describe("modelStage", () => {
  const api = {
    bpmn_model_id: "b",
    name: "n",
    has_diagram: true,
    version_count: 1,
    last_saved_at: null,
    process_id: "p",
    process_name: "p",
    process_stage: "s",
    project_id: "pr",
    project_name: "pr",
    client_id: "c",
    client_name: "c",
    review_status: "pending" as string | null,
    review_version: 1,
    readiness_score: 50,
    review_updated_at: null,
    conformance_verdict: null as string | null,
    conformance_findings: 0,
    conformance_pending: false,
  };

  it("puts drawing before anything else, and approval above an old finding", () => {
    expect(modelStage({ ...api, has_diagram: false })).toBe("toDraw");
    expect(modelStage({ ...api, review_status: "approved", conformance_verdict: "not_conformant" })).toBe(
      "approved",
    );
    expect(modelStage({ ...api, conformance_verdict: "not_conformant" })).toBe("toFix");
    expect(modelStage({ ...api, review_status: null })).toBe("noPlan");
    expect(modelStage(api)).toBe("inReview");
  });
});
