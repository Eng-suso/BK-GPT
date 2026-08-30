import { z } from "zod";

export const simulationRunSchema = z.object({
  id: z.number(),
  bpmn_model_id: z.string(),
  process_id: z.string(),
  scenario_name: z.string(),
  engine: z.string(),
  status: z.enum(["pending", "completed", "failed"]),
  idempotency_key: z.string().nullable().optional(),
  request: z.record(z.string(), z.unknown()),
  scenario: z.record(z.string(), z.unknown()),
  result: z.record(z.string(), z.unknown()),
  outputs: z.array(z.string()),
  error: z.string().nullable(),
  created_at: z.string(),
  completed_at: z.string().nullable(),
});

export const simulationRunsSchema = z.array(simulationRunSchema);

export type SimulationRun = z.infer<typeof simulationRunSchema>;

export type CreateSimulationRunInput = {
  scenarioName: string;
  totalCases: number;
  currentBpmnXml: string | null;
  arrivalIntervalSeconds: number;
  defaultTaskDurationSeconds: number;
  defaultCostPerHour: number;
  resourceAmount: number;
  resourceName: string;
  idempotencyKey?: string;
};
