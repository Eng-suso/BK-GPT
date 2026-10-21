import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import "@/lib/i18n";

import { OperationsBrief } from "./OperationsBrief";
import { PerspectiveSwitch } from "./PerspectiveSwitch";
import type { SimulationSummary } from "./simulationTypes";
import { SimulationSectionContext, type SimulationSectionValue } from "./useSimulationSection";

const act = (name: string, avg: number, count: number, queue?: number) => ({ el: `el-${name}`, name, count, wait: { avg }, ...(queue === undefined ? {} : { queue: { avg: queue, max: 3 } }) });
const summary = (byActivity: Record<string, unknown>[]) => ({ byActivity } as unknown as SimulationSummary);

function withSection(ui: React.ReactNode, section: Partial<SimulationSectionValue>) {
  return <SimulationSectionContext.Provider value={section as SimulationSectionValue}>{ui}</SimulationSectionContext.Provider>;
}

describe("prospettive (SIM-21)", () => {
  it("il selettore dice quale vista e' attiva e cambia solo su una vista diversa", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<PerspectiveSwitch value="consultant" onChange={onChange} />);
    const group = screen.getByRole("group", { name: "Prospettiva" });
    expect(group).toHaveAccessibleDescription(/non parte nessun run/);
    expect(screen.getByRole("button", { name: "Consulente" })).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "Consulente" }));
    expect(onChange).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Operations" }));
    expect(onChange).toHaveBeenCalledWith("operations");
  });

  it("Operations mostra le code per attesa totale e porta a cosa provare", async () => {
    const user = userEvent.setup();
    const selectElement = vi.fn();
    const openPanel = vi.fn();
    render(withSection(<OperationsBrief summary={summary([act("Verifica", 600, 10, 2.25), act("Approva", 60, 10), act("Archivia", 0, 10)])} />, { selectElement, openPanel, selectedElementId: null }));
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Verifica");
    expect(items[0]).toHaveTextContent("91% del totale");
    expect(items[0]).toHaveTextContent("In media 2,3 casi in coda");
    expect(items[1]).not.toHaveTextContent("in coda");
    await user.click(screen.getByRole("button", { name: "Verifica" }));
    expect(selectElement).toHaveBeenCalledWith("el-Verifica");
    await user.click(screen.getByRole("button", { name: /Cosa provare/ }));
    expect(openPanel).toHaveBeenCalledWith("insights");
  });

  it("senza attesa nel run lo dice invece di mostrare code a zero", () => {
    render(withSection(<OperationsBrief summary={summary([act("Verifica", 0, 10)])} />, {}));
    expect(screen.getByText("Nel run nessuna attività ha casi in attesa.")).toBeInTheDocument();
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
  });
});
