import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import "@/lib/i18n";
import type { ProjectProcess, ProjectSource } from "@/contracts/workspace";

const http = vi.fn();

vi.mock("@/lib/http", async () => {
  const actual = await vi.importActual<typeof import("@/lib/http")>("@/lib/http");
  return { ...actual, http: (path: string, options?: unknown) => http(path, options) };
});

const { SourcesPanel } = await import("./SourcesPanel");

const PROCESS: ProjectProcess = {
  id: "acquisti-indiretti",
  projectId: "ciclo-acquisti",
  bpmnModelId: "acquisti-bpmn",
  name: "Acquisti indiretti",
  stage: "AS-IS",
  status: "In corso",
  owner: "Acquisti",
  readiness: 40,
  archivedAt: null,
  archiveReason: null,
};

const SOURCE: ProjectSource = {
  id: "src-1",
  projectId: PROCESS.projectId,
  processId: PROCESS.id,
  name: "Intervista Paolo Marchetti - Manutenzione",
  type: "Intervista",
  // La nota: due righe, troncate. E' quello che il pannello mostrava e basta.
  meta: "Come nascono le richieste urgenti…",
};

const TRANSCRIPT = [
  "D. Parlami delle urgenze.",
  "",
  "Se ho una linea ferma non posso permettermi di aspettare il giro normale,",
  "quindi chiamo direttamente il fornitore.",
].join("\n");

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SourcesPanel sources={[SOURCE]} processes={[PROCESS]} onOpenProcess={vi.fn()} />
    </QueryClientProvider> as ReactNode,
  );
}

afterEach(() => {
  http.mockReset();
});

describe("SourcesPanel — una fonte si legge, non si riassume", () => {
  it("mostra l'intervista per intero e la sua sintesi quando la fonte si apre", async () => {
    http.mockResolvedValue({
      id: SOURCE.id,
      project_id: SOURCE.projectId,
      process_id: SOURCE.processId,
      name: SOURCE.name,
      type: SOURCE.type,
      summary: "Come nascono e come si chiudono le richieste urgenti.",
      participants: ["Paolo Marchetti"],
      occurred_at: null,
      episode_id: "ep-1",
      content: TRANSCRIPT,
      has_content: true,
    });

    renderPanel();
    await userEvent.click(screen.getByRole("button", { name: /Intervista Paolo/ }));

    await waitFor(() =>
      expect(
        screen.getByText(/Come nascono e come si chiudono le richieste urgenti/),
      ).toBeInTheDocument(),
    );
    // Il testo integrale, non la nota troncata di due righe.
    expect(
      screen.getByText(/chiamo direttamente il fornitore/),
    ).toBeInTheDocument();
    expect(screen.getByText("Paolo Marchetti")).toBeInTheDocument();
    expect(http).toHaveBeenCalledWith(
      `/v1/workspace/sources/${SOURCE.id}/document`,
      undefined,
    );
  });

  it("non chiede il testo finche' nessuno apre una fonte", () => {
    renderPanel();

    expect(http).not.toHaveBeenCalled();
  });

  it("dichiara quando una fonte non ha un testo registrato", async () => {
    http.mockResolvedValue({
      id: SOURCE.id,
      project_id: SOURCE.projectId,
      process_id: SOURCE.processId,
      name: SOURCE.name,
      type: SOURCE.type,
      summary: "Procedura ricevuta dal cliente.",
      participants: [],
      occurred_at: null,
      episode_id: null,
      content: "",
      has_content: false,
    });

    renderPanel();
    await userEvent.click(screen.getByRole("button", { name: /Intervista Paolo/ }));

    await waitFor(() =>
      expect(
        screen.getByText(/non ha un testo integrale registrato/),
      ).toBeInTheDocument(),
    );
  });
});
