import { describe, expect, it } from "vitest";

import {
  formatCurrency,
  formatDuration,
  heatBucket,
  readSimulationInsights,
  topBottleneckElementIds,
  type SimulationInsights,
} from "./simulationResults";

const RESULT = {
  ResourceUtilization: [
    {
      "Resource ID": "delir-resource-operator",
      "Resource name": "Operatore",
      "Utilization Ratio": 0.9738138739,
      "Tasks Allocated": 200,
      "Pool name": "Operatore",
    },
  ],
  IndividualTaskStatistics: [
    {
      Name: "Raccolta dati",
      Count: 100,
      "Avg Waiting Time": 41293.59,
      "Avg Processing Time": 896.13,
      "Avg Cycle Time": 42189.72,
      "Avg Cost": 8.71,
      "Total Cost": 871.24,
    },
    {
      Name: "Validazione",
      Count: 100,
      "Avg Waiting Time": 53120.21,
      "Avg Processing Time": 906.85,
      "Avg Cycle Time": 54027.07,
      "Avg Cost": 8.81,
      "Total Cost": 881.66,
    },
  ],
  OverallScenarioStatistics: [
    { KPI: "cycle_time", Average: 97914.98, "Trace Ocurrences": 100 },
    { KPI: "processing_time", Average: 3501.17, "Trace Ocurrences": 100 },
    { KPI: "waiting_time", Average: 94413.81, "Trace Ocurrences": 100 },
  ],
  StatsFilename: "stats_x.csv",
  LogsFilename: "logs_x.csv",
};

describe("readSimulationInsights", () => {
  it("summarises the Prosimos payload", () => {
    const insights = readSimulationInsights(RESULT);

    expect(insights.hasData).toBe(true);
    expect(insights.casesCompleted).toBe(100);
    expect(insights.avgCycleSec).toBeCloseTo(97914.98);
    expect(insights.waitingShare).toBeGreaterThan(0.9);
    expect(insights.totalCost).toBeCloseTo(1752.9);
    expect(insights.avgCostPerCase).toBeCloseTo(17.529);
    expect(insights.resources[0].utilizationPct).toBe(97);
    expect(insights.bottleneck?.name).toBe("Validazione");
  });

  it("decodes doubly json-encoded sections", () => {
    const wrapped = {
      ...RESULT,
      IndividualTaskStatistics: JSON.stringify(
        JSON.stringify(RESULT.IndividualTaskStatistics),
      ),
    };
    expect(readSimulationInsights(wrapped).tasks).toHaveLength(2);
  });

  it("returns empty insights for junk", () => {
    expect(readSimulationInsights({}).hasData).toBe(false);
    expect(readSimulationInsights(null).hasData).toBe(false);
  });

  it("maps task stats to BPMN element ids by name", () => {
    const bpmnXml = `<?xml version="1.0"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <bpmn:process id="P">
    <bpmn:userTask id="Task_Raccolta" name="Raccolta dati" />
    <bpmn:serviceTask id="Task_Val" name="Validazione" />
  </bpmn:process>
</bpmn:definitions>`;
    const insights = readSimulationInsights(RESULT, { bpmnXml });
    expect(insights.tasks.find((t) => t.name === "Raccolta dati")?.elementId).toBe(
      "Task_Raccolta",
    );
    expect(insights.bottleneckElementId).toBe("Task_Val");
  });
});

describe("formatDuration", () => {
  it("shows the two largest units", () => {
    expect(formatDuration(45)).toBe("45 s");
    expect(formatDuration(750)).toBe("12 min");
    expect(formatDuration(9540)).toBe("2h 39 min");
    expect(formatDuration(97914)).toBe("1g 3h");
    expect(formatDuration(250000)).toBe("2g 21h");
    expect(formatDuration(9540, "en")).toBe("2h 39 min");
  });
});

describe("formatCurrency", () => {
  it("drops decimals above 1000", () => {
    expect(formatCurrency(1752.9, "en")).toBe("€1,753");
    expect(formatCurrency(17.53, "en")).toBe("€17.53");
  });
});

describe("heatBucket", () => {
  it("maps waiting time to 0–4 by share of the worst", () => {
    expect(heatBucket(0, 100)).toBe(0);
    expect(heatBucket(10, 100)).toBe(0);
    expect(heatBucket(50, 100)).toBe(2);
    expect(heatBucket(100, 100)).toBe(4);
    expect(heatBucket(5, 0)).toBe(0);
  });
});

describe("topBottleneckElementIds", () => {
  it("returns the worst-waiting mapped tasks, capped", () => {
    const insights = {
      hasData: true,
      tasks: [
        { name: "A", elementId: "a", avgWaitingSec: 10 },
        { name: "B", elementId: "b", avgWaitingSec: 90 },
        { name: "C", elementId: "c", avgWaitingSec: 40 },
        { name: "D", elementId: null, avgWaitingSec: 999 },
        { name: "E", elementId: "e", avgWaitingSec: 0 },
      ],
    } as unknown as SimulationInsights;
    expect(topBottleneckElementIds(insights, 2)).toEqual(["b", "c"]);
  });
});
