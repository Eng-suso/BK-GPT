import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { setupUser } from "@/test/user";

import { i18n } from "@/lib/i18n";

// Il confine e' la risposta HTTP: il test passa anche dal contratto e dalla mappatura.
const http = vi.fn<(path: string) => Promise<unknown>>();

vi.mock("@/lib/http", () => ({ http: (path: string) => http(path) }));

const { UsageMenu } = await import("./UsageMenu");
const { headlineShare, usageTone } = await import("./api");

const inHours = (hours: number) => new Date(Date.now() + hours * 3_600_000).toISOString();

function window(overrides: Record<string, unknown> = {}) {
  return {
    used_share: 0.2,
    limited: true,
    exhausted: false,
    started_at: inHours(-1),
    resets_at: inHours(4),
    ...overrides,
  };
}

function usage(overrides: Record<string, unknown> = {}) {
  return {
    enabled: true,
    session: window({ used_share: 0.64 }),
    week: window({ used_share: 0.3, resets_at: inHours(72) }),
    trial: { ...window({ used_share: 0.1, resets_at: inHours(24 * 10) }), over: false },
    blocking: null,
    forecast: null,
    ...overrides,
  };
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </I18nextProvider>
  );
}

beforeAll(async () => {
  await i18n.changeLanguage("it");
});

afterEach(() => {
  http.mockReset();
});

describe("UsageMenu", () => {
  it("con i limiti spenti non mostra niente", async () => {
    http.mockResolvedValue(usage({ enabled: false }));
    const { container } = render(<UsageMenu />, { wrapper });

    await vi.waitFor(() => expect(http).toHaveBeenCalledWith("/v1/usage/me"));
    expect(container).toBeEmptyDOMElement();
  });

  it("l'anello dice la quota della finestra piu' vicina al limite", async () => {
    http.mockResolvedValue(usage());
    render(<UsageMenu />, { wrapper });

    expect(await screen.findByRole("button", { name: "Utilizzo: 64% del limite più vicino" })).toBeVisible();
  });

  it("il pannello mostra sessione, settimana e prova con le loro barre", async () => {
    http.mockResolvedValue(usage());
    const user = setupUser();
    render(<UsageMenu />, { wrapper });

    await user.click(await screen.findByRole("button", { name: /Utilizzo/ }));

    expect(screen.getByRole("progressbar", { name: "Sessione corrente" })).toHaveAttribute("aria-valuenow", "64");
    expect(screen.getByRole("progressbar", { name: "Limite settimanale" })).toHaveAttribute("aria-valuenow", "30");
    expect(screen.getByRole("progressbar", { name: "Prova" })).toHaveAttribute("aria-valuenow", "10");
    expect(screen.getByText(/Si ripristina alle/)).toBeVisible();
  });

  it("un ritmo che esaurisce prima del rinnovo si dice", async () => {
    http.mockResolvedValue(
      usage({ forecast: { window: "session", exhausts_at: inHours(1), resets_at: inHours(4) } }),
    );
    const user = setupUser();
    render(<UsageMenu />, { wrapper });

    await user.click(await screen.findByRole("button", { name: /Utilizzo/ }));

    expect(screen.getByText("Attenzione al ritmo")).toBeVisible();
    expect(screen.getByText(/A questo ritmo esaurirai la sessione/)).toBeVisible();
  });

  it("un limite raggiunto e' un avviso con il momento della ripresa", async () => {
    http.mockResolvedValue(
      usage({ session: window({ used_share: 1, exhausted: true }), blocking: "session" }),
    );
    const user = setupUser();
    render(<UsageMenu />, { wrapper });

    await user.click(await screen.findByRole("button", { name: "Utilizzo: 100% del limite più vicino" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Sessione esaurita");
    expect(screen.getByRole("alert")).toHaveTextContent(/Puoi riprendere alle/);
  });

  it("una sessione non ancora aperta lo dice invece di inventare un orario", async () => {
    http.mockResolvedValue(usage({ session: window({ used_share: 0, started_at: null, resets_at: null }) }));
    const user = setupUser();
    render(<UsageMenu />, { wrapper });

    await user.click(await screen.findByRole("button", { name: /Utilizzo/ }));

    expect(screen.getByText("Parte con la prossima richiesta e dura 5 ore")).toBeVisible();
  });
});

describe("headlineShare e usageTone", () => {
  it("un limite raggiunto vale sempre il pieno", () => {
    const blocked = {
      enabled: true,
      session: { usedShare: 0.4, limited: true, exhausted: false, startedAt: null, resetsAt: null },
      week: { usedShare: 0.99, limited: true, exhausted: false, startedAt: null, resetsAt: null },
      trial: { usedShare: 0, limited: false, exhausted: false, startedAt: null, resetsAt: null, over: true },
      blocking: "trial" as const,
      forecast: null,
    };
    expect(headlineShare(blocked)).toBe(1);
  });

  it("i colori cambiano prima del limite", () => {
    expect(usageTone(0.5)).toBe("normal");
    expect(usageTone(0.8)).toBe("warning");
    expect(usageTone(0.95)).toBe("danger");
  });
});
