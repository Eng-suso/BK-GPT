import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MessageBubble } from "./MessageBubble";
import type { ChatMessage } from "../types";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "it" } }),
}));

const message: ChatMessage = {
  role: "assistant",
  content: "",
  activity: [{ key: "search", label: "Ricerca in corso", status: "running", startedAtMs: 0 }],
};

describe("activity disclosure", () => {
  it("opens while working, collapses on first answer, and preserves manual reopening", () => {
    const { rerender } = render(<MessageBubble message={message} />);
    const toggle = screen.getByRole("button", { name: /status.progressLabel/ });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    rerender(<MessageBubble message={{ ...message, activity: [...message.activity!] }} />);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    rerender(<MessageBubble message={{ ...message, content: "Ecco" }} />);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(document.getElementById(toggle.getAttribute("aria-controls")!)).toHaveAttribute("inert");
    fireEvent.click(toggle);
    rerender(<MessageBubble message={{ ...message, content: "Ecco la risposta" }} />);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it("starts collapsed for an existing answer and omits the control without activity", () => {
    const { rerender } = render(<MessageBubble message={{ ...message, content: "Risposta" }} />);
    expect(screen.getByRole("button", { name: /status.progressLabel/ })).toHaveAttribute("aria-expanded", "false");
    rerender(<MessageBubble message={{ role: "assistant", content: "Risposta" }} />);
    expect(screen.queryByRole("button", { name: /status.progressLabel/ })).toBeNull();
  });
});

