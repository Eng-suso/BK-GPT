import { describe, expect, it } from "vitest";

import { isPanelVisible, panelInPerspective, parsePerspective, queueHotspots } from "./perspective";
import type { SimulationInsights, TaskStat } from "./simulationResults";

const task = (name: string, avgWaitingSec: number, volume: number): TaskStat => ({
  name, elementId: name, volume, avgWaitingSec, avgProcessingSec: 60, avgCycleSec: avgWaitingSec + 60, avgCost: 1, totalCost: volume, waitingShare: 0,
});

const insights = (tasks: TaskStat[]): SimulationInsights => ({
  hasData: true, casesCompleted: 10, avgCycleSec: 0, avgProcessingSec: 0, avgWaitingSec: 0, waitingShare: 0,
  totalCost: 0, avgCostPerCase: 0, resources: [], tasks, bottleneck: null, bottleneckElementId: null, files: [],
} as SimulationInsights);

describe("perspective (SIM-21)", () => {
  it("parte dal consulente se la prospettiva manca o non e' valida", () => {
    expect(parsePerspective(null)).toBe("consultant");
    expect(parsePerspective("boh")).toBe("consultant");
    expect(parsePerspective("operations")).toBe("operations");
  });

  it("toglie a Operations i pannelli che configurano modello e dati", () => {
    for (const panel of ["scenario", "scenarios", "eventLog"] as const) {
      expect(isPanelVisible(panel, "operations")).toBe(false);
      expect(isPanelVisible(panel, "consultant")).toBe(true);
      expect(panelInPerspective(panel, "operations")).toBeNull();
      expect(panelInPerspective(panel, "consultant")).toBe(panel);
    }
    for (const panel of ["overview", "heatmap", "compare", "insights", "activity", "widget"] as const) {
      expect(panelInPerspective(panel, "operations")).toBe(panel);
    }
    expect(panelInPerspective(null, "operations")).toBeNull();
  });

  it("ordina le code per attesa totale e ne da' la quota", () => {
    const rows = queueHotspots(insights([task("A", 100, 1), task("B", 10, 50), task("C", 0, 99), task("D", 50, 4)]));
    expect(rows.map((row) => row.task.name)).toEqual(["B", "D", "A"]);
    expect(rows[0].share).toBeCloseTo(500 / 800);
    expect(rows.reduce((acc, row) => acc + row.share, 0)).toBeCloseTo(1);
  });

  it("senza attesa misurata non inventa code", () => {
    expect(queueHotspots(insights([task("A", 0, 10)]))).toEqual([]);
    expect(queueHotspots(insights([]))).toEqual([]);
  });

  it("rispetta il limite", () => {
    expect(queueHotspots(insights([task("A", 1, 1), task("B", 2, 1), task("C", 3, 1)]), 2)).toHaveLength(2);
  });
});
