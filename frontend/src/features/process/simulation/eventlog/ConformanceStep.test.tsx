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

function renderStep(onDecorations = vi.fn(), onReviewActivities = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ConformanceStep eventLogId="elog_1" mappedAt="2026-11-23T10:05:00Z" onDecorations={onDecorations} onReviewActivities={onReviewActivities} />
    </QueryClientProvider>,
  );
  return { onDecorations, onReviewActivities };
}

describe("ConformanceStep", () => {
  it("says how many cases follow the design and where the others leave it", async () => {
    await i18n.changeLanguage("it");
    http.mockResolvedValueOnce(CONFORMANCE);
    const { onDecorations } = renderStep();

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
    expect(onDecorations).toHaveBeenLastCalledWith([
      expect.objectContaining({ elementId: "T2", badge: "30%" }),
      expect.objectContaining({ elementId: "T3", badge: "30%" }),
    ]);
  });

  it("explains why conformance is unavailable instead of failing", async () => {
    await i18n.changeLanguage("it");
    http.mockRejectedValueOnce(new HttpError(409, "Il processo non ha ancora un BPMN da confrontare con il log."));
    renderStep();

    expect(await screen.findByText("Aderenza non calcolabile")).toBeInTheDocument();
    expect(screen.getByText("Il processo non ha ancora un BPMN da confrontare con il log.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Riprova" })).toBeNull();
  });

  it("sends the consultant back to the activity match when the design changed", async () => {
    await i18n.changeLanguage("it");
    http.mockResolvedValueOnce({ ...CONFORMANCE, bpmn_version_id: 4 });
    const { onReviewActivities } = renderStep();

    await userEvent.click(await screen.findByRole("button", { name: "Rivedi le attività" }));
    expect(onReviewActivities).toHaveBeenCalled();
  });
});
