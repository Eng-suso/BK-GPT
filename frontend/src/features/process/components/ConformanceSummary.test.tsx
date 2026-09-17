import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import "@/lib/i18n";
import userEvent from "@testing-library/user-event";

const http = vi.fn();

vi.mock("@/lib/http", async () => {
  const actual = await vi.importActual<typeof import("@/lib/http")>("@/lib/http");
  return {
    ...actual,
    http: (path: string, options?: unknown) => http(path, options),
  };
});

const toast = { success: vi.fn(), error: vi.fn(), message: vi.fn() };
vi.mock("sonner", () => ({ toast }));

const { ConformanceSummary } = await import("./ConformanceSummary");

const LOADED = { timeout: 5_000 };

function status(
  report: Record<string, unknown> | null,
  extra: Record<string, unknown> = {},
) {
  return {
    process_id: "p1",
    snapshot_id: "s",
    snapshot_label: "V3",
    running: false,
    is_current: true,
    report,
    ...extra,
  };
}

function report(verdict: string, findings: Record<string, unknown>[] = [], extra: Record<string, unknown> = {}) {
  return {
    verdict,
    findings,
    sources_audited: 3,
    sources_with_text: 3,
    llm_audit_note: "",
    audited_at: "2026-09-17T15:00:00+00:00",
    // Campi tecnici che il backend manda e che il consulente non deve mai vedere.
    snapshot_id: "7fda20292c006cae",
    canvas_signature: "abc123",
    llm_audit: "done",
    discarded_findings: 1,
    ...extra,
  };
}

function finding(layer: string, message: string) {
  return { layer, severity: "gap", code: "internal_code", message, element_ref: "steps:x", source_name: "" };
}

function renderSummary() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  render(<ConformanceSummary processId="p1" bpmnModelId="b1" />, { wrapper });
}

function expectNoTechnicalWords() {
  const text = document.body.textContent ?? "";
  for (const word of ["steps:", "internal_code", "7fda2029", "abc123", "llm", "snapshot", "canvas_plan", "source_coverage"]) {
    expect(text).not.toContain(word);
  }
}

afterEach(() => {
  http.mockReset();
  vi.clearAllMocks();
});

describe("ConformanceSummary", () => {
  it("says the diagram has not been checked yet", async () => {
    http.mockResolvedValue(status(null));
    renderSummary();

    expect(await screen.findByText("Non ancora confrontato", {}, LOADED)).toBeInTheDocument();
    expectNoTechnicalWords();
  });

  it("says the diagram matches the sources, with how many and when", async () => {
    http.mockResolvedValue(status(report("conformant")));
    renderSummary();

    expect(await screen.findByText("Il disegno coincide con le fonti", {}, LOADED)).toBeInTheDocument();
    expect(screen.getByText(/Confrontato con 3 fonti/)).toBeInTheDocument();
    expectNoTechnicalWords();
  });

  it("groups the points to review by what they mean for the diagram", async () => {
    http.mockResolvedValue(
      status(
        report("not_conformant", [
          finding("source_contradiction", "«Verifica autorizzazione»: «Intervista Francesca» dice diversamente."),
          finding("source_coverage", "«Intervista Paolo» dice «chiamo direttamente il fornitore», e il disegno non lo rappresenta."),
          finding("plan_sources", "«Audit trimestrale» non risulta in nessuna fonte."),
        ]),
      ),
    );
    renderSummary();

    expect(await screen.findByText("3 punti da rivedere", {}, LOADED)).toBeInTheDocument();
    expect(screen.getByText("Le fonti dicono diversamente")).toBeInTheDocument();
    expect(screen.getByText("Detto nelle fonti, assente nel disegno")).toBeInTheDocument();
    expect(screen.getByText(/dice diversamente/)).toBeInTheDocument();
    // Gli elementi senza riscontro hanno gia' la loro sezione: qui si rimanda.
    expect(screen.queryByText(/Audit trimestrale/)).not.toBeInTheDocument();
    expect(screen.getByText(/1 elemento del disegno non ha riscontro/)).toBeInTheDocument();
    expectNoTechnicalWords();
  });

  it("warns when the result no longer describes what is on screen", async () => {
    http.mockResolvedValue(status(report("conformant"), { is_current: false }));
    renderSummary();

    expect(await screen.findByText(/sono cambiati dopo l'ultimo confronto/, {}, LOADED)).toBeInTheDocument();
  });

  it("never shows an incomplete check as a match", async () => {
    http.mockResolvedValue(
      status(report("incomplete", [], { llm_audit_note: "il confronto con le fonti non e' disponibile in questo momento." })),
    );
    renderSummary();

    expect(await screen.findByText("Confronto non completo", {}, LOADED)).toBeInTheDocument();
    expect(screen.queryByText("Il disegno coincide con le fonti")).not.toBeInTheDocument();
    expect(screen.getByText(/^Il confronto con le fonti non e' disponibile/)).toBeInTheDocument();
  });

  it("runs the check on demand and shows the new result", async () => {
    http.mockImplementation((path: string, options?: { method?: string }) =>
      Promise.resolve(
        options?.method === "POST" && path.endsWith("/conformance-audit")
          ? status(report("conformant"))
          : status(null),
      ),
    );
    renderSummary();
    const user = userEvent.setup({ delay: null });

    await screen.findByText("Non ancora confrontato", {}, LOADED);
    await user.click(screen.getByRole("button", { name: "Confronta ora" }));

    expect(await screen.findByText("Il disegno coincide con le fonti", {}, LOADED)).toBeInTheDocument();
    expect(toast.success).toHaveBeenCalled();
  });

  it("tells the consultant when the check fails", async () => {
    http.mockImplementation((_path: string, options?: { method?: string }) =>
      options?.method === "POST" ? Promise.reject(new Error("boom")) : Promise.resolve(status(null)),
    );
    renderSummary();
    const user = userEvent.setup({ delay: null });

    await screen.findByText("Non ancora confrontato", {}, LOADED);
    await user.click(screen.getByRole("button", { name: "Confronta ora" }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
  });

  it("says the check is running instead of showing the previous result as current", async () => {
    http.mockResolvedValue(status(report("conformant"), { running: true, is_current: false }));
    renderSummary();

    expect(await screen.findByText("Confronto in corso", {}, LOADED)).toBeInTheDocument();
    expect(screen.queryByText("Il disegno coincide con le fonti")).not.toBeInTheDocument();
    expect(screen.getByText(/Puoi continuare a lavorare/)).toBeInTheDocument();
  });

  it("offers to add the missing points to the diagram, and only then redraws", async () => {
    http.mockImplementation((path: string, options?: { method?: string }) => {
      if (options?.method === "POST" && path.endsWith("/conformance/repair")) return Promise.resolve({});
      return Promise.resolve(
        status(
          report("not_conformant", [
            finding("source_coverage", "«Intervista Paolo» dice «chiamo il fornitore», e il disegno non lo rappresenta."),
            finding("source_divergence", "«Laura» e «Marco» lo raccontano in modo diverso."),
          ]),
        ),
      );
    });
    renderSummary();
    const user = userEvent.setup({ delay: null });

    // Il disaccordo fra voci non si "integra": si chiede. Conta solo l'altro.
    const button = await screen.findByRole("button", { name: "Integra nel disegno 1 punto" }, LOADED);
    expect(screen.getByText("Le fonti si contraddicono fra loro")).toBeInTheDocument();

    await user.click(button);

    await waitFor(() =>
      expect(http).toHaveBeenCalledWith(
        "/v1/workspace/processes/p1/conformance/repair",
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });

  it("shows a drawing that follows the sources as good, with the points to clarify", async () => {
    http.mockResolvedValue(
      status(
        report("conformant_with_divergences", [
          finding("source_divergence", "«Laura» e «Marco» lo raccontano in modo diverso."),
        ]),
      ),
    );
    renderSummary();

    expect(
      await screen.findByText("Il disegno segue le fonti · 1 punto da chiarire", {}, LOADED),
    ).toBeInTheDocument();
    expectNoTechnicalWords();
  });
});
