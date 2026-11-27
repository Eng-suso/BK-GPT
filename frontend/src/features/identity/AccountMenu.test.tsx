import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { setupUser } from "@/test/user";

import { i18n } from "@/lib/i18n";

const http = vi.fn<(path: string) => Promise<unknown>>();

vi.mock("@/lib/http", () => ({ http: (path: string) => http(path) }));

const signOutOfSupabase = vi.fn<() => Promise<void>>();
vi.mock("@/lib/supabaseSession", () => ({ signOutOfSupabase: () => signOutOfSupabase() }));

const { AccountMenu } = await import("./AccountMenu");

type ApiIdentity = {
  tenant_id: string;
  auth_mode: string;
  auth_enabled: boolean;
  is_admin: boolean;
  caller_id: string;
  has_user_identity: boolean;
  allowed_tenants: string[];
  email?: string | null;
};

function identity(overrides: Partial<ApiIdentity> = {}): ApiIdentity {
  return {
    tenant_id: "studio-frascheri",
    auth_mode: "bearer",
    auth_enabled: true,
    is_admin: false,
    caller_id: "api-client",
    has_user_identity: false,
    allowed_tenants: [],
    ...overrides,
  };
}

function renderMenu() {
  const onOpenSettings = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </I18nextProvider>
  );
  render(<AccountMenu onOpenSettings={onOpenSettings} />, { wrapper });
  return { onOpenSettings };
}

beforeAll(async () => {
  await i18n.changeLanguage("it");
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("AccountMenu", () => {
  it("shows the real workspace instead of a name written in the code", async () => {
    http.mockResolvedValue(identity());
    renderMenu();

    // "Marco Bianchi" e "Gruppo DeliR" erano la prima cosa che un cliente
    // leggeva, ed erano false.
    expect(await screen.findByText("studio-frascheri", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.queryByText(/Marco Bianchi|Gruppo DeliR/)).not.toBeInTheDocument();
  });

  it("says authentication is off when it is off", async () => {
    http.mockResolvedValue(identity({ auth_enabled: false, auth_mode: "local", tenant_id: "local" }));
    renderMenu();

    expect(
      await screen.findByText("Accesso non configurato", {}, { timeout: 5000 }),
    ).toBeInTheDocument();
  });

  it("admits it does not know who the person is, and opens the settings", async () => {
    const user = setupUser();
    http.mockResolvedValue(identity());
    const { onOpenSettings } = renderMenu();

    await user.click(await screen.findByRole("button", { name: /Spazio di lavoro/ }, { timeout: 5000 }));

    expect(await screen.findByText(/non sa ancora chi sei/)).toBeInTheDocument();
    await user.click(screen.getByRole("menuitem", { name: "Impostazioni" }));
    expect(onOpenSettings).toHaveBeenCalled();
  });

  it("does not invent a workspace when the backend cannot be read", async () => {
    http.mockRejectedValue(new Error("backend giu'"));
    renderMenu();

    expect(await screen.findByText("Non disponibile", {}, { timeout: 5000 })).toBeInTheDocument();
  });

  it("with a personal session it says so and offers to sign out", async () => {
    http.mockResolvedValue(identity({ auth_mode: "supabase", caller_id: "2b1e5c1a-0000-4000-8000-000000000001", has_user_identity: true }));
    signOutOfSupabase.mockResolvedValue();
    const reload = vi.fn();
    vi.stubGlobal("location", { ...window.location, reload });
    const user = setupUser();
    renderMenu();

    await user.click(await screen.findByRole("button", { name: /Spazio di lavoro/ }, { timeout: 5000 }));
    expect(screen.getAllByText("Accesso personale").length).toBeGreaterThan(0);
    expect(screen.queryByText(/non sa ancora chi sei/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("menuitem", { name: "Esci" }));

    expect(signOutOfSupabase).toHaveBeenCalledOnce();
    await vi.waitFor(() => expect(reload).toHaveBeenCalledOnce());
    vi.unstubAllGlobals();
  });

  it("with the shared token there is no sign-out to offer", async () => {
    http.mockResolvedValue(identity());
    const user = setupUser();
    renderMenu();

    await user.click(await screen.findByRole("button", { name: /Spazio di lavoro/ }, { timeout: 5000 }));
    expect(screen.queryByRole("menuitem", { name: "Esci" })).not.toBeInTheDocument();
  });

  it("con il login personale chiama l'account con l'email, non con il suo id tecnico", async () => {
    http.mockResolvedValue(
      identity({
        tenant_id: "acct-6f1c2b0e-0000-4000-8000-000000000001",
        auth_mode: "supabase",
        caller_id: "6f1c2b0e-0000-4000-8000-000000000001",
        has_user_identity: true,
        email: "anna@studio.it",
      }),
    );
    renderMenu();
    const user = setupUser();

    await user.click(await screen.findByRole("button", { name: /anna@studio\.it/ }));

    expect(await screen.findByText("Clienti, conversazioni e memoria di questo account sono solo tuoi.")).toBeInTheDocument();
    expect(screen.queryByText(/acct-/)).not.toBeInTheDocument();
  });
});
