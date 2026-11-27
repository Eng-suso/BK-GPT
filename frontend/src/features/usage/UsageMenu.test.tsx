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
    session_hours: 5,
    session: window({ used_share: 0.64 }),
    week: window({ used_share: 0.3, resets_at: inHours(72) }),
    trial: { ...window({ used_share: 0.1, resets_at: inHours(24 * 10) }), over: false },
    blocking: null,
    forecast: null,
    audio: {
      week: { used_seconds: 7_800, limit_seconds: 21_600, exhausted: false, resets_at: inHours(72) },
      trial: { used_seconds: 10_800, limit_seconds: 36_000, exhausted: false, resets_at: inHours(240) },
      blocking: null,
    },
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
    // Spento, il backend manda il minimo e non legge niente.
    http.mockResolvedValue({ enabled: false, session_hours: 5 });
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

describe("UsageMenu, registrazioni", () => {
  it("mostra le ore di registrazione in chiaro", async () => {
    http.mockResolvedValue(usage());
    const user = setupUser();
    render(<UsageMenu />, { wrapper });

    await user.click(await screen.findByRole("button", { name: /Utilizzo/ }));

    expect(screen.getByText("2 h 10 min su 6 h")).toBeVisible();
    expect(screen.getByText("3 h su 10 h")).toBeVisible();
    expect(screen.getByRole("progressbar", { name: "Ore di registrazione questa settimana" })).toHaveAttribute(
      "aria-valuenow",
      "36",
    );
  });

  it("a ore finite avvisa che la chat continua", async () => {
    http.mockResolvedValue(
      usage({
        audio: {
          week: { used_seconds: 21_600, limit_seconds: 21_600, exhausted: true, resets_at: inHours(30) },
          trial: { used_seconds: 21_600, limit_seconds: 36_000, exhausted: false, resets_at: inHours(240) },
          blocking: "week",
        },
      }),
    );
    const user = setupUser();
    render(<UsageMenu />, { wrapper });

    await user.click(await screen.findByRole("button", { name: /Utilizzo/ }));

    expect(screen.getByText("Ore di registrazione finite")).toBeVisible();
    expect(screen.getByText(/La chat e il resto continuano/)).toBeVisible();
  });
});

describe("formatDuration", () => {
  it("scrive le durate come le dice una persona", async () => {
    const { formatDuration } = await import("@/lib/date");
    expect(formatDuration(7_800, "it")).toBe("2 h 10 min");
    expect(formatDuration(2_700, "it")).toBe("45 min");
    expect(formatDuration(21_600, "it")).toBe("6 h");
    expect(formatDuration(21_570, "it")).toBe("5 h 59 min");
    expect(formatDuration(20, "it")).toBe("< 1 min");
    expect(formatDuration(0, "it")).toBe("0 min");
  });
});

describe("headlineShare e usageTone", () => {
  it("un limite raggiunto vale sempre il pieno", () => {
    const window = { usedShare: 0.4, limited: true, exhausted: false, resetsAt: null };
    const blocked = {
      enabled: true as const,
      sessionHours: 5,
      session: window,
      week: { ...window, usedShare: 0.99 },
      trial: { ...window, usedShare: 0, limited: false, over: true },
      trialOver: true,
      blocking: "trial" as const,
      forecast: null,
      audio: {
        week: { usedSeconds: 0, limitSeconds: null, usedShare: 0, limited: false, exhausted: false, resetsAt: null },
        trial: { usedSeconds: 0, limitSeconds: null, usedShare: 0, limited: false, exhausted: false, resetsAt: null },
        blocking: null,
      },
    };
    expect(headlineShare(blocked)).toBe(1);
  });

  it("i colori cambiano prima del limite", () => {
    expect(usageTone(0.5)).toBe("ok");
    expect(usageTone(0.8)).toBe("warning");
    expect(usageTone(0.95)).toBe("danger");
  });
});
