import { http } from "@/lib/http";

import {
  simulationRunSchema,
  simulationRunsSchema,
  type CreateSimulationRunInput,
  type SimulationRun,
} from "./simulationTypes";

export async function runProsimosSimulation(
  bpmnModelId: string,
  input: CreateSimulationRunInput,
): Promise<SimulationRun> {
  const raw = await http<unknown>(
    `/v1/workspace/bpmn-models/${bpmnModelId}/simulation-runs`,
    {
      method: "POST",
      body: {
        scenario_name: input.scenarioName,
        total_cases: input.totalCases,
        current_bpmn_xml: input.currentBpmnXml,
        arrival_interval_seconds: input.arrivalIntervalSeconds,
        default_task_duration_seconds: input.defaultTaskDurationSeconds,
        default_cost_per_hour: input.defaultCostPerHour,
        resource_amount: input.resourceAmount,
        resource_name: input.resourceName,
        idempotency_key: input.idempotencyKey,
      },
    },
  );

  return simulationRunSchema.parse(raw);
}

export async function listProsimosSimulationRuns(
  bpmnModelId: string,
): Promise<SimulationRun[]> {
  const raw = await http<unknown>(
    `/v1/workspace/bpmn-models/${bpmnModelId}/simulation-runs`,
  );

  return simulationRunsSchema.parse(raw);
}

export async function getProsimosSimulationRun(
  runId: number,
): Promise<SimulationRun> {
  const raw = await http<unknown>(`/v1/workspace/simulation-runs/${runId}`);

  return simulationRunSchema.parse(raw);
}
