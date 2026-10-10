import React from "react";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import "@/lib/i18n";

import { ReplicationDelta } from "./ReplicationDelta";
import type { SimulationRun } from "./simulationTypes";

const run = (id: number, group: string, index: number, seed: number, cycle: number) => ({
  id, status: "completed", scenario_name: group, request: { replication_group: group, replication_index: index, seed },
  summary: { cycle: { avg: cycle }, waiting: { avg: 600 }, cost: { perCase: 50 }, throughputPerHour: 2 },
}) as unknown as SimulationRun;

describe("ReplicationDelta", () => {
  it("shows each difference with its interval and says when it is certain", () => {
    const a = [run(1, "a", 1, 7, 3600), run(2, "a", 2, 8, 4200), run(3, "a", 3, 9, 3000)];
    const b = [run(4, "b", 1, 7, 3000), run(5, "b", 2, 8, 3660), run(6, "b", 3, 9, 2340)];
    render(<ReplicationDelta runA={a[0]} runB={b[0]} runs={[...a, ...b]} />);

    const section = screen.getByRole("region", { name: "Differenza sulle ripetizioni" });
    expect(within(section).getByText(/stessi seed/)).toBeTruthy();
    const cycle = within(section).getByRole("row", { name: /Durata media del caso/ });
    expect(within(cycle).getByText("B migliore")).toBeTruthy();
    expect(within(cycle).getByText(/^−.* ± /)).toBeTruthy();
    const waiting = within(section).getByRole("row", { name: /Attesa media/ });
    expect(within(waiting).getByText("Differenza non certa")).toBeTruthy();
  });

  it("explains how to get a reliable comparison when a scenario is not repeated", () => {
    const a = [run(1, "a", 1, 7, 3600), run(2, "a", 2, 8, 4200)];
    const single = { ...run(3, "", 0, 1, 3000), request: {} } as SimulationRun;
    render(<ReplicationDelta runA={a[0]} runB={single} runs={[...a, single]} />);
    expect(screen.getByText(/ripeti entrambi gli scenari almeno due volte/)).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Differenza sulle ripetizioni" })).toBeNull();
  });
});
