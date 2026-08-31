import { http } from "@/lib/http";

import {
  scenarioProvenanceSchema,
  scenarioTemplateSchema,
  simulationReplaySchema,
  simulationRunSchema,
  simulationRunsSchema,
  type CreateSimulationRunInput,
  type ScenarioProvenance,
  type ScenarioTemplate,
  type SimulationReplay,
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
        resources: input.resources?.map((r) => ({
          id: r.id,
          name: r.name,
          cost_per_hour: r.costPerHour,
          amount: r.amount,
        })),
        tasks: input.tasks?.map((task) => ({
          element_id: task.elementId,
          mean_seconds: task.meanSeconds,
          distribution: task.distribution,
          resource_id: task.resourceId,
        })),
        gateways: input.gateways?.map((g) => ({
          element_id: g.elementId,
          branches: g.branches.map((b) => ({
            flow_id: b.flowId,
            probability: b.probability,
          })),
        })),
        idempotency_key: input.idempotencyKey,
      },
    },
  );

  return simulationRunSchema.parse(raw);
}

export async function fetchScenarioTemplate(
  bpmnModelId: string,
  currentBpmnXml: string | null,
): Promise<ScenarioTemplate> {
  const raw = await http<unknown>(
    `/v1/workspace/bpmn-models/${bpmnModelId}/simulation-template`,
    { method: "POST", body: { current_bpmn_xml: currentBpmnXml } },
  );

  return scenarioTemplateSchema.parse(raw);
}

/** Where each simulable element came from — discovery evidence or inference. */
export async function fetchScenarioProvenance(
  bpmnModelId: string,
  currentBpmnXml: string | null,
): Promise<ScenarioProvenance> {
  const raw = await http<unknown>(
    `/v1/workspace/bpmn-models/${bpmnModelId}/simulation-provenance`,
    { method: "POST", body: { current_bpmn_xml: currentBpmnXml } },
  );

  return scenarioProvenanceSchema.parse(raw);
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

/** The heavy replay artifact — only the replay / dashboard screens need it. */
export async function getSimulationReplay(
  runId: number,
): Promise<SimulationReplay> {
  const raw = await http<unknown>(
    `/v1/workspace/simulation-runs/${runId}/replay`,
  );

  return simulationReplaySchema.parse(raw);
}
