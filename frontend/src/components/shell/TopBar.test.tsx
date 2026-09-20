import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { setupUser } from "@/test/user";

import "@/lib/i18n";
import { TopBar } from "./TopBar";

describe("TopBar", () => {
  it("renders the tenant selector", () => {
    render(<TopBar />);
    expect(screen.getByText("Gruppo DeliR")).toBeInTheDocument();
  });

  it("opens the workspace search instead of pretending to be a field", async () => {
    const user = setupUser();
    const onOpenSearch = vi.fn();
    render(<TopBar onOpenSearch={onOpenSearch} />);

    // Un input qui sembrerebbe cercare nella pagina: e' un comando che apre il
    // pannello di ricerca, e da tastiera si annuncia come tale.
    const trigger = screen.getAllByRole("button", { name: /cerca|search/i })[0];
    expect(trigger).toHaveAttribute("aria-haspopup", "dialog");
    await user.click(trigger);

    expect(onOpenSearch).toHaveBeenCalledTimes(1);
  });

  it("renders the notifications and user buttons", () => {
    render(<TopBar />);
    expect(
      screen.getByRole("button", { name: /notifiche/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /marco bianchi/i }),
    ).toBeInTheDocument();
  });
});
