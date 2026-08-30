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

export const scenarioTemplateSchema = z.object({
  tasks: z.array(
    z.object({ element_id: z.string(), name: z.string(), type: z.string() }),
  ),
  gateways: z.array(
    z.object({
      element_id: z.string(),
      name: z.string(),
      type: z.string(),
      branches: z.array(
        z.object({
          flow_id: z.string(),
          flow_name: z.string(),
          target_name: z.string(),
        }),
      ),
    }),
  ),
});

export type ScenarioTemplate = z.infer<typeof scenarioTemplateSchema>;
export type ScenarioTemplateTask = ScenarioTemplate["tasks"][number];
export type ScenarioTemplateGateway = ScenarioTemplate["gateways"][number];

export type SimResourceInput = {
  id: string;
  name: string;
  costPerHour: number;
  amount: number;
};

export type SimTaskInput = {
  elementId: string;
  meanSeconds: number;
  distribution: "norm" | "expon" | "fixed";
  resourceId: string | null;
};

export type SimGatewayInput = {
  elementId: string;
  branches: { flowId: string; probability: number }[];
};

export type CreateSimulationRunInput = {
  scenarioName: string;
  totalCases: number;
  currentBpmnXml: string | null;
  arrivalIntervalSeconds: number;
  defaultTaskDurationSeconds: number;
  defaultCostPerHour: number;
  resourceAmount: number;
  resourceName: string;
  resources?: SimResourceInput[];
  tasks?: SimTaskInput[];
  gateways?: SimGatewayInput[];
  idempotencyKey?: string;
};
