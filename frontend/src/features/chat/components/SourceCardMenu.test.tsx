import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import "@/lib/i18n";
import { SourceCardMenu } from "./SourceCardMenu";

describe("SourceCardMenu", () => {
  it("mostra la proposta e la applica con un clic", async () => {
    const onApply = vi.fn();
    render(
      <SourceCardMenu
        fileName="Procedura acquisti.pdf"
        roles={["process_evidence"]}
        suggestion={["process_evidence", "policy"]}
        onApply={onApply}
        onKeep={vi.fn()}
      />,
    );

    const trigger = screen.getByRole("button", { name: /Procedura acquisti\.pdf, a cosa serve/ });
    expect(trigger).toHaveTextContent("Sembra: Come si lavora, Regole da rispettare");
    await userEvent.click(trigger);
    await userEvent.click(screen.getByRole("menuitem", { name: /Usa la proposta/ }));

    expect(onApply).toHaveBeenCalledWith(["process_evidence", "policy"]);
  });

  it("l'ultimo ruolo non si toglie, un altro si aggiunge", async () => {
    const onApply = vi.fn();
    render(
      <SourceCardMenu
        fileName="ordini.xlsx"
        roles={["operational_data"]}
        suggestion={null}
        onApply={onApply}
        onKeep={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /ordini\.xlsx/ }));
    expect(screen.getByRole("menuitemcheckbox", { name: "Dati operativi" })).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(screen.getByRole("menuitemcheckbox", { name: "Contesto" }));

    expect(onApply).toHaveBeenCalledWith(["operational_data", "context"]);
  });

  it("Salva tra le Fonti chiede di tenere il file", async () => {
    const onKeep = vi.fn();
    render(
      <SourceCardMenu fileName="a.pdf" roles={["context"]} suggestion={null} onApply={vi.fn()} onKeep={onKeep} />,
    );

    await userEvent.click(screen.getByRole("button", { name: /a\.pdf/ }));
    await userEvent.click(screen.getByRole("menuitem", { name: /Salva tra le Fonti/ }));

    expect(onKeep).toHaveBeenCalledOnce();
  });
});
