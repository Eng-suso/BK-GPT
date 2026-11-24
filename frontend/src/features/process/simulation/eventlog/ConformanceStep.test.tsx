import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { i18n } from "@/lib/i18n";
import { HttpError } from "@/lib/http";

import { CONFORMANCE } from "./conformanceFixture";

const http = vi.fn();
vi.mock("@/lib/http", async () => {
  const actual = await vi.importActual<typeof import("@/lib/http")>("@/lib/http");
  return { ...actual, http: (path: string, options?: unknown) => http(path, options) };
});

const { ConformanceStep } = await import("./ConformanceStep");

function renderStep(onDecorations = vi.fn(), onReviewActivities = vi.fn(), onNext = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ConformanceStep eventLogId="elog_1" mappedAt="2026-11-23T10:05:00Z" onDecorations={onDecorations} onReviewActivities={onReviewActivities} onNext={onNext} />
    </QueryClientProvider>,
  );
  return { onDecorations, onReviewActivities, onNext };
}

describe("ConformanceStep", () => {
  it("says how many cases follow the design and where the others leave it", async () => {
    await i18n.changeLanguage("it");
    http.mockResolvedValueOnce(CONFORMANCE);
    const { onDecorations, onNext } = renderStep();

    expect(await screen.findByText("Una parte dei casi esce dal processo disegnato")).toBeInTheDocument();
    expect(screen.getByText("7 casi su 10 seguono il disegno (70%).")).toBeInTheDocument();
    expect(http).toHaveBeenCalledWith("/v1/workspace/event-logs/elog_1/conformance", undefined);
    const table = screen.getByRole("table");
    expect(table).toHaveTextContent("Approvazione CFO");
    expect(table).not.toHaveTextContent("Gateway_1");
    expect(screen.getByText("Manca: Approvazione CFO")).toBeInTheDocument();
    // Il gergo resta nei dettagli.
    expect(screen.getByText("Fitness")).not.toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "Mostra sul disegno" }));
    expect(onDecorations).toHaveBeenLastCalledWith({
      items: [expect.objectContaining({ elementId: "T2", badge: "30%" }), expect.objectContaining({ elementId: "T3", badge: "30%" })],
      legend: { label: "simulation.eventLog.conformance.legend", levels: "simulation.eventLog.conformance.legendLevel" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Avanti" }));
    expect(onNext).toHaveBeenCalled();
  });

  it("explains why conformance is unavailable instead of failing", async () => {
    await i18n.changeLanguage("it");
    http.mockRejectedValueOnce(new HttpError(409, "conflict", { ok: false, error: { code: "no_model", message: "server text" } }));
    renderStep();

    expect(await screen.findByText("Aderenza non calcolabile")).toBeInTheDocument();
    expect(screen.getByText("Il processo non ha ancora un disegno BPMN da confrontare con il log.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Riprova" })).toBeNull();
  });

  it("leads to the activity match when the log is not matched yet", async () => {
    await i18n.changeLanguage("en");
    http.mockRejectedValueOnce(new HttpError(409, "conflict", { ok: false, error: { code: "not_mapped", message: "testo italiano" } }));
    const { onReviewActivities } = renderStep();

    expect(await screen.findByText("Complete and confirm the match between log activities and design steps.")).toBeInTheDocument();
    expect(screen.queryByText("testo italiano")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Review activities" }));
    expect(onReviewActivities).toHaveBeenCalled();
  });

  it("uses the plural of the fitting cases and translates the warnings", async () => {
    await i18n.changeLanguage("it");
    http.mockResolvedValueOnce({
      ...CONFORMANCE, cases: 3, fitting_cases: 1, fitting_share: 1 / 3,
      warnings: [{ code: "variants_truncated", params: { kept: 50, dropped: 4 } }, { code: "variants_truncated", params: { kept: 50, dropped: 4 } }],
    });
    renderStep();

    expect(await screen.findByText("1 caso su 3 segue il disegno (33%).")).toBeInTheDocument();
    expect(screen.getAllByText("Rigiocate le 50 varianti più frequenti; 4 varianti rare escluse.")).toHaveLength(2);
  });

  it("does not judge a log with no case to replay", async () => {
    await i18n.changeLanguage("it");
    http.mockResolvedValueOnce({ ...CONFORMANCE, cases: 0, fitting_cases: 0, fitting_share: 0, variants: [], deviations: [] });
    renderStep();

    expect(await screen.findByText("Nessun caso del log da rigiocare sul disegno.")).toBeInTheDocument();
    expect(screen.queryByText("Il processo reale è diverso da quello disegnato")).toBeNull();
  });

  it("sends the consultant back to the activity match when the design changed", async () => {
    await i18n.changeLanguage("it");
    http.mockResolvedValueOnce({ ...CONFORMANCE, bpmn_version_id: 4 });
    const { onReviewActivities } = renderStep();

    await userEvent.click(await screen.findByRole("button", { name: "Rivedi le attività" }));
    expect(onReviewActivities).toHaveBeenCalled();
  });
});
