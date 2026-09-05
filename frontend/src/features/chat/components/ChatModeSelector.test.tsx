import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ChatModeSelector } from "./ChatModeSelector";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe("ChatModeSelector", () => {
  it("exposes the modes as a radiogroup with the active one checked", () => {
    render(<ChatModeSelector value="plan" onChange={() => {}} />);

    const options = screen.getAllByRole("radio");
    expect(options).toHaveLength(3);
    expect(screen.getByRole("radio", { name: /plan/ })).toBeChecked();
    expect(screen.getByRole("radio", { name: /agent/ })).not.toBeChecked();
  });

  it("keeps one tab stop and moves between modes with the arrow keys", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ChatModeSelector value="plan" onChange={onChange} />);

    // Roving tabindex: only the active option is reachable with Tab.
    await user.tab();
    expect(screen.getByRole("radio", { name: /plan/ })).toHaveFocus();

    await user.keyboard("{ArrowRight}");
    expect(onChange).toHaveBeenCalledWith("edit");

    await user.keyboard("{ArrowLeft}");
    // Wraps around to the last mode rather than dead-ending on the first.
    expect(onChange).toHaveBeenCalledWith("agent");
  });

  it("reports the mode the user clicked", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ChatModeSelector value="agent" onChange={onChange} />);

    await user.click(screen.getByRole("radio", { name: /edit/ }));

    expect(onChange).toHaveBeenCalledWith("edit");
  });

  it("cannot switch mode while the agent is answering", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ChatModeSelector value="agent" onChange={onChange} disabled />);

    await user.click(screen.getByRole("radio", { name: /plan/ }));

    expect(onChange).not.toHaveBeenCalled();
  });
});
