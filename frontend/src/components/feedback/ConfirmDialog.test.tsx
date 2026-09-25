import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { i18n } from "@/lib/i18n";

import { ConfirmDialog } from "./ConfirmDialog";

function setup(onConfirm = vi.fn()) {
  const onOpenChange = vi.fn();
  render(
    <ConfirmDialog
      open
      onOpenChange={onOpenChange}
      destructive
      title="Svuotare tutta la cronologia?"
      description="Spariscono tutte le conversazioni. Non si torna indietro."
      confirmLabel="Svuota la cronologia"
      onConfirm={onConfirm}
    />,
  );
  return { onConfirm, onOpenChange };
}

describe("ConfirmDialog", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("it");
  });

  it("dice cosa si perde prima di chiederlo", () => {
    setup();

    expect(screen.getByText("Svuotare tutta la cronologia?")).toBeInTheDocument();
    expect(
      screen.getByText("Spariscono tutte le conversazioni. Non si torna indietro."),
    ).toBeInTheDocument();
  });

  it("annullare non cancella niente", async () => {
    const user = userEvent.setup();
    const { onConfirm, onOpenChange } = setup();

    await user.click(screen.getByRole("button", { name: "Annulla" }));

    expect(onConfirm).not.toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("cancella solo quando si conferma, e poi si chiude", async () => {
    const user = userEvent.setup();
    const { onConfirm, onOpenChange } = setup();

    await user.click(screen.getByRole("button", { name: "Svuota la cronologia" }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("non parte due volte se si clicca due volte", async () => {
    const user = userEvent.setup();
    let resolve: () => void = () => {};
    const onConfirm = vi.fn(() => new Promise<void>((r) => { resolve = r; }));
    setup(onConfirm);

    const button = screen.getByRole("button", { name: "Svuota la cronologia" });
    await user.click(button);
    expect(button).toBeDisabled();

    resolve();
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
