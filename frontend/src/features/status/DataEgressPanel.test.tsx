import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { i18n } from "@/lib/i18n";
import type { EgressInventory, EgressRoute } from "./api";

const fetchEgressInventory = vi.fn<() => Promise<EgressInventory>>();

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, fetchEgressInventory: () => fetchEgressInventory() };
});

const { DataEgressPanel } = await import("./DataEgressPanel");

function route(overrides: Partial<EgressRoute>): EgressRoute {
  return {
    destination: "llm_chat",
    purpose: "Modello linguistico",
    host: "api.openai.com",
    internal: false,
    active: true,
    allowed: true,
    data: ["customer_content"],
    tasks: [],
    ...overrides,
  };
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </I18nextProvider>
  );
  render(<DataEgressPanel />, { wrapper });
}

beforeEach(async () => {
  fetchEgressInventory.mockReset();
  await i18n.changeLanguage("it");
});

describe("DataEgressPanel", () => {
  it("lists only what leaves now, with the host and the data it receives", async () => {
    fetchEgressInventory.mockResolvedValue({
      environment: "prod",
      enforced: true,
      localTracePayload: false,
      routes: [
        route({ destination: "transcription", purpose: "Trascrizione", data: ["audio", "customer_content"] }),
        route({ destination: "tracing", purpose: "Tracing", host: "api.smith.langchain.com", active: false }),
        route({ destination: "document_reader", purpose: "Lettura documenti", host: "docling", internal: true }),
      ],
    });
    renderPanel();

    expect(await screen.findByText("1 fornitore esterno riceve dati.", { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/Solo gli host autorizzati/)).toBeInTheDocument();
    const row = screen.getByText("Trascrizione").closest("li")!;
    expect(within(row).getByText("api.openai.com")).toBeInTheDocument();
    expect(within(row).getByText("Audio")).toBeInTheDocument();
    expect(screen.getByText(/Servizio interno/)).toBeInTheDocument();
    // Spenta: non riceve niente, quindi non compare.
    expect(screen.queryByText("Tracing")).not.toBeInTheDocument();
  });

  it("flags a blocked destination", async () => {
    fetchEgressInventory.mockResolvedValue({
      environment: "prod",
      enforced: true,
      localTracePayload: false,
      routes: [route({ allowed: false, host: "api.groq.com" })],
    });
    renderPanel();

    expect(await screen.findByText(/Non autorizzato/)).toBeInTheDocument();
  });

  it("warns when prompt text is written to local traces", async () => {
    fetchEgressInventory.mockResolvedValue({
      environment: "dev",
      enforced: false,
      localTracePayload: true,
      routes: [],
    });
    renderPanel();

    expect(await screen.findByText(/Le tracce locali salvano su disco/)).toBeInTheDocument();
    expect(screen.getByText(/Nessun fornitore esterno/)).toBeInTheDocument();
  });

  it("says when the list cannot be read and lets the user retry", async () => {
    fetchEgressInventory.mockRejectedValue(new Error("offline"));
    renderPanel();

    expect(await screen.findByRole("alert")).toHaveTextContent("Elenco dei destinatari non leggibile.");
    expect(screen.getByRole("button", { name: "Aggiorna" })).toBeInTheDocument();
  });
});
