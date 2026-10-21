import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import "@/lib/i18n";

import { OperationsBrief } from "./OperationsBrief";
import { PerspectiveSwitch } from "./PerspectiveSwitch";
import type { SimulationInsights, TaskStat } from "./simulationResults";
import { SimulationSectionContext, type SimulationSectionValue } from "./useSimulationSection";

const task = (name: string, avgWaitingSec: number, volume: number): TaskStat => ({
  name, elementId: `el-${name}`, volume, avgWaitingSec, avgProcessingSec: 60, avgCycleSec: avgWaitingSec + 60, avgCost: 1, totalCost: volume, waitingShare: 0,
});

const insights = (tasks: TaskStat[]): SimulationInsights => ({
  hasData: true, casesCompleted: 10, avgCycleSec: 0, avgProcessingSec: 0, avgWaitingSec: 0, waitingShare: 0,
  totalCost: 0, avgCostPerCase: 0, resources: [], tasks, bottleneck: null, bottleneckElementId: null, files: [],
} as SimulationInsights);

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
    render(withSection(<OperationsBrief insights={insights([task("Verifica", 600, 10), task("Approva", 60, 10), task("Archivia", 0, 10)])} />, { selectElement, openPanel, selectedElementId: null }));
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Verifica");
    expect(items[0]).toHaveTextContent("91% del totale");
    await user.click(screen.getByRole("button", { name: "Verifica" }));
    expect(selectElement).toHaveBeenCalledWith("el-Verifica");
    await user.click(screen.getByRole("button", { name: /Cosa provare/ }));
    expect(openPanel).toHaveBeenCalledWith("insights");
  });

  it("senza attesa nel run lo dice invece di mostrare code a zero", () => {
    render(withSection(<OperationsBrief insights={insights([task("Verifica", 0, 10)])} />, {}));
    expect(screen.getByText("Nel run nessuna attività ha casi in attesa.")).toBeInTheDocument();
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
  });
});
