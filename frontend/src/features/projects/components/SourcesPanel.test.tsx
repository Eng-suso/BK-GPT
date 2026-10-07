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

const CLIENT = { id: "esaote", name: "Esaote" };

const SOURCE: ProjectSource = {
  id: "src-1",
  projectId: PROCESS.projectId,
  clientId: null,
  processId: PROCESS.id,
  name: "Intervista Paolo Marchetti - Manutenzione",
  type: "Intervista",
  // La nota: due righe, troncate. E' quello che il pannello mostrava e basta.
  meta: "Come nascono le richieste urgenti…",
  roles: [],
  retention: "persistent",
  scopes: [],
  status: "reference",
  byteSize: null,
  acquisitionStatus: null,
  acquisitionError: null,
  claimsStatus: null,
  claimsError: null,
  reconcileStatus: null,
};

const TRANSCRIPT = [
  "D. Parlami delle urgenze.",
  "",
  "Se ho una linea ferma non posso permettermi di aspettare il giro normale,",
  "quindi chiamo direttamente il fornitore.",
].join("\n");

function renderPanel(sources: ProjectSource[] = [SOURCE]) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SourcesPanel
        projectId={PROCESS.projectId}
        client={CLIENT}
        sources={sources}
        processes={[PROCESS]}
        onOpenProcess={vi.fn()}
      />
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

  it("carica un file con più usi e un ambito esplicito", async () => {
    http.mockResolvedValue({
      id: "src-upload",
      project_id: SOURCE.projectId,
      process_id: PROCESS.id,
      name: "procedura.md",
      type: "File",
      meta: "In lettura: testo ed evidenze arrivano tra poco.",
      roles: ["process_evidence", "policy"],
      retention: "persistent",
      scopes: [{ type: "process", id: PROCESS.id }],
      status: "extracted",
      byte_size: 18,
      content_hash: "hash",
      mime_type: "text/markdown",
      acquisition_status: "pending",
      acquisition_error: null,
    });

    renderPanel();
    await userEvent.click(screen.getByRole("button", { name: /aggiungi fonte/i }));
    await userEvent.upload(
      screen.getByLabelText(/file da analizzare/i),
      new File(["procedura acquisti"], "procedura.md", { type: "text/markdown" }),
    );
    await userEvent.click(screen.getByLabelText(/descrive come si lavora/i));
    await userEvent.click(screen.getByLabelText(/regole da rispettare/i));
    await userEvent.selectOptions(
      screen.getByLabelText(/ambito/i),
      `process:${PROCESS.id}`,
    );
    const submit = screen.getByRole("button", { name: /^carica e analizza$/i });
    expect(submit).toBeEnabled();
    await userEvent.click(submit);

    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: /aggiungi una fonte/i })).not.toBeInTheDocument(),
    );

    expect(http).toHaveBeenCalledTimes(1);
    const [path, options] = http.mock.calls[0] as [string, { body: FormData }];
    expect(path).toBe(`/v1/workspace/projects/${PROCESS.projectId}/sources/upload`);
    const body = options.body;
    expect(body.get("roles")).toBe('["process_evidence","policy"]');
    expect(body.get("retention")).toBe("persistent");
    expect(body.get("scopes")).toBe(JSON.stringify([{ type: "process", id: PROCESS.id }]));
  });

  it("carica un file per tutto il cliente", async () => {
    http.mockResolvedValue({
      id: "src-policy",
      project_id: null,
      client_id: CLIENT.id,
      process_id: null,
      name: "policy-acquisti.pdf",
      type: "File",
      meta: "In lettura: testo ed evidenze arrivano tra poco.",
      roles: ["policy"],
      retention: "persistent",
      scopes: [{ type: "client", id: CLIENT.id }],
      status: "extracted",
      byte_size: 18,
      content_hash: "hash",
      mime_type: "application/pdf",
      acquisition_status: "pending",
      acquisition_error: null,
    });

    renderPanel();
    await userEvent.click(screen.getByRole("button", { name: /aggiungi fonte/i }));
    await userEvent.upload(
      screen.getByLabelText(/file da analizzare/i),
      new File(["policy"], "policy-acquisti.pdf", { type: "application/pdf" }),
    );
    await userEvent.click(screen.getByLabelText(/regole da rispettare/i));
    const scope = screen.getByLabelText(/ambito/i);
    expect(screen.getByRole("option", { name: "Tutto il cliente «Esaote»" })).toBeInTheDocument();
    await userEvent.selectOptions(scope, `client:${CLIENT.id}`);
    await userEvent.click(screen.getByRole("button", { name: /^carica e analizza$/i }));

    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: /aggiungi una fonte/i })).not.toBeInTheDocument(),
    );
    expect(http).toHaveBeenCalledTimes(1);
    const [path, options] = http.mock.calls[0] as [string, { body: FormData }];
    expect(path).toBe(`/v1/workspace/clients/${CLIENT.id}/sources/upload`);
    expect(options.body.get("roles")).toBe('["policy"]');
  });

  it("una fonte del cliente lo dice nella lista e nel dettaglio, senza processo da aprire", async () => {
    const policy: ProjectSource = {
      ...SOURCE,
      id: "src-policy",
      projectId: null,
      clientId: CLIENT.id,
      processId: null,
      name: "policy-acquisti.pdf",
      type: "File",
      meta: "",
    };
    http.mockResolvedValue({
      id: policy.id,
      project_id: null,
      process_id: null,
      name: policy.name,
      type: policy.type,
      summary: "",
      participants: [],
      occurred_at: null,
      episode_id: null,
      content: "Ogni ordine sopra i 10.000 EUR richiede tre preventivi.",
      has_content: true,
    });

    renderPanel([policy]);
    const row = screen.getByRole("button", { name: /policy-acquisti\.pdf/ });
    expect(row).toHaveTextContent("Tutto il cliente");
    await userEvent.click(row);

    const dialog = await screen.findByRole("dialog", { name: /policy-acquisti\.pdf/ });
    expect(dialog).toHaveTextContent("Vale per");
    expect(dialog).toHaveTextContent("Tutto il cliente «Esaote»");
    expect(dialog).not.toHaveTextContent("Processo collegato");
    expect(screen.queryByRole("button", { name: /apri processo collegato/i })).not.toBeInTheDocument();
  });

  it("dice quali file sono ancora in lettura e quali non sono stati letti per intero", () => {
    renderPanel([
      { ...SOURCE, id: "src-a", name: "ordini.xlsx", acquisitionStatus: "pending" },
      { ...SOURCE, id: "src-b", name: "procedura.pdf", acquisitionStatus: "partial" },
      { ...SOURCE, id: "src-c", name: "verbale.docx", acquisitionStatus: "done" },
    ]);

    const statuses = screen.getAllByRole("status").map((item) => item.textContent);
    // "Pronta" non si mostra: e' il caso normale.
    expect(statuses).toEqual(["In lettura…", "Lettura parziale"]);
  });

  it("conferma un file letto come evidenza del processo", async () => {
    http.mockImplementation(async (path: string) => {
      if (path.endsWith("/verify")) {
        return {
          id: "src-letto",
          project_id: SOURCE.projectId,
          process_id: PROCESS.id,
          name: "procedura.pdf",
          type: "File",
          meta: "Testo ed evidenze pronti per la consultazione.",
          status: "approved",
          acquisition_status: "done",
        };
      }
      return {
        id: "src-letto",
        name: "procedura.pdf",
        type: "File",
        summary: "",
        participants: [],
        occurred_at: null,
        episode_id: null,
        content: "Il CFO approva.",
        has_content: true,
      };
    });
    renderPanel([
      {
        ...SOURCE,
        id: "src-letto",
        name: "procedura.pdf",
        status: "extracted",
        byteSize: 10,
        acquisitionStatus: "done",
      },
    ]);

    await userEvent.click(screen.getByRole("button", { name: /procedura\.pdf/ }));
    expect(screen.getByText("Da confermare")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /usa come evidenza/i }));

    await waitFor(() =>
      expect(http).toHaveBeenCalledWith("/v1/workspace/sources/src-letto/verify", { method: "POST" }),
    );
  });

  it("resta aperto e spiega quando l'analisi fallisce", async () => {
    const { HttpError } = await import("@/lib/http");
    http.mockRejectedValue(new HttpError(415, "415", { detail: "Il PDF non può essere letto." }));

    renderPanel();
    await userEvent.click(screen.getByRole("button", { name: /aggiungi fonte/i }));
    await userEvent.upload(
      screen.getByLabelText(/file da analizzare/i),
      new File(["rotto"], "procedura.pdf", { type: "application/pdf" }),
    );
    await userEvent.click(screen.getByLabelText(/aiuta a capire il contesto/i));
    await userEvent.click(screen.getByRole("button", { name: /^carica e analizza$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Il PDF non può essere letto.");
    expect(screen.getByRole("dialog", { name: /aggiungi una fonte/i })).toBeVisible();
  });
});
