import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { setupUser } from "@/test/user";

import "@/lib/i18n";
import { TopBar } from "./TopBar";

// La campanella legge gli avvisi dal backend: qui interessa la barra, non il
// feed, quindi la risposta e' vuota e silenziosa.
vi.mock("@/lib/http", () => ({
  http: vi.fn().mockResolvedValue({ items: [], unread: 0 }),
}));

function renderTopBar(props: React.ComponentProps<typeof TopBar> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  render(<TopBar {...props} />, { wrapper });
}

describe("TopBar", () => {
  it("renders the tenant selector", () => {
    renderTopBar();
    expect(screen.getByText("Gruppo DeliR")).toBeInTheDocument();
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

  it("renders the notifications and user buttons", () => {
    renderTopBar();
    expect(screen.getByRole("button", { name: /avvisi|notifications/i })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /marco bianchi/i }),
    ).toBeInTheDocument();
  });
});
