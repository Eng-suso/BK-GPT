import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ChatModeSelector } from "./ChatModeSelector";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

function renderSelector(overrides: Partial<React.ComponentProps<typeof ChatModeSelector>> = {}) {
  const props = {
    value: "plan" as const,
    onChange: vi.fn(),
    effort: "medium" as const,
    onEffortChange: vi.fn(),
    ...overrides,
  };
  render(<ChatModeSelector {...props} />);
  return props;
}

describe("ChatModeSelector", () => {
  it("names the active mode on the closed trigger", () => {
    renderSelector({ value: "agent" });

    // Chi non apre il menu — occhio o screen reader — deve comunque sapere in
    // che modalita' sta scrivendo.
    expect(
      screen.getByRole("button", { name: /mode\.label: mode\.agent\.label/ }),
    ).toBeInTheDocument();
  });

  it("offers the three modes as a single-choice menu", async () => {
    const user = userEvent.setup();
    renderSelector({ value: "plan" });

    await user.click(screen.getByRole("button"));

    const options = await screen.findAllByRole("menuitemradio");
    expect(options).toHaveLength(3);
    expect(
      screen.getByRole("menuitemradio", { name: /mode\.plan\.label/ }),
    ).toHaveAttribute("aria-checked", "true");
  });

  it("reports the mode the user picked", async () => {
    const user = userEvent.setup();
    const { onChange } = renderSelector({ value: "agent" });

    await user.click(screen.getByRole("button"));
    await user.click(
      await screen.findByRole("menuitemradio", { name: /mode\.edit\.label/ }),
    );

    expect(onChange).toHaveBeenCalledWith("edit");
  });

  it("carries the reasoning effort in the same menu", async () => {
    const user = userEvent.setup();
    const { onEffortChange } = renderSelector({ effort: "medium" });

    await user.click(screen.getByRole("button"));

    const levels = await screen.findAllByRole("radio");
    expect(levels).toHaveLength(3);
    expect(
      screen.getByRole("radio", { name: "effort.medium.label" }),
    ).toBeChecked();

    await user.click(screen.getByRole("radio", { name: "effort.high.label" }));
    expect(onEffortChange).toHaveBeenCalledWith("high");
  });

  it("cannot switch mode while the agent is answering", async () => {
    const user = userEvent.setup();
    const { onChange } = renderSelector({ disabled: true });

    // Il trigger disabilitato e' il contratto: in un browser non riceve
    // pointer events, quindi il menu non si apre. jsdom li consegna comunque,
    // percio' qui si verifica lo stato del bottone e che nulla arrivi al
    // chiamante, non l'assenza del menu.
    const trigger = screen.getByRole("button");
    expect(trigger).toBeDisabled();

    await user.click(trigger);
    expect(onChange).not.toHaveBeenCalled();
  });
});
