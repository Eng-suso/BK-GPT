import React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import "@/lib/i18n";

import { SensitivityPanel } from "./SensitivityTornado";
import type { SimulationRun } from "./simulationTypes";

function run(id: number, sensitivity: Record<string, unknown> | null, cycle?: number, status: SimulationRun["status"] = "completed"): SimulationRun {
  return {
    id,
    status,
    request: { sensitivity_study: "s1", sensitivity },
    summary: cycle === undefined ? null : { cycle: { avg: cycle }, cost: { perCase: cycle / 60 } },
  } as unknown as SimulationRun;
}

const mark = (kind: string, element_id: string | null, label: string, direction: "low" | "high") => ({ kind, element_id, label, direction, delta: 0.2 });

const STUDY = [
  run(1, null, 3600),
  run(2, mark("duration", "B", "Verifica", "low"), 3590),
  run(3, mark("duration", "B", "Verifica", "high"), 3610),
  run(4, mark("arrival", null, "Tempo fra due arrivi", "low"), 7200),
  run(5, mark("arrival", null, "Tempo fra due arrivi", "high"), 2400),
];

describe("sensitivity tornado (SIM-25)", () => {
  it("ranks assumptions by effect, flags noise and asks about the decisive ones", async () => {
    const user = userEvent.setup();
    render(<SensitivityPanel run={STUDY[0]} runs={STUDY} />);

    const rows = screen.getAllByRole("row").filter((row) => row.hasAttribute("data-sim-tornado-row"));
    expect(rows.map((row) => within(row).getByRole("rowheader").textContent)).toEqual(["Tempo fra due arriviArrivi", "VerificaDurata"]);
    expect(within(rows[1]).getByText("dentro il rumore")).toBeInTheDocument();
    expect(screen.getByText("5 di 5 simulazioni completate.")).toBeInTheDocument();
    expect(screen.getByText("Quanti casi arrivano davvero, e in quali giorni e ore?")).toBeInTheDocument();
    expect(screen.queryByText(/Quanto dura davvero «Verifica»/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Costo per caso" }));
    expect(screen.getByRole("button", { name: "Costo per caso" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/Valore dello scenario: 60/)).toBeInTheDocument();
  });

  it("waits for the central run and the variants", () => {
    const partial = [run(1, null, undefined, "pending"), run(2, mark("duration", "B", "Verifica", "low"), undefined, "pending")];
    render(<SensitivityPanel run={partial[0]} runs={partial} />);
    expect(screen.getByText("0 di 2 simulazioni completate.")).toBeInTheDocument();
    expect(screen.getByText(/Il tornado compare quando/)).toBeInTheDocument();
  });

  it("renders nothing outside a study", () => {
    const { container } = render(<SensitivityPanel run={{ ...STUDY[0], request: {} } as SimulationRun} runs={STUDY} />);
    expect(container).toBeEmptyDOMElement();
  });
});
