import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { i18n } from "@/lib/i18n";
import type { DegradationReport, QueueHealth } from "./api";

const fetchDegradation = vi.fn<() => Promise<DegradationReport>>();
const fetchQueueHealth = vi.fn<() => Promise<QueueHealth>>();

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return {
    ...actual,
    fetchDegradation: () => fetchDegradation(),
    fetchQueueHealth: () => fetchQueueHealth(),
  };
});

const { ServiceStatusDialog } = await import("./ServiceStatusDialog");

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </I18nextProvider>
  );
  render(<ServiceStatusDialog open onOpenChange={vi.fn()} modelName="gpt-5.6-luna" />, {
    wrapper,
  });
}

beforeAll(async () => {
  await i18n.changeLanguage("it");
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("ServiceStatusDialog", () => {
  it("says the backend answers and what the queues are carrying", async () => {
    fetchDegradation.mockResolvedValue({ status: "ok", counters: {} });
    fetchQueueHealth.mockResolvedValue({
      status: "ok",
      graph_outbox: { pending: 3, stuck: 0, dead_letter: 0 },
    } as QueueHealth);
    renderDialog();

    expect(await screen.findByText(/Il backend risponde/)).toBeInTheDocument();
    expect(await screen.findByText(/3 in attesa, 0 bloccati/)).toBeInTheDocument();
  });

  it("separates what is stuck from what was set aside", async () => {
    fetchDegradation.mockResolvedValue({ status: "ok", counters: {} });
    fetchQueueHealth.mockResolvedValue({
      status: "ok",
      graph_outbox: { pending: 0, stuck: 2, dead_letter: 1 },
    } as QueueHealth);
    renderDialog();

    // `stuck` puo' ancora passare da solo, `dead_letter` no: un pannello che li
    // somma fa aspettare una coda che non ripartira'.
    expect(await screen.findByText(/0 in attesa, 2 bloccati/)).toBeInTheDocument();
    expect(await screen.findByText(/1 messi da parte/)).toBeInTheDocument();
  });

  it("names the fallbacks the brain took instead of calling it healthy", async () => {
    fetchDegradation.mockResolvedValue({
      status: "degraded",
      counters: { "retrieval_gateway:fallback": 4 },
    });
    fetchQueueHealth.mockResolvedValue({ status: "ok" } as QueueHealth);
    renderDialog();

    expect(await screen.findByText(/via di ripiego/)).toBeInTheDocument();
    expect(await screen.findByText(/retrieval_gateway:fallback: 4/)).toBeInTheDocument();
  });

  it("reports an unreachable backend rather than an empty panel", async () => {
    fetchDegradation.mockRejectedValue(new Error("network down"));
    fetchQueueHealth.mockRejectedValue(new Error("network down"));
    renderDialog();

    expect(await screen.findByText(/Backend non raggiungibile/)).toBeInTheDocument();
  });

  it("says the queues are not configured instead of showing zeros", async () => {
    fetchDegradation.mockResolvedValue({ status: "ok", counters: {} });
    fetchQueueHealth.mockResolvedValue({ status: "not_configured" } as QueueHealth);
    renderDialog();

    expect(await screen.findByText(/Code non configurate/)).toBeInTheDocument();
  });
});
