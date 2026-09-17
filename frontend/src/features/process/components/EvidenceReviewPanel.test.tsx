import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import "@/lib/i18n";
import { setupUser } from "@/test/user";

const http = vi.fn();

vi.mock("@/lib/http", async () => {
  const actual = await vi.importActual<typeof import("@/lib/http")>("@/lib/http");
  return { ...actual, http: (path: string, options?: unknown) => http(path, options) };
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const { EvidenceReviewPanel } = await import("./EvidenceReviewPanel");

function element(overrides: Record<string, unknown>) {
  return {
    kind: "step",
    element_id: "x",
    label: "Elemento",
    status: "verified",
    mark_status: "verified",
    source_ref: "steps:x",
    source_id: "src",
    source_name: "Intervista Laura Conti",
    quote: "apro una richiesta di acquisto",
    consultant_decision: null,
    removable: true,
    ...overrides,
  };
}

const AUDIT = element({
  element_id: "audit",
  label: "Audit trimestrale",
  status: "unverified",
  mark_status: "unverified",
  source_ref: "steps:audit",
  source_name: "",
  quote: "",
});

const DECISION = element({
  kind: "decision",
  element_id: "soglia",
  label: "Sopra soglia?",
  status: "unverified",
  mark_status: "unverified",
  source_ref: "decisions:soglia",
  quote: "",
  removable: false,
});

function report(elements: Record<string, unknown>[], extra: Record<string, unknown> = {}) {
  const count = (status: string) => elements.filter((item) => item.status === status).length;
  return {
    process_id: "p1",
    snapshot_id: "s1",
    snapshot_label: "V4",
    has_plan: true,
    total: elements.length,
    verified: count("verified"),
    paraphrased: count("paraphrased"),
    label_grounded: count("label_grounded"),
    unverified: count("unverified"),
    awaiting_confirmation: elements.filter(
      (item) => item.status === "unverified" && item.consultant_decision !== "confirmed",
    ).length,
    grounded_ratio: 0.5,
    sources_checked: 3,
    unused_sources: [],
    elements,
    ...extra,
  };
}

function renderPanel(props: Partial<Parameters<typeof EvidenceReviewPanel>[0]> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const onLocate = vi.fn(() => true);
  render(
    <EvidenceReviewPanel
      processId="p1"
      bpmnModelId="b1"
      hasUnsavedChanges={false}
      onLocate={onLocate}
      onClose={vi.fn()}
      {...props}
    />,
    { wrapper },
  );
  return { onLocate };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("EvidenceReviewPanel", () => {
  it("puts what no source supports first, with the words of the sources for the rest", async () => {
    http.mockResolvedValue(
      report([element({ label: "Apri richiesta", source_ref: "steps:apri" }), AUDIT]),
    );
    renderPanel();

    const awaiting = await screen.findByRole("heading", { name: /Da confermare/ });
    const section = awaiting.closest("section") as HTMLElement;
    expect(within(section).getByText("Audit trimestrale")).toBeInTheDocument();
    expect(within(section).getByText(/Nessun passaggio delle fonti/)).toBeInTheDocument();
    // I citati stanno in fondo, chiusi, con la citazione della fonte.
    expect(screen.getByText(/Citati dalle fonti/)).toBeInTheDocument();
    expect(screen.getByText("apro una richiesta di acquisto")).toBeInTheDocument();
  });

  it("confirms an inference and moves it out of the awaiting list", async () => {
    const user = setupUser();
    http.mockImplementation((path: string) => {
      if (path.endsWith("/decisions")) {
        return Promise.resolve({
          ok: true,
          reason_code: "reviewed",
          reason: "«Audit trimestrale» confermato.",
          provenance: report([
            { ...AUDIT, consultant_decision: "confirmed", mark_status: "confirmed" },
          ]),
          draft_status: null,
        });
      }
      return Promise.resolve(report([AUDIT]));
    });
    renderPanel();

    await user.click(await screen.findByRole("button", { name: /Conferma «Audit trimestrale»/ }));

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /Confermati da te/ })).toBeInTheDocument(),
    );
    expect(http).toHaveBeenCalledWith(
      "/v1/workspace/processes/p1/provenance/decisions",
      expect.objectContaining({
        method: "POST",
        body: { source_ref: "steps:audit", decision: "confirmed", note: "" },
      }),
    );
    expect(screen.getByText(/Ogni elemento del disegno ha un appiglio/)).toBeInTheDocument();
  });

  it("asks twice before removing an element from the plan", async () => {
    const user = setupUser();
    http.mockResolvedValue(report([AUDIT]));
    renderPanel();

    await user.click(await screen.findByRole("button", { name: /Rifiuta «Audit trimestrale»/ }));
    expect(http).toHaveBeenCalledTimes(1);

    expect(
      screen.getByRole("button", { name: /togli «Audit trimestrale» dal piano e ridisegna/ }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Annulla/ }));
    expect(screen.queryByRole("button", { name: /dal piano e ridisegna/ })).not.toBeInTheDocument();
  });

  it("does not offer a rejection that would throw away unsaved canvas edits", async () => {
    http.mockResolvedValue(report([AUDIT]));
    renderPanel({ hasUnsavedChanges: true });

    expect(await screen.findByRole("button", { name: /Rifiuta «Audit trimestrale»/ })).toBeDisabled();
    expect(screen.getByText(/Salva le modifiche al canvas prima di rifiutare/)).toBeInTheDocument();
  });

  it("does not offer to remove structure from here", async () => {
    http.mockResolvedValue(report([DECISION]));
    renderPanel();

    await screen.findByRole("button", { name: /Conferma «Sopra soglia\?»/ });
    expect(screen.queryByRole("button", { name: /Rifiuta «Sopra soglia\?»/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Attori e decisioni si correggono sul piano/)).toBeInTheDocument();
  });

  it("says when an element is not in the drawing instead of doing nothing", async () => {
    const user = setupUser();
    http.mockResolvedValue(report([AUDIT]));
    const onLocate = vi.fn(() => false);
    renderPanel({ onLocate });

    await user.click(await screen.findByRole("button", { name: "Audit trimestrale" }));

    expect(onLocate).toHaveBeenCalledWith("steps:audit");
    expect(screen.getByRole("status")).toHaveTextContent(/non compare nel disegno attuale/);
  });

  it("names the sources the plan takes nothing from", async () => {
    http.mockResolvedValue(report([AUDIT], { unused_sources: ["Intervista Paolo Marchetti"] }));
    renderPanel();

    expect(await screen.findByText(/Intervista Paolo Marchetti/)).toBeInTheDocument();
  });

  it("tells a process without a plan apart from a plan with nothing verified", async () => {
    http.mockResolvedValue({ ...report([]), has_plan: false });
    renderPanel();

    expect(await screen.findByText(/non ha ancora un piano/)).toBeInTheDocument();
  });

  it("surfaces a load failure with a retry", async () => {
    http.mockRejectedValue(new Error("boom"));
    renderPanel();

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
