import type { CreateSimulationRunInput } from "./simulationTypes";

/** Global-default scenario form state (Phase 1 — per-element config lands later). */
export type ScenarioDraft = {
  scenarioName: string;
  totalCases: number;
  arrivalIntervalMinutes: number;
  taskDurationMinutes: number;
  costPerHour: number;
  resourceAmount: number;
  resourceName: string;
};

export const DEFAULT_SCENARIO: ScenarioDraft = {
  scenarioName: "Baseline AS-IS",
  totalCases: 100,
  arrivalIntervalMinutes: 30,
  taskDurationMinutes: 15,
  costPerHour: 35,
  resourceAmount: 1,
  resourceName: "Operatore",
};

export function scenarioToInput(
  draft: ScenarioDraft,
  currentBpmnXml: string | null,
): Omit<CreateSimulationRunInput, "idempotencyKey"> {
  return {
    scenarioName: draft.scenarioName,
    totalCases: draft.totalCases,
    currentBpmnXml,
    arrivalIntervalSeconds: Math.max(1, draft.arrivalIntervalMinutes * 60),
    defaultTaskDurationSeconds: Math.max(1, draft.taskDurationMinutes * 60),
    defaultCostPerHour: draft.costPerHour,
    resourceAmount: draft.resourceAmount,
    resourceName: draft.resourceName,
  };
}
