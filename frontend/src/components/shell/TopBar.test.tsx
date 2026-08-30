import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";

import "@/lib/i18n";
import { TopBar } from "./TopBar";

describe("TopBar", () => {
  it("renders the tenant selector", () => {
    render(<TopBar />);
    expect(screen.getByText("Gruppo DeliR")).toBeInTheDocument();
  });

  it("renders a global search input", () => {
    render(<TopBar />);
    expect(
      screen.getByRole("textbox", { name: /cerca|search/i }),
    ).toBeInTheDocument();
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
