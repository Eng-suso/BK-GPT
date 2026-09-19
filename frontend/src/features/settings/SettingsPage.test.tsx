import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setupUser } from "@/test/user";

import { i18n } from "@/lib/i18n";

vi.mock("@/features/status/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/status/api")>(
    "@/features/status/api",
  );
  return {
    ...actual,
    fetchDegradation: () => Promise.resolve({ status: "ok", counters: {} }),
    fetchQueueHealth: () => Promise.resolve({ status: "not_configured" }),
  };
});

const { SettingsPage } = await import("./SettingsPage");

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>
  );
  render(<SettingsPage />, { wrapper });
}

beforeEach(async () => {
  await i18n.changeLanguage("it");
});

afterEach(async () => {
  await i18n.changeLanguage("it");
});

describe("SettingsPage", () => {
  it("switches the interface language and remembers it", async () => {
    const user = setupUser();
    renderPage();

    await user.click(screen.getByRole("radio", { name: "Inglese" }));

    // La scelta cambia l'interfaccia subito, non al prossimo caricamento...
    expect(await screen.findByRole("heading", { name: "Interface language" })).toBeInTheDocument();
    expect(i18n.language).toBe("en");
    // ...e resta scelta al prossimo accesso.
    expect(window.localStorage.getItem("delir-language")).toBe("en");
  });

  it("marks the language in use as selected", () => {
    renderPage();

    expect(screen.getByRole("radio", { name: "Italiano" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Inglese" })).not.toBeChecked();
  });

  it("checks the service instead of just printing the endpoint", async () => {
    renderPage();

    expect(await screen.findByText(/Il backend risponde/)).toBeInTheDocument();
    expect(screen.getByText(/Code non configurate/)).toBeInTheDocument();
  });
});
