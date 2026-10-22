import { describe, expect, it } from "vitest";

import { isPanelVisible, panelInPerspective, parsePerspective, queueHotspots } from "./perspective";

const act = (name: string, avg: number, count: number, queue?: number) => ({ el: `el-${name}`, name, count, wait: { avg }, ...(queue === undefined ? {} : { queue: { avg: queue, max: 3 } }) });

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
    const rows = queueHotspots([act("A", 100, 1), act("B", 10, 50, 1.5), act("C", 0, 99), act("D", 50, 4)]);
    expect(rows.map((row) => row.name)).toEqual(["B", "D", "A"]);
    expect(rows[0]).toMatchObject({ el: "el-B", avgWaitSec: 10, count: 50, queueAvg: 1.5 });
    expect(rows[1].queueAvg).toBeNull();
    expect(rows[0].share).toBeCloseTo(500 / 800);
    expect(rows.reduce((acc, row) => acc + row.share, 0)).toBeCloseTo(1);
  });

  it("senza attesa misurata non inventa code", () => {
    expect(queueHotspots([act("A", 0, 10)])).toEqual([]);
    expect(queueHotspots([{ name: "X" }])).toEqual([]);
    expect(queueHotspots(null)).toEqual([]);
  });

  it("rispetta il limite", () => {
    expect(queueHotspots([act("A", 1, 1), act("B", 2, 1), act("C", 3, 1)], 2)).toHaveLength(2);
  });
});
