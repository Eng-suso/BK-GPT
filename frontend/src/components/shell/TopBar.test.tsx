import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { setupUser } from "@/test/user";

import "@/lib/i18n";
import { TopBar } from "./TopBar";

// La barra legge due cose dal backend: gli avvisi e lo spazio di lavoro. Qui
// interessa la barra, non i due feed, quindi rispondono il minimo vero.
vi.mock("@/lib/http", () => ({
  http: vi.fn(async (path: string) =>
    path.includes("/auth/me")
      ? {
          tenant_id: "studio-frascheri",
          auth_mode: "bearer",
          auth_enabled: true,
          is_admin: false,
          caller_id: "api-client",
          has_user_identity: false,
          allowed_tenants: [],
        }
      : { items: [], unread: 0 },
  ),
}));

function renderTopBar(props: React.ComponentProps<typeof TopBar> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  render(<TopBar {...props} />, { wrapper });
}

describe("TopBar", () => {
  it("names the real workspace, not one written in the code", async () => {
    renderTopBar();

    // Prima diceva "Gruppo DeliR" a chiunque, compreso un cliente che si
    // chiama diversamente.
    expect(await screen.findByText("studio-frascheri", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.queryByText("Gruppo DeliR")).not.toBeInTheDocument();
  });

  it("opens the workspace search instead of pretending to be a field", async () => {
    const user = setupUser();
    const onOpenSearch = vi.fn();
    renderTopBar({ onOpenSearch });

    // Un input qui sembrerebbe cercare nella pagina: e' un comando che apre il
    // pannello di ricerca, e da tastiera si annuncia come tale.
    const trigger = screen.getAllByRole("button", { name: /cerca|search/i })[0];
    expect(trigger).toHaveAttribute("aria-haspopup", "dialog");
    await user.click(trigger);

    expect(onOpenSearch).toHaveBeenCalledTimes(1);
  });

  it("renders the notifications and the account control", async () => {
    renderTopBar();
    expect(screen.getByRole("button", { name: /avvisi|notifications/i })).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: /spazio di lavoro|workspace/i }, { timeout: 5000 }),
    ).toBeInTheDocument();
  });
});
